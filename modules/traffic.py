#!/usr/bin/env python3
"""traffic.py — Traffic module (vehicle kit + instanced traffic) for the AAA City map.

Headless:
  blender -b -P modules/traffic.py

Outputs:
  out/traffic.blend
  out/traffic_preview.png         (aerial busy junction)
  out/traffic_street_preview.png (kerbside market street)
  reports/traffic_report.md
  reports/traffic_report.json
"""
from __future__ import annotations

import math
import os
import random
import sys
import time

ROOT = "/home/abdulhadi/Work/city"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT + "/modules")
import bpy
import bmesh
from mathutils import Matrix, Vector
import citykit as ck

OUT_BLEND = os.path.join(ck.OUT_DIR, "traffic.blend")
PREV_A = os.path.join(ck.OUT_DIR, "traffic_preview.png")
PREV_B = os.path.join(ck.OUT_DIR, "traffic_street_preview.png")
REPORT_MD = os.path.join(ck.REPORTS_DIR, "traffic_report.md")

SEED = 20261027
RND = random.Random(SEED)
T0 = time.time()

LANE_W = 3.5
PARKED_OFFSET = 4.75          # kerb parking offset from centreline
DECK_Z = 8.0                  # elevated highway deck top (flyover.blend)
ELEV_IDS = ("H_07", "H_08")  # only these two ring segments carry a deck

STADIUM_RECTS = [
    (-864.0, -1164.0, -636.0, -936.0),
    (36.0, -1164.0, 264.0, -936.0),
    (-1164.0, -864.0, -936.0, -636.0),
    (-1164.0, -564.0, -936.0, -336.0),
    (12.0, -888.0, 288.0, -612.0),
]
LAKE_BBOX = (-552.58, -1142.57, -335.1, -969.78)
TRACK_ZMIN, TRACK_ZMAX = -1188.0, -12.0
TRACK_MARGIN = 4.0

PAINTS = [
    "metal_painted_charcoal", "metal_painted_navy", "metal_painted_sand",
    "metal_painted_teal", "metal_painted_sage", "metal_painted_mustard",
    "metal_painted_oxblood", "metal_painted_bone", "metal_steel",
    "metal_painted_dark",
]
MATERIALS = {
    "paint": [ck.append_material(n) for n in PAINTS],
    "glass": ck.append_material("glass_dark"),
    "light_warm": ck.append_material("emissive_warm"),
    "neon_red": ck.append_material("neon_red"),
    "sign": ck.append_material("sign_metal"),
    "steel": ck.append_material("metal_steel"),
    "dark": ck.append_material("metal_painted_dark"),
    "col": ck.append_material("col_placeholder"),
}
MATS_USED = set()
ISSUES = []


# --------------------------------------------------------------------------
# mesh builder (verts/faces/material-index), origin at bottom centre
# --------------------------------------------------------------------------
class MB:
    def __init__(self):
        self.v = []
        self.f = []
        self.m = []
        self.mats = []

    def midx(self, name):
        for i, x in enumerate(self.mats):
            if x == name:
                return i
        self.mats.append(name)
        return len(self.mats) - 1

    def add(self, V, F, mi=0):
        if not F:
            return
        off = len(self.v)
        self.v.extend(V)
        self.f.extend([tuple(i + off for i in fc) for fc in F])
        self.m.extend([mi] * len(F))

    def box(self, cx, cy, cz, sx, sy, sz, mi=0):
        x0, x1 = cx - sx / 2.0, cx + sx / 2.0
        y0, y1 = cy - sy / 2.0, cy + sy / 2.0
        z0, z1 = cz - sz / 2.0, cz + sz / 2.0
        V = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        F = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        self.add(V, F, mi)

    def cyl_y(self, cx, cy, cz, r, width, height, mi=0, seg=4):
        """cylinder, axis along Y"""
        n = seg
        V = []
        F = []

        def ring(yoff):
            idx = []
            for k in range(n):
                a = 2.0 * math.pi * k / n
                idx.append(len(V))
                V.append((cx + r * math.cos(a), cy + yoff, cz + r * math.sin(a)))
            return idx

        b = ring(-width / 2.0)
        t = ring(width / 2.0)
        for k in range(n):
            j = (k + 1) % n
            F.append((b[k], b[j], t[j], t[k]))
        # caps
        F.append(tuple(reversed(b)))
        F.append(tuple(t))
        self.add(V, F, mi)

    def tris(self):
        return sum(len(f) - 2 for f in self.f)


def mesh_object(name, mb, coll, hidden=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata(mb.v, [], mb.f)
    me.update()
    for mn in mb.mats:
        me.materials.append(ck.append_material(mn))
        MATS_USED.add(mn)
    for i, mi in enumerate(mb.m):
        if i < len(me.polygons):
            try:
                me.polygons[i].material_index = int(mi)
            except Exception:
                me.polygons[i].material_index = 0
    bm = bmesh.new()
    bm.from_mesh(me)
    if len(bm.faces):
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    if hidden:
        ob.hide_render = True
        ob.hide_viewport = True
    return ob


def inst(src, coll, name, loc, theta=0.0, s=1.0, elevated=False):
    ob = bpy.data.objects.new(name, src.data)
    ob.location = (float(loc[0]), float(loc[1]), float(loc[2]))
    ob.rotation_euler = (0.0, 0.0, float(theta))
    ob.scale = (float(s), float(s), float(s))
    if elevated:
        ob["elevated"] = True
        ob["elevated_z"] = DECK_Z
    coll.objects.link(ob)
    return ob


# --------------------------------------------------------------------------
# vehicle kit
# --------------------------------------------------------------------------
VEH_SRC = {}
KIT_TRIS = {}
KIT_ORDER = []


def build_kit():
    global VEH_SRC, KIT_TRIS, KIT_ORDER
    VEH_SRC = {}
    KIT_TRIS = {}
    KIT_ORDER = []
    mi_g = MATERIALS["glass"]
    mi_l = MATERIALS["light_warm"]
    mi_s = MATERIALS["steel"]
    mi_sign = MATERIALS["sign"]
    mi_red = MATERIALS["neon_red"]
    paint_of = lambda n: MATERIALS["paint"][PAINTS.index(n)]

    def sedan_shape(mb, L, W, body_h, cabin_len, cabin_h, body_z0, cabin_z0, wheel_r, paint_idx):
        mb.box(0.0, 0.0, body_z0 + body_h / 2.0, L, W, body_h, MATERIALS["paint"][paint_idx])
        mb.box(-L / 2.0 + 0.30 + cabin_len / 2.0, 0.0, cabin_z0 + cabin_h / 2.0,
              cabin_len, W - 0.12, cabin_h, mi_g)
        for sx in (-1.0, 1.0):
            for sy in (-1.0, 1.0):
                mb.cyl_y(sx * (L / 2.0 - 0.55), sy * (W / 2.0 - 0.14), wheel_r,
                         wheel_r, 2.0 * wheel_r, mi_s, seg=4)
        for sy in (-1.0, 1.0):
            mb.box(L / 2.0 - 0.02, sy * (W / 2.0 - 0.40), 0.95, 0.08, 0.34, 0.09, mi_l)
            mb.box(-L / 2.0 + 0.02, sy * (W / 2.0 - 0.40), 0.80, 0.08, 0.34, 0.07, mi_l)

    paint_current = ["metal_painted_charcoal"]
    paint_of_current = [MATERIALS["paint"][PAINTS.index(paint_current[0])]]

    def build_one(base, kind, L, W, body_h, cabin_len, cabin_h, body_z0, cabin_z0, wheel_r,
                  paint, extra=None, lod=False):
        mb = MB()
        paint_idx = PAINTS.index(paint)
        mb.box(0.0, 0.0, body_z0 + body_h / 2.0, L, W, body_h, MATERIALS["paint"][paint_idx])
        if cabin_len > 0:
            mb.box(-L / 2.0 + 0.30 + cabin_len / 2.0, 0.0, cabin_z0 + cabin_h / 2.0,
                  cabin_len, W - 0.12, cabin_h, mi_g)
        for sx in (-1.0, 1.0):
            for sy in (-1.0, 1.0):
                mb.cyl_y(sx * (L / 2.0 - 0.55), sy * (W / 2.0 - 0.14), wheel_r,
                         wheel_r, 2.0 * wheel_r, mi_s, seg=4)
        for sy in (-1.0, 1.0):
            mb.box(L / 2.0 - 0.02, sy * (W / 2.0 - 0.40), 0.95, 0.08, 0.34, 0.09, mi_l)
            mb.box(-L / 2.0 + 0.02, sy * (W / 2.0 - 0.40), 0.80, 0.08, 0.34, 0.07, mi_l)
        if extra:
            extra(mb)
        nm = ("LOD1_" if lod else "SM_") + base + "_01"
        ob = mesh_object(nm, mb, C_MESH)
        if lod:
            ob.hide_render = True
            ob.hide_viewport = True
        key = base if lod else ("SM_" + base)
        if not lod:
            VEH_SRC[base] = ob
        else:
            VEH_SRC[base + "_LOD"] = ob
        KIT_TRIS[nm] = ck.tri_count(ob)
        KIT_ORDER.append(nm)
        return nm

    # sedans
    build_one("Sedan_01", "sedan", 4.4, 1.7, 1.45, 1.75, 0.80, 0.12, 0.55, 0.33,
              "metal_painted_charcoal")
    build_one("Sedan_02", "sedan", 4.9, 1.75, 1.50, 1.80, 0.85, 0.12, 0.55, 0.34,
              "metal_painted_navy")
    # hatchback / suv / taxi / police / ambulance
    build_one("Hatchback", "hatch", 3.9, 1.55, 1.35, 1.45, 0.75, 0.12, 0.50, 0.30,
              "metal_painted_sand")
    build_one("SUV", "suv", 4.6, 1.95, 1.80, 2.00, 1.05, 0.12, 0.55, 0.38,
              "metal_painted_teal")
    def taxi_extra(mb):
        mb.box(0.0, 0.0, 1.78, 1.10, 0.55, 0.14, mi_sign)
    build_one("Taxi", "taxi", 4.3, 1.70, 1.45, 1.70, 0.80, 0.12, 0.55, 0.33,
              "metal_painted_mustard", extra=taxi_extra)
    def police_extra(mb):
        mb.box(0.0, 0.0, 1.72, 1.80, 0.16, 0.30, mi_red)
    build_one("Police", "police", 4.4, 1.70, 1.50, 1.75, 0.85, 0.12, 0.55, 0.33,
              "metal_painted_charcoal", extra=police_extra)
    build_one("Ambulance", "amb", 5.0, 1.80, 2.00, 1.80, 1.70, 0.12, 0.95, 0.38,
              "metal_painted_oxblood")

    # van
    mb = MB()
    mb.box(0.0, 0.0, 0.12 + 2.20 / 2.0, 5.0, 1.8, 2.20, MATERIALS["paint"][PAINTS.index("metal_painted_sand")])
    mb.box(5.0 / 2.0 - 0.85, 0.0, 0.12 + 1.80 / 2.0, 1.7, 1.7, 1.80, MATERIALS["paint"][PAINTS.index("metal_painted_sand")])
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            mb.cyl_y(sx * (5.0 / 2.0 - 0.85), sy * 0.85, 0.40, 0.40, 0.80, mi_s, seg=4)
    ob = mesh_object("SM_Van_01", mb, C_MESH)
    VEH_SRC["Van"] = ob
    KIT_TRIS["SM_Van_01"] = ck.tri_count(ob)
    KIT_ORDER.append("SM_Van_01")

    # box truck
    mb = MB()
    mb.box(7.5 / 2.0 - 1.075, 0.0, 0.12 + 2.30 / 2.0, 2.15, 2.2, 2.30, MATERIALS["paint"][PAINTS.index("metal_painted_dark")])
    mb.box(-7.5 / 2.0 + 1.75, 0.0, 0.12 + 2.50 / 2.0, 5.3, 2.2, 2.50, MATERIALS["paint"][PAINTS.index("metal_painted_dark")])
    for sx in (2.9, -2.9):
        for sy in (-1.0, 1.0):
            mb.cyl_y(sx, sy * 0.875, 0.45, 0.45, 0.90, mi_s, seg=4)
    ob = mesh_object("SM_BoxTruck_01", mb, C_MESH)
    VEH_SRC["BoxTruck"] = ob
    KIT_TRIS["SM_BoxTruck_01"] = ck.tri_count(ob)
    KIT_ORDER.append("SM_BoxTruck_01")
    ob = mesh_object("LOD1_SM_BoxTruck_01", mb, C_MESH)
    ob.hide_render = True
    ob.hide_viewport = True

    # city bus
    mb = MB()
    mb.box(0.0, 0.0, 0.12 + 2.50 / 2.0, 12.0, 2.6, 2.50, MATERIALS["paint"][PAINTS.index("metal_painted_teal")])
    mb.box(-3.0, 0.0, 0.12 + 2.20 / 2.0, 3.0, 2.4, 2.20, mi_g)
    for sx in (4.5, -4.5):
        for sy in (-1.0, 1.0):
            mb.cyl_y(sx, sy * 1.1, 0.55, 0.55, 1.10, mi_s, seg=6)
    ob = mesh_object("SM_Bus_01", mb, C_MESH)
    VEH_SRC["Bus"] = ob
    KIT_TRIS["SM_Bus_01"] = ck.tri_count(ob)
    KIT_ORDER.append("SM_Bus_01")
    ob = mesh_object("LOD1_SM_Bus_01", mb, C_MESH)
    ob.hide_render = True
    ob.hide_viewport = True

    # coach
    mb = MB()
    mb.box(0.0, 0.0, 0.12 + 2.90 / 2.0, 11.5, 2.4, 2.90, MATERIALS["paint"][PAINTS.index("metal_painted_bone")])
    mb.box(-3.25, 0.0, 0.12 + 2.60 / 2.0, 3.0, 2.2, 2.60, mi_g)
    for sx in (4.5, -4.5):
        for sy in (-1.0, 1.0):
            mb.cyl_y(sx, sy * 0.95, 0.55, 0.55, 1.10, mi_s, seg=6)
    ob = mesh_object("SM_Coach_01", mb, C_MESH)
    VEH_SRC["Coach"] = ob
    KIT_TRIS["SM_Coach_01"] = ck.tri_count(ob)
    KIT_ORDER.append("SM_Coach_01")

    # motorcycle
    mb = MB()
    mb.box(0.0, 0.0, 0.85, 0.55, 0.45, 0.30, MATERIALS["paint"][PAINTS.index("metal_painted_sage")])
    for sx in (-0.65, 0.65):
        for sy in (-0.35, 0.35):
            mb.cyl_y(sx, sy, 0.50, 0.50, 1.00, mi_s, seg=4)
    ob = mesh_object("SM_Motorcycle_01", mb, C_MESH)
    VEH_SRC["Motorcycle"] = ob
    KIT_TRIS["SM_Motorcycle_01"] = ck.tri_count(ob)
    KIT_ORDER.append("SM_Motorcycle_01")

    # bicycle
    mb = MB()
    mb.box(0.0, 0.0, 0.75, 0.85, 0.30, 0.10, MATERIALS["paint"][PAINTS.index("metal_painted_charcoal")])
    for sx in (-0.62, 0.62):
        mb.cyl_y(sx, 0.0, 0.35, 0.35, 0.70, mi_s, seg=4)
    ob = mesh_object("SM_Bicycle_01", mb, C_MESH)
    VEH_SRC["Bicycle"] = ob
    KIT_TRIS["SM_Bicycle_01"] = ck.tri_count(ob)
    KIT_ORDER.append("SM_Bicycle_01")

    return VEH_SRC, KIT_TRIS, KIT_ORDER


# --------------------------------------------------------------------------
# layout / forbidden zones
# --------------------------------------------------------------------------
LAYOUT = ck.read_layout()
NODES = {n["id"]: n for n in LAYOUT["road_nodes"]}
NODE_POS = {k: (float(v["pos"][0]), float(v["pos"][1]), float(v["pos"][2])) for k, v in NODES.items()}
EDGES = ck.read_road_edges()
TL_NODES = {t["node"]: t for t in (LAYOUT.get("traffic_lights") or [])}
TRACK_CP = [tuple(p) for p in ((LAYOUT.get("track") or {}).get("control_points") or [])]
LAKE_POLY = [tuple(p) for p in ((LAYOUT.get("water") or [{}])[0].get("polygon") or [])]


def _norm(x0, y0, x1, y1):
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


STADIUM = [_norm(*r) for r in STADIUM_RECTS]
LAKE_BB = _norm(*LAKE_BBOX)
NODE_COORDS = [(v[0], v[1]) for v in NODE_POS.values()]


def in_stadium(x, y):
    for (x0, y0, x1, y1) in STADIUM:
        if x0 <= x <= x1 and y0 <= y <= y1:
            return True
    return False


def in_lake(x, y):
    x0, y0, x1, y1 = LAKE_BB
    return x0 <= x <= x1 and y0 <= y <= y1


def near_track(x, y):
    if not (TRACK_ZMIN <= x <= 1188.0 and TRACK_ZMIN <= y <= TRACK_ZMAX):
        return False
    for p in TRACK_CP:
        try:
            px, py = p[0], p[1]
        except Exception:
            continue
        if math.hypot(x - px, y - py) < TRACK_MARGIN:
            return True
    return False


def forbidden(x, y):
    if in_stadium(x, y) or in_lake(x, y) or near_track(x, y):
        return True
    return False


def near_node(x, y, m=10.0):
    for (nx, ny) in NODE_COORDS:
        if math.hypot(x - nx, y - ny) < m:
            return True
    return False


# --------------------------------------------------------------------------
# collections
# --------------------------------------------------------------------------
TOP = None
C_MESH = None
C_COLL = None
C_LIGHT = None


def setup():
    global TOP, C_MESH, C_COLL, C_LIGHT
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    for me in list(bpy.data.meshes):
        if me.users == 0:
            bpy.data.meshes.remove(me)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    TOP = ck.ensure_collection("Traffic")
    C_MESH = ck.ensure_collection("Meshes", TOP)
    C_COLL = ck.ensure_collection("Colliders", TOP)
    C_LIGHT = ck.ensure_collection("Lights", TOP)


# --------------------------------------------------------------------------
# placement
# --------------------------------------------------------------------------
N_INST = 0
ELEV_PLACED = []
SKIPPED = []
COUNTS_BY_TYPE = {}


def place_vehicle(base_key, x, y, z, theta, lat, elevated=False, kind=None):
    global N_INST
    src = VEH_SRC.get(base_key)
    if src is None:
        return False
    ob = inst(src, C_MESH, "%s_%05d" % (src.name, N_INST), (x, y, z), theta, 1.0, elevated)
    N_INST += 1
    if kind:
        COUNTS_BY_TYPE[kind] = COUNTS_BY_TYPE.get(kind, 0) + 1
    if elevated:
        ELEV_PLACED.append((src.name, ob))
    return True


MOVING_TYPES = ["Sedan_01", "Sedan_02", "Hatchback", "SUV", "Taxi", "Police",
                "Van", "BoxTruck", "Bus", "Coach", "Rickshaw", "Ambulance", "Motorcycle"]
PARKED_TYPES = ["Sedan_01", "Sedan_02", "Hatchback", "SUV", "Van", "Bus", "Coach"]


def pick_moving_type():
    r = RND.random()
    if r < 0.26: return "Sedan_01"
    if r < 0.46: return "Sedan_02"
    if r < 0.62: return "Hatchback"
    if r < 0.75: return "SUV"
    if r < 0.82: return "Taxi"
    if r < 0.87: return "Police"
    if r < 0.92: return "Van"
    if r < 0.94: return "BoxTruck"
    if r < 0.96: return "Bus"
    if r < 0.97: return "Coach"
    if r < 0.98: return "Rickshaw"
    if r < 0.99: return "Ambulance"
    return "Motorcycle"


def pick_parked_type():
    r = RND.random()
    if r < 0.34: return "Sedan_01"
    if r < 0.56: return "Sedan_02"
    if r < 0.76: return "Hatchback"
    if r < 0.90: return "SUV"
    if r < 0.95: return "Van"
    if r < 0.98: return "Bus"
    return "Coach"


def build_traffic():
    placed_moved = 0
    placed_parked = 0
    placed_van = 0
    placed_queue = 0
    for e in EDGES:
        h = e.get("hierarchy")
        a = NODE_POS[e["a"]]
        b = NODE_POS[e["b"]]
        dx, dy = b[0] - a[0], b[1] - a[1]
        Lg = math.hypot(dx, dy)
        if Lg < 3.5:
            continue
        th = math.atan2(dy, dx)
        ux, uy = math.cos(th), math.sin(th)
        z = DECK_Z if (e.get("elevated") and e["id"] in ELEV_IDS) else 0.0
        width = float(e.get("width") or 12.0)
        half = width / 2.0
        base_lat = half - LANE_W / 2.0          # = width/2 - 1.75  (lane centre)
        lanes = int(e.get("lanes_each_way") or 1)
        lats = [base_lat + 3.5 * i for i in range(-(lanes - 1), 1)]
        lats = [l for l in lats if abs(l) <= half - 0.4]

        if h == "alley":
            # pedestrian-first: rare delivery van (~1 per 60 m), else none
            n = max(0, int(Lg / 60.0))
            for k in range(n):
                d = Lg * (k + 0.5) / (n + 1) if n else 0.0
                lat = RND.uniform(-0.6, 0.6)
                x = a[0] + ux * d + lat * math.sin(th)
                y = a[1] + uy * d - lat * math.cos(th)
                if forbidden(x, y) or near_node(x, y, 9.0):
                    SKIPPED.append(("alley", e["id"], round(x, 1), round(y, 1)))
                    continue
                place_vehicle("Van", x, y, z, th, lat, False, "Van")
                placed_van += 1
            continue

        # ---- moving traffic -------------------------------------------------
        if h == "highway":
            sp = 60.0
        elif h == "interchange_ramp":
            sp = 40.0
        elif h == "arterial":
            mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
            sp = 25.0 if (abs(mx) < 400.0 and abs(my) < 400.0) else 45.0
        else:
            sp = 55.0
        n = max(0, int(Lg / sp))
        for k in range(n):
            d = Lg * (k + 0.5) / (n + 1) if n else 0.0
            th2 = th + RND.uniform(-2.0, 2.0)
            u2x, u2y = math.cos(th2), math.sin(th2)
            lat = lats[min(int((k * lanes) / max(n, 1)), len(lats) - 1)] + RND.uniform(-0.15, 0.15)
            x = a[0] + u2x * d + lat * math.sin(th2)
            y = a[1] + u2y * d - lat * math.cos(th2)
            if forbidden(x, y) or near_node(x, y, 9.0):
                SKIPPED.append((e["id"], round(x, 1), round(y, 1)))
                continue
            place_vehicle(pick_moving_type(), x, y, z, th2, lat, z > 0.0)
            placed_moved += 1

        # ---- parked cars at kerb (street hierarchy) -------------------------
        if h == "street":
            pn = max(1, int(Lg / 7.0))
            for k in range(pn):
                d = Lg * k / 7.0 + RND.uniform(0.0, 2.5)
                th2 = th
                lat = PARKED_OFFSET if (k % 2 == 0) else -PARKED_OFFSET
                x = a[0] + math.cos(th2) * d + lat * math.sin(th2)
                y = a[1] + math.sin(th2) * d - lat * math.cos(th2)
                if forbidden(x, y) or near_node(x, y, 9.0):
                    SKIPPED.append(("parked", e["id"], round(x, 1), round(y, 1)))
                    continue
                place_vehicle(pick_parked_type(), x, y, 0.0, th2, lat, False, None)
                placed_parked += 1

    # ---- queues at traffic-light nodes ------------------------------------
    for tid in sorted(TL_NODES):
        node_id = TL_NODES[tid].get("node") or tid
        npos = NODE_POS.get(node_id)
        if npos is None:
            continue
        for e in EDGES:
            if e["a"] != node_id and e["b"] != node_id:
                continue
            other = e["b"] if e["a"] == node_id else e["a"]
            o = NODE_POS.get(other)
            if o is None:
                continue
            dx, dy = npos[0] - o[0], npos[1] - o[1]
            Lg = math.hypot(dx, dy)
            if Lg < 3.5:
                continue
            th = math.atan2(dy, dx)
            if e.get("elevated") and e["id"] in ELEV_IDS:
                continue
            width = float(e.get("width") or 12.0)
            base_lat = width / 2.0 - LANE_W / 2.0
            q = 1 + int(RND.random() * 3)
            stop = min(Lg * 0.2, 12.0)
            for i in range(q):
                d = stop + i * 3.2
                x = npos[0] - math.cos(th) * d + base_lat * math.sin(th)
                y = npos[1] - math.sin(th) * d - base_lat * math.cos(th)
                if forbidden(x, y) or near_node(x, y, 9.0):
                    SKIPPED.append(("queue", node_id, round(x, 1), round(y, 1)))
                    continue
                place_vehicle(pick_moving_type(), x, y, 0.0, th, base_lat, False, None)
                placed_queue += 1

    print("[traffic] placed: moved=%d parked=%d van=%d queue=%d total_inst=%d"
          % (placed_moved, placed_parked, placed_van, placed_queue, N_INST))


# --------------------------------------------------------------------------
# colliders / lights
# --------------------------------------------------------------------------
def build_colliders():
    made = []
    for base, src in sorted(VEH_SRC.items(), key=lambda kv: kv[0]):
        me = src.data
        if not len(me.vertices):
            continue
        xs = [v.co[0] for v in me.vertices]
        ys = [v.co[1] for v in me.vertices]
        zs = [v.co[2] for v in me.vertices]
        mb = MB()
        mb.box((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0, (min(zs) + max(zs)) / 2.0,
               max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 0)
        nm = "COL_traffic_%s" % base
        ob = mesh_object(nm, mb, C_COLL)
        ob.hide_render = True
        ob.hide_viewport = True
        made.append((nm, ob))
    return made


def add_lights():
    for nm, loc, energy, col in (
            ("LT_traffic_01", (60.0, 260.0, 5.0), 200.0, (1.0, 0.9, 0.8)),
            ("LT_traffic_02", (-260.0, -260.0, 5.0), 180.0, (0.8, 0.88, 1.0))):
        ld = bpy.data.lights.new(nm, type="POINT")
        ld.energy = energy
        ld.color = col
        ob = bpy.data.objects.new(nm, ld)
        ob.location = loc
        C_LIGHT.objects.link(ob)
    return 2


# --------------------------------------------------------------------------
# previews
# --------------------------------------------------------------------------
def preview_ground():
    ext = 1200.0
    step = 30.0
    n = int(2 * ext / step)
    mb = MB()
    V = []
    for j in range(n + 1):
        y = -ext + j * step
        for i in range(n + 1):
            V.append((-ext + i * step, y, -0.05))
    F = []
    for j in range(n):
        for i in range(n):
            a = j * (n + 1) + i
            F.append((a, a + 1, a + n + 2, a + n + 1))
    mb.v = V
    mb.f = F
    mb.m = [0] * len(F)
    ob = mesh_object("TMP_PREVIEW_GROUND", mb, C_MESH)
    ck.assign(ob, "asphalt")
    return ob


def previews():
    tmp = preview_ground()
    ck.make_preview(PREV_A, cam_pos=(150.0, -360.0, 290.0), cam_target=(0.0, -40.0, 0.0),
                    engine="BLENDER_EEVEE", res=(1920, 1080), sun_elev=45.0, sun_azim=-30.0, samples=32)
    ck.make_preview(PREV_B, cam_pos=(750.0, 150.0, 1.6), cam_target=(750.0, 420.0, 2.5),
                    engine="BLENDER_EEVEE", res=(1920, 1080), sun_elev=50.0, sun_azim=-90.0, samples=32)
    bpy.data.objects.remove(tmp, do_unlink=True)


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------
def write_md(payload, unique, total, elapsed):
    lines = []
    lines.append("# Traffic module report\n")
    lines.append("Generated by `modules/traffic.py` (headless, EEVEE).\n")
    lines.append("## Files\n")
    lines.append("- script: `%s`\n" % os.path.abspath(__file__))
    lines.append("- blend: `%s`\n" % OUT_BLEND)
    lines.append("- previews: `%s`, `%s`\n" % (PREV_A, PREV_B))
    lines.append("- instances: %d (linked duplicates of %d kit sources)\n" % (N_INST, len(VEH_SRC)))
    lines.append("\n## Geometry\n")
    lines.append("| kit source | tris |\n|---|---|")
    for nm in sorted(KIT_TRIS):
        lines.append("| %s | %d |\n" % (nm, KIT_TRIS[nm]))
    lines.append("\n## Vehicles placed\n")
    lines.append("| type | instances |\n|---|---|")
    for k in sorted(COUNTS_BY_TYPE):
        lines.append("| %s | %d |\n" % (k, COUNTS_BY_TYPE[k]))
    lines.append("\n## Elevated traffic\n")
    lines.append("elevated instances (deck top z=%.1f): %d -> %s\n"
                 % (DECK_Z, len(ELEV_PLACED), ", ".join(sorted({e[0] for e in ELEV_PLACED}))))
    lines.append("\n## Density / skipped\n")
    lines.append("- skipped placements (stadium / lake / track / junction): %d\n" % len(SKIPPED))
    lines.append("- skipped sample: %s\n" % (SKIPPED[:12],))
    lines.append("\n## Materials used (%d)\n" % len(MATS_USED))
    lines.append("`%s`\n" % "`, `".join(sorted(MATS_USED)))
    lines.append("\n## Known issues / requests\n")
    for i in ISSUES:
        lines.append("- %s\n" % i)
    lines.append("* **requested from Materials agent**: nothing new was needed "
                 "(all paints / glass / emissive / sign / steel / col_placeholder exist in materials.blend).\n")
    lines.append("\n## Report data\n")
    lines.append("- objects: %d\n" % len(bpy.data.objects))
    lines.append("- triangles unique: %d\n" % unique)
    lines.append("- triangles instanced (expanded): %d\n" % total)
    lines.append("- build seconds: %.1f\n" % elapsed)
    with open(REPORT_MD, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("[traffic] md report ->", REPORT_MD)
    return lines


N_KIT_COUNTS = {}


def stage(name):
    dt = time.time() - T0
    print("[traffic] STAGE %-12s t=%6.1fs objects=%d" % (name, dt, len(bpy.data.objects)))
    ck.save_blend(OUT_BLEND)


def main():
    global ISSUES
    ISSUES = []
    setup()
    build_kit()
    stage("kit")
    build_traffic()
    stage("vehicles")
    colls = build_colliders()
    stage("colliders")
    n_lights = add_lights()
    stage("lights")

    unique = ck.scene_tri_count()
    seen = {}
    for o in bpy.data.objects:
        d = getattr(o, "data", None)
        if d is None:
            continue
        p = d.as_pointer()
        if p not in seen:
            seen[p] = [ck.tri_count(o), 0]
        seen[p][1] += 1
    total = sum(t * c for t, c in seen.values())

    ck.update_view()
    ck.save_blend(OUT_BLEND)

    previews()

    ck.update_view()
    ck.save_blend(OUT_BLEND)

    payload = {
        "module": "traffic",
        "blend": OUT_BLEND,
        "previews": [PREV_A, PREV_B],
        "collections": ["Traffic", "Traffic/Meshes", "Traffic/Colliders", "Traffic/Lights"],
        "objects": len(bpy.data.objects),
        "instances": N_INST,
        "kit_sources": len(VEH_SRC),
        "tris_unique": unique,
        "tris_instanced": total,
        "budget_6M_ok": total <= 6_000_000,
        "elevated_instances": len(ELEV_PLACED),
        "elevated_detail": sorted({e[0] for e in ELEV_PLACED}),
        "density": {
            "highway_m_per_dir": 60.0,
            "arterial_m": 45.0,
            "arterial_downtown_m": 25.0,
            "street_m": 55.0,
            "alley_delivery_m": 60.0,
            "parked_m": 7.0,
        },
        "skipped": len(SKIPPED),
        "skipped_sample": SKIPPED[:20],
        "counts_by_type": dict(COUNTS_BY_TYPE),
        "materials_used": sorted(MATS_USED),
        "kit_tris": {k: v for k, v in sorted(KIT_TRIS.items())},
        "kit_source_count": len(KIT_TRIS),
        "issues": list(ISSUES),
        "needed_from_others": [
            "Roads: street/curb geometry (curb height 0.15, sidewalk 2.5) the cars park against.",
            "Flyover: deck top z=8.0 for elevated traffic on H_07/H_08 (custom prop elevated set).",
            "Assembler: keep ground traffic clear of flyover service-road bands.",
        ],
        "build_seconds": round(time.time() - T0, 1),
    }
    ck.write_report("traffic", payload)
    write_md(payload, unique, total, payload["build_seconds"])
    print("[traffic] DONE instances=%d tris_unique=%d tris_instanced=%d elevated=%d"
          % (N_INST, unique, total, len(ELEV_PLACED)))


if __name__ == "__main__":
    main()
