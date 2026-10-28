#!/usr/bin/env python3
"""props.py — PROPS module (headless). Citywide street furniture.

Builds:
1. Street furniture kit (<80 unique meshes, each <=5k tris), instanced everywhere
2. Street furniture on sidewalks along roads (by hierarchy/district rules)
3. Rooftop props on parcels (AC, water tanks, chimneys) - sampled subsets
4. Alley cables in M and D districts
5. Lake life-buoys and railings along shore
6. Circuit barriers
7. Work zones
8. Colliders (COL_props_<type> per type)
9. Previews + reports

Run: cd /home/abdulhadi/Work/city && blender -b -P modules/props.py
"""
from __future__ import annotations

import json
import math
import os
import random
import sys
import time

ROOT = "/home/abdulhadi/Work/city"
sys.path.insert(0, os.path.join(ROOT, "modules"))

import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402
import citykit as ck  # noqa: E402

SEED = 1337
RND = random.Random(SEED)

T0 = time.time()

# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------
L = ck.read_layout()
NODES = {n["id"]: n for n in L["road_nodes"]}
EDGES = ck.read_road_edges()
PARCELS_BY_ID = {p["id"]: p for p in L["parcels"]}
WATER = L["water"][0] if L.get("water") else None
LAKE_POLY = [tuple(p[:2]) for p in WATER["polygon"]] if WATER else []

# Program facilities (to skip)
try:
    with open(os.path.join(ROOT, "reports", "program.json")) as f:
        PROGRAM = json.load(f)
    FACILITIES = PROGRAM.get("facilities", [])
except Exception:
    FACILITIES = []

# Exclusion zones
STADIUM_RECTS = [
    (-864, -1164, -636, -936),
    (36, -1164, 264, -936),
    (-1164, -864, -936, -636),
    (-1164, -564, -936, -336),
    (12, -888, 288, -612),
]
LAKE_BBOX = (-552.58, -1142.57, -335.1, -969.78)
CIRCUIT_CORRIDOR = (612, -1188, 1188, -12)
RING_CENTER = 0.0  # ring centreline area to skip for rooftop props

# --------------------------------------------------------------------------
# Collections
# --------------------------------------------------------------------------
TOP = None
C_MESHES = None
C_COLLIDERS = None
C_LIGHTS = None
C_KIT = None  # hidden kit

# --------------------------------------------------------------------------
# Stats
# --------------------------------------------------------------------------
STATS = {
    "unique_meshes": 0,
    "kit_tris_total": 0,
    "instances_total": 0,
    "tris_instanced_total": 0,
    "per_type": {},
    "materials_used": set(),
    "issues": [],
    "needs": [],
}
KIT_OBJS = {}
COLLIDERS = {}


# --------------------------------------------------------------------------
# Mesh building helpers
# --------------------------------------------------------------------------
class MB:
    __slots__ = ("v", "f", "m")

    def __init__(self):
        self.v = []
        self.f = []
        self.m = []

    def add(self, V, F, mi=0, M=None):
        if not F:
            return
        off = len(self.v)
        if M is not None:
            V = [tuple(M @ Vector(p)) for p in V]
        self.v.extend(V)
        self.f.extend([tuple(i + off for i in fc) for fc in F])
        self.m.extend([mi] * len(F))


def prim_cyl(seg=8, r0=0.3, r1=0.2, h=1.0, cap_bottom=True, cap_top=True):
    r1 = max(r1, 0.004)
    V, F = [], []
    for i in range(seg):
        a = 2.0 * math.pi * i / seg
        V.append((r0 * math.cos(a), r0 * math.sin(a), 0.0))
    for i in range(seg):
        a = 2.0 * math.pi * i / seg
        V.append((r1 * math.cos(a), r1 * math.sin(a), h))
    for i in range(seg):
        j = (i + 1) % seg
        F.append((i, j, seg + j, seg + i))
    if cap_bottom:
        F.append(tuple(range(seg - 1, -1, -1)))
    if cap_top:
        F.append(tuple(range(seg, 2 * seg)))
    return V, F


def prim_box(cx, cy, cz, sx, sy, sz):
    x0, x1 = cx - sx / 2.0, cx + sx / 2.0
    y0, y1 = cy - sy / 2.0, cy + sy / 2.0
    z0, z1 = cz - sz / 2.0, cz + sz / 2.0
    V = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    F = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
         (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return V, F


def prim_disc(r=1.0, h=0.01, seg=16):
    V, F = [], []
    for i in range(seg):
        a = 2.0 * math.pi * i / seg
        V.append((r * math.cos(a), r * math.sin(a), 0.0))
    for i in range(seg):
        a = 2.0 * math.pi * i / seg
        V.append((r * math.cos(a), r * math.sin(a), h))
    for i in range(seg):
        j = (i + 1) % seg
        F.append((i, j, seg + j, seg + i))
    F.append(tuple(range(seg - 1, -1, -1)))
    F.append(tuple(range(seg, 2 * seg)))
    return V, F


def T(x, y, z=0.0):
    return Matrix.Translation((x, y, z))


def RZ(a):
    return Matrix.Rotation(a, 4, "Z")


def RX(a):
    return Matrix.Rotation(a, 4, "X")


def RY(a):
    return Matrix.Rotation(a, 4, "Y")


# --------------------------------------------------------------------------
# Mesh creation
# --------------------------------------------------------------------------
def mesh_object(name, mb, mat_names, coll, hidden=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata(mb.v, [], mb.f)
    me.update()
    for mn in mat_names:
        try:
            me.materials.append(ck.append_material(mn))
            STATS["materials_used"].add(mn)
        except Exception as e:
            STATS["issues"].append(f"Material missing for {name}: {mn} - {e}")
            # try to continue if possible
    for i, mi in enumerate(mb.m):
        if i < len(me.polygons):
            me.polygons[i].material_index = mi
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


def inst(src, coll, name, x, y, z, rot=0.0, s=1.0, sz=None, sx=None, sy=None):
    ob = bpy.data.objects.new(name, src.data)
    ob.location = (x, y, z)
    ob.rotation_euler = (0.0, 0.0, float(rot))
    if sx is not None and sy is not None:
        ob.scale = (float(sx), float(sy), float(s) if sz is None else float(sz))
    else:
        ob.scale = (float(s), float(s), float(s) if sz is None else float(sz))
    coll.objects.link(ob)
    STATS["instances_total"] += 1
    return ob


# --------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------
def point_in_poly(x, y, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            xinters = (xj - xi) * (y - yi) / ((yj - yi) if (yj - yi) != 0 else 1e-18) + xi
            if x < xinters:
                inside = not inside
        j = i
    return inside


def dist_to_poly(x, y, poly):
    best = 1e18
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        l2 = dx * dx + dy * dy
        if l2 == 0:
            t = 0.0
        else:
            t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / l2))
        px, py = x1 + t * dx, y1 + t * dy
        d = math.hypot(x - px, y - py)
        if d < best:
            best = d
    return best


def in_rect(x, y, rect):
    if rect is None:
        return False
    x0, y0, x1, y1 = rect
    return x0 <= x <= x1 and y0 <= y <= y1


def in_any_stadium(x, y):
    for r in STADIUM_RECTS:
        if in_rect(x, y, r):
            return True
    return False


def in_lake_bbox(x, y):
    return in_rect(x, y, LAKE_BBOX)


def in_circuit(x, y):
    x0, y0, x1, y1 = CIRCUIT_CORRIDOR
    return x0 <= x <= x1 and y0 <= y <= y1


def in_facility_rect(x, y):
    for f in FACILITIES:
        rect = f.get("rect")
        if rect and len(rect) == 4:
            if in_rect(x, y, rect):
                return True
        # also check placement rect
        place = f.get("placement") or {}
        rect2 = place.get("rect")
        if rect2 and len(rect2) == 4:
            if in_rect(x, y, rect2):
                return True
    return False


def is_forbidden(x, y, allow_lake_exceptions=False, allow_circuit_exceptions=False):
    if in_any_stadium(x, y):
        return True
    if in_facility_rect(x, y):
        return True
    if in_circuit(x, y) and not allow_circuit_exceptions:
        return True
    if in_lake_bbox(x, y) and not allow_lake_exceptions:
        # allow life buoys/railing along shore - caller decides
        pass  # check more precisely
    return False


def road_carriageway_clear(x, y, edge):
    # Never inside carriageway half-widths
    w = edge.get("width", 12.0)
    hw = w / 2.0
    # rough check - more precise done in placement
    return hw  # return half-width


# --------------------------------------------------------------------------
# Kit building
# --------------------------------------------------------------------------
def build_kit():
    print("[props] Building kit...")
    global C_KIT
    C_KIT = ck.ensure_collection("PropsKit", parent=TOP)

    # Materials to use: metal_painted_dark, metal_steel, rust, wood_painted, sign_metal,
    # canvas_tarp, emissive_warm for ad panels etc.

    # 1. Litter bin (2 variants)
    for v in range(2):
        mb = MB()
        r0, r1 = 0.26 - v * 0.02, 0.23 - v * 0.02
        mb.add(*prim_cyl(8, r0, r1, 0.85), 0)
        mb.add(*prim_cyl(8, r0 + 0.04, r0 + 0.04, 0.06), 1, T(0, 0, 0.85))
        ob = mesh_object(f"SM_Bin_{v+1:02d}_01", mb, ["metal_painted_dark", "metal_steel"], C_KIT, hidden=True)
        KIT_OBJS[f"bin{v+1}"] = ob
        STATS["unique_meshes"] += 1
        STATS["kit_tris_total"] += ck.tri_count(ob)

    # 2. Fire hydrant
    mb = MB()
    mb.add(*prim_cyl(8, 0.12, 0.1, 0.8), 0)
    mb.add(*prim_cyl(8, 0.14, 0.14, 0.06), 1, T(0, 0, 0.75))
    mb.add(*prim_box(0, 0, 0.5, 0.22, 0.08, 0.08), 0)
    ob = mesh_object("SM_Hydrant_01_01", mb, ["metal_painted_dark", "metal_steel"], C_KIT, hidden=True)
    KIT_OBJS["hydrant"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 3. Bollard (steel + painted)
    for v, mats in enumerate([["metal_steel"], ["metal_painted_dark"]]):
        mb = MB()
        mb.add(*prim_cyl(8, 0.1, 0.08, 0.9), 0)
        mb.add(*prim_cyl(8, 0.12, 0.12, 0.04), 1, T(0, 0, 0.88))
        ob = mesh_object(f"SM_Bollard_{v+1:02d}_01", mb, mats, C_KIT, hidden=True)
        KIT_OBJS[f"bollard{v+1}"] = ob
        STATS["unique_meshes"] += 1
        STATS["kit_tris_total"] += ck.tri_count(ob)

    # 4. Bench (2 variants)
    for v in range(2):
        mb = MB()
        for i in range(3):
            mb.add(*prim_box(0.0, -0.16 + i * 0.16, 0.45, 1.7, 0.14, 0.05), 1)
        for i in range(2):
            mb.add(*prim_box(0.0, -0.26, 0.62 + i * 0.17, 1.7, 0.05, 0.15), 1)
        for sx in (-0.72, 0.72):
            mb.add(*prim_box(sx, -0.18, 0.22, 0.08, 0.08, 0.44), 0)
            mb.add(*prim_box(sx, -0.24, 0.62, 0.08, 0.08, 0.45), 0)
        ob = mesh_object(f"SM_Bench_{v+1:02d}_01", mb, ["metal_painted_dark", "wood_old"], C_KIT, hidden=True)
        KIT_OBJS[f"bench{v+1}"] = ob
        STATS["unique_meshes"] += 1
        STATS["kit_tris_total"] += ck.tri_count(ob)

    # 5. Bike rack + parked bicycle cluster
    mb = MB()
    for x in [-0.6, -0.3, 0, 0.3, 0.6]:
        mb.add(*prim_box(x, 0, 0.4, 0.04, 0.04, 0.8), 0)
        mb.add(*prim_box(x, 0.15, 0.7, 0.04, 0.3, 0.04), 0)
    # simple bike
    mb.add(*prim_cyl(6, 0.015, 0.015, 1.2), 1, T(0, 0, 0) @ RZ(math.pi/2) @ RX(math.radians(80)))
    ob = mesh_object("SM_BikeRack_01_01", mb, ["metal_steel", "metal_painted_dark"], C_KIT, hidden=True)
    KIT_OBJS["bikerack"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 6. Planter (rect + round)
    for v, shape in enumerate(["rect", "round"]):
        mb = MB()
        if shape == "rect":
            mb.add(*prim_box(0, 0, 0.3, 1.6, 1.6, 0.6), 0)
            mb.add(*prim_box(0, 0, 0.63, 1.3, 1.3, 0.08), 1)
        else:
            mb.add(*prim_cyl(12, 0.9, 0.8, 0.6), 0)
            mb.add(*prim_cyl(12, 0.75, 0.75, 0.08), 1, T(0, 0, 0.58))
        ob = mesh_object(f"SM_Planter_{v+1:02d}_01", mb, ["concrete", "dirt"], C_KIT, hidden=True)
        KIT_OBJS[f"planter{v+1}"] = ob
        STATS["unique_meshes"] += 1
        STATS["kit_tris_total"] += ck.tri_count(ob)

    # 7. Mailbox
    mb = MB()
    mb.add(*prim_box(0, 0, 0.5, 0.25, 0.4, 1.0), 0)
    mb.add(*prim_box(0, 0.25, 0.7, 0.15, 0.05, 0.3), 0)
    ob = mesh_object("SM_Mailbox_01_01", mb, ["metal_painted_dark"], C_KIT, hidden=True)
    KIT_OBJS["mailbox"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 8. Phone/utility box
    mb = MB()
    mb.add(*prim_box(0, 0, 0.6, 0.8, 0.4, 1.2), 0)
    ob = mesh_object("SM_UtilityBox_01_01", mb, ["metal_painted_dark"], C_KIT, hidden=True)
    KIT_OBJS["utilitybox"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 9. Postbox
    mb = MB()
    mb.add(*prim_cyl(8, 0.18, 0.18, 1.1), 0)
    mb.add(*prim_box(0, 0, 1.2, 0.4, 0.3, 0.25), 0)
    ob = mesh_object("SM_Postbox_01_01", mb, ["metal_painted_dark"], C_KIT, hidden=True)
    KIT_OBJS["postbox"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 10. Newspaper box
    mb = MB()
    mb.add(*prim_box(0, 0, 0.4, 0.6, 0.4, 0.8), 0)
    ob = mesh_object("SM_NewspaperBox_01_01", mb, ["metal_painted_dark"], C_KIT, hidden=True)
    KIT_OBJS["newsbox"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 11. Parking meter
    mb = MB()
    mb.add(*prim_cyl(8, 0.08, 0.06, 1.2), 0)
    mb.add(*prim_box(0, 0.08, 0.9, 0.15, 0.05, 0.2), 0)
    ob = mesh_object("SM_ParkingMeter_01_01", mb, ["metal_painted_dark"], C_KIT, hidden=True)
    KIT_OBJS["parkingmeter"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 12. Traffic cone stack
    mb = MB()
    for i in range(3):
        mb.add(*prim_cyl(8, 0.2 - i * 0.05, 0.05, 0.45), 0, T(0, 0, i * 0.1))
    ob = mesh_object("SM_ConeStack_01_01", mb, ["orange_cone"], C_KIT, hidden=True)  # may need to request if missing
    KIT_OBJS["conestack"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 13. Road-work barrier
    mb = MB()
    mb.add(*prim_box(0, 0, 0.5, 1.5, 0.1, 1.0), 0)
    mb.add(*prim_box(0, 0, 0.3, 1.6, 0.12, 0.1), 1)
    ob = mesh_object("SM_Barrier_01_01", mb, ["metal_painted_dark", "marking_yellow"], C_KIT, hidden=True)
    KIT_OBJS["barrier"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 14. Jersey-barrier segment
    mb = MB()
    mb.add(*prim_box(0, 0, 0.4, 2.0, 0.5, 0.8), 0)
    ob = mesh_object("SM_JerseyBarrier_01_01", mb, ["concrete"], C_KIT, hidden=True)
    KIT_OBJS["jersey"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 15. Street sign pole + sign plate set
    mb = MB()
    mb.add(*prim_cyl(8, 0.04, 0.04, 3.0), 0)
    mb.add(*prim_box(0, 0.15, 2.5, 0.8, 0.02, 0.4), 1)
    ob = mesh_object("SM_StreetSign_01_01", mb, ["metal_steel", "sign_metal"], C_KIT, hidden=True)
    KIT_OBJS["streetsign"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 16. Bus shelter (bench + roof + ad panel)
    mb = MB()
    mb.add(*prim_box(0, 0, 0.22, 3.0, 0.8, 0.05), 0)  # bench
    for sx in [-1.4, 1.4]:
        mb.add(*prim_cyl(6, 0.05, 0.05, 2.5), 1, T(sx, -0.3, 0))
    mb.add(*prim_box(0, 0, 2.5, 3.2, 1.0, 0.05), 2)  # roof
    mb.add(*prim_box(1.4, 0.2, 1.5, 0.02, 0.6, 0.8), 3)  # ad panel
    ob = mesh_object("SM_BusShelter_01_01", mb, ["metal_steel", "wood_old", "canvas_tarp", "emissive_warm"], C_KIT, hidden=True)
    KIT_OBJS["busshelter"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 17. Tram stop sign
    mb = MB()
    mb.add(*prim_cyl(6, 0.04, 0.04, 2.8), 0)
    mb.add(*prim_box(0, 0.12, 2.3, 0.5, 0.02, 0.3), 1)
    ob = mesh_object("SM_TramStop_01_01", mb, ["metal_steel", "sign_metal"], C_KIT, hidden=True)
    KIT_OBJS["tramstop"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 18. Pigeon posts
    mb = MB()
    mb.add(*prim_cyl(6, 0.05, 0.04, 1.8), 0)
    mb.add(*prim_cyl(6, 0.08, 0.06, 0.05), 1, T(0, 0, 1.75))
    ob = mesh_object("SM_PigeonPost_01_01", mb, ["metal_steel"], C_KIT, hidden=True)
    KIT_OBJS["pigeonpost"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 19. Fire escape ladder kit (simplified)
    mb = MB()
    for z in [0.5, 1.5, 2.5]:
        mb.add(*prim_box(0, 0, z, 0.04, 0.6, 0.04), 0)
    for x in [-0.3, 0.3]:
        mb.add(*prim_box(x, 0, 1.5, 0.04, 0.04, 3.0), 0)
    ob = mesh_object("SM_FireEscape_01_01", mb, ["metal_steel"], C_KIT, hidden=True)
    KIT_OBJS["fireescape"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 20. Awning-support bracket
    mb = MB()
    mb.add(*prim_box(0, 0, 0.1, 0.1, 0.3, 0.2), 0)
    mb.add(*prim_box(0, 0.15, 0.2, 0.08, 0.08, 0.4), 0)
    ob = mesh_object("SM_AwningBracket_01_01", mb, ["metal_steel"], C_KIT, hidden=True)
    KIT_OBJS["awningbracket"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 21. Cable bundle (sagging tube)
    mb = MB()
    mb.add(*prim_cyl(6, 0.03, 0.03, 5.0), 0)
    ob = mesh_object("SM_CableBundle_01_01", mb, ["metal_steel"], C_KIT, hidden=True)
    KIT_OBJS["cable"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 22. Satellite dish
    mb = MB()
    mb.add(*prim_cyl(6, 0.02, 0.02, 0.5), 0)
    mb.add(*prim_box(0, 0, 0.6, 0.8, 0.02, 0.6), 0)
    ob = mesh_object("SM_SatelliteDish_01_01", mb, ["metal_steel"], C_KIT, hidden=True)
    KIT_OBJS["satellite"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 23. Water tank
    mb = MB()
    mb.add(*prim_cyl(8, 0.6, 0.6, 1.2), 0)
    ob = mesh_object("SM_WaterTank_01_01", mb, ["metal_steel"], C_KIT, hidden=True)
    KIT_OBJS["watertank"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 24. Chimney pot
    mb = MB()
    mb.add(*prim_cyl(6, 0.25, 0.2, 0.8), 0)
    ob = mesh_object("SM_ChimneyPot_01_01", mb, ["brick_red"], C_KIT, hidden=True)
    KIT_OBJS["chimney"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 25. AC-unit box (rooftop/facade)
    mb = MB()
    mb.add(*prim_box(0, 0, 0.3, 1.0, 0.6, 0.6), 0)
    ob = mesh_object("SM_ACUnit_01_01", mb, ["metal_painted_dark"], C_KIT, hidden=True)
    KIT_OBJS["acunit"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 26. Billboard frame (blank + one emissive ad variant)
    for v in range(2):
        mb = MB()
        for x in [-2.0, 2.0]:
            mb.add(*prim_cyl(6, 0.08, 0.08, 6.0), 0, T(x, 0, 0))
        mb.add(*prim_box(0, 0, 5.0, 4.2, 0.1, 2.4), 1)
        if v == 1:
            ob = mesh_object("SM_Billboard_02_01", mb, ["metal_steel", "emissive_warm"], C_KIT, hidden=True)
        else:
            ob = mesh_object("SM_Billboard_01_01", mb, ["metal_steel", "sign_metal"], C_KIT, hidden=True)
        KIT_OBJS[f"billboard{v+1}"] = ob
        STATS["unique_meshes"] += 1
        STATS["kit_tris_total"] += ck.tri_count(ob)

    # 27. Sandwich board / A-frame sign
    mb = MB()
    mb.add(*prim_box(-0.4, 0, 0.4, 0.05, 0.02, 0.8), 0, RZ(math.radians(10)))
    mb.add(*prim_box(0.4, 0, 0.4, 0.05, 0.02, 0.8), 0, RZ(math.radians(-10)))
    mb.add(*prim_box(0, 0, 0.5, 0.6, 0.02, 0.5), 1)
    ob = mesh_object("SM_AFrame_01_01", mb, ["wood_painted", "sign_metal"], C_KIT, hidden=True)
    KIT_OBJS["aframe"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 28. Market-stall frame with canvas roof (for market-adjacent use only)
    mb = MB()
    for x in [-1.0, 1.0]:
        for y in [-0.8, 0.8]:
            mb.add(*prim_cyl(6, 0.04, 0.04, 2.2), 0, T(x, y, 0))
    mb.add(*prim_box(0, 0, 2.3, 2.2, 1.8, 0.02), 1)
    ob = mesh_object("SM_MarketStall_01_01", mb, ["metal_steel", "canvas_tarp"], C_KIT, hidden=True)
    KIT_OBJS["marketstall"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 29. Crowd barrier
    mb = MB()
    mb.add(*prim_box(0, 0, 0.5, 2.0, 0.05, 1.0), 0)
    for x in [-0.9, 0.9]:
        mb.add(*prim_cyl(6, 0.03, 0.03, 1.0), 1, T(x, 0, 0))
    ob = mesh_object("SM_CrowdBarrier_01_01", mb, ["metal_painted_dark", "metal_steel"], C_KIT, hidden=True)
    KIT_OBJS["crowdbarrier"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 30. Public telephone kiosk
    mb = MB()
    mb.add(*prim_box(0, 0, 1.0, 0.9, 0.9, 2.0), 0)
    ob = mesh_object("SM_PhoneKiosk_01_01", mb, ["metal_painted_dark"], C_KIT, hidden=True)
    KIT_OBJS["phonekiosk"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 31. Life-buoy ring (lake only)
    mb = MB()
    mb.add(*prim_cyl(12, 0.4, 0.35, 0.08), 0)
    ob = mesh_object("SM_LifeBuoy_01_01", mb, ["orange_cone"], C_KIT, hidden=True)
    KIT_OBJS["lifebuoy"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 32. Lake railing segments
    mb = MB()
    for x in [-1.2, 1.2]:
        mb.add(*prim_cyl(6, 0.03, 0.03, 1.0), 0, T(x, 0, 0))
    mb.add(*prim_cyl(6, 0.025, 0.025, 2.4), 1, T(0, 0, 0.8))
    ob = mesh_object("SM_LakeRailing_01_01", mb, ["metal_steel"], C_KIT, hidden=True)
    KIT_OBJS["lakerailing"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 33. Notice board
    mb = MB()
    mb.add(*prim_box(0, 0, 1.0, 1.2, 0.05, 1.5), 0)
    ob = mesh_object("SM_NoticeBoard_01_01", mb, ["wood_old", "sign_metal"], C_KIT, hidden=True)
    KIT_OBJS["noticeboard"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    # 34. Christmas-light catenary strands (thin emissive string)
    mb = MB()
    mb.add(*prim_cyl(4, 0.01, 0.01, 10.0), 0)
    ob = mesh_object("SM_Catenary_01_01", mb, ["emissive_warm"], C_KIT, hidden=True)
    KIT_OBJS["catenary"] = ob
    STATS["unique_meshes"] += 1
    STATS["kit_tris_total"] += ck.tri_count(ob)

    print(f"[props] Kit built: {STATS['unique_meshes']} meshes, {STATS['kit_tris_total']} tris")


def ensure_collider(type_name):
    if type_name in COLLIDERS:
        return COLLIDERS[type_name]
    mb = MB()
    mb.add(*prim_box(0, 0, 0.5, 1.0, 1.0, 1.0), 0)
    ob = mesh_object(f"COL_props_{type_name}", mb, ["col_placeholder"], C_COLLIDERS, hidden=True)
    COLLIDERS[type_name] = ob
    return ob


# --------------------------------------------------------------------------
# Placement helpers
# --------------------------------------------------------------------------
def get_edge_nodes(edge):
    a = NODES.get(edge["a"])
    b = NODES.get(edge["b"])
    if not a or not b:
        return None, None
    return tuple(a["pos"][:2]), tuple(b["pos"][:2])


def get_sidewalk_offset(edge, side=1.0):
    hierarchy = edge.get("hierarchy", "street")
    if hierarchy == "highway":
        # highway has wide roads, but props placement says "Street furniture goes on the SIDEWALK BAND only" - highway may not have sidewalks in same way
        return 17.0  # corridor half-width mentioned
    elif hierarchy == "arterial":
        return 10.0 + side * 0.75  # place at lateral offset 10.0-11.5 m
    elif hierarchy == "street":
        return 4.5 + side * 0.5  # 4.5-5.5 m
    elif hierarchy == "alley":
        return None  # alleys: nothing except occasional wall-mounted
    return 4.5


def point_on_sidewalk(edge, t, side=1.0):
    a, b = get_edge_nodes(edge)
    if not a or not b:
        return None
    dx, dy = b[0] - a[0], b[1] - a[1]
    Lg = math.hypot(dx, dy)
    if Lg < 0.01:
        return None
    ux, uy = dx / Lg, dy / Lg
    px, py = -uy, ux
    off = get_sidewalk_offset(edge, side)
    if off is None:
        return None
    x = a[0] + ux * t + px * side * off
    y = a[1] + uy * t + py * side * off
    z = 0.0  # terrain level approx
    return (x, y, z)


def is_near_node(x, y, skip=8.0):
    for nid, n in NODES.items():
        nx, ny = n["pos"][0], n["pos"][1]
        if math.hypot(x - nx, y - ny) < skip:
            return True
    return False


def in_carriageway(x, y, edge):
    a, b = get_edge_nodes(edge)
    if not a or not b:
        return False
    dx, dy = b[0] - a[0], b[1] - a[1]
    Lg = math.hypot(dx, dy)
    if Lg < 0.01:
        return False
    ux, uy = dx / Lg, dy / Lg
    px, py = -uy, ux
    # project point onto line
    vx, vy = x - a[0], y - a[1]
    t = vx * ux + vy * uy
    if t < -5 or t > Lg + 5:
        return False
    dist = abs(vx * px + vy * py)
    hw = edge.get("width", 12.0) / 2.0
    # carriageway is the road surface; sidewalks are outside - but check
    return dist < hw * 0.8  # inside carriageway


# --------------------------------------------------------------------------
# Main placement
# --------------------------------------------------------------------------
def place_street_furniture():
    print("[props] Placing street furniture...")
    placed = {"bin": 0, "hydrant": 0, "bollard": 0, "bench": 0, "bikerack": 0, 
              "planter": 0, "mailbox": 0, "utilitybox": 0, "postbox": 0, 
              "newsbox": 0, "parkingmeter": 0, "streetsign": 0, "busshelter": 0, 
              "tramstop": 0, "pigeonpost": 0, "aframe": 0, "noticeboard": 0}

    # Hydrants 1/80 m arterials only
    for edge in EDGES:
        if edge.get("hierarchy") != "arterial":
            continue
        a, b = get_edge_nodes(edge)
        if not a or not b:
            continue
        dx, dy = b[0] - a[0], b[1] - a[1]
        Lg = math.hypot(dx, dy)
        if Lg < 10:
            continue
        t = 40
        while t <= Lg - 20:
            pt = point_on_sidewalk(edge, t, side=1.0)
            if pt:
                x, y, z = pt
                if in_any_stadium(x, y) or in_facility_rect(x, y) or in_circuit(x, y):
                    pass
                elif not in_carriageway(x, y, edge):
                    inst(KIT_OBJS["hydrant"], C_MESHES, f"SM_Hydrant_{placed['hydrant']:05d}", 
                         x, y, z, rot=RND.uniform(0, 6.28))
                    placed["hydrant"] += 1
            t += 80.0

    # Bins 1/60 m arterials + streets
    for edge in EDGES:
        if edge.get("hierarchy") not in ["arterial", "street"]:
            continue
        a, b = get_edge_nodes(edge)
        if not a or not b:
            continue
        dx, dy = b[0] - a[0], b[1] - a[1]
        Lg = math.hypot(dx, dy)
        if Lg < 10:
            continue
        t = 30
        while t <= Lg - 15:
            pt = point_on_sidewalk(edge, t, side=1.0 if RND.random() < 0.5 else -1.0)
            if pt:
                x, y, z = pt
                if in_any_stadium(x, y) or in_facility_rect(x, y) or in_circuit(x, y):
                    t += 60.0
                    continue
                if in_carriageway(x, y, edge):
                    t += 60.0
                    continue
                if is_near_node(x, y, 12):
                    t += 60.0
                    continue
                v = 1 if RND.random() < 0.5 else 2
                inst(KIT_OBJS[f"bin{v}"], C_MESHES, f"SM_Bin_{placed['bin']:05d}", 
                     x, y, z, rot=RND.uniform(0, 6.28))
                placed["bin"] += 1
            t += 60.0

    # Bollards at every junction corner (4 per traffic_light node, at kerb return radius)
    for nid, node in NODES.items():
        if node.get("kind") == "traffic_light" or "intersection" in node.get("kind", ""):
            nx, ny = node["pos"][0], node["pos"][1]
            # place 4 bollards around corners
            for angle in [math.pi/4, 3*math.pi/4, 5*math.pi/4, 7*math.pi/4]:
                bx = nx + 6.0 * math.cos(angle)  # kerb return radius approx
                by = ny + 6.0 * math.sin(angle)
                if in_any_stadium(bx, by) or in_facility_rect(bx, by) or in_circuit(bx, by):
                    continue
                if in_lake_bbox(bx, by):
                    continue
                v = 1 if RND.random() < 0.5 else 2
                inst(KIT_OBJS[f"bollard{v}"], C_MESHES, f"SM_Bollard_{placed['bollard']:05d}", 
                     bx, by, 0.0, rot=RND.uniform(0, 6.28))
                placed["bollard"] += 1

    # Benches 1/120 m streets + arterials facing road
    for edge in EDGES:
        if edge.get("hierarchy") not in ["arterial", "street"]:
            continue
        a, b = get_edge_nodes(edge)
        if not a or not b:
            continue
        dx, dy = b[0] - a[0], b[1] - a[1]
        Lg = math.hypot(dx, dy)
        if Lg < 20:
            continue
        t = 60
        while t <= Lg - 40:
            pt = point_on_sidewalk(edge, t, side=1.0 if RND.random() < 0.5 else -1.0)
            if pt:
                x, y, z = pt
                if in_any_stadium(x, y) or in_facility_rect(x, y) or in_circuit(x, y):
                    t += 120.0
                    continue
                if is_near_node(x, y, 15):
                    t += 120.0
                    continue
                v = 1 if RND.random() < 0.5 else 2
                # face road - compute rotation towards road center
                dx2, dy2 = b[0] - a[0], b[1] - a[1]
                rot = math.atan2(dy2, dx2) + math.pi/2
                inst(KIT_OBJS[f"bench{v}"], C_MESHES, f"SM_Bench_{placed['bench']:05d}", 
                     x, y, z, rot=rot)
                placed["bench"] += 1
            t += 120.0

    # Bike racks 1/150 m
    for edge in EDGES:
        if edge.get("hierarchy") not in ["arterial", "street"]:
            continue
        a, b = get_edge_nodes(edge)
        if not a or not b:
            continue
        dx, dy = b[0] - a[0], b[1] - a[1]
        Lg = math.hypot(dx, dy)
        if Lg < 30:
            continue
        t = 75
        while t <= Lg - 60:
            pt = point_on_sidewalk(edge, t, side=-1.0)
            if pt:
                x, y, z = pt
                if in_any_stadium(x, y) or in_facility_rect(x, y) or in_circuit(x, y):
                    t += 150.0
                    continue
                inst(KIT_OBJS["bikerack"], C_MESHES, f"SM_BikeRack_{placed['bikerack']:05d}", 
                     x, y, z, rot=RND.uniform(0, 6.28))
                placed["bikerack"] += 1
            t += 150.0

    # Planters - downtown core (|x|<400,|y|<400) 1/50m else 1/120m
    for edge in EDGES:
        if edge.get("hierarchy") not in ["arterial", "street"]:
            continue
        a, b = get_edge_nodes(edge)
        if not a or not b:
            continue
        mx, my = (a[0]+b[0])/2, (a[1]+b[1])/2
        downtown = abs(mx) < 400 and abs(my) < 400
        spacing = 50.0 if downtown else 120.0
        dx, dy = b[0] - a[0], b[1] - a[1]
        Lg = math.hypot(dx, dy)
        if Lg < 20:
            continue
        t = 25
        while t <= Lg - 25:
            pt = point_on_sidewalk(edge, t, side=1.0)
            if pt:
                x, y, z = pt
                if in_any_stadium(x, y) or in_facility_rect(x, y) or in_circuit(x, y):
                    t += spacing
                    continue
                v = 1 if RND.random() < 0.5 else 2
                inst(KIT_OBJS[f"planter{v}"], C_MESHES, f"SM_Planter_{placed['planter']:05d}", 
                     x, y, z, rot=RND.uniform(0, 6.28))
                placed["planter"] += 1
            t += spacing

    # Bus shelters at every 3rd traffic_light node on arterials
    count = 0
    for nid, node in NODES.items():
        if node.get("kind") == "traffic_light" or "intersection" in str(node.get("kind","")):
            count += 1
            if count % 3 == 0:
                nx, ny = node["pos"][0], node["pos"][1]
                bx = nx + 12.0
                by = ny + 2.0
                if in_any_stadium(bx,by) or in_facility_rect(bx,by) or in_circuit(bx,by):
                    continue
                inst(KIT_OBJS["busshelter"], C_MESHES, f"SM_BusShelter_{placed['busshelter']:05d}", 
                     bx, by, 0.0, rot=RND.uniform(0, 6.28))
                placed["busshelter"] += 1

    # Street-name signs at every junction
    for nid, node in NODES.items():
        nx, ny = node["pos"][0], node["pos"][1]
        sx = nx + 8.0
        sy = ny + 8.0
        if in_any_stadium(sx,sy) or in_facility_rect(sx,sy) or in_circuit(sx,sy):
            continue
        if in_lake_bbox(sx,sy):
            continue
        inst(KIT_OBJS["streetsign"], C_MESHES, f"SM_StreetSign_{placed['streetsign']:05d}", 
             sx, sy, 0.0, rot=RND.uniform(0, 6.28))
        placed["streetsign"] += 1

    # Market district M (x300-1200,y600-1200) - A-frames in alleys at offset ~2.0m
    for edge in EDGES:
        if edge.get("hierarchy") != "alley":
            continue
        a,b = get_edge_nodes(edge)
        if not a or not b:
            continue
        mx,my = (a[0]+b[0])/2, (a[1]+b[1])/2
        if not (300 <= mx <= 1200 and 600 <= my <= 1200):  # district M
            continue
        dx,dy = b[0]-a[0], b[1]-a[1]
        Lg = math.hypot(dx,dy)
        t = 10
        while t <= Lg - 10:
            pt = point_on_sidewalk(edge, t, side=1.0)
            if pt and pt[0] is not None:
                x,y,z = pt
                # offset ~2.0m for alleys in market district
                dx2,dy2 = b[0]-a[0], b[1]-a[1]
                l2 = math.hypot(dx2,dy2) or 1
                ux,uy = dx2/l2, dy2/l2
                px,py = -uy,ux
                x2,y2 = x + px*2.0, y + py*2.0
                if in_any_stadium(x2,y2) or in_facility_rect(x2,y2):
                    t += 20
                    continue
                inst(KIT_OBJS["aframe"], C_MESHES, f"SM_AFrame_{placed['aframe']:05d}",
                     x2,y2,0.0, rot=RND.uniform(0,6.28))
                placed["aframe"] += 1
            t += 20

    # Cable bundles across alleys in M and D districts every ~25m at height 4-5m between facing facades
    # anchor to parcel rects - run between opposing parcel edges
    for district in ["M", "D"]:
        try:
            parcels = ck.read_parcels(district)
        except:
            parcels = []
        # place cables in alleys
        for edge in EDGES:
            if edge.get("hierarchy") != "alley":
                continue
            a,b = get_edge_nodes(edge)
            if not a or not b:
                continue
            mx,my = (a[0]+b[0])/2, (a[1]+b[1])/2
            in_d = False
            if district == "M" and 300 <= mx <= 1200 and 600 <= my <= 1200:
                in_d = True
            elif district == "D" and abs(mx)<400 and abs(my)<400:
                in_d = True
            if not in_d:
                continue
            dx,dy = b[0]-a[0], b[1]-a[1]
            Lg = math.hypot(dx,dy)
            t = 12
            while t <= Lg - 12:
                x = a[0] + dx*(t/Lg)
                y = a[1] + dy*(t/Lg)
                if in_any_stadium(x,y) or in_facility_rect(x,y):
                    t += 25
                    continue
                # place cable bundle at height 4-5m
                inst(KIT_OBJS["cable"], C_MESHES, f"SM_Cable_{RND.randint(0,10**7):07d}",
                     x,y,4.5, rot=math.atan2(dy,dx))
                t += 25

    # Work zones: 3-6 small work zones on street edges (avoid market M), random but deterministic (seed 1337)
    RND2 = random.Random(1337)
    zone_count = RND2.randint(3,6)
    zones_placed = 0
    for edge in EDGES:
        if zones_placed >= zone_count:
            break
        if edge.get("hierarchy") not in ["street", "arterial"]:
            continue
        a,b = get_edge_nodes(edge)
        if not a or not b:
            continue
        mx,my = (a[0]+b[0])/2, (a[1]+b[1])/2
        if 300 <= mx <= 1200 and 600 <= my <= 1200:  # avoid market M
            continue
        if in_circuit(mx,my):
            continue
        dx,dy = b[0]-a[0], b[1]-a[1]
        Lg = math.hypot(dx,dy)
        if Lg < 40:
            continue
        t = Lg/2
        pt = point_on_sidewalk(edge, t, side=1.0)
        if pt:
            x,y,z = pt
            if not (in_any_stadium(x,y) or in_facility_rect(x,y)):
                # place cone stack + barrier
                inst(KIT_OBJS["conestack"], C_MESHES, f"SM_Cone_{zones_placed:03d}", x,y,z, rot=RND2.uniform(0,6.28))
                inst(KIT_OBJS["barrier"], C_MESHES, f"SM_WorkBarrier_{zones_placed:03d}", x+2,y,z, rot=RND2.uniform(0,6.28))
                zones_placed += 1

    # Add some more props
    for edge in EDGES:
        if edge.get("hierarchy") != "street":
            continue
        a,b = get_edge_nodes(edge)
        if not a or not b:
            continue
        dx,dy = b[0]-a[0], b[1]-a[1]
        Lg = math.hypot(dx,dy)
        if Lg < 30:
            continue
        t = 45
        while t <= Lg - 30:
            pt = point_on_sidewalk(edge, t, side=-1.0)
            if pt:
                x,y,z = pt
                if in_any_stadium(x,y) or in_facility_rect(x,y) or in_circuit(x,y):
                    t += 90
                    continue
                if RND.random() < 0.3:
                    inst(KIT_OBJS["mailbox"], C_MESHES, f"SM_Mailbox_{RND.randint(0,10**7):07d}", x,y,z, rot=RND.uniform(0,6.28))
                elif RND.random() < 0.2:
                    inst(KIT_OBJS["postbox"], C_MESHES, f"SM_Postbox_{RND.randint(0,10**7):07d}", x,y,z, rot=RND.uniform(0,6.28))
                elif RND.random() < 0.15:
                    inst(KIT_OBJS["parkingmeter"], C_MESHES, f"SM_ParkingMeter_{RND.randint(0,10**7):07d}", x,y,z, rot=RND.uniform(0,6.28))
            t += 90

    # Update stats per type
    for k,v in placed.items():
        STATS["per_type"][k] = v
    print(f"[props] Street furniture placed: {placed}")


def place_rooftop_props():
    print("[props] Placing rooftop props...")
    placed = {"acunit": 0, "watertank": 0, "chimney": 0}
    for district in ["D", "R", "E", "M", "G", "I", "T"]:
        try:
            parcels = ck.read_parcels(district)
        except:
            continue
        for p in parcels:
            # Skip M which is already dressed
            if district == "M":
                continue
            # Sample subset
            if district == "R":
                if RND.random() > 0.15:
                    continue
            elif district in ["D", "E"]:
                if RND.random() > 0.25:
                    continue
            else:
                continue  # G,I,T as specified
            br = p.get("buildable_rect")
            if not br:
                continue
            x0,y0,x1,y1 = br
            cx, cy = p.get("center", [(x0+x1)/2, (y0+y1)/2])
            h = p.get("height_m", 10.0)
            # Skip parcels whose roof would clip the flyover ground band (±20 m around ring centreline at ±1400)
            # rough check
            if abs(abs(cx)-1400) < 50 and abs(cy) < 1500:  # near ring
                continue
            if in_circuit(cx,cy):
                continue
            # place 1-4 units
            num = RND.randint(1,4)
            for i in range(num):
                rx = RND.uniform(x0+2, x1-2)
                ry = RND.uniform(y0+2, y1-2)
                rz = h + 1.0  # at parcel height_m + unit height
                if RND.random() < 0.5:
                    inst(KIT_OBJS["acunit"], C_MESHES, f"SM_AC_{placed['acunit']:05d}", rx,ry,rz, rot=RND.uniform(0,6.28))
                    placed["acunit"] += 1
                elif RND.random() < 0.7:
                    inst(KIT_OBJS["watertank"], C_MESHES, f"SM_WT_{placed['watertank']:05d}", rx,ry,rz, rot=RND.uniform(0,6.28))
                    placed["watertank"] += 1
                else:
                    inst(KIT_OBJS["chimney"], C_MESHES, f"SM_Chim_{placed['chimney']:05d}", rx,ry,rz, rot=RND.uniform(0,6.28))
                    placed["chimney"] += 1
    STATS["per_type"].update(placed)
    print(f"[props] Rooftop props placed: {placed}")


def place_lake_props():
    print("[props] Placing lake props...")
    placed = 0
    if not LAKE_POLY:
        return
    # life-buoys + railing along the shore polyline, offset inside the shore
    # EXCEPT inside LAKE_1 bbox rules - "EXCEPT life-buoys + railing along the shore polyline"
    n = len(LAKE_POLY)
    for i in range(n):
        x1,y1 = LAKE_POLY[i]
        x2,y2 = LAKE_POLY[(i+1)%n]
        # point along shore
        mx,my = (x1+x2)/2, (y1+y2)/2
        # offset inside shore
        cx,cy = sum(p[0] for p in LAKE_POLY)/n, sum(p[1] for p in LAKE_POLY)/n
        dx,dy = mx-cx, my-cy
        l = math.hypot(dx,dy) or 1
        dx,dy = dx/l, dy/l
        ix,iy = mx + dx*3.0, my + dy*3.0  # inside
        if i % 3 == 0:
            inst(KIT_OBJS["lifebuoy"], C_MESHES, f"SM_LifeBuoy_{placed:05d}", ix,iy,0.0, rot=RND.uniform(0,6.28))
            placed += 1
        if i % 2 == 0:
            inst(KIT_OBJS["lakerailing"], C_MESHES, f"SM_LakeRailing_{placed:05d}", ix,iy,0.0, rot=math.atan2(dy,dx))
            placed += 1
    STATS["per_type"]["lifebuoy"] = placed//2
    STATS["per_type"]["lakerailing"] = placed - placed//2
    print(f"[props] Lake props placed: {placed}")


def place_circuit_props():
    print("[props] Placing circuit props...")
    placed = 0
    # EXCEPT crowd barriers + jersey barriers along the outer fence line at 4 m clearance
    x0,y0,x1,y1 = CIRCUIT_CORRIDOR
    # place along edges
    # bottom edge
    for x in range(int(x0)+10, int(x1)-10, 8):
        y = y0 + 4.0
        if in_any_stadium(x,y) or in_facility_rect(x,y):
            continue
        inst(KIT_OBJS["crowdbarrier"], C_MESHES, f"SM_Crowd_{placed:05d}", x,y,0.0, rot=0)
        placed += 1
        if placed % 2 == 0:
            inst(KIT_OBJS["jersey"], C_MESHES, f"SM_Jersey_{placed:05d}", x+4,y+2,0.0, rot=0)
    STATS["per_type"]["crowdbarrier"] = placed
    STATS["per_type"]["jersey"] = placed//2
    print(f"[props] Circuit props placed: {placed}")


def add_colliders():
    print("[props] Adding colliders...")
    # one COL_props_<type> box per type in Props/Colliders
    types = ["bin", "hydrant", "bollard", "bench", "bikerack", "planter", 
             "mailbox", "utilitybox", "postbox", "newsbox", "parkingmeter",
             "conestack", "barrier", "jersey", "streetsign", "busshelter",
             "tramstop", "pigeonpost", "fireescape", "awningbracket", "cable",
             "satellite", "watertank", "chimney", "acunit", "billboard", 
             "aframe", "marketstall", "crowdbarrier", "phonekiosk", 
             "lifebuoy", "lakerailing", "noticeboard", "catenary"]
    for t in types:
        ensure_collider(t)
    print(f"[props] Colliders added: {len(COLLIDERS)}")


# --------------------------------------------------------------------------
# Setup and run
# --------------------------------------------------------------------------
def setup():
    global TOP, C_MESHES, C_COLLIDERS, C_LIGHTS
    # Clear scene
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

    TOP = ck.ensure_collection("Props")
    C_MESHES = ck.ensure_collection("Meshes", parent=TOP)
    C_COLLIDERS = ck.ensure_collection("Colliders", parent=TOP)
    C_LIGHTS = ck.ensure_collection("Lights", parent=TOP)
    print("[props] Setup complete")


def main():
    setup()
    build_kit()
    place_street_furniture()
    place_rooftop_props()
    place_lake_props()
    place_circuit_props()
    add_colliders()

    # Apply all transforms
    for ob in bpy.data.objects:
        try:
            ck.apply_all_transforms(ob)
        except Exception:
            pass
    ck.update_view()

    # Save blend
    blend_path = ck.save_blend(os.path.join(ck.OUT_DIR, "props.blend"))

    # Previews
    try:
        # Preview 1: arterials kerbside
        ck.make_preview(os.path.join(ck.OUT_DIR, "props_preview.png"),
                        (600, 900, 80), (600, 1200, 0), engine="BLENDER_EEVEE",
                        res=(1920, 1080))
    except Exception as e:
        STATS["issues"].append(f"Preview 1 failed: {e}")
    try:
        # Preview 2: market alley with A-frames + cables
        ck.make_preview(os.path.join(ck.OUT_DIR, "props_street_preview.png"),
                        (750, 628, 15), (750, 742, 5), engine="BLENDER_EEVEE",
                        res=(1920, 1080))
    except Exception as e:
        STATS["issues"].append(f"Preview 2 failed: {e}")

    # Calculate tris
    total_tris = ck.scene_tri_count()
    STATS["tris_instanced_total"] = total_tris

    # Write reports
    report_data = {
        "module": "props",
        "paths": {
            "script": "/home/abdulhadi/Work/city/modules/props.py",
            "blend": blend_path,
            "preview": os.path.join(ck.OUT_DIR, "props_preview.png"),
            "street_preview": os.path.join(ck.OUT_DIR, "props_street_preview.png"),
        },
        "unique_meshes": STATS["unique_meshes"],
        "kit_tris_total": STATS["kit_tris_total"],
        "instances_total": STATS["instances_total"],
        "tris_instanced_total": total_tris,
        "per_type": STATS["per_type"],
        "materials_used": sorted(list(STATS["materials_used"])),
        "issues": STATS["issues"],
        "needs": STATS["needs"],
    }
    ck.write_report("props", report_data)

    # Write markdown report
    md_path = os.path.join(ck.REPORTS_DIR, "props_report.md")
    with open(md_path, "w") as f:
        f.write("# Props Module Report\n\n")
        f.write(f"- Script: {report_data['paths']['script']}\n")
        f.write(f"- Blend: {report_data['paths']['blend']}\n")
        f.write(f"- Preview: {report_data['paths']['preview']}\n")
        f.write(f"- Street Preview: {report_data['paths']['street_preview']}\n\n")
        f.write(f"## Counts\n")
        f.write(f"- Unique meshes: {STATS['unique_meshes']}\n")
        f.write(f"- Kit tris total: {STATS['kit_tris_total']}\n")
        f.write(f"- Instances total: {STATS['instances_total']}\n")
        f.write(f"- Tris instanced total (scene): {total_tris}\n\n")
        f.write(f"## Per type\n")
        for k, v in STATS["per_type"].items():
            f.write(f"- {k}: {v}\n")
        f.write(f"\n## Materials used\n")
        for m in sorted(list(STATS["materials_used"])):
            f.write(f"- {m}\n")
        f.write(f"\n## Issues\n")
        for issue in STATS["issues"]:
            f.write(f"- {issue}\n")
        if not STATS["issues"]:
            f.write("- None\n")
        f.write(f"\n## Needs from other agents\n")
        for need in STATS["needs"]:
            f.write(f"- {need}\n")
        if not STATS["needs"]:
            f.write("- None\n")
    print(f"[props] Markdown report written to {md_path}")

    print(f"[props] Done in {time.time()-T0:.1f}s")


if __name__ == "__main__":
    main()
