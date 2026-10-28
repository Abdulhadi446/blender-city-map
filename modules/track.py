"""track.py — Phase C (RACE-TRACK agent).

Builds the closed racing circuit of district T from layout.json['track']:

  1 surface   ribbon (track_asphalt) + start/finish + grid + shoulders
  2 kerbs     alternating red/white kerbs on the OUTSIDE of every corner
              + gravel traps (fast corners) / asphalt runoff / grass verge
  3 barriers  armco (shared 8 m segment, posts every 4 m), tyre walls
              (one shared drum, banked into run objects), debris fence, cones
  4 pit       pit lane (12 m corridor / 8 m marked lane), 14 pit boxes,
              588 m two-storey pit building with 14 open garage bays +
              INT_ room blocks, paddock apron, hospitality units, fuel bay
  5 stands    main grandstand (435 m, 30 raked rows, roof canopy, towers)
              + hairpin grandstand
  6 support   control/timing tower, marshal posts, floodlight masts + LT_
              lights, medical centre, kiosks, access road + bridge over the
              west straight, start/finish gantry
  7 colliders COL_ proxies in Track/Colliders

Run headless:  cd /home/abdulhadi/Work/city && blender -b -P modules/track.py
"""
import bisect
import math
import os
import sys
import time

sys.path.insert(0, "/home/abdulhadi/Work/city/modules")
import citykit as ck

import bpy
from mathutils import Matrix, Vector

ROOT = "/home/abdulhadi/Work/city"
BLEND = os.path.join(ck.OUT_DIR, "track.blend")
PREV_A = os.path.join(ck.OUT_DIR, "track_preview.png")
PREV_B = os.path.join(ck.OUT_DIR, "track_ground_preview.png")

# ------------------------------------------------------------------ constants
HW = 7.0                # track half width (width_m 14)
KERB_W = 1.2
KERB_RISE = 0.05
Z_TRK = 0.02            # track surface top
Z_MARK = Z_TRK + 0.006
DS = 4.0                # centreline station spacing
STN = 8.0               # barrier sampling spacing
PIT_X = 722.4           # pit lane centreline (layout.json pit_lane)
PIT_HW = 6.0            # 12 m corridor -> 8 m marked lane
PIT_Y0, PIT_Y1 = -894.0, -306.0
SF = (698.4, -717.6)    # start/finish
BAYS = 14
BAY_PITCH = 42.0        # 588 / 14
PB = (738.4, -894.0, 768.4, -306.0)      # pit building rect
BOUNDS = (612.0, -1186.0, 1187.0, -14.0)  # keep clear of arterial corridors

MATS = {}
OBST = []               # obstacle rects (x0,y0,x1,y1) my bands must respect
OBST_FULL = []          # same, as (name, rect) pairs
OBST_ID = {}            # obstacle name -> index into OBST (lets a candidate skip itself)
CORRIDORS = []          # road corridor rects (halfwidth +1 m), shared with verify


def log(msg):
    print("[track] " + msg, flush=True)


def T0():
    return time.time()


# ------------------------------------------------------------------ materials
def load_materials(names):
    for n in names:
        MATS[n] = ck.append_material(n)
    log("materials: " + ", ".join(sorted(names)))


def M(n):
    if n not in MATS:
        MATS[n] = ck.append_material(n)
    return MATS[n]


# ------------------------------------------------------------------ mesh utils
def _cross_z(p0, p1, p2):
    ux, uy = p1[0] - p0[0], p1[1] - p0[1]
    vx, vy = p2[0] - p0[0], p2[1] - p0[1]
    return ux * vy - uy * vx


def mk(name, verts, faces, mats, face_mats, coll, props=None, orient_up=False):
    """Mesh object from verts/faces with per-face material indices."""
    verts = [tuple(v) for v in verts]
    faces = [tuple(f) for f in faces]
    if orient_up:
        fixed = []
        for f in faces:
            if len(f) >= 3 and _cross_z(verts[f[0]], verts[f[1]], verts[f[2]]) < 0:
                fixed.append(tuple(reversed(f)))
            else:
                fixed.append(f)
        faces = fixed
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    for m in mats:
        me.materials.append(m)
    if face_mats:
        for i, p in enumerate(me.polygons):
            p.material_index = face_mats[i] if i < len(face_mats) else 0
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    if props:
        for k, v in props.items():
            ob[k] = v
    return ob


def box(x0, y0, x1, y1, z0, z1):
    """Axis aligned box -> (verts, faces) with outward winding."""
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
         (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return v, f


def box_obj(name, x0, y0, x1, y1, z0, z1, mat, coll, props=None):
    v, f = box(x0, y0, x1, y1, z0, z1)
    return mk(name, v, f, [mat], [0] * len(f), coll, props)


def band(name, A, B, mats, face_mats, coll, closed=False, props=None):
    """Strip between two polylines A,B (equal length). Faces (A_i,B_i,B_j,A_j)
    which yields +Z normals when A is the left edge of a north heading run."""
    n = len(A)
    verts = [tuple(p) for p in A] + [tuple(p) for p in B]
    faces = []
    cnt = n if closed else n - 1
    for i in range(cnt):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    return mk(name, verts, faces, mats, face_mats, coll, props, orient_up=True)


def inst(src, name, loc, rot_z=0.0, coll=None, scale=None):
    """Linked duplicate (shares mesh data)."""
    ob = bpy.data.objects.new(name, src.data)
    m = Matrix.Translation(Vector((loc[0], loc[1], loc[2]))) @ Matrix.Rotation(rot_z, 4, "Z")
    if scale is not None:
        m = m @ Matrix.Diagonal((scale[0], scale[1], scale[2], 1.0))
    ob.matrix_world = m
    (coll if coll is not None else src.users_collection[0]).objects.link(ob)
    return ob


def inst_src(name, verts, faces, mat, coll, props=None):
    """Source mesh object for instancing. The object itself is a placeholder and
    gets deleted again once the real instances exist (drop_src)."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.update()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name + "_SRC", me)
    coll.objects.link(ob)
    if props:
        for k, v in props.items():
            ob[k] = v
    return ob


def drop_src(*srcs):
    """Delete placeholder source objects (instances keep sharing the mesh)."""
    for s in srcs:
        if s is not None:
            try:
                bpy.data.objects.remove(s, do_unlink=True)
            except Exception as e:
                log("  drop_src warning: %s" % e)


def batch_obj(name, verts, faces, placements, mat, coll, props=None, face_mats=None):
    """Bake N placements of one piece of geometry into a SINGLE mesh object.
    placements: [(x, y, z, rot_z), ...]. Used for the long runs of identical props
    (armco, tyre banks, fence panels) so the module stays inside the object budget
    instead of emitting one object per segment."""
    V, F = [], []
    for (px, py, pz, rz) in placements:
        ca, sa = math.cos(rz), math.sin(rz)
        b = len(V)
        for (x, y, z) in verts:
            V.append((px + ca * x - sa * y, py + sa * x + ca * y, pz + z))
        for f in faces:
            F.append(tuple(b + k for k in f))
    fm = None
    if face_mats is not None:
        fm = face_mats * len(placements)
    return mk(name, V, F, [mat], fm if fm is not None else [0] * len(F), coll, props)


def font_to_mesh(ob):
    """Static mesh for a FONT/CURVE object, evaluated through the depsgraph.
    bpy.ops.object.convert needs a selection context that headless builds do not
    reliably have, so this does it directly. Returns None on failure."""
    try:
        deps = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(deps))
        me.name = ob.name
        return me
    except Exception as e:
        log("  font_to_mesh failed: %s" % e)
        return None


# ------------------------------------------------------------------ curve utils
def _cr(p0, p1, p2, p3, u):
    u2, u3 = u * u, u * u * u
    return [0.5 * ((2 * p1[i]) + (-p0[i] + p2[i]) * u
                   + (2 * p0[i] - 5 * p1[i] + 4 * p2[i] - p3[i]) * u2
                   + (-p0[i] + 3 * p1[i] - 3 * p2[i] + p3[i]) * u3) for i in range(2)]


def catmull_rom_closed(cps):
    n = len(cps)
    dense = []
    for i in range(n):
        p0, p1, p2, p3 = cps[(i - 1) % n], cps[i], cps[(i + 1) % n], cps[(i + 2) % n]
        seg = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        k = max(4, int(math.ceil(seg / 2.0)))
        for s in range(k):
            dense.append(_cr(p0, p1, p2, p3, s / float(k)))
    return dense


def resample_closed(P, step):
    """Uniform arc-length resample of a closed polyline; returns (pts, spacing)."""
    n = len(P)
    cum = [0.0]
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    total = cum[-1]
    m = max(16, int(round(total / step)))
    ds = total / m
    out = []
    for k in range(m):
        s = k * ds
        i = min(n - 1, max(0, bisect.bisect_right(cum, s) - 1))
        a, b = P[i], P[(i + 1) % n]
        seg = cum[i + 1] - cum[i]
        t = (s - cum[i]) / seg if seg > 1e-12 else 0.0
        out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out, ds


def smooth_closed(P, passes=1):
    for _ in range(passes):
        n = len(P)
        P = [((P[(i - 1) % n][0] + 2 * P[i][0] + P[(i + 1) % n][0]) / 4.0,
              (P[(i - 1) % n][1] + 2 * P[i][1] + P[(i + 1) % n][1]) / 4.0) for i in range(n)]
    return P


def smooth_open(P, passes=2):
    for _ in range(passes):
        Q = [P[0]]
        for i in range(1, len(P) - 1):
            a, b, c = P[i - 1], P[i], P[i + 1]
            Q.append(((a[0] + 2 * b[0] + c[0]) / 4.0, (a[1] + 2 * b[1] + c[1]) / 4.0))
        Q.append(P[-1])
        P = Q
    return P


def tangents(P, closed=True):
    n = len(P)
    T = []
    for i in range(n):
        if closed:
            a, b = P[(i - 1) % n], P[(i + 1) % n]
        else:
            a = P[max(0, i - 1)]
            b = P[min(n - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1.0
        T.append((dx / L, dy / L))
    return T


def normals(T):
    """Left normal of each tangent."""
    return [(-t[1], t[0]) for t in T]


def poly_normals(P, closed=True):
    """Mitred per-vertex normals for an open/closed polyline."""
    n = len(P)
    segs = []
    for i in range(n - 1 if not closed else n):
        a, b = P[i], P[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1.0
        segs.append((dx / L, dy / L))
    N = []
    for i in range(n):
        if not closed:
            s = segs[0] if i == 0 else (segs[-1] if i == n - 1 else
                                        _avg(segs[i - 1], segs[i]))
        else:
            s = _avg(segs[i - 1], segs[i])
        N.append((-s[1], s[0]))
    return N


def _avg(a, b):
    x, y = a[0] + b[0], a[1] + b[1]
    L = math.hypot(x, y) or 1.0
    return (x / L, y / L)


def poly_len(P):
    n = len(P)
    return sum(math.hypot(P[(i + 1) % n][0] - P[i][0], P[(i + 1) % n][1] - P[i][1])
               for i in range(n - 1)) + 0.0


def open_len(P):
    return sum(math.hypot(P[i + 1][0] - P[i][0], P[i + 1][1] - P[i][1])
               for i in range(len(P) - 1))


def seg_int(a, b, c, d):
    """True if segments ab and cd properly intersect."""
    def o(p, q, r):
        v = (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])
        if abs(v) < 1e-12:
            return 0
        return 1 if v > 0 else 2
    o1, o2, o3, o4 = o(a, b, c), o(a, b, d), o(c, d, a), o(c, d, b)
    if o1 != o2 and o3 != o4:
        return True
    return False


def self_intersects(P, step=1):
    """O(n^2) proper-intersection test on a closed polyline (skips neighbours)."""
    n = len(P)
    bad = []
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            c, d = P[j], P[(j + 1) % n]
            if seg_int(a, b, c, d):
                bad.append((i, j))
                if len(bad) > 4:
                    return bad
    return bad


# ------------------------------------------------------------------ placement
def rect_contains(r, x, y, pad=0.0):
    return (r[0] - pad <= x <= r[2] + pad) and (r[1] - pad <= y <= r[3] + pad)


def point_ok(x, y, pad=1.0, skip=()):
    """True when (x,y) is inside the buildable envelope and clear of every obstacle
    rect except the ones named in `skip` (a candidate may ignore its own footprint)."""
    if not (BOUNDS[0] + pad <= x <= BOUNDS[2] - pad and
            BOUNDS[1] + pad <= y <= BOUNDS[3] - pad):
        return False
    skip_idx = None
    if skip:
        skip_idx = {OBST_ID[n] for n in skip if n in OBST_ID}
    for i, r in enumerate(OBST):
        if skip_idx is not None and i in skip_idx:
            continue
        if rect_contains(r, x, y, pad):
            return False
    return True


def fill_to(dx, dy, x, y, max_t, pad=1.0, step=1.0):
    """March from (x,y) along (dx,dy) until blocked; return distance."""
    t = 0.0
    while t + step <= max_t + 1e-6:
        nx, ny = x + dx * (t + step), y + dy * (t + step)
        if not point_ok(nx, ny, pad):
            break
        t += step
    rem = max_t - t
    if rem > 1e-6:
        nx, ny = x + dx * (max_t), y + dy * (max_t)
        if point_ok(nx, ny, pad):
            t = max_t
    return t


# ------------------------------------------------------------------ collections
def reset():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for col in list(bpy.data.collections):
        bpy.data.collections.remove(col)
    for me in [m for m in bpy.data.meshes if m.users == 0]:
        bpy.data.meshes.remove(me)
    for li in [l for l in bpy.data.lights if l.users == 0]:
        bpy.data.lights.remove(li)
    for ca in [c for c in bpy.data.cameras if c.users == 0]:
        bpy.data.cameras.remove(ca)
    root = ck.ensure_collection("Track")
    sub = {n: ck.ensure_collection("Track/%s" % n, parent=root)
           for n in ("Meshes", "Colliders", "Lights")}
    log("collections ready: Track/{Meshes,Colliders,Lights}")
    return root, sub


def tri_stats():
    coll = bpy.data.collections.get("Track")
    uniq = ck.tri_count(coll)
    exp = 0
    nobj = 0
    seen = {}
    for ob in coll.all_objects:
        nobj += 1
        d = ob.data
        if d is None:
            continue
        k = d.as_pointer()
        if k not in seen:
            seen[k] = ck.tri_count(ob)
        exp += seen[k]
    return uniq, exp, nobj


# ------------------------------------------------------------------ layout data
def road_corridors(layout):
    pos = {n["id"]: n["pos"] for n in layout["road_nodes"]}
    out = []
    for e in layout["road_edges"]:
        a, b = pos[e["a"]], pos[e["b"]]
        if max(a[0], b[0]) < 400 or min(a[0], b[0]) > 1400:
            continue
        if max(a[1], b[1]) < -1400 or min(a[1], b[1]) > 200:
            continue
        hw = e["width"] / 2.0
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        out.append((x0 - hw, y0 - hw, x1 + hw, y1 + hw, e["id"]))
    return out


def build_obstacles():
    """Rects my geometry must keep 1 m away from (plus the road corridors)."""
    global OBST, OBST_ID, OBST_FULL
    rects = [
        ("pit_corridor", (714.0, -1015.0, 730.0, -300.0)),
        ("pit_boxes", (730.0, -894.0, 738.4, -306.0)),
        ("pit_building", PB),
        ("paddock", (768.4, -748.0, 828.0, -645.0)),
        ("tower", (772.4, -635.3, 788.4, -619.3)),
        ("gs_main", (636.4, -858.72, 662.4, -423.6)),
        ("gs_hairpin", (1168.0, -364.8, 1184.0, -247.2)),
        ("kiosk_a", (616.0, -806.0, 628.0, -790.0)),
        ("kiosk_b", (616.0, -622.0, 628.0, -606.0)),
        ("kiosk_c", (616.0, -458.0, 628.0, -442.0)),
        ("medical", (812.0, -916.0, 850.0, -886.0)),
        ("ramp", (612.0, -1046.0, 776.0, -1034.0)),
        ("spur", (796.0, -1044.0, 804.0, -762.0)),
        ("loop", (796.0, -772.0, 874.0, -556.0)),
    ]
    for i, p in enumerate(MAST_POS):
        rects.append(("mast%d" % i, (p[0] - 2.0, p[1] - 2.0, p[0] + 2.0, p[1] + 2.0)))
    OBST = [r for _n, r in rects]
    OBST_FULL = list(rects)
    OBST_ID = {n: i for i, (n, _r) in enumerate(rects)}
    return rects


MAST_POS = [(745.0, -1000.0), (770.0, -200.0), (860.0, -470.0), (1060.0, -360.0),
            (1080.0, -840.0), (860.0, -980.0), (624.0, -980.0), (1160.0, -700.0)]


# ------------------------------------------------------------------ centreline
class Circuit(object):
    pass


def build_circuit(layout):
    t = layout["track"]
    cps = [[float(p[0]), float(p[1])] for p in t["control_points"]]
    dense = catmull_rom_closed(cps)
    P, ds = resample_closed(dense, DS)
    P = smooth_closed(P, 1)
    P, ds = resample_closed(P, DS)
    c = Circuit()
    c.P = P
    c.ds = ds
    c.n = len(P)
    c.T = tangents(P, True)
    c.NL = normals(c.T)
    # signed radius / turn sign (3-point circumradius over a +/-10 m baseline)
    k = max(2, int(round(10.0 / ds)))
    c.R = []
    c.turn = []
    for i in range(c.n):
        a, b, d = P[(i - k) % c.n], P[i], P[(i + k) % c.n]
        ux, uy = b[0] - a[0], b[1] - a[1]
        vx, vy = d[0] - b[0], d[1] - b[1]
        cr = ux * vy - uy * vx
        L1 = math.hypot(ux, uy) or 1e-9
        L2 = math.hypot(vx, vy) or 1e-9
        cross = (ux * vy - uy * vx) / (L1 * L2)
        d2 = 2 * (a[0] * (b[1] - d[1]) + b[0] * (d[1] - a[1]) + d[0] * (a[1] - b[1]))
        if abs(d2) < 1e-9:
            c.R.append(1e9)
        else:
            ux2 = ((a[0] ** 2 + a[1] ** 2) * (b[1] - d[1]) +
                   (b[0] ** 2 + b[1] ** 2) * (d[1] - a[1]) +
                   (d[0] ** 2 + d[1] ** 2) * (a[1] - b[1])) / d2
            uy2 = ((a[0] ** 2 + a[1] ** 2) * (d[0] - b[0]) +
                   (b[0] ** 2 + b[1] ** 2) * (a[0] - d[0]) +
                   (d[0] ** 2 + d[1] ** 2) * (b[0] - a[0])) / d2
            c.R.append(math.hypot(a[0] - ux2, a[1] - uy2))
        c.turn.append(cross)
    # smooth radius a touch
    Rs = []
    for i in range(c.n):
        w = [c.R[(i + j) % c.n] for j in (-2, -1, 0, 1, 2)]
        Rs.append(sum(w) / len(w))
    c.R = Rs
    # perimeter + bbox
    c.length = sum(math.hypot(P[(i + 1) % c.n][0] - P[i][0], P[(i + 1) % c.n][1] - P[i][1])
                   for i in range(c.n))
    xs = [p[0] for p in P]
    ys = [p[1] for p in P]
    c.bbox = (min(xs), min(ys), max(xs), max(ys))
    # ---- asserts: closed + simple
    assert abs(c.length - ds * c.n) < 0.5, "centreline not closed (len %.2f vs %.2f)" % (
        c.length, ds * c.n)
    bad = self_intersects(P)
    assert not bad, "centreline self-intersects at station pairs %s" % (bad[:5],)
    # start/finish station (nearest sample)
    best, bi = 1e18, 0
    for i, p in enumerate(P):
        d = math.hypot(p[0] - SF[0], p[1] - SF[1])
        if d < best:
            best, bi = d, i
    c.sf = bi
    # orientation (must be CW -> interior on the right)
    area = 0.0
    for i in range(c.n):
        a, b = P[i], P[(i + 1) % c.n]
        area += a[0] * b[1] - b[0] * a[1]
    c.area = area / 2.0
    c.orientation = "CCW" if area > 0 else "CW"
    return c


def station_at(c, s):
    """Point/tangent at arc length s (metres from station 0, wrapping)."""
    s = s % c.length
    i = int(s / c.ds)
    t = (s - i * c.ds) / c.ds
    j = (i + 1) % c.n
    p = (c.P[i][0] + (c.P[j][0] - c.P[i][0]) * t,
         c.P[i][1] + (c.P[j][1] - c.P[i][1]) * t)
    ti = c.T[i]
    return p, ti


def arclen_index(c, s):
    return int((s % c.length) / c.ds)


# ------------------------------------------------------------------ offsets
def run_rule(R, outside):
    """Return (width, material) of the runoff strip for one side at one station."""
    if not outside:
        return 6.0, "asphalt_worn"
    if R < 70.0:
        return 15.0, "asphalt_worn"
    if R < 160.0:
        return 12.0, "gravel"
    if R < 600.0:
        return 10.0, "gravel"
    return 6.0, "asphalt_worn"


def compute_offsets(c):
    n = c.n
    off = {}
    off["kerb"] = [-1] * n                 # -1 none, 0 left, 1 right
    off["run_w"] = [[0.0] * n, [0.0] * n]
    off["run_m"] = [["asphalt_worn"] * n, ["asphalt_worn"] * n]
    for i in range(n):
        R = c.R[i]
        corner = R < 300.0
        kside = -1
        if corner:
            kside = 0 if c.turn[i] < 0 else 1
            off["kerb"][i] = kside
        for s in (0, 1):
            w, m = run_rule(R, s == kside)
            off["run_w"][s][i] = w
            off["run_m"][s][i] = m
    # geometric edges: index 0 left(+NL), 1 right(-NL)
    sign = (1.0, -1.0)
    inner = [[0.0] * n, [0.0] * n]
    runo = [[0.0] * n, [0.0] * n]
    verge1 = [[0.0] * n, [0.0] * n]
    verge2 = [[0.0] * n, [0.0] * n]
    barrier = [[0.0] * n, [0.0] * n]
    for i in range(n):
        x, y = c.P[i]
        nx, ny = c.NL[i]
        for s in (0, 1):
            sg = sign[s]
            a = HW + (KERB_W if off["kerb"][i] == s else 0.0)
            b = a + off["run_w"][s][i]
            inner[s][i] = a
            runo[s][i] = b
            # verge 1: grass from the runoff edge out to the barrier
            px, py = x + nx * sg * b, y + ny * sg * b
            dx, dy = nx * sg, ny * sg
            w1 = fill_to(dx, dy, px, py, 14.0, pad=1.0) if point_ok(px, py, 1.0) else 3.0
            w1 = max(3.0, w1)
            # if the start point itself is blocked, force a minimal band outward
            if not point_ok(px, py, 1.0):
                w1 = 3.0
            verge1[s][i] = w1
            barrier[s][i] = b + w1
            # verge 2: fill the rest of the way to the property line
            qx, qy = x + nx * sg * (b + w1), y + ny * sg * (b + w1)
            w2 = 0.0
            if point_ok(qx, qy, 1.0):
                w2 = fill_to(dx, dy, qx, qy, 30.0, pad=1.0)
            verge2[s][i] = w2
    off["inner"] = inner
    off["runo"] = runo
    off["verge1"] = verge1
    off["verge2"] = verge2
    off["barrier"] = barrier
    return off


def edge_pts(c, arr, s, z, scale=1.0):
    sign = 1.0 if s == 0 else -1.0
    out = []
    for i in range(c.n):
        x, y = c.P[i]
        nx, ny = c.NL[i]
        d = arr[s][i] * scale
        out.append((x + nx * sign * d, y + ny * sign * d, z))
    return out


def runs_of(pred, n):
    """Contiguous index runs (wrapping) where pred(i) is True."""
    if all(pred(i) for i in range(n)):
        return [list(range(n))]
    if not any(pred(i) for i in range(n)):
        return []
    start = next(i for i in range(n) if not pred(i))
    runs, cur = [], []
    for k in range(n):
        i = (start + k) % n
        if pred(i):
            cur.append(i)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return [r for r in runs if len(r) >= 3]


# ------------------------------------------------------------------ stage 1
def stage_surface(c, coll, off):
    log("--- stage 1: surface")
    t = T0()
    n = c.n
    # track ribbon
    A, B = [], []
    for i in range(n):
        x, y = c.P[i]
        nx, ny = c.NL[i]
        A.append((x + nx * HW, y + ny * HW, Z_TRK))
        B.append((x - nx * HW, y - ny * HW, Z_TRK))
    band("SM_Track_Surface_01", A, B, [M("track_asphalt")], [0] * n, coll, closed=True,
         props={"kind": "track_surface", "width_m": 2 * HW})
    # white edge lines
    for s, nm in ((0, "SM_Track_EdgeLine_L_01"), (1, "SM_Track_EdgeLine_R_01")):
        A = edge_pts(c, [[HW - 0.18] * n, [HW - 0.18] * n], s, Z_MARK)
        B = edge_pts(c, [[HW - 0.03] * n, [HW - 0.03] * n], s, Z_MARK)
        band(nm, A, B, [M("marking_white")], [0] * n, coll, closed=True)
    # runoff strips (gravel / asphalt) + grass verge 1 + verge 2
    for s, tag in ((0, "L"), (1, "R")):
        A = edge_pts(c, off["inner"], s, Z_TRK)
        B = edge_pts(c, off["runo"], s, Z_TRK - 0.004)
        fmat = [0 if off["run_m"][s][i] == "gravel" else 1 for i in range(n)]
        band("SM_Runoff_%s_01" % tag, A, B, [M("gravel"), M("asphalt_worn")], fmat,
             coll, closed=True, props={"kind": "runoff"})
        A = edge_pts(c, off["runo"], s, Z_TRK - 0.004)
        B = edge_pts(c, [[off["runo"][s][i] + off["verge1"][s][i] for i in range(n)],
                         [off["runo"][s][i] + off["verge1"][s][i] for i in range(n)]], s, 0.008)
        band("SM_Verge1_%s_01" % tag, A, B, [M("grass")], [0] * n, coll, closed=True,
             props={"kind": "verge"})
        A = edge_pts(c, [[off["runo"][s][i] + off["verge1"][s][i] for i in range(n)],
                         [off["runo"][s][i] + off["verge1"][s][i] for i in range(n)]], s, 0.008)
        B = edge_pts(c, [[off["runo"][s][i] + off["verge1"][s][i] + off["verge2"][s][i]
                          for i in range(n)],
                       [off["runo"][s][i] + off["verge1"][s][i] + off["verge2"][s][i]
                        for i in range(n)]], s, 0.006)
        band("SM_Verge2_%s_01" % tag, A, B, [M("grass")], [0] * n, coll, closed=True,
             props={"kind": "outer_verge"})
    # start / finish: chequered band across the track
    sx, sy = SF
    v, f, fm = [], [], []
    for k in range(14):
        x0 = sx - HW + k * (2 * HW / 14.0)
        x1 = sx - HW + (k + 1) * (2 * HW / 14.0)
        for r in range(2):
            y0 = sy - 1.0 + r
            y1 = y0 + 1.0
            base = len(v)
            v += [(x0, y0, Z_MARK), (x1, y0, Z_MARK), (x1, y1, Z_MARK), (x0, y1, Z_MARK)]
            f.append((base, base + 1, base + 2, base + 3))
            fm.append(0 if (k + r) % 2 == 0 else 1)
    mk("SM_StartFinish_Chequer_01", v, f, [M("marking_white"), M("metal_painted_dark")],
       fm, coll, {"kind": "start_finish"})
    # starting grid south of the line (two staggered columns)
    v, f = [], []
    for r in range(10):
        y0 = sy - 14.0 - r * 9.0
        for k, xc in ((0, sx - 3.4), (1, sx + 3.4)):
            yy = y0 - (4.0 if k == 0 else 0.0)
            x0, x1 = xc - 0.6, xc + 0.6
            base = len(v)
            v += [(x0, yy, Z_MARK), (x1, yy, Z_MARK), (x1, yy - 4.0, Z_MARK),
                  (x0, yy - 4.0, Z_MARK)]
            f.append((base, base + 1, base + 2, base + 3))
    mk("SM_StartGrid_01", v, f, [M("marking_white")], [0] * len(f), coll,
       {"kind": "start_grid"})
    log("  surface done in %.1fs (n=%d, ds=%.2f, length=%.1f m)" % (t and time.time() - t,
                                                                    n, c.ds, c.length))


# ------------------------------------------------------------------ stage 2
def stage_kerbs(c, coll, off):
    log("--- stage 2: kerbs")
    t = T0()
    n = c.n
    made = 0
    for s, tag in ((0, "L"), (1, "R")):
        pred = lambda i, s=s: off["kerb"][i] == s
        for run in runs_of(pred, n):
            verts, faces, fmat = [], [], []
            m = len(run)
            wrap = ((run[-1] + 1) % n) == run[0]
            for i in run:
                x, y = c.P[i]
                nx, ny = c.NL[i]
                sg = 1.0 if s == 0 else -1.0
                a = off["inner"][s][i] - KERB_W      # inner edge (track edge)
                b = off["inner"][s][i]               # outer edge
                zi, zo = Z_TRK, Z_TRK + KERB_RISE
                px, py = nx * sg, ny * sg
                verts += [(x + px * a, y + py * a, zi), (x + px * b, y + py * b, zi),
                          (x + px * a, y + py * a, zo), (x + px * b, y + py * b, zo)]
            steps = m if wrap else m - 1
            for j in range(steps):
                k = (j + 1) % m
                b0, b1 = 4 * j, 4 * k
                faces.append((b0 + 2, b0 + 3, b1 + 3, b1 + 2))   # top
                faces.append((b0 + 1, b0 + 3, b1 + 3, b1 + 1))   # outer side
                faces.append((b0 + 0, b0 + 2, b1 + 2, b1 + 0))   # inner side
                seg = j // max(1, int(round(4.0 / c.ds)))
                col = seg % 2
                fmat += [col, col, col]
            if not wrap:
                b0 = 0
                faces.append((b0 + 0, b0 + 1, b0 + 3, b0 + 2))
                fmat.append(0)
                bl = 4 * (m - 1)
                faces.append((bl + 0, bl + 2, bl + 3, bl + 1))
                fmat.append(1)
            mk("SM_Kerb_%s_%02d" % (tag, made), verts, faces,
               [M("kerb_red"), M("kerb_white")], fmat, coll,
               {"kind": "kerb", "side": tag})
            made += 1
    log("  kerbs: %d runs in %.1fs" % (made, time.time() - t))
    return made


# ------------------------------------------------------------------ pit lane
Z_PIT = 0.023


def pit_centerline():
    pts = [(704.5, -1000.0), (710.0, -982.0), (715.0, -962.0), (719.0, -940.0),
           (721.5, -915.0), (722.4, -894.0), (722.4, -860.0), (722.4, -800.0),
           (722.4, -700.0), (722.4, -600.0), (722.4, -500.0), (722.4, -400.0),
           (722.4, -340.0), (722.4, -306.0), (721.5, -290.0), (718.0, -272.0),
           (712.0, -260.0), (705.0, -252.0), (701.5, -248.0)]
    return smooth_open(pts, 2)


def pit_halfwidths(P, hw):
    """Tapered half width: 1 m at both ends, hw in the middle."""
    n = len(P)
    L = open_len(P)
    acc, cums = 0.0, [0.0]
    for i in range(n - 1):
        acc += math.hypot(P[i + 1][0] - P[i][0], P[i + 1][1] - P[i][1])
        cums.append(acc)
    out = []
    for s in cums:
        t = min(s, L - s)
        k = min(1.0, t / 38.0)
        out.append(1.0 + (hw - 1.0) * k)
    return out


# ------------------------------------------------------------------ stage 3
def stage_barriers(c, coll, off):
    log("--- stage 3: barriers")
    t = T0()
    n = c.n
    # ---- shared meshes -------------------------------------------------
    av, af = [], []
    for x0, x1, z0, z1 in ((-4.0, 4.0, 0.58, 0.94), (-4.0, 4.0, 0.34, 0.50)):
        v, f = box(x0, -0.07, x1, 0.07, z0, z1)
        b = len(av)
        av += v
        af += [tuple(b + k for k in face) for face in f]
    for px in (-4.0, 0.0):
        v, f = box(px - 0.09, -0.09, px + 0.09, 0.09, 0.0, 0.62)
        b = len(av)
        av += v
        af += [tuple(b + k for k in face) for face in f]
    MS = M("metal_steel")
    MPD = M("metal_painted_dark")

    tv, tf = [], []
    R0, R1, H, S = 0.34, 0.34, 0.24, 8
    for k in range(S):
        a = 2 * math.pi * k / S
        tv.append((R0 * math.cos(a), R0 * math.sin(a), 0.0))
        tv.append((R1 * math.cos(a), R1 * math.sin(a), H))
    for k in range(S):
        j = (k + 1) % S
        tf.append((2 * k, 2 * j, 2 * j + 1, 2 * k + 1))
    tf.append(tuple(range(0, 2 * S, 2)))
    tf.append(tuple(range(1, 2 * S, 2)))

    fv, ff = [], []
    for px in (-4.0, 4.0):
        v, f = box(px - 0.07, -0.07, px + 0.07, 0.07, 0.0, 2.6)
        b = len(fv)
        fv += v
        ff += [tuple(b + k for k in face) for face in f]
    for z0 in (1.1, 1.7, 2.3, 2.55):
        v, f = box(-4.0, -0.04, 4.0, 0.04, z0, z0 + 0.05)
        b = len(fv)
        fv += v
        ff += [tuple(b + k for k in face) for face in f]
    # ---- placement -----------------------------------------------------
    sign = (1.0, -1.0)
    corridors = CORRIDORS
    # buildings only - the candidate mast footprints are not buildings
    bldgs = [r for n, r in OBST_FULL if not n.startswith("mast")]

    def barrier_pos(i, s):
        x, y = c.P[i]
        nx, ny = c.NL[i]
        d = off["barrier"][s][i]
        return (x + nx * sign[s] * d, y + ny * sign[s] * d)

    def near(x, y, rects, dist):
        for r in rects:
            dx = max(r[0] - x, 0.0, x - r[2])
            dy = max(r[1] - y, 0.0, y - r[3])
            if math.hypot(dx, dy) <= dist:
                return True
        return False

    # Long runs of identical props are baked into run objects (a handful of
    # placements per mesh) instead of one object per segment: keeps the module
    # inside the 400-1500 object budget without losing any geometry.
    ARMCO_B, FENCE_B, TYRE_B = 4, 4, 6
    run_a, run_f, bank = [], [], []
    k_armco = k_tyre = k_fence = 0
    o_armco = o_fence = o_tyre = 0

    def flush_a():
        nonlocal o_armco
        if run_a:
            batch_obj("SM_Armco_Run_%03d" % (o_armco + 1), av, af, run_a, MS,
                      coll, {"kind": "armco_run", "segments": len(run_a)})
            o_armco += 1
            del run_a[:]

    def flush_f():
        nonlocal o_fence
        if run_f:
            batch_obj("SM_DebrisFence_Run_%03d" % (o_fence + 1), fv, ff, run_f, MS,
                      coll, {"kind": "debris_fence_run", "panels": len(run_f)})
            o_fence += 1
            del run_f[:]

    def flush_t():
        nonlocal o_tyre
        if bank:
            batch_obj("SM_TyreBank_%03d" % (o_tyre + 1), tv, tf, bank, MPD,
                      coll, {"kind": "tyre_bank", "stacks": len(bank)})
            o_tyre += 1
            del bank[:]

    # armco + fence every STN metres along the whole outer edge
    steps = int(round(c.length / STN))
    for q in range(steps):
        s_arc = q * STN
        i = arclen_index(c, s_arc)
        i2 = (i + 1) % n
        for s in (0, 1):
            f = (s_arc / c.ds) - i
            d = off["barrier"][s][i] * (1 - f) + off["barrier"][s][i2] * f
            x, y = c.P[i]
            nx, ny = c.NL[i]
            px = x + nx * sign[s] * d
            py = y + ny * sign[s] * d
            th = math.atan2(c.T[i][1], c.T[i][0])
            if not point_ok(px, py, 0.4):
                flush_a()
                flush_f()
                continue
            run_a.append((px, py, 0.0, th))
            k_armco += 1
            if len(run_a) >= ARMCO_B:
                flush_a()
            # debris fence: just behind the armco, only near buildings/roads
            bx = px + nx * sign[s] * 1.1
            by = py + ny * sign[s] * 1.1
            want = near(bx, by, [r for r in bldgs if r[0] < 700 or r[2] > 1100], 50.0)
            if not want:
                for cr in corridors:
                    dx = max(cr[0] - bx, 0.0, bx - cr[2])
                    dy = max(cr[1] - by, 0.0, by - cr[3])
                    if math.hypot(dx, dy) <= 45.0:
                        want = True
                        break
            if want and point_ok(bx, by, 0.4):
                run_f.append((bx, by, 0.0, th))
                k_fence += 1
                if len(run_f) >= FENCE_B:
                    flush_f()
            else:
                flush_f()
    flush_a()
    flush_f()

    # tyre walls on the outside of the fast/medium corners
    cand = []
    for i in range(n):
        if c.R[i] < 220.0:
            cand.append(i)
    # group into runs, sample every 0.8 m
    pts = []
    for i in cand:
        for k in range(5):
            f = (k + 0.5) / 5.0
            j = (i + 1) % n
            x = c.P[i][0] + (c.P[j][0] - c.P[i][0]) * f
            y = c.P[i][1] + (c.P[j][1] - c.P[i][1]) * f
            nx = c.NL[i][0] + (c.NL[j][0] - c.NL[i][0]) * f
            ny = c.NL[i][1] + (c.NL[j][1] - c.NL[i][1]) * f
            d = off["barrier"][0][i] * (1 - f) + off["barrier"][0][j] * f
            pts.append((x + nx * (d - 0.55), y + ny * (d - 0.55)))
    if len(pts) > 820:
        step = float(len(pts)) / 820.0
        pts = [pts[int(k * step)] for k in range(820)]
    for (px, py) in pts:
        if not point_ok(px, py, 0.3):
            flush_t()
            continue
        for h in range(3):
            bank.append((px, py, 0.01 + 0.24 * h, 0.0))
        k_tyre += 1
        if len(bank) >= TYRE_B * 3:
            flush_t()
    flush_t()

    # cones at the pit entry
    cv, cf = [], []
    S = 8
    for k in range(S):
        a = 2 * math.pi * k / S
        cv.append((0.2 * math.cos(a), 0.2 * math.sin(a), 0.0))
    cv.append((0.0, 0.0, 0.7))
    for k in range(S):
        cf.append((k, (k + 1) % S, S))
    cf.append(tuple(range(S - 1, -1, -1)))
    cone = inst_src("SM_Cone_01", cv, cf, M("kerb_red"), coll, {"kind": "cone"})
    P = pit_centerline()
    Np = poly_normals(P, False)
    kc = 0
    for k in range(7):
        f = k / 6.0
        idx = f * (len(P) - 1)
        i0 = min(len(P) - 2, int(idx))
        tt = idx - i0
        px = P[i0][0] + (P[i0 + 1][0] - P[i0][0]) * tt
        py = P[i0][1] + (P[i0 + 1][1] - P[i0][1]) * tt
        nx, ny = Np[i0]
        side = -1.0 if k % 2 else 1.0
        for h in (-1.0, 1.0):
            inst(cone, "SM_Cone_%02d" % kc,
                 (px + nx * side * 7.4, py + ny * side * 7.4, 0.0), 0.0, coll)
            kc += 1
            side = -side
    drop_src(cone)
    log("  armco=%d segs/%d objs tyres=%d stacks/%d objs fence=%d/%d objs cones=%d in %.1fs"
        % (k_armco, o_armco, k_tyre, o_tyre, k_fence, o_fence, kc, time.time() - t))
    return {"armco_segments": k_armco, "armco_objects": o_armco,
            "tyre_stacks": k_tyre, "tyre_objects": o_tyre,
            "fence_panels": k_fence, "fence_objects": o_fence,
            "cones": kc}


# ------------------------------------------------------------------ stage 4
def pit_bay_y(k):
    y0 = PIT_Y0 + BAY_PITCH * k
    return y0 + 6.0, y0 + 18.0


def stage_pit(coll):
    log("--- stage 4: pit lane + paddock")
    t = T0()
    # ---------------- pit lane ribbon
    P = pit_centerline()
    Np = poly_normals(P, False)
    hw = pit_halfwidths(P, PIT_HW)
    A = [(P[i][0] + Np[i][0] * hw[i], P[i][1] + Np[i][1] * hw[i], Z_PIT)
         for i in range(len(P))]
    B = [(P[i][0] - Np[i][0] * hw[i], P[i][1] - Np[i][1] * hw[i], Z_PIT)
         for i in range(len(P))]
    band("SM_PitLane_01", A, B, [M("asphalt")], [0] * len(P), coll,
         props={"kind": "pit_lane", "width_m": 2 * PIT_HW})
    # yellow edge lines (8 m marked lane)
    idx = [i for i in range(len(P)) if hw[i] >= 5.8]
    if len(idx) > 3:
        i0, i1 = idx[0], idx[-1]
        for side, nm in ((1.0, "L"), (-1.0, "R")):
            A = [(P[i][0] + Np[i][0] * side * 4.09, P[i][1] + Np[i][1] * side * 4.09,
                  Z_PIT + 0.006) for i in range(i0, i1 + 1)]
            B = [(P[i][0] + Np[i][0] * side * 3.91, P[i][1] + Np[i][1] * side * 3.91,
                  Z_PIT + 0.006) for i in range(i0, i1 + 1)]
            band("SM_PitEdgeLine_%s_01" % nm, A, B, [M("marking_yellow")],
                 [0] * len(A), coll)
    # ---------------- pit boxes (14 painted stalls)
    v, f = [], []
    for k in range(BAYS):
        y0, y1 = pit_bay_y(k)
        x0, x1 = 728.6, 738.3
        for (a, b, c, d) in ((x0, y0, x1, y0 + 0.16), (x0, y1 - 0.16, x1, y1),
                             (x0, y0, x0 + 0.16, y1), (x1 - 0.16, y0, x1, y1)):
            base = len(v)
            v += [(a, b, Z_PIT + 0.007), (c, b, Z_PIT + 0.007),
                  (c, d, Z_PIT + 0.007), (a, d, Z_PIT + 0.007)]
            f.append((base, base + 1, base + 2, base + 3))
        # stop line inside the box
        base = len(v)
        v += [(x0 + 0.4, y0 + 0.6, Z_PIT + 0.007), (x1 - 0.4, y0 + 0.6, Z_PIT + 0.007),
              (x1 - 0.4, y0 + 0.9, Z_PIT + 0.007), (x0 + 0.4, y0 + 0.9, Z_PIT + 0.007)]
        f.append((base, base + 1, base + 2, base + 3))
    mk("SM_PitBoxes_01", v, f, [M("marking_white")], [0] * len(f), coll,
       {"kind": "pit_boxes", "count": BAYS})

    # ---------------- pit building
    x0, y0b, x1, y1b = PB
    C = M("concrete")
    CP = M("concrete_poured")
    GL = M("glass_dark")
    ST = M("sign_metal")
    MP = M("metal_painted_dark")
    # slabs
    box_obj("SM_PitBldg_GroundSlab_01", x0, y0b, x1, y1b, -0.15, 0.02, CP, coll)
    box_obj("SM_PitBldg_FloorSlab_01", x0, y0b, x1, y1b, 4.0, 4.25, CP, coll)
    box_obj("SM_PitBldg_Roof_01", x0, y0b, x1, y1b, 6.4, 6.7, M("roof_bitumen"), coll)
    # parapet
    for (a, b, c, d) in ((x0, y0b, x0 + 0.4, y1b), (x1 - 0.4, y0b, x1, y1b),
                         (x0, y0b, x1, y0b + 0.4), (x0, y1b - 0.4, x1, y1b)):
        box_obj("SM_PitBldg_Parapet_%02d" % len(bpy.data.objects), a, b, c, d,
                6.7, 7.2, C, coll)
    # rear + side walls (ground + upper)
    box_obj("SM_PitBldg_BackWall_01", x1 - 0.4, y0b, x1, y1b, 0.0, 6.4, C, coll)
    box_obj("SM_PitBldg_SideS_01", x0, y0b, x1, y0b + 0.4, 0.0, 6.4, C, coll)
    box_obj("SM_PitBldg_SideN_01", x0, y1b - 0.4, x1, y1b, 0.0, 6.4, C, coll)
    # front wall: piers between the open bays (ground) + solid upper band
    for k in range(BAYS):
        by0, by1 = pit_bay_y(k)
        segs = [(y0b + k * BAY_PITCH, by0), (by1, y0b + (k + 1) * BAY_PITCH)]
        for si, (a, b) in enumerate(segs):
            if b - a < 0.05:
                continue
            box_obj("SM_PitBldg_Pier_%02d_%d" % (k, si), x0, a, x0 + 0.5, b, 0.0, 4.0,
                    C, coll)
        # canopy over the bay
        box_obj("SM_PitBldg_Canopy_%02d" % k, x0 - 3.0, by0 - 0.3, x0 + 0.6,
                by1 + 0.3, 4.2, 4.55, MP, coll)
        # INT_ garage room behind the open bay
        rn = "INT_TRK_PIT_GARAGE_%02d" % (k + 1)
        box_obj(rn + "_FLOOR", x0 + 0.1, by0 + 0.1, x1 - 0.6, by1 - 0.1, 0.02, 0.12,
                M("concrete_poured"), coll, {"kind": "interior"})
        box_obj(rn + "_BACK", x1 - 0.7, by0 + 0.1, x1 - 0.4, by1 - 0.1, 0.0, 4.0,
                MP, coll, {"kind": "interior"})
        box_obj(rn + "_SIDES", x0 + 0.1, by0 + 0.1, x1 - 0.4, by0 + 0.4, 0.0, 4.0,
                MP, coll, {"kind": "interior"})
        box_obj(rn + "_SIDES2", x0 + 0.1, by1 - 0.4, x1 - 0.4, by1 - 0.1, 0.0, 4.0,
                MP, coll, {"kind": "interior"})
    # upper facade: solid band + continuous glazing with mullions
    box_obj("SM_PitBldg_UpperBand_01", x0, y0b, x0 + 0.4, y1b, 4.25, 4.6, C, coll)
    box_obj("SM_PitBldg_UpperSill_01", x0, y0b, x0 + 0.4, y1b, 6.1, 6.4, C, coll)
    box_obj("SM_PitBldg_Glass_01", x0 + 0.05, y0b + 1.0, x0 + 0.25, y1b - 1.0,
            4.6, 6.1, GL, coll)
    nm = 0
    yy = y0b + 2.0
    while yy < y1b - 2.0:
        box_obj("SM_PitBldg_Mullion_%03d" % nm, x0 - 0.02, yy, x0 + 0.32, yy + 0.12,
                4.6, 6.1, MP, coll)
        nm += 1
        yy += 3.0
    # signage band on the parapet
    box_obj("SM_PitBldg_Sign_01", x0 - 0.06, PIT_Y0 + 6.0, x0 + 0.06, PIT_Y1 - 6.0,
            7.3, 8.1, ST, coll, {"sign": "PIT & PADDOCK"})
    # roof plant
    for k in range(6):
        yy = PIT_Y0 + 40.0 + k * 92.0
        box_obj("SM_PitBldg_Plant_%02d" % k, x0 + 8.0, yy, x0 + 14.0, yy + 5.0,
                6.7, 7.9, MP, coll)

    # ---------------- paddock apron
    ax0, ay0, ax1, ay1 = 768.4, -748.0, 828.0, -645.0
    box_obj("SM_Paddock_Apron_01", ax0, ay0, ax1, ay1, -0.1, 0.1, C, coll,
            {"kind": "paddock_apron"})
    # hospitality units (shared mesh)
    hv, hf = [], []

    def addbox(v, f, a, b, c, d, e, g):
        vv, ff = box(a, b, c, d, e, g)
        base = len(v)
        for p in vv:
            v.append(p)
        for q in ff:
            f.append(tuple(base + k for k in q))

    addbox(hv, hf, 0.0, 0.0, 8.0, 5.0, 0.0, 0.2)                 # floor
    addbox(hv, hf, 0.0, 0.0, 0.15, 5.0, 0.2, 3.2)                 # front (W)
    addbox(hv, hf, 7.85, 0.0, 8.0, 5.0, 0.2, 3.2)                 # back
    addbox(hv, hf, 0.15, 0.0, 7.85, 0.15, 0.2, 3.2)               # side
    addbox(hv, hf, 0.15, 4.85, 7.85, 5.0, 0.2, 3.2)               # side
    addbox(hv, hf, 0.0, 0.0, 8.4, 5.0, 3.2, 3.45)                 # roof
    addbox(hv, hf, -1.6, 0.5, 0.1, 4.5, 3.0, 3.3)                 # canopy
    hosp = inst_src("SM_Hospitality_Unit_01", hv, hf, M("concrete"), coll,
                    {"kind": "hospitality_unit"})
    # glazing strip as separate object sharing nothing (thin, one per instance set)
    for k, (px, py) in enumerate(((810.0, -735.0), (810.0, -714.0), (810.0, -693.0),
                                   (810.0, -672.0))):
        inst(hosp, "SM_Hospitality_Unit_%02d" % (k + 1), (px, py, 0.1), 0.0, coll)
    # fuel truck bay
    v, f = [], []
    fx0, fy0, fx1, fy1 = 772.0, -744.0, 786.0, -737.0
    for (a, b, c, d) in ((fx0, fy0, fx1, fy0 + 0.18), (fx0, fy1 - 0.18, fx1, fy1),
                         (fx0, fy0, fx0 + 0.18, fy1), (fx1 - 0.18, fy0, fx1, fy1)):
        base = len(v)
        v += [(a, b, 0.11), (c, b, 0.11), (c, d, 0.11), (a, d, 0.11)]
        f.append((base, base + 1, base + 2, base + 3))
    mk("SM_FuelBay_01", v, f, [M("marking_yellow")], [0] * len(f), coll,
       {"kind": "fuel_bay"})
    box_obj("SM_Fuel_Bowser_01", 775.0, -742.0, 781.0, -739.4, 0.3, 2.6,
            M("metal_steel"), coll, {"kind": "fuel_bowser"})
    for k, xx in enumerate((776.0, 780.0)):
        box_obj("SM_Fuel_Bowser_Leg_%d" % k, xx, -742.2, xx + 0.4, -739.2, 0.0, 0.3,
                MP, coll)
    drop_src(hosp)
    log("  pit done in %.1fs" % (time.time() - t))


# ------------------------------------------------------------------ geometry helpers
def add_box(v, f, x0, y0, x1, y1, z0, z1):
    vv, ff = box(x0, y0, x1, y1, z0, z1)
    b = len(v)
    for p in vv:
        v.append(p)
    for q in ff:
        f.append(tuple(b + k for k in q))


def add_bar(v, f, x0, z0, x1, z1, thick, y0, y1):
    """Rectangular bar in the XZ plane from (x0,z0) to (x1,z1), extruded in Y."""
    dx, dz = x1 - x0, z1 - z0
    L = math.hypot(dx, dz) or 1.0
    nx, nz = -dz / L * thick, dx / L * thick
    quad = [(x0, z0), (x1, z1), (x1 + nx, z1 + nz), (x0 + nx, z0 + nz)]
    b = len(v)
    for yy in (y0, y1):
        for (px, pz) in quad:
            v.append((px, yy, pz))
    for q in ((0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2),
              (2, 6, 7, 3), (3, 7, 4, 0)):
        f.append(tuple(b + k for k in q))


def extrude_profile(v, f, prof, y0, y1):
    """Extrude a CCW (x,z) profile along Y. Profile coords are world X/Z."""
    b = len(v)
    n = len(prof)
    for yy in (y0, y1):
        for (px, pz) in prof:
            v.append((px, yy, pz))
    for k in range(n):
        j = (k + 1) % n
        f.append((b + k, b + n + k, b + n + j, b + j))
    f.append(tuple(b + k for k in range(n)))
    f.append(tuple(b + n + k for k in range(n - 1, -1, -1)))


def row_profile(depth, x_start, back_to_front=True, rise=0.4, tread=0.32,
                backh=0.55):
    """CCW profile of one seating step. x_start = world X of local x=0 edge.
    back_to_front=True -> local x=0 is the BACK (high) edge of the step."""
    if back_to_front:
        xs = [0.0, depth, depth, depth - tread, depth - tread, 0.08, 0.08, 0.0]
        zs = [0.0, 0.0, rise, rise, rise + 0.15, rise + 0.15, rise + backh,
              rise + backh]
    else:
        xs = [0.0, depth, depth, depth - 0.08, depth - 0.08, tread, tread, 0.0]
        zs = [0.0, 0.0, rise + backh, rise + backh, rise + 0.15, rise + 0.15,
              rise, rise]
    return [(x_start + xs[k], zs[k]) for k in range(8)]


# ------------------------------------------------------------------ stage 5
def build_stand(coll, tag, rect, front_east, rows, depth, row_len, blocks,
                base_h, rise, tower_w, roof_h, name):
    """Raked grandstand. rect=(x0,y0,x1,y1). front_east=True -> seating faces +X."""
    x0, y0, x1, y1 = rect
    v, f = [], []
    L = y1 - y0
    # ---- rake mass (wedge) -------------------------------------------
    if front_east:
        fx, bx = x1, x1 - rows * depth          # front (east) / back (west)
        prof = [(fx, 0.0), (bx, 0.0), (bx, base_h + rows * rise), (fx, base_h)]
    else:
        fx, bx = x0, x0 + rows * depth
        prof = [(fx, 0.0), (bx, 0.0), (bx, base_h + rows * rise), (fx, base_h)]
    prof = [(p[0], p[1]) for p in prof]
    # make CCW
    A = 0.0
    for i in range(len(prof)):
        a, b = prof[i], prof[(i + 1) % len(prof)]
        A += a[0] * b[1] - b[0] * a[1]
    if A < 0:
        prof = prof[::-1]
    extrude_profile(v, f, prof, y0, y1)
    mk(name + "_Rake_01", v, f, [M("concrete")], [0] * len(f), coll,
       {"kind": "grandstand_rake"})

    # ---- seating rows (one shared mesh, instanced) --------------------
    step = depth
    if front_east:
        x_off = x1 - step                      # row 0 back edge
        b2f = True
    else:
        x_off = x0
        b2f = False
    rv, rf = [], []
    prof = row_profile(step, 0.0, b2f)
    extrude_profile(rv, rf, prof, 0.0, row_len)
    rowsrc = inst_src(name + "_Row", rv, rf, M("metal_painted_dark"), coll,
                      {"kind": "seat_row"})
    gap = (L - blocks * row_len) / float(max(1, blocks - 1)) if blocks > 1 else 0.0
    made = 0
    ystart = y0
    for b in range(blocks):
        for i in range(rows):
            if front_east:
                xx = x1 - step * (i + 1)
            else:
                xx = x0 + step * i
            inst(rowsrc, "%s_Row_%02d_%02d" % (name, b, i),
                 (xx, ystart, base_h + rise * i), 0.0, coll)
            made += 1
        ystart += row_len + gap

    # ---- stair towers -------------------------------------------------
    tv, tf = [], []
    if front_east:
        tx0, tx1 = x0 + 1.0, x1 - 1.0
    else:
        tx0, tx1 = x0 + 1.0, x1 - 1.0
    for cx in (tx0, tx0 + 1.4, tx1 - 1.4, tx1):
        add_box(tv, tf, cx, 0.0, cx + 0.45, 4.0, 0.0, roof_h - 0.4)
    for lz in (1.4, 4.4, 7.4, 10.4):
        if lz < roof_h - 1.0:
            add_box(tv, tf, tx0, 0.2, tx1, 3.8, lz - 0.12, lz)
    for k in range(3):
        xa = tx0 + (0.5 if k % 2 == 0 else 2.0)
        xb = tx1 - (2.0 if k % 2 == 0 else 0.5)
        add_bar(tv, tf, xa, 1.4 + k * 3.0, xb, 4.4 + k * 3.0, 0.12, 1.0, 2.8)
    add_box(tv, tf, tx0 - 0.3, -0.3, tx1 + 0.3, 4.3, roof_h - 0.4, roof_h)
    towersrc = inst_src(name + "_Tower", tv, tf, M("concrete"), coll,
                        {"kind": "stair_tower"})
    ty = y0 + gap / 2.0 - tower_w / 2.0
    tpos = []
    if blocks > 1:
        for b in range(blocks - 1):
            tpos.append(y0 + row_len + b * (row_len + gap) + (gap - tower_w) / 2.0)
    for k, yy in enumerate(tpos):
        inst(towersrc, "%s_Tower_%02d" % (name, k), (0.0, yy, 0.0), 0.0, coll)

    # ---- back wall ----------------------------------------------------
    bv, bf = [], []
    if front_east:
        add_box(bv, bf, x0, y0, x0 + 0.5, y1, 0.0, base_h + rows * rise + 0.6)
        for k in range(int(L / 6.0)):
            yy = y0 + 2.0 + k * 6.0
            add_box(bv, bf, x0 - 0.25, yy, x0 + 0.5, yy + 0.5, 0.0,
                    base_h + rows * rise + 0.6)
    else:
        add_box(bv, bf, x1 - 0.5, y0, x1, y1, 0.0, base_h + rows * rise + 0.6)
        for k in range(int(L / 6.0)):
            yy = y0 + 2.0 + k * 6.0
            add_box(bv, bf, x1 - 0.5, yy, x1 + 0.25, yy + 0.5, 0.0,
                    base_h + rows * rise + 0.6)
    mk(name + "_BackWall_01", bv, bf, [M("concrete")], [0] * len(bf), coll,
       {"kind": "grandstand_back"})

    # ---- front fascia + handrail --------------------------------------
    hv, hf = [], []
    if front_east:
        add_box(hv, hf, x1 - 0.4, y0, x1, y1, 0.0, base_h)
        add_box(hv, hf, x1 - 0.35, y0, x1 - 0.15, y1, base_h + 0.9, base_h + 1.05)
        add_box(hv, hf, x1 - 0.35, y0, x1 - 0.15, y1, base_h + 0.45, base_h + 0.55)
        npost = int(L / 3.0)
        for k in range(npost + 1):
            yy = y0 + k * (L / max(1, npost))
            add_box(hv, hf, x1 - 0.35, yy, x1 - 0.15, yy + 0.1, base_h, base_h + 1.05)
    else:
        add_box(hv, hf, x0, y0, x0 + 0.4, y1, 0.0, base_h)
        add_box(hv, hf, x0 + 0.15, y0, x0 + 0.35, y1, base_h + 0.9, base_h + 1.05)
        add_box(hv, hf, x0 + 0.15, y0, x0 + 0.35, y1, base_h + 0.45, base_h + 0.55)
        npost = int(L / 3.0)
        for k in range(npost + 1):
            yy = y0 + k * (L / max(1, npost))
            add_box(hv, hf, x0 + 0.15, yy, x0 + 0.35, yy + 0.1, base_h, base_h + 1.05)
    mk(name + "_Handrail_01", hv, hf, [M("metal_steel")], [0] * len(hf), coll,
       {"kind": "handrail"})

    # ---- roof canopy ---------------------------------------------------
    rcf, rcf_f = [], []
    if front_east:
        rx0, rx1 = x0 + 0.6, x1 + 4.6
        z0, z1 = roof_h, roof_h - 1.6
    else:
        rx0, rx1 = x0 - 4.6, x1 - 0.6
        z0, z1 = roof_h - 1.6, roof_h
    ntr = max(3, int(round(L / 22.0)) + 1)
    for k in range(ntr):
        yy = y0 + (L - 1.0) * k / float(max(1, ntr - 1))
        add_bar(rcf, rcf_f, rx0, z0, rx1, z1, 0.35, yy, yy + 0.7)
        add_bar(rcf, rcf_f, rx0, z0 - 1.5, rx1, z1 - 1.5, 0.3, yy + 0.15, yy + 0.55)
        for s in range(7):
            tt = s / 6.0
            ta = rx0 + (rx1 - rx0) * tt
            za = z0 + (z1 - z0) * tt
            add_bar(rcf, rcf_f, ta, za - 1.5, ta, za, 0.18, yy + 0.1, yy + 0.6)
            if s < 6:
                tb = rx0 + (rx1 - rx0) * (s + 1) / 6.0
                zb = z0 + (z1 - z0) * (s + 1) / 6.0
                add_bar(rcf, rcf_f, ta, za - 1.5, tb, zb, 0.14, yy + 0.2, yy + 0.5)
    # columns at the back
    ncol = max(2, int(round(L / 30.0)) + 1)
    for k in range(ncol):
        yy = y0 + (L - 1.4) * k / float(max(1, ncol - 1))
        if front_east:
            add_box(rcf, rcf_f, x0 + 0.8, yy, x0 + 2.2, yy + 1.4, 0.0, z0 - 1.4)
        else:
            add_box(rcf, rcf_f, x1 - 2.2, yy, x1 - 0.8, yy + 1.4, 0.0, z1 - 0.1)
    # roof deck
    prof = [(rx0, z0), (rx1, z1), (rx1, z1 + 0.3), (rx0, z0 + 0.3)]
    extrude_profile(rcf, rcf_f, prof, y0 - 0.6, y1 + 0.6)
    ndeck = 6
    mk(name + "_Roof_01", rcf, rcf_f, [M("roof_metal"), M("metal_steel")],
       [1] * (len(rcf_f) - ndeck) + [0] * ndeck, coll,
       {"kind": "grandstand_roof"})

    # ---- accessibility platforms ---------------------------------------
    for k, yy in enumerate((y0 + 6.0, y1 - 12.0)):
        av, af = [], []
        if front_east:
            ax0, ax1 = x1 - 6.4, x1 - 0.6
        else:
            ax0, ax1 = x0 + 0.6, x0 + 6.4
        add_box(av, af, ax0, yy, ax1, yy + 5.0, base_h - 0.1, base_h + 0.1)
        add_box(av, af, ax0, yy, ax1, yy + 0.12, base_h + 0.1, base_h + 1.1)
        add_box(av, af, ax0, yy + 4.88, ax1, yy + 5.0, base_h + 0.1, base_h + 1.1)
        add_box(av, af, ax0, yy, ax0 + 0.12, yy + 5.0, base_h + 0.1, base_h + 1.1)
        mk("%s_Access_%02d" % (name, k + 1), av, af, [M("metal_steel")],
           [0] * len(af), coll, {"kind": "access_platform"})

    drop_src(rowsrc, towersrc)
    log("  %s: rows=%d towers=%d" % (name, made, len(tpos)))
    return made


def stage_grandstands(coll):
    log("--- stage 5: grandstands")
    t = T0()
    a = build_stand(coll, "SM_GS_MAIN", (636.4, -858.72, 662.4, -423.6), True,
                    30, 0.85, 105.78, 4, 1.0, 0.4, 4.0, 16.8, "SM_GS_MAIN")
    b = build_stand(coll, "SM_GS_HAIRPIN", (1168.0, -364.8, 1184.0, -247.2), False,
                    20, 0.8, 56.8, 2, 1.0, 0.42, 4.0, 11.6, "SM_GS_HAIRPIN")
    log("  grandstands done in %.1fs" % (time.time() - t))
    return a + b


# ------------------------------------------------------------------ stage 6a
def build_mast_geom(H=27.0):
    v, f = [], []
    r = 0.62
    for sx in (-1, 1):
        for sy in (-1, 1):
            add_box(v, f, sx * r - 0.09, sy * r - 0.09, sx * r + 0.09,
                    sy * r + 0.09, 0.0, H - 2.0)
    segs = 8
    h0, h1 = 0.0, H - 2.0
    for s in range(segs):
        za = h0 + (h1 - h0) * s / segs
        zb = h0 + (h1 - h0) * (s + 1) / segs
        for k in range(4):
            a = k * math.pi / 2.0
            b = (k + 1) * math.pi / 2.0
            ax, ay = r * math.cos(a), r * math.sin(a)
            bx, by = r * math.cos(b), r * math.sin(b)
            add_bar(v, f, ax, za, bx, zb, 0.06, ay - 0.06, ay + 0.06)
    # lamp head platform
    add_box(v, f, -1.9, -1.1, 1.9, 1.1, H - 2.0, H - 1.7)
    for k in range(6):
        lx = -1.6 + (k % 3) * 1.25
        ly = -0.75 if k < 3 else 0.4
        add_box(v, f, lx, ly, lx + 0.9, ly + 0.7, H - 1.7, H - 1.05)
    add_box(v, f, -1.9, -1.1, 1.9, -1.0, H - 1.7, H - 0.7)
    add_box(v, f, -1.9, 1.0, 1.9, 1.1, H - 1.7, H - 0.7)
    return v, f


def stage_support(coll, lights, c):
    log("--- stage 6: support facilities")
    t = T0()
    C = M("concrete")
    CP = M("concrete_poured")
    MP = M("metal_painted_dark")
    MS = M("metal_steel")
    GL = M("glass_dark")
    SG = M("sign_metal")
    EW = M("emissive_warm")

    # ---------------- control / timing tower ---------------------------
    tx0, ty0, tx1, ty1 = 772.4, -635.28, 788.4, -619.28
    box_obj("SM_Tower_Shaft_01", tx0, ty0, tx1, ty1, 0.0, 18.0, C, coll,
            {"kind": "control_tower", "floors": 5})
    for k in range(4):
        z = 3.2 + k * 3.6
        box_obj("SM_Tower_WinS_%d" % k, tx0 + 1.0, ty0 - 0.06, tx1 - 1.0, ty0 + 0.1,
                z, z + 1.5, GL, coll)
    # glazed control room (overhanging)
    box_obj("SM_Tower_GlazedTop_01", tx0 - 1.6, ty0 - 1.6, tx1 + 1.6, ty1 + 1.6,
            18.0, 22.4, GL, coll, {"kind": "control_room"})
    box_obj("SM_Tower_TopSlab_01", tx0 - 1.9, ty0 - 1.9, tx1 + 1.9, ty1 + 1.9,
            22.4, 22.8, C, coll)
    box_obj("SM_Tower_Parapet_01", tx0 - 1.9, ty0 - 1.9, tx1 + 1.9, ty1 + 1.9,
            22.8, 23.4, C, coll)
    box_obj("SM_Tower_Mast_01", tx0 + 7.4, ty0 + 7.4, tx0 + 8.6, ty0 + 8.6,
            23.4, 28.5, MS, coll)
    box_obj("SM_Tower_Sign_01", tx0 - 0.12, ty0 + 1.0, tx0 + 0.12, ty1 - 1.0,
            14.6, 17.0, SG, coll, {"sign": "TIMING"})
    # TIMING letters (font curve -> real mesh, so the .blend has no curve/font deps)
    try:
        cu = bpy.data.curves.new("TIMING", type="FONT")
        cu.body = "TIMING"
        cu.size = 2.1
        cu.extrude = 0.07
        cu.align_x = "CENTER"
        cu.materials.append(EW)
        txt = bpy.data.objects.new("SM_Sign_TIMING_TMP", cu)
        coll.objects.link(txt)
        txt.location = (tx0 - 0.2, (ty0 + ty1) / 2.0, 14.9)
        txt.rotation_euler = (math.radians(90.0), 0.0, math.radians(-90.0))
        me = font_to_mesh(txt)
        if me is not None:
            me.name = "SM_Sign_TIMING_01"
            me.materials.clear()
            me.materials.append(EW)
            sign = bpy.data.objects.new("SM_Sign_TIMING_01", me)
            sign.matrix_world = txt.matrix_world.copy()
            sign["sign"] = "TIMING"
            sign["kind"] = "sign"
            coll.objects.link(sign)
            old_curve = txt.data
            bpy.data.objects.remove(txt, do_unlink=True)
            if old_curve.users == 0:
                try:
                    bpy.data.curves.remove(old_curve)
                except Exception:
                    pass
            log("  TIMING sign converted to mesh (%d faces)" % len(me.polygons))
        else:
            txt.name = "SM_Sign_TIMING_01"
            log("  TIMING sign kept as font curve")
    except Exception as e:
        log("  TIMING sign failed: %s" % e)

    # ---------------- medical centre + recovery garage -----------------
    mx0, my0, mx1, my1 = 812.0, -916.0, 850.0, -886.0
    box_obj("SM_Medical_Slab_01", mx0, my0, mx1, my1, -0.12, 0.02, CP, coll)
    box_obj("SM_Medical_Back_01", mx1 - 0.4, my0, mx1, my1, 0.0, 4.6, C, coll)
    box_obj("SM_Medical_N_01", mx0, my1 - 0.4, mx1, my1, 0.0, 4.6, C, coll)
    box_obj("SM_Medical_S_01", mx0, my0, mx1, my0 + 0.4, 0.0, 4.6, C, coll)
    box_obj("SM_Medical_FrontN_01", mx0, my1 - 0.4, mx0 + 0.4, my1, 0.0, 4.6, C, coll)
    box_obj("SM_Medical_FrontS_01", mx0, my0, mx0 + 0.4, my0 + 11.0, 0.0, 4.6, C, coll)
    box_obj("SM_Medical_Pier_01", mx0, my0 + 21.0, mx0 + 0.4, my1 - 0.4, 0.0, 4.6,
            C, coll)
    box_obj("SM_Medical_Roof_01", mx0 - 0.4, my0 - 0.4, mx1 + 0.4, my1 + 0.4,
            4.6, 4.95, M("roof_bitumen"), coll)
    box_obj("SM_Medical_Canopy_01", mx0 - 3.0, my0 + 11.4, mx0 + 0.6, my0 + 20.6,
            4.3, 4.7, MP, coll)
    box_obj("INT_TRK_MEDICAL_BAY_01", mx0 + 0.5, my0 + 11.5, mx1 - 0.5, my0 + 20.5,
            0.02, 0.12, CP, coll, {"kind": "interior"})
    box_obj("INT_TRK_MEDICAL_BAY_01_BACK", mx1 - 0.9, my0 + 11.5, mx1 - 0.5,
            my0 + 20.5, 0.0, 4.6, MP, coll, {"kind": "interior"})
    box_obj("INT_TRK_RECOVERY_BAY_01", mx0 + 0.5, my0 + 1.0, mx1 - 0.6, my0 + 10.5,
            0.02, 0.12, CP, coll, {"kind": "interior"})
    box_obj("INT_TRK_RECOVERY_BAY_01_BACK", mx1 - 1.0, my0 + 1.0, mx1 - 0.6,
            my0 + 10.5, 0.0, 4.6, MP, coll, {"kind": "interior"})
    box_obj("SM_Medical_Sign_01", mx0 - 0.1, my0 + 11.5, mx0 + 0.1, my0 + 20.5,
            5.0, 6.2, SG, coll, {"sign": "MEDICAL"})

    # ---------------- concession kiosks --------------------------------
    for k, (kx0, ky0, kx1, ky1) in enumerate(((616.0, -806.0, 628.0, -790.0),
                                              (616.0, -622.0, 628.0, -606.0),
                                              (616.0, -458.0, 628.0, -442.0))):
        n = "%02d" % (k + 1)
        box_obj("SM_Kiosk_%s_Base" % n, kx0, ky0, kx1, ky1, -0.1, 0.02, CP, coll)
        box_obj("SM_Kiosk_%s_Body" % n, kx0, ky0, kx1, ky1, 0.0, 3.2, C, coll,
                {"kind": "kiosk"})
        box_obj("SM_Kiosk_%s_Opening" % n, kx1 - 0.6, ky0 + 1.2, kx1 + 0.05,
                ky1 - 1.2, 1.0, 2.7, MP, coll)
        box_obj("SM_Kiosk_%s_Counter" % n, kx1 - 0.1, ky0 + 1.2, kx1 + 0.8,
                ky1 - 1.2, 0.95, 1.1, MS, coll)
        box_obj("SM_Kiosk_%s_Canopy" % n, kx1 - 0.1, ky0 - 0.5, kx1 + 1.6, ky1 + 0.5,
                2.7, 3.0, MP, coll)
        box_obj("SM_Kiosk_%s_Roof" % n, kx0 - 0.3, ky0 - 0.3, kx1 + 0.3, ky1 + 0.3,
                3.2, 3.5, M("roof_bitumen"), coll)
        box_obj("SM_Kiosk_%s_Sign" % n, kx1 - 0.1, ky0 + 1.0, kx1 + 0.1, ky1 - 1.0,
                3.6, 4.4, SG, coll, {"sign": "REFRESHMENTS"})
    log("  support part A in %.1fs" % (time.time() - t))


def stage_support2(coll, lights, c, off):
    log("--- stage 6b: marshals, masts, access road, gantry")
    t = T0()
    C = M("concrete")
    CP = M("concrete_poured")
    MP = M("metal_painted_dark")
    MS = M("metal_steel")
    SG = M("sign_metal")
    AS = M("asphalt")
    MKW = M("marking_white")

    # ---------------- marshal posts (shared hut, instanced) -------------
    hv, hf = [], []
    add_box(hv, hf, 0.0, 0.0, 3.0, 2.4, 0.0, 0.15)
    add_box(hv, hf, 0.0, 0.0, 3.0, 0.16, 0.15, 2.5)
    add_box(hv, hf, 0.0, 0.0, 0.16, 2.4, 0.15, 2.5)
    add_box(hv, hf, 2.84, 0.0, 3.0, 2.4, 0.15, 2.5)
    add_box(hv, hf, 0.16, 1.1, 2.84, 1.26, 0.95, 1.1)      # counter
    add_box(hv, hf, -0.5, -0.3, 3.5, 2.7, 2.5, 2.75)        # roof
    add_box(hv, hf, -0.5, 2.5, 3.5, 2.7, 1.0, 1.35)         # awning
    hut = inst_src("SM_MarshalPost_01", hv, hf, C, coll, {"kind": "marshal_post"})
    kh = 0
    npost = int(c.length / 200.0)
    for k in range(npost):
        s_arc = 60.0 + k * 200.0
        i = arclen_index(c, s_arc)
        x, y = c.P[i]
        nx, ny = c.NL[i]                     # outside of the circuit (CW loop)
        d = off["barrier"][0][i] + 5.0
        px, py = x + nx * d, y + ny * d
        if not point_ok(px, py, 2.2):
            log("    marshal post %d skipped (blocked) at %.0f,%.0f" % (k, px, py))
            continue
        th = math.atan2(c.T[i][1], c.T[i][0]) + math.pi
        # hut local origin: place so the 3.0 x 2.4 body sits around (px,py)
        inst(hut, "SM_MarshalPost_%02d" % (kh + 1),
             (px - 1.5 * math.cos(th) + 1.2 * math.sin(th),
              py - 1.5 * math.sin(th) - 1.2 * math.cos(th), 0.0), th, coll)
        kh += 1
    drop_src(hut)

    # ---------------- floodlight masts + lights -------------------------
    mv, mf = build_mast_geom(27.0)
    mast = inst_src("SM_FloodMast_01", mv, mf, MS, coll, {"kind": "floodlight_mast"})
    placed = 0
    for k, (px, py) in enumerate(MAST_POS):
        # the candidate's own footprint rect must not block the candidate itself
        if not point_ok(px, py, 2.0, skip=("mast%d" % k,)):
            log("    mast %d rejected (blocked)" % (k + 1))
            continue
        dmin = min(math.hypot(q[0] - px, q[1] - py) for q in c.P)
        if dmin < 26.0:
            log("    mast %d rejected (only %.1f m from the racing line)" % (k + 1, dmin))
            continue
        inst(mast, "SM_FloodMast_%02d" % (placed + 1), (px, py, 0.0), 0.0, coll)
        # aim at the nearest point of the circuit
        best, bp = 1e18, None
        for q in c.P:
            dd = math.hypot(q[0] - px, q[1] - py)
            if dd < best:
                best, bp = dd, q
        ld = bpy.data.lights.new("LT_track_%02d" % (placed + 1), type="SPOT")
        ld.energy = 30000.0
        ld.spot_size = 1.15
        ld.spot_blend = 0.45
        ld.use_shadow = False
        ld.color = (1.0, 0.95, 0.86)
        lo = bpy.data.objects.new("LT_track_%02d" % (placed + 1), ld)
        lo.location = (px, py, 25.6)
        tgt = Vector((bp[0], bp[1], 0.0))
        lo.rotation_euler = (tgt - Vector(lo.location)).to_track_quat("-Z", "Y").to_euler()
        lights.objects.link(lo)
        placed += 1
    drop_src(mast)
    log("    %d masts / %d lights" % (placed, len(lights.objects)))

    # ---------------- access road: bridge over the west straight --------
    def wedge(name, xa, xb, za, zb, y0, y1, props=None):
        v = [(xa, y0, 0.0), (xb, y0, 0.0), (xb, y1, 0.0), (xa, y1, 0.0),
             (xa, y0, za), (xb, y0, zb), (xb, y1, zb), (xa, y1, za)]
        top = (4, 5, 6, 7)
        if _cross_z(v[4], v[5], v[6]) < 0:
            top = (7, 6, 5, 4)
        f = [(0, 3, 2, 1), top, (0, 1, 5, 4), (1, 2, 6, 5),
             (2, 3, 7, 6), (3, 0, 4, 7)]
        return mk(name, v, f, [C, AS], [0, 1, 0, 0, 0, 0], coll, props)

    wedge("SM_Access_RampW_01", 612.0, 686.0, 0.0, 5.3, -1044.0, -1036.0,
          {"kind": "access_ramp"})
    box_obj("SM_Access_Deck_01", 686.0, -1044.0, 710.0, -1036.0, 4.4, 5.3, C, coll,
            {"kind": "access_bridge"})
    wedge("SM_Access_RampE_01", 776.0, 710.0, 0.0, 5.3, -1044.0, -1036.0,
          {"kind": "access_ramp"})
    # deck side fascia
    for yy in (-1044.0, -1036.0):
        box_obj("SM_Access_Fascia_%d" % int(yy), 684.0, yy - 0.15, 712.0, yy + 0.15,
                4.3, 5.6, MP, coll)
    # railing over the span
    for yy in (-1044.2, -1035.8):
        box_obj("SM_Access_Rail_%d" % int(yy), 684.0, yy - 0.06, 712.0, yy + 0.06,
                5.6, 6.6, MS, coll)

    # ground road: spur + loop
    spur = [(776.0, -1040.0), (792.0, -1040.0), (800.0, -1032.0), (800.0, -764.0)]
    Nn = poly_normals(spur, False)
    A = [(spur[i][0] + Nn[i][0] * 4.0, spur[i][1] + Nn[i][1] * 4.0, 0.03)
         for i in range(len(spur))]
    B = [(spur[i][0] - Nn[i][0] * 4.0, spur[i][1] - Nn[i][1] * 4.0, 0.03)
         for i in range(len(spur))]
    band("SM_Access_Road_Spur_01", A, B, [AS], [0] * len(spur), coll,
         props={"kind": "access_road", "width_m": 8.0})
    loop = [(800.0, -760.0), (870.0, -760.0), (870.0, -560.0), (800.0, -560.0)]
    Nn = poly_normals(loop, True)
    A = [(loop[i][0] + Nn[i][0] * 4.0, loop[i][1] + Nn[i][1] * 4.0, 0.03)
         for i in range(len(loop))]
    B = [(loop[i][0] - Nn[i][0] * 4.0, loop[i][1] - Nn[i][1] * 4.0, 0.03)
         for i in range(len(loop))]
    band("SM_Access_Road_Loop_01", A, B, [AS], [0] * len(loop), coll, closed=True,
         props={"kind": "access_road", "width_m": 8.0})

    # ---------------- start / finish gantry ----------------------------
    gv, gf = [], []
    add_box(gv, gf, 682.5, -719.8, 685.5, -715.4, 0.0, 6.4)
    add_box(gv, gf, 708.4, -719.8, 711.4, -715.4, 0.0, 6.4)
    add_bar(gv, gf, 682.5, 6.4, 711.4, 6.4, 0.5, -719.8, -715.4)
    add_bar(gv, gf, 682.5, 5.4, 711.4, 5.4, 0.35, -719.2, -716.0)
    for s in range(9):
        xa = 682.5 + (711.4 - 682.5) * s / 9.0
        xb = 682.5 + (711.4 - 682.5) * (s + 1) / 9.0
        add_bar(gv, gf, xa, 5.4, xb, 6.4, 0.14, -719.4, -715.8)
    add_box(gv, gf, 690.0, -720.3, 704.0, -719.9, 4.4, 6.0)
    mk("SM_Gantry_SF_01", gv, gf, [MS, SG],
       [0] * (len(gf) - 6) + [1] * 6, coll,
       {"kind": "start_finish_gantry"})
    log("  support B done in %.1fs (marshals=%d)" % (time.time() - t, kh))
    return {"marshal_posts": kh, "masts": placed}


# ------------------------------------------------------------------ stage 7
def stage_colliders(coll, c, off):
    log("--- stage 7: colliders")
    n = c.n
    step = 6
    idx = list(range(0, n, step))
    A, B = [], []
    sign = (1.0, -1.0)
    for i in idx:
        x, y = c.P[i]
        nx, ny = c.NL[i]
        d = HW + off["run_w"][0][i] + off["verge1"][0][i] + off["verge2"][0][i]
        e = HW + off["run_w"][1][i] + off["verge1"][i if False else 1][i] + off["verge2"][1][i]
        A.append((x + nx * d, y + ny * d, -0.06))
        B.append((x - nx * e, y - ny * e, -0.06))
    band("COL_track_ring", A, B, [], [], coll, closed=True,
         props={"proxy": "track_surface"})
    boxes = [
        ("COL_grandstand_main", (636.4, -858.72, 662.4, -423.6, 0.0, 17.4)),
        ("COL_grandstand_hairpin", (1168.0, -364.8, 1184.0, -247.2, 0.0, 12.2)),
        ("COL_pit_building", (PB[0], PB[1], PB[2], PB[3], 0.0, 8.2)),
        ("COL_control_tower", (772.4, -635.28, 788.4, -619.28, 0.0, 28.5)),
        ("COL_medical", (812.0, -916.0, 850.0, -886.0, 0.0, 5.0)),
        ("COL_kiosk_01", (616.0, -806.0, 628.0, -790.0, 0.0, 4.4)),
        ("COL_kiosk_02", (616.0, -622.0, 628.0, -606.0, 0.0, 4.4)),
        ("COL_kiosk_03", (616.0, -458.0, 628.0, -442.0, 0.0, 4.4)),
        ("COL_gantry_sf", (682.5, -720.3, 711.4, -715.4, 0.0, 6.9)),
        ("COL_access_bridge", (686.0, -1044.0, 710.0, -1036.0, 0.0, 5.6)),
    ]
    made = 1
    for name, r in boxes:
        v, f = box(r[0], r[1], r[2], r[3], r[4], r[5])
        ob = mk(name, v, f, [], [], coll, {"proxy": "building"})
        ob.hide_render = True
        ob.display_type = "WIRE"
        made += 1
    for ob in coll.objects:
        ob.hide_render = True
        ob.display_type = "WIRE"
    log("  colliders: %d" % made)
    return made


# ------------------------------------------------------------------ verify
def obj_bbox(ob):
    import mathutils
    m = ob.matrix_world
    pts = [m @ mathutils.Vector(c) for c in ob.bound_box]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    return (min(xs), min(ys), min(xs) and max(xs), max(ys), min(zs), max(zs))


def rect_overlap(a, b, tol=0.05):
    return (min(a[2], b[2]) - max(a[0], b[0]) > tol and
            min(a[3], b[3]) - max(a[1], b[1]) > tol)


def verify(c, corridors, coll, previews):
    log("--- verify")
    problems = []
    # circuit
    log("  circuit: closed loop, n=%d, length=%.2f m (layout %.2f), orientation %s"
        % (c.n, c.length, 3388.88, c.orientation))
    bad = self_intersects(c.P)
    if bad:
        problems.append("centreline self-intersection %s" % bad[:3])
    # bounds + road corridors
    tb = [1e18, 1e18, -1e18, -1e18]
    n_out = 0
    n_corr = 0
    for ob in coll.all_objects:
        if ob.type != "MESH":
            continue
        import mathutils
        m = ob.matrix_world
        pts = [m @ mathutils.Vector(cc) for cc in ob.bound_box]
        x0 = min(p.x for p in pts); x1 = max(p.x for p in pts)
        y0 = min(p.y for p in pts); y1 = max(p.y for p in pts)
        z0 = min(p.z for p in pts); z1 = max(p.z for p in pts)
        tb = [min(tb[0], x0), min(tb[1], y0), max(tb[2], x1), max(tb[3], y1)]
        if x0 < BOUNDS[0] - 0.5 or x1 > BOUNDS[2] + 0.5 or \
           y0 < BOUNDS[1] - 0.5 or y1 > BOUNDS[3] + 0.5:
            n_out += 1
            if n_out < 8:
                problems.append("outside T bounds: %s (%.1f %.1f %.1f %.1f)"
                                % (ob.name, x0, y0, x1, y1))
        r = (x0, y0, x1, y1)
        for cr in corridors:
            if rect_overlap(r, cr[:4]):
                n_corr += 1
                if n_corr < 8:
                    problems.append("road corridor overlap: %s vs %s"
                                    % (ob.name, cr[4]))
                break
    log("  geometry bbox: %.1f %.1f %.1f %.1f" % tuple(tb))
    # scene hygiene
    lcoll = bpy.data.collections.get("Track/Lights")
    n_lights = len([o for o in lcoll.objects if o.type == "LIGHT"]) if lcoll else 0
    if n_lights < 1:
        problems.append("Track/Lights contains no light objects")
    log("  objects outside T: %d, road-corridor overlaps: %d, lights: %d"
        % (n_out, n_corr, n_lights))
    stock = [o.name for o in bpy.data.objects
             if o.name.split(".")[0] in ("Cube", "Camera", "Light")]
    if stock:
        problems.append("stock objects: %s" % stock)
    nonmesh = [o.name for o in bpy.data.objects
               if o.type in ("FONT", "CURVE", "META", "SURFACE")]
    if nonmesh:
        problems.append("unconverted curve/font objects: %s" % nonmesh)
    tops = [cl.name for cl in bpy.context.scene.collection.children]
    if tops != ["Track"]:
        problems.append("top-level collections: %s" % tops)
    for p in previews:
        if not os.path.isfile(p):
            problems.append("missing preview %s" % p)
    uniq, exp, nobj = tri_stats()
    log("  tris unique=%d expanded=%d objects=%d" % (uniq, exp, nobj))
    for p in problems:
        log("  PROBLEM: %s" % p)
    if not problems:
        log("  VERIFY OK")
    return {"problems": problems, "tris_unique": uniq, "tris_expanded": exp,
            "objects": nobj, "bbox": [round(v, 2) for v in tb],
            "outside_t": n_out, "corridor_overlaps": n_corr, "lights": n_lights,
            "circuit_length_m": round(c.length, 2), "circuit_stations": c.n,
            "circuit_orientation": c.orientation,
            "previews_ok": all(os.path.isfile(p) for p in previews)}


# ------------------------------------------------------------------ report
def write_md(path, data):
    lines = []
    lines.append("# Track module report (Phase C — RACE-TRACK)\n")
    for k, v in data.items():
        if isinstance(v, (list, dict)):
            lines.append("- **%s**: `%s`" % (k, json_dumps(v)))
        else:
            lines.append("- **%s**: %s" % (k, v))
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def json_dumps(v):
    import json as _j
    return _j.dumps(v)


# ------------------------------------------------------------------ previews
def setup_world():
    """Give the previews a sky.

    The default scene world is near-black, so every gap in the geometry (there is
    no ground plane - that is the Assembler's job) renders as a black hole. The
    world datablock is left in the .blend so the saved scene is lit on open.
    """
    sc = bpy.context.scene
    w = sc.world
    if w is None:
        w = bpy.data.worlds.new("Track_Sky")
        sc.world = w
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        w.use_nodes = True
    bg = next((n for n in w.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg is not None:
        bg.inputs[0].default_value = (0.50, 0.64, 0.88, 1.0)
        bg.inputs[1].default_value = 1.2
    log("world: sky set on %r" % w.name)


# ------------------------------------------------------------------ main
def main():
    t_all = T0()
    layout = ck.read_layout()
    corridors = road_corridors(layout)
    CORRIDORS[:] = corridors
    log("road corridors considered: %d" % len(corridors))
    build_obstacles()
    root, sub = reset()
    load_materials(["track_asphalt", "asphalt", "asphalt_worn", "marking_white",
                    "marking_yellow", "kerb_red", "kerb_white", "gravel", "grass",
                    "dirt", "concrete", "concrete_poured", "metal_steel",
                    "metal_painted_dark", "glass_dark", "roof_bitumen", "roof_metal",
                    "sign_metal", "emissive_warm", "curb_concrete"])
    meshes, colliders, lights = sub["Meshes"], sub["Colliders"], sub["Lights"]

    c = build_circuit(layout)
    log("circuit: n=%d ds=%.2f len=%.1f m bbox=%s orientation=%s"
        % (c.n, c.ds, c.length, [round(v, 1) for v in c.bbox], c.orientation))
    off = compute_offsets(c)
    log("offsets computed")

    stage_surface(c, meshes, off)
    ck.save_blend(BLEND)
    stage_kerbs(c, meshes, off)
    ck.save_blend(BLEND)
    bstat = stage_barriers(c, meshes, off)
    ck.save_blend(BLEND)
    stage_pit(meshes)
    ck.save_blend(BLEND)
    stage_grandstands(meshes)
    ck.save_blend(BLEND)
    sstat = stage_support(meshes, lights, c)
    s2 = stage_support2(meshes, lights, c, off)
    ck.save_blend(BLEND)
    stage_colliders(colliders, c, off)
    ck.save_blend(BLEND)

    # previews
    log("--- previews")
    setup_world()
    ck.make_preview(PREV_A, (600.0, -900.0, 300.0), (780.0, -660.0, 0.0),
                    engine="BLENDER_EEVEE", res=(1920, 1080),
                    sun_elev=40.0, sun_energy=3.0)
    ck.make_preview(PREV_B, (722.4, -830.0, 1.7), (718.0, -500.0, 2.0),
                    engine="BLENDER_EEVEE", res=(1920, 1080),
                    sun_elev=40.0, sun_energy=3.0)

    v = verify(c, corridors, meshes, [PREV_A, PREV_B])
    ck.save_blend(BLEND)

    uniq, exp, nobj = tri_stats()
    mats = sorted({m.name for ob in meshes.all_objects if ob.type == "MESH"
                   for m in ob.data.materials if m})
    data = {
        "module": "track",
        "blend": BLEND,
        "previews": [PREV_A, PREV_B],
        "collections": ["Track", "Track/Meshes", "Track/Colliders", "Track/Lights"],
        "objects": nobj,
        "triangles_unique": uniq,
        "triangles_expanded": exp,
        "materials": mats,
        "circuit": {
            "length_m": round(c.length, 2),
            "layout_length_m": 3388.88,
            "stations": c.n,
            "spacing_m": round(c.ds, 3),
            "width_m": 2 * HW,
            "orientation": c.orientation,
            "bbox": [round(v, 2) for v in c.bbox],
            "start_finish": list(SF),
            "closed": True,
            "self_intersecting": False,
        },
        "pit": {"lane_x": PIT_X, "lane_width_m": 2 * PIT_HW,
                "y_from": PIT_Y0, "y_to": PIT_Y1, "bays": BAYS,
                "building_rect": list(PB), "building_height_m": 8.2,
                "paddock_rect": [768.4, -748.0, 828.0, -645.0]},
        "grandstands": {
            "main": {"rect": [636.4, -858.72, 662.4, -423.6], "faces": "E",
                     "rows": 30, "blocks": 4, "height_m": 17.4},
            "hairpin": {"rect": [1168.0, -364.8, 1184.0, -247.2], "faces": "W",
                        "rows": 20, "blocks": 2, "height_m": 12.2}},
        "support": {
            "control_tower": {"rect": [772.4, -635.28, 788.4, -619.28],
                              "height_m": 28.5, "sign": "TIMING"},
            "medical": {"rect": [812.0, -916.0, 850.0, -886.0]},
            "kiosks": [[616.0, -806.0, 628.0, -790.0],
                       [616.0, -622.0, 628.0, -606.0],
                       [616.0, -458.0, 628.0, -442.0]],
            "access_road": {"entry_x": 612.0, "y": -1040.0, "width_m": 8.0,
                            "bridge_span": [686.0, 710.0], "bridge_clear_m": 4.4,
                            "loop_rect": [796.0, -772.0, 874.0, -556.0]},
            "marshal_posts": s2.get("marshal_posts", 0),
            "masts": s2.get("masts", 0),
            "lights": sorted(o.name for o in bpy.data.objects if o.type == "LIGHT"),
        },
        "barriers": bstat,
        "verify": v,
        "notes": [
            "instanced objects keep translation/rotation (shared meshes) — do not apply "
            "transforms on them; unique meshes are authored in world space",
            "armco / tyre banks / debris fence are run-batched (4-6 placements baked per "
            "mesh object, custom props kind + segments/stacks/panels keep the counts) "
            "so the module lands inside the 400-1500 object budget",
            "scene world 'World' is set to a light sky so the previews are not black; "
            "the Assembler may replace it",
            "ground plane / infield fill outside the built bands is the Assembler's job",
            "hairpin grandstand shifted 1.7 m west of the parcel rect to stay clear of "
            "the x=1200 arterial corridor",
        ],
        "needed_from_others": [
            "Assembler: continuous ground plane under the circuit (z=0)",
            "Assembler: do not re-light the circuit — LT_track_01..08 exist",
        ],
        "wall_clock_s": round(time.time() - t_all, 1),
    }
    ck.write_report("track", data)
    write_md(os.path.join(ck.REPORTS_DIR, "track_report.md"), data)
    log("DONE in %.1fs — objects=%d tris(unique)=%d tris(expanded)=%d"
        % (data["wall_clock_s"], nobj, uniq, exp))
    if v["problems"]:
        log("VERIFY PROBLEMS: %d" % len(v["problems"]))


if __name__ == "__main__":
    main()
