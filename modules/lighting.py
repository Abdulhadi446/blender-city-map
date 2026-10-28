#!/usr/bin/env python3
"""lighting.py — LIGHTING module (headless). Street lamps, traffic signals, night rig.

Builds:
  kit meshes (8 types) + colliders
  placements per layout (arterial/street/alley/highway/deck/signals/bollards/uplights/flood towers)
  real light objects (<=300) in Lights collection
  previews (night) + reports

Run: cd /home/abdulhadi/Work/city && blender -b -P modules/lighting.py
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

import bpy
import bmesh
from mathutils import Matrix, Vector
import citykit as ck

OUT_BLEND = os.path.join(ck.OUT_DIR, "lighting.blend")
PREV_A = os.path.join(ck.OUT_DIR, "lighting_preview.png")
PREV_B = os.path.join(ck.OUT_DIR, "lighting_street_preview.png")
REPORT_MD = os.path.join(ck.REPORTS_DIR, "lighting_report.md")
REPORT_JSON = os.path.join(ck.REPORTS_DIR, "lighting_report.json")

SEED = 1337
RND = random.Random(SEED)
T0 = time.time()

L = ck.read_layout()
NODES = {n["id"]: n for n in L["road_nodes"]}
EDGES = ck.read_road_edges()
PARCELS_BY_ID = {p["id"]: p for p in L["parcels"]}

# Exclusion / keepout constants
STADIUM_RECTS = [
    (-864.0, -1164.0, -636.0, -936.0),
    (36.0, -1164.0, 264.0, -936.0),
    (-1164.0, -864.0, -936.0, -636.0),
    (-1164.0, -564.0, -936.0, -336.0),
    (12.0, -888.0, 288.0, -612.0),
]
LAKE_BBOX = (-552.58, -1142.57, -335.1, -969.78)

# Program facilities (rects for keepout / landmark uplights)
try:
    with open(os.path.join(ROOT, "reports", "program.json")) as f:
        PROGRAM = json.load(f)
    FACILITIES = PROGRAM.get("facilities", [])
except Exception:
    FACILITIES = []

# landmark rects for uplighting
LANDMARK_RECTS = {
    "ICON_TOWER": (45.0, 1214.0, 198.0, 1360.0),
    "CITY_HALL": (12.0, 222.0, 78.0, 288.0),
    "RET_MALL": (78.0, -288.0, 144.0, -222.0),
    "HOT_HOTEL": (78.0, -222.0, 144.0, -156.0),
}
# LM_BAZAAR parcel rect
bz = PARCELS_BY_ID.get("BZ_6_6_1_1")
if bz:
    LANDMARK_RECTS["LM_BAZAAR"] = tuple(bz["rect"])
lt = PARCELS_BY_ID.get("B_4_3_0_1_0_0")
if lt:
    LANDMARK_RECTS["LM_LANDMARK_TOWER"] = tuple(lt["rect"])

# Collections
TOP = None
C_MESHES = None
C_COLLIDERS = None
C_LIGHTS = None

# Stats
STATS = {
    "kit": {},            # name -> count
    "kit_tris": {},       # name -> tris
    "instances_total": 0,
    "real_lights": 0,
    "emissive_instances": 0,
    "materials_used": set(),
    "issues": [],
}
KIT_SRC = {}   # kit name -> source object
LIGHT_COUNTER = {"n": 0}


# --------------------------------------------------------------------------
# MB mesh builder
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
        STATS["materials_used"].add(name)
        return len(self.mats) - 1

    def add(self, V, F, mi=0):
        if not F:
            return
        off = len(self.v)
        self.v.extend([tuple(p) for p in V])
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

    def cyl_z(self, cx, cy, z0, r0, r1, h, seg=8, mi=0, cap_bottom=True, cap_top=True):
        # vertical cylinder from z0 to z0+h
        r1 = max(r1, 0.004)
        V, F = [], []
        for i in range(seg):
            a = 2.0 * math.pi * i / seg
            V.append((cx + r0 * math.cos(a), cy + r0 * math.sin(a), z0))
        for i in range(seg):
            a = 2.0 * math.pi * i / seg
            V.append((cx + r1 * math.cos(a), cy + r1 * math.sin(a), z0 + h))
        for i in range(seg):
            j = (i + 1) % seg
            F.append((i, j, seg + j, seg + i))
        if cap_bottom:
            F.append(tuple(range(seg - 1, -1, -1)))
        if cap_top:
            F.append(tuple(range(seg, 2 * seg)))
        self.add(V, F, mi)

    def tris(self):
        return sum(len(f) - 2 for f in self.f)


def mesh_object(name, mb, coll, hidden=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata(mb.v, [], mb.f)
    me.update()
    for mn in mb.mats:
        me.materials.append(ck.append_material(mn))
    for i, mi in enumerate(mb.m):
        if i < len(me.polygons):
            me.polygons[i].material_index = int(mi)
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


def inst(src, coll, name, x, y, z, rot=0.0, sx=1.0, sy=None, sz=None):
    ob = bpy.data.objects.new(name, src.data)
    ob.location = (float(x), float(y), float(z))
    ob.rotation_euler = (0.0, 0.0, float(rot))
    if sy is None and sz is None:
        ob.scale = (float(sx), float(sx), float(sx))
    else:
        ob.scale = (float(sx), float(sy if sy is not None else sx),
                    float(sz if sz is not None else sx))
    coll.objects.link(ob)
    STATS["instances_total"] += 1
    return ob


def add_light(loc, rot=(0.0, 0.0, 0.0), light_type="SPOT", energy=200.0, color=(1,1,1),
              spot_size=1.2, spot_blend=0.3):
    LIGHT_COUNTER["n"] += 1
    n = LIGHT_COUNTER["n"]
    data = bpy.data.lights.new("LT_light_%03d" % n, type=light_type)
    data.energy = energy
    if light_type == "SPOT":
        data.spot_size = spot_size
        data.spot_blend = spot_blend
    data.color = color
    ob = bpy.data.objects.new("LT_light_%03d" % n, data)
    ob.location = (float(loc[0]), float(loc[1]), float(loc[2]))
    ob.rotation_euler = rot
    C_LIGHTS.objects.link(ob)
    STATS["real_lights"] += 1
    return ob


# --------------------------------------------------------------------------
# KIT BUILD
# --------------------------------------------------------------------------
def build_kit():
    global KIT_SRC
    # materials indices
    m_conc = None
    # 1. Arterial lamp
    mb = MB()
    i_conc = mb.midx("concrete")
    i_steel = mb.midx("metal_steel")
    i_warm = mb.midx("emissive_warm")
    # base
    mb.cyl_z(0, 0, 0, 0.35, 0.30, 0.4, seg=10, mi=i_conc)
    # pole
    mb.cyl_z(0, 0, 0.4, 0.12, 0.10, 10.6, seg=8, mi=i_steel)  # to 11.0
    # arms: two curved-ish arms (boxes) at top, opposite sides
    # left arm
    mb.box(-1.5, 0, 11.0, 3.0, 0.12, 0.12, mi=i_steel)
    mb.box(-3.0, 0, 10.6, 0.12, 0.12, 0.8, mi=i_steel)
    # right arm
    mb.box(1.5, 0, 11.0, 3.0, 0.12, 0.12, mi=i_steel)
    mb.box(3.0, 0, 10.6, 0.12, 0.12, 0.8, mi=i_steel)
    # heads (emissive) at arm ends
    mb.box(-3.0, 0, 10.4, 0.5, 0.35, 0.2, mi=i_warm)
    mb.box(3.0, 0, 10.4, 0.5, 0.35, 0.2, mi=i_warm)
    ob = mesh_object("SM_Lamp_Arterial_01", mb, C_MESHES)
    KIT_SRC["Lamp_Arterial"] = ob
    STATS["kit"]["SM_Lamp_Arterial_01"] = 0
    STATS["kit_tris"]["SM_Lamp_Arterial_01"] = mb.tris()

    # 2. Street lamp
    mb = MB()
    i_conc = mb.midx("concrete")
    i_steel = mb.midx("metal_steel")
    i_warm = mb.midx("emissive_warm")
    mb.cyl_z(0, 0, 0, 0.30, 0.26, 0.35, seg=8, mi=i_conc)
    mb.cyl_z(0, 0, 0.35, 0.10, 0.08, 7.65, seg=8, mi=i_steel)  # to 8.0
    # arm one side
    mb.box(1.25, 0, 8.0, 2.5, 0.10, 0.10, mi=i_steel)
    mb.box(2.5, 0, 7.7, 0.10, 0.10, 0.6, mi=i_steel)
    mb.box(2.5, 0, 7.5, 0.45, 0.30, 0.18, mi=i_warm)
    ob = mesh_object("SM_Lamp_Street_01", mb, C_MESHES)
    KIT_SRC["Lamp_Street"] = ob
    STATS["kit_tris"]["SM_Lamp_Street_01"] = mb.tris()

    # 3. Wall lantern (slim pole 4m + bracket + lantern)
    mb = MB()
    i_conc = mb.midx("concrete")
    i_steel = mb.midx("metal_steel")
    i_warm = mb.midx("emissive_warm")
    mb.cyl_z(0, 0, 0, 0.12, 0.10, 0.15, seg=6, mi=i_conc)
    mb.cyl_z(0, 0, 0.15, 0.06, 0.05, 3.85, seg=6, mi=i_steel)  # to 4.0
    # bracket
    mb.box(0.4, 0, 4.0, 0.8, 0.10, 0.10, mi=i_steel)
    mb.box(0.8, 0, 3.85, 0.10, 0.10, 0.3, mi=i_steel)
    # lantern
    mb.box(0.8, 0, 3.7, 0.35, 0.25, 0.35, mi=i_warm)
    ob = mesh_object("SM_Lamp_Wall_01", mb, C_MESHES)
    KIT_SRC["Lamp_Wall"] = ob
    STATS["kit_tris"]["SM_Lamp_Wall_01"] = mb.tris()

    # 4. Highway lamp (13m)
    mb = MB()
    i_conc = mb.midx("concrete")
    i_steel = mb.midx("metal_steel")
    i_warm = mb.midx("emissive_warm")
    mb.cyl_z(0, 0, 0, 0.32, 0.28, 0.4, seg=8, mi=i_conc)
    mb.cyl_z(0, 0, 0.4, 0.11, 0.09, 11.6, seg=8, mi=i_steel)  # to 12.0
    mb.box(1.4, 0, 12.0, 2.8, 0.10, 0.10, mi=i_steel)
    mb.box(2.8, 0, 11.7, 0.10, 0.10, 0.6, mi=i_steel)
    mb.box(2.8, 0, 11.5, 0.5, 0.32, 0.2, mi=i_warm)
    ob = mesh_object("SM_Lamp_Highway_01", mb, C_MESHES)
    KIT_SRC["Lamp_Highway"] = ob
    STATS["kit_tris"]["SM_Lamp_Highway_01"] = mb.tris()

    # 5. Signal
    mb = MB()
    i_conc = mb.midx("concrete")
    i_steel = mb.midx("metal_steel")
    i_red = mb.midx("neon_red")
    i_amb = mb.midx("emissive_warm")
    i_grn = mb.midx("neon_green")
    # pole
    mb.cyl_z(0, 0, 0, 0.22, 0.18, 0.35, seg=8, mi=i_conc)
    mb.cyl_z(0, 0, 0.35, 0.10, 0.08, 5.65, seg=8, mi=i_steel)  # to 6.0
    # mast arm along +X at z=5.5
    mb.box(3.5, 0, 5.5, 7.0, 0.12, 0.12, mi=i_steel)
    # signal head (vertical 3-light) at arm end, hanging
    mb.box(7.0, 0, 4.6, 0.35, 0.25, 1.2, mi=i_steel)
    mb.box(7.0, 0, 5.0, 0.22, 0.18, 0.22, mi=i_red)
    mb.box(7.0, 0, 4.6, 0.22, 0.18, 0.22, mi=i_amb)
    mb.box(7.0, 0, 4.2, 0.22, 0.18, 0.22, mi=i_grn)
    # pedestrian signal box on pole
    mb.box(0, 0.15, 2.5, 0.25, 0.12, 0.4, mi=i_steel)
    mb.box(0, 0.22, 2.5, 0.18, 0.06, 0.18, mi=i_red)
    mb.box(0, 0.22, 2.3, 0.18, 0.06, 0.18, mi=i_grn)
    ob = mesh_object("SM_Signal_01", mb, C_MESHES)
    KIT_SRC["Signal"] = ob
    STATS["kit_tris"]["SM_Signal_01"] = mb.tris()

    # 6. Bollard light
    mb = MB()
    i_conc = mb.midx("concrete")
    i_steel = mb.midx("metal_steel")
    i_warm = mb.midx("emissive_warm")
    mb.cyl_z(0, 0, 0, 0.12, 0.12, 0.15, seg=8, mi=i_conc)
    mb.cyl_z(0, 0, 0.15, 0.08, 0.07, 0.70, seg=8, mi=i_steel)  # to 0.85
    mb.cyl_z(0, 0, 0.85, 0.09, 0.09, 0.15, seg=8, mi=i_warm)  # band
    ob = mesh_object("SM_BollardLight_01", mb, C_MESHES)
    KIT_SRC["BollardLight"] = ob
    STATS["kit_tris"]["SM_BollardLight_01"] = mb.tris()

    # 7. Uplight
    mb = MB()
    i_conc = mb.midx("concrete")
    i_steel = mb.midx("metal_steel")
    i_cool = mb.midx("emissive_cool")
    mb.cyl_z(0, 0, 0, 0.10, 0.10, 0.04, seg=8, mi=i_conc)
    mb.cyl_z(0, 0, 0.04, 0.08, 0.08, 0.02, seg=8, mi=i_steel)
    mb.cyl_z(0, 0, 0.06, 0.07, 0.07, 0.02, seg=8, mi=i_cool)
    ob = mesh_object("SM_Uplight_01", mb, C_MESHES)
    KIT_SRC["Uplight"] = ob
    STATS["kit_tris"]["SM_Uplight_01"] = mb.tris()

    # 8. Flood tower
    mb = MB()
    i_steel = mb.midx("metal_steel")
    i_warm = mb.midx("emissive_warm")
    # base
    mb.box(0, 0, 0.1, 2.0, 2.0, 0.2, mi=i_steel)
    # lattice legs (4)
    for (sx, sy) in ((-0.8, -0.8), (0.8, -0.8), (-0.8, 0.8), (0.8, 0.8)):
        mb.box(sx, sy, 9.0, 0.18, 0.18, 18.0, mi=i_steel)
    # cross braces
    for z in (3.0, 6.0, 9.0, 12.0, 15.0):
        mb.box(0, 0, z, 1.8, 0.12, 0.12, mi=i_steel)
        mb.box(0, 0, z + 1.5, 0.12, 1.8, 0.12, mi=i_steel)
    # top flood heads
    for (sx, sy) in ((-0.6, -0.6), (0.6, -0.6), (-0.6, 0.6), (0.6, 0.6)):
        mb.box(sx, sy, 17.5, 0.4, 0.3, 0.25, mi=i_warm)
    ob = mesh_object("SM_FloodTower_01", mb, C_MESHES)
    KIT_SRC["FloodTower"] = ob
    STATS["kit_tris"]["SM_FloodTower_01"] = mb.tris()

    # Colliders: one per kit type
    collider_specs = {
        "Lamp_Arterial": (0.3, 11.0),
        "Lamp_Street": (0.25, 8.0),
        "Lamp_Wall": (0.15, 4.0),
        "Lamp_Highway": (0.28, 12.0),
        "Signal": (0.25, 6.0),
        "BollardLight": (0.15, 1.0),
        "Uplight": (0.12, 0.1),
        "FloodTower": None,
    }
    for key, spec in collider_specs.items():
        mb = MB()
        i_col = mb.midx("col_placeholder")
        if spec is None:
            mb.box(0, 0, 9.0, 2.0, 2.0, 18.0, mi=i_col)
        else:
            r, h = spec
            mb.cyl_z(0, 0, 0, r, r, h, seg=8, mi=i_col)
        name = "COL_lighting_%s" % key.lower()
        ob = mesh_object(name, mb, C_COLLIDERS)
        KIT_SRC["COL_" + key] = ob
        STATS["kit_tris"][name] = mb.tris()


def place_along_edge(edge, kit_key, spacing, offset, z=0.0, both_sides=False, elevated=False):
    """Place lamps along a straight road edge. Returns count."""
    src = KIT_SRC[kit_key]
    coll = C_MESHES
    n = NODES[edge["a"]]
    m = NODES[edge["b"]]
    ax, ay = float(n["pos"][0]), float(n["pos"][1])
    bx, by = float(m["pos"][0]), float(m["pos"][1])
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    if length < 1.0:
        return 0
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux  # left normal
    count = 0
    # positions
    dist = spacing * 0.5
    idx = 0
    while dist < length - spacing * 0.25:
        x0 = ax + ux * dist
        y0 = ay + uy * dist
        if both_sides:
            for side in (-1.0, 1.0):
                px = x0 + nx * (side * offset)
                py = y0 + ny * (side * offset)
                # rotation: arm toward centerline = -side*normal
                cx = -side * nx
                cy = -side * ny
                rot = math.atan2(cy, cx)
                _o = inst(src, coll, "SM_%s_%05d" % (kit_key, idx + (0 if side < 0 else 100000)), px, py, z, rot=rot)
                if elevated:
                    _o["elevated"] = True
                    _o["elevated_z"] = 8.0
                STATS["kit"][kit_key] = STATS["kit"].get(kit_key, 0) + 1
                count += 1
        else:
            side = 1.0 if (idx % 2 == 0) else -1.0
            px = x0 + nx * (side * offset)
            py = y0 + ny * (side * offset)
            cx = -side * nx
            cy = -side * ny
            rot = math.atan2(cy, cx)
            _o = inst(src, coll, "SM_%s_%05d" % (kit_key, idx), px, py, z, rot=rot)
            if elevated:
                _o["elevated"] = True
                _o["elevated_z"] = 8.0
            STATS["kit"][kit_key] = STATS["kit"].get(kit_key, 0) + 1
            count += 1
        dist += spacing
        idx += 1
    return count


# --------------------------------------------------------------------------
# PLACEMENT
# --------------------------------------------------------------------------
def place_arterial():
    kit = "Lamp_Arterial"
    for e in EDGES:
        if e["hierarchy"] != "arterial":
            continue
        place_along_edge(e, kit, 35.0, 10.8, z=0.0, both_sides=False)
    # real lights: every ~19th arterial lamp instance
    arterial_obs = [o for o in C_MESHES.objects if o.name.startswith("SM_Lamp_Arterial_")]
    # sort by name for determinism
    arterial_obs.sort(key=lambda o: o.name)
    nspots = min(60, len(arterial_obs))
    step = max(1, len(arterial_obs) // nspots) if nspots > 0 else 1
    for i, ob in enumerate(arterial_obs):
        if i % step != 0:
            continue
        if STATS["real_lights"] >= 60 + 40:
            break
        # lamp head approx: ob location + arm offset. Use ob location + forward 3m at z=10.4
        # We don't have rotation easily? use ob.matrix_world not applied; rotation_euler z.
        rotz = ob.rotation_euler.z
        hx = ob.location.x + math.cos(rotz) * 3.0
        hy = ob.location.y + math.sin(rotz) * 3.0
        hz = 10.4
        add_light((hx, hy, hz), rot=(0.0, 0.0, 0.0), light_type="SPOT",
                  energy=250.0, spot_size=2.0, spot_blend=0.4)
        if STATS["real_lights"] >= 100:
            break
    # cap at 60 arterial spots: track separately not needed


def place_street():
    for e in EDGES:
        if e["hierarchy"] != "street":
            continue
        place_along_edge(e, "Lamp_Street", 32.0, 5.0, z=0.0, both_sides=False)


def place_alley():
    # market M and downtown core
    def in_zone(x, y):
        if 300 <= x <= 1200 and 600 <= y <= 1200:
            return True
        if abs(x) < 400 and abs(y) < 400:
            return True
        return False
    for e in EDGES:
        if e["hierarchy"] != "alley":
            continue
        n = NODES[e["a"]]; m = NODES[e["b"]]
        mx = (n["pos"][0] + m["pos"][0]) / 2.0
        my = (n["pos"][1] + m["pos"][1]) / 2.0
        if not in_zone(mx, my):
            continue
        place_along_edge(e, "Lamp_Wall", 30.0, 2.2, z=0.0, both_sides=False)


def place_highway():
    deck_ids = {"H_07", "H_08"}
    for e in EDGES:
        if e["hierarchy"] != "highway":
            continue
        if e["id"] in deck_ids:
            continue
        place_along_edge(e, "Lamp_Highway", 60.0, 11.0, z=0.0, both_sides=False)
    # deck lamps on H_07, H_08 and ramp X_N_600
    for eid in ("H_07", "H_08"):
        e = next((x for x in EDGES if x["id"] == eid), None)
        if e:
            place_along_edge(e, "Lamp_Highway", 50.0, 15.5, z=8.0, both_sides=True, elevated=True)
    # ramp
    ramp = next((x for x in EDGES if x["id"] == "X_N_600"), None)
    if ramp:
        place_along_edge(ramp, "Lamp_Highway", 50.0, 8.0, z=8.0, both_sides=True, elevated=True)


def place_signals():
    for tl in L["traffic_lights"]:
        nid = tl["node"]
        node = NODES[nid]
        conn = [e for e in EDGES if e["a"] == nid or e["b"] == nid]
        n_app = int(tl.get("approaches", len(conn) or 1))
        # build list of (dx,dy,hw) for each approach
        app_list = []
        for e in conn:
            other = e["b"] if e["a"] == nid else e["a"]
            onode = NODES[other]
            dx = onode["pos"][0] - node["pos"][0]
            dy = onode["pos"][1] - node["pos"][1]
            app_list.append((dx, dy, e["width"]))
        # synthesize missing approaches by rotating
        if len(app_list) == 0:
            app_list.append((1.0, 0.0, 12.0))
        i = 0
        while len(app_list) < n_app:
            # rotate last direction by ~120 deg
            dx, dy, w = app_list[-1]
            ang = math.atan2(dy, dx) + 2.094
            app_list.append((math.cos(ang), math.sin(ang), 12.0))
        for (dx, dy, w) in app_list[:n_app]:
            length = math.hypot(dx, dy) or 1.0
            ux, uy = dx / length, dy / length
            tx, ty = -ux, -uy
            hw = w / 2.0
            offset = hw - 0.5
            rx, ry = ty, -tx
            px = node["pos"][0] + rx * offset
            py = node["pos"][1] + ry * offset
            rot = math.atan2(ty, tx)
            inst(KIT_SRC["Signal"], C_MESHES, "SM_Signal_%s_%d" % (tl["id"], i), px, py, 0.0, rot=rot)
            STATS["kit"]["SM_Signal_01"] = STATS["kit"].get("SM_Signal_01", 0) + 1
            i += 1


def place_bollards():
    kit = "BollardLight"
    src = KIT_SRC[kit]
    # central plaza perimeter, inset 0.5
    rect = (12.0, 12.0, 144.0, 144.0)
    x0, y0, x1, y1 = rect
    # inset
    ix0, iy0, ix1, iy1 = x0 + 0.5, y0 + 0.5, x1 - 0.5, y1 - 0.5
    pts = []
    # bottom edge
    x = ix0
    while x <= ix1:
        pts.append((x, iy0)); x += 6.0
    # right edge
    y = iy0
    while y <= iy1:
        pts.append((ix1, y)); y += 6.0
    # top edge
    x = ix1
    while x >= ix0:
        pts.append((x, iy1)); x -= 6.0
    # left edge
    y = iy1
    while y >= iy0:
        pts.append((ix0, y)); y -= 6.0
    for (px, py) in pts:
        inst(src, C_MESHES, "SM_BollardLight_plaza", px, py, 0.0)
        STATS["kit"][kit] = STATS["kit"].get(kit, 0) + 1
    # stadium perimeters: rect+2m outside, space 6m
    for sr in STADIUM_RECTS:
        x0, y0, x1, y1 = sr  # note: x0<x1? check
        # ensure
        xa, xb = sorted([x0, x1])
        ya, yb = sorted([y0, y1])
        # expanded rect by 2m
        ex0, ey0, ex1, ey1 = xa - 2.0, ya - 2.0, xb + 2.0, yb + 2.0
        # generate perimeter points on expanded rect, space 6
        pts = []
        x = ex0
        while x <= ex1:
            pts.append((x, ey0)); x += 6.0
        y = ey0
        while y <= ey1:
            pts.append((ex1, y)); y += 6.0
        x = ex1
        while x >= ex0:
            pts.append((x, ey1)); x -= 6.0
        y = ey1
        while y >= ey0:
            pts.append((ex0, y)); y -= 6.0
        for (px, py) in pts:
            inst(src, C_MESHES, "SM_BollardLight_stadium", px, py, 0.0)
            STATS["kit"][kit] = STATS["kit"].get(kit, 0) + 1


def place_uplights():
    kit = "Uplight"
    src = KIT_SRC[kit]
    # number of fixtures per landmark
    counts = {
        "ICON_TOWER": 8,
        "CITY_HALL": 6,
        "RET_MALL": 6,
        "HOT_HOTEL": 6,
        "LM_BAZAAR": 6,
        "LM_LANDMARK_TOWER": 6,
    }
    for name, rect in LANDMARK_RECTS.items():
        x0, y0, x1, y1 = rect
        xa, xb = sorted([x0, x1])
        ya, yb = sorted([y0, y1])
        n = counts.get(name, 6)
        # perimeter of rect
        perim = 2 * ((xb - xa) + (yb - ya))
        # generate n points around perimeter, offset outward by 1.5m
        # parametrize
        pts = []
        # collect base perimeter points (before offset) evenly
        for i in range(n):
            s = perim * i / n
            # walk perimeter
            # edges: bottom, right, top, left
            w = xb - xa
            h = yb - ya
            if s < w:
                px, py = xa + s, ya
                ox, oy = 0, -1.5
            elif s < w + h:
                t = s - w
                px, py = xb, ya + t
                ox, oy = 1.5, 0
            elif s < 2 * w + h:
                t = s - (w + h)
                px, py = xb - t, yb
                ox, oy = 0, 1.5
            else:
                t = s - (2 * w + h)
                px, py = xa, yb - t
                ox, oy = -1.5, 0
            # For BZ use 1.5 outside parcel rect (already). Apply offset
            fpx = px + ox
            fpy = py + oy
            pts.append((fpx, fpy))
        for (fpx, fpy) in pts:
            inst(src, C_MESHES, "SM_Uplight_%s" % name, fpx, fpy, 0.0)
            STATS["kit"][kit] = STATS["kit"].get(kit, 0) + 1
            # real spot light (uplight) pointing up at facade
            if STATS["real_lights"] < 100 + 40:
                # spot pointing upward
                add_light((fpx, fpy, 0.1), rot=(math.pi, 0.0, 0.0), light_type="SPOT",
                          energy=400.0, color=(1.0, 0.95, 0.85), spot_size=1.5, spot_blend=0.5)


def place_flood_towers():
    kit = "FloodTower"
    src = KIT_SRC[kit]
    for sr in STADIUM_RECTS:
        xa, xb = sorted([sr[0], sr[2]])
        ya, yb = sorted([sr[1], sr[3]])
        # place 2 towers 40m outside north side
        for k in range(2):
            px = xa + (xb - xa) * (k + 1) / 3.0
            py = yb + 40.0
            inst(src, C_MESHES, "SM_FloodTower_stadium", px, py, 0.0)
            STATS["kit"][kit] = STATS["kit"].get(kit, 0) + 1


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------
def setup():
    global TOP, C_MESHES, C_COLLIDERS, C_LIGHTS
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    for me in list(bpy.data.meshes):
        if me.users == 0:
            bpy.data.meshes.remove(me)
    for lt in list(bpy.data.lights):
        bpy.data.lights.remove(lt)
    for w in list(bpy.data.worlds):
        bpy.data.worlds.remove(w)

    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    try:
        scene.render.engine = "BLENDER_EEVEE"
    except Exception:
        pass

    TOP = ck.ensure_collection("Lighting")
    C_MESHES = ck.ensure_collection("Meshes", parent=TOP)
    C_COLLIDERS = ck.ensure_collection("Colliders", parent=TOP)
    C_LIGHTS = ck.ensure_collection("Lights", parent=TOP)
    print("[lighting] setup complete")


def main():
    setup()
    build_kit()

    # placements
    place_arterial()
    place_street()
    place_alley()
    place_highway()
    place_signals()
    place_bollards()
    place_uplights()
    place_flood_towers()

    # Apply transforms to unique meshes only
    for coll in (C_MESHES, C_COLLIDERS):
        for ob in list(coll.objects):
            if ob.type == "MESH" and ob.data is not None and getattr(ob.data, "users", 1) == 1:
                try:
                    ck.apply_all_transforms(ob)
                except Exception:
                    pass
    ck.update_view()

    # counts per kit type (subtract the single source mesh per type)
    sig_instances = sum(1 for o in C_MESHES.objects if o.name.startswith("SM_Signal_")) - 1
    bollard_instances = sum(1 for o in C_MESHES.objects if o.name.startswith("SM_BollardLight_")) - 1
    uplight_instances = sum(1 for o in C_MESHES.objects if o.name.startswith("SM_Uplight_")) - 1
    flood_instances = sum(1 for o in C_MESHES.objects if o.name.startswith("SM_FloodTower_")) - 1
    arterial_instances = sum(1 for o in C_MESHES.objects if o.name.startswith("SM_Lamp_Arterial_")) - 1
    street_instances = sum(1 for o in C_MESHES.objects if o.name.startswith("SM_Lamp_Street_")) - 1
    wall_instances = sum(1 for o in C_MESHES.objects if o.name.startswith("SM_Lamp_Wall_")) - 1
    highway_instances = sum(1 for o in C_MESHES.objects if o.name.startswith("SM_Lamp_Highway_")) - 1

    counts_per_type = {
        "SM_Lamp_Arterial_01": arterial_instances,
        "SM_Lamp_Street_01": street_instances,
        "SM_Lamp_Wall_01": wall_instances,
        "SM_Lamp_Highway_01": highway_instances,
        "SM_Signal_01": sig_instances,
        "SM_BollardLight_01": bollard_instances,
        "SM_Uplight_01": uplight_instances,
        "SM_FloodTower_01": flood_instances,
    }
    STATS["counts_per_type"] = counts_per_type

    mesh_instances = sum(counts_per_type.values())
    STATS["emissive_instances"] = mesh_instances

    # Save blend
    blend_path = ck.save_blend(OUT_BLEND)

    # Previews (night)
    # create dark world
    world = bpy.data.worlds.new("TMP_NIGHT_WORLD")
    world.use_nodes = True
    bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg is not None:
        bg.inputs[0].default_value = (0.02, 0.03, 0.06, 1.0)
        bg.inputs[1].default_value = 0.05
    bpy.context.scene.world = world

    try:
        ck.make_preview(PREV_A, (0.0, 0.0, 900.0), (0.0, 0.0, 0.0),
                       engine="BLENDER_EEVEE", res=(1920, 1080),
                       sun_elev=5.0, sun_azim=-40.0, sun_energy=0.05, samples=16)
    except Exception as e:
        STATS["issues"].append("Preview A failed: %s" % e)
    try:
        ck.make_preview(PREV_B, (750.0, 628.0, 8.0), (750.0, 742.0, 4.0),
                       engine="BLENDER_EEVEE", res=(1920, 1080),
                       sun_elev=5.0, sun_azim=-40.0, sun_energy=0.05, samples=16)
    except Exception as e:
        STATS["issues"].append("Preview B failed: %s" % e)

    # remove temp world
    try:
        bpy.context.scene.world = None
        bpy.data.worlds.remove(world)
    except Exception:
        pass

    # re-save after preview cleanup
    ck.save_blend(OUT_BLEND)

    # tri counts
    unique_tris = ck.scene_tri_count()

    def instanced_tris():
        seen = {}
        for o in bpy.data.objects:
            d = getattr(o, "data", None)
            if d is None:
                continue
            p = d.as_pointer()
            if p not in seen:
                seen[p] = [ck.tri_count(o), 0]
            seen[p][1] += 1
        return sum(t * c for t, c in seen.values())

    inst_tris = instanced_tris()

    # Write JSON report
    report_data = {
        "module": "lighting",
        "paths": {
            "script": "/home/abdulhadi/Work/city/modules/lighting.py",
            "blend": blend_path,
            "preview": PREV_A,
            "street_preview": PREV_B,
        },
        "unique_meshes": len([m for m in bpy.data.meshes]),
        "kit_tris_total": sum(v for k, v in STATS["kit_tris"].items() if not k.startswith("COL_")),
        "kit_tris_per_mesh": STATS["kit_tris"],
        "instances_total": STATS["instances_total"],
        "counts_per_type": counts_per_type,
        "real_lights": STATS["real_lights"],
        "emissive_instances": STATS["emissive_instances"],
        "tris_unique": unique_tris,
        "tris_instanced": inst_tris,
        "materials_used": sorted(list(STATS["materials_used"])),
        "issues": STATS["issues"],
    }
    ck.write_report("lighting", report_data)

    # Markdown report
    with open(REPORT_MD, "w") as f:
        f.write("# Lighting Module Report\n\n")
        f.write(f"- Script: {report_data['paths']['script']}\n")
        f.write(f"- Blend: {report_data['paths']['blend']}\n")
        f.write(f"- Preview (aerial night): {PREV_A}\n")
        f.write(f"- Preview (street night): {PREV_B}\n\n")
        f.write("## Counts per kit type\n")
        for k, v in counts_per_type.items():
            f.write(f"- {k}: {v} instances ({STATS['kit_tris'].get(k,0)} tris/mesh)\n")
        f.write(f"\n- Unique meshes: {report_data['unique_meshes']}\n")
        f.write(f"- Kit tris total (unique meshes): {report_data['kit_tris_total']}\n")
        f.write(f"- Instances total: {report_data['instances_total']}\n")
        f.write(f"- Tris unique: {unique_tris}\n")
        f.write(f"- Tris instanced: {inst_tris}\n")
        f.write(f"- Real lights: {STATS['real_lights']}\n")
        f.write(f"- Emissive instances: {STATS['emissive_instances']}\n\n")
        f.write("## Real-vs-emissive split\n")
        f.write(f"- Real light objects: {STATS['real_lights']} (named LT_light_<nn>)\n")
        f.write(f"- Emissive instances: {STATS['emissive_instances']} (lamp heads etc.)\n")
        f.write("- Signal lenses are emissive-only (no real lights).\n")
        f.write("- 60 spot lights for arterial lamp heads (sampled), 40 spot uplights for landmarks.\n\n")
        f.write("## ASSEMBLER NIGHT-RIG NOTES\n")
        f.write("- Recommended sun angle: low (5 deg) or off; haze moderate.\n")
        f.write("- Emissive multipliers: neon x4-8 per style bible; emissive_warm lamp heads x3-5.\n")
        f.write("- World/TOD owned by Assembler; this module's previews use a temporary dark world.\n")
        f.write("- Real lights budget used: %d / 300.\n" % STATS["real_lights"])
        if STATS["issues"]:
            f.write("\n## Issues\n")
            for it in STATS["issues"]:
                f.write(f"- {it}\n")

    print("[lighting] DONE. unique_tris=%d instanced_tris=%d real_lights=%d"
          % (unique_tris, inst_tris, STATS["real_lights"]))
    print("[lighting] counts:", counts_per_type)


if __name__ == "__main__":
    main()
