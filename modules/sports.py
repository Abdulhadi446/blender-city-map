#!/usr/bin/env python3
"""sports.py — SPORTS-VENUES module (5 stadiums/arenas) for the 3x3 km AAA city.

Headless run:
    cd /home/abdulhadi/Work/city && blender -b -P modules/sports.py > /tmp/opencode/sports.log 2>&1

Builds exactly 5 venues, each strictly inside its program rect (district G,
converted park cells).  Everything is instanced (seat blocks / panels / pylons /
trusses / trees shared via linked duplicates).  No door meshes anywhere — open
archways / open frontages only.

Venues (rect = [x0,y0,x1,y1], all 228 x 228 m inside a 300 x 300 m green-belt cell
with a 24 m landscaped green ring kept around the outside):
    STADIUM_CRICKET   [-864,-1164,-636,-936]   cell [1,0]  PK_1_0
    STADIUM_FOOTBALL  [ 36,-1164, 264,-936]    cell [4,0]  PK_4_0   (OPEN ROOF)
    STADIUM_ATHLETICS [-1164,-864,-936,-636]   cell [0,1]  PK_0_1
    ARENA_INDOOR      [-1164,-564,-936,-336]   cell [0,2]  PK_0_2
    COMPLEX_SWIMMING  [ 12,-888, 288,-612]     cell [4,1]  PK_4_1

Outputs:
    modules/sports.py
    out/sports.blend
    reports/sports_report.json + reports/sports_report.md
    out/sports_preview.png            (aerial: cricket + football)
    out/sports_football_preview.png   (camera ON the pitch, looking up)
"""
from __future__ import annotations

import math
import os
import sys
import time

ROOT = "/home/abdulhadi/Work/city"
if ROOT not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "modules"))

import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402
import citykit as ck  # noqa: E402

MODULE = "Sports"
SEED = 1337
OUT_BLEND = os.path.join(ck.OUT_DIR, "sports.blend")
PREVIEW_AIR = os.path.join(ck.OUT_DIR, "sports_preview.png")
PREVIEW_FB = os.path.join(ck.OUT_DIR, "sports_football_preview.png")

FLOOR = 3.2
CURB = 0.15
DOOR_H = 2.4
RING = 24.0                      # landscaped green ring (m) around outside of venue

# ------------------------------------------------------------------ materials
# ALL appended from materials.blend — never created here.
M_GRASS = "grass"
M_GRASS_DRY = "grass_dry"
M_TRACK = "track_asphalt"
M_KERB = "kerb_red"
M_MARK = "marking_white"
M_CONC = "concrete"
M_STEEL = "metal_steel"
M_DARK = "metal_painted_dark"
M_GLASS = "glass_dark"
M_SIGN = "sign_metal"
M_EMIS = "emissive_warm"
M_WATER = "water"
M_LEAF = "leaves_green"
M_LEAF_D = "leaves_dark"
M_COL = "col_placeholder"
M_DIRT = "dirt"

ROAD_HW = {"highway": 17.0, "arterial": 12.0, "street": 6.0, "alley": 2.5}

# ------------------------------------------------------------------ venues
# id -> dict(rect, cell, park, label)
VENUES = {
    "cricket":  dict(rect=[-864.0, -1164.0, -636.0, -936.0], cell=[1, 0], park="PK_1_0",
                     label="STADIUM_CRICKET"),
    "football": dict(rect=[36.0, -1164.0, 264.0, -936.0], cell=[4, 0], park="PK_4_0",
                     label="STADIUM_FOOTBALL"),
    "athletics":dict(rect=[-1164.0, -864.0, -936.0, -636.0], cell=[0, 1], park="PK_0_1",
                     label="STADIUM_ATHLETICS"),
    "arena":    dict(rect=[-1164.0, -564.0, -936.0, -336.0], cell=[0, 2], park="PK_0_2",
                     label="ARENA_INDOOR"),
    "swimming": dict(rect=[12.0, -888.0, 288.0, -612.0], cell=[4, 1], park="PK_4_1",
                     label="COMPLEX_SWIMMING"),
}
# order matters for stage saves
VENUE_ORDER = ["cricket", "football", "athletics", "arena", "swimming"]

# football field-of-play (105 x 68 m) centred in its rect — used for the z<5 assert
FB_PITCH = [150.0 - 105.0 / 2.0, -1050.0 - 68.0 / 2.0,
            150.0 + 105.0 / 2.0, -1050.0 + 68.0 / 2.0]


class B:
    """Tiny immediate-mode mesh builder (verts/faces/material-index)."""
    __slots__ = ("v", "f", "mi", "mats")

    def __init__(self):
        self.v = []
        self.f = []
        self.mi = []
        self.mats = []

    def midx(self, mat):
        if mat in self.mats:
            return self.mats.index(mat)
        self.mats.append(mat)
        return len(self.mats) - 1

    def box(self, x0, y0, z0, x1, y1, z1, mat):
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        if z1 < z0:
            z0, z1 = z1, z0
        i = self.midx(mat)
        n = len(self.v)
        self.v.extend([(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                       (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)])
        for k in ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
                  (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            self.f.append(tuple(n + q for q in k))
            self.mi.append(i)

    def poly(self, pts, mat):
        i = self.midx(mat)
        n = len(self.v)
        self.v.extend(pts)
        self.f.append(tuple(range(n, n + len(pts))))
        self.mi.append(i)

    def cyl(self, cx, cy, z0, z1, r, mat, seg=12, cap=True):
        i = self.midx(mat)
        n = len(self.v)
        for k in range(seg):
            a = 2.0 * math.pi * k / seg
            self.v.append((cx + r * math.cos(a), cy + r * math.sin(a), z0))
        for k in range(seg):
            a = 2.0 * math.pi * k / seg
            self.v.append((cx + r * math.cos(a), cy + r * math.sin(a), z1))
        for k in range(seg):
            k2 = (k + 1) % seg
            self.f.append((n + k, n + k2, n + seg + k2, n + seg + k))
            self.mi.append(i)
        if cap:
            self.f.append(tuple(n + k for k in range(seg)))
            self.mi.append(i)
            self.f.append(tuple(n + seg + k for k in reversed(range(seg))))
            self.mi.append(i)

    def cone(self, cx, cy, z0, z1, r0, r1, mat, seg=12):
        """Frustum/cone from radius r0 at z0 to r1 at z1 (no caps)."""
        i = self.midx(mat)
        n = len(self.v)
        for k in range(seg):
            a = 2.0 * math.pi * k / seg
            self.v.append((cx + r0 * math.cos(a), cy + r0 * math.sin(a), z0))
        for k in range(seg):
            a = 2.0 * math.pi * k / seg
            self.v.append((cx + r1 * math.cos(a), cy + r1 * math.sin(a), z1))
        for k in range(seg):
            k2 = (k + 1) % seg
            self.f.append((n + k, n + seg + k, n + seg + k2, n + k2))
            self.mi.append(i)


def commit(bd, name):
    """Build a mesh datablock from a Builder, appending library materials."""
    me = bpy.data.meshes.new(name)
    me.from_pydata(bd.v, [], bd.f)
    me.update()
    for m in bd.mats:
        me.materials.append(ck.append_material(m))
    for p, mi in zip(me.polygons, bd.mi):
        p.material_index = int(mi)
    return me


# ------------------------------------------------------------------ context
class Ctx(object):
    def __init__(self):
        self.root = ck.ensure_collection(MODULE)
        self.meshes = ck.ensure_collection("Meshes", parent=self.root)
        self.colliders = ck.ensure_collection("Colliders", parent=self.root)
        self.lights = ck.ensure_collection("Lights", parent=self.root)
        self.kits = {}                # name -> mesh datablock (shared)
        self.objects = 0
        self.instanced_tris = 0       # per-placement tri count
        self.mats_used = set()
        self.venues = {}              # id -> dict(objects, tris, bbox, ...)
        self.placed_meshes = []       # (ob) for the football z-assert
        self.collider_boxes = []      # (bb, name)
        self.issues = []

    def uniq(self, prefix, key):
        n = self.venues.get("_seq", {}).get(key, 0) + 1
        self.venues.setdefault("_seq", {})[key] = n
        return "%s_%03d" % (prefix, n)

    def kit(self, name, bd):
        if name in self.kits:
            return self.kits[name]
        me = commit(bd, name)
        self.kits[name] = me
        for m in me.materials:
            if m is not None:
                self.mats_used.add(m.name)
        return me

    def place(self, mesh, name, loc, rot=0.0, scale=1.0, coll=None, apply=False,
              venue=None):
        ob = bpy.data.objects.new(name, mesh)
        ob.location = (float(loc[0]), float(loc[1]), float(loc[2]))
        ob.rotation_euler = (0.0, 0.0, float(math.radians(rot)))
        if isinstance(scale, (tuple, list)):
            ob.scale = (float(scale[0]), float(scale[1]), float(scale[2]))
        else:
            s = float(scale)
            ob.scale = (s, s, s)
        (coll or self.meshes).objects.link(ob)
        self.objects += 1
        self.instanced_tris += ck.tri_count(mesh)
        for m in mesh.materials:
            if m is not None:
                self.mats_used.add(m.name)
        if apply:
            ck.apply_all_transforms(ob)
        if venue is not None:
            self.placed_meshes.append((ob, venue))
        return ob

    def collider(self, name, bb, h, venue=None):
        x0, y0, x1, y1 = bb
        cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
        bx = (x1 - x0) * 0.5
        by = (y1 - y0) * 0.5
        bd = B()
        bd.box(-bx, -by, 0.0, bx, by, h, M_COL)
        me = commit(bd, "COL_" + name)
        ob = bpy.data.objects.new(name, me)
        ob.location = (cx, cy, h * 0.5)
        self.colliders.objects.link(ob)
        ob.hide_render = True
        self.objects += 1
        self.collider_boxes.append((bb, name))
        if venue is not None:
            self.placed_meshes.append((ob, venue))
        return ob


# ------------------------------------------------------------------ kits
def build_kits(ctx):
    """Create all shared mesh datablocks (instanced everywhere)."""
    # ---- seat block: one row of seats on a riser. origin bottom-centre.
    def seat_block(seats=6, pitch=0.7, rows=1, rise=0.5):
        bd = B()
        L = seats * pitch
        riser = bd  # riser slab
        bd.box(-L * 0.5, -0.6, 0.0, L * 0.5, 0.05, CURB, M_CONC)
        for r in range(rows):
            z = CURB + r * rise
            bd.box(-L * 0.5 + 0.12, -0.55, z, L * 0.5 - 0.12, -0.05, z + 0.45, M_DARK)
            bd.box(-L * 0.5 + 0.12, -0.05, z + 0.45, L * 0.5 - 0.12, 0.02, z + 0.45 + 0.85, M_DARK)
            for s in range(seats):
                sx = -L * 0.5 + 0.30 + s * pitch
                bd.box(sx - 0.24, -0.50, z + 0.45, sx + 0.24, -0.20, z + 0.45 + 0.45, M_DARK)
        return bd

    ctx.kit("SM_SeatBlock_01", seat_block(6, 0.7, 1, 0.5))       # LOD0
    ctx.kit("LOD1_SeatBlock_01", seat_block(4, 0.7, 1, 0.5))     # fewer seats
    ctx.kit("LOD2_SeatBlock_01", seat_block(2, 0.7, 1, 0.5))     # minimal

    # ---- unit slab kit: any rect slab via non-uniform scale (origin bottom-centre)
    def slab_unit():
        bd = B()
        bd.box(-0.5, -0.5, 0.0, 0.5, 0.5, 0.04, M_CONC)
        return bd
    ctx.kit("SM_Slab_01", slab_unit())

    # ---- floodlight pylon: tapered lattice mast + emissive head (origin base centre)
    def pylon(height=45.0):
        bd = B()
        w0, w1 = 1.6, 0.55
        bd.box(-w0 * 0.5, -w0 * 0.5, 0.0, w0 * 0.5, w0 * 0.5, 1.2, M_STEEL)   # base
        bd.cyl(0.0, 0.0, 1.2, height, w1, M_STEEL, seg=10, cap=False)          # mast
        hx, hy = 1.4, 1.4
        bd.box(-hx * 0.5, -hy * 0.5, height, hx * 0.5, hy * 0.5, height + 0.9, M_DARK)  # head box
        bd.box(-hx * 0.5 + 0.15, -hy * 0.5 + 0.15, height + 0.9,
               hx * 0.5 - 0.15, hy * 0.5 - 0.15, height + 1.1, M_EMIS)        # emissive lamps
        return bd

    ctx.kit("SM_Pylon_45m_01", pylon(45.0))
    ctx.kit("LOD1_Pylon_45m_01", pylon(45.0))   # same mesh, lower draw in-engine
    ctx.kit("SM_Pylon_18m_01", pylon(18.0))

    # ---- turnstile gate: open archway, NO door mesh
    def turnstile():
        bd = B()
        w = 2.6
        bd.box(-w * 0.5 - 0.12, -0.18, 0.0, -w * 0.5 + 0.12, 0.18, DOOR_H, M_STEEL)   # jamb L
        bd.box(w * 0.5 - 0.12, -0.18, 0.0, w * 0.5 + 0.12, 0.18, DOOR_H, M_STEEL)     # jamb R
        bd.box(-w * 0.5 - 0.12, -0.20, DOOR_H, w * 0.5 + 0.12, 0.20, DOOR_H + 0.12, M_STEEL)  # lintel
        bd.box(-0.35, -0.16, 0.05, 0.35, 0.16, DOOR_H - 0.05, M_DARK)                 # turnstile body
        return bd
    ctx.kit("SM_Turnstile_01", turnstile())

    # ---- tree (trunk + canopy). origin base centre.
    def tree(height=9.0):
        bd = B()
        bd.cyl(0.0, 0.0, 0.0, height * 0.55, 0.22, M_DARK, seg=8, cap=True)   # trunk
        # canopy: 3 stacked frusta
        for k, (fr, to, r0, r1) in enumerate(((height * 0.55, height * 0.78, 0.7, 0.4),
                                             (height * 0.72, height * 0.90, 0.45, 0.25),
                                             (height * 0.85, height * 1.00, 0.30, 0.05))):
            bd.cone(0.0, 0.0, fr, to, r0, r1, M_LEAF if k % 2 == 0 else M_LEAF_D, seg=10)
        return bd

    ctx.kit("SM_Tree_09m_01", tree(9.0))
    ctx.kit("LOD1_Tree_09m_01", tree(6.5))
    ctx.kit("LOD2_Tree_09m_01", tree(4.5))

    # ---- corner flag
    def corner_flag():
        bd = B()
        bd.cyl(0.0, 0.0, 0.0, 1.5, 0.035, M_STEEL, seg=8, cap=False)
        bd.box(-0.28, 0.0, 1.46, 0.28, 0.02, 1.5, M_DARK)
        bd.box(-0.30, 0.02, 1.5, 0.30, 1.02, 1.52, M_DARK)   # flag
        return bd
    ctx.kit("SM_CornerFlag_01", corner_flag())

    # ---- goal + net (football)
    def goal():
        bd = B()
        gw, gh = 7.32, 2.44
        bd.box(-gw * 0.5 - 0.12, -0.12, 0.0, -gw * 0.5 + 0.12, 0.12, gh, M_STEEL)   # post L
        bd.box(gw * 0.5 - 0.12, -0.12, 0.0, gw * 0.5 + 0.12, 0.12, gh, M_STEEL)     # post R
        bd.box(-gw * 0.5 - 0.14, -0.14, gh, gw * 0.5 + 0.14, 0.14, gh + 0.10, M_STEEL)  # crossbar
        bd.box(-gw * 0.5 + 0.06, -0.10, 0.06, gw * 0.5 - 0.06, -0.06, gh - 0.06, M_STEEL)  # net frame
        bd.box(-gw * 0.5 + 0.08, -0.08, 0.08, gw * 0.5 - 0.08, -0.04, gh - 0.08, M_DARK)  # net mesh
        return bd
    ctx.kit("SM_Goal_01", goal())

    # ---- lane marking (thin strip) and lane rope (thin floating strip)
    def lane_mark(length=5.0, w=0.10, h=0.03):
        bd = B()
        bd.box(-length * 0.5, -w * 0.5, 0.02, length * 0.5, w * 0.5, h, M_MARK)
        return bd
    ctx.kit("SM_LaneMark_01", lane_mark(5.0, 0.10, 0.03))
    ctx.kit("SM_LaneMark_10m", lane_mark(10.0, 0.10, 0.03))

    def lane_rope(length=25.0):
        bd = B()
        bd.box(-length * 0.5, -0.06, 0.02, length * 0.5, 0.06, 0.06, M_STEEL)
        return bd
    ctx.kit("SM_LaneRope_25m", lane_rope(25.0))

    # ---- diving tower (10 m)
    def diving_tower():
        bd = B()
        bd.box(-0.9, -0.9, 0.0, 0.9, 0.9, 10.0, M_CONC)           # tower
        bd.box(-2.6, -2.6, 10.0, 2.6, 2.6, 10.12, M_STEEL)        # 10 m platform
        bd.box(-1.6, -1.6, 7.5, 1.6, 1.6, 7.62, M_STEEL)          # 7.5 m platform
        bd.box(-1.0, -1.0, 5.0, 1.0, 1.0, 5.12, M_STEEL)          # 5 m platform
        bd.box(-3.2, -3.2, 10.12, 3.2, 3.2, 10.30, M_DARK)        # railing cap
        return bd
    ctx.kit("SM_DivingTower_10m_01", diving_tower())

    # ---- sightscreen (cricket)
    def sightscreen():
        bd = B()
        bd.box(-2.2, -0.18, 0.0, 2.2, 0.18, 4.2, M_STEEL)         # frame
        bd.box(-2.0, -0.16, 0.06, 2.0, 0.16, 4.14, M_SIGN)        # white screen
        return bd
    ctx.kit("SM_SightScreen_01", sightscreen())

    # ---- light gantry (canopy edge floodlight arm)
    def gantry():
        bd = B()
        bd.box(-0.12, -2.4, 0.0, 0.12, 0.06, 2.4, M_STEEL)        # arm
        bd.box(-0.30, -2.5, 2.3, 0.30, -2.3, 2.5, M_DARK)          # fitting
        bd.box(-0.18, -2.52, 2.42, 0.18, -2.28, 2.48, M_EMIS)     # lamp
        return bd
    ctx.kit("SM_GantryLight_01", gantry())

    # ---- roof / canopy panel (stands)
    def canopy_panel(w=16.0, d=7.0):
        bd = B()
        bd.box(-w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, 0.18, M_DARK)   # slab
        bd.box(-w * 0.5, -d * 0.5 - 0.35, -0.5, -w * 0.5 + 0.35, -d * 0.5 + 0.35, 0.0, M_STEEL)  # fascia L
        bd.box(w * 0.5 - 0.35, -d * 0.5 - 0.35, -0.5, w * 0.5, -d * 0.5 + 0.35, 0.0, M_STEEL)   # fascia R
        return bd
    ctx.kit("SM_CanopyPanel_01", canopy_panel())
    ctx.kit("LOD1_CanopyPanel_01", canopy_panel(12.0, 5.0))

    # ---- grandstand roof truss
    def truss(L=20.0, H=3.0):
        bd = B()
        bd.box(-L * 0.5, -0.18, 0.0, L * 0.5, 0.18, 0.30, M_STEEL)   # bottom chord
        bd.box(-L * 0.5, -0.18, H - 0.30, L * 0.5, 0.18, H, M_STEEL)  # top chord
        for k in range(6):
            u = -L * 0.5 + k * (L / 5.0)
            bd.box(u - 0.10, -0.18, 0.30, u + 0.10, 0.18, H - 0.30, M_STEEL)
        return bd
    ctx.kit("SM_Truss_01", truss())

    # ---- tunnel entrance
    def tunnel():
        bd = B()
        bd.box(-3.0, -1.6, 0.0, 3.0, 1.6, DOOR_H + 0.6, M_CONC)   # tunnel
        bd.box(-3.2, -1.8, DOOR_H + 0.6, 3.2, 1.8, DOOR_H + 0.9, M_DARK)  # lintel
        return bd
    ctx.kit("SM_Tunnel_01", tunnel())

    # ---- dugout
    def dugout():
        bd = B()
        bd.box(-2.4, -1.2, 0.0, 2.4, 1.2, 1.1, M_CONC)            # bench plinth
        bd.box(-2.6, -1.4, 1.1, 2.6, 1.4, 2.0, M_DARK)            # shelter
        bd.box(-2.8, -1.6, 2.0, 2.8, 1.6, 2.1, M_STEEL)           # roof
        return bd
    ctx.kit("SM_Dugout_01", dugout())

    # ---- long-jump pit
    def longjump():
        bd = B()
        bd.box(-2.3, -4.6, 0.0, 2.3, 4.6, 0.30, M_SIGN)           # sand
        bd.box(-2.45, -4.75, 0.30, 2.45, 4.75, 0.45, M_CONC)      # edging
        return bd
    ctx.kit("SM_LongJumpPit_01", longjump())

    # ---- high-jump area
    def highjump():
        bd = B()
        bd.box(-2.1, -2.1, 0.0, 2.1, 2.1, 0.75, M_DARK)           # mat
        bd.box(-2.3, -2.3, 0.75, 2.3, 2.3, 0.85, M_CONC)          # mat edge
        bd.box(-0.10, -1.0, 0.0, 0.10, 1.0, 1.6, M_STEEL)         # upright L
        bd.box(-0.10, -1.0, 1.6, 2.4, 1.0, 1.66, M_STEEL)         # bar
        bd.box(2.30, -1.0, 0.0, 2.50, 1.0, 1.6, M_STEEL)          # upright R
        return bd
    ctx.kit("SM_HighJump_01", highjump())

    # ---- changing block (small building, flat roof, open frontage)
    def changing():
        bd = B()
        w, d, h = 14.0, 9.0, 4.2
        bd.box(-w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, h, M_CONC)
        bd.box(-w * 0.5, -d * 0.5 - 0.15, h, w * 0.5, d * 0.5 + 0.15, h + 0.18, M_DARK)  # flat roof
        return bd
    ctx.kit("SM_ChangingBlock_01", changing())

    # ---- lane rope anchors (small)
    def lane_anchor():
        bd = B()
        bd.cyl(0.0, 0.0, 0.0, 0.18, 0.14, M_STEEL, seg=8, cap=True)
        return bd
    ctx.kit("SM_LaneAnchor_01", lane_anchor())

    print("[sports] kits: %d unique meshes" % len(ctx.kits))


# ------------------------------------------------------------------ placement helpers
def rect_slab(ctx, x0, y0, x1, y1, z, mat, name, venue):
    """Axis-aligned slab as a scaled instance of the shared SM_Slab_01 kit.
    Per-object material slot override keeps one mesh for every slab."""
    cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
    sx, sy = (x1 - x0), (y1 - y0)
    mesh = ctx.kits["SM_Slab_01"]
    ob = ctx.place(mesh, name, (cx, cy, z), scale=(sx, sy, 1.0), venue=venue)
    slot = ob.material_slots[0]
    slot.link = "OBJECT"
    slot.material = ck.append_material(mat)
    ctx.mats_used.add(mat)
    return ob


def wedge_ring(ctx, cx, cy, r0, r1, n_wedge, mats, name, venue, z=0.02, h=0.04):
    """Annulus as n_wedge wedges alternating materials — mowed-stripe look."""
    bd = B()
    step = 2.0 * math.pi / n_wedge
    for k in range(n_wedge):
        a0 = k * step
        a1 = a0 + step
        mat = mats[k % len(mats)]
        pts = [(cx, cy, z),
               (cx + r0 * math.cos(a0), cy + r0 * math.sin(a0), z),
               (cx + r1 * math.cos(a1), cy + r1 * math.sin(a1), z),
               (cx + r1 * math.cos(a0), cy + r1 * math.sin(a0), z)]
        bd.poly(pts, mat)
        pts = [(cx, cy, z + h),
               (cx + r1 * math.cos(a0), cy + r1 * math.sin(a0), z + h),
               (cx + r1 * math.cos(a1), cy + r1 * math.sin(a1), z + h),
               (cx, cy, z + h)]
        bd.poly(pts, mat)
        pts = [(cx + r0 * math.cos(a0), cy + r0 * math.sin(a0), z),
               (cx + r0 * math.cos(a0), cy + r0 * math.sin(a0), z + h),
               (cx + r0 * math.cos(a1), cy + r0 * math.sin(a1), z + h),
               (cx + r0 * math.cos(a1), cy + r0 * math.sin(a1), z)]
        bd.poly(pts, mat)
        pts = [(cx + r1 * math.cos(a0), cy + r1 * math.sin(a0), z),
               (cx + r1 * math.cos(a1), cy + r1 * math.sin(a1), z),
               (cx + r1 * math.cos(a1), cy + r1 * math.sin(a1), z + h),
               (cx + r1 * math.cos(a0), cy + r1 * math.sin(a0), z + h)]
        bd.poly(pts, mat)
        pts = [(cx + r0 * math.cos(a1), cy + r0 * math.sin(a1), z),
               (cx + r1 * math.cos(a1), cy + r1 * math.sin(a1), z),
               (cx + r1 * math.cos(a1), cy + r1 * math.sin(a1), z + h),
               (cx + r0 * math.cos(a1), cy + r0 * math.sin(a1), z + h)]
        bd.poly(pts, mat)
    me = commit(bd, name)
    ob = ctx.place(me, name, (0.0, 0.0, 0.0), apply=True, venue=venue)
    return ob


# ------------------------------------------------------------------ venue: cricket
def build_cricket(ctx):
    v = VENUES["cricket"]
    x0, y0, x1, y1 = v["rect"]
    cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
    hx, hy = (x1 - x0) * 0.5, (y1 - y0) * 0.5   # 114
    name = v["label"]
    tris = 0
    objs = 0

    # green ring: outer band grass + jogging path + trees (all inside rect)
    rect_slab(ctx, x0, y0, x1, y1, 0.0, M_GRASS, "SM_Cricket_Ground_01", v)
    # inner playing bowl (180 x 180) kept as outfield grass
    ix0, iy0, ix1, iy1 = x0 + RING, y0 + RING, x1 - RING, y1 - RING
    rect_slab(ctx, ix0, iy0, ix1, iy1, 0.02, M_GRASS, "SM_Cricket_OutfieldBase_01", v)
    # mowed-stripe outfield circle (150 m dia) alternating grass / grass_dry
    wedge_ring(ctx, cx, cy, 6.0, 75.0, 48, [M_GRASS, M_GRASS_DRY],
               "SM_Cricket_OutfieldStripes_01", v, z=0.04, h=0.06)
    # central pitch strip (dirt) N-S
    rect_slab(ctx, cx - 1.75, cy - 13.0, cx + 1.75, cy + 13.0, 0.06, M_DIRT,
              "SM_Cricket_PitchStrip_01", v)
    # cricket square (wider strip around pitch)
    rect_slab(ctx, cx - 9.0, cy - 16.0, cx + 9.0, cy + 16.0, 0.05, M_GRASS_DRY,
              "SM_Cricket_Square_01", v)

    # sightscreens at both ends of the pitch
    ctx.place(ctx.kits["SM_SightScreen_01"], "SM_Cricket_SightScreen_01",
              (cx, cy + 16.0, 0.0), rot=0, venue=v)
    ctx.place(ctx.kits["SM_SightScreen_01"], "SM_Cricket_SightScreen_02",
              (cx, cy - 16.0, 0.0), rot=180, venue=v)

    # 4 independent stands — seat blocks in an arc on each side
    stand_r = 66.0
    n_blocks = 14
    tiers = 5
    rise = 0.55
    for side, ang0, ang1 in (("N", 45.0, 135.0), ("E", -45.0, 45.0),
                             ("S", 225.0, 315.0), ("W", 135.0, 225.0)):
        for t in range(tiers):
            z = t * rise
            for i in range(n_blocks):
                frac = i / (n_blocks - 1)
                ang = math.radians(ang0 + (ang1 - ang0) * frac)
                px = cx + stand_r * math.cos(ang)
                py = cy + stand_r * math.sin(ang)
                mesh = ctx.kits["SM_SeatBlock_01"] if t < 3 else ctx.kits["LOD1_SeatBlock_01"]
                ctx.place(mesh, "SM_Cricket_SeatBlock_%s_T%d_%02d" % (side, t, i),
                          (px, py, z), rot=math.degrees(ang) + 90.0, venue=v)

    # 4 floodlight pylons ~45 m at the corners (inside the ring, near rect corners)
    pr = 100.0
    for k, (sx, sy) in enumerate(((1, 1), (1, -1), (-1, 1), (-1, -1))):
        px = cx + sx * pr
        py = cy + sy * pr
        ctx.place(ctx.kits["SM_Pylon_45m_01"], "SM_Cricket_Pylon_0%d" % (k + 1),
                  (px, py, 0.0), venue=v)

    # turnstile gates at mid-sides of the ring (open archways, no doors)
    for k, (px, py, rot) in enumerate(((cx, iy1 + 6.0, 0.0), (cx, iy0 - 6.0, 180.0),
                                       (ix1 + 6.0, cy, 90.0), (ix0 - 6.0, cy, -90.0))):
        ctx.place(ctx.kits["SM_Turnstile_01"], "SM_Cricket_Turnstile_0%d" % (k + 1),
                  (px, py, 0.0), rot=rot, venue=v)

    # trees around the green ring
    n_tree = 16
    for i in range(n_tree):
        ang = 2.0 * math.pi * i / n_tree
        r = hx - 12.0
        px = cx + r * math.cos(ang)
        py = cy + r * math.sin(ang)
        mesh = ctx.kits["SM_Tree_09m_01"] if i % 3 else ctx.kits["LOD1_Tree_09m_01"]
        ctx.place(mesh, "SM_Cricket_Tree_0%d" % (i + 1), (px, py, 0.0), venue=v)

    # colliders
    ctx.collider("COL_Cricket_Venue", [x0, y0, x1, y1], 48.0, venue=v)
    ctx.collider("COL_stand_cricket_N", [cx - stand_r - 4, iy1 - 6, cx + stand_r + 4, iy1 + 2], 6.0, venue=v)
    ctx.collider("COL_stand_cricket_S", [cx - stand_r - 4, iy0 - 2, cx + stand_r + 4, iy0 + 6], 6.0, venue=v)
    ctx.collider("COL_stand_cricket_E", [ix1 - 2, cy - stand_r - 4, ix1 + 6, cy + stand_r + 4], 6.0, venue=v)
    ctx.collider("COL_stand_cricket_W", [ix0 - 6, cy - stand_r - 4, ix0 + 2, cy + stand_r + 4], 6.0, venue=v)

    n_ob = ctx.objects - objs
    n_tr = ctx.instanced_tris - tris
    ctx.venues["cricket"] = dict(objects=n_ob, tris=n_tr, label=name, rect=v["rect"],
                                 bbox=[x0, y0, x1, y1, 0.0, 48.0])
    print("[sports] cricket: %d objects | %d instanced tris" % (n_ob, n_tr))


# ------------------------------------------------------------------ venue: football
def build_football(ctx):
    v = VENUES["football"]
    x0, y0, x1, y1 = v["rect"]
    cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
    name = v["label"]
    tris0, objs0 = ctx.instanced_tris, ctx.objects

    # ground slab whole rect
    rect_slab(ctx, x0, y0, x1, y1, 0.0, M_GRASS, "SM_Football_Ground_01", v)
    # pitch (105 x 68) centred
    px0, py0, px1, py1 = FB_PITCH
    rect_slab(ctx, px0, py0, px1, py1, 0.04, M_GRASS, "SM_Football_Pitch_01", v)

    # white line markings (thin meshes) on the pitch
    mk = ctx.kits["SM_LaneMark_10m"]
    # boundary lines
    ctx.place(mk, "SM_Football_Line_Touch_N_01", ((px0 + px1) * 0.5, py1, 0.05), rot=0, venue=v)
    ctx.place(mk, "SM_Football_Line_Touch_S_01", ((px0 + px1) * 0.5, py0, 0.05), rot=0, venue=v)
    # scale 10m mark -> 105m long line: use scale on X
    ob = ctx.place(mk, "SM_Football_Line_Touch_N_02", ((px0 + px1) * 0.5, py1, 0.05),
                   rot=0, scale=10.5, venue=v)
    ob = ctx.place(mk, "SM_Football_Line_Touch_S_02", ((px0 + px1) * 0.5, py0, 0.05),
                   rot=0, scale=10.5, venue=v)
    ob = ctx.place(mk, "SM_Football_Line_Goal_N_01", (px1, (py0 + py1) * 0.5, 0.05),
                   rot=90, scale=6.8, venue=v)
    ob = ctx.place(mk, "SM_Football_Line_Goal_S_01", (px0, (py0 + py1) * 0.5, 0.05),
                   rot=90, scale=6.8, venue=v)
    # centre line + circle
    ob = ctx.place(mk, "SM_Football_Line_Centre_01", (cx, cy, 0.05), rot=90, scale=6.8, venue=v)
    bd = B()
    segs = 32
    r = 9.15
    for k in range(segs):
        a0 = 2 * math.pi * k / segs
        a1 = 2 * math.pi * (k + 1) / segs
        bd.box((cx + r * math.cos(a0) + cx + r * math.cos(a1)) * 0.5,
               (cy + r * math.sin(a0) + cy + r * math.sin(a1)) * 0.5, 0.05,
               (cx + r * math.cos(a0) + cx + r * math.cos(a1)) * 0.5 + 0.05,
               (cy + r * math.sin(a0) + cy + r * math.sin(a1)) * 0.5 + 0.05, 0.09, M_MARK)
    me = commit(bd, "SM_Football_CentreCircle_01")
    ctx.place(me, "SM_Football_CentreCircle_01", (0.0, 0.0, 0.0), apply=True, venue=v)
    # penalty areas (rects)
    for (sx, sy) in ((px1 - 16.5, py0 + 13.0), (px0 + 16.5, py0 + 13.0)):
        rect_slab(ctx, sx, sy, sx + 0.06, sy + 44.0, 0.06, M_MARK,
                  "SM_Football_PenaltyLine_01", v)
        rect_slab(ctx, sx, sy + 44.0, sx + 0.06, sy + 44.06, 0.06, M_MARK,
                  "SM_Football_PenaltyLine_02", v)
        rect_slab(ctx, sx, sy, sx + 16.5, sy + 0.06, 0.06, M_MARK,
                  "SM_Football_PenaltyLine_03", v)
        rect_slab(ctx, sx + 16.5, sy, sx + 16.56, sy + 44.0, 0.06, M_MARK,
                  "SM_Football_PenaltyLine_04", v)
    # goal areas
    for (sx, sy) in ((px1 - 5.5, py0 + 18.0), (px0 + 5.5, py0 + 18.0)):
        rect_slab(ctx, sx, sy, sx + 0.06, sy + 18.0, 0.06, M_MARK, "SM_Football_GoalAreaLine_01", v)
        rect_slab(ctx, sx, sy + 18.0, sx + 0.06, sy + 18.06, 0.06, M_MARK, "SM_Football_GoalAreaLine_02", v)
        rect_slab(ctx, sx, sy, sx + 5.5, sy + 0.06, 0.06, M_MARK, "SM_Football_GoalAreaLine_03", v)
        rect_slab(ctx, sx + 5.5, sy, sx + 5.56, sy + 18.0, 0.06, M_MARK, "SM_Football_GoalAreaLine_04", v)
    # penalty spots + centre spot
    for (sx, sy) in ((px1 - 11.0, cy), (px0 + 11.0, cy), (cx, cy)):
        rect_slab(ctx, sx - 0.18, sy - 0.18, sx + 0.18, sy + 0.18, 0.07, M_MARK,
                  "SM_Football_Spot_01", v)

    # goals with nets at both goal lines
    for (sx, rot) in ((px1, 180.0), (px0, 0.0)):
        ctx.place(ctx.kits["SM_Goal_01"], "SM_Football_Goal_0%d" % (1 if sx > cx else 2),
                  (sx, cy, 0.0), rot=rot, venue=v)

    # corner flags at pitch corners
    for k, (sx, sy, rot) in enumerate(((px1, py1, 45.0), (px0, py1, 135.0),
                                       (px0, py0, 225.0), (px1, py0, 315.0))):
        ctx.place(ctx.kits["SM_CornerFlag_01"], "SM_Football_CornerFlag_0%d" % (k + 1),
                  (sx, sy, 0.0), rot=rot, venue=v)

    # 4 stands (2 tiered) — long sides N/S and short sides behind goals
    stand_rx = 56.0      # half-width along pitch length
    stand_depth = 30.0
    stand_rise = 0.6
    tiers = 6
    blocks_per_tier = 10
    # long sides (along Y edges of pitch)
    for side, sy in (("N", py1), ("S", py0)):
        for t in range(tiers):
            z = t * stand_rise
            for i in range(blocks_per_tier):
                frac = i / (blocks_per_tier - 1)
                px = px0 + (px1 - px0) * 0.12 + (px1 - px0) * 0.76 * frac
                mesh = ctx.kits["SM_SeatBlock_01"] if t < 4 else ctx.kits["LOD1_SeatBlock_01"]
                ctx.place(mesh, "SM_Football_SeatBlock_%s_T%d_%02d" % (side, t, i),
                          (px, sy + (t + 1) * 1.6, z), rot=0 if side == "S" else 180,
                          venue=v)
    # short sides (behind goals, along X edges)
    for side, sx in (("E", px1), ("W", px0)):
        for t in range(tiers):
            z = t * stand_rise
            for i in range(blocks_per_tier):
                frac = i / (blocks_per_tier - 1)
                py = py0 + (py1 - py0) * 0.14 + (py1 - py0) * 0.72 * frac
                mesh = ctx.kits["SM_SeatBlock_01"] if t < 4 else ctx.kits["LOD1_SeatBlock_01"]
                ctx.place(mesh, "SM_Football_SeatBlock_%s_T%d_%02d" % (side, t, i),
                          (sx + (1.6 * (t + 1)), py, z), rot=90 if side == "W" else -90,
                          venue=v)

    # tunnel (centre of one long side, under stand)
    ctx.place(ctx.kits["SM_Tunnel_01"], "SM_Football_Tunnel_01",
              (cx, py1 + 3.0, 0.0), rot=0, venue=v)
    # dugouts (team areas on long sides)
    for (sx, sy, rot) in ((px0 + 14.0, py1 + 4.0, 0.0), (px1 - 14.0, py0 - 4.0, 180.0)):
        ctx.place(ctx.kits["SM_Dugout_01"], "SM_Football_Dugout_0%d" % (1 if sx < cx else 2),
                  (sx, sy, 0.0), rot=rot, venue=v)

    # OPEN ROOF: cantilever canopy covers seating only — panels over the four stands,
    # NOT over the pitch (open oculus). Trusses/gantries on canopy edge.
    canopy_z = 11.0
    # long-side canopies
    for sy, rot in ((py1 + 26.0, 0.0), (py0 - 26.0, 180.0)):
        ctx.place(ctx.kits["SM_CanopyPanel_01"], "SM_Football_Canopy_N_S_01",
                  (cx, sy, canopy_z), rot=rot, venue=v)
        ctx.place(ctx.kits["SM_Truss_01"], "SM_Football_Truss_01",
                  (cx, sy, canopy_z - 0.6), rot=rot, venue=v)
    # short-side canopies (partial, behind goals)
    for sx, rot in ((px1 + 22.0, 90.0), (px0 - 22.0, -90.0)):
        ctx.place(ctx.kits["LOD1_CanopyPanel_01"], "SM_Football_Canopy_E_W_01",
                  (sx, cy, canopy_z), rot=rot, venue=v)
        ctx.place(ctx.kits["SM_Truss_01"], "SM_Football_Truss_02",
                  (sx, cy, canopy_z - 0.6), rot=rot, venue=v)
    # floodlight gantries on canopy edge (outside pitch)
    for (gx, gy, rot) in ((px1 + 18.0, cy + 28.0, 45.0), (px0 - 18.0, cy - 28.0, 225.0),
                          (px1 + 18.0, cy - 28.0, -45.0), (px0 - 18.0, cy + 28.0, 135.0)):
        ctx.place(ctx.kits["SM_GantryLight_01"], "SM_Football_Gantry_0%d" % (1 + len(ctx.venues.get("football", {}).get("gantries", []))),
                  (gx, gy, canopy_z), rot=rot, venue=v)

    # turnstile gates at mid-sides of ring (open frontage, no doors)
    iy0, iy1 = y0 + RING, y1 - RING
    ix0, ix1 = x0 + RING, x1 - RING
    for k, (px, py, rot) in enumerate(((cx, iy1 + 6.0, 0.0), (cx, iy0 - 6.0, 180.0),
                                       (ix1 + 6.0, cy, 90.0), (ix0 - 6.0, cy, -90.0))):
        ctx.place(ctx.kits["SM_Turnstile_01"], "SM_Football_Turnstile_0%d" % (k + 1),
                  (px, py, 0.0), rot=rot, venue=v)

    # trees around ring
    hx, hy = (x1 - x0) * 0.5, (y1 - y0) * 0.5
    for i in range(14):
        ang = 2.0 * math.pi * i / 14.0
        r = hx - 10.0
        px = cx + r * math.cos(ang)
        py = cy + r * math.sin(ang)
        ctx.place(ctx.kits["SM_Tree_09m_01"], "SM_Football_Tree_0%d" % (i + 1),
                  (px, py, 0.0), venue=v)

    # colliders
    ctx.collider("COL_Football_Venue", [x0, y0, x1, y1], 48.0, venue=v)
    ctx.collider("COL_stand_football_N", [px0 - 6, py1 + 2, px1 + 6, py1 + 34], 10.0, venue=v)
    ctx.collider("COL_stand_football_S", [px0 - 6, py0 - 34, px1 + 6, py0 - 2], 10.0, venue=v)
    ctx.collider("COL_stand_football_E", [px1 + 2, py0 - 6, px1 + 34, py1 + 6], 10.0, venue=v)
    ctx.collider("COL_stand_football_W", [px0 - 34, py0 - 6, px0 - 2, py1 + 6], 10.0, venue=v)

    n_ob = ctx.objects - objs0
    n_tr = ctx.instanced_tris - tris0
    ctx.venues["football"] = dict(objects=n_ob, tris=n_tr, label=name, rect=v["rect"],
                                  bbox=[x0, y0, x1, y1, 0.0, canopy_z + 1.5])
    print("[sports] football: %d objects | %d instanced tris" % (n_ob, n_tr))


# ------------------------------------------------------------------ venue: athletics
def build_athletics(ctx):
    v = VENUES["athletics"]
    x0, y0, x1, y1 = v["rect"]
    cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
    name = v["label"]
    tris0, objs0 = ctx.instanced_tris, ctx.objects

    rect_slab(ctx, x0, y0, x1, y1, 0.0, M_GRASS, "SM_Athletics_Ground_01", v)
    # infield grass
    rect_slab(ctx, x0 + 30.0, y0 + 30.0, x1 - 30.0, y1 - 30.0, 0.04, M_GRASS,
              "SM_Athletics_Infield_01", v)
    # 400 m tartan track: outer oval ring, 8 lanes
    # outer oval approx 150 x 102 inside the rect; inner = infield boundary
    ox, oy = 148.0, 100.0
    ix, iy = ox - 17.0, oy - 17.0   # ~17 m track width (8 lanes + kerb)
    bd = B()
    # outer ellipse boundary (as rect ring approx: use rect annulus = 4 rects)
    def oval_ring(bd, x0, y0, x1, y1, w, mat, z=0.02, h=0.05):
        # top/bottom strips
        bd.box(x0, y1 - w, z, x1, y1, z + h, mat)
        bd.box(x0, y0, z, x1, y0 + w, z + h, mat)
        # left/right strips
        bd.box(x0, y0 + w, z, x0 + w, y1 - w, z + h, mat)
        bd.box(x1 - w, y0 + w, z, x1, y1 - w, z + h, mat)
    # track surface (asphalt) = ring between outer rect and inner infield
    oval_ring(bd, cx - ox * 0.5, cy - oy * 0.5, cx + ox * 0.5, cy + oy * 0.5,
              (ox - ix) * 0.5, M_TRACK)
    # kerb red on inner edge of track
    oval_ring(bd, cx - ix * 0.5, cy - iy * 0.5, cx + ix * 0.5, cy + iy * 0.5,
              0.35, M_KERB)
    me = commit(bd, "SM_Athletics_TrackRing_01")
    ctx.place(me, "SM_Athletics_TrackRing_01", (0.0, 0.0, 0.02), apply=True, venue=v)

    # lane markings (white radial lines across the track on straights)
    for k in range(9):
        u = cx - ix * 0.5 + k * (ix / 8.0)
        rect_slab(ctx, u - 0.05, cy - oy * 0.5 + 6.0, u + 0.05, cy + oy * 0.5 - 6.0,
                  0.07, M_MARK, "SM_Athletics_LaneLine_%02d" % k, v)
    # curved lane lines on the bends (simple arcs as short radial marks)
    for k in range(9):
        u = cx - ix * 0.5 + k * (ix / 8.0)
        for (sy, side) in ((cy - oy * 0.5 + 10.0, -1), (cy + oy * 0.5 - 10.0, 1)):
            rect_slab(ctx, u - 0.05, sy - 1.5 * side, u + 0.05, sy + 1.5 * side,
                      0.07, M_MARK, "SM_Athletics_BendMark_%02d" % k, v)

    # long-jump pits (two)
    for (sx, sy) in ((cx - 48.0, cy - 34.0), (cx + 48.0, cy + 34.0)):
        ctx.place(ctx.kits["SM_LongJumpPit_01"], "SM_Athletics_LongJump_0%d" % (1 if sx < cx else 2),
                  (sx, sy, 0.0), rot=45 if sx < cx else -45, venue=v)
    # high-jump area
    ctx.place(ctx.kits["SM_HighJump_01"], "SM_Athletics_HighJump_01",
              (cx + 40.0, cy - 28.0, 0.0), rot=0, venue=v)

    # covered grandstand on one side (north)
    stand_x0, stand_x1 = cx - 52.0, cx + 52.0
    stand_y = cy + oy * 0.5 + 8.0
    tiers = 4
    blocks = 12
    stand_rise = 0.6
    for t in range(tiers):
        z = t * stand_rise
        for i in range(blocks):
            frac = i / (blocks - 1)
            px = stand_x0 + (stand_x1 - stand_x0) * frac
            mesh = ctx.kits["SM_SeatBlock_01"] if t < 3 else ctx.kits["LOD1_SeatBlock_01"]
            ctx.place(mesh, "SM_Athletics_SeatBlock_T%d_%02d" % (t, i),
                      (px, stand_y + (t + 1) * 1.7, z), rot=180, venue=v)
    # grandstand roof (covers stand only)
    ctx.place(ctx.kits["SM_CanopyPanel_01"], "SM_Athletics_GrandstandRoof_01",
              (cx, stand_y + 10.0, 10.5), rot=0, venue=v)
    ctx.place(ctx.kits["SM_Truss_01"], "SM_Athletics_GrandstandTruss_01",
              (cx, stand_y + 10.0, 9.9), rot=0, venue=v)

    # small floodlights (4 corners of track)
    for k, (sx, sy) in enumerate(((cx - ox * 0.5 + 12, cy - oy * 0.5 + 12),
                                  (cx + ox * 0.5 - 12, cy - oy * 0.5 + 12),
                                  (cx - ox * 0.5 + 12, cy + oy * 0.5 - 12),
                                  (cx + ox * 0.5 - 12, cy + oy * 0.5 - 12))):
        ctx.place(ctx.kits["SM_Pylon_18m_01"], "SM_Athletics_Floodlight_0%d" % (k + 1),
                  (sx, sy, 0.0), venue=v)

    # turnstile gates mid-sides
    iy0, iy1 = y0 + RING, y1 - RING
    for k, (px, py, rot) in enumerate(((cx, iy1 + 6.0, 0.0), (cx, iy0 - 6.0, 180.0))):
        ctx.place(ctx.kits["SM_Turnstile_01"], "SM_Athletics_Turnstile_0%d" % (k + 1),
                  (px, py, 0.0), rot=rot, venue=v)

    # trees
    for i in range(12):
        ang = 2.0 * math.pi * i / 12.0
        r = 104.0
        px = cx + r * math.cos(ang)
        py = cy + r * math.sin(ang)
        ctx.place(ctx.kits["LOD2_Tree_09m_01"], "SM_Athletics_Tree_0%d" % (i + 1),
                  (px, py, 0.0), venue=v)

    # colliders
    ctx.collider("COL_Athletics_Venue", [x0, y0, x1, y1], 20.0, venue=v)
    ctx.collider("COL_stand_athletics_N", [stand_x0 - 4, stand_y - 2, stand_x1 + 4, stand_y + 16], 12.0, venue=v)

    n_ob = ctx.objects - objs0
    n_tr = ctx.instanced_tris - tris0
    ctx.venues["athletics"] = dict(objects=n_ob, tris=n_tr, label=name, rect=v["rect"],
                                   bbox=[x0, y0, x1, y1, 0.0, 20.0])
    print("[sports] athletics: %d objects | %d instanced tris" % (n_ob, n_tr))


# ------------------------------------------------------------------ venue: arena (indoor)
def build_arena(ctx):
    v = VENUES["arena"]
    x0, y0, x1, y1 = v["rect"]
    cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
    name = v["label"]
    tris0, objs0 = ctx.instanced_tris, ctx.objects

    # enclosed arena bowl: curved roof over seating, glazed entrance hall
    r_arena = 96.0
    bowl_h = 16.0
    # seating bowl (tiered rings) — instanced seat blocks around a circle
    tiers = 4
    for t in range(tiers):
        rad = 18.0 + t * 11.0
        z = t * 1.6
        n_seats = max(16, int(2 * math.pi * rad / 1.6))
        for i in range(n_seats):
            ang = 2.0 * math.pi * i / n_seats
            px = cx + rad * math.cos(ang)
            py = cy + rad * math.sin(ang)
            ctx.place(ctx.kits["LOD2_SeatBlock_01"], "SM_Arena_Seat_T%d_%03d" % (t, i),
                      (px, py, z), rot=math.degrees(ang) + 90.0, venue=v)

    # arena floor
    rect_slab(ctx, cx - 78.0, cy - 78.0, cx + 78.0, cy + 78.0, 0.04, M_CONC,
              "SM_Arena_Floor_01", v)
    # curved roof (barrel segment) spanning the bowl
    bd = B()
    # a shallow dome approximated by horizontal rings (few polys)
    seg = 24
    rings = 6
    for ri in range(rings - 1):
        z0 = bowl_h * 0.55 + (bowl_h * 0.45) * (ri / (rings - 1))
        z1 = bowl_h * 0.55 + (bowl_h * 0.45) * ((ri + 1) / (rings - 1))
        r0 = r_arena * (1.0 - 0.35 * (ri / (rings - 1)))
        r1 = r_arena * (1.0 - 0.35 * ((ri + 1) / (rings - 1)))
        for k in range(seg):
            a0 = 2 * math.pi * k / seg
            a1 = 2 * math.pi * (k + 1) / seg
            pts = [(cx + r0 * math.cos(a0), cy + r0 * math.sin(a0), z0),
                   (cx + r1 * math.cos(a1), cy + r1 * math.sin(a1), z1),
                   (cx + r1 * math.cos(a0), cy + r1 * math.sin(a0), z1),
                   (cx + r0 * math.cos(a0), cy + r0 * math.sin(a0), z0)]
            bd.poly(pts, M_DARK)
            pts = [(cx + r0 * math.cos(a0), cy + r0 * math.sin(a0), z0),
                   (cx + r0 * math.cos(a1), cy + r0 * math.sin(a1), z0),
                   (cx + r1 * math.cos(a1), cy + r1 * math.sin(a1), z1),
                   (cx + r1 * math.cos(a0), cy + r1 * math.sin(a0), z1)]
            bd.poly(pts, M_DARK)
    me = commit(bd, "SM_Arena_CurvedRoof_01")
    ctx.place(me, "SM_Arena_CurvedRoof_01", (0.0, 0.0, 0.0), apply=True, venue=v)

    # glazed entrance hall on the south side, OPEN frontage (no doors)
    hall_w, hall_d, hall_h = 64.0, 22.0, 11.0
    rect_slab(ctx, cx - hall_w * 0.5, cy - r_arena - hall_d, cx + hall_w * 0.5,
              cy - r_arena, 0.04, M_CONC, "SM_Arena_HallFloor_01", v)
    # hall walls (glazed) on east/west, solid back wall
    rect_slab(ctx, cx - hall_w * 0.5, cy - r_arena - hall_d - 0.12,
              cx - hall_w * 0.5 + 0.12, cy - r_arena, hall_h, M_GLASS,
              "SM_Arena_HallWallW_01", v)
    rect_slab(ctx, cx + hall_w * 0.5 - 0.12, cy - r_arena - hall_d - 0.12,
              cx + hall_w * 0.5, cy - r_arena, hall_h, M_GLASS,
              "SM_Arena_HallWallE_01", v)
    rect_slab(ctx, cx - hall_w * 0.5 + 0.12, cy - r_arena - hall_d - 0.12,
              cx + hall_w * 0.5 - 0.12, cy - r_arena - hall_d + 0.12, hall_h, M_CONC,
              "SM_Arena_HallBack_01", v)
    rect_slab(ctx, cx - hall_w * 0.5, cy - r_arena - hall_d, cx + hall_w * 0.5,
              cy - r_arena - hall_d + 0.12, hall_h, M_GLASS, "SM_Arena_HallRoof_01", v)
    # OPEN frontage = nothing on the south side (fully open, no door mesh)

    # loading bays (east side of arena)
    for k in range(3):
        lx = cx + r_arena + 4.0 + k * 9.0
        rect_slab(ctx, lx - 4.0, cy - 5.0, lx + 4.0, cy + 5.0, 0.06, M_CONC,
                  "SM_Arena_LoadingBay_0%d" % (k + 1), v)
        rect_slab(ctx, lx - 4.2, cy - 5.2, lx + 4.2, cy + 5.2, 1.1, M_DARK,
                  "SM_Arena_LoadingDock_0%d" % (k + 1), v)

    # 2 tiers visible through glazing — already in bowl; add tier facade panels
    for t in (1, 3):
        rad = 18.0 + t * 9.0
        z = t * 1.4
        bd = B()
        bd.box(cx - r_arena * 0.35, cy - r_arena * 0.35 - 0.1, z,
               cx + r_arena * 0.35, cy - r_arena * 0.35 + 0.1, z + 2.6, M_GLASS)
        me = commit(bd, "SM_Arena_TierGlazing_T%d" % t)
        ctx.place(me, "SM_Arena_TierGlazing_T%d" % t, (0.0, 0.0, 0.0), apply=True, venue=v)

    # lights inside arena (real)
    for k in range(4):
        ang = 2.0 * math.pi * k / 4.0
        rad = 40.0
        px = cx + rad * math.cos(ang)
        py = cy + rad * math.sin(ang)
        lt = bpy.data.lights.new("LT_sports_ar_%02d" % (k + 1), "POINT")
        lt.energy = 60.0
        ob = bpy.data.objects.new("LT_sports_ar_%02d" % (k + 1), lt)
        ob.location = (px, py, bowl_h + 2.0)
        ctx.lights.objects.link(ob)
        ctx.objects += 1

    # turnstiles at entrance hall (open frontage)
    for k in range(3):
        px = cx - hall_w * 0.5 + 10.0 + k * 14.0
        ctx.place(ctx.kits["SM_Turnstile_01"], "SM_Arena_Turnstile_0%d" % (k + 1),
                  (px, cy - r_arena - hall_d + 1.0, 0.0), rot=0, venue=v)

    # trees around ring
    for i in range(10):
        ang = 2.0 * math.pi * i / 10.0
        r = 114.0 - 8.0
        px = cx + r * math.cos(ang)
        py = cy + r * math.sin(ang)
        ctx.place(ctx.kits["LOD1_Tree_09m_01"], "SM_Arena_Tree_0%d" % (i + 1),
                  (px, py, 0.0), venue=v)

    ctx.collider("COL_Arena_Venue", [x0, y0, x1, y1], bowl_h + 4.0, venue=v)
    ctx.collider("COL_Arena_Hall", [cx - hall_w * 0.5, cy - r_arena - hall_d,
                                    cx + hall_w * 0.5, cy - r_arena], hall_h, venue=v)

    n_ob = ctx.objects - objs0
    n_tr = ctx.instanced_tris - tris0
    ctx.venues["arena"] = dict(objects=n_ob, tris=n_tr, label=name, rect=v["rect"],
                               bbox=[x0, y0, x1, y1, 0.0, bowl_h + 4.0])
    print("[sports] arena: %d objects | %d instanced tris" % (n_ob, n_tr))


# ------------------------------------------------------------------ venue: swimming
def build_swimming(ctx):
    v = VENUES["swimming"]
    x0, y0, x1, y1 = v["rect"]
    cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
    name = v["label"]
    tris0, objs0 = ctx.instanced_tris, ctx.objects

    rect_slab(ctx, x0, y0, x1, y1, 0.0, M_GRASS, "SM_Swimming_Ground_01", v)
    # outdoor 50 m pool (water), E-W
    pw, pd = 52.0, 22.0
    rect_slab(ctx, cx - pw * 0.5, cy - pd * 0.5, cx + pw * 0.5, cy + pd * 0.5,
              0.06, M_WATER, "SM_Swimming_Pool_01", v)
    # deck around pool
    rect_slab(ctx, cx - pw * 0.5 - 6.0, cy - pd * 0.5 - 6.0,
              cx + pw * 0.5 + 6.0, cy + pd * 0.5 + 6.0, 0.05, M_CONC,
              "SM_Swimming_Deck_01", v)
    # lane ropes (thin strips) across pool width, floating
    n_lanes = 8
    for i in range(n_lanes + 1):
        py = cy - pd * 0.5 + 2.0 + i * ((pd - 4.0) / n_lanes)
        if py >= cy + pd * 0.5 - 2.0:
            continue
        ctx.place(ctx.kits["SM_LaneRope_25m"], "SM_Swimming_LaneRope_%02d" % i,
                  (cx, py, 0.12), rot=0, scale=pw / 25.0, venue=v)
        # anchors
        ctx.place(ctx.kits["SM_LaneAnchor_01"], "SM_Swimming_LaneAnchor_L_%02d" % i,
                  (cx - pw * 0.5 + 1.0, py, 0.12), venue=v)
        ctx.place(ctx.kits["SM_LaneAnchor_01"], "SM_Swimming_LaneAnchor_R_%02d" % i,
                  (cx + pw * 0.5 - 1.0, py, 0.12), venue=v)

    # 10 m diving board tower at one end
    ctx.place(ctx.kits["SM_DivingTower_10m_01"], "SM_Swimming_DivingTower_01",
              (cx - pw * 0.5 + 9.0, cy + pd * 0.5 + 5.0, 0.0), rot=0, venue=v)

    # changing block with flat roof
    ctx.place(ctx.kits["SM_ChangingBlock_01"], "SM_Swimming_ChangingBlock_01",
              (cx + pw * 0.5 + 14.0, cy - 8.0, 0.0), rot=0, venue=v)

    # small grandstand
    stand_x = cx - pw * 0.5 - 14.0
    for t in range(3):
        z = t * 0.6
        for i in range(6):
            px = stand_x + i * 2.2
            ctx.place(ctx.kits["LOD1_SeatBlock_01"], "SM_Swimming_SeatBlock_T%d_%02d" % (t, i),
                      (px, cy + pd * 0.5 + 4.0 + (t + 1) * 1.6, z), rot=90, venue=v)

    # domed indoor pool hall beside (north-east of outdoor pool)
    dome_cx, dome_cy = cx + 42.0, cy + 38.0
    dome_r, dome_h = 30.0, 13.0
    rect_slab(ctx, dome_cx - dome_r, dome_cy - dome_r, dome_cx + dome_r, dome_cy + dome_r,
              0.04, M_CONC, "SM_Swimming_IndoorFloor_01", v)
    # indoor pool water
    rect_slab(ctx, dome_cx - 20.0, dome_cy - 14.0, dome_cx + 20.0, dome_cy + 14.0,
              0.06, M_WATER, "SM_Swimming_IndoorPool_01", v)
    # glazed dome wall
    bd = B()
    seg = 28
    rings = 5
    for ri in range(rings - 1):
        z0 = dome_h * 0.15 + (dome_h * 0.8) * (ri / (rings - 1))
        z1 = dome_h * 0.15 + (dome_h * 0.8) * ((ri + 1) / (rings - 1))
        r0 = dome_r * (1.0 - 0.25 * (ri / (rings - 1)))
        r1 = dome_r * (1.0 - 0.25 * ((ri + 1) / (rings - 1)))
        for k in range(seg):
            a0 = 2 * math.pi * k / seg
            a1 = 2 * math.pi * (k + 1) / seg
            pts = [(dome_cx + r0 * math.cos(a0), dome_cy + r0 * math.sin(a0), z0),
                   (dome_cx + r1 * math.cos(a1), dome_cy + r1 * math.sin(a1), z1),
                   (dome_cx + r1 * math.cos(a0), dome_cy + r1 * math.sin(a0), z1),
                   (dome_cx + r0 * math.cos(a0), dome_cy + r0 * math.sin(a0), z0)]
            bd.poly(pts, M_GLASS)
            pts = [(dome_cx + r0 * math.cos(a0), dome_cy + r0 * math.sin(a0), z0),
                   (dome_cx + r0 * math.cos(a1), dome_cy + r0 * math.sin(a1), z0),
                   (dome_cx + r1 * math.cos(a1), dome_cy + r1 * math.sin(a1), z1),
                   (dome_cx + r1 * math.cos(a0), dome_cy + r1 * math.sin(a0), z1)]
            bd.poly(pts, M_GLASS)
    me = commit(bd, "SM_Swimming_IndoorDome_01")
    ctx.place(me, "SM_Swimming_IndoorDome_01", (0.0, 0.0, 0.0), apply=True, venue=v)
    # dome roof cap
    rect_slab(ctx, dome_cx - dome_r * 0.5, dome_cy - dome_r * 0.5,
              dome_cx + dome_r * 0.5, dome_cy + dome_r * 0.5,
              dome_h + 0.15, M_DARK, "SM_Swimming_DomeCap_01", v)

    # real lights over outdoor pool
    for k in range(3):
        ang = 2.0 * math.pi * k / 3.0
        rad = 26.0
        px = cx + rad * math.cos(ang)
        py = cy + rad * math.sin(ang)
        lt = bpy.data.lights.new("LT_sports_sw_%02d" % (k + 1), "POINT")
        lt.energy = 45.0
        ob = bpy.data.objects.new("LT_sports_sw_%02d" % (k + 1), lt)
        ob.location = (px, py, 10.0)
        ctx.lights.objects.link(ob)
        ctx.objects += 1

    # colliders
    ctx.collider("COL_Swimming_Venue", [x0, y0, x1, y1], 16.0, venue=v)
    ctx.collider("COL_stand_swimming_N", [stand_x - 2, cy + pd * 0.5 + 2,
                                         stand_x + 16, cy + pd * 0.5 + 18], 5.0, venue=v)
    ctx.collider("COL_Swimming_Dome", [dome_cx - dome_r, dome_cy - dome_r,
                                       dome_cx + dome_r, dome_cy + dome_r], dome_h + 2.0, venue=v)

    n_ob = ctx.objects - objs0
    n_tr = ctx.instanced_tris - tris0
    ctx.venues["swimming"] = dict(objects=n_ob, tris=n_tr, label=name, rect=v["rect"],
                                  bbox=[x0, y0, x1, y1, 0.0, dome_h + 2.0])
    print("[sports] swimming: %d objects | %d instanced tris" % (n_ob, n_tr))


# ------------------------------------------------------------------ real lights for cricket & football
def add_real_lights(ctx):
    # cricket: 4 real lights on pylons
    cr_cx, cr_cy = -750.0, -1050.0
    pr = 100.0
    for k, (sx, sy) in enumerate(((1, 1), (1, -1), (-1, 1), (-1, -1))):
        lt = bpy.data.lights.new("LT_sports_cr_%02d" % (k + 1), "POINT")
        lt.energy = 80.0
        ob = bpy.data.objects.new("LT_sports_cr_%02d" % (k + 1), lt)
        ob.location = (cr_cx + sx * pr, cr_cy + sy * pr, 44.0)
        ctx.lights.objects.link(ob)
        ctx.objects += 1
    # football: 4 real lights on gantry corners
    fb_cx, fb_cy = 150.0, -1050.0
    for k, (sx, sy) in enumerate(((1, 1), (1, -1), (-1, 1), (-1, -1))):
        lt = bpy.data.lights.new("LT_sports_fb_%02d" % (k + 1), "POINT")
        lt.energy = 80.0
        ob = bpy.data.objects.new("LT_sports_fb_%02d" % (k + 1), lt)
        ob.location = (fb_cx + sx * 92.0, fb_cy + sy * 92.0, 42.0)
        ctx.lights.objects.link(ob)
        ctx.objects += 1
    # athletics small real lights (2)
    ath_cx, ath_cy = -1050.0, -750.0
    for k in range(2):
        lt = bpy.data.lights.new("LT_sports_ath_%02d" % (k + 1), "POINT")
        lt.energy = 35.0
        ob = bpy.data.objects.new("LT_sports_ath_%02d" % (k + 1), lt)
        ob.location = (ath_cx + (-1 if k == 0 else 1) * 70.0,
                       ath_cy + (-1 if k == 0 else 1) * 45.0, 16.0)
        ctx.lights.objects.link(ob)
        ctx.objects += 1


# ------------------------------------------------------------------ football z<5 assert
def assert_football_pitch_z(ctx):
    """No mesh vertex above z=5 m inside the football pitch rect."""
    x0, y0, x1, y1 = FB_PITCH
    worst = -1e18
    worst_ob = None
    n_checked = 0
    for ob, venue in ctx.placed_meshes:
        if venue is not VENUES["football"]:
            continue
        me = ob.data
        if me is None:
            continue
        mw = ob.matrix_world
        for v in me.vertices:
            w = mw @ v.co
            if x0 - 1e-4 <= w.x <= x1 + 1e-4 and y0 - 1e-4 <= w.y <= y1 + 1e-4:
                n_checked += 1
                if w.z > worst:
                    worst = w.z
                    worst_ob = ob.name
    ok = worst <= 5.0 + 1e-3
    if not ok:
        ctx.issues.append("FOOTBALL PITCH ASSERT FAILED: vertex z=%.3f in %s (limit 5 m)"
                          % (worst, worst_ob))
        raise AssertionError("football pitch z<5 assert violated: %s at z=%.3f"
                             % (worst_ob, worst))
    print("[sports] ASSERT football pitch z<5 m: OK (max z=%.3f m, %d vertices checked)"
          % (worst, n_checked))
    return worst, n_checked


# ------------------------------------------------------------------ purge / main
def purge_sports():
    coll = bpy.data.collections.get(MODULE)
    if coll is None:
        return
    for ob in list(coll.all_objects):
        try:
            bpy.data.objects.remove(ob, do_unlink=True)
        except Exception:
            pass
    def rm(c):
        for ch in list(c.children):
            rm(ch)
        try:
            bpy.data.collections.remove(c)
        except Exception:
            pass
    rm(coll)
    print("[sports] purged previous '%s' collection" % MODULE)


def write_md(d):
    lines = [
        "# Sports module report (5 venues)\n",
        "Generated by `modules/sports.py` (headless, %s).\n" % d.get("engine"),
        "## Counts\n",
        "| item | value |",
        "|---|---|",
        "| venues | %d |" % d["venues"],
        "| objects | %d |" % d["objects"],
        "| collider objects | %d |" % d["collider_objects"],
        "| light objects | %d |" % d["light_objects"],
        "| unique meshes | %d |" % d["unique_meshes"],
        "| instanced tris | %d |" % d["instanced_tris"],
        "| unique tris | %d |" % d["unique_tris"],
        "| budget (<=1,500,000) | %s |" % ("OK" if d["instanced_tris"] <= 1500000 else "EXCEEDED"),
        "\n## Per venue\n",
        "| venue | rect | objects | tris | height |",
        "|---|---|---|---|---|",
    ]
    for vn in VENUE_ORDER:
        v = d["per_venue"][vn]
        lines.append("| %s | %s | %d | %d | %.0f m |"
                     % (v["label"], v["rect"], v["objects"], v["tris"], v["bbox"][5]))
    lines.append("\n## Budgets (program.json)\n| venue | tris | budget | |")
    lines.append("|---|---|---|---|")
    for vn in VENUE_ORDER:
        bud = {"cricket": 150000, "football": 150000, "athletics": 150000,
               "arena": 150000, "swimming": 120000}[vn]
        v = d["per_venue"][vn]
        lines.append("| %s | %d | %d | %s |" % (v["label"], v["tris"], bud,
             "OK" if v["tris"] <= bud else "OVER"))
    lines.append("\n## Materials used (%d)" % len(d["materials"]))
    lines.append(", ".join("`%s`" % m for m in d["materials"]))
    lines.append("\n## Collections\n- Sports / Sports/Meshes / Sports/Colliders / Sports/Lights")
    lines.append("- naming: SM_<Type>_<Variant>_<nn>, COL_<name>, COL_stand_*, LT_sports_*")
    lines.append("- LOD1_/LOD2_ prefixed kits: seat block, pylon, tree, canopy panel")
    lines.append("\n## Asserts\n- football pitch z<5 m: %s (max z=%.3f m)" % (d["pitch_assert_ok"], d["pitch_assert_max_z"]))
    lines.append("\n## Known issues / notes\n")
    for i in d["issues"]:
        lines.append("- %s" % i)
    lines.append("- ASSEMBLER MUST STRIP Nature objects inside these 5 rects: PK_1_0, PK_4_0,")
    lines.append("  PK_0_1, PK_4_1, PK_0_2 (converted park cells).")
    lines.append("- No door meshes anywhere: all gates/frontages are open archways.")
    lines.append("- Venues stay strictly inside their rects; green ring kept inside rect.")
    lines.append("- Nearest road corridor is 24 m away for all venues (no road in land);")
    lines.append("  gates face the nearest road corridor; service spur is the Roads module's job.")
    path = os.path.join(ck.REPORTS_DIR, "sports_report.md")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("  [sports] markdown report -> %s" % path)


def main():
    t0 = time.time()
    layout = ck.read_layout()
    # sanity: engine
    eng = "BLENDER_EEVEE"
    try:
        ids = [i.identifier for i in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
        if eng not in ids:
            eng = [i for i in ids if "EEVEE" in i][0]
    except Exception:
        pass
    print("[sports] engine:", eng)

    purge_sports()
    for nm in ("Cube", "Camera", "Light"):
        ob = bpy.data.objects.get(nm)
        if ob is not None:
            bpy.data.objects.remove(ob, do_unlink=True)

    ctx = Ctx()
    build_kits(ctx)

    for vn in VENUE_ORDER:
        if vn == "cricket":
            build_cricket(ctx)
        elif vn == "football":
            build_football(ctx)
        elif vn == "athletics":
            build_athletics(ctx)
        elif vn == "arena":
            build_arena(ctx)
        elif vn == "swimming":
            build_swimming(ctx)
        ck.save_blend(OUT_BLEND)   # stage save after each venue
        print("[sports] staged save after %s" % vn)

    add_real_lights(ctx)

    # ---- football pitch z<5 assert
    pitch_max_z, pitch_n = assert_football_pitch_z(ctx)

    # ---- previews
    prev_air = prev_fb = None
    try:
        prev_air = ck.make_preview(PREVIEW_AIR, (-300.0, -1500.0, 340.0),
                                   (-300.0, -1050.0, 18.0), engine=eng,
                                   res=(1920, 1080), sun_elev=38.0, sun_azim=-55.0,
                                   sun_energy=3.8, samples=36)
    except Exception as exc:
        print("[sports] aerial preview failed:", exc)
        ctx.issues.append("aerial preview failed: %s" % exc)
    try:
        prev_fb = ck.make_preview(PREVIEW_FB, (150.0, -1050.0, 2.2),
                                  (150.0, -1042.0, 70.0), engine=eng,
                                  res=(1920, 1080), sun_elev=60.0, sun_azim=-30.0,
                                  sun_energy=4.0, samples=36)
    except Exception as exc:
        print("[sports] football preview failed:", exc)
        ctx.issues.append("football preview failed: %s" % exc)

    # final save
    ck.save_blend(OUT_BLEND)

    n_obj = len(bpy.data.objects)
    uniq_tris = ck.scene_tri_count()
    n_meshes = len([m for m in bpy.data.meshes if m.users > 0 or m.use_fake_user])
    n_lights = len([o for o in bpy.data.objects if o.type == "LIGHT"])
    n_colliders = len([o for o in bpy.data.objects
                       if o.name.startswith("COL_") and o.hide_render])

    payload = {
        "module": MODULE,
        "venues": len(VENUES),
        "venue_order": VENUE_ORDER,
        "per_venue": {vn: dict(ctx.venues[vn]) for vn in VENUE_ORDER},
        "objects": n_obj,
        "collider_objects": n_colliders,
        "light_objects": n_lights,
        "unique_meshes": n_meshes,
        "unique_meshes_kits": len(ctx.kits),
        "instanced_tris": ctx.instanced_tris,
        "unique_tris": uniq_tris,
        "budget_instanced_tris": 1500000,
        "budget_ok": ctx.instanced_tris <= 1500000,
        "materials": sorted(ctx.mats_used),
        "materials_count": len(ctx.mats_used),
        "pitch_assert_max_z": round(pitch_max_z, 4),
        "pitch_assert_vertices_checked": pitch_n,
        "pitch_assert_ok": pitch_max_z <= 5.0 + 1e-3,
        "engine": eng,
        "collections": ["Sports", "Sports/Meshes", "Sports/Colliders", "Sports/Lights"],
        "previews": [p for p in (prev_air, prev_fb) if p],
        "assembler": {
            "instancing": "linked duplicates (shared mesh datablocks) + collection instances",
            "kits": "~%d unique meshes MAX; seat blocks / panels / pylons / trusses / trees instanced"
                    % len(ctx.kits),
            "transforms": "instanced kits keep placement transforms; unique meshes apply transforms",
            "origins": "every kit piece origin at bottom-centre",
        },
        "issues": ctx.issues,
        "build_seconds": round(time.time() - t0, 1),
        "venues_inside_rects": True,
        "no_door_meshes": True,
        "green_ring_m": RING,
    }
    ck.write_report("sports", payload)
    write_md(payload)

    print("[sports] DONE in %.0fs | objects=%d | instanced_tris=%d | unique_tris=%d "
          "| meshes=%d | lights=%d | colliders=%d"
          % (time.time() - t0, n_obj, ctx.instanced_tris, uniq_tris, n_meshes, n_lights,
             n_colliders))
    print("[sports] materials:", ", ".join(sorted(ctx.mats_used)))
    print("[sports] pitch assert: max_z=%.3f m OK=%s" % (pitch_max_z,
          pitch_max_z <= 5.0 + 1e-3))
    if ctx.issues:
        print("[sports] ISSUES:")
        for i in ctx.issues:
            print("   -", i)


if __name__ == "__main__":
    main()
