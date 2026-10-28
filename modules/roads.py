#!/usr/bin/env python3
"""roads.py — FULL ground road network (454 edges) for the 3x3 km city.

Extends the Phase-B pilot (out/roads.blend, 149 edges, 534 objects, 12 208 tris)
to every edge of layout.json:

  arterial           134 edges  40.2 km  width 24  (2x2 lanes, 3 m median, 2x2.5 sidewalks)
  street             148 edges  22.2 km  width 12  (1 lane each way, 2x2.5 sidewalks)
  alley              144 edges  10.8 km  width  5  (cobble, clipped 12 m off arterials)
  highway             16 edges  11.2 km  ground band only: service road + verges
  interchange_ramp    12 edges   2.4 km  elevated — DECK belongs to the Flyover module

The elevated ring deck is NOT built here (Flyover owns H_07/H_08 + ramp X_N_600);
this module builds the ground service road under every ring segment plus the
ground-level tie-ins where the 12 ramps reach the ground.

Run headless:
    cd /home/abdulhadi/Work/city && blender -b -P modules/roads.py

Pilot contract preserved (see reports/roads_report.md -> PILOT PARITY):
  carriageway top z=0, kerb/sidewalk/median top z=0.15, markings z=0.005,
  crosswalks z=0.007, arterial envelope halfwidth 12.0 (carriageway 9.5 +
  sidewalk 2.5), median 3.0 wide raised 0.15, alley halfwidth 2.5 cobble,
  street envelope halfwidth 6.0 (carriageway 3.5 + sidewalk 2.5).
"""
import sys, os, math, json, time

ROOT = "/home/abdulhadi/Work/city"
sys.path.insert(0, os.path.join(ROOT, "modules"))

import bpy
import citykit as ck
from mathutils import Vector

# --------------------------------------------------------------------------
# constants
# --------------------------------------------------------------------------
KERB_H = 0.15
Z_MARK = 0.005
Z_CROSS = 0.007
SW = 2.5
ART_HW = 12.0
ART_CAR = 9.5
MEDIAN_HW = 1.5
ST_HW = 6.0
ST_CAR = 3.5
ALLEY_HW = 2.5
HW_ASP = 5.0
HW_GRAVEL = 14.0
HW_DIRT = 20.0
Z_VERGE = -0.05
SPUR_W = 8.0

ENV = {"arterial": ART_HW, "street": ST_HW, "alley": ALLEY_HW,
       "highway": HW_DIRT, "interchange_ramp": 9.0}
CAR = {"arterial": ART_CAR, "street": ST_CAR, "alley": ALLEY_HW,
       "highway": HW_ASP, "interchange_ramp": 9.0}
PRIO = {"alley": 0, "street": 1, "arterial": 2, "highway": 3,
        "interchange_ramp": 4}
GROUND = ("arterial", "street", "alley")
H_TAG = {"arterial": "Arterial", "street": "Street", "alley": "Alley"}
# cross-section object kinds compared by the pilot parity check (spurs,
# crosswalks, ring bands, details live in the same collection but are not
# part of any single edge's cross-section)
CROSS_KINDS = {"RoadSurface", "Median", "Sidewalk", "KerbRamp", "RoadMarking"}

LAKE_BBOX = (-552.58, -1142.57, -335.1, -969.78)
CIRCUIT_ZONE = (612.0, -1188.0, 1188.0, -12.0)
TRACK_SURF_HW = 8.2

MATS = {}
STATS = {"edges_built": {}, "zebras": 0, "spurs": 0, "spurs_skipped": [],
         "spurs_infield": [], "ramp_connectors": 0, "junctions": {},
         "curb_returns": 0, "details": 0, "colliders": 0, "stages": []}


def log(msg):
    print("[roads] %s" % msg, flush=True)


# --------------------------------------------------------------------------
# math helpers
# --------------------------------------------------------------------------
def sub_iv(unit, blocked):
    free = [list(unit)]
    for bs, be in sorted(blocked):
        nxt = []
        for fs, fe in free:
            if be <= fs + 1e-9 or bs >= fe - 1e-9:
                nxt.append([fs, fe])
                continue
            if bs > fs + 1e-9:
                nxt.append([fs, bs])
            if be < fe - 1e-9:
                nxt.append([be, fe])
        free = nxt
    return [f for f in free if f[1] - f[0] > 1e-4]


def lerp2(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def dist2(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])


def clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def rect_overlap(r1, r2):
    x0, y0 = max(r1[0], r2[0]), max(r1[1], r2[1])
    x1, y1 = min(r1[2], r2[2]), min(r1[3], r2[3])
    if x1 - x0 > 1e-9 and y1 - y0 > 1e-9:
        return (x0, y0, x1, y1)
    return None


def rect_gap(r1, r2):
    dx = max(r1[0] - r2[2], r2[0] - r1[2], 0.0)
    dy = max(r1[1] - r2[3], r2[1] - r1[3], 0.0)
    return math.hypot(dx, dy)


def liang_barsky(a, b, rx0, ry0, rx1, ry1):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - rx0), (dx, rx1 - a[0]),
                 (-dy, a[1] - ry0), (dy, ry1 - a[1])):
        if abs(p) < 1e-12:
            if q < 0:
                return None
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return None
            if r > t0:
                t0 = r
        else:
            if r < t0:
                return None
            if r < t1:
                t1 = r
    return (t0, t1) if t1 - t0 > 1e-9 else None


def seg_rect_dist(a, b, r, step=2.0):
    n = max(2, int(dist2(a, b) / step))
    best = 1e18
    for k in range(n + 1):
        t = k / float(n)
        x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        ex = max(r[0] - x, x - r[2], 0.0)
        ey = max(r[1] - y, y - r[3], 0.0)
        best = min(best, math.hypot(ex, ey))
    return best


# --------------------------------------------------------------------------
# mesh helpers
# --------------------------------------------------------------------------
def make_obj(name, verts, faces, mats, face_mats, coll, props=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], [tuple(f) for f in faces])
    me.update()
    for m in mats:
        me.materials.append(m)
    if face_mats:
        for i, p in enumerate(me.polygons):
            p.material_index = face_mats[i] if i < len(face_mats) else 0
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    ob["module"] = "roads"
    if props:
        for k, v in props.items():
            ob[k] = v
    return ob


def strip_faces(p0, p1, hw, z=0.0):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dy)
    if L < 1e-9:
        return [], []
    nx, ny = -dy / L * hw, dx / L * hw
    return ([(p0[0] + nx, p0[1] + ny, z), (p1[0] + nx, p1[1] + ny, z),
             (p1[0] - nx, p1[1] - ny, z), (p0[0] - nx, p0[1] - ny, z)]), [0, 1, 2, 3]


def quad_xy(x0, y0, x1, y1, z=0.0):
    return [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)]


def box_geom(x0, y0, x1, y1, z0, z1):
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
         (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return v, f


# --------------------------------------------------------------------------
# scene / collections / materials
# --------------------------------------------------------------------------
def reset_collections():
    # headless startup file: drop the stock cube so out/roads.blend contains
    # only this module (a live master scene is untouched - the cube is matched
    # by name, mesh, vertex count and collection)
    cube = bpy.data.objects.get("Cube")
    if cube is not None and cube.type == "MESH" and \
            cube.data is not None and cube.data.name == "Cube" and \
            len(cube.data.vertices) == 8 and \
            tuple(round(v, 6) for v in cube.location) == (0.0, 0.0, 0.0) and \
            any(c.name == "Collection" for c in cube.users_collection):
        try:
            bpy.data.objects.remove(cube, do_unlink=True)
        except Exception:
            pass
    old = bpy.data.collections.get("Roads")
    if old is not None:
        for ob in list(old.all_objects):
            try:
                bpy.data.objects.remove(ob, do_unlink=True)
            except Exception:
                pass
        try:
            bpy.data.collections.remove(old)
        except Exception:
            pass
    for me in [m for m in bpy.data.meshes if m.users == 0]:
        try:
            bpy.data.meshes.remove(me)
        except Exception:
            pass
    root = ck.ensure_collection("Roads")
    sub = {}
    for c in ("Meshes", "Colliders", "Lights"):
        sub[c] = ck.ensure_collection("Roads/%s" % c, parent=root)
    log("collections ready: Roads/{Meshes,Colliders,Lights}")
    return root, sub


def load_materials():
    for n in ("asphalt", "asphalt_worn", "asphalt_highway", "cobble_stone",
              "marking_white", "marking_yellow", "curb_concrete",
              "sidewalk_concrete", "gravel", "dirt", "metal_steel", "rust"):
        MATS[n] = ck.append_material(n)
    log("materials loaded: %s" % ", ".join(sorted(MATS)))


# --------------------------------------------------------------------------
# road edge model
# --------------------------------------------------------------------------
class Road(object):
    def __init__(self, e, nodes):
        self.e = e
        self.id = e["id"]
        self.hier = e["hierarchy"]
        a = nodes[e["a"]][:2]
        b = nodes[e["b"]][:2]
        self.a, self.b = a, b
        if abs(a[1] - b[1]) < 1e-6:
            self.axis = "H"
            self.c0, self.c1 = sorted((a[0], b[0]))
            self.center = a[1]
        else:
            assert abs(a[0] - b[0]) < 1e-6, "edge %s is not axis aligned" % self.id
            self.axis = "V"
            self.c0, self.c1 = sorted((a[1], b[1]))
            self.center = a[0]
        self.env = ENV[self.hier]
        self.car = CAR[self.hier]
        self.prio = PRIO[self.hier]
        self.length = e.get("length", self.c1 - self.c0)
        self.stops = [0.0, 0.0]
        self.sstops = [0.0, 0.0]

    def pt(self, along, lat=0.0, z=0.0):
        if self.axis == "H":
            return (along, self.center + lat, z)
        return (self.center + lat, along, z)

    def lat_of(self, p):
        return (p[1] - self.center) if self.axis == "H" else (p[0] - self.center)

    def along_of(self, p):
        return p[0] if self.axis == "H" else p[1]

    def env_rect(self):
        if self.axis == "H":
            return (self.c0, self.center - self.env, self.c1, self.center + self.env)
        return (self.center - self.env, self.c0, self.center + self.env, self.c1)

    def strip_rect(self, side, a0=None, a1=None):
        a0 = self.c0 if a0 is None else a0
        a1 = self.c1 if a1 is None else a1
        lo, hi = sorted((self.center + side * self.car, self.center + side * self.env))
        if self.axis == "H":
            return (a0, lo, a1, hi)
        return (lo, a0, hi, a1)

    def clipped(self):
        return (self.c0 + self.stops[0], self.c1 - self.stops[1])

    def sidewalk_span(self):
        return (self.c0 + self.sstops[0], self.c1 - self.sstops[1])


def build_index(roads):
    idx = {"H": {}, "V": {}}
    for r in roads:
        idx[r.axis].setdefault(round(r.center, 4), []).append(r)
    return idx


def perp_through(p, axis, idx, tol=1e-6):
    other = "V" if axis == "H" else "H"
    key = round(p[0] if other == "V" else p[1], 4)
    out = []
    for r in idx[other].get(key, []):
        v = p[1] if other == "V" else p[0]
        if r.c0 - tol <= v <= r.c1 + tol:
            out.append(r)
    return out


def compute_stops(roads, idx, ctx):
    """Stop distances at both ends + sidewalk mouth openings."""
    for r in roads:
        for end in (0, 1):
            p = r.a if end == 0 else r.b
            for f in perp_through(p, r.axis, idx):
                if f is r:
                    continue
                if f.prio > r.prio:
                    if r.hier == "alley":
                        car_stop, side_stop = f.env, f.env
                    else:
                        car_stop, side_stop = f.car, f.car
                    r.stops[end] = max(r.stops[end], car_stop)
                    r.sstops[end] = max(r.sstops[end], side_stop)
                    far = r.b if end == 0 else r.a
                    side = 1 if f.lat_of(far) > 0 else -1
                    along = f.along_of(p)
                    if r.hier == "alley":
                        w, kind = 2 * ALLEY_HW + 0.5, "alley"
                    else:
                        w, kind = 2 * r.env, "street"
                    ctx["gaps"].setdefault((f.id, side), []).append(
                        (along - w / 2.0, along + w / 2.0))
                    if kind != "street":
                        ctx["ramps"].setdefault((f.id, side), []).append(
                            (along - w / 2.0, along + w / 2.0, kind))
                elif f.prio == r.prio:
                    r.stops[end] = max(r.stops[end], f.car)
                    r.sstops[end] = max(r.sstops[end], f.env)
        lim = 0.45 * max(r.c1 - r.c0, 1.0)
        r.stops = [min(r.stops[0], lim), min(r.stops[1], lim)]
        r.sstops = [min(r.sstops[0], lim), min(r.sstops[1], lim)]


# --------------------------------------------------------------------------
# access spurs
# --------------------------------------------------------------------------
def track_polyline():
    t = ck.read_layout().get("track") or {}
    return [tuple(p[:2]) for p in (t.get("centerline_sample") or [])]


def pt_seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = clamp(((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2, 0.0, 1.0)
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def seg_seg_dist(a, b, c, d):
    """2D segment-to-segment distance (0 when they cross)."""
    def cr(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
    d1, d2 = cr(c, d, a), cr(c, d, b)
    d3, d4 = cr(a, b, c), cr(a, b, d)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return 0.0
    return min(pt_seg_dist(a, c, d), pt_seg_dist(b, c, d),
               pt_seg_dist(c, a, b), pt_seg_dist(d, a, b))


def seg_track_min(a, b, track):
    """True distance to the racing surface centreline (segment-accurate, not
    sample-accurate: the sparse sample list must not hide a crossing)."""
    if len(track) < 2:
        return 1e18
    best = 1e18
    for k in range(len(track)):
        c, d = track[k], track[(k + 1) % len(track)]
        best = min(best, seg_seg_dist(a, b, c, d))
        if best <= 0.0:
            break
    return best


def compute_spurs(roads, ctx, ring=()):
    """8 m asphalt spur per facility rect that touches no road envelope.

    Axis-aligned, perpendicular to the road, flush with the facility rect edge
    (never inside the rect). Avoids LAKE_1, the circuit corridor and the racing
    surface (infield facilities are served by the Track module's bridge access).
    Facilities in the corner belts (outside the square ring, diagonally) only
    have the ground service-road band nearby, so the ring is a fallback
    candidate and the spur attaches at the 10 m asphalt edge instead of the
    20 m dirt edge.
    """
    try:
        prog = json.load(open(os.path.join(ck.REPORTS_DIR, "program.json")))
    except Exception as e:
        log("WARNING: program.json unreadable (%s) - no spurs" % e)
        STATS["spurs_skipped"] = ["program.json missing"]
        return []
    fac = [f for f in prog.get("facilities", [])
           if (f.get("placement") or {}).get("rect")]
    track = track_polyline()
    roads_g = list(roads)
    roads_ring = list(ring)
    spurs = []
    skipped = []

    def candidates(rect, cx, cy, pool):
        out = []
        order = sorted(pool, key=lambda r: rect_gap(rect, r.env_rect()))[:10]
        for r in order:
            off = r.car if r.hier == "highway" else r.env
            if r.axis == "H":
                side = 1 if cy > r.center else -1
                att_y = r.center + side * off
                near = rect[1] if side > 0 else rect[3]
                if (near - att_y) * side <= 1.0:
                    continue
                lo, hi = r.c0, r.c1
                if rect[2] - rect[0] > SPUR_W + 0.1:
                    lo = max(lo, rect[0] + SPUR_W / 2.0)
                    hi = min(hi, rect[2] - SPUR_W / 2.0)
                x = clamp(cx, lo, hi)
                if hi < lo:
                    continue
                att, end = (x, att_y), (x, near)
            else:
                side = 1 if cx > r.center else -1
                att_x = r.center + side * off
                near = rect[0] if side > 0 else rect[2]
                if (near - att_x) * side <= 1.0:
                    continue
                lo, hi = r.c0, r.c1
                if rect[3] - rect[1] > SPUR_W + 0.1:
                    lo = max(lo, rect[1] + SPUR_W / 2.0)
                    hi = min(hi, rect[3] - SPUR_W / 2.0)
                if hi < lo:
                    continue
                y = clamp(cy, lo, hi)
                att, end = (att_x, y), (near, y)
            d = dist2(att, end)
            if d < 1.0 or d > 400.0:
                continue
            # never touch the circuit corridor or the racing surface: the Track
            # module owns the gated access road + bridge at (612, -1040)
            if seg_rect_dist(att, end, CIRCUIT_ZONE, step=1.0) < 0.01:
                continue
            if seg_track_min(att, end, track) < \
                    TRACK_SURF_HW + SPUR_W / 2.0 + 0.5:
                continue
            if seg_rect_dist(att, end, LAKE_BBOX, step=1.0) < 1.0:
                continue
            out.append((d, r, att, end, side))
        return out

    for f in fac:
        rect = [float(v) for v in f["placement"]["rect"]]
        cx, cy = (rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0
        if any(rect_overlap(rect, r.env_rect()) for r in roads_g):
            continue
        if min(rect_gap(rect, r.env_rect()) for r in roads_g) < 1e-6:
            continue
        if rect_overlap(rect, CIRCUIT_ZONE) or \
                rect_gap(rect, CIRCUIT_ZONE) < 1e-6:
            STATS["spurs_infield"].append(f["id"])
            continue
        cands = candidates(rect, cx, cy, roads_g)
        if not cands:
            cands = candidates(rect, cx, cy, roads_ring)
        if not cands:
            skipped.append(f["id"])
            continue
        cands.sort(key=lambda c: c[0])
        d, r, att, end, side = cands[0]
        spurs.append({"facility": f["id"], "edge": r.id, "hier": r.hier,
                      "axis": r.axis, "side": side, "att": att, "end": end,
                      "length": d, "district": f.get("district")})
        if r.hier in ("arterial", "street"):
            along = r.along_of(att)
            w = SPUR_W + 0.5
            ctx["gaps"].setdefault((r.id, side), []).append(
                (along - w / 2.0, along + w / 2.0))
            ctx["ramps"].setdefault((r.id, side), []).append(
                (along - w / 2.0, along + w / 2.0, "spur"))
    STATS["spurs"] = len(spurs)
    STATS["spurs_skipped"] = skipped
    log("  access spurs: %d routed, %d in circuit zone (Track access), "
        "%d skipped (of %d facilities with a rect)"
        % (len(spurs), len(STATS["spurs_infield"]), len(skipped), len(fac)))
    for sid in skipped:
        log("    SKIP (no clear route): %s" % sid)
    return spurs


# --------------------------------------------------------------------------
# zebra crosswalks
# --------------------------------------------------------------------------
def compute_zebras(roads, nodes, layout, ctx):
    inc = {}
    for r in roads:
        inc.setdefault(r.e["a"], []).append(r)
        inc.setdefault(r.e["b"], []).append(r)
    verts, faces = [], []
    n = 0
    tl_nodes = []
    for tl in layout.get("traffic_lights", []):
        nid = tl.get("node")
        if nid in nodes and nid not in tl_nodes:
            tl_nodes.append(nid)
    per_node = {}
    for nid in tl_nodes:
        p = nodes[nid][:2]
        cand = list(inc.get(nid, []))
        for r in roads:
            if r in cand:
                continue
            if r.axis == "H" and abs(p[1] - r.center) < 1e-6 and \
                    r.c0 - 1e-6 <= p[0] <= r.c1 + 1e-6:
                cand.append(r)
            elif r.axis == "V" and abs(p[0] - r.center) < 1e-6 and \
                    r.c0 - 1e-6 <= p[1] <= r.c1 + 1e-6:
                cand.append(r)
        cnt = 0
        for e in cand:
            perp = [f for f in cand if f.axis != e.axis]
            ext = max([e.car] + [f.env for f in perp])
            na = e.along_of(p)
            a0, a1 = e.clipped()
            for sgn in (-1, 1):
                if ((e.c1 - na) if sgn > 0 else (na - e.c0)) < 9.0:
                    continue
                start = na + sgn * (ext + 0.5)
                hi_, lo_ = sorted((start, start + sgn * 4.0))
                if lo_ < a0 - 0.01 or hi_ > a1 + 0.01:
                    continue
                for k in range(5):
                    s0 = lo_ + 0.1 + k * 0.8
                    s1 = s0 + 0.4
                    if e.axis == "H":
                        f = quad_xy(s0, e.center - e.car, s1,
                                    e.center + e.car, Z_CROSS)
                    else:
                        f = quad_xy(e.center - e.car, s0, e.center + e.car,
                                    s1, Z_CROSS)
                    b = len(verts)
                    verts.extend(f)
                    faces.append((b, b + 1, b + 2, b + 3))
                cnt += 1
                n += 1
                gc = 0.5 * (lo_ + hi_)
                for side in (-1, 1):
                    ctx["gaps"].setdefault((e.id, side), []).append(
                        (gc - 0.9, gc + 0.9))
                    ctx["ramps"].setdefault((e.id, side), []).append(
                        (gc - 0.9, gc + 0.9, "zebra"))
        per_node[nid] = cnt
    objs = []
    if faces:
        objs.append(make_obj("SM_Crosswalk_01", verts, faces,
                             [MATS["marking_white"]], None, ctx["Meshes"],
                             {"kind": "zebra_crosswalk", "count": n,
                              "lights": len(tl_nodes)}))
    STATS["zebra_nodes"] = per_node
    STATS["zebras"] = n
    log("  zebra crosswalks: %d legs at %d traffic lights" % (n, len(tl_nodes)))
    return objs


# --------------------------------------------------------------------------
# ramp connectors
# --------------------------------------------------------------------------
def compute_ramp_connectors(roads, nodes, layout, ctx):
    ramps = [e for e in layout["road_edges"]
             if e["hierarchy"] == "interchange_ramp"]
    out = []
    for e in ramps:
        A = nodes[e["a"]][:2]
        B = nodes[e["b"]][:2]
        axis = "H" if abs(A[1] - B[1]) < 1e-6 else "V"
        q = {"id": e["id"], "axis": axis, "a": A, "b": B,
             "flyover": e["id"] == "X_N_600"}
        if axis == "H":
            inboard = -1.0 if A[0] > B[0] else 1.0
            x0, x1 = sorted((A[0] + inboard * HW_ASP, A[0] + inboard * 13.0))
            q["ring_apron"] = (x0, A[1] - 15.0, x1, A[1] + 15.0)
            foot_dir = -1.0 if A[0] > B[0] else 1.0
            fx = B[0] + foot_dir * ART_HW
            q["foot_pad"] = (min(fx, fx + foot_dir * 30.0), B[1] - 9.0,
                             max(fx, fx + foot_dir * 30.0), B[1] + 9.0)
        else:
            inboard = -1.0 if A[1] > B[1] else 1.0
            y0, y1 = sorted((A[1] + inboard * HW_ASP, A[1] + inboard * 13.0))
            q["ring_apron"] = (A[0] - 15.0, y0, A[0] + 15.0, y1)
            foot_dir = -1.0 if A[1] > B[1] else 1.0
            fy = B[1] + foot_dir * ART_HW
            q["foot_pad"] = (B[0] - 9.0, min(fy, fy + foot_dir * 30.0),
                             B[0] + 9.0, max(fy, fy + foot_dir * 30.0))
        # the ramp foot lands on a grid arterial: open its sidewalk over 18 m
        if e["id"] != "X_N_600":
            for r in roads:
                if r.hier != "arterial":
                    continue
                if axis == "H" and r.axis == "V" and abs(B[0] - r.center) < 1e-6 \
                        and r.c0 - 1e-6 <= B[1] <= r.c1 + 1e-6:
                    side = 1 if foot_dir > 0 else -1
                    a = r.along_of(B)
                    ctx["gaps"].setdefault((r.id, side), []).append((a - 9.0, a + 9.0))
                    ctx["ramps"].setdefault((r.id, side), []).append(
                        (a - 9.0, a + 9.0, "spur"))
                    q["foot_edge"] = r.id
                elif axis == "V" and r.axis == "H" and abs(B[1] - r.center) < 1e-6 \
                        and r.c0 - 1e-6 <= B[0] <= r.c1 + 1e-6:
                    side = 1 if foot_dir > 0 else -1
                    a = r.along_of(B)
                    ctx["gaps"].setdefault((r.id, side), []).append((a - 9.0, a + 9.0))
                    ctx["ramps"].setdefault((r.id, side), []).append(
                        (a - 9.0, a + 9.0, "spur"))
                    q["foot_edge"] = r.id
        out.append(q)
    STATS["ramp_connectors"] = len(out)
    log("  ramp connectors: %d ring aprons + %d foot pads (X_N_600 foot = Flyover)"
        % (len(out), sum(1 for q in out if not q["flyover"])))
    return out


# --------------------------------------------------------------------------
# carriageway / median / sidewalk / markings
# --------------------------------------------------------------------------
def build_carriageway(r, ctx, idx):
    a0, a1 = r.clipped()
    if a1 - a0 < 1.0:
        return None
    verts, faces, fm = [], [], []
    n = max(1, int(math.ceil((a1 - a0) / 30.0)))
    for k in range(n):
        s = a0 + (a1 - a0) * k / n
        e = a0 + (a1 - a0) * (k + 1) / n
        v, f = strip_faces(r.pt(s), r.pt(e), r.car, 0.0)
        if not v:
            continue
        b = len(verts)
        verts.extend(v)
        faces.append((b, b + 1, b + 2, b + 3))
        fm.append(1 if (k % 5 == 3) else 0)
    if not faces:
        return None
    if r.hier == "alley":
        mats = [MATS["cobble_stone"], MATS["asphalt_worn"]]
    else:
        mats = [MATS["asphalt"], MATS["asphalt_worn"]]
    return make_obj("SM_RoadSurface_%s_%03d" % (H_TAG[r.hier], idx), verts, faces,
                    mats, fm, ctx["Meshes"],
                    {"edge_id": r.id, "hierarchy": r.hier,
                     "width": r.e.get("width", 2 * r.env), "halfwidth": r.car})


def build_median(r, ctx, idx):
    if r.hier != "arterial":
        return None
    a0, a1 = r.clipped()
    if a1 - a0 < 2.0:
        return None
    s, e = a0, a1
    if r.axis == "H":
        top = [(s, r.center - MEDIAN_HW, KERB_H), (e, r.center - MEDIAN_HW, KERB_H),
               (e, r.center + MEDIAN_HW, KERB_H), (s, r.center + MEDIAN_HW, KERB_H)]
        bot = [(s, r.center - MEDIAN_HW, 0.0), (e, r.center - MEDIAN_HW, 0.0),
               (e, r.center + MEDIAN_HW, 0.0), (s, r.center + MEDIAN_HW, 0.0)]
    else:
        top = [(r.center - MEDIAN_HW, s, KERB_H), (r.center - MEDIAN_HW, e, KERB_H),
               (r.center + MEDIAN_HW, e, KERB_H), (r.center + MEDIAN_HW, s, KERB_H)]
        bot = [(r.center - MEDIAN_HW, s, 0.0), (r.center - MEDIAN_HW, e, 0.0),
               (r.center + MEDIAN_HW, e, 0.0), (r.center + MEDIAN_HW, s, 0.0)]
    mv = top + bot
    T = [0, 1, 2, 3]
    B = [4, 5, 6, 7]
    mf = [tuple(T)]
    for i in range(4):
        j = (i + 1) % 4
        mf.append((T[i], T[j], B[j], B[i]))
    return make_obj("SM_Median_Arterial_%03d" % idx, mv, mf,
                    [MATS["curb_concrete"]], None, ctx["Meshes"],
                    {"edge_id": r.id, "median_width": 2 * MEDIAN_HW})


def build_sidewalk(r, side, ctx, idx):
    if r.hier not in ("arterial", "street"):
        return None, None
    a0, a1 = r.sidewalk_span()
    ivs = sub_iv([a0, a1], ctx["gaps"].get((r.id, side), []))
    if not ivs:
        return None, None
    outer = r.center + side * r.env
    inner = r.center + side * r.car
    verts, faces, fm = [], [], []
    for s, e in ivs:
        if e - s < 0.05:
            continue
        base = len(verts)
        if r.axis == "H":
            pts = [(s, outer, KERB_H), (e, outer, KERB_H),
                   (e, inner, KERB_H), (s, inner, KERB_H),
                   (s, outer, 0.0), (e, outer, 0.0),
                   (e, inner, 0.0), (s, inner, 0.0)]
        else:
            pts = [(outer, s, KERB_H), (outer, e, KERB_H),
                   (inner, e, KERB_H), (inner, s, KERB_H),
                   (outer, s, 0.0), (outer, e, 0.0),
                   (inner, e, 0.0), (inner, s, 0.0)]
        verts.extend(pts)
        T = [base + i for i in range(4)]
        B = [base + 4 + i for i in range(4)]
        faces.append(tuple(T)); fm.append(0)
        faces.append((T[0], T[1], B[1], B[0])); fm.append(1)
        faces.append((T[3], T[2], B[2], B[3])); fm.append(1)
        faces.append((T[0], T[3], B[3], B[0])); fm.append(1)
        faces.append((T[1], T[2], B[2], B[1])); fm.append(1)
    if not faces:
        return None, None
    tag = H_TAG[r.hier]
    suffix = "A" if side < 0 else "B"
    ob = make_obj("SM_Sidewalk_%s_%03d%s" % (tag, idx, suffix), verts, faces,
                  [MATS["sidewalk_concrete"], MATS["curb_concrete"]], fm,
                  ctx["Meshes"], {"edge_id": r.id, "side": side,
                                  "top_z": KERB_H, "width": SW})
    rv, rf = [], []
    for g0, g1, kind in ctx["ramps"].get((r.id, side), []):
        if kind == "street":
            continue
        if r.axis == "H":
            if kind == "zebra":
                pts = [(g0, outer, KERB_H), (g1, outer, KERB_H),
                       (g1, inner, 0.0), (g0, inner, 0.0)]
            else:
                pts = [(g0, outer, 0.0), (g1, outer, 0.0),
                       (g1, inner, KERB_H), (g0, inner, KERB_H)]
        else:
            if kind == "zebra":
                pts = [(outer, g0, KERB_H), (outer, g1, KERB_H),
                       (inner, g1, 0.0), (inner, g0, 0.0)]
            else:
                pts = [(outer, g0, 0.0), (outer, g1, 0.0),
                       (inner, g1, KERB_H), (inner, g0, KERB_H)]
        b = len(rv)
        rv.extend(pts)
        rf.append((b, b + 1, b + 2, b + 3))
    ramp = None
    if rf:
        ramp = make_obj("SM_KerbRamp_%s_%03d%s" % (tag, idx, suffix), rv, rf,
                        [MATS["sidewalk_concrete"]], None, ctx["Meshes"],
                        {"edge_id": r.id, "side": side, "kind": "kerb_ramp"})
    return ob, ramp


def build_markings(r, ctx, idx):
    if r.hier not in ("arterial", "street"):
        return None
    a0, a1 = r.clipped()
    if a1 - a0 < 2.0:
        return None
    mv, mf, mm = [], [], []
    c = r

    def mark(s, e, lat, width, mi):
        h = width / 2.0
        if c.axis == "H":
            pts = [(s, c.center + lat - h, Z_MARK), (e, c.center + lat - h, Z_MARK),
                   (e, c.center + lat + h, Z_MARK), (s, c.center + lat + h, Z_MARK)]
        else:
            pts = [(c.center + lat - h, s, Z_MARK), (c.center + lat - h, e, Z_MARK),
                   (c.center + lat + h, e, Z_MARK), (c.center + lat + h, s, Z_MARK)]
        b = len(mv)
        mv.extend(pts)
        mf.append((b, b + 1, b + 2, b + 3))
        mm.append(mi)

    if r.hier == "arterial":
        for lat in (-(c.car - 0.5), (c.car - 0.5)):
            mark(a0, a1, lat, 0.15, 0)
        for lat in (-(MEDIAN_HW + 0.18), (MEDIAN_HW + 0.18)):
            mark(a0, a1, lat, 0.15, 1)
        for lat in (-(MEDIAN_HW + 4.0), (MEDIAN_HW + 4.0)):
            t = a0 + 1.5
            while t + 3.0 <= a1:
                mark(t, t + 3.0, lat, 0.15, 0)
                t += 9.0
        name = "SM_RoadMarking_Arterial_%03d" % idx
    else:
        for lat in (-(c.car - 0.5), (c.car - 0.5)):
            mark(a0, a1, lat, 0.12, 0)
        t = a0 + 1.5
        while t + 3.0 <= a1:
            mark(t, t + 3.0, 0.0, 0.15, 0)
            t += 9.0
        name = "SM_RoadMarking_Street_%03d" % idx
    if not mf:
        return None
    return make_obj(name, mv, mf, [MATS["marking_white"], MATS["marking_yellow"]],
                    mm, ctx["Meshes"], {"edge_id": r.id})


# --------------------------------------------------------------------------
# junctions + curb returns
# --------------------------------------------------------------------------
def patch_quads(inc_list):
    hx = max([d["hw"] for d in inc_list if d["axis"] == "V"] or [0.0])
    hy = max([d["hw"] for d in inc_list if d["axis"] == "H"] or [0.0])
    if hx <= 1e-6 or hy <= 1e-6:
        return []
    has = {(d["axis"], d["sign"]) for d in inc_list}
    faces = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            if ("H", sx) in has or ("V", sy) in has:
                x0, x1 = sorted((0.0, sx * hx))
                y0, y1 = sorted((0.0, sy * hy))
                faces.append((x0, y0, x1, y1))
    return faces


def node_incidence(roads):
    inc = {}
    for r in roads:
        for nid, p in ((r.e["a"], r.a), (r.e["b"], r.b)):
            if r.axis == "H":
                sign = 1 if abs(p[0] - r.c1) < 1e-6 else -1
            else:
                sign = 1 if abs(p[1] - r.c1) < 1e-6 else -1
            inc.setdefault(nid, []).append(
                {"axis": r.axis, "sign": sign, "hw": r.car, "id": r.id,
                 "prio": r.prio, "hier": r.hier})
    return inc


def build_junction_patches(roads, nodes, ctx):
    inc = node_incidence(roads)
    buckets = {"arterial": [[], []], "street": [[], []], "alley": [[], []]}
    per_class = {}
    for nid, lst in inc.items():
        if len({d["axis"] for d in lst}) < 2:
            continue
        hp = max(d["prio"] for d in lst if d["axis"] == "H")
        vp = max(d["prio"] for d in lst if d["axis"] == "V")
        if hp != vp:
            continue
        hier = [k for k, v in PRIO.items() if v == hp and k in GROUND][0]
        p = nodes[nid][:2]
        for (x0, y0, x1, y1) in patch_quads(lst):
            v = [(p[0] + x0, p[1] + y0, 0.0), (p[0] + x1, p[1] + y0, 0.0),
                 (p[0] + x1, p[1] + y1, 0.0), (p[0] + x0, p[1] + y1, 0.0)]
            b = len(buckets[hier][0])
            buckets[hier][0].extend(v)
            buckets[hier][1].append((b, b + 1, b + 2, b + 3))
            per_class[hier] = per_class.get(hier, 0) + 1
    objs = []
    for hier, (v, f) in buckets.items():
        if not f:
            continue
        mat = MATS["cobble_stone"] if hier == "alley" else MATS["asphalt"]
        nm = {"arterial": "SM_RoadSurface_Junction_Arterial_01",
              "street": "SM_RoadSurface_Junction_Street_01",
              "alley": "SM_RoadJunction_Alley_01"}[hier]
        objs.append(make_obj(nm, v, f, [mat], None, ctx["Meshes"],
                             {"kind": "%s_junction" % hier, "quads": len(f)}))
    STATS["junctions"] = per_class
    log("  junction patches: %s" % per_class)
    return objs


def build_curb_returns(roads, nodes, ctx):
    verts, faces = [], []
    n_fill = 0
    by_node = {}
    for r in roads:
        if r.hier not in ("arterial", "street"):
            continue
        by_node.setdefault(r.e["a"], []).append(r)
        by_node.setdefault(r.e["b"], []).append(r)
    for nid, lst in by_node.items():
        hh = [r for r in lst if r.axis == "H"]
        vv = [r for r in lst if r.axis == "V"]
        for h in hh:
            for v in vv:
                if h.prio != v.prio:
                    continue
                jx, jy = nodes[nid][0], nodes[nid][1]
                for hs in (-1, 1):
                    for vs in (-1, 1):
                        ov = rect_overlap(h.strip_rect(hs), v.strip_rect(vs))
                        if ov is None:
                            continue
                        x0, y0, x1, y1 = ov
                        if (x1 - x0) > SW + 1e-6 or (y1 - y0) > SW + 1e-6:
                            continue
                        ix = x0 if abs(x0 - jx) < abs(x1 - jx) else x1
                        iy = y0 if abs(y0 - jy) < abs(y1 - jy) else y1
                        ox, oy = (x1 if ix == x0 else x0), (y1 if iy == y0 else y0)
                        rad = min(x1 - x0, y1 - y0)
                        cx, cy = ox, oy
                        sgnx = 1.0 if ix > cx else -1.0
                        sgny = 1.0 if iy > cy else -1.0
                        pa = (cx, cy + sgny * rad)
                        pb = (cx + sgnx * rad, cy)
                        poly = [pa]
                        N = 6
                        a0 = math.atan2(pa[1] - cy, pa[0] - cx)
                        a1 = math.atan2(pb[1] - cy, pb[0] - cx)
                        while a1 - a0 > math.pi:
                            a1 -= 2 * math.pi
                        while a0 - a1 > math.pi:
                            a1 += 2 * math.pi
                        for k in range(1, N + 1):
                            a = a0 + (a1 - a0) * k / N
                            poly.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
                        poly.append((ox, oy))
                        b = len(verts)
                        verts.extend([(px, py, KERB_H) for px, py in poly])
                        faces.append(tuple(b + i for i in range(len(poly))))
                        n_fill += 1
    objs = []
    if faces:
        objs.append(make_obj("SM_CurbReturn_Arterial_Street_01", verts, faces,
                             [MATS["sidewalk_concrete"]], None, ctx["Meshes"],
                             {"kind": "curb_return", "count": n_fill}))
    STATS["curb_returns"] = n_fill
    log("  curb returns: %d fillets" % n_fill)
    return objs


# --------------------------------------------------------------------------
# highway ring ground band
# --------------------------------------------------------------------------
def ring_quad(r, a0, a1, lat0, lat1, z):
    lo, hi = sorted((lat0, lat1))
    if r.axis == "H":
        return [(a0, r.center + lo, z), (a1, r.center + lo, z),
                (a1, r.center + hi, z), (a0, r.center + hi, z)]
    return [(r.center + lo, a0, z), (r.center + lo, a1, z),
            (r.center + hi, a1, z), (r.center + hi, a0, z)]


def build_service_road(ring, ctx):
    objs = []
    for r in ring:
        corner = [False, False]
        for end in (0, 1):
            p = r.a if end == 0 else r.b
            for f in ring:
                if f.axis == r.axis:
                    continue
                ok = (abs((p[0] if r.axis == "H" else p[1]) - f.center) < 1e-6 and
                      f.c0 - 1e-6 <= (p[1] if r.axis == "H" else p[0]) <= f.c1 + 1e-6)
                if ok:
                    corner[end] = True

        def span(hw):
            """Trim each band by its own half-width, so the nested corner
            patch closes the square exactly (asphalt 10, gravel 28, dirt 40)."""
            return (r.c0 + (hw if corner[0] else 0.0),
                    r.c1 - (hw if corner[1] else 0.0))

        a0, a1 = span(HW_DIRT)
        if a1 - a0 < 1.0:
            continue
        sa0, sa1 = span(HW_ASP)
        v = ring_quad(r, sa0, sa1, -HW_ASP, HW_ASP, 0.0)
        objs.append(make_obj("SM_ServiceRoad_%s" % r.id, v, [(0, 1, 2, 3)],
                             [MATS["asphalt_highway"], MATS["asphalt_worn"]], [0],
                             ctx["Meshes"],
                             {"edge_id": r.id, "kind": "service_road",
                              "width": 2 * HW_ASP, "z": 0.0,
                              "dedupe_with_flyover": r.id in ("H_07", "H_08")}))
        ga0, ga1 = span(HW_GRAVEL)
        for sgn in (-1, 1):
            tag = "L" if sgn < 0 else "R"
            v = ring_quad(r, ga0, ga1, sgn * HW_ASP, sgn * HW_GRAVEL, Z_VERGE)
            objs.append(make_obj("SM_ServiceVerge_%s%s" % (r.id, tag), v,
                                 [(0, 1, 2, 3)], [MATS["gravel"]], None,
                                 ctx["Meshes"], {"edge_id": r.id, "kind": "verge"}))
            v = ring_quad(r, a0, a1, sgn * HW_GRAVEL, sgn * HW_DIRT, Z_VERGE)
            objs.append(make_obj("SM_ServiceDirt_%s%s" % (r.id, tag), v,
                                 [(0, 1, 2, 3)], [MATS["dirt"]], None,
                                 ctx["Meshes"], {"edge_id": r.id, "kind": "dirt"}))
        for end in (0, 1):
            if not corner[end]:
                continue
            ox, oy = (r.c0, r.center) if (r.axis == "H" and end == 0) else \
                     (r.c1, r.center) if r.axis == "H" else \
                     (r.center, r.c0) if end == 0 else (r.center, r.c1)
            for ha, hb, mat in ((HW_DIRT, HW_GRAVEL, "dirt"),
                                (HW_GRAVEL, HW_ASP, "gravel")):
                v = [(ox - ha, oy - ha, Z_VERGE), (ox + ha, oy - ha, Z_VERGE),
                     (ox + ha, oy + ha, Z_VERGE), (ox - ha, oy + ha, Z_VERGE),
                     (ox - hb, oy - hb, Z_VERGE), (ox + hb, oy - hb, Z_VERGE),
                     (ox + hb, oy + hb, Z_VERGE), (ox - hb, oy + hb, Z_VERGE)]
                f = [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
                objs.append(make_obj("SM_ServiceCorner_%s_%s_%d" % (r.id, mat, end),
                                     v, f, [MATS[mat]], None, ctx["Meshes"],
                                     {"kind": "ring_corner"}))
            v = [(ox + sx * HW_ASP, oy + sy * HW_ASP, 0.0)
                 for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            objs.append(make_obj("SM_ServiceRoad_Corner_%s_%d" % (r.id, end), v,
                                 [(0, 1, 2, 3)], [MATS["asphalt_highway"]], None,
                                 ctx["Meshes"], {"kind": "ring_corner"}))
    log("  highway ring ground: %d edges, %d objects" % (len(ring), len(objs)))
    return objs


def build_ramp_geometry(conns, ctx):
    objs = []
    for q in conns:
        x0, y0, x1, y1 = q["ring_apron"]
        objs.append(make_obj("SM_RampConnector_%s" % q["id"],
                             [(x0, y0, 0.0), (x1, y0, 0.0), (x1, y1, 0.0), (x0, y1, 0.0)],
                             [(0, 1, 2, 3)], [MATS["asphalt"]], None, ctx["Meshes"],
                             {"ramp": q["id"], "kind": "ring_apron", "z": 0.0}))
        if q["flyover"]:
            continue
        x0, y0, x1, y1 = q["foot_pad"]
        objs.append(make_obj("SM_RampFoot_%s" % q["id"],
                             [(x0, y0, 0.0), (x1, y0, 0.0), (x1, y1, 0.0), (x0, y1, 0.0)],
                             [(0, 1, 2, 3)], [MATS["asphalt"]], None, ctx["Meshes"],
                             {"ramp": q["id"], "kind": "foot_pad", "z": 0.0,
                              "width": 18.0}))
        mv, mf = [], []
        if q["axis"] == "H":
            for yy in (y0 + 0.6, y1 - 0.75):
                b = len(mv)
                mv.extend([(x0, yy, Z_MARK), (x1, yy, Z_MARK),
                           (x1, yy + 0.15, Z_MARK), (x0, yy + 0.15, Z_MARK)])
                mf.append((b, b + 1, b + 2, b + 3))
        else:
            for xx in (x0 + 0.6, x1 - 0.75):
                b = len(mv)
                mv.extend([(xx, y0, Z_MARK), (xx + 0.15, y0, Z_MARK),
                           (xx + 0.15, y1, Z_MARK), (xx, y1, Z_MARK)])
                mf.append((b, b + 1, b + 2, b + 3))
        objs.append(make_obj("SM_RampFoot_Marking_%s" % q["id"], mv, mf,
                             [MATS["marking_white"]], None, ctx["Meshes"],
                             {"ramp": q["id"], "kind": "ramp_marking"}))
    log("  ramp connector geometry: %d objects" % len(objs))
    return objs


def build_spurs(spurs, ctx):
    objs = []
    for sp in spurs:
        v, f = strip_faces(sp["att"], sp["end"], SPUR_W / 2.0, 0.0)
        if not v:
            continue
        objs.append(make_obj("SM_Spur_%s" % sp["facility"], v, [(0, 1, 2, 3)],
                             [MATS["asphalt"]], None, ctx["Meshes"],
                             {"facility": sp["facility"], "edge_id": sp["edge"],
                              "length": round(sp["length"], 2), "width": SPUR_W,
                              "district": sp.get("district", "")}))
    log("  spur geometry: %d objects" % len(objs))
    return objs


# --------------------------------------------------------------------------
# details (instanced manholes / drains)
# --------------------------------------------------------------------------
def shared_instance(name, src_me, loc, rot_z, coll, props=None):
    ob = bpy.data.objects.new(name, src_me)
    ob.location = (loc[0], loc[1], loc[2])
    ob.rotation_euler = (0.0, 0.0, rot_z)
    coll.objects.link(ob)
    ob["module"] = "roads"
    if props:
        for k, v in props.items():
            ob[k] = v
    return ob


def build_details(roads, ctx):
    N = 16
    rad = 0.34
    mv, mf = [], []
    for k in range(N):
        a = 2 * math.pi * k / N
        mv.append((rad * math.cos(a), rad * math.sin(a), 0.004))
    for k in range(N):
        a = 2 * math.pi * k / N
        mv.append((rad * math.cos(a), rad * math.sin(a), 0.035))
    mv.append((0.0, 0.0, 0.035))
    ctop = 2 * N
    for k in range(N):
        j = (k + 1) % N
        mf.append((k, j, N + j, N + k))
        mf.append((ctop, N + k, N + j))
    man_me = bpy.data.meshes.new("SM_Manhole_Cast_01")
    man_me.from_pydata(mv, [], mf)
    man_me.update()
    man_me.materials.append(MATS["metal_steel"])

    w, d, h = 0.85, 0.45, 0.06
    gv = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for z in (0.0, h):
                gv.append((sx * w / 2, sy * d / 2, z))
    gf = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
          (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    grate_me = bpy.data.meshes.new("SM_StormDrain_Grate_01")
    grate_me.from_pydata(gv, [], gf)
    grate_me.update()
    grate_me.materials.append(MATS["rust"])

    made = 0
    for i, e in enumerate(roads, 1):
        if e.hier not in GROUND:
            continue
        a0, a1 = e.clipped()
        L = a1 - a0
        if L < 8.0:
            continue
        n_man = max(1, int(L // 70.0))
        for k in range(n_man):
            along = a0 + L * (k + 0.5) / n_man
            lat = 1.6 if (k + i) % 2 == 0 else -1.6
            p = e.pt(along, lat, 0.0)
            shared_instance("SM_Manhole_Cast_%04d" % made, man_me,
                            (p[0], p[1], 0.0), 0.0, ctx["Meshes"],
                            {"edge_id": e.id})
            made += 1
        n_dr = max(1, int(L // 55.0))
        for k in range(n_dr):
            along = a0 + L * (k + 0.5) / n_dr
            side = 1 if (k + i) % 2 == 0 else -1
            p = e.pt(along, side * (e.car - 0.35), 0.0)
            shared_instance("SM_StormDrain_Grate_%04d" % made, grate_me,
                            (p[0], p[1], 0.0),
                            0.0 if e.axis == "H" else math.pi / 2,
                            ctx["Meshes"], {"edge_id": e.id})
            made += 1
    STATS["details"] = made
    log("  detail instances: %d (2 shared meshes)" % made)
    return made


# --------------------------------------------------------------------------
# colliders
# --------------------------------------------------------------------------
def build_colliders(roads, ring, spurs, conns, ctx):
    coll = ctx["Colliders"]
    made = 0
    for r in roads:
        x0, y0, x1, y1 = r.env_rect()
        v, f = box_geom(x0, y0, x1, y1, -0.05, 0.0)
        ob = make_obj("COL_road_%s" % r.id, v, f, [], None, coll,
                      {"edge_id": r.id, "proxy": "road", "hierarchy": r.hier})
        ob.hide_render = True
        made += 1
        if r.hier in ("arterial", "street"):
            for side, tag in ((-1, ""), (1, "_R")):
                sx0, sy0, sx1, sy1 = r.strip_rect(side)
                v, f = box_geom(sx0, sy0, sx1, sy1, 0.0, KERB_H)
                ob = make_obj("COL_sidewalk_%s%s" % (r.id, tag), v, f, [], None,
                              coll, {"edge_id": r.id, "proxy": "sidewalk",
                                     "side": side})
                ob.hide_render = True
                made += 1
    for r in ring:
        x0, y0, x1, y1 = r.env_rect()
        v, f = box_geom(x0, y0, x1, y1, -0.1, 0.0)
        ob = make_obj("COL_road_%s" % r.id, v, f, [], None, coll,
                      {"edge_id": r.id, "proxy": "service_road"})
        ob.hide_render = True
        made += 1
    for q in conns:
        x0, y0, x1, y1 = q["ring_apron"]
        v, f = box_geom(x0, y0, x1, y1, -0.05, 0.0)
        ob = make_obj("COL_road_%s" % q["id"], v, f, [], None, coll,
                      {"edge_id": q["id"], "proxy": "ring_apron"})
        ob.hide_render = True
        made += 1
    for sp in spurs:
        att, end = sp["att"], sp["end"]
        pad = SPUR_W / 2.0
        v, f = box_geom(min(att[0], end[0]) - (pad if sp["axis"] == "V" else 0),
                        min(att[1], end[1]) - (pad if sp["axis"] == "H" else 0),
                        max(att[0], end[0]) + (pad if sp["axis"] == "V" else 0),
                        max(att[1], end[1]) + (pad if sp["axis"] == "H" else 0),
                        -0.05, 0.0)
        ob = make_obj("COL_spur_%s" % sp["facility"], v, f, [], None, coll,
                      {"facility": sp["facility"], "proxy": "spur"})
        ob.hide_render = True
        made += 1
    for q in conns:
        if q["flyover"]:
            continue
        x0, y0, x1, y1 = q["foot_pad"]
        v, f = box_geom(x0, y0, x1, y1, -0.05, 0.0)
        ob = make_obj("COL_rampfoot_%s" % q["id"], v, f, [], None, coll,
                      {"ramp": q["id"], "proxy": "ramp_foot"})
        ob.hide_render = True
        made += 1
    STATS["colliders"] = made
    log("  colliders: %d" % made)
    return made


# --------------------------------------------------------------------------
# verification + parity
# --------------------------------------------------------------------------
def collect_facts(roads):
    coll = bpy.data.collections.get("Roads")
    by_edge = {}
    for ob in coll.all_objects:
        eid = ob.get("edge_id")
        if eid and ob.name.startswith("SM_"):
            by_edge.setdefault(eid, []).append(ob)
    facts = {}
    for r in roads:
        objs = by_edge.get(r.id, [])
        zs, lats, mats, kinds = set(), set(), set(), {}
        along = []
        for ob in objs:
            if ob.data is None or ob.data.users > 1:
                continue
            kind = ob.name.split("_")[1]
            if kind not in CROSS_KINDS:
                continue
            kz, kl, km = kinds.setdefault(kind, [set(), set(), set()])
            for m in ob.data.materials:
                mats.add(m.name)
                km.add(m.name)
            for v in ob.data.vertices:
                zs.add(round(v.co.z, 3))
                lats.add(round(r.lat_of((v.co.x, v.co.y)), 3))
                along.append(round(r.along_of((v.co.x, v.co.y)), 3))
                kz.add(round(v.co.z, 3))
                kl.add(round(r.lat_of((v.co.x, v.co.y)), 3))
        facts[r.id] = {"z": sorted(zs), "lat": sorted(lats), "mats": sorted(mats),
                       "kinds": {k: {"z": sorted(v[0]), "lat": sorted(v[1]),
                                     "mats": sorted(v[2])}
                                 for k, v in kinds.items()},
                       "along": [min(along), max(along)] if along else [0.0, 0.0]}
    return facts


def parity_check(roads, facts, ref_path):
    """Compare the 149 pilot edges with the pilot blend's extracted facts.

    Per edge: z-level set, material set, lateral envelope, and per-object-kind
    (RoadSurface / Median / Sidewalk / KerbRamp / RoadMarking) cross-section.
    Alleys additionally compare their along-extent (12 m arterial clip).
    """
    if not os.path.isfile(ref_path):
        return {"status": "SKIP", "reason": "pilot reference facts not found",
                "edges": 0, "pass": 0, "fail": 0}
    ref = json.load(open(ref_path))
    by_id = {r.id: r for r in roads}
    rows, fails = [], []
    for eid, ref_objs in ref["per_edge"].items():
        r = by_id.get(eid)
        if r is None or eid not in facts:
            fails.append("%s: edge missing" % eid)
            continue
        f = facts[eid]
        rz, rm = set(), set()
        r_lat = [1e9, -1e9]
        rkind = {}
        r_along = []
        for o in ref_objs:
            if o["users"] > 1 or o["name"].startswith("COL_"):
                continue
            kind = o["name"].split("_")[1]
            kz, km = rkind.setdefault(kind, [set(), set()])
            for z in o["z"]:
                rz.add(round(z, 3)); kz.add(round(z, 3))
            for m in o["mats"]:
                rm.add(m); km.add(m)
            bb = o["bb"]
            if r.axis == "H":
                lo, hi = min(bb[1], bb[3]), max(bb[1], bb[3])
                r_along.extend([bb[0], bb[2]])
            else:
                lo, hi = min(bb[0], bb[2]), max(bb[0], bb[2])
                r_along.extend([bb[1], bb[3]])
            r_lat[0] = min(r_lat[0], lo)
            r_lat[1] = max(r_lat[1], hi)
        diffs = []
        if rz != set(f["z"]):
            diffs.append("z %s != %s" % (sorted(rz), f["z"]))
        if rm != set(f["mats"]):
            diffs.append("mats %s != %s" % (sorted(rm), f["mats"]))
        n_lat = [min(f["lat"]), max(f["lat"])]
        r_lat = [r_lat[0] - r.center, r_lat[1] - r.center]
        if abs(n_lat[0] - r_lat[0]) > 1e-3 or abs(n_lat[1] - r_lat[1]) > 1e-3:
            diffs.append("lat envelope %s != %s" % (r_lat, n_lat))
        for kind, (kz, km) in rkind.items():
            if kind not in f["kinds"]:
                continue
            nk = f["kinds"][kind]
            if kz != set(nk["z"]) or km != set(nk["mats"]):
                diffs.append("%s cross-section differs" % kind)
            else:
                rl = [1e9, -1e9]
                for o in ref_objs:
                    if o["users"] > 1 or o["name"].split("_")[1] != kind:
                        continue
                    bb = o["bb"]
                    rl[0] = min(rl[0], min(bb[1], bb[3]) if r.axis == "H"
                                else min(bb[0], bb[2]))
                    rl[1] = max(rl[1], max(bb[1], bb[3]) if r.axis == "H"
                                else max(bb[0], bb[2]))
                nl = [min(nk["lat"]), max(nk["lat"])]
                rl = [rl[0] - r.center, rl[1] - r.center]
                if abs(rl[0] - nl[0]) > 1e-3 or abs(rl[1] - nl[1]) > 1e-3:
                    diffs.append("%s lat %s != %s" % (kind, rl, nl))
        if eid.startswith("L_"):
            ra = [min(r_along), max(r_along)]
            if abs(ra[0] - f["along"][0]) > 0.02 or \
                    abs(ra[1] - f["along"][1]) > 0.02:
                diffs.append("clip %s != %s" % (ra, f["along"]))
        rows.append({"edge": eid, "ok": not diffs, "diffs": diffs[:4]})
        if diffs:
            fails.append("%s: %s" % (eid, "; ".join(diffs[:2])))
    n_ok = sum(1 for x in rows if x["ok"])
    status = "PASS" if not fails else "FAIL"
    for x in fails[:12]:
        log("   PARITY FAIL %s" % x)
    log("  pilot parity: %s (%d/%d edges identical cross-section: z, materials, "
        "lateral envelope)" % (status, n_ok, len(rows)))
    return {"status": status, "edges": len(rows), "pass": n_ok,
            "fail": len(rows) - n_ok, "failures": fails[:20],
            "reference": ref_path,
            "checks": ["z levels", "materials", "lateral envelope",
                       "per-kind cross-section", "alley clip distance"]}


def verify(roads, facts, ctx, png):
    coll = bpy.data.collections.get("Roads")
    objs = list(coll.all_objects) if coll else []
    n_obj = len(objs)
    tris_unique = ck.scene_tri_count()
    tris_inst = ck.tri_count(coll)
    # geometry sanity
    bad_z = []
    for ob in objs:
        if ob.type != "MESH" or ob.name.startswith("COL_"):
            continue
        if ob.data is None or ob.data.users > 1:
            continue
        for v in ob.data.vertices:
            if v.co.z < -0.11 or v.co.z > 0.16:
                bad_z.append(ob.name)
                break
    # carriageway coverage: every ground edge has a RoadSurface object
    have = {ob.get("edge_id") for ob in objs if "RoadSurface" in ob.name}
    missing = [r.id for r in roads if r.hier in GROUND and r.id not in have]
    log("VERIFY objects=%d tris(unique scene)=%d tris(instanced module)=%d"
        % (n_obj, tris_unique, tris_inst))
    log("VERIFY z out of [-0.11,0.16]: %d objects" % len(bad_z))
    log("VERIFY ground edges without carriageway: %d %s"
        % (len(missing), missing[:6]))
    log("VERIFY preview=%s (%s)" % (png, "ok" if os.path.isfile(png) else "MISSING"))
    return {"objects": n_obj, "tris_unique": tris_unique,
            "tris_instanced": tris_inst, "objects_bad_z": len(bad_z),
            "edges_missing_carriageway": missing,
            "preview_ok": os.path.isfile(png)}


# --------------------------------------------------------------------------
# reports
# --------------------------------------------------------------------------
def write_reports(data, extra, parity):
    ck.write_report("roads", data)
    md = []
    md.append("# Roads module report — FULL network (454 edges)\n\n")
    md.append("Generated: %s\n\n" % data["written"])
    md.append("Files\n\n")
    md.append("- script: `modules/roads.py`\n")
    md.append("- blend: `out/roads.blend`\n")
    md.append("- preview: `out/roads_preview.png` (1920x1080, EEVEE)\n")
    md.append("- pilot reference blend: `%s`\n\n" % data["pilot_reference"])
    md.append("## Scope (layout.json)\n\n")
    for h in ("arterial", "street", "alley", "highway", "interchange_ramp"):
        md.append("* %s: **%d** edges, %d km\n"
                  % (h, data["edges_by_hierarchy"][h],
                     round(data["km_by_hierarchy"][h], 1)))
    md.append("* total: **%d** edges / **%d** nodes\n\n"
              % (data["edges_total"], data["nodes_total"]))
    md.append("## Counts\n\n")
    md.append("| item | value |\n|---|---|\n")
    md.append("| objects in module | %d |\n" % data["objects"])
    md.append("| triangles unique (whole file) | %d |\n" % data["tris_unique"])
    md.append("| triangles instanced (module) | %d |\n" % data["tris_instanced"])
    md.append("| colliders | %d |\n" % data["colliders"])
    md.append("| zebra crosswalks (legs / lights) | %d / %d |\n"
              % (data["crosswalks"], data["traffic_lights"]))
    md.append("| access spurs | %d |\n" % data["spurs"])
    md.append("| infield facilities (Track access, no spur) | %d |\n"
              % len(data["spurs_infield"]))
    md.append("| ramp connectors (ring aprons) | %d |\n" % data["ramp_connectors"])
    md.append("| junction patches (quads) | %s |\n" % data["junctions"])
    md.append("| curb-return fillets | %d |\n" % data["curb_returns"])
    md.append("| manhole/drain instances | %d |\n" % data["details"])
    md.append("| build seconds | %.1f |\n\n" % data["build_seconds"])
    md.append("## PILOT PARITY\n\n")
    md.append("Reference: pilot blend snapshot + facts extracted per edge "
              "(%s).\n\n" % parity.get("reference", "n/a"))
    md.append("- status: **%s** — %d/%d pilot edges identical (%d failed)\n"
              % (parity["status"], parity["pass"], parity["edges"], parity["fail"]))
    md.append("- checks: %s\n" % ", ".join(parity.get("checks", [])))
    if parity.get("failures"):
        md.append("- failures: %s\n" % "; ".join(parity["failures"][:6]))
    md.append("\nThe pilot's 5 arterial edges and 144 market alleys keep the exact "
              "same cross-section: carriageway top z=0, kerb/sidewalk top z=0.15, "
              "median 3.0 m raised 0.15, markings z=0.005, crosswalks z=0.007, "
              "arterial envelope 12.0 m (carriageway 9.5 + sidewalk 2.5), alley "
              "envelope 2.5 m cobble clipped 12 m off the arterial centreline. "
              "What changed on those edges is only the number of junction cuts "
              "(the rest of the network now exists) and the crosswalk positions at "
              "the newly built perpendicular legs.\n\n")
    md.append("## Geometry facts for the Assembler\n\n")
    for line in extra:
        md.append("* %s\n" % line)
    md.append("\n## Materials used (%d)\n\n" % len(data["materials"]))
    for m in data["materials"]:
        md.append("* `%s`\n" % m)
    md.append("\n## Known issues\n\n")
    for i in data["issues"]:
        md.append("* %s\n" % i)
    md.append("\njson report: `reports/roads_report.json`\n")
    with open(os.path.join(ck.REPORTS_DIR, "roads_report.md"), "w") as f:
        f.write("".join(md))
    log("report -> %s" % os.path.join(ck.REPORTS_DIR, "roads_report.md"))


def render_preview(png):
    """1920x1080 EEVEE aerial: 4-way arterial junction at (1200,0) in the
    foreground, east ring service road + verges across the top. The preview
    brightens the saved world / exposure temporarily (the scene world is a dark
    neutral for the master render) and restores both afterwards."""
    scene = bpy.context.scene
    old_exp = scene.view_settings.exposure
    bg = None
    old_bg = None
    world = scene.world
    if world is not None and world.use_nodes:
        bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
        if bg is not None:
            old_bg = (tuple(bg.inputs[0].default_value), bg.inputs[1].default_value)
            bg.inputs[0].default_value = (0.42, 0.52, 0.66, 1.0)
            bg.inputs[1].default_value = 0.9
    scene.view_settings.exposure = 0.5
    try:
        ck.make_preview(png, (880.0, -260.0, 260.0), (1300.0, 30.0, 0.0),
                        engine="BLENDER_EEVEE", res=(1920, 1080), samples=32,
                        sun_elev=48.0, sun_energy=5.0)
    finally:
        scene.view_settings.exposure = old_exp
        if bg is not None and old_bg is not None:
            bg.inputs[0].default_value = old_bg[0]
            bg.inputs[1].default_value = old_bg[1]


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main():
    t0 = time.time()
    layout = ck.read_layout()
    nodes = {n["id"]: tuple(n["pos"]) for n in layout["road_nodes"]}
    all_edges = layout["road_edges"]
    root, sub = reset_collections()
    load_materials()
    ctx = {"Meshes": sub["Meshes"], "Colliders": sub["Colliders"],
           "Lights": sub["Lights"], "gaps": {}, "ramps": {}}

    roads = [Road(e, nodes) for e in all_edges if e["hierarchy"] in GROUND]
    ring = [Road(e, nodes) for e in all_edges if e["hierarchy"] == "highway"]
    ramps = [Road(e, nodes) for e in all_edges
             if e["hierarchy"] == "interchange_ramp"]
    idx = build_index(roads)
    for h in GROUND:
        log("%s edges: %d" % (h, sum(1 for r in roads if r.hier == h)))

    compute_stops(roads, idx, ctx)
    spurs = compute_spurs(roads, ctx, ring)
    compute_zebras(roads, nodes, layout, ctx)
    conns = compute_ramp_connectors(roads, nodes, layout, ctx)
    log("gaps registered: %d sidewalk openings, %d ramps"
        % (sum(len(v) for v in ctx["gaps"].values()),
           sum(len(v) for v in ctx["ramps"].values())))

    # ---- staged build -----------------------------------------------------
    counters = {h: 0 for h in GROUND}
    for hier in GROUND:
        group = [r for r in roads if r.hier == hier]
        n_car = 0
        for i, r in enumerate(group, 1):
            counters[hier] += 1
            if build_carriageway(r, ctx, counters[hier]):
                n_car += 1
            if hier == "arterial":
                build_median(r, ctx, counters[hier])
                build_markings(r, ctx, counters[hier])
            elif hier == "street":
                build_markings(r, ctx, counters[hier])
            for side in (-1, 1):
                build_sidewalk(r, side, ctx, counters[hier])
            if i % 50 == 0:
                log("  %s %d/%d" % (hier, i, len(group)))
                ck.save_blend(os.path.join(ck.OUT_DIR, "roads.blend"))
        STATS["edges_built"][hier] = counters[hier]
        ck.save_blend(os.path.join(ck.OUT_DIR, "roads.blend"))
        STATS["stages"].append("built %s (%d edges)" % (hier, counters[hier]))
        log("stage saved: %s (%d edges, %d carriageways)"
            % (hier, counters[hier], n_car))

    build_junction_patches(roads, nodes, ctx)
    build_curb_returns(roads, nodes, ctx)
    ck.save_blend(os.path.join(ck.OUT_DIR, "roads.blend"))
    STATS["stages"].append("junctions + curb returns")

    build_service_road(ring, ctx)
    build_ramp_geometry(conns, ctx)
    build_spurs(spurs, ctx)
    ck.save_blend(os.path.join(ck.OUT_DIR, "roads.blend"))
    STATS["stages"].append("ring service road + ramps + spurs")

    build_details(roads, ctx)
    build_colliders(roads, ring, spurs, conns, ctx)
    ck.save_blend(os.path.join(ck.OUT_DIR, "roads.blend"))
    STATS["stages"].append("details + colliders")

    # transforms: unique meshes only (instance placement transforms are kept)
    n_applied = 0
    for ob in list(sub["Meshes"].objects) + list(sub["Colliders"].objects):
        if ob.type == "MESH" and ob.data is not None and ob.data.users == 1:
            if ck.apply_all_transforms(ob):
                n_applied += 1
    ck.update_view()
    log("applied transforms on %d unique meshes" % n_applied)

    # ---- verification / parity -------------------------------------------
    facts = collect_facts(roads)
    ref = os.path.join(ck.REPORTS_DIR, "roads_pilot_reference.json")
    parity = parity_check(roads, facts, ref)

    png = os.path.join(ck.OUT_DIR, "roads_preview.png")
    if not os.environ.get("ROADS_NOPREVIEW"):
        render_preview(png)
    stats = verify(roads, facts, ctx, png)
    ck.save_blend(os.path.join(ck.OUT_DIR, "roads.blend"))

    # ---- report -----------------------------------------------------------
    by_h = {h: sum(1 for e in all_edges if e["hierarchy"] == h)
            for h in ("arterial", "street", "alley", "highway",
                      "interchange_ramp")}
    km_h = {}
    for h in by_h:
        km_h[h] = sum(e.get("length", 0.0) for e in all_edges
                      if e["hierarchy"] == h) / 1000.0
    data = {
        "edges_total": len(all_edges),
        "nodes_total": len(layout["road_nodes"]),
        "edges_by_hierarchy": by_h,
        "km_by_hierarchy": km_h,
        "edges_built": STATS["edges_built"],
        "objects": stats["objects"],
        "tris_unique": stats["tris_unique"],
        "tris_instanced": stats["tris_instanced"],
        "colliders": STATS["colliders"],
        "crosswalks": STATS["zebras"],
        "traffic_lights": len(layout["traffic_lights"]),
        "traffic_light_nodes": len(STATS.get("zebra_nodes", {})),
        "spurs": STATS["spurs"],
        "spurs_skipped": STATS["spurs_skipped"],
        "spurs_infield": STATS["spurs_infield"],
        "ramp_connectors": STATS["ramp_connectors"],
        "junctions": STATS["junctions"],
        "curb_returns": STATS["curb_returns"],
        "details": STATS["details"],
        "materials": sorted(MATS),
        "parity": parity,
        "objects_bad_z": stats["objects_bad_z"],
        "edges_missing_carriageway": stats["edges_missing_carriageway"],
        "preview_ok": stats["preview_ok"],
        "preview": png,
        "build_seconds": round(time.time() - t0, 1),
        "pilot_reference": "/tmp/opencode/roads_pilot_ref.blend",
        "written": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "extrinsics": {
            "road_surface_z": 0.0,
            "kerb_top_z": KERB_H,
            "median_top_z": KERB_H,
            "marking_z": Z_MARK,
            "crosswalk_z": Z_CROSS,
            "arterial_envelope_halfwidth": ART_HW,
            "arterial_carriageway_halfwidth": ART_CAR,
            "street_envelope_halfwidth": ST_HW,
            "street_carriageway_halfwidth": ST_CAR,
            "alley_envelope_halfwidth": ALLEY_HW,
            "highway_service_asphalt_halfwidth": HW_ASP,
            "highway_verge_halfwidth": HW_GRAVEL,
            "highway_dirt_halfwidth": HW_DIRT,
            "ring_deck_top_z": 8.0,
            "service_road_z": 0.0,
            "verge_z": Z_VERGE,
        },
        "issues": [
            "The Flyover module already builds a ground band for H_07/H_08 "
            "(its NE ring corner). This module builds all 16 ring segments as "
            f"contracted, so H_07/H_08 ground bands exist twice; the objects carry "
            "dedupe_with_flyover=True. The Assembler should keep ONE copy (our "
            "ground band is square-cornered per layout.json, Flyover's NE corner is "
            "a 120 m arc) - dropping our H_07/H_08 objects is the safer choice.",
            "Elevated decks for the other 11 ramps are not built anywhere yet: this "
            "module only provides their ground tie-ins (ring apron + 18 m foot pad).",
            "Ramp X_N_600 already has a landing flare from the Flyover module, so its "
            "foot pad is not duplicated here (its ring apron is).",
            "Spurs: strict geometric adjacency finds %d landlocked facilities "
            "(the brief said 124). %d get a new 8 m spur, none of which enters "
            "the circuit corridor or the racing surface. The other %d sit inside "
            "the circuit zone and are served by the Track module's gated access "
            "road + bridge at (612,-1040) and its infield loop; Roads does not "
            "lay asphalt across the track. That loop serves the pit / paddock / "
            "museum / fan-zone block; the east infield (karting, parking, skid "
            "pad, scoring tower, floodlight B) and the north stand still need "
            "infield service roads from Track."
            % (STATS["spurs"] + len(STATS["spurs_infield"]),
               STATS["spurs"], len(STATS["spurs_infield"])),
            "Alley mouths keep the pilot ramp (0 at the outer kerb line rising to "
            "0.15 at the carriageway edge); street mouths are flush, filled by the "
            "street's own asphalt and sidewalk tongues.",
            "Sidewalk / kerb strips are shells (top z=0.15, faces to z=0); this "
            "module contains no ground plane.",
            "Manhole / drain instances keep their placement transforms on purpose "
            "(baking them would move the single shared mesh).",
            "Zebra crosswalk stripes are one merged mesh (SM_Crosswalk_01), not "
            "instances: 5 quads per leg is cheaper than 5 instanced objects.",
            "Sidewalk openings are cut for every crossing leg, so the pedestrian "
            "route across a junction uses the zebra ramps rather than a continuous "
            "raised footway.",
        ],
    }
    data.update({k: stats[k] for k in ("preview_ok",)})
    extra = [
        "carriageway top **z = 0.0**; kerb / sidewalk / median top **z = 0.15**; "
        "markings **z = 0.005**; zebra stripes **z = 0.007**",
        "arterial: envelope halfwidth **12.0** (carriageway 9.5 + 2.5 sidewalk), "
        "3.0 m median raised 0.15, 2 lanes each way",
        "street: envelope halfwidth **6.0** (carriageway 3.5 + 2.5 sidewalk), "
        "one lane each way, dashed centre line",
        "alley: envelope halfwidth **2.5**, cobble, ends clipped **12 m** off every "
        "arterial centreline",
        "highway ring: ground service road z=0, asphalt 10 m wide (u +/-5), gravel "
        "verge to u=14, dirt to u=20 (both z=-0.05); ring deck at z=8 is Flyover's",
        "ring bands are trimmed at the 4 square corners by their own half-width "
        "(asphalt 5 m, gravel 14 m, dirt 20 m) and closed with nested "
        "dirt/gravel/asphalt corner patches, so the asphalt is continuous",
        "access spurs: %d x 8 m asphalt outside the circuit zone, z=0, "
        "perpendicular to the nearest road, flush with the facility rect edge, "
        "plus a 8.5 m dropped-kerb opening; the %d infield facilities use "
        "Track's gated access road + bridge" % (STATS["spurs"],
                                                len(STATS["spurs_infield"])),
        "12 interchange sites: ring apron (8 x 30 m, z=0) + 18 m foot pad where the "
        "ramp reaches the ground (11 pads; X_N_600 is Flyover's)",
        "everything under collection **Roads** with sub-collections "
        "Meshes / Colliders / Lights; instances keep their placement transforms",
        "preview: `citykit.make_preview` now derives camera clip_start / clip_end "
        "from the camera-target distance, so 1920x1080 aerial views are no "
        "longer cut off by the 100 m default clip",
    ]
    write_reports(data, extra, parity)
    log("DONE in %.1f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
