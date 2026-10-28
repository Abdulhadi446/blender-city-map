#!/usr/bin/env python3
"""nature.py — Phase C "NATURE" agent for the AAA City map.

Builds, headless:
  1. tree / prop kit (shared meshes, LOD0/LOD1/LOD2)
  2. street trees along every arterial + street in districts R/E/G/D
  3. 26 parks: terrain, path network, scatter, furniture, hedges, flowerbeds
  4. LAKE_1: water, shoreline, reeds/gravel, jetty, fence
  5. playground clusters (>= 4) inside park rects
  6. COL_ collision proxies
  7. previews + reports

Run:  cd /home/abdulhadi/Work/city && blender -b -P modules/nature.py
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

import bpy                      # noqa: E402
import bmesh                    # noqa: E402
from mathutils import Matrix, Vector   # noqa: E402
import citykit as ck             # noqa: E402

SEED = 1337
RND = random.Random(SEED)

T0 = time.time()

# --------------------------------------------------------------------------
# layout
# --------------------------------------------------------------------------
L = ck.read_layout()
PARK_ROWS = L["meta"]["grid"]           # grid[0] = north row
PITCH = L["meta"]["cell_pitch_m"]
EXT = L["meta"]["inner_city_extent_m"][0]
PARCEL_BY_ID = {p["id"]: p for p in L["parcels"]}
PARK_PARCELS = []
for entry in L["parks"]:
    p = PARCEL_BY_ID[entry["parcel"]]
    feats = list(entry.get("features", []) or [])
    for f in (p.get("features") or []):
        if f not in feats:
            feats.append(f)
    PARK_PARCELS.append({
        "id": p["id"], "name": entry["name"], "rect": p["rect"],
        "center": p["center"], "size": p["size"], "type": p["type"],
        "district": p["district"], "features": feats,
    })
NODES = {n["id"]: n for n in L["road_nodes"]}
NODE_POS = [tuple(n["pos"][:2]) for n in L["road_nodes"]]
WATER = L["water"][0]
LAKE_POLY = [tuple(p) for p in WATER["polygon"]]

VR = L["vegetation_rules"]
ST_SPACING = VR["street_trees"]["spacing_m"]              # 14
ST_OFFSET = VR["street_trees"]["offset_from_curb_m"]      # 1.5
ST_SKIP = VR["street_trees"]["skip_near_junction_m"]      # 12
ST_DISTRICTS = set(VR["street_trees"]["districts"])        # R E G D
ST_HIER = set(VR["street_trees"]["hierarchies"])           # arterial street
PARK_DENSITY = VR["park_scatter"]["density_per_100m2"]     # 1.2
COURT_DENSITY = VR["courtyard_scatter"]["density_per_100m2"]  # 0.8

PARK_CAP_LARGE = 400      # instance budget guard for the 276x276 parks
PARK_CAP_SMALL = 260

# --------------------------------------------------------------------------
# collections
# --------------------------------------------------------------------------
TOP = None
C_MESH = C_COLL = C_LIGHT = None
C_STREET = C_PARK = C_PROP = C_PLAY = C_LAKE = None
C_COL = None

# --------------------------------------------------------------------------
# counters / report data
# --------------------------------------------------------------------------
N = {
    "kit_meshes": 0, "kit_tris": 0,
    "street_trees": 0, "park_trees": 0, "shade_trees": 0,
    "plaza_trees": 0, "shore_trees": 0, "shrub_instances": 0,
    "benches": 0, "bins": 0, "hedges": 0, "flowerbeds": 0,
    "reed_instances": 0, "stones": 0, "fence_segments": 0,
    "path_segments": 0, "terrain_faces": 0,
    "playground_clusters": 0, "play_objects": 0,
    "colliders": 0, "courtyard_instances": 0,
    "suppressed_buildable": 0,
}
VIOLATIONS = []
ISSUES = []
MATS_USED = set()
KIT_ROWS = []
STAGE_TIMES = []


# --------------------------------------------------------------------------
# small geometry builders  (verts / faces / face-material-index)
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

    def merge(self, other, M=None, mi_override=None):
        self.add(other.v, other.f, 0, M)
        if mi_override is not None:
            self.m[-len(other.f):] = [mi_override] * len(other.f)


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


def _hash01(i, seed):
    h = math.sin((i + 1) * 12.9898 + seed * 78.233) * 43758.5453
    return h - math.floor(h)


def prim_sphere(seg=14, rings=10, r=1.0, squash=1.0, jitter=0.0, seed=1):
    V = [(0.0, 0.0, r * squash)]
    F = []
    for j in range(1, rings):
        th = math.pi * j / rings
        for i in range(seg):
            ph = 2.0 * math.pi * i / seg
            V.append((r * math.sin(th) * math.cos(ph),
                      r * math.sin(th) * math.sin(ph),
                      r * math.cos(th) * squash))
    bot = len(V)
    V.append((0.0, 0.0, -r * squash))
    for i in range(seg):
        F.append((0, 1 + i, 1 + (i + 1) % seg))
    for j in range(rings - 2):
        a = 1 + j * seg
        b = a + seg
        for i in range(seg):
            i2 = (i + 1) % seg
            F.append((a + i, b + i, b + i2, a + i2))
    a = 1 + (rings - 2) * seg
    for i in range(seg):
        F.append((a + i, bot, a + (i + 1) % seg))
    if jitter:
        V = [(x * (1.0 + jitter * (_hash01(k, seed) - 0.5) * 2.0),
              y * (1.0 + jitter * (_hash01(k, seed) - 0.5) * 2.0),
              z * (1.0 + jitter * (_hash01(k, seed) - 0.5) * 2.0))
             for k, (x, y, z) in enumerate(V)]
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


def prim_disc(r=3.0, h=0.12, seg=16):
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
# mesh -> object
# --------------------------------------------------------------------------
def mesh_object(name, mb, mat_names, coll, hidden=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata(mb.v, [], mb.f)
    me.update()
    for mn in mat_names:
        me.materials.append(ck.append_material(mn))
        MATS_USED.add(mn)
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


def inst(src, coll, name, x, y, z, rot=0.0, s=1.0, sz=None):
    """linked duplicate (shares the source mesh data)"""
    ob = bpy.data.objects.new(name, src.data)
    ob.location = (x, y, z)
    ob.rotation_euler = (0.0, 0.0, float(rot))
    ob.scale = (s, s, s if sz is None else sz)
    coll.objects.link(ob)
    return ob


# --------------------------------------------------------------------------
# TREE KIT
# --------------------------------------------------------------------------
# per-lod detail: (trunk_seg, blob_seg, blob_rings, branch_seg, blob_detail)
LOD_PARAMS = [
    dict(tseg=9,  bseg=16, bring=11, fseg=7, detail=1.0),
    dict(tseg=6,  bseg=10, bring=7,  fseg=5, detail=0.7),
    dict(tseg=5, bseg=7,  bring=5,  fseg=4, detail=0.45),
]


def _blob(mb, x, y, z, r, mi, lod, squash=1.0, jitter=0.14, seed=1):
    p = LOD_PARAMS[lod]
    seg = max(6, int(p["bseg"] * (0.6 + 0.4 * p["detail"])))
    rng = max(4, int(p["bring"] * (0.6 + 0.4 * p["detail"])))
    V, F = prim_sphere(seg, rng, r, squash, jitter=jitter, seed=seed)
    mb.add(V, F, mi, T(x, y, z))


def _trunk(mb, r0, r1, h, lod, mi=0, seg=None, M=None):
    p = LOD_PARAMS[lod]
    V, F = prim_cyl(seg or p["tseg"], r0, r1, h)
    mb.add(V, F, mi, M)


def _branch(mb, x, y, z, length, radius, tilt, azim, lod, mi=0):
    p = LOD_PARAMS[lod]
    V, F = prim_cyl(p["fseg"], radius, radius * 0.45, length)
    mb.add(V, F, mi, T(x, y, z) @ RZ(azim) @ RX(tilt))


def tree_mesh(kind, lod=0):
    """-> (MB, [material names])"""
    mb = MB()
    d = LOD_PARAMS[lod]["detail"]

    if kind == "broadleaf_tall":
        h = 4.6
        _trunk(mb, 0.30, 0.17, h, lod)
        nb = 3 if lod == 0 else (2 if lod == 1 else 1)
        for i in range(nb):
            a = i * 2.2 + 0.5
            _branch(mb, 0, 0, h * (0.62 + 0.1 * i), 2.4 * d, 0.11,
                    math.radians(34), a, lod)
        _blob(mb, 0, 0, h + 1.5, 2.35, 1, lod, seed=11)
        n = max(2, int(5 * d))
        for i in range(n):
            a = i * 2.4 + 0.7
            rr = 1.55 * (0.8 + 0.4 * _hash01(i, 3))
            _blob(mb, 1.6 * math.cos(a), 1.6 * math.sin(a),
                  h + 0.7 + 0.9 * _hash01(i, 5), rr, 1, lod, seed=21 + i)
        if lod == 0:
            _blob(mb, 0.4, -0.5, h + 3.0, 1.5, 1, lod, seed=41)
        mats = ["bark", "leaves_green"]

    elif kind == "broadleaf_small":
        h = 3.2
        _trunk(mb, 0.20, 0.12, h, lod)
        _blob(mb, 0, 0, h + 1.2, 1.75, 1, lod, seed=7)
        n = max(2, int(4 * d))
        for i in range(n):
            a = i * 1.9 + 0.3
            _blob(mb, 1.15 * math.cos(a), 1.15 * math.sin(a), h + 0.6 + 0.6 * _hash01(i, 9),
                  1.2 * (0.85 + 0.3 * _hash01(i, 4)), 1, lod, seed=31 + i)
        mats = ["bark", "leaves_green"]

    elif kind == "conifer":
        h = 1.9
        _trunk(mb, 0.26, 0.16, h + 0.6, lod)
        tiers = 5 if lod == 0 else (4 if lod == 1 else 3)
        z = 1.0
        r = 2.0
        step = 6.0 / tiers
        for i in range(tiers):
            hh = step * 1.5
            V, F = prim_cyl(max(7, LOD_PARAMS[lod]["tseg"]), r, 0.02, hh)
            mb.add(V, F, 1, T(0, 0, z))
            z += step
            r *= 0.76
        _blob(mb, 0, 0, z + 0.4, 0.42, 1, lod, seed=13)
        mats = ["bark", "leaves_dark"]

    elif kind == "palm":
        segs = 7 if lod == 0 else (5 if lod == 1 else 4)
        r = 0.24
        z = 0.0
        bend = 0.11
        M = Matrix.Identity(4)
        for i in range(segs):
            hh = 1.05
            V, F = prim_cyl(LOD_PARAMS[lod]["tseg"], r, r * 0.94, hh)
            mb.add(V, F, 0, M @ T(0, 0, 0))
            M = M @ T(0, 0, hh) @ RX(bend)
            r *= 0.93
        top = M @ Vector((0, 0, 0))
        fronds = 9 if lod == 0 else (7 if lod == 1 else 5)
        for i in range(fronds):
            a = i * 2.0 * math.pi / fronds
            n = 5 if lod == 0 else (4 if lod == 1 else 3)
            pts = []
            Lg = 3.4 if lod == 0 else 3.0
            w0 = 0.42
            for k in range(n + 1):
                t = k / float(n)
                dd = Lg * t
                zz = 0.55 * t - 2.0 * t * t
                w = w0 * (1.0 - 0.82 * t)
                px, py = math.cos(a) * dd, math.sin(a) * dd
                qx, qy = -math.sin(a) * w, math.cos(a) * w
                pts.append(((px + qx, py + qy, zz), (px - qx, py - qy, zz)))
            F = []
            for k in range(n):
                i0 = k * 2
                F.append((i0, i0 + 2, i0 + 3, i0 + 1))
            V = [p for pair in pts for p in pair]
            mb.add(V, F, 1, T(top.x, top.y, top.z))
        mats = ["bark", "leaves_green"]

    elif kind == "street_columnar":
        h = 3.4
        _trunk(mb, 0.19, 0.12, h, lod)
        _blob(mb, 0, 0, h + 2.0, 1.15, 1, lod, squash=2.15, seed=17)
        _blob(mb, 0.25, -0.2, h + 0.9, 1.05, 1, lod, squash=1.3, seed=19)
        if lod == 0:
            _blob(mb, -0.3, 0.35, h + 3.4, 0.85, 1, lod, squash=1.4, seed=23)
        mats = ["bark", "leaves_green"]

    elif kind == "shade_large":
        h = 4.2
        _trunk(mb, 0.52, 0.30, h, lod)
        nb = 4 if lod == 0 else (3 if lod == 1 else 2)
        for i in range(nb):
            _branch(mb, 0, 0, h * (0.55 + 0.12 * i), 3.4 * d, 0.20,
                    math.radians(46), i * 1.7 + 0.4, lod)
        _blob(mb, 0, 0, h + 1.7, 3.5, 1, lod, squash=0.62, seed=51)
        n = max(3, int(6 * d))
        for i in range(n):
            a = i * 1.9
            _blob(mb, 2.6 * math.cos(a), 2.6 * math.sin(a), h + 1.4 + 0.7 * _hash01(i, 6),
                  2.0 * (0.85 + 0.3 * _hash01(i, 8)), 1, lod, squash=0.7, seed=61 + i)
        mats = ["bark", "leaves_green"]

    elif kind == "scatter":
        h = 3.9
        _trunk(mb, 0.23, 0.13, h, lod)
        _blob(mb, 0, 0, h + 1.4, 2.0, 1, lod, seed=71)
        n = max(2, int(3 * d))
        for i in range(n):
            a = i * 2.1 + 0.9
            _blob(mb, 1.3 * math.cos(a), 1.3 * math.sin(a), h + 0.9 + 0.5 * _hash01(i, 12),
                  1.35 * (0.85 + 0.3 * _hash01(i, 14)), 1, lod, seed=81 + i)
        mats = ["bark", "leaves_dark"]

    elif kind == "shrub":
        r = 0.95
        n = 3 if lod == 0 else 2
        for i in range(n):
            a = i * 2.3
            _blob(mb, 0.55 * math.cos(a), 0.55 * math.sin(a), 0.62 + 0.2 * _hash01(i, 15),
                  r * (0.85 + 0.3 * _hash01(i, 16)), 1, lod, squash=0.85,
                  jitter=0.2, seed=91 + i)
        if lod == 0:
            _blob(mb, 0.1, -0.2, 1.15, 0.7, 1, lod, squash=0.8, jitter=0.2, seed=97)
        mats = ["bark", "leaves_dark"]

    elif kind == "reed":
        blades = 7 if lod == 0 else 5
        for i in range(blades):
            a = i * 0.9 + 0.3
            hh = 1.15 + 0.45 * _hash01(i, 21)
            lean = 0.28 * (_hash01(i, 22) - 0.5) * 2.0
            w = 0.075
            V, F = [], []
            segs = 4 if lod == 0 else 3
            for k in range(segs + 1):
                t = k / float(segs)
                z = hh * t
                xx = lean * t * t
                ww = w * (1.0 - 0.75 * t)
                V.append((xx - ww, 0.0, z))
                V.append((xx + ww, 0.0, z))
            for k in range(segs):
                i0 = k * 2
                F.append((i0, i0 + 1, i0 + 3, i0 + 2))
            mb.add(V, F, 0, T(0, 0, 0) @ RZ(a))
        mats = ["leaves_dark"]

    else:
        raise RuntimeError("unknown tree kind %r" % kind)

    return mb, mats


TREE_KINDS = ["broadleaf_tall", "broadleaf_small", "conifer", "palm",
              "street_columnar", "shade_large", "scatter", "shrub", "reed"]
TREE_L = [[], [], []]      # TREE_L[lod][idx] -> object


# --------------------------------------------------------------------------
# prop kit
# --------------------------------------------------------------------------
def bench_mesh():
    mb = MB()
    for i in range(3):
        mb.add(*prim_box(0.0, -0.16 + i * 0.16, 0.45, 1.7, 0.14, 0.05), 1)
    for i in range(2):
        mb.add(*prim_box(0.0, -0.26, 0.62 + i * 0.17, 1.7, 0.05, 0.15), 1)
    for sx in (-0.72, 0.72):
        mb.add(*prim_box(sx, -0.18, 0.22, 0.08, 0.08, 0.44), 0)
        mb.add(*prim_box(sx, -0.24, 0.62, 0.08, 0.08, 0.45), 0)
    return mb, ["metal_painted_dark", "wood_old"]


def bin_mesh():
    mb = MB()
    mb.add(*prim_cyl(8, 0.26, 0.23, 0.85), 0)
    mb.add(*prim_cyl(8, 0.30, 0.30, 0.06), 1, T(0, 0, 0.85))
    return mb, ["metal_painted_dark", "metal_steel"]


def hedge_mesh():
    mb = MB()
    mb.add(*prim_box(0, 0, 0.42, 5.0, 0.85, 0.84), 0)
    mb.add(*prim_box(0, 0, 0.88, 4.7, 0.7, 0.16), 0)
    return mb, ["leaves_dark"]


def flowerbed_mesh(r=3.5):
    mb = MB()
    mb.add(*prim_disc(r, 0.16, 20), 0)
    return mb, ["grass_dry"]


def planter_mesh():
    mb = MB()
    mb.add(*prim_box(0, 0, 0.3, 1.6, 1.6, 0.6), 0)
    mb.add(*prim_box(0, 0, 0.63, 1.3, 1.3, 0.08), 1)
    return mb, ["wood_old", "dirt"]


def stone_mesh():
    mb = MB()
    V, F = prim_sphere(9, 6, 1.0, 0.62, jitter=0.22, seed=5)
    mb.add(V, F, 0, T(0, 0, 0.45))
    return mb, ["gravel"]


def fence_seg_mesh():
    """2.4 m of low rail fence, +Y = along the fence line, faces +Y"""
    mb = MB()
    for sx in (-1.2, 1.2):
        mb.add(*prim_box(sx, 0, 0.5, 0.09, 0.09, 1.0), 0)
    for z in (0.45, 0.78):
        mb.add(*prim_box(0, 0, z, 2.4, 0.06, 0.07), 1)
    return mb, ["metal_painted_dark", "wood_old"]


def path_seg_mesh():
    mb = MB()
    mb.add(*prim_box(0, 0, 0.06, 1.9, 1.9, 0.12), 0)
    return mb, ["paving_slab"]


# ---- playground kit -------------------------------------------------------
def play_pad_mesh(sx=15.0, sy=11.0):
    """rubber/floor pad — 0.3 m thick so it reads as a poured pad over the lawn"""
    mb = MB()
    mb.add(*prim_box(0, 0, -0.15, sx, sy, 0.3), 0)
    return mb, ["floor_tile"]


def play_swing_mesh():
    mb = MB()
    for sx in (-1.9, 1.9):
        for sgn in (-1, 1):
            mb.add(*prim_box(sx, 0, 1.1, 0.12, 0.12, 2.4), 0,
                   T(0, sgn * 0.5, 0) @ RX(math.radians(sgn * 12)) @ T(-sx, 0, 0))
        # A-frame cross bar
        mb.add(*prim_box(sx, 0, 2.3, 0.14, 1.3, 0.14), 0)
    mb.add(*prim_box(0, 0, 2.45, 4.2, 0.16, 0.16), 0)
    for sx in (-1.0, 1.0):
        for z in (1.35, 1.15):
            mb.add(*prim_box(sx, 0, z, 0.035, 0.035, 1.15), 1)
        mb.add(*prim_box(sx, 0, 0.78, 0.5, 0.3, 0.06), 2)
    return mb, ["metal_painted_dark", "metal_steel", "wood_old"]


def play_slide_mesh():
    mb = MB()
    for sx in (-0.9, 0.9):
        for sy in (-0.9, 0.9):
            mb.add(*prim_box(sx, sy, 0.85, 0.14, 0.14, 1.7), 0)
    mb.add(*prim_box(0, 0, 1.75, 2.1, 2.1, 0.12), 1)
    mb.add(*prim_box(0, 0, 2.55, 2.3, 2.3, 0.1), 0)
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            mb.add(*prim_box(sx, sy, 2.15, 0.1, 0.1, 0.8), 0)
    # slide chute
    mb.add(*prim_box(0, 2.1, 0.95, 1.0, 2.6, 0.1), 2,
           T(0, 0, 0) @ RX(math.radians(-26)) @ T(0, -1.0, 0))
    for sx in (-0.5, 0.5):
        mb.add(*prim_box(sx, 2.1, 1.2, 0.1, 2.6, 0.35), 0,
               T(0, 0, 0) @ RX(math.radians(-26)) @ T(0, -1.0, 0))
    # ladder
    for k in range(5):
        mb.add(*prim_box(0, -1.35, 0.35 + k * 0.32, 0.9, 0.08, 0.07), 1)
    return mb, ["metal_painted_dark", "wood_old", "metal_steel"]


def play_climb_mesh():
    mb = MB()
    for sx in (-1.6, 1.6):
        for sy in (-1.2, 1.2):
            mb.add(*prim_box(sx, sy, 1.0, 0.12, 0.12, 2.0), 0)
    for k in range(5):
        z = 0.45 + k * 0.38
        mb.add(*prim_box(0, -1.2, z, 3.3, 0.07, 0.07), 1)
        mb.add(*prim_box(0, 1.2, z, 3.3, 0.07, 0.07), 1)
    for x in [-1.2, -0.6, 0.0, 0.6, 1.2]:
        mb.add(*prim_box(x, 0, 1.95, 0.07, 2.5, 0.07), 1)
    for sy in (-0.6, 0.0, 0.6):
        mb.add(*prim_box(0, sy, 1.2, 3.3, 0.07, 0.07), 1)
    return mb, ["metal_painted_dark", "metal_steel"]


def play_seesaw_mesh():
    mb = MB()
    mb.add(*prim_box(0, 0, 0.35, 0.5, 0.5, 0.7), 0)
    mb.add(*prim_box(0, 0, 0.78, 3.6, 0.28, 0.14), 1, RX(math.radians(7)))
    for sx in (-1.7, 1.7):
        mb.add(*prim_box(sx, 0, 1.02, 0.45, 0.4, 0.08), 2, RX(math.radians(7)))
        mb.add(*prim_box(sx * 0.9, 0, 1.3, 0.06, 0.5, 0.06), 0, RX(math.radians(7)))
    return mb, ["metal_painted_dark", "wood_old", "metal_steel"]


def play_spring_mesh():
    mb = MB()
    mb.add(*prim_cyl(6, 0.12, 0.12, 0.5), 0, T(0, 0, 0))
    mb.add(*prim_box(0, 0, 0.68, 0.9, 0.35, 0.36), 1)
    mb.add(*prim_box(0.42, 0, 0.8, 0.3, 0.3, 0.24), 1)
    return mb, ["metal_steel", "wood_painted"]


def play_sandbox_mesh():
    mb = MB()
    for sx, sy, sxx, syy in ((0, -1.6, 3.6, 0.3), (0, 1.6, 3.6, 0.3),
                             (-1.65, 0, 0.3, 3.0), (1.65, 0, 0.3, 3.0)):
        mb.add(*prim_box(sx, sy, 0.18, sxx, syy, 0.36), 0)
    mb.add(*prim_box(0, 0, 0.1, 3.0, 2.9, 0.2), 1)
    return mb, ["wood_old", "sand"]


# --------------------------------------------------------------------------
# geometry helpers : polygons, ribbons, rings
# --------------------------------------------------------------------------
def poly_centroid(poly):
    sx = sum(p[0] for p in poly) / len(poly)
    sy = sum(p[1] for p in poly) / len(poly)
    return sx, sy


def point_in_poly(x, y, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            xint = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < xint:
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
        t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / l2))
        px, py = x1 + t * dx, y1 + t * dy
        d = math.hypot(x - px, y - py)
        if d < best:
            best = d
    return best


def ring_points(poly, d, sub=1):
    """points pushed `d` metres along the OUTWARD normal, `sub` samples per edge"""
    cx, cy = poly_centroid(poly)
    out = []
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        ex, ey = x2 - x1, y2 - y1
        el = math.hypot(ex, ey) or 1.0
        nx, ny = ey / el, -ex / el
        mx, my = x1 + ex * 0.5, y1 + ey * 0.5
        if (mx + nx - cx) ** 2 + (my + ny - cy) ** 2 < (mx - cx) ** 2 + (my - cy) ** 2:
            nx, ny = -nx, -ny
        for k in range(sub):
            t = (k + 0.5) / sub
            px, py = x1 + ex * t, y1 + ey * t
            out.append((px + nx * d, py + ny * d, nx, ny))
    return out


def shore_band(mb, poly, d0, d1, zfun, steps=4, sub=4):
    """radially + longitudinally subdivided band that hugs the shore terrain"""
    rings = [ring_points(poly, d0 + (d1 - d0) * k / float(steps), sub)
             for k in range(steps + 1)]
    for k in range(steps):
        band(mb, rings[k], rings[k + 1], zfun)


def ribbon(mb, pts, width, zfun, closed=False, mi=0):
    """quad strip of `width` centred on polyline pts; zfun(x,y)->z"""
    n = len(pts)
    if n < 2:
        return
    left, right = [], []
    for i in range(n):
        if closed:
            p0, p1 = pts[(i - 1) % n], pts[(i + 1) % n]
        else:
            p0 = pts[max(0, i - 1)]
            p1 = pts[min(n - 1, i + 1)]
        tx, ty = p1[0] - p0[0], p1[1] - p0[1]
        tl = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / tl, tx / tl
        x, y = pts[i]
        hw = width / 2.0
        left.append((x + nx * hw, y + ny * hw))
        right.append((x - nx * hw, y - ny * hw))
    V, F = [], []
    for p in left:
        V.append((p[0], p[1], zfun(p[0], p[1])))
    for p in right:
        V.append((p[0], p[1], zfun(p[0], p[1])))
    lim = n if closed else n - 1
    for i in range(lim):
        j = (i + 1) % n
        F.append((i, j, n + j, n + i))
    mb.add(V, F, mi)


def band(mb, ring_a, ring_b, zfun, mi=0):
    """quad strip between two polylines of equal length"""
    n = len(ring_a)
    if len(ring_b) != n or n < 2:
        return
    V = [(p[0], p[1], zfun(p[0], p[1])) for p in ring_a]
    V += [(p[0], p[1], zfun(p[0], p[1])) for p in ring_b]
    F = []
    for i in range(n - 1):
        F.append((i, i + 1, n + i + 1, n + i))
    mb.add(V, F, mi)


def rect_ring(cx, cy, hx, hy, step=8.0):
    """closed polyline around a rectangle (inset), resampled every `step`"""
    pts = []
    corners = [(cx - hx, cy - hy), (cx + hx, cy - hy), (cx + hx, cy + hy), (cx - hx, cy + hy)]
    for i in range(4):
        x0, y0 = corners[i]
        x1, y1 = corners[(i + 1) % 4]
        seg = math.hypot(x1 - x0, y1 - y0)
        k = max(1, int(round(seg / step)))
        for j in range(k):
            t = j / float(k)
            pts.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    return pts


def serpentine(x0, y0, x1, y1, amp, phase=0.0, waves=1.5, step=6.0):
    """points from (x0,y0) to (x1,y1) with a sine offset on the perpendicular axis"""
    pts = []
    dx, dy = x1 - x0, y1 - y0
    Lg = math.hypot(dx, dy)
    if Lg < 1:
        return pts
    ux, uy = dx / Lg, dy / Lg
    px, py = -uy, ux
    n = max(2, int(Lg / step))
    for i in range(n + 1):
        t = i / float(n)
        s = t * Lg
        o = amp * math.sin(t * waves * 2.0 * math.pi + phase)
        pts.append((x0 + ux * s + px * o, y0 + uy * s + py * o))
    return pts


def dist_to_polyline(x, y, pts, closed=True):
    best = 1e18
    n = len(pts)
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        l2 = dx * dx + dy * dy
        t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / l2))
        d = math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))
        if d < best:
            best = d
    return best


# --------------------------------------------------------------------------
# scene setup
# --------------------------------------------------------------------------
def purge_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    for me in list(bpy.data.meshes):
        if me.users == 0:
            bpy.data.meshes.remove(me)


def setup():
    global TOP, C_MESH, C_COLL, C_LIGHT, C_STREET, C_PARK, C_PROP, C_PLAY, C_LAKE, C_COL
    purge_scene()
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    TOP = ck.ensure_collection("Nature")
    C_MESH = ck.ensure_collection("Meshes", TOP)
    C_STREET = ck.ensure_collection("StreetTrees", TOP)
    C_PARK = ck.ensure_collection("Parks", TOP)
    C_PROP = ck.ensure_collection("Props", TOP)
    C_PLAY = ck.ensure_collection("Playground", TOP)
    C_LAKE = ck.ensure_collection("Lake", TOP)
    C_COLL = ck.ensure_collection("Colliders", TOP)
    C_LIGHT = ck.ensure_collection("Lights", TOP)
    print("[nature] setup ok — collections under Nature/")


def stage(name):
    dt = time.time() - T0
    STAGE_TIMES.append((name, dt))
    path = ck.save_blend(os.path.join(ck.OUT_DIR, "nature.blend"))
    print("[nature] STAGE %-12s t=%6.1fs objects=%d tris(unique)=%d -> %s"
          % (name, dt, len(bpy.data.objects), ck.scene_tri_count(), path))


# --------------------------------------------------------------------------
# 1. KIT
# --------------------------------------------------------------------------
def build_kit():
    for lod in range(3):
        for k, kind in enumerate(TREE_KINDS):
            mb, mats = tree_mesh(kind, lod)
            name = ("SM_Tree_%s_01" % kind) if lod == 0 else \
                   ("%d_SM_Tree_%s_01" % (lod, kind))
            ob = mesh_object(name, mb, mats, C_MESH, hidden=True)
            tris = ck.tri_count(ob)
            if lod == 0 and tris > 8000:
                raise RuntimeError("kit %s exceeds 8k tris (%d)" % (name, tris))
            TREE_L[lod].append(ob)
            N["kit_meshes"] += 1
            N["kit_tris"] += tris
            KIT_ROWS.append((name, tris, len(ob.data.polygons) and len(ob.data.vertices)))
    # props
    props = []
    for nm, fn in (("SM_Prop_Bench_01", bench_mesh), ("SM_Prop_Bin_01", bin_mesh),
                   ("SM_Prop_Hedge_01", hedge_mesh), ("SM_Prop_Planter_01", planter_mesh),
                   ("SM_Prop_Stone_01", stone_mesh), ("SM_Prop_FenceSeg_01", fence_seg_mesh)):
        mb, mats = fn()
        ob = mesh_object(nm, mb, mats, C_MESH, hidden=True)
        props.append(ob)
        N["kit_meshes"] += 1
        N["kit_tris"] += ck.tri_count(ob)
        KIT_ROWS.append((nm, ck.tri_count(ob), 0))
    for r, tag in ((3.5, "S"), (5.0, "L")):
        mb, mats = flowerbed_mesh(r)
        ob = mesh_object("SM_Prop_Flowerbed_%s" % tag, mb, mats, C_MESH, hidden=True)
        N["kit_meshes"] += 1
        N["kit_tris"] += ck.tri_count(ob)
    # playground
    for nm, fn in (("SM_Play_Pad_01", lambda: play_pad_mesh()),
                   ("SM_Play_Swing_01", play_swing_mesh),
                   ("SM_Play_Slide_01", play_slide_mesh),
                   ("SM_Play_Climb_01", play_climb_mesh),
                   ("SM_Play_Seesaw_01", play_seesaw_mesh),
                   ("SM_Play_Spring_01", play_spring_mesh),
                   ("SM_Play_Sandbox_01", play_sandbox_mesh)):
        mb, mats = fn()
        ob = mesh_object(nm, mb, mats, C_MESH, hidden=True)
        N["kit_meshes"] += 1
        N["kit_tris"] += ck.tri_count(ob)
        KIT_ROWS.append((nm, ck.tri_count(ob), 0))
    # collider proxy: unit cylinder (r=1, h=1, base at z=0), open (no caps)
    mb = MB()
    mb.add(*prim_cyl(6, 1.0, 1.0, 1.0, cap_bottom=False, cap_top=False), 0)
    mesh_object("COL_TreeProxy_01", mb, ["bark"], C_MESH, hidden=True)
    N["kit_meshes"] += 1
    print("[nature] kit: %d meshes, %d tris (LOD0 tree tris: %s)"
          % (N["kit_meshes"], N["kit_tris"],
             ", ".join("%s=%d" % (n, t) for n, t, _ in KIT_ROWS if n.startswith("SM_Tree"))))


def kit_pick(lod, kind):
    return TREE_L[lod][TREE_KINDS.index(kind)]


# --------------------------------------------------------------------------
# spatial index of buildable rects
# --------------------------------------------------------------------------
BUILD_BUCKETS = {}
PARK_RECTS = []


def build_index():
    for d in ("R", "D", "E", "G"):
        for p in ck.read_parcels(d):
            br = p.get("buildable_rect")
            if not br:
                continue
            x0, y0, x1, y1 = br
            for bx in range(int(x0 // 100), int(x1 // 100) + 1):
                for by in range(int(y0 // 100), int(y1 // 100) + 1):
                    BUILD_BUCKETS.setdefault((bx, by), []).append(br)
    for pk in PARK_PARCELS:
        x0, y0, x1, y1 = pk["rect"]
        PARK_RECTS.append((x0, y0, x1, y1))


def in_buildable(x, y):
    for br in BUILD_BUCKETS.get((int(x // 100), int(y // 100)), ()):
        if br[0] <= x <= br[2] and br[1] <= y <= br[3]:
            return True
    return False


def in_park(x, y):
    for r in PARK_RECTS:
        if r[0] <= x <= r[2] and r[1] <= y <= r[3]:
            return True
    return False


def check_point(x, y, tag):
    if in_buildable(x, y) and not in_park(x, y):
        N["suppressed_buildable"] += 1
        if len(VIOLATIONS) < 40:
            VIOLATIONS.append((tag, round(x, 2), round(y, 2)))
        return True
    return False


# --------------------------------------------------------------------------
# 2. STREET TREES
# --------------------------------------------------------------------------
def district_of_edge(e, a, b):
    if e.get("district"):
        return e["district"]
    mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
    cx = int((mx - EXT) // PITCH)
    cy = int((my - EXT) // PITCH)
    if 0 <= cx < len(PARK_ROWS[0]) and 0 <= cy < len(PARK_ROWS):
        return PARK_ROWS[len(PARK_ROWS) - 1 - cy][cx]
    return None


SPECIES_BY_DISTRICT = {
    "R": ["broadleaf_tall", "broadleaf_small", "broadleaf_tall", "conifer"],
    "D": ["street_columnar", "street_columnar", "broadleaf_small"],
    "E": ["broadleaf_tall", "palm", "broadleaf_small", "street_columnar"],
    "G": ["broadleaf_tall", "conifer", "shade_large", "broadleaf_small"],
}


def build_street_trees():
    placed = 0
    for e in ck.read_road_edges():
        if e["hierarchy"] not in ST_HIER:
            continue
        a = tuple(NODES[e["a"]]["pos"][:2])
        b = tuple(NODES[e["b"]]["pos"][:2])
        dd = district_of_edge(e, a, b)
        if dd not in ST_DISTRICTS:
            continue
        dx, dy = b[0] - a[0], b[1] - a[1]
        Lg = math.hypot(dx, dy)
        if Lg < 4:
            continue
        ux, uy = dx / Lg, dy / Lg
        px, py = -uy, ux
        off = e["width"] / 2.0 + ST_OFFSET
        pool = SPECIES_BY_DISTRICT.get(dd, SPECIES_BY_DISTRICT["R"])
        t = ST_SKIP
        while t <= Lg - ST_SKIP:
            for side in (1.0, -1.0):
                x = a[0] + ux * t + px * side * off
                y = a[1] + uy * t + py * side * off
                if min((x - nx) ** 2 + (y - ny) ** 2 for nx, ny in NODE_POS) < ST_SKIP ** 2:
                    continue
                if check_point(x, y, "street:" + e["id"]):
                    continue
                kind = pool[int(RND.random() * len(pool)) % len(pool)]
                r = RND.random()
                lod = 0 if r < 0.15 else (1 if r < 0.65 else 2)
                src = kit_pick(lod, kind)
                s = RND.uniform(0.85, 1.25)
                inst(src, C_STREET, "SM_TreeStreet_%s_%05d" % (kind[:6], placed),
                     x, y, 0.0, rot=RND.uniform(0, 6.283), s=s)
                placed += 1
            t += ST_SPACING
    N["street_trees"] = placed
    print("[nature] street trees: %d placed" % placed)


# --------------------------------------------------------------------------
# 3. PARKS
# --------------------------------------------------------------------------
def make_park_terrain(pk, lake=None):
    x0, y0, x1, y1 = pk["rect"]
    hx, hy = (x1 - x0) / 2.0, (y1 - y0) / 2.0
    cx, cy = pk["center"]
    n = max(10, int(min((x1 - x0), (y1 - y0)) / 9.0))
    if lake:
        n = max(n, 36)          # the 16 m shore ramp needs a finer grid
    seed = sum(ord(c) for c in pk["id"]) % 97

    def taper(x, y):
        d = min(x - x0, x1 - x, y - y0, y1 - y)
        return max(0.0, min(1.0, d / 7.0))

    def hump(x, y):
        h = (math.sin(x / 47.0 + seed) * math.cos(y / 53.0 - seed * 0.7)
             + 0.6 * math.sin((x + y) / 29.0 + seed * 1.3)
             + 0.5 * math.cos((x - y) / 61.0 - seed))
        return max(0.0, min(1.0, (h + 2.1) / 4.2))

    def zfun(x, y):
        t = taper(x, y)
        z = 0.02 + 0.03 * t + 0.30 * hump(x, y) * t
        if lake:
            d = dist_to_poly(x, y, lake)
            if point_in_poly(x, y, lake):
                z = -3.0
            elif d < 16.0:
                z = z - 3.05 * (1.0 - d / 16.0)
        return z

    mb = MB()
    V = []
    for j in range(n + 1):
        y = y0 + (y1 - y0) * j / float(n)
        for i in range(n + 1):
            x = x0 + (x1 - x0) * i / float(n)
            V.append((x, y, zfun(x, y)))
    F, FMI = [], []
    for j in range(n):
        for i in range(n):
            a = j * (n + 1) + i
            F.append((a, a + 1, a + n + 2, a + n + 1))
            fcx = x0 + (x1 - x0) * (i + 0.5) / float(n)
            fcy = y0 + (y1 - y0) * (j + 0.5) / float(n)
            near_shore = lake and dist_to_poly(fcx, fcy, lake) < 11.0
            FMI.append(1 if near_shore else 0)
    mb.v = V
    mb.f = F
    mb.m = FMI
    ob = mesh_object("SM_ParkTerrain_%s" % pk["id"], mb, ["grass", "dirt"], C_PARK)
    ck.apply_all_transforms(ob)
    N["terrain_faces"] += len(F)
    pk["_zfun"] = zfun
    return zfun


def build_parks():
    big_play = ["PK_0_0", "PK_1_1", "PK_2_1", "PK_4_1", "PK_1_2"]
    for pk in PARK_PARCELS:
        x0, y0, x1, y1 = pk["rect"]
        cx, cy = pk["center"]
        w, h = pk["size"]
        if pk["type"] == "central_plaza":
            build_plaza(pk)
            continue
        lake = LAKE_POLY if "lake" in pk["features"] else None
        zfun = make_park_terrain(pk, lake)
        inset = 10.0 if min(w, h) > 200 else 6.0
        ring = rect_ring(cx, cy, w / 2 - inset, h / 2 - inset, step=8.0)

        # playground footprint reserved here, the kit is built in build_playgrounds()
        play_pos = None
        if pk["id"] in big_play:
            ppx, ppy = cx + w * 0.27, cy - h * 0.27
            if x0 + 14 < ppx < x1 - 14 and y0 + 14 < ppy < y1 - 14:
                play_pos = (ppx, ppy)
                pk["_play"] = play_pos

        # ---- path network
        pm = MB()
        ribbon(pm, ring, 2.0, lambda x, y: zfun(x, y) + 0.05, closed=True)
        hpath = serpentine(x0 + 2, cy, x1 - 2, cy, amp=h * 0.16, phase=RND.uniform(0, 6.28))
        vpath = serpentine(cx, y0 + 2, cx, y1 - 2, amp=w * 0.16, phase=RND.uniform(0, 6.28))
        for pl in (hpath, vpath):
            keep = [p for p in pl if not (lake and point_in_poly(p[0], p[1], lake))]
            for i in range(0, len(keep) - 1, 6):
                ribbon(pm, keep[i:i + 7], 2.0, lambda x, y: zfun(x, y) + 0.05, closed=False)
        pob = mesh_object("SM_ParkPath_%s" % pk["id"], pm, ["paving_slab"], C_PARK)
        ck.apply_all_transforms(pob)
        N["path_segments"] += len(pm.f)
        polylines = [ring, hpath, vpath]

        # ---- shade trees (few large)
        n_shade = 4 if min(w, h) > 200 else 2
        shade_pts = []
        for i in range(n_shade):
            for _try in range(30):
                x = RND.uniform(x0 + 14, x1 - 14)
                y = RND.uniform(y0 + 14, y1 - 14)
                if min(dist_to_polyline(x, y, pl) for pl in polylines) < 7:
                    continue
                if lake and (point_in_poly(x, y, lake) or dist_to_poly(x, y, lake) < 26):
                    continue
                if play_pos and math.hypot(x - play_pos[0], y - play_pos[1]) < 16:
                    continue
                if check_point(x, y, "shade:" + pk["id"]):
                    continue
                shade_pts.append((x, y))
                break
        for i, (x, y) in enumerate(shade_pts):
            src = kit_pick(0 if RND.random() < 0.6 else 1, "shade_large")
            inst(src, C_PARK, "SM_TreeShade_%s_%02d" % (pk["id"], i),
                 x, y, zfun(x, y), rot=RND.uniform(0, 6.283), s=RND.uniform(0.9, 1.3))
            N["shade_trees"] += 1

        # ---- flowerbeds
        for i in range(4 if min(w, h) > 200 else 2):
            for _try in range(30):
                x = RND.uniform(x0 + 16, x1 - 16)
                y = RND.uniform(y0 + 16, y1 - 16)
                if min(dist_to_polyline(x, y, pl) for pl in polylines) < 7:
                    continue
                if any(math.hypot(x - sx, y - sy) < 9 for sx, sy in shade_pts):
                    continue
                if lake and (point_in_poly(x, y, lake) or dist_to_poly(x, y, lake) < 26):
                    continue
                if play_pos and math.hypot(x - play_pos[0], y - play_pos[1]) < 16:
                    continue
                if check_point(x, y, "bed:" + pk["id"]):
                    continue
                src = bpy.data.objects["SM_Prop_Flowerbed_%s" % ("S" if i % 2 == 0 else "L")]
                inst(src, C_PROP, "SM_Flowerbed_%s_%02d" % (pk["id"], i),
                     x, y, zfun(x, y) - 0.02, rot=RND.uniform(0, 6.283))
                N["flowerbeds"] += 1
                break

        # ---- park scatter (density from vegetation_rules)
        area = w * h
        target = int(area * PARK_DENSITY / 100.0)
        cap = PARK_CAP_LARGE if min(w, h) > 200 else PARK_CAP_SMALL
        target = min(target, cap)
        cell = math.sqrt(area / float(max(1, target)))
        placed = 0
        tries = 0
        while placed < target and tries < target * 6:
            tries += 1
            x = RND.uniform(x0 + 5, x1 - 5)
            y = RND.uniform(y0 + 5, y1 - 5)
            if min(dist_to_polyline(x, y, pl) for pl in polylines) < 3.4:
                continue
            if any(math.hypot(x - sx, y - sy) < 7 for sx, sy in shade_pts):
                continue
            if lake and (point_in_poly(x, y, lake) or dist_to_poly(x, y, lake) < 20):
                continue
            if play_pos and math.hypot(x - play_pos[0], y - play_pos[1]) < 15:
                continue
            if check_point(x, y, "scatter:" + pk["id"]):
                continue
            lod = 0 if RND.random() < 0.10 else (1 if RND.random() < 0.78 else 2)
            kind = "scatter" if RND.random() < 0.7 else (
                "broadleaf_small" if RND.random() < 0.6 else "conifer")
            inst(kit_pick(lod, kind), C_PARK, "SM_TreePark_%s_%04d" % (kind[:6], placed),
                 x, y, zfun(x, y), rot=RND.uniform(0, 6.283), s=RND.uniform(0.85, 1.25))
            placed += 1
        N["park_trees"] += placed

        # ---- benches + bins along the ring
        bench_src = bpy.data.objects["SM_Prop_Bench_01"]
        bin_src = bpy.data.objects["SM_Prop_Bin_01"]
        hedge_src = bpy.data.objects["SM_Prop_Hedge_01"]
        k = 0
        for i in range(0, len(ring), 3):        # ring resampled every 8 m -> 24 m steps
            x, y = ring[i]
            nx = cx - x
            ny = cy - y
            nl = math.hypot(nx, ny) or 1.0
            nx, ny = nx / nl, ny / nl          # inward (towards park centre)
            bx, by = x - nx * 1.7, y - ny * 1.7   # just inside the ring, facing the path
            if k % 4 == 0:
                if not check_point(bx, by, "bench:" + pk["id"]):
                    inst(bench_src, C_PROP, "SM_Bench_%s_%03d" % (pk["id"], i),
                         bx, by, zfun(bx, by), rot=math.atan2(nx, -ny))
                    N["benches"] += 1
            elif k % 4 == 2:
                if not check_point(bx, by, "bin:" + pk["id"]):
                    inst(bin_src, C_PROP, "SM_Bin_%s_%03d" % (pk["id"], i),
                         bx, by, zfun(bx, by), rot=RND.uniform(0, 6.283),
                         s=RND.uniform(0.9, 1.15))
                    N["bins"] += 1
            k += 1

        # ---- low hedges along the border
        if min(w, h) > 100:
            border = rect_ring(cx, cy, w / 2 - 4.5, h / 2 - 4.5, step=8.0)
            for i in range(0, len(border), 2):
                x, y = border[i]
                if check_point(x, y, "hedge:" + pk["id"]):
                    continue
                px, py = border[(i + 1) % len(border)]
                rot = math.atan2(py - y, px - x)
                inst(hedge_src, C_PROP, "SM_Hedge_%s_%03d" % (pk["id"], i),
                     x, y, zfun(x, y), rot=rot, s=0.98)
                N["hedges"] += 1

        # ---- reeds + gravel band (central park) / lake shore handled in lake stage
        if pk["id"] == "LM_CENTRAL_PARK" or pk["id"] == "PK_2_1":
            reed_bed(pk, zfun, cx, cy, w, h)

        if pk["id"] in big_play:
            PLAYGROUND_PARKS.append(pk)

    print("[nature] parks: %d terrains, %d path faces, scatter=%d shade=%d "
          "benches=%d bins=%d hedges=%d beds=%d"
          % (sum(1 for p in PARK_PARCELS if p.get("_zfun")), N["path_segments"],
             N["park_trees"], N["shade_trees"], N["benches"], N["bins"],
             N["hedges"], N["flowerbeds"]))


PLAYGROUND_PARKS = []


def build_plaza(pk):
    """central plaza: hardscape belongs to another agent — only trees in grates"""
    x0, y0, x1, y1 = pk["rect"]
    pts = [(x0 + 14, y0 + 14), (x1 - 14, y0 + 14), (x0 + 14, y1 - 14),
           (x1 - 14, y1 - 14), (x0 + 14, (y0 + y1) / 2), (x1 - 14, (y0 + y1) / 2)]
    for i, (x, y) in enumerate(pts):
        if check_point(x, y, "plaza:" + pk["id"]):
            continue
        inst(kit_pick(0 if i % 2 == 0 else 1, "shade_large"), C_PARK,
             "SM_TreePlaza_%02d" % i, x, y, 0.0, rot=RND.uniform(0, 6.283),
             s=RND.uniform(0.85, 1.1))
        N["plaza_trees"] += 1
    print("[nature] central plaza trees: %d" % N["plaza_trees"])


def reed_bed(pk, zfun, cx, cy, w, h):
    """gravel + reed band in the central park"""
    zfun_path = lambda x, y: zfun(x, y)
    pts = serpentine(cx - w * 0.34, cy - h * 0.36, cx + w * 0.34, cy - h * 0.30,
                     amp=h * 0.05, phase=1.1, step=5.0)
    g = MB()
    band(g, [(x, y - 4.5) for x, y in pts], [(x, y + 4.5) for x, y in pts],
         lambda x, y: zfun_path(x, y) + 0.04)
    gob = mesh_object("SM_ReedGravel_%s" % pk["id"], g, ["gravel"], C_PARK)
    ck.apply_all_transforms(gob)
    reed_src = kit_pick(1, "reed")
    for i in range(len(pts)):
        for s in (-1, 1):
            if RND.random() < 0.55:
                x = pts[i][0] + RND.uniform(-1.5, 1.5)
                y = pts[i][1] + s * RND.uniform(2.5, 5.5)
                if check_point(x, y, "reed:" + pk["id"]):
                    continue
                inst(reed_src, C_PARK, "SM_Reed_%03d" % i, x, y,
                     zfun_path(x, y), rot=RND.uniform(0, 6.283),
                     s=RND.uniform(0.8, 1.3), sz=RND.uniform(0.8, 1.4))
                N["reed_instances"] += 1


# --------------------------------------------------------------------------
# 4. LAKE
# --------------------------------------------------------------------------
def build_lake():
    poly = LAKE_POLY
    cx, cy = poly_centroid(poly)
    z_water = -0.3

    # water surface (triangulated fan)
    mb = MB()
    V = [(cx, cy, z_water)] + [(x, y, z_water) for x, y in poly]
    F = []
    n = len(poly)
    for i in range(n):
        F.append((0, 1 + i, 1 + (i + 1) % n))
    mb.v, mb.f, mb.m = V, F, [0] * len(F)
    mesh_object("SM_Lake_Water_01", mb, ["water"], C_LAKE)
    ck.apply_all_transforms(bpy.data.objects["SM_Lake_Water_01"])

    # shoreline gravel band (d 13 -> 21) — uses the SAME terrain function as the
    # park terrain mesh so the band never floats or sinks
    park = next(p for p in PARK_PARCELS if "lake" in p["features"])
    x0, y0, x1, y1 = park["rect"]
    zfun = park["_zfun"]

    g = MB()
    shore_band(g, poly, 13.0, 21.0, lambda x, y: zfun(x, y) + 0.05, steps=5, sub=4)
    gob = mesh_object("SM_Lake_ShoreGravel_01", g, ["gravel"], C_LAKE)
    ck.apply_all_transforms(gob)

    # shore path (closed ring at d=24) + fence at d=27
    pth = MB()
    ribbon(pth, [(p[0], p[1]) for p in ring_points(poly, 24.0, 6)], 2.0,
           lambda x, y: zfun(x, y) + 0.05, closed=True)
    pobj = mesh_object("SM_Lake_ShorePath_01", pth, ["paving_slab"], C_LAKE)
    ck.apply_all_transforms(pobj)

    fence_ring = ring_points(poly, 27.0, 4)
    fence_src = bpy.data.objects["SM_Prop_FenceSeg_01"]
    for i in range(len(fence_ring)):
        x, y, nx, ny = fence_ring[i]
        x2, y2, _, _ = fence_ring[(i + 1) % len(fence_ring)]
        gap = math.hypot(x2 - x, y2 - y)
        rot = math.atan2(y2 - y, x2 - x) - math.pi / 2
        if check_point(x, y, "fence:" + park["id"]):
            continue
        inst(fence_src, C_LAKE, "SM_Fence_%03d" % i, x, y, zfun(x, y),
             rot=rot, s=max(1.0, gap / 2.4), sz=1.0)
        N["fence_segments"] += 1

    # reeds just above / in the waterline + stones
    reed_src = kit_pick(1, "reed")
    stone_src = bpy.data.objects["SM_Prop_Stone_01"]
    for i in range(len(poly)):
        for k in range(7):
            d = RND.uniform(12.0, 19.0)
            rp = ring_points(poly, d)[i]
            x = rp[0] + RND.uniform(-4.0, 4.0)
            y = rp[1] + RND.uniform(-4.0, 4.0)
            if check_point(x, y, "lakereed:" + park["id"]):
                continue
            inst(reed_src, C_LAKE, "SM_ReedShore_%03d" % (i * 7 + k), x, y,
                 zfun(x, y), rot=RND.uniform(0, 6.283),
                 s=RND.uniform(0.85, 1.35), sz=RND.uniform(0.9, 1.6))
            N["reed_instances"] += 1
        if i % 2 == 0:
            rp = ring_points(poly, RND.uniform(15.0, 21.0))[i]
            if not check_point(rp[0], rp[1], "stone:" + park["id"]):
                inst(stone_src, C_LAKE, "SM_Stone_%03d" % i, rp[0], rp[1],
                     zfun(rp[0], rp[1]), rot=RND.uniform(0, 6.283),
                     s=RND.uniform(0.5, 1.4))
                N["stones"] += 1

    # bank planting: shrubs + a few trees between path and gravel
    shrub_src = kit_pick(1, "shrub")
    for i in range(len(poly) * 4):
        d = RND.uniform(22.0, 34.0)
        rp = ring_points(poly, d)
        r = rp[int(RND.random() * len(rp)) % len(rp)]
        x = r[0] + RND.uniform(-4.0, 4.0)
        y = r[1] + RND.uniform(-4.0, 4.0)
        if not (x0 + 4 < x < x1 - 4 and y0 + 4 < y < y1 - 4):
            continue
        if check_point(x, y, "bank:" + park["id"]):
            continue
        if RND.random() < 0.72:
            inst(shrub_src, C_LAKE, "SM_Shrub_%03d" % i, x, y, zfun(x, y),
                 rot=RND.uniform(0, 6.283), s=RND.uniform(0.8, 1.4))
            N["shrub_instances"] += 1
        else:
            inst(kit_pick(1 if RND.random() < 0.7 else 0, "broadleaf_tall"), C_LAKE,
                 "SM_TreeBank_%03d" % i, x, y, zfun(x, y),
                 rot=RND.uniform(0, 6.283), s=RND.uniform(0.85, 1.2))
            N["shore_trees"] += 1

    # ---- jetty on the northern shore, deck running out over the water
    best_i, best_ny = 0, -9.0
    ring0 = ring_points(poly, 0.0)
    for i, (x, y, nx, ny) in enumerate(ring0):
        if ny > best_ny:
            best_i, best_ny = i, ny
    sx, sy, nx, ny = ring_points(poly, 17.0)[best_i]   # dry land, ramp ends ~14.5 m
    jz = zfun(sx, sy)
    mbj = MB()
    length = 17.0
    wid = 2.4
    nk = 27
    for k in range(nk):
        yy = 0.4 + k * (length / nk)
        mbj.add(*prim_box(0, yy, 0.15, wid, 0.46, 0.07), 0)
    for yy in (1.0, 8.0, 15.5):
        for sxs in (-1.0, 1.0):
            mbj.add(*prim_box(sxs, yy, -0.7, 0.18, 0.18, 1.7), 1)
    for sxs in (-1.15, 1.15):
        mbj.add(*prim_box(sxs, length * 0.5, 0.46, 0.09, length - 1.6, 0.09), 0)
        for yy in (2.0, 8.5, 15.0):
            mbj.add(*prim_box(sxs, yy, 0.30, 0.09, 0.09, 0.32), 0)
    # local +Y must point INTO the lake (= -outward normal)
    rot = math.atan2(nx, -ny)
    job = mesh_object("SM_Lake_Jetty_01", mbj, ["wood_old", "wood_old"], C_LAKE)
    job.location = (sx, sy, jz)
    job.rotation_euler = (0, 0, rot)
    print("[nature] lake: reeds=%d stones=%d shrubs=%d shore_trees=%d fence=%d jetty"
          % (N["reed_instances"], N["stones"], N["shrub_instances"],
             N["shore_trees"], N["fence_segments"]))


# --------------------------------------------------------------------------
# 5. PLAYGROUNDS
# --------------------------------------------------------------------------
def build_playgrounds():
    pad_src = bpy.data.objects["SM_Play_Pad_01"]
    swing_src = bpy.data.objects["SM_Play_Swing_01"]
    slide_src = bpy.data.objects["SM_Play_Slide_01"]
    climb_src = bpy.data.objects["SM_Play_Climb_01"]
    seesaw_src = bpy.data.objects["SM_Play_Seesaw_01"]
    spring_src = bpy.data.objects["SM_Play_Spring_01"]
    sand_src = bpy.data.objects["SM_Play_Sandbox_01"]
    fence_src = bpy.data.objects["SM_Prop_FenceSeg_01"]
    bench_src = bpy.data.objects["SM_Prop_Bench_01"]

    clusters = 0
    for pk in PLAYGROUND_PARKS:
        if clusters >= 5:
            break
        x0, y0, x1, y1 = pk["rect"]
        w, h = pk["size"]
        cx = pk["center"][0] + w * 0.27
        cy = pk["center"][1] - h * 0.27
        if pk.get("_play"):
            cx, cy = pk["_play"]
        elif not (x0 + 14 < cx < x1 - 14 and y0 + 14 < cy < y1 - 14):
            cx, cy = pk["center"]
        if check_point(cx, cy, "play:" + pk["id"]):
            continue
        zfun = pk.get("_zfun")
        if zfun:
            z = max(zfun(cx + ox, cy + oy)
                    for ox in (-7.5, 0.0, 7.5) for oy in (-5.5, 0.0, 5.5)) + 0.02
        else:
            z = 0.05
        inst(pad_src, C_PLAY, "SM_PlayPad_%s" % pk["id"], cx, cy, z, s=1.0)
        N["play_objects"] += 1
        items = [
            # src, dx, dy, rot, scale, on_pad
            (slide_src, -4.6, 1.4, 0.0, 1.0, True),
            (swing_src, 3.6, -2.4, math.radians(90), 1.0, True),
            (climb_src, -3.2, -3.4, math.radians(25), 1.0, True),
            (seesaw_src, 4.4, 2.6, math.radians(-35), 1.0, True),
            (sand_src, 0.2, 3.6, 0.0, 1.0, True),
            (spring_src, -5.2, -1.0, 0.3, 1.0, True),
            (spring_src, -4.4, 3.0, 2.1, 0.9, True),
            (bench_src, 0.5, 8.4, math.pi, 1.0, False),
            (bench_src, -10.4, -0.5, -math.pi / 2, 1.0, False),
        ]
        for src, ox, oy, rot, sc, on_pad in items:
            iz = z if on_pad else (zfun(cx + ox, cy + oy) if zfun else z)
            inst(src, C_PLAY, "SM_PlayItem_%s_%02d" % (pk["id"], int(abs(ox * 10 + oy))),
                 cx + ox, cy + oy, iz, rot=rot, s=sc)
            N["play_objects"] += 1
        # safety fence ring around the 15 x 11 pad
        hx, hy = 8.6, 6.6
        border = rect_ring(cx, cy, hx, hy, step=2.4)
        for i in range(len(border)):
            x, y = border[i]
            x2, y2 = border[(i + 1) % len(border)]
            rot = math.atan2(y2 - y, x2 - x) - math.pi / 2
            inst(fence_src, C_PLAY, "SM_PlayFence_%s_%02d" % (pk["id"], i),
                 x, y, zfun(x, y) if zfun else z, rot=rot, s=1.0)
            N["play_objects"] += 1
        # collider box for the cluster
        add_box_collider("COL_Play_%s" % pk["id"], cx, cy, z, hx * 2, hy * 2, 2.6)
        pk["_play_cam"] = clear_camera_spot(cx, cy)
        clusters += 1
    N["playground_clusters"] = clusters
    print("[nature] playgrounds: %d clusters, %d objects" % (clusters, N["play_objects"]))


def clear_camera_spot(cx, cy, z=9.0, radius=7.0):
    """pick a ground-level preview spot that is not inside a tree canopy"""
    trees = [o for o in bpy.data.objects
             if not o.hide_render and o.name.startswith("SM_Tree")]
    for ox, oy in ((26, -24), (34, -20), (22, -32), (30, -32), (18, -26),
                   (36, -28), (24, -20), (28, -38)):
        cand = (cx + ox, cy + oy)
        ok = True
        for o in trees:
            if abs(o.location.x - cand[0]) < radius and abs(o.location.y - cand[1]) < radius:
                ok = False
                break
        if ok:
            return cand
    return (cx + 26.0, cy - 24.0)


# --------------------------------------------------------------------------
# 6. COLLIDERS
# --------------------------------------------------------------------------
def add_box_collider(name, cx, cy, z, sx, sy, sz):
    mb = MB()
    mb.add(*prim_box(0, 0, sz / 2.0, sx, sy, sz), 0)
    ob = mesh_object(name, mb, ["bark"], C_COLL)
    ob.location = (cx, cy, z)
    ob.hide_render = True
    ob.hide_viewport = True
    N["colliders"] += 1
    return ob


def build_colliders():
    proxy = bpy.data.objects["COL_TreeProxy_01"]
    count = 0
    for coll in (C_STREET, C_PARK, C_LAKE):
        for ob in list(coll.objects):
            if not ob.name.startswith("SM_Tree") and not ob.name.startswith("SM_Shrub"):
                continue
            src_data = proxy.data
            # radius from the shared mesh footprint scaled by object scale
            s = ob.scale[0]
            r = 0.34 * s
            h = 6.2 * s
            if ob.name.startswith("SM_Shrub"):
                r, h = 0.9 * s, 1.6 * s
            c = bpy.data.objects.new("COL_" + ob.name, src_data)
            c.location = (ob.location.x, ob.location.y, ob.location.z)
            c.scale = (r, r, h)
            c.hide_render = True
            c.hide_viewport = True
            C_COLL.objects.link(c)
            count += 1
    N["colliders"] += count
    print("[nature] colliders: %d (per-tree proxies + %d cluster boxes)"
          % (N["colliders"], sum(1 for o in C_COLL.objects if o.name.startswith("COL_Play"))))


# --------------------------------------------------------------------------
# 7. VERIFY + PREVIEWS + REPORT
# --------------------------------------------------------------------------
def instanced_tris():
    """total triangles if every linked instance were expanded (data counted once per use)"""
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


def verify():
    bad = []
    for ob in bpy.data.objects:
        if ob.name in ("Cube", "Camera", "Light"):
            bad.append(ob.name)
    tops = [c.name for c in bpy.context.scene.collection.children]
    print("[nature] top-level collections:", tops)
    print("[nature] buildable_rect violations:", len(VIOLATIONS), VIOLATIONS[:10])
    for prev in ("nature_preview.png", "nature_playground_preview.png"):
        p = os.path.join(ck.OUT_DIR, prev)
        if not os.path.isfile(p):
            bad.append("missing preview " + p)
    if tops != ["Nature"]:
        bad.append("top-level collections are %s" % tops)
    if bad:
        raise RuntimeError("verification failed: %s" % bad)
    # material sanity
    for m in ("bark", "leaves_green", "grass", "water", "gravel", "paving_slab"):
        if m not in MATS_USED:
            raise RuntimeError("material %s not used/applied" % m)
    print("[nature] verify OK — objects=%d unique_tris=%d instanced_tris=%d"
          % (len(bpy.data.objects), ck.scene_tri_count(), instanced_tris()))


def preview_ground():
    """Temporary ground slab so the preview is not full of background gaps
    (roads/ground belong to other modules). Created AFTER the last save and
    deleted straight after the render, so it never appears in nature.blend.
    Cells over the LAKE bowl are skipped — the park terrain already covers
    everything else (its lawn sits above z = 0)."""
    lx0 = min(p[0] for p in LAKE_POLY) - 20
    lx1 = max(p[0] for p in LAKE_POLY) + 20
    ly0 = min(p[1] for p in LAKE_POLY) - 20
    ly1 = max(p[1] for p in LAKE_POLY) + 20
    step = 20.0
    ext = 2000.0
    n = int(2 * ext / step)
    mb = MB()
    V, F = [], []
    for j in range(n + 1):
        y = -ext + j * step
        for i in range(n + 1):
            V.append((-ext + i * step, y, 0.0))
    for j in range(n):
        for i in range(n):
            cx = -ext + (i + 0.5) * step
            cy = -ext + (j + 0.5) * step
            if lx0 <= cx <= lx1 and ly0 <= cy <= ly1:
                if point_in_poly(cx, cy, LAKE_POLY) or dist_to_poly(cx, cy, LAKE_POLY) < 16.0:
                    continue
            a = j * (n + 1) + i
            F.append((a, a + 1, a + n + 2, a + n + 1))
    mb.v, mb.f, mb.m = V, F, [0] * len(F)
    return mesh_object("TMP_PREVIEW_GROUND", mb, ["dirt"], C_PARK)


def previews():
    tmp = preview_ground()
    # NOTE: Blender's default camera clip_end is 1000 m — every point of the
    # frame must stay within 1000 m of the camera (45 deg, height 400 m).
    ck.make_preview(os.path.join(ck.OUT_DIR, "nature_preview.png"),
                    cam_pos=(-238.0, -560.0, 400.0),
                    cam_target=(-450.0, -900.0, 0.0),
                    engine="BLENDER_EEVEE", res=(1920, 1080), samples=24)
    if PLAYGROUND_PARKS:
        pk = PLAYGROUND_PARKS[0]
        cx, cy = pk["_play"] if pk.get("_play") else pk["center"]
        px, py = pk.get("_play_cam", (cx + 26.0, cy - 24.0))
        ck.make_preview(os.path.join(ck.OUT_DIR, "nature_playground_preview.png"),
                        cam_pos=(px, py, 4.2),
                        cam_target=(cx, cy, 1.2),
                        engine="BLENDER_EEVEE", res=(1920, 1080), samples=24,
                        sun_elev=42.0, sun_azim=-60.0)
    bpy.data.objects.remove(tmp, do_unlink=True)


def courtyard_green():
    """courtyard_scatter 0.8/100m² inside G-district courtyard parcels"""
    g = ck.read_parcels("G")
    courts = [p for p in g if p.get("type") in ("courtyard",) or
              p.get("subtype") in ("backyard_garden", "plaza_dining")]
    if not courts:
        ISSUES.append("parcels_G.json contains only park/pocket_park parcels — "
                      "no courtyard parcels exist, so courtyard_scatter (%.1f/100m²) "
                      "was skipped (0 instances)." % COURT_DENSITY)
        print("[nature] courtyard green: 0 G-district courtyard parcels -> skipped")
        return
    planter = bpy.data.objects["SM_Prop_Planter_01"]
    for p in courts:
        br = p.get("buildable_rect") or p.get("rect")
        x0, y0, x1, y1 = br
        area = (x1 - x0) * (y1 - y0)
        n = max(2, int(area * COURT_DENSITY / 100.0))
        for i in range(n):
            x = RND.uniform(x0 + 2, x1 - 2)
            y = RND.uniform(y0 + 2, y1 - 2)
            if check_point(x, y, "court:" + p["id"]):
                continue
            if i % 2 == 0:
                inst(planter, C_PROP, "SM_Planter_%s_%02d" % (p["id"], i),
                     x, y, 0.0, rot=RND.uniform(0, 6.283))
            else:
                inst(kit_pick(1, "broadleaf_small"), C_PROP,
                     "SM_TreeCourt_%s_%02d" % (p["id"], i), x, y, 0.0,
                     rot=RND.uniform(0, 6.283), s=RND.uniform(0.85, 1.15))
            N["courtyard_instances"] += 1


def write_md(total_tris, instanced, elapsed):
    lines = []
    lines.append("# Nature module report (Phase C)\n")
    lines.append("Generated by `modules/nature.py` (headless, EEVEE).\n")
    lines.append("## Counts\n")
    lines.append("| item | value |\n|---|---|")
    for k in sorted(N):
        lines.append("| %s | %s |" % (k, N[k]))
    lines.append("| objects_total | %d |" % len(bpy.data.objects))
    lines.append("| tris_unique_meshes | %d |" % total_tris)
    lines.append("| tris_instanced | %d |" % instanced)
    lines.append("| build_seconds | %.1f |" % elapsed)
    lines.append("\n## Tree kit (43 unique meshes, %d tris)\n" % sum(r[1] for r in KIT_ROWS))
    kinds = {}
    for nm, tris, _ in KIT_ROWS:
        base = nm.split("SM_", 1)[-1]
        lod = ""
        if nm.startswith("1_"):
            base, lod = base[2:], "L1"
        elif nm.startswith("2_"):
            base, lod = base[2:], "L2"
        kinds.setdefault(base, {})[lod or "L0"] = tris
    lines.append("| kind | L0 | L1 | L2 |\n|---|---|---|---|")
    for k in sorted(kinds):
        v = kinds[k]
        lines.append("| %s | %s | %s | %s |" % (k, v.get("L0", "-"), v.get("L1", "-"), v.get("L2", "-")))
    lines.append("\n## Materials used (%d)\n" % len(MATS_USED))
    lines.append("`%s`\n" % "`, `".join(sorted(MATS_USED)))
    lines.append("\n## Geometry facts for the Assembler\n")
    lines.append("* collections: `Nature` / `Meshes` (kit sources, hidden, staged at z=-2000), "
                 "`StreetTrees`, `Parks`, `Props`, `Playground`, `Lake`, `Colliders`, `Lights`.\n")
    lines.append("* street trees: offset = carriageway half-width + 1.5 m from the kerb, "
                 "spacing 14 m, skipped within 12 m of every road node; base z = 0.0 "
                 "(sidewalk top will be 0.15, so trunks are slightly buried - correct).\n")
    lines.append("* park terrain: gentle humps 0.02..0.35 m above z=0, tapered to 0.02 m "
                 "at the parcel edge; lawn = `grass`, shore band faces = `dirt`.\n")
    lines.append("* paths: 2.0 m wide ribbons at terrain z + 0.05 (a rect ring inset 10 m "
                 "for big parks / 6 m for pocket parks + two serpentine cross paths).\n")
    lines.append("* LAKE_1: water plane at **z = -0.3**, lake bed -3.0 (matches layout depth), "
                 "shore ramp 16 m (waterline ~14 m out from the polygon), gravel band 13..21 m, "
                 "shore path ring at 24 m (2 m wide), fence at 27 m, jetty on the north shore "
                 "deck at z = +0.34, reeds 12..19 m.\n")
    lines.append("* park scatter: %.1f/100 m^2 capped at %d instances per big park "
                 "(instance budget) - see issues.\n" % (PARK_DENSITY, PARK_CAP_LARGE))
    lines.append("* per-instance variation comes from `City_Variation` (Object Info > Random) "
                 "already inside the library materials + random scale 0.85..1.25 and rotation; "
                 "no new materials were created.\n")
    lines.append("* colliders: one unit-cylinder proxy (`COL_TreeProxy_01`, r=0.34 h=6.2 scaled) "
                 "per street/park/shore tree + one box per playground cluster.\n")
    lines.append("\n## Verification\n")
    lines.append("* buildable_rect violations: **%d** (placements inside a buildable lot are "
                 "suppressed at placement time: %d suppressed)\n" % (len(VIOLATIONS), N["suppressed_buildable"]))
    lines.append("* stock Cube/Camera/Light: none; top-level collection: `Nature` only\n")
    lines.append("* previews: out/nature_preview.png, out/nature_playground_preview.png\n")
    lines.append("\n## Known issues / requests\n")
    for i in ISSUES:
        lines.append("* %s\n" % i)
    lines.append("* **requested from Materials agent**: nothing new was needed "
                 "(`grass_dry` doubles as the flowerbed/rubber-pad colour; a dedicated "
                 "`rubber_playground` mat would be nicer).\n")
    path = os.path.join(ck.REPORTS_DIR, "nature_report.md")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    print("[nature] md report ->", path)


# --------------------------------------------------------------------------
def main():
    t_start = time.time()
    setup()

    build_kit()
    stage("kit")

    build_index()
    build_street_trees()
    stage("street")

    build_parks()
    stage("parks")

    courtyard_green()
    build_lake()
    stage("lake")

    build_playgrounds()
    stage("playground")

    build_colliders()
    stage("colliders")

    unique = ck.scene_tri_count()
    total = instanced_tris()
    previews()
    verify()

    payload = dict(N)
    payload.update({
        "objects": len(bpy.data.objects),
        "unique_meshes": len([m for m in bpy.data.meshes if m.users > 0]),
        "tris_unique": unique,
        "tris_instanced": total,
        "budget_6M_ok": total <= 6_000_000,
        "materials_used": sorted(MATS_USED),
        "kit_rows": [[n, t] for n, t, _ in KIT_ROWS],
        "violations": VIOLATIONS,
        "suppressed_buildable": N["suppressed_buildable"],
        "build_seconds": round(time.time() - t_start, 1),
        "stage_times": [[n, round(t, 1)] for n, t in STAGE_TIMES],
        "issues": ISSUES,
        "previews": [os.path.join(ck.OUT_DIR, "nature_preview.png"),
                     os.path.join(ck.OUT_DIR, "nature_playground_preview.png")],
        "collections": ["Nature", "Nature/Meshes", "Nature/StreetTrees", "Nature/Parks",
                        "Nature/Props", "Nature/Playground", "Nature/Lake",
                        "Nature/Colliders", "Nature/Lights"],
        "geometry_facts": {
            "street_tree_offset": "half-width + 1.5 m, spacing 14 m, junction skip 12 m",
            "park_terrain": "0.02..0.35 m humps, grass, tapered at parcel edge",
            "path_width_m": 2.0,
            "lake_water_z": -0.3,
            "lake_bed_z": -3.0,
            "shore_gravel_band_m": [13, 21],
            "shore_path_offset_m": 24,
            "fence_offset_m": 27,
        },
    })
    ck.write_report("nature", payload)
    write_md(unique, total, payload["build_seconds"])
    print("[nature] DONE in %.1fs — objects=%d unique_tris=%d instanced_tris=%d"
          % (payload["build_seconds"], len(bpy.data.objects), unique, total))


if __name__ == "__main__":
    main()
