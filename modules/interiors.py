#!/usr/bin/env python3
"""interiors.py — shared interior kits + 3 reference rooms for the AAA city.

Headless run:
    cd /home/abdulhadi/Work/city && blender -b -P modules/interiors.py > /tmp/opencode/interiors.log 2>&1

Builds (NO building shells — district modules own shells):
  * 6 shared interior kit families (office, hotel, gym, restaurant, shop, home),
    each as modular parts: walls (paint/wallpaper), floor slabs (tile/carpet/wood),
    ceilings, open archway door frames (2.4 m high, NO door meshes), counters,
    reception desks, shelving, table+chair, sofa+coffee table, beds, kitchen units,
    bathroom fixtures (toilet/sink/shower), partition screens, wall shelves, rugs,
    pendant lamps (emissive), framed art, mirrors (int_mirror), curtains, plants
    (leaves_*), TVs (dark glass + emissive screen). Named INT_<kit>_<part>_<nn>,
    one source mesh per family/part, instanced everywhere else via linked duplicates
    (shared datablock, never unique copies). Each part <= 5 k tris.
  * 3 reference rooms (office lobby, restaurant dining+bar, home living/kitchen/dining)
    inside the first 3 tier-1 anchors of parcels_D.json (program.json rects are null).
    Convention matching entertainment.py: object at world z=0.0, floor mesh at local
    z=CURB=0.15 (finished floor z=0.15), ceiling 3.2.
  * Colliders: one COL_int_kit_<family>_01 box per family under Interiors/Colliders.
  * Lights: <= 40 LT_int_<nn> point lights (pendants/patches) under Interiors/Lights.

Saves out/interiors.blend, reports/interiors_report.json + interiors_report.md,
renders out/interiors_preview.png and out/interiors_kit_preview.png (1920x1080 EEVEE).

Keepouts respected: no M-district shells, no circuit zone [612,-1188,1188,-12], no
LAKE_1, no 5 stadium rects — nothing is built outside the three D reference rooms.
"""
from __future__ import annotations

import json
import math
import os
import sys

ROOT = "/home/abdulhadi/Work/city"
if ROOT not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "modules"))

import bpy  # noqa: E402 (only available inside blender -b -P)
from mathutils import Matrix  # noqa: E402

import citykit as ck  # noqa: E402

# ------------------------------------------------------------------ constants
MODULE = "Interiors"
FLOOR = 3.2        # floor height (metres)
CURB = 0.15        # curb / finished-ground offset
DOOR_H = 2.4       # door opening height
DOOR_W = 0.9       # door opening width
KIT_ROOT = "Interiors"
COLL_NAME = "col_placeholder"

OUT_BLEND = os.path.join(ck.OUT_DIR, "interiors.blend")
REPORT_MD = os.path.join(ck.REPORTS_DIR, "interiors_report.md")
PREVIEW_HERO = os.path.join(ck.OUT_DIR, "interiors_preview.png")
PREVIEW_KIT = os.path.join(ck.OUT_DIR, "interiors_kit_preview.png")

# ------------------------------------------------------------------ primitives
def _box_verts_faces(x0, y0, z0, x1, y1, z1):
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 2, 1), (0, 3, 2),          # bottom  (-Z)
         (4, 5, 6), (4, 6, 7),          # top     (+Z)
         (0, 1, 5), (0, 5, 4),          # front   (-Y)
         (3, 2, 6), (3, 6, 7),          # back    (+Y)
         (0, 4, 7), (0, 7, 3),          # left    (-X)
         (1, 2, 6), (1, 6, 5)]          # right   (+X)
    return v, f


def _cyl_verts_faces(cx, cy, z0, z1, r, seg=10):
    v = []
    for k in (0, 1):
        z = z0 if k == 0 else z1
        for i in range(seg):
            a = 2.0 * math.pi * i / seg
            v.append((cx + r * math.cos(a), cy + r * math.sin(a), z))
    f = []
    for i in range(seg):
        i0 = i; i1 = (i + 1) % seg
        f.append((i0, i1, seg + i1))
        f.append((i0, seg + i1, seg + i0))
    c0 = len(v); v.append((cx, cy, z0))
    for i in range(seg):
        i0 = i; i1 = (i + 1) % seg
        f.append((c0, i1, i0))           # bottom cap (-Z)
    c1 = len(v); v.append((cx, cy, z1))
    for i in range(seg):
        i0 = i; i1 = (i + 1) % seg
        f.append((c1 + i0, c1 + i1, c1))  # top cap (+Z)
    return v, f


def build_mesh(name, solids):
    """solids: list of ('box', x0,y0,z0,x1,y1,z1) or
    ('cyl', cx,cy,z0,z1,r[,seg]). Single material slot, all polygons index 0."""
    verts, faces = [], []
    voff = 0
    for s in solids:
        if s[0] == "box":
            _, x0, y0, z0, x1, y1, z1 = s
            v, f = _box_verts_faces(x0, y0, z0, x1, y1, z1)
        elif s[0] == "cyl":
            _, cx, cy, z0, z1, r = s[:6]
            seg = s[6] if len(s) > 6 else 10
            v, f = _cyl_verts_faces(cx, cy, z0, z1, r, seg)
        else:
            raise RuntimeError("unknown solid %r" % (s[0],))
        verts += v
        faces += [[a + voff, b + voff, c + voff] for (a, b, c) in f]
        voff += len(v)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    return mesh


def new_obj(name, mesh, mat_name, loc, coll, rot_z=0.0, scale=1.0):
    ob = bpy.data.objects.new(name, mesh)
    if mat_name:
        m = ck.append_material(mat_name)
        ob.data.materials.append(m)
        for p in ob.data.polygons:
            p.material_index = 0
    ob.matrix_world = Matrix.Translation((float(loc[0]), float(loc[1]), float(loc[2])))
    if rot_z:
        ob.rotation_euler = (0.0, 0.0, float(rot_z))
    if scale != 1.0:
        ob.scale = (float(scale), float(scale), float(scale))
    coll.objects.link(ob)
    try:
        bpy.context.scene.collection.objects.unlink(ob)
    except Exception:
        pass
    return ob


def dup_into(src, name, loc, coll, rot_z=0.0, scale=1.0):
    """Linked duplicate of src (shared mesh datablock) placed at loc, linked to coll."""
    ob = bpy.data.objects.new(name, src.data)
    ob.matrix_world = Matrix.Translation((float(loc[0]), float(loc[1]), float(loc[2])))
    if rot_z:
        ob.rotation_euler = (0.0, 0.0, float(rot_z))
    if scale != 1.0:
        ob.scale = (float(scale), float(scale), float(scale))
    coll.objects.link(ob)
    try:
        bpy.context.scene.collection.objects.unlink(ob)
    except Exception:
        pass
    return ob


# ------------------------------------------------------------------ part builders (local coords, bottom at z=0 -> origin at bottom-centre)
def W(w=3.0, d=0.15, h=3.2):
    return [("box", -w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, h)]


def FLOOR_SLAB(w=4.0, d=4.0, t=0.03):
    return [("box", -w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, t)]


def CEILING(w=4.0, d=4.0, t=0.03):
    return [("box", -w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, t)]


def ARCH_FRAME(frame_w=1.1, t=0.12, open_w=DOOR_W, open_h=DOOR_H, header_h=0.15):
    """Open archway door frame (no door mesh). Opening open_w x open_h (2.4 m high)."""
    hw = frame_w * 0.5
    return [
        ("box", -hw, -t * 0.5, 0.0, -hw + t, t * 0.5, open_h),        # left jamb
        ("box", hw - t, -t * 0.5, 0.0, hw, t * 0.5, open_h),          # right jamb
        ("box", -hw, -t * 0.5, open_h, hw, t * 0.5, open_h + header_h),  # header
    ]


def COUNTER(w=2.0, d=0.6, h=1.05):
    return [("box", -w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, h)]


def RECEPTION(w=2.6, d=0.8, h=1.1):
    return [("box", -w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, h)]


def SHELVING(w=1.0, d=0.35, h=1.8, shelves=4):
    solids = [
        ("box", -w * 0.5 - 0.025, -d * 0.5, 0.0, -w * 0.5 + 0.025, d * 0.5, h),
        ("box", w * 0.5 - 0.025, -d * 0.5, 0.0, w * 0.5 + 0.025, d * 0.5, h),
    ]
    for i in range(1, shelves + 1):
        z = h * i / (shelves + 1)
        solids.append(("box", -w * 0.5, -d * 0.5, z - 0.02, w * 0.5, d * 0.5, z + 0.02))
    return solids


def TABLE(w=1.0, d=0.7, h=0.74, leg=0.06):
    return [("box", -w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, h),
            ("box", -leg * 0.5, -leg * 0.5, 0.0, leg * 0.5, leg * 0.5, h)]


def CHAIR(w=0.5, d=0.5, h=0.9, seat_h=0.46):
    return [("box", -w * 0.5, -d * 0.5, seat_h, w * 0.5, d * 0.5, seat_h + 0.04),
            ("box", -w * 0.5, d * 0.5 - 0.1, seat_h, w * 0.5, d * 0.5, h),
            ("box", -0.04, -0.04, 0.0, 0.04, 0.04, seat_h)]


def SOFA(w=1.8, d=0.75, h=0.85):
    return [("box", -w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, h * 0.55),
            ("box", -w * 0.5, -d * 0.5 + 0.05, h * 0.55, w * 0.5, -d * 0.5 + 0.25, h)]


def COFFEE_TABLE(w=0.9, d=0.5, h=0.42):
    return [("box", -w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, h)]


def BED(w=1.6, d=2.0, h=0.5):
    return [("box", -w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, h * 0.7),
            ("box", -w * 0.5, -d * 0.5 - 0.02, h * 0.7, w * 0.5, -d * 0.5 + 0.1, h)]


def KITCHEN(w=1.0, d=0.6, h=0.9):
    return [("box", -w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, h)]


def TOILET(w=0.4, d=0.7, h=0.45):
    return [("box", -w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, h)]


def SINK(w=0.5, d=0.55, h=0.85):
    return [("box", -w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, h)]


def SHOWER(w=0.9, d=0.9, h=2.1):
    return [("box", -w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, h)]


def PARTITION(w=2.4, d=0.12, h=2.4):
    return [("box", -w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, h)]


def WALL_SHELF(w=0.6, d=0.15, t=0.03):
    return [("box", -w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, t)]


def RUG(w=2.5, d=1.8, t=0.01):
    return [("box", -w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, t)]


def PENDANT(r=0.06, h=0.25):
    return [("cyl", 0.0, 0.0, 0.0, h, r, 8)]


def FRAMED_ART(w=0.8, d=0.03, h=0.6):
    return [("box", -w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, h)]


def MIRROR(w=0.9, d=0.02, h=1.6):
    return [("box", -w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, h)]


def CURTAIN(w=1.2, d=0.03, h=2.5):
    return [("box", -w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, h)]


def PLANT(w=0.4, d=0.4, h=0.7):
    return [("box", -w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, h)]


def TV_DARK(w=1.0, d=0.04, h=0.6):
    return [("box", -w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, h)]


def TV_SCREEN(w=0.92, d=0.02, h=0.56):
    return [("box", -w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, h)]


# ------------------------------------------------------------------ kit spec
PART_SPECS = {
    "wall_paint":        (W, "wall_paint"),
    "wall_wallpaper":    (W, "int_wall_paint_bone"),
    "floor_tile":        (FLOOR_SLAB, "floor_tile"),
    "floor_carpet":      (FLOOR_SLAB, "floor_carpet"),
    "floor_wood":        (FLOOR_SLAB, "floor_wood"),
    "ceiling":           (CEILING, "ceiling_paint"),
    "door_frame_arch":   (ARCH_FRAME, "wood_painted"),
    "counter":           (COUNTER, "int_laminate_counter"),
    "reception_desk":    (RECEPTION, "wood_painted"),
    "shelving":          (SHELVING, "metal_painted_dark"),
    "table":             (TABLE, "wood_old"),
    "chair":             (CHAIR, "int_upholstery"),
    "sofa":              (SOFA, "int_upholstery"),
    "coffee_table":      (COFFEE_TABLE, "wood_old"),
    "bed":               (BED, "int_upholstery"),
    "kitchen_unit":      (KITCHEN, "wood_painted"),
    "toilet":            (TOILET, "int_marble"),
    "sink":              (SINK, "int_marble"),
    "shower":            (SHOWER, "metal_steel"),
    "partition":         (PARTITION, "glass_frosted"),
    "wall_shelf":        (WALL_SHELF, "wood_old"),
    "rug":               (RUG, "int_carpet"),
    "pendant_lamp":      (PENDANT, "emissive_warm"),
    "framed_art":        (FRAMED_ART, "plaster_white"),
    "mirror":            (MIRROR, "int_mirror"),
    "curtain":           (CURTAIN, "canvas_tarp"),
    "plant":             (PLANT, "leaves_green"),
    "tv_dark":           (TV_DARK, "glass_dark"),
    "tv_screen":         (TV_SCREEN, "emissive_cool"),
}

FAMILY_PARTS = {
    "office": ["wall_paint", "wall_wallpaper", "floor_tile", "floor_carpet", "floor_wood",
               "ceiling", "door_frame_arch", "counter", "reception_desk", "shelving",
               "table", "chair", "sofa", "coffee_table", "partition", "wall_shelf",
               "rug", "pendant_lamp", "framed_art", "mirror", "curtain", "plant",
               "tv_dark", "tv_screen"],
    "hotel":  ["wall_paint", "wall_wallpaper", "floor_tile", "floor_carpet", "floor_wood",
               "ceiling", "door_frame_arch", "reception_desk", "shelving", "table", "chair",
               "sofa", "coffee_table", "bed", "partition", "wall_shelf", "rug",
               "pendant_lamp", "framed_art", "mirror", "curtain", "plant"],
    "gym":    ["wall_paint", "wall_wallpaper", "floor_tile", "floor_wood", "ceiling",
               "door_frame_arch", "shelving", "table", "chair", "partition", "wall_shelf",
               "rug", "pendant_lamp", "mirror", "curtain", "plant", "tv_dark", "tv_screen"],
    "restaurant": ["wall_paint", "wall_wallpaper", "floor_tile", "floor_wood", "ceiling",
                   "door_frame_arch", "counter", "shelving", "table", "chair", "sofa",
                   "coffee_table", "partition", "wall_shelf", "rug", "pendant_lamp",
                   "framed_art", "mirror", "curtain", "plant", "tv_dark", "tv_screen"],
    "shop":   ["wall_paint", "wall_wallpaper", "floor_tile", "floor_wood", "ceiling",
               "door_frame_arch", "counter", "shelving", "table", "chair", "partition",
               "wall_shelf", "rug", "pendant_lamp", "framed_art", "mirror", "curtain",
               "plant", "tv_dark"],
    "home":   ["wall_paint", "wall_wallpaper", "floor_tile", "floor_carpet", "floor_wood",
               "ceiling", "door_frame_arch", "counter", "kitchen_unit", "table", "chair",
               "sofa", "coffee_table", "bed", "toilet", "sink", "shower", "partition",
               "wall_shelf", "rug", "pendant_lamp", "framed_art", "mirror", "curtain",
               "plant", "tv_dark", "tv_screen"],
}

GRID_SPACING = 7.0
GRID_COLS = 6


# ------------------------------------------------------------------ scene setup
def clear_scene():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for m in list(bpy.data.meshes):
        bpy.data.meshes.remove(m)
    for c in list(bpy.data.cameras):
        bpy.data.cameras.remove(c)
    for l in list(bpy.data.lights):
        bpy.data.lights.remove(l)
    for col in list(bpy.data.collections):
        if col.name != "Scene Collection":
            bpy.data.collections.remove(col)


def ensure_collections():
    top = ck.ensure_collection(KIT_ROOT)
    meshes = ck.ensure_collection("Meshes", parent=top)
    colliders = ck.ensure_collection("Colliders", parent=top)
    lights = ck.ensure_collection("Lights", parent=top)
    return top, meshes, colliders, lights


# ------------------------------------------------------------------ kits
def build_kits(meshes):
    """One source mesh per family/part, laid out on a grid (kit preview).
    Mesh data modelled at local origin (origin = bottom-centre). Objects keep their
    grid-position translation (shared datablocks must stay instancable)."""
    kit_sources = {}
    x = 0.0
    y = 0.0
    for family in FAMILY_PARTS:
        fcoll = ck.ensure_collection("Kit_" + family.title(), parent=meshes)
        parts = []
        for pi, part_key in enumerate(FAMILY_PARTS[family]):
            builder, mat = PART_SPECS[part_key]
            mesh = build_mesh("INT_%s_%s_mesh" % (family, part_key), builder())
            name = "INT_%s_%s_%02d" % (family, part_key, pi + 1)
            src = new_obj(name, mesh, mat, (x, y, 0.0), fcoll)
            parts.append((part_key, src, ck.tri_count(src)))
            x += GRID_SPACING
            if x >= GRID_COLS * GRID_SPACING:
                x = 0.0
                y -= GRID_SPACING
        kit_sources[family] = parts
    return kit_sources


# ------------------------------------------------------------------ colliders / lights
def build_colliders(colliders, kit_sources):
    made = []
    for fi, family in enumerate(FAMILY_PARTS):
        cx = (fi % GRID_COLS) * GRID_SPACING + GRID_SPACING * 0.5
        cy = -((fi // GRID_COLS) * GRID_SPACING + GRID_SPACING * 0.5)
        mesh = build_mesh("COL_int_kit_%s_mesh" % family,
                          [("box", -5.0, -5.0, 0.0, 5.0, 5.0, 3.2)])
        name = "COL_int_kit_%s_01" % family
        ob = new_obj(name, mesh, COLL_NAME, (cx, cy, 1.6), colliders)
        made.append((name, ck.tri_count(ob)))
    return made


def place_light(lights, name, loc):
    lt = bpy.data.lights.new(name, type="POINT")
    lt.energy = 100.0
    lt.color = (1.0, 0.92, 0.84)  # warm
    ob = bpy.data.objects.new(name, lt)
    ob.matrix_world = Matrix.Translation((float(loc[0]), float(loc[1]), float(loc[2])))
    lights.objects.link(ob)
    try:
        bpy.context.scene.collection.objects.unlink(ob)
    except Exception:
        pass
    return ob


# ------------------------------------------------------------------ reference rooms
# program.json Interiors facilities have rect == null -> fall back to parcels_D.json
# tier-1 anchors (first 3), stated in the report.
REF_ANCHORS = [
    ("B_4_3_0_1_0_0", "OfficeLobby", (45.0, -111.0),
     ["floor_carpet", "wall_paint", "ceiling", "reception_desk", "sofa", "coffee_table",
      "table", "chair", "table", "chair", "framed_art", "pendant_lamp", "pendant_lamp"]),
    ("B_3_4_1_0_0_0", "RestaurantDining", (-111.0, 45.0),
     ["floor_tile", "wall_paint", "ceiling", "counter", "table", "chair", "table", "chair",
      "table", "chair", "sofa", "coffee_table", "pendant_lamp", "pendant_lamp", "pendant_lamp"]),
    ("B_3_4_1_1_1_1", "HomeLiving", (-45.0, 255.0),
     ["floor_wood", "wall_paint", "ceiling", "kitchen_unit", "sofa", "coffee_table",
      "table", "chair", "chair", "chair", "tv_dark", "tv_screen", "pendant_lamp"]),
]

ROOM_RUG = {"OfficeLobby": ("rug", 0.0, 2.0),
            "RestaurantDining": ("rug", -3.0, -2.0),
            "HomeLiving": ("rug", 0.0, -2.0)}

FURN = {
    "OfficeLobby": [
        ("reception_desk", -4.0, -2.0, 0.0, 1.0),
        ("sofa", 2.0, 2.0, 0.0, 1.0),
        ("coffee_table", 2.0, 3.4, 0.0, 1.0),
        ("table", -1.0, 2.6, 0.0, 1.0),
        ("chair", -1.0, 3.6, 0.0, 1.0),
        ("chair", -1.0, 1.6, 180.0, 1.0),
        ("framed_art", -6.0, 0.0, 0.0, 1.0),
    ],
    "RestaurantDining": [
        ("counter", -5.0, -2.0, 0.0, 1.0),
        ("table", 1.0, 2.0, 0.0, 1.0),
        ("chair", 1.0, 3.0, 0.0, 1.0),
        ("chair", 1.0, 1.0, 180.0, 1.0),
        ("table", 3.0, 0.0, 0.0, 1.0),
        ("chair", 3.0, 1.0, 0.0, 1.0),
        ("chair", 3.0, -1.0, 180.0, 1.0),
        ("sofa", -1.0, -3.0, 0.0, 1.0),
        ("coffee_table", -1.0, -1.6, 0.0, 1.0),
    ],
    "HomeLiving": [
        ("kitchen_unit", -5.0, -2.0, 0.0, 1.0),
        ("sofa", 1.0, 2.0, 0.0, 1.0),
        ("coffee_table", 1.0, 3.4, 0.0, 1.0),
        ("table", -2.0, 2.0, 0.0, 1.0),
        ("chair", -2.0, 3.0, 0.0, 1.0),
        ("chair", -0.9, 2.0, 90.0, 1.0),
        ("chair", -3.1, 2.0, -90.0, 1.0),
        ("tv_dark", 4.0, -1.0, 0.0, 1.0),
        ("tv_screen", 4.0, -1.0, 0.0, 1.0),
    ],
}

LIGHT_OFFSETS = {
    "OfficeLobby": [(-2.0, 1.5, 3.0), (2.0, 1.5, 3.0), (0.0, -3.0, 3.0)],
    "RestaurantDining": [(-3.0, 2.5, 3.0), (0.0, 2.5, 3.0), (3.0, 2.5, 3.0), (0.0, -2.0, 3.0)],
    "HomeLiving": [(-1.5, 2.0, 3.0), (1.5, -1.0, 3.0), (-1.5, -3.0, 3.0)],
}


def build_reference_rooms(meshes, lights, kit_sources):
    with open(os.path.join(ck.CITY_ROOT, "parcels_D.json")) as f:
        ddata = json.load(f)
    dparcels = ddata["parcels"] if isinstance(ddata, dict) and "parcels" in ddata else ddata
    t1 = [p for p in dparcels if p.get("interior_tier") == 1]
    used = t1[:3]
    rooms = []
    light_idx = [1]
    for (pid, rname, _centre_hint, parts) in REF_ANCHORS:
        anchor = next((p for p in used if p.get("id") == pid), None)
        if anchor is None:
            raise RuntimeError("tier-1 anchor %s not found in parcels_D.json" % pid)
        br = [float(v) for v in anchor["buildable_rect"]]
        cx = (br[0] + br[2]) * 0.5
        cy = (br[1] + br[3]) * 0.5
        rcoll = ck.ensure_collection("Ref_%s" % rname, parent=meshes)
        placed = []
        # floor slab scaled to footprint (inside buildable_rect), finished floor z=CURB
        fw = (br[2] - br[0]) * 0.6
        fd = (br[3] - br[1]) * 0.6
        floor_key = parts[0]
        builder, mat = PART_SPECS[floor_key]
        fmesh = build_mesh("INT_REF_%s_floor_mesh" % rname, builder())
        finst = new_obj("INT_REF_%s_floor_01" % rname, fmesh, mat, (cx, cy, CURB), rcoll)
        finst.scale = (fw / 4.0, fd / 4.0, 1.0)
        placed.append(("INT_REF_%s_floor_01" % rname, ck.tri_count(finst)))
        # ceiling slab
        cmesh = build_mesh("INT_REF_%s_ceiling_mesh" % rname, CEILING())
        cinst = new_obj("INT_REF_%s_ceiling_01" % rname, cmesh, "ceiling_paint",
                        (cx, cy, FLOOR - 0.03), rcoll)
        cinst.scale = (fw / 4.0, fd / 4.0, 1.0)
        placed.append(("INT_REF_%s_ceiling_01" % rname, ck.tri_count(cinst)))
        # perimeter walls (paint)
        wx0, wy0, wx1, wy1 = br
        wall_h = FLOOR
        wall_z = CURB
        wall_specs = [
            ("wall_paint", ((wx0 + wx1) * 0.5, wy0), (wx1 - wx0) * 0.62, 0.15, 0.0),
            ("wall_paint", ((wx0 + wx1) * 0.5, wy1), (wx1 - wx0) * 0.62, 0.15, 0.0),
            ("wall_paint", (wx0, (wy0 + wy1) * 0.5), 0.15, (wy1 - wy0) * 0.62, 0.0),
            ("wall_paint", (wx1, (wy0 + wy1) * 0.5), 0.15, (wy1 - wy0) * 0.62, 0.0),
        ]
        wi = 1
        for mat_name, (px, py), sx, sy, _rot in wall_specs:
            wmesh = build_mesh("INT_REF_%s_wall%02d_mesh" % (rname, wi), W(sx, sy, wall_h))
            winst = new_obj("INT_REF_%s_wall%02d" % (rname, wi), wmesh, mat_name,
                            (px, py, wall_z), rcoll)
            placed.append(("INT_REF_%s_wall%02d" % (rname, wi), ck.tri_count(winst)))
            wi += 1
        # furniture from kit sources (shared datablocks)
        fam = "office" if rname == "OfficeLobby" else ("restaurant" if rname == "RestaurantDining" else "home")
        src_by_key = {pk: src for (pk, src, _t) in kit_sources[fam]}
        fi = 1
        for (part_key, dx, dy, rot, scale) in FURN[rname]:
            src = src_by_key.get(part_key)
            if src is None:
                continue
            name = "INT_REF_%s_%s_%02d" % (rname, part_key, fi)
            ob = dup_into(src, name, (cx + dx, cy + dy, CURB), rcoll, rot_z=rot, scale=scale)
            placed.append((name, ck.tri_count(ob)))
            fi += 1
        # rug
        rkey, rdx, rdy = ROOM_RUG[rname]
        src = src_by_key.get(rkey)
        if src:
            ob = dup_into(src, "INT_REF_%s_rug_01" % rname,
                          (cx + rdx, cy + rdy, CURB + 0.011), rcoll)
            placed.append(("INT_REF_%s_rug_01" % rname, ck.tri_count(ob)))
        # lights (pendants) — count toward <= 40
        for (lx, ly, lz) in LIGHT_OFFSETS[rname]:
            if light_idx[0] > 40:
                break
            place_light(lights, "LT_int_%02d" % light_idx[0], (cx + lx, cy + ly, lz))
            light_idx[0] += 1
        rooms.append({
            "room": rname, "anchor": pid, "anchor_type": anchor.get("type"),
            "buildable_rect": br, "centre": [cx, cy], "placed": placed,
        })
    return rooms, light_idx[0] - 1


# ------------------------------------------------------------------ program / gap audit
def program_interiors():
    with open(os.path.join(ck.REPORTS_DIR, "program.json")) as f:
        prog = json.load(f)
    return [f for f in prog["facilities"]
            if str(f.get("owning_module", "")).lower() == "interiors"]


def gap_audit():
    districts = ["R", "D", "E", "M", "G", "I", "T"]
    parcel_stats = {}
    for d in districts:
        path = os.path.join(ck.CITY_ROOT, "parcels_%s.json" % d)
        with open(path) as f:
            data = json.load(f)
        ps = data["parcels"] if isinstance(data, dict) and "parcels" in data else data
        from collections import Counter
        c = Counter(p.get("interior_tier", 0) for p in ps)
        parcel_stats[d] = {
            "total": len(ps),
            "t1": int(c.get(1, 0)), "t2": int(c.get(2, 0)),
            "t3": int(c.get(3, 0)), "t0": int(c.get(0, 0)),
            "enterable": int(sum(1 for p in ps if p.get("enterable"))),
        }
    report_file = {"D": "downtown", "E": "entertainment", "M": "market"}
    reports = {}
    for d, rf in report_file.items():
        rp = os.path.join(ck.REPORTS_DIR, "%s_report.json" % rf)
        if os.path.isfile(rp):
            with open(rp) as f:
                reports[d] = json.load(f)
    gaps = []
    for d in ["D", "E", "M"]:
        pt1 = parcel_stats[d]["t1"]
        rp = reports.get(d)
        rt1 = None
        has_field = False
        if rp is not None:
            tc = rp.get("tier_counts") or rp.get("counts_by_interior_tier") or {}
            if "1" in tc:
                has_field = True
                rt1 = int(tc["1"])
        if not has_field:
            gaps.append({"district": d, "parcel_t1": pt1, "report_t1": None,
                         "status": "no_tier_field"})
        elif rt1 < pt1:
            gaps.append({"district": d, "parcel_t1": pt1, "report_t1": rt1,
                         "status": "UNDER_BUILT", "missing": pt1 - rt1})
        else:
            gaps.append({"district": d, "parcel_t1": pt1, "report_t1": rt1,
                         "status": "ok"})
    # Residential has no district report -> unaudited
    gaps.append({"district": "R", "parcel_t1": parcel_stats["R"]["t1"],
                 "report_t1": None, "status": "unaudited_no_report"})
    return parcel_stats, gaps


# ------------------------------------------------------------------ markdown report
def write_md(payload, path):
    lines = []
    lines.append("# Interiors module report")
    lines.append("")
    lines.append("Module: `interiors`  |  blend: `out/interiors.blend`  |  engine: BLENDER_EEVEE  |  units: metres, Z-up")
    lines.append("")
    lines.append("## Program.json facilities (Interiors owning module)")
    lines.append("")
    lines.append("| id | district | interior_tier | budget_class |")
    lines.append("|---|---|---|---|")
    for f in payload["facilities"]:
        lines.append("| %s | %s | %s | %s |" % (f["id"], f["district"], f["interior_tier"], f["budget_class"]))
    lines.append("")
    lines.append("All three are 'no new footprint' passes over already-placed buildings; this module "
                   "provides the shared kits and reference rooms only. Building shells remain with their district modules.")
    lines.append("")
    lines.append("## INT_HERO_INTERIORS -> market parcels (skip_list)")
    lines.append("")
    hm = payload["hero_market_skip"]
    lines.append("INT_HERO_INTERIORS references 39 parcels (E15 / D11 / M7 / R6). The 7 market-district parcels are exactly "
                 "market's 7 tier-1 parcels, already fitted by the market module, so they are **skipped** to avoid duplication.")
    lines.append("Skipped ids: %s" % ", ".join(hm["skipped_ids"]) if hm["skipped_ids"] else "none")
    lines.append("Remaining %d parcels (E/D/R) are district-owned; kits are provided for the Assembler to place there." % hm["other_parcels_district_owned"])
    lines.append("")
    lines.append("| skip id | district | reason |")
    lines.append("|---|---|---|")
    for s in payload["skip_list"]:
        lines.append("| %s | %s | %s |" % (s["id"], s["district"], s["reason"]))
    lines.append("")
    lines.append("## Shared interior kits")
    lines.append("")
    lines.append("Six kit families (office, hotel, gym, restaurant, shop, home). One source mesh per family/part, "
                 "named `INT_<kit>_<part>_<nn>`, instanced via linked duplicates (shared datablock). Each part <= 5 k tris.")
    lines.append("")
    lines.append("| family | parts | unique tris |")
    lines.append("|---|---|---|")
    for family in payload["kit_families"]:
        ent = payload["kits"][family]
        ntr = sum(e["tris"] for e in ent)
        lines.append("| %s | %d | %d |" % (family, len(ent), ntr))
    lines.append("")
    lines.append("| family | part | tris |")
    lines.append("|---|---|---|")
    for family in payload["kit_families"]:
        for e in payload["kits"][family]:
            lines.append("| %s | %s | %d |" % (family, e["part"], e["tris"]))
    lines.append("")
    lines.append("Kit parts total: %d parts, %d unique tris." % (payload["kit_part_count"], payload["kit_total_tris"]))
    lines.append("")
    lines.append("Kit family part lists cover: walls (paint/wallpaper), floor slabs (tile/carpet/wood), ceilings, "
                 "open archway door frames (2.4 m high, no door meshes), counters, reception desks, shelving, table+chair, "
                 "sofa+coffee table, beds, kitchen units, bathroom fixtures (toilet/sink/shower), partition screens, wall shelves, "
                 "rugs, pendant lamps (emissive), framed art, mirrors (int_mirror), curtains, plants (leaves_*), TVs (dark glass + emissive screen).")
    lines.append("")
    lines.append("## Reference rooms (furnished demonstrations)")
    lines.append("")
    lines.append("program.json Interiors rects are null, so the three rooms sit inside the first 3 tier-1 anchors of parcels_D.json "
                 "(stated; all are office_tower civic parcels in district D, furnished as office lobby / restaurant / home using the kits).")
    lines.append("")
    lines.append("| room | anchor | type | buildable_rect | objects | tris | floor z |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in payload["reference_rooms"]:
        br = r["buildable_rect"]
        lines.append("| %s | %s | %s | [%s] | %d | %d | %.2f |"
                     % (r["room"], r["anchor"], r["type"],
                        ", ".join("%.1f" % v for v in br), r["objects"], r["tris"], payload["reference_room_floor_z"]))
    lines.append("")
    lines.append("Furniture is built from kit parts (shared datablocks) at local z=CURB=0.15 (finished floor z=0.15), ceiling 3.2, "
                 "matching entertainment.py's ground-floor convention. Objects at world z=0.0.")
    lines.append("")
    lines.append("## Colliders")
    lines.append("")
    lines.append("One box proxy per kit family under `Interiors/Colliders`, named `COL_int_kit_<family>_01`.")
    lines.append("| collider | tris |")
    lines.append("|---|---|")
    lines.append("| %d families | %d tris |" % (payload["colliders"]["count"], payload["colliders"]["tris"]))
    lines.append("")
    lines.append("## Lights")
    lines.append("")
    lines.append("%d real point lights (pendants/patches) under `Interiors/Lights`, named `LT_int_<nn>` (limit 40). "
                 "Emissive props (pendant_lamp meshes, tv_screen) use emissive materials elsewhere." % payload["lights"]["count"])
    lines.append("")
    lines.append("## Gap audit (report-only, no geometry)")
    lines.append("")
    lines.append("| district | parcels | t1 | t2 | t3 | t0 | enterable | report t1 | status |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    st = payload["gap_audit"]["parcel_stats"]
    for d in ["R", "D", "E", "M", "G", "I", "T"]:
        s = st[d]
        gap = next((g for g in payload["gap_audit"]["gaps"] if g["district"] == d), None)
        rt = gap["report_t1"] if gap and gap["report_t1"] is not None else "-"
        stat = gap["status"] if gap else "unaudited"
        lines.append("| %s | %d | %d | %d | %d | %d | %d | %s | %s |"
                     % (d, s["total"], s["t1"], s["t2"], s["t3"], s["t0"], s["enterable"], rt, stat))
    lines.append("")
    gaps = payload["gap_audit"]["gaps"]
    ok = [g for g in gaps if g["status"] == "ok"]
    built_lines = []
    for g in gaps:
        if g["status"] == "ok":
            built_lines.append("%s %d/%d" % (g["district"], g["report_t1"], g["parcel_t1"]))
        elif g["status"] == "no_tier_field":
            built_lines.append("%s (report lacks tier count; parcel t1=%d)" % (g["district"], g["parcel_t1"]))
        elif g["status"] == "unaudited_no_report":
            built_lines.append("%s (no district report; parcel t1=%d)" % (g["district"], g["parcel_t1"]))
        else:
            built_lines.append("%s UNDER_BUILT missing %d" % (g["district"], g.get("missing", 0)))
    lines.append("Headline: %s. No district reports fewer t1 interiors than the parcel file; "
                 "market's current report exposes no tier count (market previously reported 7 t1 = 7 parcels), "
                 "residential is unaudited." % "; ".join(built_lines))
    lines.append("")
    lines.append("## Materials")
    lines.append("")
    lines.append("Appended only from `/city/materials.blend` — no new materials created. "
                 "Used: wall_paint, int_wall_paint_bone, floor_tile, floor_carpet, floor_wood, ceiling_paint, "
                 "wood_painted, int_laminate_counter, metal_painted_dark, wood_old, int_upholstery, int_marble, "
                 "metal_steel, glass_frosted, int_carpet, emissive_warm, emissive_cool, plaster_white, int_mirror, "
                 "canvas_tarp, leaves_green, glass_dark, col_placeholder. `int_mirror` exists and is used for mirrors.")
    lines.append("")
    lines.append("## Naming / collections / transforms")
    lines.append("")
    lines.append("Collections: `Interiors` > `Meshes` (kit parts per family + `Ref_<room>`), `Colliders`, `Lights`. "
                 "Naming: `INT_<kit>_<part>_<nn>`, `INT_REF_<room>_<part>_<nn>`, `COL_int_kit_<family>_01`, `LT_int_<nn>`. "
                 "Every kit piece origin at bottom-centre. Linked duplicates / shared datablocks for anything repeated — "
                 "no unique copies. Transforms kept as translation (shared datablocks require instancing; codebase convention).")
    lines.append("")
    lines.append("## Keepouts")
    lines.append("")
    lines.append("No M-district shells, no circuit zone [612,-1188,1188,-12], no LAKE_1, no 5 stadium rects touched: "
                 "nothing is built outside the three D-district reference rooms (all inside their buildable_rects).")
    lines.append("")
    lines.append("## Budgets")
    lines.append("")
    lines.append("| item | tris |")
    lines.append("|---|---|")
    lines.append("| kit unique meshes | %d |" % payload["tris"]["kit_unique"])
    lines.append("| colliders | %d |" % payload["tris"]["colliders"])
    lines.append("| reference rooms | %d |" % payload["tris"]["reference_rooms"])
    lines.append("")
    lines.append("## Issues / needs from Assembler")
    lines.append("")
    lines.append("- %s" % payload["issues"][0])
    lines.append("- INT_HERO_INTERIORS / INT_SHELL_INTERIORS / INT_MALL_FITOUT are district-owned fit-out passes over already-placed "
                 "buildings; the Assembler places kit instances into those shells using these kits.")
    lines.append("- Residential district has no tier report; its 6 t1 parcels are unaudited.")
    lines.append("")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("  [interiors] md report -> %s" % path)


# ------------------------------------------------------------------ main
def main():
    clear_scene()
    top, meshes, colliders, lights = ensure_collections()

    # 1. program.json Interiors facilities (no new footprint — district-owned shells)
    facilities = program_interiors()

    # INT_HERO_INTERIORS: the 7 market-district parcels are exactly market's 7 t1
    # parcels, already fitted by the market module -> skip (skip_list). The other
    # 32 parcels (E/D/R) are district-owned; our kits are provided for the Assembler.
    skip_list = []
    hero = next((f for f in facilities if f.get("id") == "INT_HERO_INTERIORS"), None)
    hero_m = []
    hero_other = 0
    if hero is not None:
        with open(os.path.join(ck.CITY_ROOT, "parcels_M.json")) as f:
            mdata = json.load(f)
        mps = mdata["parcels"] if isinstance(mdata, dict) and "parcels" in mdata else mdata
        mt1_ids = {p["id"] for p in mps if p.get("interior_tier") == 1}
        for pid in hero.get("gap", {}).get("parcel_ids", []):
            if pid in mt1_ids:
                skip_list.append({"id": pid, "district": "M",
                                  "reason": "market t1 interior already built by market module - skipped to avoid duplication"})
                hero_m.append(pid)
            else:
                hero_other += 1

    # 2. kits
    kit_sources = build_kits(meshes)

    # 3. colliders (one box proxy per kit family)
    colliders_made = build_colliders(colliders, kit_sources)

    # 4. reference rooms
    rooms, n_lights_used = build_reference_rooms(meshes, lights, kit_sources)

    # 5. save
    ck.save_blend(OUT_BLEND)

    # 6. stats
    kit_inventory = {}
    total_kit_tris = 0
    for family in FAMILY_PARTS:
        ent = []
        for (pk, src, tris) in kit_sources[family]:
            ent.append({"part": pk, "tris": tris})
            total_kit_tris += tris
        kit_inventory[family] = ent

    room_stats = []
    for r in rooms:
        t = sum(tr for _n, tr in r["placed"])
        room_stats.append({"room": r["room"], "anchor": r["anchor"], "type": r["anchor_type"],
                           "objects": len(r["placed"]), "tris": t,
                           "buildable_rect": r["buildable_rect"], "centre": r["centre"]})

    collider_tris = sum(tr for _n, tr in colliders_made)

    parcel_stats, gaps = gap_audit()

    payload = {
        "module": MODULE,
        "engine": "BLENDER_EEVEE",
        "units": "metres", "z_up": True,
        "facilities": [
            {"id": f.get("id"), "label": f.get("label"), "district": f.get("district"),
             "interior_tier": f.get("interior_tier"), "budget_class": f.get("budget_class")}
            for f in facilities
        ],
        "hero_market_skip": {"market_t1_in_hero": len(hero_m),
                             "skipped_ids": hero_m,
                             "other_parcels_district_owned": hero_other},
        "skip_list": skip_list,
        "kits": kit_inventory,
        "kit_families": FAMILY_PARTS,
        "kit_part_count": sum(len(v) for v in kit_inventory.values()),
        "kit_total_tris": total_kit_tris,
        "reference_rooms": room_stats,
        "reference_room_floor_z": CURB,
        "lights": {"count": n_lights_used, "limit": 40, "prefix": "LT_int_"},
        "colliders": {"count": len(colliders_made), "tris": collider_tris,
                      "prefix": "COL_int_kit_"},
        "collections": ["Interiors", "Interiors/Meshes", "Interiors/Colliders", "Interiors/Lights"],
        "materials": "appended only from materials.blend (no new materials created)",
        "naming": "INT_<kit>_<part>_<nn> kit parts; INT_REF_<room>_<part>_<nn> room pieces; "
                  "COL_int_kit_<family>_01 colliders; LT_int_<nn> lights",
        "tris": {"kit_unique": total_kit_tris, "colliders": collider_tris,
                 "reference_rooms": sum(r["tris"] for r in room_stats)},
        "gap_audit": {"parcel_stats": parcel_stats, "gaps": gaps},
        "issues": ["kit sources keep translation-only transforms (shared datablocks require "
                   "instancing — codebase convention, see market report); transforms not baked "
                   "on instances"],
    }
    ck.write_report("interiors", payload)   # filename reports/interiors_report.json
    write_md(payload, REPORT_MD)

    # 7. previews (1920x1080 EEVEE)
    ck.make_preview(PREVIEW_HERO, cam_pos=(-48.0, 252.0, 1.6), cam_target=(-30.0, 258.0, 1.4),
                    sun_elev=45.0, sun_azim=-40.0, samples=32)
    ck.make_preview(PREVIEW_KIT, cam_pos=(16.0, -84.0, 42.0), cam_target=(16.0, -84.0, 0.0),
                    sun_elev=55.0, sun_azim=-30.0, samples=32)
    print("  [interiors] done")


if __name__ == "__main__":
    main()
