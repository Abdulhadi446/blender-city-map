"""flyover.py — Phase B pilot (FLYOVER agent).

Builds ONLY the NE quadrant of the highway ring + its ramp, per layout.json:

  FLY_RING   segments H_07 (1400,600)->(1400,1400) and H_08 (1400,1400)->(600,1400)
             with the 120 m rounded corner between them, deck_width 34, deck_z 8.
  FLY_RAMPS  ramp X_N_600 (600,1400,8) -> (600,1200,0), deck_width 18, <= 4 %.
  Substructure: instanced piers / caps / footings, ~35 m spacing, arc piers.
  Ground band: 10 m service road under the ring centreline + gravel/dirt verges.

Run headless:  cd /home/abdulhadi/Work/city && blender -b -P modules/flyover.py
"""
import math
import os
import sys

sys.path.insert(0, "/home/abdulhadi/Work/city/modules")
import citykit as ck

import bpy
from mathutils import Matrix, Vector

BLEND = os.path.join(ck.OUT_DIR, "flyover.blend")
PREV_A = os.path.join(ck.OUT_DIR, "flyover_preview.png")
PREV_B = os.path.join(ck.OUT_DIR, "flyover_ground_preview.png")

# ---------------------------------------------------------------- constants
DECK_Z = 8.0
DECK_HW = 17.0              # 34 m wide
DECK_T = 1.5                # slab depth -> soffit 6.5
SOFFIT = DECK_Z - DECK_T
LANE = 3.5
MEDIAN_HW = 2.0             # 4.0 m median zone
SHOULDER_OUT = 15.0         # |u| beyond this = shoulder/edge band
BAR_W = 0.6
BAR_H = 1.05
SEG = 6.0                   # barrier segment length (instanced)
DECK_STEP = 3.0             # deck sweep sampling

RAMP_W = 18.0
RAMP_END_W = 24.0           # matches arterial corridor envelope (halfwidth 12)
RAMP_END_FLARE_Y = 1212.0   # flare starts here, lands 24 m wide at y=1200
RAMP_BULGE = 40.0           # eastward sweep (keeps gradient under 4 %)
RAMP_Z0 = 7.99              # ramp top inside the ring deck (1 cm below deck top)
RAMP_T = 1.2                # ramp slab depth
ROAD_HW = 5.0               # service road half width (10 m road)
VERGE_HW = 20.0             # prepared ground out to 20 m
PIER_SPACING = 35.0
FOOT_TOP = 0.6
CAP_D = 1.4                 # ring cap beam depth
COL_BASE = (2.4, 1.2)       # tapered column base section (transverse, longitudinal)
COL_TOP = (2.0, 1.0)
PIER_U = 9.0                # column lateral offset (service road passes between)
GRAD_MAX = 0.04


def log(msg):
    print("[flyover] " + msg, flush=True)


# ---------------------------------------------------------------- reset / collections
def reset():
    root = bpy.data.collections.get("Flyovers")
    if root is None:
        purge_startups()
        return
    dead = []

    def walk(col):
        dead.append(col)
        for ch in col.children:
            walk(ch)

    walk(root)
    for col in dead:
        for ob in list(col.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
    for col in dead:
        bpy.data.collections.remove(col)
    log("removed stale 'Flyovers' collection")
    purge_startups()


def purge_startups():
    """Headless runs start from the default scene (Camera/Cube/Light) — drop them."""
    root = bpy.data.collections.get("Flyovers")
    keep = set()
    if root is not None:
        keep = set(walk_objs(root))
    for ob in list(bpy.data.objects):
        if ob not in keep:
            log("purging non-flyover object %r" % ob.name)
            bpy.data.objects.remove(ob, do_unlink=True)
    for col in list(bpy.data.collections):
        if col.name != "Flyovers" and not col.objects and not col.children:
            bpy.data.collections.remove(col)
    for me in [m for m in bpy.data.meshes if m.users == 0]:
        bpy.data.meshes.remove(me)


def setup():
    reset()
    root = ck.ensure_collection("Flyovers")
    sub = {}
    for nm in ("Meshes", "Colliders", "Lights"):
        sub[nm] = ck.ensure_collection("Flyovers/" + nm, parent=root)
    return root, sub


def M(name):
    return ck.append_material(name)


def mk(name, verts, faces, mats, face_mats, coll, props=None):
    """Build one mesh object inside `coll` (verts/faces in world space)."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.update()
    for m in mats:
        me.materials.append(m)
    if face_mats:
        for i, mi in enumerate(face_mats):
            if i < len(me.polygons) and mi is not None:
                me.polygons[i].material_index = mi
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    if props:
        for k, v in props.items():
            ob[k] = v
    return ob


def inst(src, name, loc, rot_z=0.0, coll=None, scale=None, quat=None):
    """Linked duplicate of `src` (shares mesh data) at loc/rot/scale."""
    ob = bpy.data.objects.new(name, src.data)
    if quat is not None:
        m = Matrix.Translation(Vector(loc)) @ quat.to_matrix().to_4x4()
    else:
        m = Matrix.Translation(Vector(loc)) @ Matrix.Rotation(rot_z, 4, "Z")
    if scale is not None:
        m = m @ Matrix.Diagonal(Vector((scale[0], scale[1], scale[2], 1.0)))
    ob.matrix_world = m
    (coll or bpy.context.scene.collection).objects.link(ob)
    return ob


# ---------------------------------------------------------------- path helpers
def raw_ring_path():
    """(1400,600) -> (1400,1280) -> 120 m arc -> (1280,1400) -> (600,1400)."""
    pts = []
    y = 600.0
    while y < 1280.0:
        pts.append((1400.0, y))
        y += 2.0
    pts.append((1400.0, 1280.0))
    for i in range(1, 61):
        a = math.radians(90.0 * i / 60.0)
        pts.append((1280.0 + 120.0 * math.cos(a), 1280.0 + 120.0 * math.sin(a)))
    x = 1280.0
    while x > 600.0:
        pts.append((x, 1400.0))
        x -= 2.0
    pts.append((600.0, 1400.0))
    return pts


def raw_ramp_path():
    """Swept (bulged) ramp: starts due south at (600,1400), lands due south at
    (600,1200); raised-cosine bulge to the east keeps both end tangents due south."""
    pts = []
    y = 1400.0
    while y > 1200.0:
        u = (1400.0 - y) / 200.0
        x = 600.0 + 0.5 * RAMP_BULGE * (1.0 - math.cos(2.0 * math.pi * u))
        pts.append((x, y))
        y -= 1.0
    pts.append((600.0, 1200.0))
    return pts


def resample(raw, n):
    """Uniform arc-length resample of a polyline -> [(x, y, s), ...] of length n+1."""
    d = [0.0]
    for i in range(1, len(raw)):
        d.append(d[-1] + math.hypot(raw[i][0] - raw[i - 1][0], raw[i][1] - raw[i - 1][1]))
    length = d[-1]
    out, j = [], 0
    for k in range(n + 1):
        s = length * k / n
        while j < len(d) - 2 and d[j + 1] < s:
            j += 1
        seg = d[j + 1] - d[j]
        t = 0.0 if seg <= 1e-9 else (s - d[j]) / seg
        x = raw[j][0] + (raw[j + 1][0] - raw[j][0]) * t
        y = raw[j][1] + (raw[j + 1][1] - raw[j][1]) * t
        out.append((x, y, s))
    return out, length


def frames(pts):
    """Attach unit tangents/normals: n = (ty, -tx) points to the RIGHT of travel."""
    n = len(pts)
    fr = []
    for i, (x, y, s) in enumerate(pts):
        xa, ya = pts[max(0, i - 1)][:2]
        xb, yb = pts[min(n - 1, i + 1)][:2]
        tx, ty = xb - xa, yb - ya
        m = math.hypot(tx, ty) or 1.0
        tx, ty = tx / m, ty / m
        fr.append({"x": x, "y": y, "s": s, "tx": tx, "ty": ty,
                   "nx": ty, "ny": -tx})
    return fr


def pt(fr, u):
    """World point at lateral offset u from a frame."""
    return (fr["x"] + fr["nx"] * u, fr["y"] + fr["ny"] * u)


def head_angle(fr):
    """World Z rotation that maps local +Y onto the frame tangent."""
    return math.atan2(-fr["tx"], fr["ty"])


def sweep(name, fr, prof, mats, edge_mats, coll, props=None, cap_mat=0):
    """Extrude a closed profile (list of (u,z), same length for every frame) along frames.

    edge_mats[k] = material index of the edge profile[k] -> profile[k+1] (wrap).
    Returns the object."""
    n, m = len(fr), len(prof(fr[0]))
    verts = []
    for f in fr:
        for u, z in prof(f):
            x, y = pt(f, u)
            verts.append((x, y, z))
    faces, fm = [], []
    for i in range(n - 1):
        for k in range(m):
            k2 = (k + 1) % m
            a = i * m + k
            b = i * m + k2
            c = (i + 1) * m + k2
            d = (i + 1) * m + k
            faces.append((a, b, c, d))
            fm.append(edge_mats[k])
    # end caps (fan)
    for base, rev in ((0, True), ((n - 1) * m, False)):
        ring = [base + k for k in range(m)]
        if rev:
            ring.reverse()
        for k in range(1, m - 1):
            faces.append((ring[0], ring[k], ring[k + 1]))
            fm.append(cap_mat)
    return mk(name, verts, faces, mats, fm, coll, props)


def align_rot(cx, cy):
    """World Z rotation mapping local +Y onto direction (cx, cy)."""
    return math.atan2(-cx, cy)


def frame_at(fr, s):
    """Interpolated frame at arc-length s."""
    lo, hi = 0, len(fr) - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if fr[mid]["s"] <= s:
            lo = mid
        else:
            hi = mid
    a, b = fr[lo], fr[hi]
    t = 0.0 if b["s"] - a["s"] <= 1e-9 else (s - a["s"]) / (b["s"] - a["s"])
    tx, ty = a["tx"] + (b["tx"] - a["tx"]) * t, a["ty"] + (b["ty"] - a["ty"]) * t
    m = math.hypot(tx, ty) or 1.0
    tx, ty = tx / m, ty / m
    return {"x": a["x"] + (b["x"] - a["x"]) * t, "y": a["y"] + (b["y"] - a["y"]) * t,
            "s": s, "tx": tx, "ty": ty, "nx": ty, "ny": -tx}


def barrier_profile():
    return [(0.0, 0.0), (BAR_W, 0.0), (BAR_W, 0.20),
            (0.42, BAR_H), (0.18, BAR_H), (0.0, 0.20)]


def barrier_run(name, fr, u0, step, coll, z_off=0.0, s_range=None, src=None,
                z_fn=None):
    """Instance one jersey-barrier mesh along a deck/ramp edge (shared mesh, no gaps).

    Each segment spans frames[i] -> frames[i+step]; its origin sits at lateral u0,
    it is aligned to the 3D chord between the two edge points and scaled along its
    own length, so consecutive segments meet exactly (also over slopes)."""
    prof = barrier_profile()
    m = len(prof)
    made, n = [], len(fr)
    i = 0
    while i + step <= n - 1:
        s0, s1 = fr[i]["s"], fr[i + step]["s"]
        if s_range and (s1 < s_range[0] or s0 > s_range[1]):
            i += step
            continue
        a, b = fr[i], fr[i + step]
        pa, pb = pt(a, u0), pt(b, u0)
        za = float(z_fn(s0)) if z_fn else float(z_off)
        zb = float(z_fn(s1)) if z_fn else float(z_off)
        cx, cy, cz = pb[0] - pa[0], pb[1] - pa[1], zb - za
        dist = math.sqrt(cx * cx + cy * cy + cz * cz)
        if dist < 1e-6:
            i += step
            continue
        d = Vector((cx / dist, cy / dist, cz / dist))
        quat = Vector((0.0, 1.0, 0.0)).rotation_difference(d)
        scale = (1.0, dist / SEG, 1.0)
        if src is None:
            verts = [(u, 0.0, z) for u, z in prof] + \
                    [(u, SEG, z) for u, z in prof]
            faces = [(k, (k + 1) % m, m + (k + 1) % m, m + k) for k in range(m)]
            faces.append(tuple(reversed(range(m))))          # start cap
            faces.append(tuple(range(m, 2 * m)))             # end cap
            src = mk(name, verts, faces, [M("concrete_poured")], None, coll)
            src.location = (pa[0], pa[1], za)
            src.rotation_euler = quat.to_euler()
            src.scale = scale
        else:
            inst(src, "%s_%03d" % (name, len(made) + 1),
                 (pa[0], pa[1], za), coll=coll, scale=scale, quat=quat)
        made.append(1)
        i += step
    return made, src


# ---------------------------------------------------------------- marking helpers
def mk_strip(fr, u_fn, w, z_fn, s0=None, s1=None):
    """Quad strip between lateral offsets u_fn(f) +/- w/2 (one quad per interval)."""
    verts, faces = [], []
    for i in range(len(fr) - 1):
        a, b = fr[i], fr[i + 1]
        if s1 is not None and a["s"] >= s1:
            break
        if s0 is not None and b["s"] <= s0:
            continue
        ua, ub = u_fn(a), u_fn(b)
        za, zb = z_fn(a), z_fn(b)
        pa1, pa2 = pt(a, ua - w * 0.5), pt(a, ua + w * 0.5)
        pb1, pb2 = pt(b, ub - w * 0.5), pt(b, ub + w * 0.5)
        k = len(verts)
        verts += [(pa1[0], pa1[1], za), (pa2[0], pa2[1], za),
                  (pb2[0], pb2[1], zb), (pb1[0], pb1[1], zb)]
        faces.append((k, k + 1, k + 2, k + 3))
    return verts, faces


def mk_dashes(fr, u_fn, w, z_fn, period=12.0, duty=4.0, s0=0.0, s1=None):
    verts, faces = [], []
    end = fr[-1]["s"] if s1 is None else min(s1, fr[-1]["s"])
    s = s0
    while s + duty <= end:
        f0, f1 = frame_at(fr, s), frame_at(fr, s + duty)
        u0, u1, z0, z1 = u_fn(f0), u_fn(f1), z_fn(f0), z_fn(f1)
        p1, p2 = pt(f0, u0 - w * 0.5), pt(f0, u0 + w * 0.5)
        q1, q2 = pt(f1, u1 - w * 0.5), pt(f1, u1 + w * 0.5)
        k = len(verts)
        verts += [(p1[0], p1[1], z0), (p2[0], p2[1], z0),
                  (q2[0], q2[1], z1), (q1[0], q1[1], z1)]
        faces.append((k, k + 1, k + 2, k + 3))
        s += period
    return verts, faces


def mk_marks(name, parts, mats, coll, props=None):
    verts, faces = [], []
    for v, f in parts:
        b = len(verts)
        verts += v
        faces += [tuple(b + i for i in ff) for ff in f]
    if not verts:
        return None
    return mk(name, verts, faces, mats, None, coll, props)


def const(x):
    return lambda f: x


# ---------------------------------------------------------------- stage 1: deck
def stage_deck(sub, ctx):
    log("stage 1/5: ring deck (H_07 + H_08 + 120 m corner)")
    fr = ctx["ring"]
    meshes = sub["Meshes"]

    def prof(f):
        return [(-DECK_HW, DECK_Z), (-SHOULDER_OUT, DECK_Z), (SHOULDER_OUT, DECK_Z),
                (DECK_HW, DECK_Z), (DECK_HW, SOFFIT), (-DECK_HW, SOFFIT)]

    deck = sweep("SM_Deck_Ring_NE_01", fr, prof,
                 [M("concrete"), M("asphalt_highway")], [0, 1, 0, 0, 0, 0],
                 meshes, {"kind": "ring_deck", "edges": "H_07,H_08"})
    log("   deck: %d verts, %d tris" % (len(deck.data.vertices), ck.tri_count(deck)))

    step = max(1, int(round(SEG / ctx["ring_dl"])))
    total = 0
    for nm, u0 in (("SM_Barrier_Jersey_Edge_R_01", DECK_HW - BAR_W),
                   ("SM_Barrier_Jersey_Edge_L_01", -DECK_HW),
                   ("SM_Barrier_Jersey_Median_01", -BAR_W * 0.5)):
        made, _src = barrier_run(nm, fr, u0, step, meshes, z_off=DECK_Z)
        total += len(made)
        log("   barrier %s: %d segments" % (nm, len(made)))
    ctx["n_barrier_ring"] = total

    z = const(DECK_Z + 0.006)
    white, yellow = [], []
    for u in (SHOULDER_OUT, -SHOULDER_OUT):                 # solid white edge lines
        white.append(mk_strip(fr, const(u), 0.15, z))
    for u in (5.5, 9.0, -5.5, -9.0):                        # lane splits (3 lanes/way)
        white.append(mk_dashes(fr, const(u), 0.15, z))
    for u in (MEDIAN_HW, -MEDIAN_HW):                       # yellow next to the median
        yellow.append(mk_strip(fr, const(u), 0.15, z))
    mk_marks("SM_Marking_Ring_White_01", white, [M("marking_white")],
             meshes, {"kind": "markings"})
    mk_marks("SM_Marking_Ring_Yellow_01", yellow, [M("marking_yellow")],
             meshes, {"kind": "markings"})
    ctx["deck_obj"] = deck
    ck.save_blend(BLEND)
    log("   saved deck stage -> %s" % BLEND)


# ---------------------------------------------------------------- stage 2: ramp
def ramp_w(y):
    """Ramp deck width at plan-y: 18 m, flaring to 24 m over the last 12 m."""
    if y >= RAMP_END_FLARE_Y:
        return RAMP_W
    t = (RAMP_END_FLARE_Y - y) / (RAMP_END_FLARE_Y - 1200.0)
    return RAMP_W + (RAMP_END_W - RAMP_W) * t


def build_ramp_frames():
    """Ramp X_N_600: (600,1400,8) -> (600,1200,0), swept plan curve, <= 4 %."""
    pts, length = resample(raw_ramp_path(), 100)
    fr = frames(pts)
    s_exit = None
    for i in range(len(fr) - 1):
        y0, y1 = fr[i]["y"], fr[i + 1]["y"]
        if y0 >= 1383.0 >= y1 and y0 - y1 > 1e-9:
            t = (y0 - 1383.0) / (y0 - y1)
            s_exit = fr[i]["s"] + t * (fr[i + 1]["s"] - fr[i]["s"])
            break
    assert s_exit is not None, "ramp never crosses the ring deck edge (y=1383)"
    grad = RAMP_Z0 / (length - s_exit)

    def rz(s):
        if s <= s_exit:
            return RAMP_Z0
        return RAMP_Z0 * (1.0 - (s - s_exit) / (length - s_exit))

    for f in fr:
        f["z"] = rz(f["s"])
        f["zb"] = max(0.0, f["z"] - RAMP_T)
        f["w"] = ramp_w(f["y"])
    return fr, length, s_exit, grad, rz


def ramp_frame_at(ctx, s):
    """Interpolated ramp frame carrying z / zb / w at arc-length s."""
    f = frame_at(ctx["ramp"], s)
    z = ctx["ramp_z"](s)
    f["z"] = z
    f["zb"] = max(0.0, z - RAMP_T)
    f["w"] = ramp_w(f["y"])
    return f


def stage_ramp(sub, ctx):
    log("stage 2/5: ramp X_N_600")
    fr, length, s_exit, grad, rz = ctx["ramp"], ctx["ramp_L"], ctx["ramp_s_exit"], \
        ctx["ramp_grad"], ctx["ramp_z"]
    meshes = sub["Meshes"]
    log("   length %.1f m, flat run to y=1383 %.1f m, gradient %.3f %% (max 4.000)"
        % (length, s_exit, grad * 100.0))
    assert grad <= GRAD_MAX + 1e-9, "ramp gradient %.3f %% > 4 %%" % (grad * 100)

    def prof(f):
        hw = f["w"] * 0.5
        return [(-hw, f["z"]), (hw, f["z"]), (hw, f["zb"]), (-hw, f["zb"])]

    ramp = sweep("SM_Deck_Ramp_X_N_600_01", fr, prof,
                 [M("concrete"), M("asphalt")], [1, 0, 0, 0],
                 meshes, {"kind": "ramp", "edge": "X_N_600"}, cap_mat=0)
    log("   ramp deck: %d verts, %d tris" % (len(ramp.data.vertices), ck.tri_count(ramp)))

    # barriers both edges — from the ring deck edge down to z = 1.4 m
    s_stop = max([f["s"] for f in fr if f["z"] > 1.4] + [s_exit])
    step = max(1, int(round(SEG / (length / 100.0))))
    n = 0
    for nm, u0 in (("SM_Barrier_Ramp_R_01", RAMP_W * 0.5 - BAR_W),
                   ("SM_Barrier_Ramp_L_01", -RAMP_W * 0.5)):
        made, _src = barrier_run(nm, fr, u0, step, meshes, s_range=(s_exit, s_stop),
                                 z_fn=rz)
        n += len(made)
        log("   ramp barrier %s: %d segments" % (nm, len(made)))
    ctx["n_barrier_ramp"] = n
    ctx["ramp_barrier_stop_s"] = s_stop

    # markings: double yellow centre, dashed lane split, solid edge lines
    z = lambda f: rz(f["s"]) + 0.006
    white, yellow = [], []
    white.append(mk_strip(fr, lambda f: ramp_w(f["y"]) * 0.5 - 1.2, 0.15, z,
                          s0=s_exit))
    white.append(mk_strip(fr, lambda f: -(ramp_w(f["y"]) * 0.5 - 1.2), 0.15, z,
                          s0=s_exit))
    white.append(mk_dashes(fr, const(4.0), 0.15, z, s0=s_exit))
    white.append(mk_dashes(fr, const(-4.0), 0.15, z, s0=s_exit))
    yellow.append(mk_strip(fr, const(0.28), 0.15, z, s0=s_exit))
    yellow.append(mk_strip(fr, const(-0.28), 0.15, z, s0=s_exit))
    mk_marks("SM_Marking_Ramp_White_01", white, [M("marking_white")],
             meshes, {"kind": "markings"})
    mk_marks("SM_Marking_Ramp_Yellow_01", yellow, [M("marking_yellow")],
             meshes, {"kind": "markings"})
    ctx["ramp_obj"] = ramp
    ck.save_blend(BLEND)
    log("   saved ramp stage -> %s" % BLEND)


# ---------------------------------------------------------------- kit instancing
class Kit:
    """One mesh, many linked instances (the first instance IS the source object)."""

    def __init__(self, name, verts, faces, mat, coll):
        me = bpy.data.meshes.new(name)
        me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
        me.update()
        me.materials.append(mat)
        self.me, self.name, self.coll, self.n, self.src = me, name, coll, 0, None

    def put(self, loc, rot=0.0, scale=None, tag=None):
        self.n += 1
        nm = "%s_%03d" % (self.name, self.n) if tag is None else "%s_%s" % (self.name, tag)
        if self.src is None:
            ob = bpy.data.objects.new(nm, self.me)
            ob.location = (float(loc[0]), float(loc[1]), float(loc[2]))
            ob.rotation_euler = (0.0, 0.0, float(rot))
            ob.scale = scale or (1.0, 1.0, 1.0)
            self.coll.objects.link(ob)
            self.src = ob
            return ob
        return inst(self.src, nm, loc, rot, self.coll, scale=scale)


def box_vf(sx, sy, z0, z1):
    hx, hy = sx * 0.5, sy * 0.5
    v = [(-hx, -hy, z0), (hx, -hy, z0), (hx, hy, z0), (-hx, hy, z0),
         (-hx, -hy, z1), (hx, -hy, z1), (hx, hy, z1), (-hx, hy, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
         (2, 3, 7, 6), (3, 0, 4, 7)]
    return v, f


def taper_vf(bx, by, tx, ty, z1):
    v = [(-bx, -by, 0.0), (bx, -by, 0.0), (bx, by, 0.0), (-bx, by, 0.0),
         (-tx, -ty, z1), (tx, -ty, z1), (tx, ty, z1), (-tx, ty, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
         (2, 3, 7, 6), (3, 0, 4, 7)]
    return v, f


# ---------------------------------------------------------------- stage 3: piers
def stage_piers(sub, ctx):
    log("stage 3/5: substructure (piers, caps, footings)")
    meshes = sub["Meshes"]
    cv, cf = taper_vf(COL_BASE[0] * 0.5, COL_BASE[1] * 0.5,
                      COL_TOP[0] * 0.5, COL_TOP[1] * 0.5, 1.0)
    k_col = Kit("SM_Pier_Column", cv, cf, M("concrete_poured"), meshes)
    fv, ff = box_vf(4.4, 3.4, 0.0, FOOT_TOP)
    k_foot = Kit("SM_Pier_Footing", fv, ff, M("concrete"), meshes)
    kv, kf = box_vf(32.0, 1.6, 0.0, CAP_D)
    k_cap = Kit("SM_Pier_Cap", kv, kf, M("concrete_poured"), meshes)
    rv, rf_ = box_vf(17.0, 1.4, 0.0, 1.0)
    k_rcap = Kit("SM_Pier_Cap_Ramp", rv, rf_, M("concrete_poured"), meshes)
    av, af = box_vf(13.0, 11.0, 0.0, 0.05)
    k_apr = Kit("SM_Gravel_Apron", av, af, M("gravel"), meshes)

    # --- ring bents -------------------------------------------------------
    fr, length = ctx["ring"], ctx["ring_L"]
    bents, k = [], 1
    while True:
        s = PIER_SPACING * k
        if s > length - 20.0:
            break
        f = frame_at(fr, s)
        keep = s >= 20.0
        if f["y"] > 1350.0 and 555.0 <= f["x"] <= 645.0:
            keep = False                      # keep the ramp junction clear
        if keep:
            bents.append((s, f))
        k += 1
    col_h = SOFFIT - CAP_D - FOOT_TOP
    for s, f in bents:
        rot = head_angle(f)
        for u in (PIER_U, -PIER_U):
            p = pt(f, u)
            k_foot.put((p[0], p[1], 0.0), rot)
            k_col.put((p[0], p[1], FOOT_TOP), rot, scale=(1.0, 1.0, col_h))
        c = pt(f, 0.0)
        k_cap.put((c[0], c[1], SOFFIT - CAP_D), rot)
    log("   ring bents: %d (columns %d, footings %d, caps %d)"
        % (len(bents), k_col.n, k_foot.n, k_cap.n))
    ctx["bents"] = [(s, dict(f)) for s, f in bents]

    # --- ramp bents -------------------------------------------------------
    rf_fr, s_exit, rL = ctx["ramp"], ctx["ramp_s_exit"], ctx["ramp_L"]
    rz = ctx["ramp_z"]
    rp, s = [], s_exit + 28.0
    while s < rL - 12.0:
        f = ramp_frame_at(ctx, s)
        h = f["zb"] - 1.0 - FOOT_TOP
        if f["z"] >= 3.0 and h > 1.0:
            rp.append((s, f, h))
        s += 28.0
    for s, f, h in rp:
        rot = head_angle(f)
        for u in (6.0, -6.0):
            p = pt(f, u)
            k_apr.put((p[0], p[1], 0.0), rot)
            k_foot.put((p[0], p[1], 0.0), rot)
            k_col.put((p[0], p[1], FOOT_TOP), rot, scale=(1.0, 1.0, h))
        c = pt(f, 0.0)
        k_rcap.put((c[0], c[1], f["zb"] - 1.0), rot)
    log("   ramp bents: %d" % len(rp))
    ctx["ramp_bents"] = [(s, dict(f), h) for s, f, h in rp]
    ck.save_blend(BLEND)
    log("   saved pier stage -> %s" % BLEND)


def flat_strip(name, fr, u1, u2, z, mat, coll, props=None):
    verts, faces = [], []
    for f in fr:
        p1, p2 = pt(f, u1), pt(f, u2)
        verts += [(p1[0], p1[1], z), (p2[0], p2[1], z)]
    for i in range(len(fr) - 1):
        a = 2 * i
        faces.append((a, a + 1, a + 3, a + 2))
    return mk(name, verts, faces, [mat], None, coll, props)


# ---------------------------------------------------------------- stage 4: ground band
def stage_ground(sub, ctx):
    log("stage 4/5: ground band (service road + verges)")
    fr = ctx["ring"]
    meshes = sub["Meshes"]

    def prof(f):
        return [(-ROAD_HW, 0.0), (ROAD_HW, 0.0), (ROAD_HW, -0.05), (-ROAD_HW, -0.05)]

    road = sweep("SM_Road_Service_01", fr, prof, [M("asphalt_worn")],
                 [0, 0, 0, 0], meshes,
                 {"kind": "service_road", "width": 10.0}, cap_mat=0)
    log("   service road: 10 m wide, %d tris" % ck.tri_count(road))
    flat_strip("SM_Verge_Gravel_R_01", fr, ROAD_HW, 14.0, -0.05, M("gravel"),
               meshes, {"kind": "verge"})
    flat_strip("SM_Verge_Gravel_L_01", fr, -14.0, -ROAD_HW, -0.05, M("gravel"),
               meshes, {"kind": "verge"})
    flat_strip("SM_Verge_Dirt_R_01", fr, 14.0, VERGE_HW, -0.05, M("dirt"),
               meshes, {"kind": "verge"})
    flat_strip("SM_Verge_Dirt_L_01", fr, -VERGE_HW, -14.0, -0.05, M("dirt"),
               meshes, {"kind": "verge"})
    z = const(0.004)
    lines = [mk_strip(fr, const(4.6), 0.12, z), mk_strip(fr, const(-4.6), 0.12, z)]
    mk_marks("SM_Marking_Service_Yellow_01", lines, [M("marking_yellow")],
             meshes, {"kind": "markings_service"})
    ck.save_blend(BLEND)
    log("   saved ground band stage -> %s" % BLEND)


# ---------------------------------------------------------------- stage 5: details
def stage_details(sub, ctx):
    log("stage 5/5: expansion joints, scuppers, colliders")
    fr, meshes, colliders = ctx["ring"], sub["Meshes"], sub["Colliders"]

    jv, jf = box_vf(33.9, 0.14, 0.0, 0.03)
    k_joint = Kit("SM_ExpansionJoint", jv, jf, M("metal_steel"), meshes)
    s = 40.0
    while s < ctx["ring_L"] - 15.0:
        f = frame_at(fr, s)
        k_joint.put((f["x"], f["y"], DECK_Z - 0.015), head_angle(f))
        s += 40.0
    log("   expansion joints: %d" % k_joint.n)

    sv, sf = box_vf(0.4, 0.6, 0.0, 0.4)
    k_scup = Kit("SM_Scupper", sv, sf, M("metal_steel"), meshes)
    for _s, f in ctx["bents"]:
        rot = head_angle(f)
        for u in (DECK_HW + 0.2, -DECK_HW - 0.2):
            p = pt(f, u)
            k_scup.put((p[0], p[1], SOFFIT - 0.05), rot)
    log("   scuppers: %d" % k_scup.n)

    # --- collision proxies -------------------------------------------------
    def cbox(name, x0, y0, x1, y1, z0, z1):
        f = box_vf(x1 - x0, y1 - y0, z0, z1)[1]
        cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
        v = [(cx + x, cy + y, z)
             for (x, y, z) in box_vf(x1 - x0, y1 - y0, z0, z1)[0]]
        return mk(name, v, f, [M("concrete")], None, colliders,
                  {"proxy": "deck"})

    cbox("COL_ring_deck_east", 1383.0, 600.0, 1417.0, 1280.0, SOFFIT, DECK_Z)
    cbox("COL_ring_deck_north", 600.0, 1383.0, 1280.0, 1417.0, SOFFIT, DECK_Z)
    cbox("COL_ring_deck_corner", 1280.0, 1280.0, 1417.0, 1417.0, SOFFIT, DECK_Z)

    # ramp: one slab box per quarter
    rfr = ctx["ramp"]
    n = len(rfr)
    for qi in range(4):
        a, b = n * qi // 4, n * (qi + 1) // 4
        seg = rfr[a:max(b, a + 2)]
        xs, ys, zs, zb = [], [], [], []
        for f in seg:
            hw = f["w"] * 0.5 + 0.4
            for u in (hw, -hw):
                p = pt(f, u)
                xs.append(p[0])
                ys.append(p[1])
            zs.append(f["z"])
            zb.append(f["zb"])
        cbox("COL_ramp_%02d" % (qi + 1), min(xs), min(ys), max(xs), max(ys),
             min(zb), max(zs))

    # piers
    pk = Kit("COL_pier", *box_vf(22.4, 3.4, 0.0, SOFFIT), M("concrete"), colliders)
    for _s, f in ctx["bents"]:
        pk.put((f["x"], f["y"], 0.0), head_angle(f))
    rk = Kit("COL_pier_ramp", *box_vf(16.4, 3.4, 0.0, 1.0), M("concrete"), colliders)
    for _s, f, h in ctx["ramp_bents"]:
        rk.put((f["x"], f["y"], 0.0), head_angle(f),
               scale=(1.0, 1.0, (f["zb"] + 0.4) / 1.0))
    for ob in colliders.objects:
        ob.hide_render = True
        ob.display_type = "WIRE"
    log("   colliders: %d" % len(colliders.objects))
    ck.save_blend(BLEND)
    log("   saved details stage -> %s" % BLEND)


# ---------------------------------------------------------------- verify / preview
def walk_objs(coll):
    for ob in coll.objects:
        yield ob
    for ch in coll.children:
        for ob in walk_objs(ch):
            yield ob


def world_z_range(ob):
    mw = ob.matrix_world
    lo, hi = 1e18, -1e18
    for v in ob.data.vertices:
        z = (mw @ v.co).z
        lo = min(lo, z)
        hi = max(hi, z)
    return lo, hi


def verify(sub, ctx):
    root = bpy.data.collections["Flyovers"]
    objs = [o for o in walk_objs(root) if o.type == "MESH"]
    zlo, zhi = 1e18, -1e18
    for ob in objs:
        a, b = world_z_range(ob)
        zlo, zhi = min(zlo, a), max(zhi, b)
    deck = ctx["deck_obj"]
    d_lo, d_hi = world_z_range(deck)
    ramp = ctx["ramp_obj"]
    r_end = ctx["ramp"][-1]
    facts = {
        "ring_deck_top_z": round(d_hi, 6),
        "ring_deck_soffit_z": round(d_lo, 6),
        "ring_deck_width_m": 2 * DECK_HW,
        "ring_path": "H_07 x=1400 y=600->1280, 120 m arc (c=1280,1280), "
                     "H_08 y=1400 x=1280->600",
        "ring_path_length_m": round(ctx["ring_L"], 2),
        "corner_radius_m": 120.0,
        "min_ground_clearance_m": round(d_lo, 3),
        "ramp_start": [600.0, 1400.0, RAMP_Z0],
        "ramp_end": [round(r_end["x"], 3), round(r_end["y"], 3), round(r_end["z"], 4)],
        "ramp_end_width_m": round(r_end["w"], 3),
        "ramp_plan_length_m": round(ctx["ramp_L"], 2),
        "ramp_gradient_pct": round(ctx["ramp_grad"] * 100.0, 4),
        "ramp_bulge_m": RAMP_BULGE,
        "ramp_barrier_stop_s": round(ctx["ramp_barrier_stop_s"], 1),
        "global_z_min": round(zlo, 4),
        "global_z_max": round(zhi, 4),
    }
    checks = {
        "deck_z_is_8m": abs(d_hi - 8.0) < 1e-6,
        "deck_soffit_6_5m": abs(d_lo - 6.5) < 1e-6,
        "clearance_ge_5_5m": d_lo >= 5.5,
        "ramp_gradient_le_4pct": ctx["ramp_grad"] <= GRAD_MAX + 1e-9,
        "ramp_lands_at_600_1200_z0": abs(r_end["x"] - 600) < 0.05
        and abs(r_end["y"] - 1200) < 0.05 and abs(r_end["z"]) < 1e-6,
        "nothing_below_minus_0_05": zlo >= -0.05 - 1e-6,
    }
    for k, v in checks.items():
        log("   CHECK %-28s %s" % (k, "PASS" if v else "*** FAIL ***"))
    bad = [k for k, v in checks.items() if not v]
    assert not bad, "verification failed: %s" % bad
    return facts, checks


def do_previews():
    ck.make_preview(PREV_A, (1560.0, 1980.0, 560.0), (1000.0, 1310.0, 0.0),
                    engine="BLENDER_EEVEE", res=(1920, 1080),
                    sun_elev=45.0, sun_azim=-40.0, sun_energy=4.0)
    ck.make_preview(PREV_B, (1400.0, 640.0, 1.9), (1400.0, 1260.0, 5.5),
                    engine="BLENDER_EEVEE", res=(1920, 1080),
                    sun_elev=20.0, sun_azim=0.0, sun_energy=4.5)


def do_report(facts, checks, counts, ctx):
    mats = sorted({m.name for ob in walk_objs(bpy.data.collections["Flyovers"])
                   if ob.type == "MESH" for m in ob.data.materials if m})
    payload = {
        "files": {"blend": BLEND, "preview_aerial": PREV_A, "preview_ground": PREV_B,
                  "script": os.path.abspath(__file__)},
        "objects": counts["objects"],
        "objects_by_collection": counts["by_coll"],
        "triangles_instanced": counts["tris_inst"],
        "triangles_unique_meshes": counts["tris_uniq"],
        "materials_used": mats,
        "geometry_facts": facts,
        "checks": checks,
        "collections": ["Flyovers", "Flyovers/Meshes", "Flyovers/Colliders",
                        "Flyovers/Lights (empty)"],
        "known_issues": [
            "The ramp start (600,1400) sits inside the ring deck: the ramp slab top is "
            "7.99 m there (1 cm below the 8.00 m deck) so the two surfaces never "
            "z-fight; the ramp becomes visible exactly at the deck edge y=1383 with a "
            "1 cm ledge.",
            "To stay under the 4 % gradient the ramp is swept (raised-cosine bulge "
            + str(int(RAMP_BULGE)) + " m east of x=600); its plan footprint reaches "
            "x~" + str(int(600 + RAMP_BULGE)) + " at y~1300, outside the 18 m "
            "straight corridor in layout.json.",
            "Ramp terminus overlaps the y=1200 arterial junction for its last 12 m "
            "(y 1200..1212) with a wedge nose: top 0.48 m at y=1212 falling to 0.00 m "
            "at y=1200. No step at the landing line.",
            "Instance transforms (location/rotation/scale) are intentionally NOT "
            "applied — applying them would bake into the shared mesh and destroy the "
            "instancing. All swept/unique meshes are built in world space, so their "
            "matrix_basis is already identity.",
        ],
        "for_assembler": {
            "deck_surface_z": 8.0,
            "deck_soffit_z": 6.5,
            "deck_halfwidth_m": 17.0,
            "deck_extents": "x 1383..1417 for y 600..1280; y 1383..1417 for "
                            "x 600..1280; rounded corner radius 120 centred (1280,1280)",
            "ramp_landing_cross_section": {
                "line": "y=1200.0, x from 588.0 to 612.0, z=0.000 (flush)",
                "width_m": 24.0,
                "heading": "due south (-Y), ramp deck top flush with arterial z=0",
                "flare": "18.0 m wide above y=1212, linear flare to 24.0 m at y=1200",
                "matches": "arterial corridor envelope halfwidth 12.0 m; the ramp "
                           "footprint sits on the junction patch (carriageway "
                           "590.5..609.5) and the cut-out sidewalk gap (588..612)",
                "surfaces": "asphalt, no step (>0.5 m gap/overlap: none)",
            },
            "pier_positions_ring": [
                {"s": round(s, 1), "x": round(f["x"], 1), "y": round(f["y"], 1),
                 "rot_deg": round(math.degrees(head_angle(f)), 1)}
                for s, f in ctx["bents"]],
            "pier_bays": "columns at u = +/-9.0 (2.4x1.2 tapered, 4.5 m tall), "
                         "cap 32.0x1.6x1.4 under the deck, footing 4.4x3.4x0.6, "
                         "spacing 35 m along the centreline",
            "ground_band": "service road 10 m wide (u +/-5) along the ring centreline, "
                           "x=1400 strip y 600..1400 and y=1400 strip x 600..1400 "
                           "(rounded corner), gravel verge u 5..14, dirt verge "
                           "u 14..20, all tops at z 0.0 / -0.05",
        },
    }
    ck.write_report("flyover", payload)
    write_markdown(facts, checks, counts, mats, payload)
    return payload


def write_markdown(facts, checks, counts, mats, payload):
    lines = ["# flyover — Phase B pilot (NE ring corner + ramp X_N_600)", ""]
    lines += ["## Files", "",
              "- script: `%s`" % payload["files"]["script"],
              "- blend: `%s`" % BLEND,
              "- preview (aerial): `%s`" % PREV_A,
              "- preview (ground): `%s`" % PREV_B, ""]
    lines += ["## Counts", "",
              "- objects: **%d** (%s)" % (counts["objects"], counts["by_coll"]),
              "- triangles (instanced): **%d**" % counts["tris_inst"],
              "- triangles (unique meshes): **%d**" % counts["tris_uniq"], ""]
    lines += ["## Materials used", ""]
    lines += ["- " + m for m in mats]
    lines += ["", "## Geometry facts for the Assembler", ""]
    for k, v in facts.items():
        lines.append("- **%s**: %s" % (k, v))
    fa = payload["for_assembler"]
    lines += ["", "### Ramp landing cross-section", ""]
    for k, v in fa["ramp_landing_cross_section"].items():
        lines.append("- **%s**: %s" % (k, v))
    lines += ["- **ground band**: %s" % fa["ground_band"], ""]
    lines += ["## Checks", ""]
    for k, v in checks.items():
        lines.append("- %s: %s" % (k, "PASS" if v else "FAIL"))
    lines += ["", "## Known issues", ""]
    lines += ["- " + s for s in payload["known_issues"]]
    lines += ["", "## Wanted from other agents", "",
              "- MISSING MATERIAL: none — every material used exists in materials.blend.",
              "- Signage/gantry agents may attach to the deck edges (top z=8.0, "
              "barrier top z=9.05, barrier at |u| 16.4..17.0).",
              "- The Assembler should not place ground roads or buildings inside the "
              "ground band (service road + verges, u +/-20 around the ring centreline).",
              ""]
    path = os.path.join(ck.REPORTS_DIR, "flyover_report.md")
    with open(path, "w") as fh:
        fh.write("\n".join(lines))
    log("  [flyover] markdown report -> %s" % path)


# ---------------------------------------------------------------- main
def poly_len(raw):
    return sum(math.hypot(raw[i][0] - raw[i - 1][0], raw[i][1] - raw[i - 1][1])
               for i in range(1, len(raw)))


def main():
    t0 = __import__("time").time()
    log("=== flyover pilot build start ===")
    root, sub = setup()
    ctx = {}

    raw = raw_ring_path()
    est = poly_len(raw)
    n = max(8, int(round(est / DECK_STEP)))
    pts, length = resample(raw, n)
    ctx["ring"] = frames(pts)
    ctx["ring_L"] = length
    ctx["ring_dl"] = length / n
    log("ring path: %.1f m over %d samples (step %.2f m)" % (length, n, ctx["ring_dl"]))

    fr, rL, s_exit, grad, rz = build_ramp_frames()
    ctx.update({"ramp": fr, "ramp_L": rL, "ramp_s_exit": s_exit,
                "ramp_grad": grad, "ramp_z": rz})
    log("ramp path: %.1f m, exit at s=%.1f, gradient %.3f %%" % (rL, s_exit, grad * 100))

    stage_deck(sub, ctx)
    stage_ramp(sub, ctx)
    stage_piers(sub, ctx)
    stage_ground(sub, ctx)
    stage_details(sub, ctx)

    objs = list(walk_objs(root))
    counts = {
        "objects": len(objs),
        "by_coll": "Meshes %d / Colliders %d / Lights %d"
                   % (len(list(walk_objs(sub["Meshes"]))),
                      len(list(walk_objs(sub["Colliders"]))),
                      len(list(walk_objs(sub["Lights"])))),
        "tris_inst": sum(ck.tri_count(o) for o in objs),
        "tris_uniq": ck.scene_tri_count(),
    }
    facts, checks = verify(sub, ctx)
    log("objects: %d | tris instanced: %d | tris unique: %d"
        % (counts["objects"], counts["tris_inst"], counts["tris_uniq"]))
    assert counts["tris_inst"] < 500000, "over tri budget"

    ck.save_blend(BLEND)
    do_previews()
    do_report(facts, checks, counts, ctx)
    log("=== done in %.1f s ===" % (__import__("time").time() - t0))


if __name__ == "__main__":
    main()
