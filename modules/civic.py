#!/usr/bin/env python3
"""civic.py — SportsCivic module for the 3x3 km AAA city (civic + institutional).

Headless run:
    cd /home/abdulhadi/Work/city && blender -b -P modules/civic.py

Builds every program.json facility with owning_module == "SportsCivic" EXCEPT the
five stadiums (owned by modules/sports.py). Facilities follow placement.rect
exactly; mesh ORIGIN = bottom-centre of each facility rect; Z-up; metres.

Re-runnable: deletes the "Civic" collection first. Stage-saves out/civic.blend
every 20 facilities. Only the Assembler touches the master scene.
No doors are ever meshed: enterable tiers get wide open archways / missing-glass
frontage. Materials come ONLY from materials.blend (via citykit.append_material).
"""
from __future__ import annotations

import gc
import json
import math
import os
import sys
import time

ROOT = "/home/abdulhadi/Work/city"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT + "/modules")

import citykit as ck          # noqa: E402
import entertainment as ent   # noqa: E402
import bpy                    # noqa: E402
from mathutils import Matrix  # noqa: E402

from entertainment import (Builder, Face, wall_rects, make_mesh, Kit, new_obj,   # noqa
                           mesh_tris, build_road_grid, road_hits,
                           inside, overlap_check, dhash)

PROGRAM = os.path.join(ROOT, "reports", "program.json")
MODULE = "Civic"
FLOOR = 3.2
CURB = 0.15
WALL_T = 0.25
CLEAR = 2.4

STADIUMS = {"STADIUM_CRICKET", "STADIUM_FOOTBALL", "STADIUM_ATHLETICS",
            "ARENA_INDOOR", "COMPLEX_SWIMMING"}
ZONE_M = [300.0, 600.0, 1200.0, 1200.0]          # market district: never build
ZONE_CIRCUIT = [612.0, -1188.0, 1188.0, -12.0]   # only TRK_* may be inside
ZONE_LAKE = [-552.58, -1142.57, -335.1, -969.78]
ZONE_STADIUM = [
    [-864, -1164, -636, -936], [36, -1164, 264, -936],
    [-1164, -864, -936, -636], [-1164, -564, -936, -336],
    [12, -888, 288, -612]]
LANE_HW = {"highway": 17.0, "arterial": 12.0, "street": 6.0,
           "alley": 2.5, "interchange_ramp": 10.0}
ROT = {"S": 0, "E": 90, "N": 180, "W": 270}

# ------------------------------------------------------------------ materials
_AVAIL = set(ck._available_materials()) if ck.bpy is not None else set()


def _m(*cands):
    for c in cands:
        if c in _AVAIL:
            return c
    raise RuntimeError("civic: none of the candidate materials exist: %s" % (cands,))


M_STONE = _m("stone_grey")
M_CONC = _m("concrete")
M_CONC2 = _m("concrete_poured", "concrete")
M_ASPA = _m("asphalt", "road_asphalt_new")
M_GRASS = _m("nature_grass", "grass")
M_SAND = _m("sand")
M_DIRT = _m("nature_dirt", "dirt")
M_GRAVEL = _m("nature_gravel", "gravel")
M_PAVE = _m("sidewalk_paving", "paving_slab")
M_WALK = _m("sidewalk_concrete", "sidewalk_paving", "paving_slab")
M_CLASSIC = _m("facade_plaster_stone", "facade_plaster_bone", "stucco_grey")
M_BONE = _m("facade_plaster_bone")
M_MODE = _m("facade_concrete_slab", "facade_concrete", "concrete")
M_BRICK = _m("facade_brick_red")
M_BRICKB = _m("brick_brown")
M_PANEL = _m("facade_metal_panel")
M_CHAR = _m("metal_painted_charcoal", "metal_painted_dark")
M_DARK = _m("metal_painted_dark")
M_NAVY = _m("metal_painted_navy")
M_OXB = _m("metal_painted_oxblood", "kerb_red")
M_TEAL = _m("metal_painted_teal", "facade_plaster_teal")
M_MUST = _m("metal_painted_mustard", "facade_plaster_mustard")
M_GLASS = _m("glass_tinted_office", "glass_dark")
M_GLASSC = _m("glass_clear", "glass_dark")
M_GLASSH = _m("glass_frosted", "glass_dark")
M_ROOF = _m("roof_bitumen_flat", "roof_bitumen")
M_ROOFM = _m("roof_corrugated_metal", "roof_metal")
M_ROOFT = _m("roof_clay_tile", "roof_tile_red")
M_STEEL = _m("metal_steel")
M_RUST = _m("metal_rust", "metal_rusty")
M_WOODO = _m("wood_old")
M_WOODP = _m("wood_painted")
M_WPLAN = _m("wood_planks")
M_WPLANW = _m("wood_planks_weathered", "wood_planks", "wood_old")
M_NPINK = _m("neon_pink", "neon_magenta")
M_NBLUE = _m("neon_blue", "neon_teal")
M_NLIST = ["neon_magenta", "neon_violet", "neon_teal", "neon_mustard", "neon_oxblood"]
M_NLIST = [n for n in M_NLIST if n in _AVAIL] or [_m("neon_teal")]
M_EMITW = _m("emissive_warm", "light_warm")
M_EMITC = _m("emissive_cool", "light_cool")
M_SIGNW = _m("sign_white")
M_SIGNM = _m("sign_metal")
M_MARBLE = _m("int_marble")
M_FLCARP = _m("floor_carpet")
M_FLT = _m("int_tile_floor", "floor_tile")
M_FLW = _m("int_wood_floor", "floor_wood")
M_CEIL = _m("ceiling_paint")
M_WALLP = _m("int_wall_paint_bone", "wall_paint")
M_INTUP = _m("int_upholstery")
M_MARKW = _m("marking_white", "road_lane_paint_white")
M_MARKY = _m("marking_yellow", "road_lane_paint_yellow")
M_KERBW = _m("kerb_white")
M_LEAFD = _m("nature_leaf_dark", "leaves_dark")
M_LEAFL = _m("nature_leaf_light", "leaves_green", "nature_leaf_mid")
M_CHROME = _m("metal_chrome")
M_TRACK = _m("road_track_asphalt", "track_asphalt", "asphalt")
M_INTLAM = _m("int_laminate_counter")
M_MIRROR = _m("int_mirror")
M_CANVAS = _m("canvas_tarp")


# --------------------------------------------------------------- geometry help
def ring_pts(cx, cy, r, seg, a0=0.0, a1=2.0 * math.pi):
    return [(cx + r * math.cos(a0 + (a1 - a0) * k / seg),
             cy + r * math.sin(a0 + (a1 - a0) * k / seg)) for k in range(seg + 1)]


def loft_ring(bd, pts_lo, pts_hi, z_lo, z_hi, mat):
    """Quaded ring between two same-length point lists (outward normals if CCW)."""
    n = len(pts_lo) - 1
    for k in range(n):
        x0, y0 = pts_lo[k]
        x1, y1 = pts_lo[k + 1]
        u0, v0 = pts_hi[k]
        u1, v1 = pts_hi[k + 1]
        bd.poly([(x0, y0, z_lo), (x1, y1, z_lo), (u1, v1, z_hi), (u0, v0, z_hi)], mat)


def dome(bd, cx, cy, z0, r, rise, mat, seg=16, rings=5, bulge=0.0):
    """Hemispherical / onion cap (origin bottom-centre of the drum)."""
    prof = []
    for k in range(rings + 1):
        t = k / rings
        h = rise * t
        if bulge > 0.0:
            rr = r * (1.0 + bulge * math.sin(math.pi * min(t, 0.999))) * (1.0 - 0.18 * t)
        else:
            rr = r * math.sqrt(max(0.0, 1.0 - t * t)) if rise > 0 else 0.0
        prof.append((z0 + h, rr))
    for k in range(rings):
        z0a, ra = prof[k]
        z1a, rb = prof[k + 1]
        loft_ring(bd, ring_pts(cx, cy, ra, seg), ring_pts(cx, cy, rb, seg), z0a, z1a, mat)
    bd.poly([(cx, cy, z0 + rise)], mat)


def barrel(bd, x0, x1, y0, y1, z, rise, mat, seg=10, along="x"):
    """Half-cylinder vault; along='x' -> profile in the YZ plane."""
    n = seg
    if along == "x":
        w = y1 - y0
        cyv = (y0 + y1) * 0.5
        prof = [(cyv - (w * 0.5) * math.cos(math.pi * k / n),
                 z + rise * math.sin(math.pi * k / n)) for k in range(n + 1)]
        for k in range(n):
            ya, za = prof[k]
            yb, zb = prof[k + 1]
            bd.poly([(x0, ya, za), (x0, yb, zb), (x1, yb, zb), (x1, ya, za)], mat)
            bd.poly([(x0, ya, za), (x1, ya, za), (x1, yb, zb), (x0, yb, zb)], M_STEEL)
    else:
        w = x1 - x0
        cxv = (x0 + x1) * 0.5
        prof = [(cxv - (w * 0.5) * math.cos(math.pi * k / n),
                 z + rise * math.sin(math.pi * k / n)) for k in range(n + 1)]
        for k in range(n):
            xa, za = prof[k]
            xb, zb = prof[k + 1]
            bd.poly([(xa, y0, za), (xb, y0, zb), (xb, y1, zb), (xa, y1, zb)], mat)


def gable(bd, x0, x1, y0, y1, z0, ridge, mat, along="y", eaves=0.55):
    """Pitched roof: ridge along y (along='y') or x; overhang clipped to rect."""
    if along == "y":
        cxx = (x0 + x1) * 0.5
        bd.poly([(x0, y0, z0), (cxx, y0, ridge), (cxx, y1, ridge), (x0, y1, z0)], mat)
        bd.poly([(x1, y0, z0), (x1, y1, z0), (cxx, y1, ridge), (cxx, y0, ridge)], mat)
        bd.poly([(x1, y0, z0), (cxx, y0, ridge), (x0, y0, z0)], mat)
        bd.poly([(x1, y1, z0), (x0, y1, z0), (cxx, y1, ridge)], mat)
    else:
        cyy = (y0 + y1) * 0.5
        bd.poly([(x0, y0, z0), (x1, y0, z0), (x1, cyy, ridge), (x0, cyy, ridge)], mat)
        bd.poly([(x0, y1, z0), (x0, cyy, ridge), (x1, cyy, ridge), (x1, y1, z0)], mat)
        bd.poly([(x0, y0, z0), (x0, cyy, ridge), (x0, y1, z0)], mat)
        bd.poly([(x1, y0, z0), (x1, y1, z0), (x1, cyy, ridge)], mat)


def pyramid(bd, cx, cy, z0, hx, hy, h, mat):
    bd.poly([(cx - hx, cy - hy, z0), (cx + hx, cy - hy, z0), (cx + hx, cy + hy, z0),
             (cx - hx, cy + hy, z0)], mat)
    for (a, b) in (((-hx, -hy), (hx, -hy)), ((hx, -hy), (hx, hy)),
                   ((hx, hy), (-hx, hy)), ((-hx, hy), (-hx, -hy))):
        bd.poly([(cx + a[0], cy + a[1], z0), (cx + b[0], cy + b[1], z0), (cx, cy, z0 + h)], mat)


def pediment_front(bd, u0, u1, z0, z1, y0, y1, mat):
    """Classic triangular pediment spanning width u0..u1, depth y0..y1 (tri-prism)."""
    um = (u0 + u1) * 0.5
    bd.poly([(u0, y0, z0), (u1, y0, z0), (um, y0, z1)], mat)
    bd.poly([(u0, y1, z0), (um, y1, z1), (u1, y1, z0)], mat)
    bd.poly([(u0, y0, z0), (u1, y0, z0), (u1, y1, z0), (u0, y1, z0)], mat)
    bd.poly([(u0, y0, z0), (u0, y1, z0), (um, y1, z1), (um, y0, z1)], mat)
    bd.poly([(u1, y0, z0), (um, y0, z1), (um, y1, z1), (u1, y1, z0)], mat)


def steps_front(bd, u0, u1, y, n, mat, rise=0.16, tread=0.45):
    """Front steps descending toward -Y (origin at the top landing edge)."""
    for k in range(n):
        bd.box(u0, y - tread * (k + 1), 0.0, u1, y - tread * k, rise * (n - k), mat)


def wall_boxes(bd, hx, hy, top, mat):
    bd.box(-hx, -hy, 0.0, hx, hy, top, mat)


def fac_faces(bd, hx, hy):
    return dict(
        F=Face(bd, "y", -hy, -hy + WALL_T, -1, -hx, hx),
        B=Face(bd, "y", hy - WALL_T, hy, 1, -hx, hx),
        L=Face(bd, "x", -hx, -hx + WALL_T, -1, -hy, hy),
        R=Face(bd, "x", hx - WALL_T, hx, 1, -hy, hy))


def plinth(bd, hx, hy, mat=M_STONE, h=CURB):
    bd.box(-hx, -hy, 0.0, hx, hy, h, mat)


def cornice(bd, hx, hy, z, mat=M_STONE, t=0.35, h=0.55):
    bd.box(-hx - 0.3, -hy - 0.3, z, hx + 0.3, hy + 0.3, z + h, mat)


def parapet_ring(bd, hx, hy, z, mat, t=0.25, h=1.0, cap=True):
    bd.box(-hx, -hy, z, hx, -hy + t, z + h, mat)
    bd.box(-hx, hy - t, z, hx, hy, z + h, mat)
    bd.box(-hx, -hy + t, z, -hx + t, hy - t, z + h, mat)
    bd.box(hx - t, -hy + t, z, hx, hy - t, z + h, mat)
    if cap:
        c = 0.06
        bd.box(-hx - c, -hy - c, z + h, hx + c, -hy + t + c, z + h + 0.09, M_STONE)
        bd.box(-hx - c, hy - t - c, z + h, hx + c, hy + c, z + h + 0.09, M_STONE)
        bd.box(-hx - c, -hy + t + c, z + h, -hx + t + c, hy - t - c, z + h + 0.09, M_STONE)
        bd.box(hx - t - c, -hy + t + c, z + h, hx + c, hy - t - c, z + h + 0.09, M_STONE)


def roof_deck(bd, hx, hy, z, mat=M_ROOF):
    bd.box(-hx, -hy, z - 0.05, hx, hy, z + 0.04, mat)


def punched(face, z0, wall, sp=4.6, w=2.2, h=1.8, sill=1.0, glass=None, frame=None):
    """Row of punched windows on one face; openings left, glass proud of the sill."""
    glass = glass or M_GLASS
    frame = frame or M_CHAR
    L = face.length
    n = max(2, int((L - 2.0) / sp))
    step = L / n
    ops = []
    for i in range(n):
        u = face.u0 + step * (i + 0.5)
        ww = min(w, step - 0.7)
        if ww < 0.7:
            continue
        ops.append(dict(u0=u - ww * 0.5, u1=u + ww * 0.5,
                        z0=z0 + sill, z1=z0 + sill + h))
    face.wall(z0, z0 + FLOOR, ops, wall)
    for o in ops:
        face.rect(o["u0"], o["z0"], o["u1"], o["z1"], glass, 0.10, 0.17)
        face.rect(o["u0"] - 0.08, o["z0"], o["u0"] + 0.02, o["z1"], frame, -0.02, 0.05)
        face.rect(o["u1"] - 0.02, o["z0"], o["u1"] + 0.08, o["z1"], frame, -0.02, 0.05)
        face.rect(o["u0"] - 0.10, o["z0"] - 0.12, o["u1"] + 0.10, o["z0"], M_STONE, -0.06, 0.06)
    return len(ops)


def archway(face, o, wall, steps=4, glass=None):
    """Wide open archway: opening already cut by face.wall(ops); head + reveals."""
    wall = wall if isinstance(wall, str) else wall
    glass = glass or M_GLASSC
    w = o["u1"] - o["u0"]
    z0, z1 = o["z0"], o["z1"]
    face.rect(o["u0"], z0, o["u1"], z1, M_STONE, -0.03, 0.0)  # jamb trim back
    for k in range(steps):
        t = k / steps
        iz = z1 - (z1 - z0) * 0.0 - t * min(1.6, w * 0.28)
        iw = w * (1.0 - (k + 1) * 0.22)
        if iw <= 0.4:
            break
        um = (o["u0"] + o["u1"]) * 0.5
        face.rect(um - iw * 0.5, iz - 0.001, um + iw * 0.5, iz + 0.34, M_STONE, 0.02, 0.10)
    face.rect(o["u0"], z0, o["u1"], z1 - 0.05, glass, 0.05, 0.12)


def glass_curtain(face, z0, z1, glass, frame, mull=2.6, inset=0.08):
    """Full-height glazing with mullions between the wall openings."""
    o = dict(u0=face.u0 + 0.4, u1=face.u1 - 0.4, z0=z0, z1=z1)
    face.wall(z0, z1, [o], frame)
    face.rect(o["u0"], o["z0"], o["u1"], o["z1"], glass, inset, inset + 0.09)
    nu = max(1, int((o["u1"] - o["u0"]) / mull))
    for i in range(1, nu):
        u = o["u0"] + (o["u1"] - o["u0"]) * i / nu
        face.rect(u - 0.06, o["z0"], u + 0.06, o["z1"], frame, inset - 0.02, inset + 0.16)
    face.rect(o["u0"] - 0.1, o["z0"] - 0.1, o["u1"] + 0.1, o["z0"], M_STONE, -0.05, 0.05)
    face.rect(o["u0"] - 0.1, o["z1"], o["u1"] + 0.1, o["z1"] + 0.12, frame, -0.04, 0.06)


def ribbon_band(face, z0, wall, band_h=1.7, band_z=0.8, glass=None, frame=None):
    glass = glass or M_GLASS
    frame = frame or M_CHAR
    o = dict(u0=face.u0 + 0.8, u1=face.u1 - 0.8, z0=z0 + band_z, z1=z0 + band_z + band_h)
    face.wall(z0, z0 + FLOOR, [o], wall)
    face.rect(o["u0"], o["z0"], o["u1"], o["z1"], glass, 0.08, 0.16)
    nu = max(2, int((o["u1"] - o["u0"]) / 2.4))
    for i in range(1, nu):
        u = o["u0"] + (o["u1"] - o["u0"]) * i / nu
        face.rect(u - 0.06, o["z0"], u + 0.06, o["z1"], frame, 0.06, 0.13)
    face.rect(o["u0"] - 0.09, o["z0"] - 0.12, o["u1"] + 0.09, o["z0"], M_STONE, -0.05, 0.07)
    face.rect(o["u0"] - 0.09, o["z1"], o["u1"] + 0.09, o["z1"] + 0.09, frame, -0.02, 0.05)


def fake_facade(bd, hx, hy, z0, z1, wall, glass, cols, rows, dep=0.9):
    """Tier-3 facade-only: recessed fake-depth window grid on all four walls."""
    for side, f in (("F", None), ("B", None), ("L", None), ("R", None)):
        d = fac_faces(bd, hx, hy)[side]
        L = d.length
        step = L / cols
        fh = (z1 - z0) / rows
        for r in range(rows):
            zz0 = z0 + r * fh + fh * 0.22
            zz1 = z0 + r * fh + fh * 0.78
            ops = []
            for c in range(cols):
                u = d.u0 + step * (c + 0.5)
                ops.append(dict(u0=u - min(1.6, step * 0.36), u1=u + min(1.6, step * 0.36),
                                z0=zz0, z1=zz1))
            d.wall(zz0 - 0.05, zz1 + 0.05, ops, wall)
            for o in ops:
                d.rect(o["u0"], o["z0"], o["u1"], o["z1"], M_DARK, WALL_T, WALL_T + dep)
                d.rect(o["u0"], o["z0"], o["u1"], o["z1"], glass, WALL_T + 0.55, WALL_T + 0.62)


def recess_box(bd, hx, fy, by, fl_rise, ceil_z, floor, wall, glass=None):
    """Enterable shell: floor + ceiling + side walls behind an open frontage."""
    glass = glass or M_DARK
    bd.box(-hx, fy, fl_rise, hx, by, fl_rise + 0.04, floor)
    bd.box(-hx, fy, ceil_z - 0.12, hx, by, ceil_z, M_CEIL)
    wx = hx - 0.3
    bd.box(-hx, fy, fl_rise, -hx + 0.22, by, ceil_z, wall)
    bd.box(hx - 0.22, fy, fl_rise, hx, by, ceil_z, wall)
    bd.box(-hx, by - 0.22, fl_rise, hx, by, ceil_z, wall)


# ------------------------------------------------------------------ shared kits
def k_column(h=8.0, r=0.45):
    bd = Builder()
    bd.box(-r - 0.18, -r - 0.18, 0.0, r + 0.18, r + 0.18, 0.22, M_STONE)
    bd.cyl(0.0, 0.0, 0.22, h - 0.55, r, M_CLASSIC, seg=12)
    for (za, zb, s) in ((h - 0.55, h - 0.35, 1.12), (h - 0.35, h - 0.12, 1.3),
                        (h - 0.12, h, 0.9)):
        bd.box(-r * s, -r * s, za, r * s, r * s, zb, M_CLASSIC)
    return bd


def k_desk():
    bd = Builder()
    bd.box(-1.1, -0.38, 0.0, 1.1, 0.38, 0.68, M_WOODP)
    bd.box(-1.16, -0.42, 0.68, 1.16, 0.42, 0.74, M_INTLAM)
    bd.box(-1.05, -0.3, 0.1, 1.05, 0.3, 0.62, M_DARK)
    return bd


def k_bench(w=1.8):
    bd = Builder()
    bd.box(-w * 0.5, -0.22, 0.4, w * 0.5, 0.22, 0.46, M_WOODO)
    for sx in (-w * 0.5 + 0.12, w * 0.5 - 0.12):
        bd.box(sx - 0.05, -0.18, 0.0, sx + 0.05, 0.18, 0.4, M_STEEL)
    bd.box(-w * 0.5, 0.12, 0.46, w * 0.5, 0.2, 0.86, M_WOODO)
    return bd


def k_shelf():
    bd = Builder()
    bd.box(-0.9, -0.22, 0.0, 0.9, 0.22, 2.0, M_WPLAN)
    for zz in (0.4, 0.9, 1.4):
        for i in range(5):
            x = -0.78 + i * 0.36
            bd.box(x, -0.16, zz, x + 0.26, 0.16, zz + 0.34, M_CHAR)
    return bd


def k_planter():
    bd = Builder()
    bd.box(-0.8, -0.8, 0.0, 0.8, 0.8, 0.55, M_STONE)
    bd.box(-0.68, -0.68, 0.55, 0.68, 0.68, 0.62, M_DARK)
    bd.cyl(0.0, 0.0, 0.62, 1.35, 0.62, M_LEAFD, seg=8)
    bd.cyl(0.0, 0.0, 1.2, 1.75, 0.4, M_LEAFL, seg=6)
    return bd


def k_bollard():
    bd = Builder()
    bd.cyl(0.0, 0.0, 0.0, 0.9, 0.11, M_STEEL, seg=8)
    bd.cyl(0.0, 0.0, 0.9, 0.98, 0.13, M_CHAR, seg=8)
    return bd


def k_mast(h=18.0):
    bd = Builder()
    s = 0.9
    for sx in (-s, s):
        for sy in (-s, s):
            bd.box(sx - 0.05, sy - 0.05, 0.0, sx + 0.05, sy + 0.05, h, M_STEEL)
    for k in range(6):
        z = h * k / 6.0
        bd.box(-s, -s, z, s, -s + 0.09, z + 0.07, M_STEEL)
        bd.box(-s, s - 0.09, z, s, s, z + 0.07, M_STEEL)
        bd.box(-s + 0.09, -s, z, s - 0.09, -s + 0.09, z + 0.07, M_STEEL)
        bd.box(-s + 0.09, s - 0.09, z, s - 0.09, s, z + 0.07, M_STEEL)
    bd.box(-0.09, -0.09, h, 0.09, 0.09, h + 2.2, M_STEEL)
    bd.box(-0.22, -0.06, h + 2.2, 0.22, 0.06, h + 2.35, M_EMITC)
    return bd


def k_flag(h=12.0):
    bd = Builder()
    bd.cyl(0.0, 0.0, 0.0, h, 0.08, M_CHROME, seg=8)
    bd.box(-0.2, -0.02, 0.0, 0.2, 0.3, 0.35, M_CONC)
    bd.box(0.0, 0.04, h * 0.72, 0.9, 0.07, h * 0.72 + 0.62, M_NAVY)
    return bd


def k_goal():
    bd = Builder()
    for sx in (-3.6, 3.6):
        bd.box(sx - 0.07, -0.07, 0.0, sx + 0.07, 0.07, 2.44, M_SIGNW)
        bd.box(sx - 0.05, 1.4, 0.0, sx + 0.05, 1.5, 0.3, M_SIGNW)
    bd.box(-3.66, -0.07, 2.44, 3.66, 0.07, 2.52, M_SIGNW)
    bd.box(-3.6, 0.0, 0.4, 3.6, 0.1, 0.48, M_SIGNW)
    bd.box(-3.6, 1.3, 0.35, 3.6, 1.4, 0.45, M_SIGNW)
    return bd


def k_flood():
    bd = Builder()
    bd.box(-0.14, -0.14, 0.0, 0.14, 0.14, 14.0, M_STEEL)
    bd.box(-0.9, -0.35, 13.6, 0.9, 0.25, 14.4, M_CHAR)
    bd.box(-0.8, -0.42, 13.75, 0.8, -0.3, 14.25, M_EMITC)
    return bd


def k_lamppost():
    bd = Builder()
    bd.cyl(0.0, 0.0, 0.0, 5.4, 0.09, M_CHAR, seg=8)
    bd.cyl(0.0, 0.0, 0.0, 0.25, 0.16, M_STONE, seg=8)
    bd.box(-0.06, -1.1, 5.4, 0.06, 0.0, 5.7, M_CHAR)
    bd.box(-0.14, -1.16, 5.32, 0.14, -0.9, 5.44, M_EMITW)
    return bd


def k_cab():
    bd = Builder()
    bd.box(-0.42, -0.3, 0.0, 0.42, 0.3, 1.85, M_CHAR)
    bd.box(-0.4, -0.34, 0.55, 0.4, -0.2, 1.05, M_EMITC)
    bd.box(-0.32, -0.34, 1.2, 0.32, -0.05, 1.6, M_EMITW)
    bd.box(-0.38, -0.32, 0.62, 0.38, -0.26, 0.7, M_STEEL)
    return bd


# --------------------------------------------------------------------- context
def nearest_side(rect, segs):
    x0, y0, x1, y1 = rect
    cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
    best, bside = 1e18, "S"
    for (ax, ay, bx, by, r) in segs:
        vx, vy = bx - ax, by - ay
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((cx - ax) * vx + (cy - ay) * vy) / L2))
        dx, dy = ax + vx * t - cx, ay + vy * t - cy
        d = math.hypot(dx, dy) - r
        if d < best:
            best, bside = d, ("E" if abs(dx) > abs(dy) and dx > 0 else
                              "W" if abs(dx) > abs(dy) else
                              "N" if dy > 0 else "S")
    return bside


class Fac(object):
    """One program facility (rect/heights/derocumented placement from program.json)."""

    def __init__(self, pf, segs):
        self.pf = pf
        self.id = pf["id"]
        self.label = pf["label"]
        self.rect = [float(v) for v in pf["placement"]["rect"]]
        self.floors = int(pf["placement"].get("floors") or 1)
        self.hm = float(pf["placement"].get("height_m") or 0.0)
        self.tier = int(pf.get("interior_tier") or 3)
        self.budget = int(pf.get("tri_budget") or 40000)
        self.bclass = pf.get("budget_class", "regular")
        self.enterable = bool(pf.get("enterable"))
        self.cx = (self.rect[0] + self.rect[2]) * 0.5
        self.cy = (self.rect[1] + self.rect[3]) * 0.5
        self.hx = (self.rect[2] - self.rect[0]) * 0.5
        self.hy = (self.rect[3] - self.rect[1]) * 0.5
        self.top = self.floors * FLOOR if self.floors >= 1 else 0.0
        self.top = max(self.top, self.hm)
        self.rng_kind = None
        self.tris = 0
        self.nobj = 0
        self.notes = []
        self.over = False
        self.ok = True
        self.side = nearest_side(self.rect, segs)
        self.rot = ROT.get(self.side, 0)


class Ctx(object):
    def __init__(self):
        self.root = ck.ensure_collection(MODULE)
        self.meshes = ck.ensure_collection("Meshes", parent=self.root)
        if self.root.name == self.meshes.name:
            self.meshes = self.root
        self.colliders = ck.ensure_collection("Colliders", parent=self.root)
        self.lights = ck.ensure_collection("Lights", parent=self.root)
        self.shell = Kit("SM_Civic")
        self.inter = Kit("INT")
        self.prop = Kit("SM_Prop")
        self.kit = Kit("KIT")
        self.coll = Kit("COL")
        self.counts = {}
        self.placed = 0
        self.props = 0
        self.lights_n = 0
        self.tris = 0
        self.collider_tris = 0
        self.colliders_n = 0
        self.built = {}
        self.bboxes = []
        self.viol = []
        self.mat_used = set()
        self.road = build_road_grid(ck.read_layout())
        self.segments = self.road[2]

    def uniq(self, prefix):
        n = self.counts.get(prefix, 0) + 1
        self.counts[prefix] = n
        return "%s_%03d" % (prefix, n)

    def note(self, f, msg):
        f.notes.append(msg)
        self.viol.append((f.id, msg))

    def collect_mats(self, me):
        for m in me.materials:
            if m is not None:
                self.mat_used.add(m.name)


def put(ctx, key, fn, name, cx, cy, rot, xl, yl, z, coll=None, kit=None):
    """Instance a shared kit mesh at a local offset (xl,yl) rotated about the facility."""
    if kit is None:
        kit = ctx.prop
    int_rot = int(rot) % 360
    ck_ = (key, int_rot)
    if ck_ in kit.cache:
        mesh = kit.cache[ck_]
    else:
        raw = fn()
        mesh = raw if isinstance(raw, bpy.types.Mesh) else make_mesh("KIT_tmp", raw)
        mesh = kit.get(key, int_rot, lambda: mesh)
    a = math.radians(int_rot)
    c, s = math.cos(a), math.sin(a)
    px, py = cx + xl * c - yl * s, cy + xl * s + yl * c
    ob = new_obj(name, mesh, (px, py, z), ctx.meshes if coll is None else coll)
    ctx.placed += 1
    ctx.props += 1
    cur = getattr(ctx, "cur", None)
    if cur is not None:
        cur.tris += mesh_tris(mesh)
        cur.nobj += 1
    ctx.tris += mesh_tris(mesh)
    ctx.collect_mats(mesh)
    return ob


def emit(ctx, f, bd, name, coll=None, rot=0):
    """Finish a builder into a mesh (facility rotation baked), place at rect centre."""
    me = make_mesh(name, bd)
    if rot % 360:
        me.transform(Matrix.Rotation(math.radians(rot % 360), 4, "Z"))
    ob = new_obj(name, me, (f.cx, f.cy, 0.0), ctx.meshes if coll is None else coll)
    ctx.placed += 1
    f.nobj += 1
    f.tris += mesh_tris(me)
    ctx.collect_mats(me)
    return ob


def add_light(ctx, loc, name=None, energy=60.0, radius=5.0, color=(1.0, 0.92, 0.82)):
    ctx.lights_n += 1
    nm = name or "LT_civic_%03d" % ctx.lights_n
    lt = bpy.data.lights.new(nm, type="POINT")
    lt.energy = energy
    lt.shadow_soft_size = radius
    lt.color = color
    ob = bpy.data.objects.new(nm, lt)
    ob.location = (float(loc[0]), float(loc[1]), float(loc[2]))
    ctx.lights.objects.link(ob)
    ctx.placed += 1
    ob.hide_render = False
    return ob


def collider(ctx, f, h=None, inset=0.15):
    h = h if h is not None else f.top + 0.6
    hx = max(1.0, f.hx - inset)
    hy = max(1.0, f.hy - inset)

    def fn():
        bd = Builder()
        bd.box(-hx, -hy, 0.0, hx, hy, h, M_CONC)
        return bd
    key = ("col", round(hx, 2), round(hy, 2), round(h, 2))
    mesh = ctx.coll.get(key, 0, lambda: make_mesh("COL_tmp", fn()))
    ob = new_obj("COL_%s" % f.id, mesh, (f.cx, f.cy, 0.0), ctx.colliders)
    ob.hide_render = True
    ctx.colliders_n += 1
    ctx.collider_tris += mesh_tris(mesh)


def forecourt(bd, hx, hy, mat, h=0.06, inset=0.0):
    bd.box(-hx - inset, -hy - inset, 0.0, hx + inset, hy + inset, h, mat)


# ================================================================ builders
def b_classical(ctx, f, kind="hall"):
    """CITY_HALL (tower cupola) / COURTHOUSE (two wings) / MUSEUM (colonnade ring)."""
    hx, hy, top = f.hx, f.hy, f.top
    fl = max(2, f.floors)
    bd = Builder()
    forecourt(bd, hx, hy, M_PAVE)
    plinth(bd, hx, hy, M_STONE, 0.3)
    mass_hx, mass_hy = hx, hy
    port = 4 if kind == "museum" else 4.5
    col_h = 8.0
    wall = M_CLASSIC

    # main mass: ground floor colonnade-free wall, upper punched floors
    faces = fac_faces(bd, mass_hx, mass_hy)
    for fkey in ("F", "B", "L", "R"):
        fc = faces[fkey]
        ground_ops = []
        if fkey == "F":
            n_gate = 3 if kind != "courthouse" else 4
            gw = 3.6
            um = 0.0
            for i in range(n_gate):
                u = (i - (n_gate - 1) / 2.0) * (gw + 4.4)
                ground_ops.append(dict(u0=u - gw * 0.5, u1=u + gw * 0.5, z0=CURB, z1=col_h))
        if fkey == "F" and kind == "museum":
            ground_ops = [dict(u0=-4.5, u1=4.5, z0=CURB, z1=col_h)]
        fc.wall(CURB, col_h, ground_ops, wall)
        for o in ground_ops:
            archway(fc, o, wall)
        for z0 in range(1, fl):
            zz = col_h + (z0) * FLOOR
            if zz + FLOOR <= top:
                punched(fc, zz, wall)
    roof_deck(bd, hx, hy, top)
    parapet_ring(bd, hx, hy, top, wall)
    cornice(bd, hx, hy, col_h + 0.35, M_STONE)

    # portico: raised podium front strip + columns + pediment
    podium = 0.6
    bd.box(-hx, -hy - 3.4, 0.0, hx, -hy + port, podium, M_STONE)
    n = 6 if kind != "courthouse" else 8
    span = 2 * min(hx, 26.0) - 4.0
    for i in range(n):
        u = -span * 0.5 + span * i / max(1, n - 1) if n > 1 else 0.0
        put(ctx, ("col", col_h), lambda: k_column(col_h), "KIT_Column_%02d" % (i + 1),
            f.cx, f.cy, f.rot, u, -hy + port - 1.4, podium, kit=ctx.kit)
    bd.box(-span * 0.5 - 1.4, -hy + port - 3.2, podium + col_h,
           span * 0.5 + 1.4, -hy + port, podium + col_h + 1.1, M_STONE)
    pediment_front(bd, -span * 0.5 - 1.6, span * 0.5 + 1.6, podium + col_h,
                   podium + col_h + 3.6, -hy - 3.4, -hy + port, M_CLASSIC)
    steps_front(bd, span * 0.5 + 1.6, span * 0.5 + 3.6, -hy - 3.4, 3, M_STONE)

    if kind == "hall":
        # civic clock tower + cupola on the mass
        bd.box(-5.0, -5.0, top, 5.0, 5.0, top + 5.6, wall)
        for i, sx in enumerate((-4.6, 4.6)):
            bd.box(sx - 1.1, sx * 0.5 - 1.4, top + 0.8, sx + 1.1, sx * 0.5 + 1.4, top + 4.6,
                   M_GLASS)
        bd.box(-5.6, -5.6, top + 5.6, 5.6, 5.6, top + 6.2, M_STONE)
        bd.cyl(0.0, 0.0, top + 6.2, top + 7.6, 3.6, M_CLASSIC, seg=12)
        dome(bd, 0.0, 0.0, top + 7.6, 3.6, 1.9, M_CLASSIC, seg=12)
        bd.box(-0.07, -0.07, top + 9.5, 0.07, 0.07, top + 11.0, M_STEEL)
        bd.box(-0.5, -0.06, top + 9.2, 0.5, 0.06, top + 9.35, M_STEEL)
        put(ctx, ("pbox",), lambda: k_planter(), "KIT_RoofPlanter_01",
            f.cx, f.cy, f.rot, hx - 4.0, hy - 4.0, top + 0.05, kit=ctx.kit)
    if kind == "courthouse":
        # wide side wings with colonnade strips + central steps
        for sx in (-1.0, 1.0):
            bd.box(sx * hx, -hy, 0.0, sx * (hx + 0.0), hy, 0.0, wall)
        bd.box(-2.4, -hy - 6.2, 0.0, 2.4, -hy, 2.8, wall)
    if kind == "museum":
        dome(bd, 0.0, 8.0, top, 15.0, 7.0, M_CLASSIC, seg=20, rings=6)
        bd.cyl(0.0, 8.0, top, 16.5, 15.6, M_CLASSIC, seg=20)
        put(ctx, ("pbox",), lambda: k_planter(), "KIT_RoofPlanter_01",
            f.cx, f.cy, f.rot, hx - 5.0, 6.0, top + 0.05, kit=ctx.kit)

    # interiors (tier 1): furnished lobby strip behind the portico
    if f.tier <= 2 and f.enterable:
        ibd = Builder()
        fy = -hy + port + 0.2
        ry = fy + 12.0
        inward = max(3.0, hx - 6.0)
        recess = 16.0 if kind != "museum" else 10.0
        ibd.box(-recess, fy, CURB, recess, ry, CURB + 0.04, M_MARBLE)
        ibd.box(-recess, fy, 3.1, recess, ry, 3.2, M_CEIL)
        for sx in (-recess, recess - 0.25):
            ibd.box(sx, fy, CURB, sx + 0.25, ry, 3.2, M_WALLP)
        ibd.box(-recess, ry - 0.25, CURB, recess, ry, 3.2, M_WALLP)
        ibd.box(-1.5, ry, CURB, 1.5, ry - 0.25, 3.2, M_STONE)
        put(ctx, ("desk",), lambda: k_desk(), "KIT_Desk_01",
            f.cx, f.cy, f.rot, -recess + 2.6, ry - 2.0, 0.0, kit=ctx.kit)
        for i in range(3):
            put(ctx, ("bench",), lambda: k_bench(), "KIT_Bench_%02d" % (i + 1),
                f.cx, f.cy, f.rot, -6.0 + i * 6.0, fy + 3.2, 0.0, kit=ctx.kit)
        put(ctx, ("shelf",), lambda: k_shelf(), "KIT_Shelf_01",
            f.cx, f.cy, f.rot, recess - 1.6, ry - 2.2, 0.0, kit=ctx.kit)
        put(ctx, ("plan",), lambda: k_planter(), "KIT_PlanterIn_01",
            f.cx, f.cy, f.rot, recess - 2.0, fy + 2.0, 0.0, kit=ctx.kit)
        emit(ctx, f, ibd, "INT_%s_Lobby" % _cap(f.id), rot=f.rot)
    if f.tier <= 2 and f.enterable:
        a = math.radians(f.rot)
        lx = -6.0
        ly = -hy + port + 6.0
        px = f.cx + lx * math.cos(a) - ly * math.sin(a)
        py = f.cy + lx * math.sin(a) + ly * math.cos(a)
        add_light(ctx, (px, py, 2.6), energy=80.0, radius=6.0)
    collider(ctx, f)
    if f.tris > f.budget:
        ctx.note(f, "tri budget over: %d > %d" % (f.tris, f.budget))
    return bd


def _cap(fid):
    return "".join(w.capitalize() for w in fid.lower().split("_"))


def b_planetarium(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_ASPA)
    plinth(bd, hx, hy, M_STONE, 0.3)
    wall = M_MODE
    # entrance box (front third) with full glass curtain
    ey0 = -hy + 2.0
    ey1 = ey0 + 34.0
    bd.box(-28.0, ey0, CURB, 28.0, ey1, top, wall)
    fc = Face(bd, "y", ey0, ey0 + WALL_T, -1, -28.0, 28.0)
    glass_curtain(fc, CURB, top - 1.2, M_GLASSC, M_CHAR)
    faces = dict(B=Face(bd, "y", ey1 - WALL_T, ey1, 1, -28.0, 28.0),
                 L=Face(bd, "x", -28.0, -28.0 + WALL_T, -1, ey0, ey1),
                 R=Face(bd, "x", 28.0 - WALL_T, 28.0, 1, ey0, ey1))
    faces["B"].wall(top - FLOOR, top, [], wall)
    faces["L"].wall(top - FLOOR, top, [], M_GLASS)
    faces["R"].wall(top - FLOOR, top, [], M_GLASS)
    roof_deck(bd, 28.0, 16.0, top, M_ROOF)
    parapet_ring(bd, 28.0, 16.0, top, wall)
    # science centre slab (rear left)
    bd.box(-hx + 2.0, ey1, CURB, -28.0, hy - 2.0, top, wall)
    lfc = Face(bd, "x", -hx + 2.0, -hx + 2.0 + WALL_T, -1, ey1, hy - 2.0)
    for ffi in range(max(1, f.floors)):
        ribbon_band(lfc, ffi * FLOOR, wall)
    wx0, wx1 = -hx + 2.0, -28.0
    wy0, wy1 = ey1, hy - 2.0
    bd.box(wx0, wy0, top - 0.05, wx1, wy1, top + 0.04, M_ROOF)
    bd.box(wx0, wy0, top, wx1, wy0 + 0.25, top + 0.9, wall)
    bd.box(wx0, wy1 - 0.25, top, wx1, wy1, top + 0.9, wall)
    bd.box(wx0, wy0, top, wx0 + 0.25, wy1, top + 0.9, wall)
    bd.box(wx1 - 0.25, wy0, top, wx1, wy1, top + 0.9, wall)
    # planetarium drum + dome (rear right)
    dcx = 34.0
    dcy = (ey1 + hy - 2.0) * 0.5
    loft_ring(bd, ring_pts(dcx, dcy, 26.6, 24), ring_pts(dcx, dcy, 26.0, 24), 0.0, 0.3, M_STONE)
    bd.cyl(dcx, dcy, 0.3, 13.0, 26.0, M_MODE, seg=24)
    for k in range(3):
        a = 2.0 * math.pi * k / 3.0
        bd.box(dcx - 1.6 + 2.6 * math.cos(a) - 0.5, dcy + 2.6 * math.sin(a) - 0.5,
               1.2, dcx - 1.6 + 2.6 * math.cos(a) + 0.5, dcy + 2.6 * math.sin(a) + 0.5,
               9.6, M_GLASS)
    bd.box(dcx - 26.4, dcy - 26.4, 13.0, dcx + 26.4, dcy + 26.4, 13.5, M_STEEL)
    dome(bd, dcx, dcy, 13.5, 26.0, 12.0, M_MODE, seg=24, rings=6)
    bd.box(dcx - 0.12, dcy - 0.12, 25.5, dcx + 0.12, dcy + 0.12, 27.4, M_STEEL)
    bd.box(dcx - 1.0, dcy - 0.08, 26.6, dcx + 1.0, dcy + 0.08, 26.95, M_EMITC)
    # entrance canopy + planet balls lawn
    put(ctx, ("can", 12.0), lambda: ent.p_canopy(12.0), "KIT_Canopy_01",
        f.cx, f.cy, f.rot, 0.0, ey0, 3.0, kit=ctx.kit)
    for (px, py, rr, mm) in ((46.0, -18.0, 3.2, M_TEAL), (46.0, 0.0, 2.2, M_MUST),
                             (46.0, 16.0, 4.4, M_NAVY), (46.0, 34.0, 2.8, M_CHROME)):
        bd.cyl(px, py, 0.2, 3.0, rr, mm, seg=14)
        pyramid(bd, px, py, 2.0, 0.35, 0.35, 1.1, M_STEEL)
        bd.box(px - 1.0, py - 1.0, 0.0, px + 1.0, py + 1.0, 0.2, M_CONC)
    if f.tier <= 2 and f.enterable:
        ibd = Builder()
        ibd.box(-26.0, ey0 + 0.5, CURB, 26.0, ey0 + 12.0, CURB + 0.04, M_FLCARP)
        ibd.box(-26.0, ey0 + 12.0, CURB, 26.0, ey0 + 12.3, 3.0, M_WALLP)
        put(ctx, ("desk",), lambda: k_desk(), "KIT_Desk_01",
            f.cx, f.cy, f.rot, -10.0, ey0 + 3.0, 0.0, kit=ctx.kit)
        for i in range(4):
            put(ctx, ("bench",), lambda: k_bench(), "KIT_Bench_%02d" % (i + 1),
                f.cx, f.cy, f.rot, -15.0 + i * 10.0, ey0 + 6.0, 0.0, kit=ctx.kit)
        emit(ctx, f, ibd, "INT_%s_Foyer" % _cap(f.id), rot=f.rot)
        a = math.radians(f.rot)
        add_light(ctx, (f.cx - 5.0 * math.sin(a), f.cy - 5.0 * math.cos(a), 2.6),
                  energy=90.0, radius=7.0)
    collider(ctx, f)
    if f.tris > f.budget:
        ctx.note(f, "tri budget over: %d > %d" % (f.tris, f.budget))
    return bd


def _tier1_lobby(ctx, f, u0, u1, fy, ry, name_suffix="Lobby", floor=None,
                 desks=None, benches=3, shelfs=0, mezz=False):
    floor = floor or M_MARBLE
    ibd = Builder()
    ibd.box(u0, fy, CURB, u1, ry, CURB + 0.04, floor)
    ibd.box(u0, fy, 3.1, u1, ry, 3.2, M_CEIL)
    for sx in (u0, u1 - 0.25):
        ibd.box(sx, fy, CURB, sx + 0.25, ry, 3.2, M_WALLP)
    ibd.box(u0, ry - 0.25, CURB, u1, ry, 3.2, M_WALLP)
    ibd.box(-1.5 if u0 < 0 < u1 else 0.0, ry, CURB,
            1.5 if u0 < 0 < u1 else 0.0, ry - 0.25, 3.2, M_STONE)
    n = 0
    for dx in (desks or [-3.0]):
        n += 1
        put(ctx, ("desk",), lambda: k_desk(), "KIT_Desk_%02d" % n,
            f.cx, f.cy, f.rot, dx, ry - 1.8, 0.0, kit=ctx.kit)
    for i in range(benches):
        put(ctx, ("bench",), lambda: k_bench(), "KIT_Bench_%02d" % (i + 1),
            f.cx, f.cy, f.rot, u0 + 3.0 + i * ((u1 - u0 - 6.0) / max(1, benches - 1)),
            fy + 2.6, 0.0, kit=ctx.kit)
    for i in range(shelfs):
        put(ctx, ("shelf",), lambda: k_shelf(), "KIT_Shelf_%02d" % (i + 1),
            f.cx, f.cy, f.rot, u0 + 1.6, ry - 2.6 - i * 2.2, 0.0, kit=ctx.kit)
    emit(ctx, f, ibd, "INT_%s_%s" % (_cap(f.id), name_suffix), rot=f.rot)
    a = math.radians(f.rot)
    px, py = f.cx + 0.5 * math.sin(-a), f.cy + 0.5 * math.cos(-a)
    add_light(ctx, (f.cx, f.cy, 2.6), energy=90.0, radius=8.0)


def _furnish_light(ctx, f, z=2.6):
    add_light(ctx, (f.cx, f.cy, z), energy=80.0, radius=7.0)


def b_theatre(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_PAVE)
    plinth(bd, hx, hy, M_STONE, 0.3)
    wall = M_BONE
    faces = fac_faces(bd, hx, hy)
    # ground: open lobby archway triple + ticket booth
    ops = [dict(u0=-9.0, u1=9.0, z0=CURB, z1=3.6),
           dict(u0=-hx + 3.0, u1=-hx + 7.0, z0=CURB, z1=3.0),
           dict(u0=hx - 7.0, u1=hx - 3.0, z0=CURB, z1=3.0)]
    faces["F"].wall(CURB, FLOOR, ops, wall)
    for o in ops[:2]:
        archway(faces["F"], o, wall)
    bd.box(hx - 6.0, -hy + 0.4, CURB, hx - 4.0, -hy + 1.8, 1.2, M_WOODP)
    for z0 in range(1, f.floors):
        zz = FLOOR + (z0 - 1) * FLOOR
        punched(faces["F"], zz, wall, sp=5.5, w=2.6, h=2.0)
        ribbon_band(faces["L"], zz, M_BRICKB, band_h=1.5)
        ribbon_band(faces["R"], zz, M_BRICKB, band_h=1.5)
        faces["B"].wall(zz, zz + FLOOR, [], wall)
    roof_deck(bd, hx, hy, top)
    parapet_ring(bd, hx, hy, top, wall)
    # marquee + vertical neon tower + fascia
    put(ctx, ("marq", 24.0), lambda: ent.p_marquee(24.0), "KIT_Marquee_01",
        f.cx, f.cy, f.rot, 0.0, -hy, 3.6, kit=ctx.kit)
    for sx in (-12.5, 12.5):
        put(ctx, ("poster",), lambda: ent.p_poster(), "KIT_Poster_%d" % (1 if sx < 0 else 2),
            f.cx, f.cy, f.rot, sx, -hy, 2.45, kit=ctx.kit)
    put(ctx, ("nv", 12.5), lambda: ent.p_neonvert(9.5, M_NPINK), "KIT_NeonRun_01",
        f.cx, f.cy, f.rot, 26.0, -hy + 0.1, 1.0, kit=ctx.kit)
    put(ctx, ("fas", 18.0), lambda: ent.p_fascia(18.0, M_NLIST[0]), "KIT_Fascia_01",
        f.cx, f.cy, f.rot, 0.0, -hy, top - 2.2, kit=ctx.kit)
    if f.tier <= 2 and f.enterable:
        _tier1_lobby(ctx, f, -hx + 0.4, hx - 0.4, -hy + 0.4, -hy + 11.0,
                     floor=M_FLCARP, desks=[-6.0], benches=2, shelfs=0)
        rows = 5
        bd2 = Builder()
        for r in range(rows):
            y = -hy + 14.0 + r * 3.4
            for i in range(8):
                x = -12.0 + i * 3.4
                bd2.box(x - 0.7, y, CURB, x + 0.7, y + 0.8, 0.45, M_INTUP)
                bd2.box(x - 0.7, y + 0.75, CURB, x + 0.7, y + 0.85, 1.0, M_INTUP)
        ibd = Builder()
        ibd.box(-hx + 0.6, -hy + 12.0, CURB, hx - 0.6, hy - 0.6, CURB + 0.03, M_FLCARP)
        remap = ibd.midx(M_INTUP)
        ibd.v.extend(bd2.v)
        ibd.f.extend(bd2.f)
        ibd.mi.extend([remap for _ in bd2.mi])
        emit(ctx, f, ibd, "INT_%s_Auditorium" % _cap(f.id), rot=f.rot)
        add_light(ctx, (f.cx, f.cy, 3.0), energy=120.0, radius=9.0)
    put(ctx, ("lamp",), lambda: ent.p_lamp(), "KIT_WallLamp_01",
        f.cx, f.cy, f.rot, -hx + 2.5, -hy, 2.95, coll=ctx.lights, kit=ctx.kit)
    put(ctx, ("lamp",), lambda: ent.p_lamp(), "KIT_WallLamp_02",
        f.cx, f.cy, f.rot, hx - 2.5, -hy, 2.95, coll=ctx.lights, kit=ctx.kit)
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def b_concert(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_PAVE)
    plinth(bd, hx, hy, M_STONE, 0.3)
    wall = M_MODE
    foe_hy = 20.0
    faces = fac_faces(bd, hx, hy)
    # foyer: full glass curtain front + angled roof
    ffy = -hy + 0.0
    fface = Face(bd, "y", ffy, ffy + WALL_T, -1, -hx + 6.0, hx - 6.0)
    glass_curtain(fface, CURB, 6.4, M_GLASSC, M_CHAR)
    sides = dict(L=Face(bd, "x", -hx, -hx + WALL_T, -1, ffy, ffy + foe_hy),
                 R=Face(bd, "x", hx - WALL_T, hx, 1, ffy, ffy + foe_hy))
    for s in sides.values():
        s.wall(CURB, 6.6, [], wall)
        s.rect(-hx + 0.6 if False else s.u0 + 0.5, CURB, s.u1 - 0.5, 6.4, M_GLASS, 0.1, 0.2)
    roof_deck(bd, hx, foe_hy, 6.6, M_ROOF)
    parapet_ring(bd, hx, foe_hy, 6.6, wall)
    # hall volume: brick box, vertical fins, emissive roof bands
    mass = dict(x0=-hx + 8.0, x1=hx - 8.0, y0=ffy + foe_hy, y1=hy - 1.0)
    zt = f.floors * FLOOR
    bd.box(mass["x0"], mass["y0"], CURB, mass["x1"], mass["y1"], zt, wall)
    n = int((mass["x1"] - mass["x0"]) / 4.0)
    for i in range(n + 1):
        x = mass["x0"] + i * (mass["x1"] - mass["x0"]) / n
        bd.box(x - 0.25, mass["y0"] - 0.4, CURB, x + 0.25, mass["y1"], zt, M_STONE)
    for k in range(3):
        z = zt - 1.2 + k * 0.0
        bd.box(mass["x0"] + 4.0, mass["y0"] - 0.55, zt - 0.9 - k * 0.9,
               mass["x1"] - 4.0, mass["y0"] - 0.42, zt - 0.65 - k * 0.9,
               M_EMITC if k % 2 == 0 else M_EMITW)
    bd.box(mass["x0"], mass["y0"], zt - 0.05, mass["x1"], mass["y1"], zt + 0.04, M_ROOF)
    for (a0, b0, a1, b1) in ((mass["x0"], mass["y0"], mass["x1"], mass["y0"] + 0.3),
                             (mass["x0"], mass["y1"] - 0.3, mass["x1"], mass["y1"]),
                             (mass["x0"], mass["y0"], mass["x0"] + 0.3, mass["y1"]),
                             (mass["x1"] - 0.3, mass["y0"], mass["x1"], mass["y1"])):
        bd.box(a0, b0, zt, a1, b1, zt + 0.9, wall)
    bd.box(mass["x0"], mass["y0"], zt, mass["x1"], mass["y1"], zt + 0.36, M_STONE)
    put(ctx, ("can", 14.0), lambda: ent.p_canopy(14.0), "KIT_Canopy_01",
        f.cx, f.cy, f.rot, 0.0, -hy, 3.0, kit=ctx.kit)
    put(ctx, ("fas", 14.0), lambda: ent.p_fascia(14.0, M_NBLUE), "KIT_Fascia_01",
        f.cx, f.cy, f.rot, -hx + 18.0, -hy, 6.9, kit=ctx.kit)
    if f.tier <= 2 and f.enterable:
        _tier1_lobby(ctx, f, -hx + 0.6, hx - 0.6, -hy + 0.5, -hy + foe_hy - 1.0,
                     "Foyer", floor=M_WPLAN, desks=[-4.0, 4.0], benches=4)
        add_light(ctx, (f.cx, f.cy, 2.8), energy=110.0, radius=9.0)
        add_light(ctx, (f.cx - 12.0 * math.cos(f.rot * math.pi / 180.0),
                        f.cy - 12.0 * math.sin(f.rot * math.pi / 180.0), 2.8),
                  energy=70.0, radius=6.0)
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def b_cinema(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_ASPA)
    plinth(bd, hx, hy, M_DARK, 0.3)
    wall = M_CHAR
    faces = fac_faces(bd, hx, hy)
    ops = [dict(u0=-8.0, u1=8.0, z0=CURB, z1=3.2)]
    faces["F"].wall(CURB, FLOOR, ops, wall)
    archway(faces["F"], ops[0], wall)
    for ff in ("L", "R", "B"):
        faces[ff].wall(CURB, FLOOR, [], wall)
    for z0 in range(1, f.floors):
        zz = FLOOR + (z0 - 1) * FLOOR
        faces["F"].wall(zz, zz + FLOOR, [], wall)
        faces["B"].wall(zz, zz + FLOOR, [], wall)
        for s in ("L", "R"):
            ribbon_band(faces[s], zz, wall, band_h=1.4)
    roof_deck(bd, hx, hy, top)
    parapet_ring(bd, hx, hy, top, wall, t=0.3)
    put(ctx, ("marq", 16.0), lambda: ent.p_marquee(16.0), "KIT_Marquee_01",
        f.cx, f.cy, f.rot, 0.0, -hy, 3.3, kit=ctx.kit)
    for sx in (-17.5, 17.5):
        put(ctx, ("poster",), lambda: ent.p_poster(), "KIT_Poster_%d" % (1 if sx < 0 else 2),
            f.cx, f.cy, f.rot, sx, -hy, 2.5, kit=ctx.kit)
    put(ctx, ("fas", 12.0), lambda: ent.p_fascia(12.0, M_NLIST[f.rng_kind or 0]),
        "KIT_Fascia_01", f.cx, f.cy, f.rot, 0.0, -hy, top - 2.3, kit=ctx.kit)
    put(ctx, ("rfac",), lambda: ent.p_roofac(), "KIT_RoofAC_01",
        f.cx, f.cy, f.rot, hx - 4.0, hy - 4.0, top + 0.05, kit=ctx.kit)
    put(ctx, ("pbox",), lambda: k_planter(), "KIT_RoofPlanter_01",
        f.cx, f.cy, f.rot, -hx + 4.0, hy - 4.0, top + 0.05, kit=ctx.kit)
    if f.tier <= 2 and f.enterable:
        _tier1_lobby(ctx, f, -hx + 0.4, hx - 0.4, -hy + 0.4, -hy + 10.0,
                     floor=M_FLCARP, desks=[-4.0, 3.5], benches=2)
        bd2 = Builder()
        for r in range(4):
            y = -hy + 12.5 + r * 3.2
            for i in range(6):
                x = -10.0 + i * 4.0
                bd2.box(x - 0.7, y, CURB, x + 0.7, y + 0.8, 0.45, M_INTUP)
        ibd = Builder()
        ibd.box(-hx + 0.6, -hy + 11.0, CURB, hx - 0.6, hy - 0.6, CURB + 0.03, M_DARK)
        remap = ibd.midx(M_INTUP)
        ibd.v.extend(bd2.v)
        ibd.f.extend(bd2.f)
        ibd.mi.extend([remap for _ in bd2.mi])
        emit(ctx, f, ibd, "INT_%s_Auditorium" % _cap(f.id), rot=f.rot)
        add_light(ctx, (f.cx, f.cy, 3.0), energy=90.0, radius=8.0)
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def _budget_note(ctx, f):
    if f.tris > f.budget:
        ctx.note(f, "tri budget over: %d > %d" % (f.tris, f.budget))


def b_club(ctx, f):
    """CUL_CLUB: tier-3 dark facade-only, neon runs + recessed fake depth."""
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_ASPA)
    plinth(bd, hx, hy, M_CHAR, 0.3)
    wall = M_CHAR
    ply = top
    fake_facade(bd, hx - 0.0, hy, CURB, ply - 1.0, wall, M_GLASSH, cols=6, rows=max(1, f.floors))
    roof_deck(bd, hx, hy, ply)
    parapet_ring(bd, hx, hy, ply, wall, t=0.3)
    for u in (-hx + 2.2, hx - 2.2):
        put(ctx, ("nv", u), lambda: ent.p_neonvert(min(6.0, top - 0.6), M_NLIST[1]),
            "KIT_NeonRun_%02d" % (1 if u < 0 else 2), f.cx, f.cy, f.rot, u, -hy, 1.2,
            kit=ctx.kit)
    put(ctx, ("led",), lambda: ent.p_led(5.0, 1.8), "KIT_LEDPanel_01",
        f.cx, f.cy, f.rot, 0.0, -hy, 0.9, kit=ctx.kit)
    put(ctx, ("rfvent",), lambda: ent.p_ventroof(), "KIT_RoofVent_01",
        f.cx, f.cy, f.rot, hx - 3.0, hy - 3.0, ply + 0.05, kit=ctx.kit)
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def b_arcade(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_ASPA)
    plinth(bd, hx, hy, M_STONE, 0.3)
    wall = M_BONE
    faces = fac_faces(bd, hx, hy)
    ops = [dict(u0=-10.0, u1=10.0, z0=CURB, z1=3.4),
           dict(u0=-hx + 4.0, u1=-hx + 9.0, z0=CURB, z1=3.4),
           dict(u0=hx - 9.0, u1=hx - 4.0, z0=CURB, z1=3.4)]
    faces["F"].wall(CURB, FLOOR, ops, wall)
    for o in ops:
        archway(faces["F"], o, wall)
    for eff in ("L", "R", "B"):
        faces[eff].wall(CURB, FLOOR, [], wall)
    for z0 in range(1, f.floors):
        zz = FLOOR + (z0 - 1) * FLOOR
        ribbon_band(faces["L"], zz, wall, band_h=1.5)
        ribbon_band(faces["R"], zz, wall, band_h=1.5)
        punched(faces["F"], zz, wall, sp=5.0, w=2.4)
        faces["B"].wall(zz, zz + FLOOR, [], wall)
    roof_deck(bd, hx, hy, top)
    parapet_ring(bd, hx, hy, top, wall)
    # neon accent bands across the facade
    for k, mat in enumerate(M_NLIST[:3]):
        z = 4.0 + k * 1.1
        bd.box(-hx + 2.0, -hy - 0.12, z, hx - 2.0, -hy + 0.02, z + 0.32, mat)
    for i in range(6):
        put(ctx, ("cab",), lambda: k_cab(), "KIT_ArcadeCab_%02d" % (i + 1),
            f.cx, f.cy, f.rot, -7.5 + i * 3.0, -hy + 3.2, 0.0, kit=ctx.kit)
    put(ctx, ("fas", 16.0), lambda: ent.p_fascia(16.0, M_NLIST[2]), "KIT_Fascia_01",
        f.cx, f.cy, f.rot, 0.0, -hy, top - 2.3, kit=ctx.kit)
    _tier1_lobby(ctx, f, -hx + 0.4, hx - 0.4, -hy + 0.5, -hy + 10.0,
                 floor=M_FLT, desks=[0.0], benches=2)
    for i in range(8):
        put(ctx, ("cab",), lambda: k_cab(), "KIT_CabHall_%02d" % (i + 1),
            f.cx, f.cy, f.rot, -10.5 + (i % 4) * 7.0, -hy + 12.0 + (i // 4) * 4.0,
            0.0, kit=ctx.kit)
    add_light(ctx, (f.cx, f.cy, 2.8), energy=90.0, radius=9.0)
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def b_casino(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_ASPA)
    plinth(bd, hx, hy, M_STONE, 0.3)
    wall = M_DARK
    faces = fac_faces(bd, hx, hy)
    ops = [dict(u0=-12.0, u1=12.0, z0=CURB, z1=4.2)]
    faces["F"].wall(CURB, FLOOR, ops, wall)
    archway(faces["F"], ops[0], wall, steps=6)
    for eff in ("L", "R", "B"):
        faces[eff].wall(CURB, FLOOR, [], wall)
    for z0 in range(1, f.floors):
        zz = FLOOR + (z0 - 1) * FLOOR
        punched(faces["F"], zz, wall, sp=6.0, w=2.6, h=2.0, glass=M_GLASSH)
        faces["B"].wall(zz, zz + FLOOR, [], wall)
        for s in ("L", "R"):
            ribbon_band(faces[s], zz, wall, band_h=1.55, glass=M_GLASSH)
    roof_deck(bd, hx, hy, top)
    parapet_ring(bd, hx, hy, top, wall, t=0.35)
    # emissive signage: horizontal strips + big vertical runs + canopy
    for k in range(4):
        z = 5.2 + k * 2.2
        mat = [M_NPINK, M_NBLUE, M_EMITW, M_NLIST[0]][k]
        bd.box(-hx + 3.0, -hy - 0.14, z, hx - 3.0, -hy + 0.01, z + 0.5, mat)
    put(ctx, ("can", 22.0), lambda: ent.p_canopy(22.0), "KIT_Canopy_01",
        f.cx, f.cy, f.rot, 0.0, -hy, 4.3, kit=ctx.kit)
    for sx in (-hx + 2.0, hx - 2.0):
        put(ctx, ("nv2", sx), lambda: ent.p_neonvert(top - 2.0, M_NPINK),
            "KIT_NeonRun_%02d" % (1 if sx < 0 else 2), f.cx, f.cy, f.rot, sx, -hy + 0.1,
            1.0, kit=ctx.kit)
    put(ctx, ("fas", 24.0), lambda: ent.p_fascia(24.0, M_NPINK), "KIT_Fascia_01",
        f.cx, f.cy, f.rot, 0.0, -hy, top - 2.4, kit=ctx.kit)
    _tier1_lobby(ctx, f, -hx + 0.5, hx - 0.5, -hy + 0.4, -hy + 16.0,
                 floor=M_MARBLE, desks=[-6.0, 6.0], benches=3)
    bd2 = Builder()
    for r in range(3):
        y = -hy + 20.0 + r * 7.0
        for i in range(6):
            x = -40.0 + i * 16.0
            bd2.box(x - 0.9, y, CURB, x + 0.9, y + 1.9, 0.78, M_WOODO)
            bd2.box(x - 1.0, y - 0.1, 0.78, x + 1.0, y + 2.0, 0.84, M_FLW)
    bd2.box(-hx + 2.0, hy - 6.0, CURB, hx - 2.0, hy - 2.0, 2.2, M_WALLP)
    ibd = Builder()
    ibd.box(-hx + 0.7, -hy + 15.0, CURB, hx - 0.7, hy - 0.7, CURB + 0.03, M_MARBLE)
    remap = ibd.midx(M_INTLAM)
    ibd.v.extend(bd2.v)
    ibd.f.extend(bd2.f)
    ibd.mi.extend([ibd.midx(M_WOODO) for _ in bd2.mi])
    emit(ctx, f, ibd, "INT_%s_GamingHall" % _cap(f.id), rot=f.rot)
    add_light(ctx, (f.cx, f.cy, 6.0), energy=160.0, radius=12.0)
    add_light(ctx, (f.cx, f.cy, 2.8), energy=140.0, radius=10.0)
    put(ctx, ("pbox",), lambda: k_planter(), "KIT_RoofPlanter_01",
        f.cx, f.cy, f.rot, hx - 6.0, hy - 6.0, top + 0.05, kit=ctx.kit)
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def b_gallery(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_PAVE)
    plinth(bd, hx, hy, M_STONE, 0.3)
    wall = M_BONE
    faces = fac_faces(bd, hx, hy)
    ops = [dict(u0=-9.0, u1=9.0, z0=CURB, z1=4.0)]
    faces["F"].wall(CURB, FLOOR + FLOOR, ops, wall)
    archway(faces["F"], ops[0], wall, steps=3)
    for zz in (FLOOR,):
        punched(faces["L"], zz, wall, sp=6.5, w=3.2, h=2.2, glass=M_GLASSC)
        punched(faces["R"], zz, wall, sp=6.5, w=3.2, h=2.2, glass=M_GLASSC)
    faces["B"].wall(CURB, 2.0 * FLOOR, [], wall)
    roof_deck(bd, hx, hy, 2.0 * FLOOR)
    parapet_ring(bd, hx, hy, 2.0 * FLOOR, wall)
    saw = [(-1.0, -0.45), (-0.35, 0.2), (0.3, 0.85)]
    for (a0, a1) in saw:
        x0 = a0 * hx
        x1 = a1 * hx
        gable(bd, x0, x1, -hy + 1.0, hy - 1.0, 2.0 * FLOOR + 0.3, 2.0 * FLOOR + 3.4,
              M_PANEL, along="y")
    bd.box(-9.0, -hy + 14.0, CURB, -5.0, -hy + 18.0, 0.9, M_CONC)
    bd.cyl(-7.0, -hy + 16.0, 0.9, 3.0, 1.0, M_CHROME, seg=12)
    if f.tier <= 2 and f.enterable:
        _tier1_lobby(ctx, f, -hx + 0.5, hx - 0.5, -hy + 0.4, -hy + 18.0,
                     floor=M_WPLAN, desks=[-3.0], benches=3, shelfs=2)
    for i in range(6):
        put(ctx, ("plan",), lambda: k_planter(), "KIT_CourtPlanter_%02d" % (i + 1),
            f.cx, f.cy, f.rot, hx - 4.0 if i % 2 else -hx + 4.0,
            -hy + 6.0 + (i // 2) * 6.0, 0.0, kit=ctx.kit)
    add_light(ctx, (f.cx, f.cy, 2.7), energy=100.0, radius=9.0)
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def b_library(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_PAVE)
    plinth(bd, hx, hy, M_STONE, 0.3)
    wall = M_BRICK
    faces = fac_faces(bd, hx, hy)
    ops = [dict(u0=-8.0, u1=8.0, z0=CURB, z1=4.2)]
    faces["F"].wall(CURB, FLOOR, ops, wall)
    archway(faces["F"], ops[0], wall)
    for z0 in range(1, f.floors):
        zz = FLOOR + (z0 - 1) * FLOOR
        ribbon_band(faces["F"], zz, wall, band_h=1.9)
        ribbon_band(faces["L"], zz, wall, band_h=1.9)
        ribbon_band(faces["R"], zz, wall, band_h=1.9)
        ribbon_band(faces["B"], zz, wall, band_h=1.6)
    roof_deck(bd, hx, hy, top)
    parapet_ring(bd, hx, hy, top, wall)
    # brise-soleil fins on the front + roof plant/water tanks
    n = int(2 * hx / 2.6)
    for i in range(n + 1):
        u = -hx + i * (2 * hx) / n
        bd.box(u - 0.09, -hy - 0.5, FLOOR, u + 0.09, -hy + 0.05, top - 0.6, M_STEEL)
    put(ctx, ("tank",), lambda: ent.p_tank(), "KIT_WaterTank_01",
        f.cx, f.cy, f.rot, hx - 6.0, hy - 6.0, top + 0.05, kit=ctx.kit)
    put(ctx, ("rfac",), lambda: ent.p_roofac(), "KIT_RoofAC_01",
        f.cx, f.cy, f.rot, -hx + 6.0, hy - 6.0, top + 0.05, kit=ctx.kit)
    _tier1_lobby(ctx, f, -hx + 0.5, hx - 0.5, -hy + 0.4, -hy + 12.0,
                 floor=M_FLW, desks=[-5.0, 5.0], benches=3, shelfs=4)
    bd2 = Builder()
    for i in range(6):
        x = -hx + 5.0 + i * ((2 * hx - 12.0) / 5.0)
        bd2.box(x - 0.9, -hy + 14.0, CURB, x + 0.9, -hy + 14.9, 2.0, M_WPLAN)
    ibd = Builder()
    ibd.box(-hx + 0.7, -hy + 11.5, CURB, hx - 0.7, hy - 0.7, CURB + 0.03, M_FLW)
    remap = ibd.midx(M_WPLAN)
    ibd.v.extend(bd2.v)
    ibd.f.extend(bd2.f)
    ibd.mi.extend([remap for _ in bd2.mi])
    emit(ctx, f, ibd, "INT_%s_ReadingRoom" % _cap(f.id), rot=f.rot)
    add_light(ctx, (f.cx, f.cy, 2.7), energy=110.0, radius=10.0)
    add_light(ctx, (f.cx, f.cy + (hy - 10.0) * math.cos(f.rot * math.pi / 180.0), 2.7),
              energy=60.0, radius=7.0)
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def b_hospital(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_PAVE)
    plinth(bd, hx, hy, M_STONE, 0.3)
    wall = M_PANEL
    zpod = 2 * FLOOR
    faces = fac_faces(bd, hx, hy)
    opsF = [dict(u0=-10.0, u1=10.0, z0=CURB, z1=3.6)]
    faces["F"].wall(CURB, zpod, opsF, wall)
    archway(faces["F"], opsF[0], wall)
    for eff in ("L", "R", "B"):
        faces[eff].wall(CURB, zpod, [], wall)
    deckz = 2.0 * FLOOR
    roof_deck(bd, hx, hy, deckz)
    parapet_ring(bd, hx, hy, deckz, wall)
    # 8-floor tower over the rear half
    tz = deckz
    ttz = tz + (f.floors - 2) * FLOOR
    bd.box(-hx + 2.0, hy * 0.05, tz, hx - 2.0, hy - 1.5, ttz, wall)
    for sz in ("x0",):
        pass
    tface_B = Face(bd, "y", hy - 1.5 - WALL_T, hy - 1.5, 1, -hx + 2.0, hx - 2.0)
    zc = tz
    while zc + FLOOR <= ttz:
        ribbon_band(tface_B, zc, wall, band_h=1.6)
        zc += FLOOR
    face_L2 = Face(bd, "x", -hx + 2.0, -hx + 2.0 + WALL_T, -1, hy * 0.05, hy - 1.5)
    face_R2 = Face(bd, "x", hx - 2.0 - WALL_T, hx - 2.0, 1, hy * 0.05, hy - 1.5)
    for fc2 in (face_L2, face_R2):
        zc = tz
        while zc + FLOOR <= ttz:
            ribbon_band(fc2, zc, wall, band_h=1.6)
            zc += FLOOR
    bd.box(-hx + 2.0, hy * 0.05, ttz - 0.05, hx - 2.0, hy - 1.5, ttz + 0.04, M_ROOF)
    for (a0, b0, a1, b1) in ((-hx + 2.0, hy * 0.05, hx - 2.0, hy * 0.05 + 0.3),
                             (-hx + 2.0, hy - 1.8, hx - 2.0, hy - 1.5),
                             (-hx + 2.0, hy * 0.05, -hx + 2.3, hy - 1.5),
                             (hx - 2.3, hy * 0.05, hx - 2.0, hy - 1.5)):
        bd.box(a0, b0, ttz, a1, b1, ttz + 0.9, wall)
    # helipad on the tower roof
    hpx, hpy = 0.0, (hy * 0.05 + hy - 1.5) * 0.5
    bd.box(-8.0, hpy - 8.0, ttz + 0.1, 8.0, hpy + 8.0, ttz + 0.22, M_CONC)
    for k in range(8):
        aa = math.pi * k / 8.0
        bx0 = -7.2 * math.cos(aa)
        by0 = hpy - 7.2 * math.sin(aa)
        bx1 = -6.6 * math.cos(aa)
        by1 = hpy - 6.6 * math.sin(aa)
        # ring segments drawn as small quads
        bd.poly([(bx0, by0, ttz + 0.26), (bx1, by0, ttz + 0.26),
                 (bx1, by1, ttz + 0.26), (bx0, by1, ttz + 0.26)], M_MARKW) if False else None
    loft_ring(bd, ring_pts(hpx, hpy, 7.0, 16), ring_pts(hpx, hpy, 6.4, 16),
              ttz + 0.24, ttz + 0.24, "unused") if False else None
    for k in range(16):
        a0 = 2 * math.pi * k / 16
        a1 = 2 * math.pi * (k + 1) / 16
        bd.poly([(-6.0 * math.sin(a0), hpy - 6.0 * math.cos(a0) + (0.0), ttz + 0.24),
                 (-6.0 * math.sin(a1), hpy - 6.0 * math.cos(a1), ttz + 0.24),
                 (-6.4 * math.sin(a1), hpy - 6.4 * math.cos(a1), ttz + 0.24),
                 (-6.4 * math.sin(a0), hpy - 6.4 * math.cos(a0), ttz + 0.24)], M_MARKW)
    for k in range(16):
        a0 = 2 * math.pi * k / 16
        a1 = 2 * math.pi * (k + 1) / 16
        bd.poly([(6.0 * math.sin(a0), hpy - 6.0 * math.cos(a0), ttz + 0.24),
                 (6.0 * math.sin(a1), hpy - 6.0 * math.cos(a1), ttz + 0.24),
                 (6.4 * math.sin(a1), hpy - 6.4 * math.cos(a1), ttz + 0.24),
                 (6.4 * math.sin(a0), hpy - 6.4 * math.cos(a0), ttz + 0.24)], M_MARKW)
    bd.box(-1.2, hpy - 6.0, ttz + 0.24, 1.2, hpy - 4.0, ttz + 0.27, M_MARKW)
    bd.box(-1.2, hpy + 4.0, ttz + 0.24, 1.2, hpy + 6.0, ttz + 0.27, M_MARKW)
    bd.box(-3.4, hpy - 0.9, ttz + 0.24, -1.2, hpy + 0.9, ttz + 0.27, M_MARKW)
    bd.box(1.2, hpy - 0.9, ttz + 0.24, 3.4, hpy + 0.9, ttz + 0.27, M_MARKW)
    bd.box(-0.55, hpy - 0.9, ttz + 0.24, 0.55, hpy + 0.9, ttz + 0.27, M_MARKW)
    # ambulance canopy + open bays at the rear podium
    bd.box(hx - 22.0, hy - 16.0, CURB, hx - 2.0, hy - 12.0, 0.06, M_ASPA)
    for k in range(3):
        put(ctx, ("can", 6.0), lambda: ent.p_awning(M_CANVAS, 6.0),
            "KIT_AmbAward_%02d" % (k + 1), f.cx, f.cy, f.rot, hx - 18.0 + k * 7.0,
            hy - 16.0, 4.6, kit=ctx.kit)
    put(ctx, ("rfac",), lambda: ent.p_roofac(), "KIT_RoofAC_01",
        f.cx, f.cy, f.rot, hx - 6.0, -hy + 6.0, deckz + 0.05, kit=ctx.kit)
    _tier1_lobby(ctx, f, -hx + 0.5, hx - 0.5, -hy + 0.4, -hy + 14.0,
                 floor=M_FLW, desks=[-6.0, 6.0], benches=4)
    add_light(ctx, (f.cx, f.cy, 2.7), energy=110.0, radius=10.0)
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def b_fire(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_ASPA)
    plinth(bd, hx, hy, M_STONE, 0.25)
    wall = M_BONE
    faces = fac_faces(bd, hx, hy)
    bay_h = 4.6
    n_bays = 4
    ops = [dict(u0=-hx + 8.0 + k * 11.0, u1=-hx + 8.0 + k * 11.0 + 8.0, z0=CURB, z1=bay_h)
           for k in range(n_bays)]
    faces["F"].wall(CURB, bay_h, ops, wall)     # NO door meshes: bays stay open
    faces["F"].wall(bay_h, top, [], wall)
    for eff in ("L", "R", "B"):
        faces[eff].wall(CURB, top, [], wall)
    bay_deck = bay_h + 0.1
    bd.box(-hx + 1.0, -hy + 1.0, bay_deck - 0.6, hx - 1.0, hy - 1.0, bay_deck - 0.3,
           M_CONC)
    roof_deck(bd, hx, hy, top + 1.0)
    parapet_ring(bd, hx, hy, top + 1.0, wall)
    # red fascia + hose tower
    bd.box(-hx + 1.0, -hy - 0.16, top + 1.0, hx - 1.0, -hy + 0.01, top + 2.0, M_OXB)
    bd.box(-hx + 2.0, -hy + 1.5, top + 1.0, -hx + 11.0, hy - 1.5, top + 11.0, M_BRICK)
    dome(bd, -hx + 6.5, 0.0, top + 11.0, 3.4, 1.6, M_BRICKB, seg=10)
    bd.cyl(-hx + 2.4, -22.0, top + 11.0, top + 13.6, 0.09, M_STEEL, seg=6)
    bd.box(-hx + 2.2, -22.4, top + 13.6, -hx + 2.6, -21.6, top + 14.1, M_EMITC)
    put(ctx, ("lamp",), lambda: ent.p_lamp(), "KIT_WallLamp_01",
        f.cx, f.cy, f.rot, -hx + 3.0, -hy, 2.95, coll=ctx.lights, kit=ctx.kit)
    put(ctx, ("lamp",), lambda: ent.p_lamp(), "KIT_WallLamp_02",
        f.cx, f.cy, f.rot, hx - 3.0, -hy, 2.95, coll=ctx.lights, kit=ctx.kit)
    if f.tier <= 2 and f.enterable:
        _tier1_lobby(ctx, f, -hx + 0.6, hx - 0.6, -hy + 6.2, -hy + 13.0,
                     floor=M_FLT, desks=[0.0], benches=2)
    add_light(ctx, (f.cx, f.cy, 3.4), energy=80.0, radius=7.0)
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def b_police(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_ASPA)
    plinth(bd, hx, hy, M_STONE, 0.3)
    wall = M_BONE
    faces = fac_faces(bd, hx, hy)
    ops = [dict(u0=-7.0, u1=7.0, z0=CURB, z1=3.4)]
    faces["F"].wall(CURB, FLOOR, ops, wall)
    archway(faces["F"], ops[0], wall)
    for eff in ("L", "R", "B"):
        faces[eff].wall(CURB, FLOOR, [], wall)
    for z0 in range(1, f.floors):
        zz = FLOOR + (z0 - 1) * FLOOR
        punched(faces["F"], zz, wall, sp=4.4, w=1.9, h=1.6, glass=M_GLASSH)
        faces["B"].wall(zz, zz + FLOOR, [], wall)
        for s in ("L", "R"):
            ribbon_band(faces[s], zz, wall, band_h=1.35)
    roof_deck(bd, hx, hy, top)
    parapet_ring(bd, hx, hy, top, wall)
    bd.box(-hx + 1.0, -hy - 0.14, top - 0.7, hx - 1.0, -hy + 0.01, top, M_NAVY)
    # parking pads, bollards, blue lamp
    for k in range(6):
        bd.box(-hx + 4.0 + k * 9.0, -hy - 6.0, 0.0, -hx + 12.0 + k * 9.0, hy - 2.0 if False else -hy - 3.6, 0.06, M_ASPA)
    for k in range(7):
        put(ctx, ("bol",), lambda: k_bollard(), "KIT_Bollard_%02d" % (k + 1),
            f.cx, f.cy, f.rot, -hx + 4.0 + k * 9.0, -hy - 0.8, 0.0, kit=ctx.kit)
    put(ctx, ("led",), lambda: ent.p_led(6.0, 1.6), "KIT_LEDPanel_01",
        f.cx, f.cy, f.rot, 0.0, -hy, 1.0, kit=ctx.kit)
    if f.tier <= 2 and f.enterable:
        _tier1_lobby(ctx, f, -hx + 0.5, hx - 0.5, -hy + 0.4, -hy + 12.0,
                     floor=M_FLT, desks=[-3.0, 3.0], benches=2)
    add_light(ctx, (f.cx, f.cy, 2.7), energy=80.0, radius=7.0, color=(0.75, 0.85, 1.0))
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def _school_common(ctx, f, wall, accents, wing_layout, yard="M_ASPA", shade=True):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_ASPA)
    plinth(bd, hx, hy, M_STONE, 0.3)
    faces_cache = fac_faces(bd, hx, hy)
    placed_faces = {}
    for (x0, y0, x1, y1, fl) in wing_layout:
        # rectangular wing with its own punched storeys
        wbd = []
        for zfi in range(max(1, fl)):
            zz = CURB + zfi * FLOOR
            gt = zz + FLOOR
            bd.box(x0, y0, zz, x1, y1, gt, wall)
            for side, (a0, b0, a1, b1, axis, d0, d1, out, u0, u1) in (
                    ("F", (x0, y0, x1, y0, "y", y0, y0 + WALL_T, -1, x0, x1)),
                    ("B", (x0, y1 - WALL_T, x1, y1, "y", y1 - WALL_T, y1, 1, x0, x1)),
                    ("L", (x0, y0, x0 + WALL_T, y1, "x", x0, x0 + WALL_T, -1, y0, y1)),
                    ("R", (x1 - WALL_T, y0, x1, y1, "x", x1 - WALL_T, x1, 1, y0, y1))):
                fc = FakeFace(bd, axis, d0, d1, out, u0, u1)
                ops = [dict(u0=fc.u0 + 1.5 + (i % max(1, int((fc.length - 3.0) / 4.0))) * 4.0,
                            u1=fc.u0 + 3.2 + (i % max(1, int((fc.length - 3.0) / 4.0))) * 4.0,
                            z0=zz + 1.0, z1=zz + 2.6)
                       for i in range(max(1, int((fc.length - 3.0) / 4.0)))]
                ops = [o for o in ops if o["u1"] < fc.u1 - 1.2]
                fc.wall(zz, gt, ops, wall)
                for o in ops:
                    fc.rect(o["u0"], o["z0"], o["u1"], o["z1"], M_GLASS, 0.1, 0.18)
                    fc.rect(o["u0"] - 0.08, o["z0"] - 0.12, o["u1"] + 0.08, o["z0"],
                            M_STONE, -0.06, 0.07)
        if fl <= 0:
            bd.box(x0, y0, 0.0, x1, y1, 3.0, wall)
        # roof
        bd.box(x0, y0, CURB + fl * FLOOR - 0.05, x1, y1, CURB + fl * FLOOR + 0.05, M_ROOF)
        bd.box(x0, y0, CURB + fl * FLOOR, x1, y0 + 0.25, CURB + fl * FLOOR + 0.9, wall)
        bd.box(x0, y1 - 0.25, CURB + fl * FLOOR, x1, y1, CURB + fl * FLOOR + 0.9, wall)
        bd.box(x0, y0, CURB + fl * FLOOR, x0 + 0.25, y1, CURB + fl * FLOOR + 0.9, wall)
        bd.box(x1 - 0.25, y0, CURB + fl * FLOOR, x1, y1, CURB + fl * FLOOR + 0.9, wall)
    if accents:
        for (a0, b0, a1, b1, mat) in accents:
            bd.box(a0, b0, 0.3, a1, b1, 3.2, mat)
    # covered walkway columns
    if shade:
        for k in range(5):
            u = -hx * 0.55 + k * (hx * 1.1 / 4.0)
            put(ctx, ("lp",), lambda: k_lamppost(), "KIT_LampPost_%02d" % (k + 1),
                f.cx, f.cy, f.rot, u, -hy - 6.5, 0.0, kit=ctx.kit)
    return bd


class FakeFace(Face):
    pass


def b_school(ctx, f, layout_key="U"):
    hx, hy, top = f.hx, f.hy, f.top
    if layout_key == "U":
        wings = [(-hx, -hy, -hx + 22.0, hy, f.floors),
                 (hx - 22.0, -hy, hx, hy, f.floors),
                 (-hx + 22.0, hy - 20.0, hx - 22.0, hy, f.floors)]
        accents = [(-7.0, -hy - 0.12, 7.0, -hy + 0.03, M_TEAL)]
    elif layout_key == "L":
        wings = [(-hx, -hy, hx, -hy + 22.0, f.floors),
                 (-hx, -hy + 22.0, -hx + 26.0, hy, f.floors)]
        accents = [(-4.0, -hy - 0.12, 4.0, -hy + 0.03, M_MUST)]
    else:  # kinder: single block
        wings = [(-hx + 4.0, -hy + 4.0, hx - 4.0, hy - 4.0, max(2, f.floors))]
        accents = [(-hx + 5.0, -hy + 3.4, hx - 5.0, -hy + 3.6, M_TEAL),
                   (-hx + 5.0, -0.4, hx - 5.0, -0.2, M_MUST)]
    bd = _school_common(ctx, f, M_BONE, accents, wings)
    # playground / yard markings
    bd.box(-hx + 2.0, -hy + 2.0, 0.06, hx - 2.0, -hy + 20.0, 0.09, M_ASPA)
    if layout_key != "single" and f.id == "SCHOOL_SECONDARY":
        for k in range(3):
            bd.box(-8.0 + k * 2.4, -hy + 6.0, 0.09, -7.2 + k * 2.4, -hy + 12.0,
                   0.12, M_MARKW)
        bd.box(6.0, -hy + 8.0, 0.09, 21.0, 6.2 + 8.0 if False else -hy + 20.0, 0.12, M_MARKW)
    if f.id == "SCHOOL_KINDER":
        bd.cyl(10.0, -hy + 12.0, 0.06, 0.14, 6.0, M_SAND, seg=14)
        bd.box(16.0, -hy + 6.0, 0.0, 20.0, -hy + 10.0, 0.5, M_WPLAN)
        put(ctx, ("slide",), lambda: k_bench(3.0), "KIT_WaterSill_01",
            f.cx, f.cy, f.rot, 18.0, -hy + 8.0, 0.5, kit=ctx.kit)
    if f.tier <= 2 and f.enterable:
        _tier1_lobby(ctx, f, -hx + 1.0, -hx + 18.0 if layout_key == "U" else hx - 20.0,
                     -hy + 0.5, -hy + 12.0, floor=M_FLW, desks=[-3.0], benches=2)
    for k in range(4):
        put(ctx, ("pbox",), lambda: k_planter(), "KIT_YardPlanter_%02d" % (k + 1),
            f.cx, f.cy, f.rot, -hx + 6.0 + k * ((2 * hx - 12.0) / 3.0), hy - 3.0,
            0.0, kit=ctx.kit)
    add_light(ctx, (f.cx, f.cy, 2.7), energy=70.0, radius=7.0)
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def b_clinic(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_PAVE)
    plinth(bd, hx, hy, M_STONE, 0.3)
    wall = M_PANEL
    faces = fac_faces(bd, hx, hy)
    ops = [dict(u0=-6.0, u1=6.0, z0=CURB, z1=3.4)]
    faces["F"].wall(CURB, FLOOR, ops, wall)
    archway(faces["F"], ops[0], wall)
    for eff in ("L", "R", "B"):
        faces[eff].wall(CURB, FLOOR, [], wall)
    for z0 in range(1, max(2, f.floors)):
        zz = FLOOR + (z0 - 1) * FLOOR
        ribbon_band(faces["F"], zz, wall)
        ribbon_band(faces["L"], zz, wall)
        ribbon_band(faces["R"], zz, wall)
        faces["B"].wall(zz, zz + FLOOR, [], wall)
    roof_deck(bd, hx, hy, top)
    parapet_ring(bd, hx, hy, top, wall)
    put(ctx, ("can", 8.0), lambda: ent.p_canopy(8.0), "KIT_Canopy_01",
        f.cx, f.cy, f.rot, 0.0, -hy, 3.0, kit=ctx.kit)
    # emissive cross sign
    bd.box(-0.5, -hy - 0.3, top - 2.6, 0.5, -hy + 0.0, top - 0.6, M_SIGNW)
    bd.box(-1.6, -hy - 0.34, top - 2.0, 1.6, -hy + 0.04, top - 1.2, M_SIGNW)
    bd.box(-0.5, -hy - 0.35, top - 2.6, 0.5, -hy - 0.3, top - 0.6, M_EMITC)
    bd.box(-1.6, -hy - 0.39, top - 2.0, 1.6, -hy - 0.34, top - 1.2, M_EMITC)
    _tier1_lobby(ctx, f, -hx + 0.4, hx - 0.4, -hy + 0.4, -hy + 12.0,
                 floor=M_FLT, desks=[-3.0, 3.0], benches=3)
    add_light(ctx, (f.cx, f.cy, 2.7), energy=80.0, radius=7.0)
    put(ctx, ("rfac",), lambda: ent.p_roofac(), "KIT_RoofAC_01",
        f.cx, f.cy, f.rot, hx - 4.0, hy - 4.0, top + 0.05, kit=ctx.kit)
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def b_offices(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_PAVE)
    plinth(bd, hx, hy, M_STONE, 0.3)
    wall = M_MODE
    faces = fac_faces(bd, hx, hy)
    ops = [dict(u0=-9.0, u1=9.0, z0=CURB, z1=3.8)]
    faces["F"].wall(CURB, FLOOR, ops, wall)
    archway(faces["F"], ops[0], wall)
    for eff in ("L", "R", "B"):
        faces[eff].wall(CURB, FLOOR, [], wall)
    for z0 in range(1, f.floors):
        zz = FLOOR + (z0 - 1) * FLOOR
        ribbon_band(faces["F"], zz, wall, band_h=1.75)
        ribbon_band(faces["L"], zz, wall, band_h=1.75)
        ribbon_band(faces["R"], zz, wall, band_h=1.75)
        faces["B"].wall(zz, zz + FLOOR, [], wall)
    roof_deck(bd, hx, hy, top)
    parapet_ring(bd, hx, hy, top, wall)
    n = int(2 * hx / 3.2)
    for i in range(n + 1):
        u = -hx + i * (2 * hx) / n
        bd.box(u - 0.1, -hy - 0.45, FLOOR, u + 0.1, -hy + 0.05, top - 0.7, M_STEEL)
    put(ctx, ("rfac",), lambda: ent.p_roofac(), "KIT_RoofAC_01",
        f.cx, f.cy, f.rot, hx - 5.0, hy - 5.0, top + 0.05, kit=ctx.kit)
    put(ctx, ("rfac",), lambda: ent.p_roofac(), "KIT_RoofAC_02",
        f.cx, f.cy, f.rot, -hx + 5.0, -hy + 5.0, top + 0.05, kit=ctx.kit)
    put(ctx, ("pbox",), lambda: k_planter(), "KIT_RoofPlanter_01",
        f.cx, f.cy, f.rot, 0.0, hy - 5.0, top + 0.05, kit=ctx.kit)
    for k in range(3):
        put(ctx, ("flag", 12.0), lambda: k_flag(12.0), "KIT_Flagpole_%02d" % (k + 1),
            f.cx, f.cy, f.rot, -10.0 + k * 10.0, -hy - 5.0, 0.0, kit=ctx.kit)
    if f.tier <= 2 and f.enterable:
        _tier1_lobby(ctx, f, -hx + 0.4, hx - 0.4, -hy + 0.4, -hy + 13.0,
                     floor=M_MARBLE, desks=[-4.0, 4.0], benches=3, shelfs=1)
    add_light(ctx, (f.cx, f.cy, 2.7), energy=90.0, radius=8.0)
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def b_college(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = b_offices(ctx, f)
    # workshop sheds: mono-pitch, open bays (no doors)
    for sy in (-1.0, 1.0):
        y0 = sy * (hy - 12.0) if sy > 0 else -hy + 2.0
        sx0, sx1 = -hx + 4.0, hx - 30.0
        gy0, gy1 = (0.0, 12.0) if sy < 0 else (hy - 16.0, hy - 4.0)
        bd.box(sx0, gy0 + 4.0, CURB, sx1, gy1, 4.4, M_BRICKB)
        bd.poly([(sx0, gy0 + 4.0, 4.4), (sx1, gy0 + 4.0, 4.4),
                 (sx1, gy0 + 4.0, 7.4), (sx0, gy0 + 4.0, 7.4)], M_ROOFM) if False else None
        bd.poly([(sx0, gy0 + 4.0, 4.4), (sx1, gy0 + 4.0, 4.4),
                 (sx1, gy1, 5.8), (sx0, gy1, 5.8)], M_ROOFM)
        bd.poly([(sx0, gy0 + 4.0, 4.4), (sx0, gy1, 5.8), (sx1, gy1, 5.8), (sx1, gy0 + 4.0, 4.4)],
                M_ROOFM)
        bd.box(sx0, gy0 + 4.0, 4.4, sx1, gy0 + 4.1, 5.6, M_ROOFM) if False else None
    return bd


def b_uni_main(ctx, f):
    """UNIVERSITY_MAIN: colonnaded front + inner QUAD with arcade ring."""
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_ASPA)
    plinth(bd, hx, hy, M_STONE, 0.3)
    wall = M_BRICK
    ihx, ihy = hx - 14.0, hy - 14.0
    qh = FLOOR * 2.2 + 1.2
    # front block with portico on the forecourt side
    faces = fac_faces(bd, hx, hy)
    osp = [dict(u0=-6.0, u1=6.0, z0=CURB, z1=6.6)]
    faces["F"].wall(CURB, qh, osp, wall)
    archway(faces["F"], osp[0], wall, steps=5)
    bd.box(hx - 30.0, -hy + 2.0, CURB, hx, hy, qh, wall)
    bd.box(-hx, -hy + 2.0, CURB, -hx + 30.0, hy, qh, wall)
    for sx in (-1.0, 1.0):
        put(ctx, ("col", 6.6), lambda: k_column(6.6, 0.5), "KIT_Column_%02d" % (1 if sx < 0 else 2),
            f.cx, f.cy, f.rot, sx * 7.4, -hy + 1.0, CURB, kit=ctx.kit)
        for k in range(3):
            put(ctx, ("col", 6.6), lambda: k_column(6.6, 0.5), "KIT_PorticoCol_%02d" % (k + 1),
                f.cx, f.cy, f.rot, sx * (4.0 + k * 4.6), -hy + 1.0, CURB, kit=ctx.kit)
    put(ctx, ("col", 6.6), lambda: k_column(6.6, 0.5), "KIT_PorticoCol_C",
        f.cx, f.cy, f.rot, 0.0, -hy - 0.2, CURB, kit=ctx.kit)
    pediment_front(bd, -12.0, 12.0, CURB + 6.6, CURB + 9.6, -hy - 1.0, -hy + 6.0, M_CLASSIC)
    # inner quad: cross-axis blocks + arcade ring with open archways
    for (a0, b0, a1, b1) in ((-ihx, -ihy, ihx, -ihy + 10.0),
                             (-ihx, ihy - 10.0, ihx, ihy),
                             (-ihx, -ihy, -ihx + 10.0, ihy),
                             (ihx - 10.0, -ihy, ihx, ihy)):
        bd.box(a0, b0, CURB, a1, b1, qh, wall)
    for i in range(10):
        u = -ihx + 10.0 + i * ((2 * ihx - 20.0) / 9.0)
        bd.box(u - 0.35, -ihy + 9.65, CURB, u + 0.35, -ihy + 10.0, qh, wall)
        bd.box(u - 0.35, ihy - 10.0, CURB, u + 0.35, ihy - 9.65, qh, wall)
        bd.box(u - 0.35, -ihy + 9.65, qh, u + 0.35, -ihy, qh + 0.7, M_STONE)
        bd.box(u - 0.35, ihy - 10.0, qh, u + 0.35, ihy, qh + 0.7, M_STONE)
        for yy in (-ihy + 2.2, ihy - 3.2):
            put(ctx, ("col2", 4.6), lambda: k_column(4.6, 0.3), "KIT_ArcadeCol_%03d" % i,
                f.cx, f.cy, f.rot, u, yy, CURB, kit=ctx.kit)
    roof_deck(bd, hx, hy, qh)
    parapet_ring(bd, hx, hy, qh, wall)
    # bell tower over the front
    bd.box(-4.0, -hy - 2.0, CURB, 4.0, -hy + 13.0, qh + 9.0, wall)
    for sxx in (-1.0, 1.0):
        bd.box(sxx * 2.8 - 1.0, -hy + 3.6, qh + 1.0, sxx * 2.8 + 1.0, -hy + 6.6, qh + 8.0, M_GLASS)
    gable(bd, -5.0, 5.0, -hy + 2.0, -hy + 12.0, qh + 9.0, qh + 13.4, M_ROOFT, along="x")
    bd.box(-0.06, -hy - 2.4, qh + 13.4, 0.06, -hy + 3.0, qh + 16.4, M_STEEL)
    bd.box(-1.2, -hy - 2.55, qh + 15.4, 1.2, -hy - 2.25, qh + 15.7, M_STEEL)
    # QUAD: lawn, diagonal paths, benches, lamp columns
    bd.box(-ihx + 2.0, -ihy + 2.0, 0.06, ihx - 2.0, ihy - 2.0, 0.16, M_GRASS)
    q = 0.4
    bd.box(-1.6, -ihy + 2.0, 0.16, 1.6, ihy - 2.0, 0.22, M_WALK)
    bd.box(-ihx + 2.0, -1.6, 0.16, ihx - 2.0, 1.6, 0.22, M_WALK)
    bd.box(6.0, 6.0, CURB, 12.0, 12.0, qh + 7.0, wall)
    gable(bd, 5.0, 13.0, 5.0, 13.0, qh + 7.0, qh + 11.6, M_ROOFT, along="x")
    for k in range(8):
        put(ctx, ("lp",), lambda: k_lamppost(), "KIT_QuadLamp_%02d" % (k + 1),
            f.cx, f.cy, f.rot, 8.0 * (1 if k % 2 else -1), (k - 3.5) * 14.0, 0.0, kit=ctx.kit)
    for k in range(8):
        put(ctx, ("bench",), lambda: k_bench(), "KIT_QuadBench_%02d" % (k + 1),
            f.cx, f.cy, f.rot, 20.0 + (k % 4) * 14.0, (1 if k >= 4 else -1) * 10.0,
            0.0, kit=ctx.kit)
    _univ_room(ctx, f, wall)
    for k in range(2):
        put(ctx, ("plan",), lambda: k_planter(), "KIT_QuadPlanter_%02d" % (k + 1),
            f.cx, f.cy, f.rot, -28.0 + k * 56.0, 0.0, 0.0, kit=ctx.kit)
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def _univ_room(ctx, f, wall):
    ibd = Builder()
    fy = -f.hy + 12.0
    ibd.box(-10.0, fy, CURB, 10.0, fy + 10.0, CURB + 0.04, M_FLW)
    ibd.box(-10.0, fy, 3.1, 10.0, fy + 10.0, 3.2, M_CEIL)
    for sx in (-10.0, 9.75):
        ibd.box(sx, fy, CURB, sx + 0.25, fy + 10.0, 3.2, M_WALLP)
    ibd.box(-10.0, fy + 9.75, CURB, 10.0, fy + 10.0, 3.2, M_WALLP)
    put(ctx, ("desk",), lambda: k_desk(), "KIT_Desk_01",
        f.cx, f.cy, f.rot, -6.0, fy + 8.0, 0.0, kit=ctx.kit)
    put(ctx, ("shelf",), lambda: k_shelf(), "KIT_Shelf_01",
        f.cx, f.cy, f.rot, 8.0, fy + 2.5, 0.0, kit=ctx.kit)
    emit(ctx, f, ibd, "INT_%s_Foyer" % _cap(f.id), rot=f.rot)
    add_light(ctx, (f.cx, f.cy, 2.7), energy=90.0, radius=8.0)


def b_uni_faculty(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_ASPA)
    plinth(bd, hx, hy, M_STONE, 0.3)
    wall = M_BRICK
    qh = 2 * FLOOR + 1.2
    zt = f.floors * FLOOR
    # three blocks + two link bridges
    bw = 38.0
    for k, xx in enumerate((-1.0, 0.0, 1.0)):
        cx0 = xx * (hx - bw * 0.5 - 2.0)
        bd.box(cx0 - bw * 0.5, -hy + 4.0, CURB, cx0 + bw * 0.5, hy - 4.0, zt, wall)
        faces = dict(
            F=Face(bd, "y", -hy + 4.0, -hy + 4.0 + WALL_T, -1, cx0 - bw * 0.5, cx0 + bw * 0.5),
            B=Face(bd, "y", hy - 4.0 - WALL_T, hy - 4.0, 1, cx0 - bw * 0.5, cx0 + bw * 0.5))
        nf = int((bw - 4.0) / 5.0)
        for z0 in range(f.floors):
            zz = CURB + z0 * FLOOR
            ops = []
            for i in range(nf):
                u = cx0 - bw * 0.5 + 2.6 + i * 5.0
                ops.append(dict(u0=u, u1=u + 2.6, z0=zz + 1.0, z1=zz + 2.6))
            for fc in faces.values():
                fc.wall(zz, zz + FLOOR, ops if z0 > 0 else [], wall)
            for o in ops:
                faces["F"].rect(o["u0"], o["z0"], o["u1"], o["z1"], M_GLASS, 0.1, 0.18)
                faces["F"].rect(o["u0"] - 0.08, o["z0"] - 0.12, o["u1"] + 0.08, o["z0"],
                                M_STONE, -0.06, 0.07)
        bd.box(cx0 - bw * 0.5, -hy + 4.0, zt, cx0 + bw * 0.5, hy - 4.0, zt + 0.4, M_ROOF)
        for (px0, px1, py0, py1) in ((cx0 - bw * 0.5, cx0 + bw * 0.5, -hy + 4.0, -hy + 4.25),
                                     (cx0 - bw * 0.5, cx0 + bw * 0.5, hy - 4.25, hy - 4.0),
                                     (cx0 - bw * 0.5, cx0 - bw * 0.5 + 0.25, -hy + 4.0, hy - 4.0),
                                     (cx0 + bw * 0.5 - 0.25, cx0 + bw * 0.5, -hy + 4.0, hy - 4.0)):
            bd.box(px0, py0, zt, px1, py1, zt + 0.9, wall)
        put(ctx, ("rfac",), lambda: ent.p_roofac(), "KIT_RoofAC_%02d" % (k + 1),
            f.cx, f.cy, f.rot, cx0, hy - 9.0, zt + 0.4, kit=ctx.kit)
    for xx in (-(hx - bw * 0.5 - 2.0), (hx - bw * 0.5 - 2.0)):
        bd.box(xx - 5.0, -8.0, qh, xx + 5.0, 8.0, qh + 0.4, M_STEEL)
        bd.box(xx - 5.0, -8.0, qh + 0.4, xx + 5.0, -7.6, qh + 3.6, M_STEEL)
        bd.box(xx - 5.0, 7.6, qh + 0.4, xx + 5.0, 8.0, qh + 3.6, M_STEEL)
        for yy in (-7.0, 7.0):
            put(ctx, ("col2", 2.6), lambda: k_column(2.6, 0.25), "KIT_BridgeCol_%02d" % 1,
                f.cx, f.cy, f.rot, xx, yy, 0.0, kit=ctx.kit)
    _univ_room(ctx, f, wall)
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def b_embassy(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_ASPA)
    plinth(bd, hx, hy, M_STONE, 0.2)
    wall = M_PAVE  # compound walls use paving stone
    # perimeter wall with pillars + gate portal (NO gate door)
    wx, wy = hx - 3.0, hy - 3.0
    tcop = 2.4
    for (a0, b0, a1, b1) in ((-wx, -wy, wx, -wy + 0.35), (-wx, wy - 0.35, wx, wy),
                             (-wx, -wy, -wx + 0.35, wy), (wx - 0.35, -wy, wx, wy)):
        x0, y0, x1, y1 = min(a0, a1), min(b0, b1), max(a0, a1), max(b0, b1)
        gd = 7.0
        if a1 - a0 < 0.4:  # side walls: split around gate
            pass
        bd.box(x0, y0, 0.0, x1, y1, tcop, wall)
    # front wall gate split
    bd.box(-wx, -wy, 0.0, -5.0, -wy + 0.35, tcop, wall)
    bd.box(5.0, -wy, 0.0, wx, -wy + 0.35, tcop, wall)
    for k in range(int((wx - 5.0) / 8.0) + 1):
        x = -wx + k * 8.0
        bd.box(x - 0.3, -wy - 0.2, 0.0, x + 0.3, -wy + 0.55, tcop + 0.5, M_STONE)
        bd.box(x - 0.3, wy - 0.55, 0.0, x + 0.3, wy + 0.2, tcop + 0.5, M_STONE)
    for sx in (-5.4, 5.4):
        bd.box(sx - 0.4, -wy - 0.4, 0.0, sx + 0.4, -wy + 0.75, tcop + 0.9, M_STONE)
    bd.box(-5.4, -wy - 0.4, tcop + 0.9, 5.4, -wy + 0.75, tcop + 1.15, M_STEEL)
    # gatehouse wings + flag plaza
    bd.box(-9.0, -wy + 1.0, 0.0, -4.0, -wy + 9.0, 3.2, M_BONE)
    bd.box(4.0, -wy + 1.0, 0.0, 9.0, -wy + 9.0, 3.2, M_BONE)
    bd.box(-9.0, -wy + 1.0, 3.2, -4.0, -wy + 9.0, 3.5, M_STEEL)
    bd.box(4.0, -wy + 1.0, 3.2, 9.0, -wy + 9.0, 3.5, M_STEEL)
    put(ctx, ("flag", 14.0), lambda: k_flag(14.0), "KIT_Flagpole_01",
        f.cx, f.cy, f.rot, 0.0, -wy + 12.0, 0.0, kit=ctx.kit)
    # chancery block rear + drive
    zt = f.floors * FLOOR + 1.2
    bd.box(-hx + 12.0, hy - 40.0, CURB, hx - 12.0, hy - 6.0, zt, M_BONE)
    chF = Face(bd, "y", hy - 40.0, hy - 40.0 + WALL_T, -1, -hx + 12.0, hx - 12.0)
    ops = []
    nf = int((2 * (hx - 24.0)) / 5.0)
    for z0 in range(f.floors):
        zz = CURB + z0 * FLOOR
        ops = []
        for i in range(nf):
            u = -hx + 14.5 + i * 5.0
            ops.append(dict(u0=u, u1=u + 3.0, z0=zz + 1.0, z1=zz + 2.5))
        chF.wall(zz, zz + FLOOR, ops, M_BONE)
        for o in ops:
            chF.rect(o["u0"], o["z0"], o["u1"], o["z1"], M_GLASS, 0.1, 0.18)
            chF.rect(o["u0"] - 0.08, o["z0"] - 0.12, o["u1"] + 0.08, o["z0"], M_STONE, -0.05, 0.06)
    bd.box(-hx + 12.0, hy - 40.0, zt, hx - 12.0, hy - 6.0, zt + 0.4, M_ROOF)
    for (a0, b0, a1, b1) in ((-hx + 12.0, hy - 40.0, hx - 12.0, hy - 39.75),
                             (-hx + 12.0, hy - 6.25, hx - 12.0, hy - 6.0),
                             (-hx + 12.0, hy - 40.0, -hx + 12.25, hy - 6.0),
                             (hx - 12.25, hy - 40.0, hx - 12.0, hy - 6.0)):
        bd.box(a0, b0, zt, a1, b1, zt + 0.9, M_BONE)
    bd.box(-6.0, -wy + 2.0, 0.05, 6.0, hy - 40.0, 0.14, M_WALK)
    for i in range(4):
        put(ctx, ("plan",), lambda: k_planter(), "KIT_GardenPlanter_%02d" % (i + 1),
            f.cx, f.cy, f.rot, (-1.0 if i < 2 else 1.0) * 18.0,
            -30.0 + (i % 2) * 22.0, 0.0, kit=ctx.kit)
    if f.tier <= 2 and f.enterable:
        _tier1_lobby(ctx, f, -hx + 11.5, -hx + 30.0, hy - 39.0, hy - 26.0,
                     floor=M_MARBLE, desks=[0.0], benches=2)
    add_light(ctx, (f.cx, f.cy + 10.0, 2.7), energy=70.0, radius=8.0)
    # wall colliders handled via footprint box
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def b_mosque(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_PAVE)
    plinth(bd, hx, hy, M_STONE, 0.3)
    wall = M_BONE
    # prayer hall (rear) with drum + dome
    hall_y0 = hy * 0.02
    bd.box(-30.0, hall_y0, CURB, 30.0, hy - 3.0, top, wall)
    for zz in range(1, max(2, f.floors)):
        z = CURB + (zz - 1) * FLOOR
        punched(Face(bd, "x", -30.0, -30.0 + WALL_T, -1, hall_y0, hy - 3.0), z, wall)
        punched(Face(bd, "x", 30.0 - WALL_T, 30.0, 1, hall_y0, hy - 3.0), z, wall)
    bd.box(-30.0, hall_y0, top - 0.05, 30.0, hy - 3.0, top + 0.04, M_ROOF)
    for (ex0, ey0, ex1, ey1) in ((-30.0, hall_y0, 30.0, hall_y0 + 0.3),
                                 (-30.0, hy - 3.3, 30.0, hy - 3.0),
                                 (-30.0, hall_y0, -29.7, hy - 3.0),
                                 (29.7, hall_y0, 30.0, hy - 3.0)):
        bd.box(ex0, ey0, top, ex1, ey1, top + 0.9, wall)
    dome(bd, 0.0, (hall_y0 + hy - 3.0) * 0.5, top, 12.5, 5.4, M_TEAL, seg=20, rings=6)
    bd.cyl(0.0, (hall_y0 + hy - 3.0) * 0.5, top + 4.9, top + 6.1, 0.09, M_CHROME, seg=8)
    bd.cyl(0.0, (hall_y0 + hy - 3.0) * 0.5, top + 5.4, top + 5.95, 0.5, M_CHROME, seg=8)
    # front arcade courtyard with arches + fountain
    fa_y1 = hall_y0 + 1.6
    arcade_y = -hy + 2.0
    # side arcades: covered walk from the front gate to the prayer hall
    bd.box(-30.0, arcade_y, CURB, -28.0, fa_y1, CURB + 4.4, wall)
    bd.box(28.0, arcade_y, CURB, 30.0, fa_y1, CURB + 4.4, wall)
    n = 6
    for i in range(n):
        u = -30.0 + i * (60.0 / n)
        bd.box(u - 0.4, arcade_y, CURB, u + 0.4, arcade_y + 0.8, CURB + 4.4, wall)
        put(ctx, ("arc", i), lambda: k_column(4.2, 0.32), "KIT_ArcadeCol_%02d" % (i + 1),
            f.cx, f.cy, f.rot, u + 5.0, arcade_y + 0.4, CURB, kit=ctx.kit)
    bd.box(-30.4, arcade_y - 0.4, CURB + 4.4, 30.4, arcade_y + 0.8, CURB + 5.0, M_STONE)
    bd.cyl(0.0, arcade_y + 5.0, CURB, CURB + 0.6, 3.0, M_TEAL, seg=12)
    bd.cyl(0.0, arcade_y + 5.0, CURB + 0.6, CURB + 1.4, 0.8, M_STONE, seg=12)
    bd.cyl(0.0, arcade_y + 5.0, CURB + 1.4, CURB + 1.5, 2.4, M_TEAL, seg=12)
    # minaret (with balcony) at the front-right of the courtyard
    mx, my = 26.0, arcade_y + 9.0
    bd.box(mx - 2.2, my - 2.2, 0.0, mx + 2.2, my + 2.2, 8.0, wall)
    bd.cyl(mx, my, 8.0, 22.0, 1.7, wall, seg=10)
    bd.cyl(mx, my, 14.0, 15.2, 2.6, wall, seg=10)
    loft_ring(bd, ring_pts(mx, my, 2.6, 10), ring_pts(mx, my, 1.4, 10), 15.2, 15.7, M_STONE)
    bd.cyl(mx, my, 22.0, 24.6, 1.3, M_TEAL, seg=10)
    dome(bd, mx, my, 24.6, 1.3, 1.6, M_TEAL, seg=10)
    bd.cyl(mx, my, 26.1, 26.7, 0.07, M_CHROME, seg=6)
    put(ctx, ("lamp",), lambda: ent.p_lamp(), "KIT_WallLamp_01",
        f.cx, f.cy, f.rot, 0.0, arcade_y, 3.2, coll=ctx.lights, kit=ctx.kit)
    if f.tier <= 2 and f.enterable:
        ibd = Builder()
        ibd.box(-29.0, hall_y0 + 0.5, CURB, 29.0, hall_y0 + 14.0, CURB + 0.04, M_FLW)
        ibd.box(-29.0, hall_y0 + 14.0, CURB, 29.0, hall_y0 + 14.3, 2.8, M_TEAL)
        for i in range(3):
            put(ctx, ("pbox",), lambda: k_planter(), "KIT_NichePlant_%02d" % (i + 1),
                f.cx, f.cy, f.rot, -16.0 + i * 16.0, hall_y0 + 3.0, 0.0, kit=ctx.kit)
        emit(ctx, f, ibd, "INT_%s_PrayerHall" % _cap(f.id), rot=f.rot)
        add_light(ctx, (f.cx, f.cy - 4.0, 2.6), energy=80.0, radius=8.0)
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def b_church(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_PAVE)
    plinth(bd, hx, hy, M_STONE, 0.3)
    wall = M_STONE
    nave_y0 = -hy + 16.0
    zt = top
    bd.box(-14.0, nave_y0, CURB, 14.0, hy - 4.0, zt, wall)
    gable(bd, -15.0, 15.0, nave_y0 - 1.2, hy - 2.8, zt, zt + 6.0, M_ROOFT, along="y")
    # buttresses
    for k in range(4):
        yy = nave_y0 + 4.0 + k * ((hy - 8.0 - nave_y0) / 3.0)
        for sx in (-1.0, 1.0):
            bd.box(sx * 14.0, yy, CURB, sx * 15.6, yy + 1.4, zt - 1.4, wall)
            bd.box(sx * 14.6, yy + 1.4, zt - 2.6, sx * 15.6, yy + 2.0, zt - 1.4, wall)
    # tower + belfry + spire + cross
    bd.box(-4.5, nave_y0 - 12.0, CURB, 4.5, nave_y0, zt + 7.0, wall)
    for sx in (-1.0, 1.0):
        bd.box(sx * 2.6 - 0.9, nave_y0 - 10.4, zt + 1.6, sx * 2.6 + 0.9, nave_y0 - 4.4,
               zt + 6.6, M_GLASSH)
    bd.box(-5.4, nave_y0 - 12.9, zt + 7.0, 5.4, nave_y0 + 0.9, zt + 7.6, wall)
    pyramid(bd, 0.0, nave_y0 - 6.0, zt + 7.6, 5.4, 6.6, 8.4, M_ROOFT)
    bd.box(-0.09, nave_y0 - 6.6, zt + 16.0, 0.09, nave_y0 - 5.4, zt + 18.6, M_CHROME)
    bd.box(-1.0, nave_y0 - 5.9, zt + 17.4, 1.0, nave_y0 - 5.6, zt + 17.7, M_CHROME)
    # archways into the nave + rose window
    for sx in (-1.0, 1.0):
        pass
    ops = [dict(u0=-3.4, u1=3.4, z0=CURB, z1=4.4)]
    Face(bd, "y", nave_y0 - 12.0, nave_y0 - 12.0 + WALL_T, -1, -4.5, 4.5).wall(
        CURB, zt + 6.8, ops + [dict(u0=-2.2, u1=2.2, z0=zt + 1.6, z1=zt + 6.0)], wall)
    rf = Face(bd, "y", nave_y0 - 12.0, nave_y0 - 12.0 + WALL_T, -1, -4.5, 4.5)
    rf.rect(-2.2, zt + 1.6, 2.2, zt + 6.0, M_GLASSH, 0.12, 0.2)
    rf.wall(CURB, zt + 6.8, ops, wall)
    archway(rf, ops[0], wall)
    if f.tier <= 2 and f.enterable:
        ibd = Builder()
        ibd.box(-13.0, nave_y0 + 0.5, CURB, 13.0, nave_y0 + 18.0, CURB + 0.04, M_FLT)
        ibd.box(-13.0, nave_y0 + 0.5, 3.4, 13.0, nave_y0 + 18.0, 3.6, M_CEIL)
        put(ctx, ("bench",), lambda: k_bench(2.6), "KIT_Pew_01",
            f.cx, f.cy, f.rot, 0.0, nave_y0 + 4.0, 0.0, kit=ctx.kit)
        for r in range(3):
            put(ctx, ("bench",), lambda: k_bench(2.6), "KIT_Pew_%02d" % (r + 2),
                f.cx, f.cy, f.rot, -6.0 + r * 6.0 if False else (-6.0 if r % 2 else 6.0),
                nave_y0 + 8.0 + r * 3.4, 0.0, kit=ctx.kit)
        emit(ctx, f, ibd, "INT_%s_Nave" % _cap(f.id), rot=f.rot)
        add_light(ctx, (f.cx, f.cy - 6.0, 2.6), energy=70.0, radius=8.0)
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def b_temple(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_PAVE)
    plinth(bd, hx, hy, M_STONE, 0.3)
    z = CURB
    w = min(hx, 16.0)
    for k in range(5):
        s = w * (1.0 - k * 0.22)
        bd.box(-s, -6.0, z, s, 8.0, z + 2.4, M_BONE if k % 2 == 0 else M_CONC2)
        z += 2.4
    pyramid(bd, 0.0, 1.0, z, w * 0.78, 7.0, 3.6, M_TEAL)
    bd.box(0.4, -8.0, CURB, w * 0.6, -6.0, z, M_MUST)
    # gate pillars
    for sx in (-1.0, 1.0):
        bd.box(sx * 10.0 - 0.6, -hy + 2.0, CURB, sx * 10.0 + 0.6, -hy + 3.2, 5.2, M_OXB)
    bd.box(-11.6, -hy + 1.6, 5.2, 11.6, -hy + 3.4, 5.8, M_OXB)
    put(ctx, ("bol",), lambda: k_bollard(), "KIT_Bollard_01",
        f.cx, f.cy, f.rot, 0.0, -hy + 6.0, 0.0, kit=ctx.kit)
    if f.tier <= 2 and f.enterable:
        _tier1_lobby(ctx, f, -w + 1.0, w - 1.0, -hy + 12.0, -hy + 22.0,
                     floor=M_FLW, desks=[0.0], benches=1)
    add_light(ctx, (f.cx, f.cy, 2.6), energy=60.0, radius=6.0)
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def b_gurudwara(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_PAVE)
    plinth(bd, hx, hy, M_STONE, 0.3)
    wall = M_BONE
    bd.box(-18.0, -hy + 3.0, CURB, 18.0, hy - 3.0, top, wall)
    ops = [dict(u0=-4.0, u1=4.0, z0=CURB, z1=3.6)]
    Face(bd, "y", -hy + 3.0, -hy + 3.0 + WALL_T, -1, -18.0, 18.0).wall(CURB, top, ops, wall)
    archway(Face(bd, "y", -hy + 3.0, -hy + 3.0 + WALL_T, -1, -18.0, 18.0), ops[0], wall)
    dome(bd, 0.0, 0.0, top, 9.0, 6.5, M_TEAL, seg=16, rings=6, bulge=0.55)
    bd.cyl(0.0, 0.0, top + 12.0, top + 14.6, 0.08, M_CHROME, seg=8)
    bd.box(0.0, 0.06, top + 13.0, 2.8, 0.14, top + 13.9, M_OXB)
    for sx in (-1.0, 1.0):
        bd.box(sx * 17.0 - 2.0, -hy + 5.0, CURB, sx * 17.0 + 2.0, -hy + 9.0, top + 1.4, wall)
        dome(bd, sx * 17.0, -hy + 7.0, top + 1.4, 2.0, 1.8, M_TEAL, seg=10, bulge=0.4)
    if f.tier <= 2 and f.enterable:
        _tier1_lobby(ctx, f, -17.0, 17.0, -hy + 4.0, -hy + 16.0,
                     floor=M_FLW, desks=[0.0], benches=3)
    add_light(ctx, (f.cx, f.cy, 2.6), energy=70.0, radius=7.0)
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def b_crematorium(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_GRAVEL)
    # chapel (rear-left) with open porch
    cx0, cy0 = -hx + 6.0, hy - 44.0
    bd.box(cx0, cy0, CURB, cx0 + 26.0, cy0 + 24.0, 6.0, M_BONE)
    gable(bd, cx0 - 0.6, cx0 + 26.6, cy0 - 1.2, cy0 + 25.2, 6.0, 10.4, M_ROOFT, along="x")
    for k in range(4):
        put(ctx, ("col", 4.2), lambda: k_column(4.2, 0.28), "KIT_PorchCol_%02d" % (k + 1),
            f.cx, f.cy, f.rot, cx0 + 3.0 + k * 6.6, cy0 - 4.5, CURB, kit=ctx.kit)
    bd.box(cx0 - 1.0, cy0 - 5.5, CURB, cx0 + 27.0, cy0 - 4.5, 0.35, M_STONE)
    # ovens hall (rear-right) + chimney
    ox0 = 4.0
    bd.box(ox0, hy - 34.0, CURB, ox0 + 42.0, hy - 6.0, 7.5, M_BRICKB)
    gable(bd, ox0 - 0.6, ox0 + 42.6, hy - 35.2, hy - 4.8, 7.5, 11.2, M_ROOFM, along="y")
    bd.cyl(ox0 + 34.0, hy - 20.0, 11.2, 26.0, 1.5, M_BRICK, seg=12)
    bd.cyl(ox0 + 34.0, hy - 20.0, 25.0, 26.4, 2.0, M_CONC2, seg=12)
    bd.box(0.0, -hy + 4.0, 0.0, 30.0, -hy + 26.0, 4.6, M_BRICKB)
    gable(bd, -0.6, 30.6, -hy + 2.8, -hy + 27.2, 4.6, 8.0, M_ROOFT, along="x")
    for k in range(24):
        put(ctx, ("cyp",), lambda: k_bollard(), "KIT_GraveLamp_%02d" % (k + 1),
            f.cx, f.cy, f.rot, (k % 12) * 11.0 - 55.0, -24.0 if k < 12 else 22.0,
            0.0, kit=ctx.kit)
    for k in range(6):
        bd.box(-hx + 6.0 + k * 20.0, -hy + 1.0, 0.05, -hx + 20.0 + k * 20.0, hy - 52.0, 0.1,
               M_ASPA)
    if f.tier <= 2 and f.enterable:
        _tier1_lobby(ctx, f, cx0 + 1.0, cx0 + 25.0, cy0 - 3.5, cy0 + 10.0,
                     floor=M_FLW, desks=[0.0], benches=2)
    add_light(ctx, (f.cx, f.cy, 2.6), energy=50.0, radius=6.0)
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def b_emergency(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_ASPA)
    plinth(bd, hx, hy, M_STONE, 0.3)
    wall = M_MODE
    faces = fac_faces(bd, hx, hy)
    ply = top
    fake_facade(bd, hx, hy, CURB, ply - 0.8, wall, M_GLASSH, cols=10, rows=max(1, f.floors))
    roof_deck(bd, hx, hy, ply)
    parapet_ring(bd, hx, hy, ply, wall, t=0.35)
    put(ctx, ("mast", 18.0), lambda: k_mast(18.0), "KIT_AntennaMast_01",
        f.cx, f.cy, f.rot, -hx + 8.0, hy - 8.0, ply, kit=ctx.kit)
    bd.cyl(hx - 8.0, hy - 8.0, ply, ply + 0.6, 3.4, M_PANEL, seg=12)
    dome(bd, hx - 8.0, hy - 8.0, ply + 0.6, 3.4, 2.0, M_PANEL, seg=12)
    for k in range(3):
        bd.box(-hx + 22.0, hy - 12.0 + k * 4.0, ply, -hx + 40.0, hy - 10.0 + k * 4.0,
               ply + 2.6, M_STEEL)
        bd.cyl(-hx + 23.0, hy - 13.0 + k * 4.0, ply + 2.6, ply + 3.4, 0.12, M_RUST, seg=6)
    bd.box(-hx + 6.0, -hy - 10.0, 0.06, hx - 6.0, -hy - 2.0, 0.1, M_ASPA)
    for k in range(4):
        bd.box(-18.0 + k * 10.0, -hy - 7.6, 0.1, -12.0 + k * 10.0, -hy - 2.4, 0.14, M_MARKW)
    for k, mat in enumerate([M_EMITC, M_EMITW]):
        bd.box(-hx + 3.0, -hy - 0.12, 1.6 + k * 0.9, hx - 3.0, -hy + 0.02, 2.0 + k * 0.9, mat)
    if f.tier <= 2 and f.enterable:
        _tier1_lobby(ctx, f, -hx + 0.6, 0.0, -hy + 0.5, -hy + 12.0, floor=M_FLW,
                     desks=[-4.0], benches=2)
    add_light(ctx, (f.cx, f.cy, 2.7), energy=70.0, radius=7.0, color=(0.8, 0.88, 1.0))
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def b_gym(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_ASPA)
    plinth(bd, hx, hy, M_STONE, 0.3)
    wall = M_MODE
    faces = fac_faces(bd, hx, hy)
    # missing-glass frontage: huge opening with glass grid
    ops = [dict(u0=-hx + 2.0, u1=hx - 2.0, z0=CURB, z1=4.4)]
    faces["F"].wall(CURB, top, ops, wall)
    glass_curtain(faces["F"], CURB, 4.4, M_GLASSC, M_CHAR)
    for eff in ("L", "R", "B"):
        faces[eff].wall(CURB, top, [], wall)
    roof_deck(bd, hx, hy, top)
    parapet_ring(bd, hx, hy, top, wall)
    put(ctx, ("led",), lambda: ent.p_led(8.0, 1.6), "KIT_LEDPanel_01",
        f.cx, f.cy, f.rot, 0.0, -hy, 5.0, kit=ctx.kit)
    if f.tier <= 2 and f.enterable:
        _tier1_lobby(ctx, f, -hx + 0.5, hx - 0.5, -hy + 0.5, -hy + 12.0,
                     floor=M_FLT, desks=[-3.0], benches=2)
        bd2 = Builder()
        for i in range(6):
            x = -hx + 3.0 + (i % 3) * 8.0
            y = -hy + 14.0 + (i // 3) * 6.0
            bd2.box(x - 0.9, y - 0.7, 0.0, x + 0.9, y + 0.7, 0.35, M_DARK)
            bd2.box(x - 0.8, y + 0.5, 0.35, x + 0.8, y + 0.7, 1.5, M_STEEL)
        bd2.box(-hx + 1.0, hy - 3.4, 1.0, hx - 1.0, hy - 3.3, 2.9, M_MIRROR)
        ibd = Builder()
        ibd.box(-hx + 0.7, -hy + 11.0, CURB, hx - 0.7, hy - 0.7, CURB + 0.03, M_FLT)
        remap = ibd.midx(M_DARK)
        remap2 = ibd.midx(M_STEEL)
        remap3 = ibd.midx(M_MIRROR)
        remapd = {0: remap, 1: remap2, 2: remap3}
        ibd.v.extend(bd2.v)
        ibd.f.extend(bd2.f)
        ibd.mi.extend([remapd.get(m, remap) for m in bd2.mi])
        emit(ctx, f, ibd, "INT_%s_GymFloor" % _cap(f.id), rot=f.rot)
    add_light(ctx, (f.cx, f.cy, 3.2), energy=110.0, radius=10.0)
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def b_velodrome(ctx, f):
    """SPT_VELODROME: clear-span barrel vault + banked timber loop."""
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_ASPA)
    wall = M_PANEL
    # outer wall ring on the perimeter, ends glazed
    zwall = 7.5
    for sx in (-1.0, 1.0):
        x0 = sx * hx - sx * WALL_T
        x1 = sx * hx
        fc = Face(bd, "x", min(x0, x1), max(x0, x1), sx, -hy + 2.0, hy - 2.0)
        ops = [dict(u0=fc.u0 + 4.0, u1=fc.u0 + fc.length - 4.0, z0=CURB, z1=5.6)]
        fc.wall(CURB, zwall, ops, wall)
        glass_curtain(fc, CURB, 5.6, M_GLASSC, M_CHAR)
    for (a0, b0, a1, b1) in ((-hx + WALL_T, -hy, hx - WALL_T, -hy + WALL_T),
                             (-hx + WALL_T, hy - WALL_T, hx - WALL_T, hy),
                             ):
        bd.box(a0, b0, CURB, a1, b1, zwall, wall)
    # barrel vault roof
    barrel(bd, -hx, hx, -hy, hy, zwall, top - zwall, M_ROOFM, seg=16, along="y")
    # infield + apron
    bd.box(-hx + 2.0, -hy + 6.0, 0.05, hx - 2.0, hy - 6.0, 0.2, M_GRASS)
    bd.box(-hx + 6.0, -hy + 14.0, 0.05, hx - 6.0, hy - 14.0, 0.2, M_WALK)
    # banked timber loop (oval with rounded ends)
    import math as _m
    cxv, cyv = 0.0, 0.0
    rx, ry = hx - 14.0, hy - 18.0
    path = []
    n = 20
    for k in range(n):
        t = 2 * math.pi * k / n
        # superellipse-ish oval
        px = cxv + rx * math.cos(t)
        py = cyv + ry * math.sin(t)
        if abs(math.cos(t)) > 0.86 or abs(math.sin(t)) > 0.995:
            pass
        path.append((px, py, t))
    w, rise = 9.0, 3.0
    for k in range(n):
        px, py, t = path[k]
        qx, qy, t2 = path[(k + 1) % n]
        nxv, nyv = math.sin(t), -math.cos(t)
        ax, ay = px + nxv * w * 0.5, py + nyv * w * 0.5
        bx, by = px - nxv * w * 0.5, py - nyv * w * 0.5
        qx2, qy2 = qx + math.sin(t2) * w * 0.5, qy - math.cos(t2) * w * 0.5
        rx2, ry2 = qx - math.sin(t2) * w * 0.5, qy - math.cos(t2) * w * 0.5
        bd.poly([(ax, ay, 0.35), (bx, by, 0.35 + rise), (rx2, ry2, 0.35 + rise),
                 (qx2, qy2, 0.35)], M_WPLANW)
    # spectator stands (straight) + start house
    for sy in (-1.0, 1.0):
        bd.box(-22.0, sy * (ry - 6.0), 0.35, 22.0, sy * ry + sy * 4.0, 5.2, M_CONC)
    bd.box(6.0, -hy + 4.0, 0.06, 18.0, -hy + 10.0, 4.4, M_WPLAN)
    if f.tier <= 2 and f.enterable:
        ibd = Builder()
        ibd.box(-12.0, -hy + 10.5, CURB, 12.0, -hy + 22.0, CURB + 0.04, M_CONC2)
        put(ctx, ("desk",), lambda: k_desk(), "KIT_Desk_01",
            f.cx, f.cy, f.rot, 0.0, -hy + 12.0, 0.0, kit=ctx.kit)
        for i in range(3):
            put(ctx, ("bench",), lambda: k_bench(), "KIT_Bench_%02d" % (i + 1),
                f.cx, f.cy, f.rot, -6.0 + i * 6.0, -hy + 16.0, 0.0, kit=ctx.kit)
        emit(ctx, f, ibd, "INT_%s_Concourse" % _cap(f.id), rot=f.rot)
    add_light(ctx, (f.cx, f.cy, 9.0), energy=140.0, radius=12.0)
    collider(ctx, f, h=zwall + (top - zwall) * 0.35, inset=0.5)
    _budget_note(ctx, f)
    return bd


def b_tennis(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_GRASS)
    # clubhouse
    bd.box(-hx + 6.0, -hy + 4.0, CURB, -hx + 6.0 + 34.0, -hy + 26.0, 6.4, M_CONC2)
    for z0 in range(2):
        z = CURB + z0 * FLOOR
        for side, (axis, d0, d1, out, u0, u1) in (
                ("F", ("y", -hy + 4.0, -hy + 4.0 + WALL_T, -1, -hx + 6.0, -hx + 40.0)),
                ("L", ("x", -hx + 6.0, -hx + 6.0 + WALL_T, -1, -hy + 4.0, -hy + 26.0))):
            fc = Face(bd, axis, d0, d1, out, u0, u1)
            if z0 == 0 and side == "F":
                ops = [dict(u0=-6.0, u1=6.0, z0=z, z1=z + 3.0)]
                fc.wall(z, z + FLOOR, ops, M_CONC2)
                archway(fc, ops[0], M_CONC2)
            else:
                ribbon_band(fc, z, M_CONC2)
    roof_deck(bd, 0.0, 0.0, 0.0, M_CONC2) if False else None
    bd.box(-hx + 6.0, -hy + 4.0, 6.4, -hx + 40.0, -hy + 26.0, 6.8, M_ROOF)
    # courts grid
    for k in range(8):
        cxx = hx - 8.0 - (k % 2) * 32.0
        cyy = -hy + 40.0 + (k // 2) * 34.0
        bd.box(cxx - 14.0, cyy - 16.0, 0.05, cxx + 14.0, cyy + 16.0, 0.12, M_TRACK)
        for ln in range(1, 4):
            bd.box(cxx - 12.0, cyy - 16.0 + ln * 8.0, 0.12, cxx + 12.0,
                   cyy - 16.0 + ln * 8.0 + 0.1, 0.15, M_MARKW)
        for sx in (-1.0, 1.0):
            bd.box(cxx + sx * 12.6 - 0.06, cyy - 0.06, 0.12, cxx + sx * 12.6 + 0.06,
                   cyy + 0.06, 1.1, M_STEEL)
        bd.box(cxx - 12.66, cyy - 0.04, 0.92, cxx + 12.66, cyy + 0.04, 1.0, M_CANVAS)
        bd.box(cxx - 0.04, cyy - 0.9, 0.12, cxx + 0.04, cyy + 0.9, 1.0, M_CANVAS)
    for k in range(4):
        put(ctx, ("fl",), lambda: k_flood(), "KIT_Floodlight_%02d" % (k + 1),
            f.cx, f.cy, f.rot, (23.0 if k % 2 else -23.0) * 0.75 + (hx - 16.0),
            -hy + 46.0 + (k // 2) * 60.0, 0.0, kit=ctx.kit)
    # covered courts: steel canopy over 2 courts
    bd.box(hx - 46.0, -hy + 40.0, 4.6, hx - 14.0, -hy + 40.6, 5.0, M_STEEL)
    bd.poly([(hx - 46.0, -hy + 40.0, 5.0), (hx - 46.0, -hy + 74.0, 6.6),
             (hx - 14.0, -hy + 74.0, 6.6), (hx - 14.0, -hy + 40.0, 5.0)], M_ROOFM)
    if f.tier <= 2 and f.enterable:
        _tier1_lobby(ctx, f, -hx + 7.0, -hx + 39.0, -hy + 5.0, -hy + 20.0,
                     floor=M_FLT, desks=[0.0], benches=2)
    add_light(ctx, (f.cx, f.cy, 3.0), energy=80.0, radius=9.0)
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def b_motocross(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_DIRT)
    bd.box(-hx + 2.0, -hy + 2.0, 0.0, hx - 2.0, hy - 2.0, 0.06, M_DIRT)
    # dirt loop: ring of mounds with 6 jump pairs
    n_m = 14
    for k in range(n_m):
        t = 2 * math.pi * k / n_m
        r = min(hx, hy) * 0.62
        mx = r * math.cos(t)
        my = r * math.sin(t) * 0.72
        hh = 1.6 + (k % 3) * 0.8
        bd.cyl(mx, my, 0.0, hh, 5.5 if k % 3 else 7.5, M_DIRT, seg=9)
        if k % 3 == 0:
            bd.box(mx - 7.0, my - 1.1, hh, mx + 7.0, my + 1.1, hh + 0.7, M_DIRT)
    # spectator bank + timing hut + start gate
    for sy in (-1.0, 1.0):
        bd.poly([(-40.0, sy * (hy - 10.0), 0.0), (40.0, sy * (hy - 10.0), 0.0),
                 (34.0, sy * (hy - 22.0), 3.4), (-34.0, sy * (hy - 22.0), 3.4)],
                M_GRASS)
    bd.box(hx - 26.0, -hy + 8.0, CURB, hx - 12.0, -hy + 16.0, 3.6, M_PANEL)
    gable(bd, hx - 26.6, hx - 11.4, -hy + 6.8, -hy + 17.2, 3.6, 5.6, M_ROOFM, along="x")
    bd.box(-12.0, -hy + 8.0, 0.0, 12.0, -hy + 11.4, 1.1, M_STEEL)
    put(ctx, ("flag", 9.0), lambda: k_flag(9.0), "KIT_Flagpole_01",
        f.cx, f.cy, f.rot, 0.0, -hy + 18.0, 0.0, kit=ctx.kit)
    for k in range(6):
        put(ctx, ("lp",), lambda: k_lamppost(), "KIT_TrackLamp_%02d" % (k + 1),
            f.cx, f.cy, f.rot, -60.0 + k * 24.0, (0.62 * min(hx, hy) + 4.0) *
            (1 if k % 2 else -1), 0.0, kit=ctx.kit)
    collider(ctx, f, h=3.6, inset=4.0)
    _budget_note(ctx, f)
    return bd


def b_archery(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_GRASS)
    # 18 covered lanes: long shed
    lanes = 18
    shed_w = 3.4
    y0 = -hy + 12.0
    y1 = -hy + 12.0 + 70.0
    x0 = -hx + 8.0
    bd.box(x0, y0, CURB, x0 + lanes * shed_w, y0 + 1.2, 3.0, M_WPLAN)
    for k in range(lanes + 1):
        x = x0 + k * shed_w
        bd.box(x - 0.08, y0, CURB, x + 0.08, y1, 3.0, M_WPLAN)
    bd.poly([(x0 - 1.0, y0, 3.0), (x0 + lanes * shed_w + 1.0, y0, 3.0),
             (x0 + lanes * shed_w + 1.0, y1 + 4.0, 4.6), (x0 - 1.0, y1 + 4.0, 4.6)],
            M_ROOFM)
    bd.box(x0 - 1.0, y0, 3.0, x0, y1, 3.0, M_WPLAN)
    bd.box(x0 + lanes * shed_w, y0, 3.0, x0 + lanes * shed_w + 1.0, y1, 3.0, M_WPLAN)
    # target butts wall + safety berm
    bd.box(x0, y1 + 2.0, 0.0, x0 + lanes * shed_w, y1 + 4.6, 3.2, M_DIRT)
    for k in range(lanes):
        bd.box(x0 + k * shed_w + 0.9, y1 + 3.2, 0.0, x0 + k * shed_w + 2.5, y1 + 3.9,
               1.3, M_CANVAS)
        bd.poly([], M_CONC) if False else None
    bd.poly([(x0 + lanes * shed_w + 4.6, y0 - 6.0, 0.0),
             (x0 + lanes * shed_w + 4.6, y1 + 10.0, 0.0),
             (x0 + lanes * shed_w + 26.0, y1 + 10.0, 5.2),
             (x0 + lanes * shed_w + 26.0, y0 - 6.0, 5.2)], M_GRASS)
    # clubhouse
    bd.box(x0, y1 + 12.0, CURB, x0 + 18.0, y1 + 24.0, 5.0, M_CONC2)
    gable(bd, x0 - 0.6, x0 + 18.6, y1 + 10.8, y1 + 25.2, 5.0, 7.8, M_ROOFM, along="y")
    if f.tier <= 2 and f.enterable:
        _tier1_lobby(ctx, f, x0 + 1.0, x0 + 17.0, y1 + 12.5, y1 + 23.0,
                     floor=M_FLW, desks=[0.0], benches=2)
    add_light(ctx, (f.cx, f.cy, 3.0), energy=60.0, radius=8.0)
    collider(ctx, f, h=5.0, inset=6.0)
    _budget_note(ctx, f)
    return bd


def _field_common(ctx, f, pitch="football"):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_GRASS)
    bd.box(-hx, -hy, 0.0, hx, hy, 0.05, M_GRASS)
    bd.box(-hx + 4.0, -hy + 4.0, 0.05, hx - 4.0, hy - 4.0, 0.08, GRASS_DARK if False else M_ASPA if False else M_ASPA)
    if pitch == "football":
        bd.box(-hx + 6.0, -hy + 10.0, 0.08, hx - 6.0, hy - 10.0, 0.12, M_GRASS)
        bd.box(-hx + 7.0, -hy + 11.0, 0.12, hx - 7.0, -hy + 11.4, 0.15, M_MARKW)
        bd.box(-hx + 7.0, hy - 11.4, 0.12, hx - 7.0, hy - 11.0, 0.15, M_MARKW)
        bd.box(-11.5, -hy + 11.0, 0.12, -11.1, hy - 11.0, 0.15, M_MARKW)
        bd.box(11.1, -hy + 11.0, 0.12, 11.5, hy - 11.0, 0.15, M_MARKW)
        put(ctx, ("goal",), lambda: k_goal(), "KIT_Goal_N",
            f.cx, f.cy, f.rot, 0.0, -hy + 11.0, 0.16, kit=ctx.kit)
        put(ctx, ("goal",), lambda: k_goal(), "KIT_Goal_S",
            f.cx, f.cy, f.rot, 0.0, hy - 11.0, 0.16, kit=ctx.kit)
    elif pitch == "cricket":
        bd.box(-3.0, -11.0, 0.08, 3.0, 11.0, 0.12, M_GRASS)
        bd.box(-10.0, 24.0, 0.05, 10.0, 44.0, 0.09, M_SAND)
        for sy in (-1.0, 1.0):
            bd.box(-9.8, 24.5 + (0 if sy < 0 else 18.0), 0.09, 1.2, 24.9, 2.2, M_STEEL)
            bd.box(9.2, 24.5 if sy < 0 else 42.6, 0.09, 9.8, 24.9 if sy < 0 else 43.0,
                   2.0, M_STEEL)
            bd.box(-9.8, 24.5 if sy < 0 else 42.6, 0.9, 9.8, 24.9 if sy < 0 else 43.0,
                   0.98, M_CANVAS)
    # 4 floodlights + fence ring posts (perimeter, 8 m spacing)
    n = int((2 * hx) / 9.0)
    for k in range(n):
        put(ctx, ("fp",), lambda: k_bollard(), "KIT_FencePost_%03d" % (k + 1),
            f.cx, f.cy, f.rot, -hx + 2.0 + k * ((2 * hx - 4.0) / max(1, n - 1)), -hy + 1.0,
            0.0, kit=ctx.kit)
        put(ctx, ("fp",), lambda: k_bollard(), "KIT_FencePostN_%03d" % (k + 1),
            f.cx, f.cy, f.rot, -hx + 2.0 + k * ((2 * hx - 4.0) / max(1, n - 1)), hy - 1.0,
            0.0, kit=ctx.kit)
    ny = int((2 * hy) / 9.0)
    for k in range(ny):
        put(ctx, ("fp",), lambda: k_bollard(), "KIT_FencePostW_%03d" % (k + 1),
            f.cx, f.cy, f.rot, -hx + 1.0, -hy + 2.0 + k * ((2 * hy - 4.0) / max(1, ny - 1)),
            0.0, kit=ctx.kit)
        put(ctx, ("fp",), lambda: k_bollard(), "KIT_FencePostE_%03d" % (k + 1),
            f.cx, f.cy, f.rot, hx - 1.0, -hy + 2.0 + k * ((2 * hy - 4.0) / max(1, ny - 1)),
            0.0, kit=ctx.kit)
    add_light(ctx, (f.cx, f.cy, 12.0), energy=80.0, radius=12.0)
    collider(ctx, f, h=3.0, inset=3.0)
    _budget_note(ctx, f)
    return bd


def b_field(ctx, f):
    return _field_common(ctx, f, "football")


def b_field2(ctx, f):
    return _field_common(ctx, f, "cricket")


def b_amphitheatre(ctx, f):
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_GRASS)
    # stage shell: half-dome against the rear wall
    stagy = -hy + 10.0
    bd.box(-9.0, stagy, CURB, 9.0, stagy + 12.0, 6.0, M_BONE)
    for k in range(6):
        a0 = math.pi * (k / 6.0)
        a1 = math.pi * ((k + 1) / 6.0)
        bd.box(7.0 * math.cos(a0) - 0.2, stagy, CURB, 7.0 * math.cos(a0) + 0.2,
               stagy - 0.6, 6.0, M_BONE) if False else None
    bd.cyl(0.0, stagy, CURB, 0.0, 0.0, M_BONE, seg=1) if False else None
    for k in range(8):
        lo = ring_pts(0.0, stagy, 7.0 * math.sqrt(max(0.0, 1.0 - (k / 8.0) ** 2)), 10,
                      a0=0.0, a1=math.pi)
        hi = ring_pts(0.0, stagy, 7.0 * math.sqrt(max(0.0, 1.0 - ((k + 1) / 8.0) ** 2)), 10,
                      a0=0.0, a1=math.pi)
        loft_ring(bd, lo, hi, CURB + 6.0 * k / 8.0, CURB + 6.0 * (k + 1) / 8.0, M_BONE)
    bd.box(-12.0, stagy + 12.0, CURB, 12.0, stagy + 22.0, 4.4, M_BRICKB)
    gable(bd, -12.6, 12.6, stagy + 10.8, stagy + 23.2, 4.4, 7.0, M_ROOFM, along="x")
    # terraced grass seating arcs facing the stage (-Y side)
    rows = 6
    for r in range(rows):
        rr0 = 12.0 + r * 3.2
        rr1 = rr0 + 3.2
        lo = ring_pts(0.0, stagy, rr0, 16, a0=math.pi, a1=2 * math.pi)
        hi = ring_pts(0.0, stagy, rr1, 16, a0=math.pi, a1=2 * math.pi)
        loft_ring(bd, lo, hi, CURB + r * 0.55, CURB + r * 0.55, M_GRASS)
        bd.box(-rr1, stagy - rr1, CURB + r * 0.55, rr1, stagy - rr0, CURB + r * 0.55 + 0.5,
               M_CONC)
        for k in range(6):
            px = -rr0 * 0.8 + k * (rr0 * 1.6 / 5.0)
            py = stagy - math.sqrt(max(0.0, rr0 * rr0 - px * px)) + 0.9
            if -hx + 2.0 < px < hx - 2.0 and -hy + 2.0 < py < hy - 2.0:
                put(ctx, ("bench",), lambda: k_bench(), "KIT_TerrBench_%d_%d" % (r, k),
                    f.cx, f.cy, f.rot, px, py, CURB + r * 0.55 + 0.5, kit=ctx.kit)
    if f.tier <= 2 and f.enterable:
        _tier1_lobby(ctx, f, -11.0, 11.0, stagy - 2.0 + 1.0, stagy + 10.0,
                     floor=M_FLW, desks=[0.0])
    add_light(ctx, (f.cx, f.cy, 6.0), energy=90.0, radius=10.0)
    collider(ctx, f, h=6.0, inset=4.0)
    _budget_note(ctx, f)
    return bd



def b_trk_museum(ctx, f):
    """TRK_MOTORSPORT_MUSEUM — 228x224 m glazed hall, race simulators, trophy hall, cafe."""
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_ASPA)
    plinth(bd, hx, hy, M_CONC, 0.3)
    zwall = 13.0
    wall = M_CHAR
    # glazed hall: full-height glass curtain ring with a solid open-arch gate band
    faces = fac_faces(bd, hx, hy)
    for fkey, fc in faces.items():
        ops = []
        if fkey == "F":
            ops = [dict(u0=-22.0, u1=22.0, z0=CURB, z1=zwall - 1.2)]
        fc.wall(CURB, zwall, ops, wall)
        glass_curtain(fc, CURB, zwall, M_GLASSC, M_CHAR, mull=4.0)
        for o in ops:
            archway(fc, o, wall, steps=6)
    # steel ring + arched roof vault
    roof_deck(bd, hx, hy, zwall)
    parapet_ring(bd, hx, hy, zwall, wall)
    barrel(bd, -hx + 3.0, hx - 3.0, -hy + 3.0, hy - 3.0, zwall, top - zwall,
           M_ROOFM, seg=12, along="y")
    # arcade of colour chevrons on the long glass seams
    for k in range(6):
        u = -60.0 + k * 24.0
        put(ctx, ("col", 9.5), lambda: k_column(9.5, 0.55), "KIT_HallCol_%02d" % (k + 1),
            f.cx, f.cy, f.rot, u, -hy + 2.6, CURB, kit=ctx.kit)
        put(ctx, ("col", 9.5), lambda: k_column(9.5, 0.55), "KIT_HallCol_R%02d" % (k + 1),
            f.cx, f.cy, f.rot, u, hy - 2.6, CURB, kit=ctx.kit)
    for i, u in enumerate((-34.0, 0.0, 34.0)):
        put(ctx, ("flag", 16.0), lambda: k_flag(16.0), "KIT_GateFlag_%02d" % (i + 1),
            f.cx, f.cy, f.rot, u, -hy - 3.0, 0.0, kit=ctx.kit)
    # tier-3 fake-depth recess behind the entry glass (no door geometry)
    recess_box(bd, hx, -hy + 4.0, -hy + 20.0, CURB, 3.4, M_CONC2, wall, glass=M_GLASSC)
    # interior main floor: dark resin + red carpet runners
    bd.box(-hx + 4.0, -hy + 4.0, CURB, hx - 4.0, hy - 4.0, CURB + 0.05, M_CONC2)
    for u0 in (-30.0, 6.0):
        bd.box(u0, -hy + 10.0, CURB + 0.05, u0 + 24.0, -hy + 70.0, CURB + 0.2, M_FLCARP)
    # race simulator pod rows (2 rows x 4)
    for r in range(2):
        yy = -66.0 + r * 26.0
        for k in range(4):
            px = -45.0 + k * 30.0
            bd.cyl(px, yy, CURB, CURB + 0.35, 2.6, M_CHAR, seg=12)
            bd.box(px - 1.6, yy - 2.0, CURB + 0.35, px + 1.6, yy + 0.7, CURB + 2.2,
                   M_CHAR)
            dome(bd, px, yy - 0.6, CURB + 2.2, 2.0, 1.1, M_CHAR, seg=10, rings=3)
            bd.box(px - 2.2, yy + 0.7, CURB + 0.6, px + 2.2, yy + 1.0, CURB + 2.6,
                   M_MIRROR)
    # trophy hall strip along the north wall
    bd.box(-70.0, hy - 12.0, CURB, 70.0, hy - 4.0, CURB + 0.05, M_MARBLE)
    for k in range(7):
        u = -60.0 + k * 20.0
        put(ctx, ("shelf",), lambda: k_shelf(), "KIT_Trophy_%02d" % (k + 1),
            f.cx, f.cy, f.rot, u, hy - 8.0, CURB + 0.1, kit=ctx.kit)
        put(ctx, ("cab",), lambda: k_cab(), "KIT_TrophyCase_%02d" % (k + 1),
            f.cx, f.cy, f.rot, u + 10.0, hy - 8.0, CURB + 0.1, kit=ctx.kit)
    put(ctx, ("bench",), lambda: k_bench(), "KIT_TrophyBench_01",
        f.cx, f.cy, f.rot, 0.0, hy - 14.0, CURB + 0.1, kit=ctx.kit)
    # cafe corner (south-east)
    bd.box(44.0, -100.0, CURB, 72.0, -74.0, CURB + 0.05, M_FLW)
    put(ctx, ("desk",), lambda: k_desk(), "KIT_CafeCounter_01",
        f.cx, f.cy, f.rot, 58.0, -76.0, CURB + 0.1, kit=ctx.kit)
    for i in range(4):
        put(ctx, ("bench",), lambda: k_bench(), "KIT_CafeTable_%02d" % (i + 1),
            f.cx, f.cy, f.rot, 48.0 + (i % 2) * 18.0, -92.0 + (i // 2) * 12.0,
            CURB + 0.1, kit=ctx.kit)
    bd.box(44.0, -76.0, CURB + 0.05, 72.0, -75.8, 3.0, M_WOODP)
    # heritage cars on plinths
    for i, (px, py) in enumerate(((-30.0, -30.0), (30.0, -30.0), (0.0, 40.0))):
        bd.box(px - 4.0, py - 8.0, CURB, px + 4.0, py + 8.0, CURB + 0.45, M_CONC)
        bd.box(px - 2.4, py - 6.4, CURB + 0.45, px + 2.4, py + 6.4, CURB + 2.6,
               M_RUST if i == 2 else M_STEEL)
        dome(bd, px, py, CURB + 2.6, 2.2, 0.9, M_GLASSC, seg=8, rings=2)
    add_light(ctx, (f.cx - 20.0, f.cy - 60.0, 4.5), energy=120.0, radius=16.0)
    add_light(ctx, (f.cx + 30.0, f.cy + 40.0, 4.5), energy=110.0, radius=16.0)
    add_light(ctx, (f.cx - 50.0, f.cy + 70.0, 4.0), energy=90.0, radius=14.0)
    collider(ctx, f, h=zwall + 0.6, inset=0.3)
    _budget_note(ctx, f)
    return bd


def b_trk_medical(ctx, f):
    """TRK_MEDICAL — track medical centre: two-storey block, ambulance bays, helipad."""
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_ASPA)
    plinth(bd, hx, hy, M_CONC, 0.3)
    wall = M_BONE
    z0 = CURB
    ztop = f.floors * FLOOR + 1.2          # therapy block ~7.6 m
    ztop = min(ztop + 1.0, top)
    # main block in the upper half, deep apron in the lower half
    bx0, bx1 = -24.0, 24.0
    by0, by1 = -16.0, 62.0
    bd.box(bx0, by0, z0, bx1, by1, ztop, wall)
    # window punching on the long side walls
    for sx, side in ((bx0 + WALL_T, "L"), (bx1 - WALL_T, "R")):
        lfc = Face(bd, "x", sx - WALL_T * 0.5, sx + WALL_T * 0.5, -1 if side == "L" else 1,
                   by0, by1)
        for zz in range(f.floors):
            ribbon_band(lfc, z0 + zz * FLOOR, wall, band_h=1.6, band_z=1.0,
                        glass=M_GLASS, frame=M_CHAR)
    ffy = Face(bd, "y", by0, by0 + WALL_T, -1, bx0, bx1)
    for zz in range(f.floors):
        ribbon_band(ffy, z0 + zz * FLOOR, wall, band_h=1.7, band_z=0.9,
                    glass=M_GLASS, frame=M_CHAR)
    bd.box(bx0, by0, ztop, bx1, by1, ztop + 0.05, M_ROOF)
    for (a0, b0, a1, b1) in ((bx0, by0, bx1, by0 + 0.3), (bx0, by1 - 0.3, bx1, by1),
                             (bx0, by0, bx0 + 0.3, by1), (bx1 - 0.3, by0, bx1, by1)):
        bd.box(a0, b0, ztop, a1, b1, ztop + 0.9, wall)
    # oxblood accent band + response sign
    bd.box(bx0, by0, ztop - 0.5, bx1, by1, ztop - 0.1, M_OXB)
    bd.box(-3.0, by0 + 1.2, ztop - 2.4, 3.0, by0 + 1.5, ztop - 1.6, M_OXB)
    bd.box(34.0, by0 + 4.0, z0 + 3.0, 34.4, by0 + 12.0, z0 + 4.4, M_SIGNW)
    # ambulance bay: canopy on columns along the east flank with 4 open bays
    bd.box(24.0, -8.0, z0 + 4.2, 26.5, 40.0, z0 + 4.5, M_CHAR)
    for k in range(5):
        yy = -4.0 + k * 11.0
        put(ctx, ("colmed", k + 1), lambda: k_column(4.2, 0.3), "KIT_BayCol_%02d" % (k + 1),
            f.cx, f.cy, f.rot, 25.4, yy, z0, kit=ctx.kit)
        put(ctx, ("lampp",), lambda: k_lamppost(), "KIT_BayLamp_%02d" % (k + 1),
            f.cx, f.cy, f.rot, 21.5, yy, z0, kit=ctx.kit)
    put(ctx, ("floodb",), lambda: k_flood(), "KIT_BayFlood_01",
        f.cx, f.cy, f.rot, 26.0, 22.0, z0 + 4.5, kit=ctx.kit)
    # ambulance parking pads in the service apron
    for k in range(4):
        yy = 2.0 + k * 10.0
        bd.box(28.0, yy - 3.4, z0 + 0.05, 40.0, yy + 3.4, z0 + 0.12, M_CONC)
        bd.box(28.0, yy - 0.15, z0 + 0.12, 40.0, yy + 0.15, z0 + 0.18, M_MARKW)
    # helipad marking at the south apron end
    hc = -52.0
    bd.box(-16.0, hc - 16.0, z0 + 0.05, 16.0, hc + 16.0, z0 + 0.12, M_CONC)
    loft_ring(bd, ring_pts(0.0, hc, 12.6, 24), ring_pts(0.0, hc, 13.0, 24),
              z0 + 0.12, z0 + 0.18, M_MARKW)
    for (cx0, cy0, cx1, cy1) in ((-1.1, hc - 7.0, 1.1, hc + 7.0),
                                 (-6.5, hc - 7.0, -4.3, hc + 7.0),
                                 (4.3, hc - 7.0, 6.5, hc + 7.0),
                                 (-6.5, hc - 0.6, 6.5, hc + 0.6),
                                 (-6.5, hc - 7.6, 6.5, hc - 5.4),
                                 (-6.5, hc + 5.4, 6.5, hc + 7.6)):
        bd.box(cx0, cy0, z0 + 0.12, cx1, cy1, z0 + 0.18, M_MARKW)
    put(ctx, ("windsock",), lambda: k_mast(9.0), "KIT_MedWindsock_01",
        f.cx, f.cy, f.rot, 0.0, hc - 22.0, z0, kit=ctx.kit)
    # tier-2 furnished reception behind the south face
    if f.tier <= 2 and f.enterable:
        _tier1_lobby(ctx, f, -14.0, 14.0, by0 + 0.4, by0 + 14.0,
                     floor=M_MARBLE, desks=[0.0], benches=3)
    add_light(ctx, (f.cx, f.cy + 24.0, 3.0), energy=90.0, radius=10.0)
    add_light(ctx, (f.cx, f.cy - 50.0, 3.0), energy=70.0, radius=9.0)
    collider(ctx, f, h=ztop + 0.6, inset=0.3)
    _budget_note(ctx, f)
    return bd


def b_track_museum(ctx, f):
    """TRK_MOTORSPORT_MUSEUM: windowless stone hall + glazed skylight, hero tier-3 facade."""
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_ASPA)
    plinth(bd, hx, hy, M_STONE, 0.3)
    wall = M_STONE
    # long windowless stone mass with a central glazed skylight band on the roof
    faces = fac_faces(bd, hx, hy)
    for fkey in ("F", "B", "L", "R"):
        faces[fkey].wall(CURB, top, [], wall)
    roof_deck(bd, hx, hy, top)
    parapet_ring(bd, hx, hy, top, wall, t=0.35, h=0.9)
    # skylight ridge along the roof centre
    skylight_w = 14.0
    bd.box(-skylight_w * 0.5, -hy - WALL_T, top + 0.05, skylight_w * 0.5, -hy,
           top + 2.6, M_GLASSC)
    bd.box(-skylight_w * 0.5, hy, skylight_w * 0.5, hy + WALL_T, top + 0.05,
           top + 2.6, M_GLASSC)
    for k in range(6):
        u = -hx + 6.0 + k * ((2 * hx - 12.0) / 5.0)
        bd.box(u - 0.15, -hy - 0.05, top + 0.2, u + 0.15, hy + 0.05, top + 2.4,
               M_STEEL)
    # trophy-hall fascia + neon blade sign at the front
    put(ctx, ("fas", 16.0), lambda: ent.p_fascia(16.0, M_NBLUE), "KIT_Fascia_01",
        f.cx, f.cy, f.rot, 0.0, -hy, top - 2.4, kit=ctx.kit)
    put(ctx, ("blade",), lambda: ent.p_blade(M_NPINK, w=2.6), "KIT_Blade_01",
        f.cx, f.cy, f.rot, hx - 4.0, -hy, 3.4, kit=ctx.kit)
    # cafe canopy at the entry
    put(ctx, ("can", 10.0), lambda: ent.p_canopy(10.0), "KIT_Canopy_01",
        f.cx, f.cy, f.rot, 0.0, -hy, 3.0, kit=ctx.kit)
    # tier-3 dark fake-depth interior (no props)
    if f.tier <= 3:
        ibd = Builder()
        ibd.box(-hx + 0.5, -hy + 0.5, CURB, hx - 0.5, hy - 0.5, CURB + 0.03, M_FLT)
        ibd.box(-hx + 0.5, -hy + 0.5, 3.08, hx - 0.5, hy - 0.5, 3.20, M_CEIL)
        for sx in (-hx + 0.5, hx - 0.75):
            ibd.box(sx, -hy + 0.5, CURB, sx + 0.25, hy - 0.5, 3.20, M_WALLP)
        ibd.box(-hx + 0.5, hy - 0.75, CURB, hx - 0.5, hy - 0.5, 3.20, M_WALLP)
        emit(ctx, f, ibd, "INT_%s_Hall" % _cap(f.id), rot=f.rot)
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


def b_track_medical(ctx, f):
    """TRK_MEDICAL: infield trauma centre, 4 ambulance bays, helipad 'H' apron."""
    hx, hy, top = f.hx, f.hy, f.top
    bd = Builder()
    forecourt(bd, hx, hy, M_ASPA)
    plinth(bd, hx, hy, M_STONE, 0.3)
    wall = M_PANEL
    faces = fac_faces(bd, hx, hy)
    ops = [dict(u0=-8.0, u1=8.0, z0=CURB, z1=3.6)]
    faces["F"].wall(CURB, FLOOR, ops, wall)
    archway(faces["F"], ops[0], wall)
    for eff in ("L", "R", "B"):
        faces[eff].wall(CURB, FLOOR, [], wall)
    for z0 in range(1, f.floors):
        zz = FLOOR + (z0 - 1) * FLOOR
        ribbon_band(faces["F"], zz, wall, band_h=1.6)
        ribbon_band(faces["L"], zz, wall, band_h=1.6)
        ribbon_band(faces["R"], zz, wall, band_h=1.6)
        faces["B"].wall(zz, zz + FLOOR, [], wall)
    roof_deck(bd, hx, hy, top)
    parapet_ring(bd, hx, hy, top, wall)
    # 4 ambulance bays along the +Y side (rear apron), open - no doors
    bay_ops = [dict(u0=-hx + 4.0 + k * 10.0, u1=-hx + 10.0 + k * 10.0,
                    z0=CURB, z1=4.2) for k in range(4)]
    faces["B"].wall(CURB, 4.6, bay_ops, wall)
    for o in bay_ops:
        archway(faces["B"], o, wall, steps=4)
    bd.box(-hx + 2.0, hy - 4.6, CURB, hx - 2.0, hy, 0.06, M_ASPA)
    # helipad 'H' marking on the apron
    bd.box(-4.0, hy - 0.5, 0.08, 4.0, hy + 0.5, 0.12, M_MARKW)
    bd.box(-1.0, hy - 1.8, 0.08, 1.0, hy - 0.5, 0.12, M_MARKW)
    bd.box(-1.8, hy - 1.0, 0.08, -1.0, hy - 0.5, 0.12, M_MARKW)
    bd.box(1.0, hy - 1.0, 0.08, 1.8, hy - 0.5, 0.12, M_MARKW)
    put(ctx, ("rfac",), lambda: ent.p_roofac(), "KIT_RoofAC_01",
        f.cx, f.cy, f.rot, hx - 5.0, hy - 5.0, top + 0.05, kit=ctx.kit)
    if f.tier <= 2 and f.enterable:
        _tier1_lobby(ctx, f, -hx + 0.5, hx - 0.5, -hy + 0.5, -hy + 12.0,
                     floor=M_FLT, desks=[-3.0], benches=2)
    add_light(ctx, (f.cx, f.cy, 2.7), energy=90.0, radius=8.0,
              color=(0.85, 0.9, 1.0))
    collider(ctx, f)
    _budget_note(ctx, f)
    return bd


BUILDERS = {
    "CITY_HALL": lambda ctx, f: b_classical(ctx, f, "hall"),
    "COURTHOUSE": lambda ctx, f: b_classical(ctx, f, "courthouse"),
    "MUSEUM_CITY": lambda ctx, f: b_classical(ctx, f, "museum"),
    "PLANETARIUM": b_planetarium,
    "THEATRE": b_theatre,
    "CONCERT_HALL": b_concert,
    "CUL_CINEMA": b_cinema,
    "CUL_CLUB": b_club,
    "ARCADE_GAMES": b_arcade,
    "CASINO": b_casino,
    "GALLERY_ART": b_gallery,
    "LIBRARY_PUBLIC": b_library,
    "HOSPITAL_MAIN": b_hospital,
    "STATION_FIRE": b_fire,
    "STATION_POLICE": b_police,
    "SCHOOL_SECONDARY": lambda ctx, f: b_school(ctx, f, "U"),
    "SCHOOL_PRIMARY": lambda ctx, f: b_school(ctx, f, "L"),
    "SCHOOL_KINDER": lambda ctx, f: b_school(ctx, f, "K"),
    "CLINIC_URGENT": b_clinic,
    "CIVIC_TOWN_OFFICES": b_offices,
    "COLLEGE_VOCATIONAL": b_college,
    "UNIVERSITY_MAIN": b_uni_main,
    "UNIVERSITY_FACULTY": b_uni_faculty,
    "EMBASSY": b_embassy,
    "MOSQUE": b_mosque,
    "CHURCH": b_church,
    "TEMPLE": b_temple,
    "GURUDWARA": b_gurudwara,
    "UTL_CREMATORIUM": b_crematorium,
    "CIVIC_EMERGENCY_OPS": b_emergency,
    "SPT_VELODROME": b_velodrome,
    "SPT_TENNIS_CENTRE": b_tennis,
    "REC_GYM": b_gym,
    "SPT_MOTOCROSS_PARK": b_motocross,
    "SPT_ARCHERY_RANGE": b_archery,
    "SPORTS_FIELD_1": b_field,
    "SPORTS_FIELD_2": b_field2,
    "AMPHITHEATRE": b_amphitheatre,
    "TRK_MOTORSPORT_MUSEUM": b_trk_museum,
    "TRK_MEDICAL": b_trk_medical,
}


def load_program():
    with open(PROGRAM) as fh:
        p = json.load(fh)
    out = []
    for pf in p["facilities"]:
        if pf.get("owning_module") != "SportsCivic":
            continue
        if pf["id"] in STADIUMS:
            continue
        out.append(pf)
    return out


def zone_check(f):
    """True when a rect would violate another agent's land; returns reason or None."""
    r = f.rect

    def ovl(b):
        return not (r[2] <= b[0] or r[0] >= b[2] or r[3] <= b[1] or r[1] >= b[3])
    if ovl(ZONE_M):
        return "inside M district (market zone)"
    if ovl(ZONE_LAKE):
        return "overlaps LAKE_1"
    if ovl(ZONE_CIRCUIT) and not f.id.startswith("TRK_"):
        return "inside circuit zone without TRK id"
    for i, s in enumerate(ZONE_STADIUM, 1):
        if ovl(s):
            return "overlaps stadium rect %d (Sports module)" % i
    return None


def purge_civic():
    coll = bpy.data.collections.get(MODULE)
    if coll is not None:
        for ob in list(coll.all_objects):
            try:
                bpy.data.objects.remove(ob, do_unlink=True)
            except Exception as exc:
                print("  [civic] purge object failed:", exc)

        def rm(c):
            for ch in list(c.children):
                rm(ch)
            try:
                bpy.data.collections.remove(c)
            except Exception as exc:
                print("  [civic] purge collection failed:", exc)
        rm(coll)
    lt = bpy.data.objects.get("TMP_GROUND")
    if lt is not None:
        bpy.data.objects.remove(lt, do_unlink=True)
    for nm in ("Cube", "Camera", "Light"):
        ob = bpy.data.objects.get(nm)
        if ob is not None:
            bpy.data.objects.remove(ob, do_unlink=True)
    for c in list(bpy.data.collections):
        if c.name == MODULE or len(c.objects) or len(c.children):
            continue
        try:
            bpy.data.collections.remove(c)
        except Exception:
            pass


def pick_engine():
    ids = []
    try:
        ids = [i.identifier
               for i in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    except Exception:
        pass
    if "BLENDER_EEVEE" in ids:
        return "BLENDER_EEVEE"
    for i in ids:
        if "EEVEE" in i:
            return i
    return "BLENDER_EEVEE"


def temp_ground(on, big=True):
    """Preview-only ground slab (scene collection, deleted before the save)."""
    if on:
        if bpy.data.objects.get("TMP_GROUND") is not None:
            return
        bd = Builder()
        bd.box(-1800.0, -1800.0, -0.4, 1800.0, 1800.0, 0.0, M_GRASS)
        me = make_mesh("TMP_GROUND", bd)
        ob = bpy.data.objects.new("TMP_GROUND", me)
        bpy.context.scene.collection.objects.link(ob)
    else:
        ob = bpy.data.objects.get("TMP_GROUND")
        if ob is not None:
            bpy.data.objects.remove(ob, do_unlink=True)
        me = bpy.data.meshes.get("TMP_GROUND")
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)


def run_previews(eng):
    prev1 = os.path.join(ck.OUT_DIR, "civic_preview.png")
    prev2 = os.path.join(ck.OUT_DIR, "civic_street_preview.png")
    temp_ground(True)
    try:
        try:
            ck.make_preview(prev1, (620.0, -560.0, 340.0), (60.0, 220.0, 10.0),
                            engine=eng, res=(1920, 1080),
                            sun_elev=35.0, sun_azim=-50.0, sun_energy=3.4, samples=32)
        except Exception as exc:
            print("[civic] preview 1 failed:", exc)
            prev1 = None
        try:
            ck.make_preview(prev2, (45.0, 90.0, 1.7), (45.0, 250.0, 7.0),
                            engine=eng, res=(1920, 1080),
                            sun_elev=28.0, sun_azim=-35.0, sun_energy=3.0, samples=32)
        except Exception as exc:
            print("[civic] preview 2 failed:", exc)
            prev2 = None
    finally:
        temp_ground(False)
    return prev1, prev2


def _rss_mb():
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmRSS"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return -1


def _zone_note(ctx, f):
    hits = road_hits([f.rect[0] - 0.5, f.rect[1] - 0.5, f.rect[2] + 0.5, f.rect[3] + 0.5],
                     ctx.road)
    if hits:
        ctx.note(f, "facility rect touches road corridor %s" % (hits[:2],))


def main():
    t0 = time.time()
    if "--previews-only" in sys.argv:
        # Phase 2 of a full run: reload the saved blend and render previews only.
        bpy.ops.wm.open_mainfile(filepath=os.path.join(ck.OUT_DIR, "civic.blend"))
        rp = os.path.join(ck.REPORTS_DIR, "civic_report.json")
        payload = json.load(open(rp)) if os.path.exists(rp) else {}
        eng = pick_engine()
        prev1, prev2 = run_previews(eng)
        payload["previews"] = [p for p in (prev1, prev2) if p]
        payload.setdefault("issues", []).append(
            "previews rendered in a separate process (--previews-only)")
        print("[civic] previews done: %s" % payload["previews"], flush=True)
        ck.write_report("civic", payload)
        write_md(payload)
        return
    purge_civic()
    ctx = Ctx()
    prog = load_program()
    print("[civic] %d SportsCivic facilities (stadiums excluded)" % len(prog))
    only = None
    lim = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
        prog = [pf for pf in prog if pf["id"] == only]
        print("[civic] single-facility run: %s" % only)
    if "--limit" in sys.argv:
        lim = int(sys.argv[sys.argv.index("--limit") + 1])
        prog = prog[:lim]
        print("[civic] SMOKE TEST: first %d facilities" % lim)
    staged = 0
    for pf in prog:
        print("[civic] -- iter begin", flush=True)
        f = Fac(pf, ctx.segments)
        reason = zone_check(f)
        if reason:
            f.ok = False
            ctx.note(f, "CONFLICT: %s — facility NOT built" % reason)
            ctx.built[f.id] = f
            continue
        _zone_note(ctx, f)
        fn = BUILDERS.get(pf["id"])
        if fn is None:
            f.ok = False
            ctx.note(f, "no builder registered")
            ctx.built[f.id] = f
            continue
        print("[civic] building %s ..." % f.id, flush=True)
        try:
            ctx.cur = f
            res = fn(ctx, f)
            if isinstance(res, Builder):
                emit(ctx, f, res, "SM_%s" % _cap(f.id), rot=f.rot)
            ctx.cur = None
            if f.tris > f.budget:
                ctx.note(f, "tri budget over: %d > %d" % (f.tris, f.budget))
            ctx.buildboxes = None
            ctx.bboxes.append((f.rect, f.id))
        except Exception as exc:
            import traceback
            traceback.print_exc()
            f.ok = False
            ctx.note(f, "builder crashed: %s" % exc)
        ctx.built[f.id] = f
        staged += 1
        print("[civic] %-24s tris=%-6d tier=%d %s   [rss=%d MB]"
              % (f.id, f.tris, f.tier, "ok" if f.ok else "PROBLEM", _rss_mb()),
              flush=True)
        if staged % 10 == 0:
            bgc = gc.collect()
            del bgc
        if not lim and staged % 20 == 0:
            ck.save_blend(os.path.join(ck.OUT_DIR, "civic.blend"))
            print("[civic] stage save after %d facilities" % staged)
    # -------------------------------------------------------------- stats
    n_obj = len([o for o in bpy.data.objects if o.name.startswith(("SM_", "KIT_", "INT_",
                                                                  "LT_", "COL_"))])
    uniq_tris = ck.scene_tri_count()
    over = [(fid, ff.tris, ff.budget) for fid, ff in ctx.built.items()
            if ff.tris > ff.budget]
    build_list = [(fid, ff.tris, ff.tier, ff.bclass) for fid, ff in ctx.built.items()]
    ok_ids = sorted([fid for fid, ff in ctx.built.items() if ff.ok])
    eng = pick_engine()
    prev1 = prev2 = None
    noprev = "--nopreview" in sys.argv
    if lim is None and only is None and not noprev:
        prev1, prev2 = run_previews(eng)
    else:
        print("[civic] stage skipping previews", flush=True)
    ck.save_blend(os.path.join(ck.OUT_DIR, "civic.blend"))
    matlist = sorted(ctx.mat_used)
    payload = {
        "facilities_expected": len(prog),
        "facilities_built": len([f for f in ctx.built.values() if f.ok]),
        "facilities_conflicted": len([f for f in ctx.built.values() if not f.ok]),
        "objects": n_obj,
        "placed_objects": ctx.placed,
        "kit_props": ctx.props,
        "lights": ctx.lights_n,
        "colliders": ctx.colliders_n,
        "tris_unique_meshes": uniq_tris,
        "tris_instanced_total": ctx.tris + ctx.collider_tris,
        "collider_tris": ctx.collider_tris,
        "budget_overruns": over,
        "per_facility": build_list,
        "facilities_ok": ok_ids,
        "extensions": [],
        "collections": ["Civic", "Civic/Meshes", "Civic/Colliders", "Civic/Lights"],
        "materials": matlist,
        "engine": eng,
        "previews": [pp for pp in (prev1, prev2) if pp],
        "issues": sorted(set("{}: {}".format(fid, m) for fid, m in ctx.viol)),
        "build_seconds": round(time.time() - t0, 1),
    }
    ck.write_report("civic", payload)
    write_md(payload, ctx)
    print("[civic] DONE %.0fs facilities=%d obj=%d unique tris=%d"
          % (time.time() - t0, len([f for f in ctx.built.values() if f.ok]),
             n_obj, uniq_tris))


def write_md(d, ctx=None):
    lines = [
        "# Civic (SportsCivic) module report\n",
        "Generated by `modules/civic.py` (headless, EEVEE).\n",
        "## Counts\n",
        "| item | value |",
        "|---|---|",
        "| facilities expected | %s |" % d["facilities_expected"],
        "| built / conflicted | %s / %s |" % (d["facilities_built"],
                                             d["facilities_conflicted"]),
        "| objects (kit props / lights / colliders) | %s (%s / %s / %s) |"
        % (d["objects"], d["kit_props"], d["lights"], d["colliders"]),
        "| unique mesh tris | %s |" % d["tris_unique_meshes"],
        "| tris incl. instances + colliders | %s |" % d["tris_instanced_total"],
        "\n## Per facility\n",
        "| id | tris | tier | class | status |",
        "|---|---|---|---|---|",
    ]
    ok_ids = set(d.get("facilities_ok") or [])
    for fid, tris, tier, bcls in d["per_facility"]:
        status = "ok" if fid in ok_ids else "problem"
        lines.append("| %s | %s | %s | %s | %s |" % (fid, tris, tier, bcls, status))
    lines.append("\n## Budget overruns\n")
    lines.append(", ".join("%s %d>%d" % o for o in d["budget_overruns"]) or "none")
    lines.append("\n## Materials (%d, all from materials.blend)\n" % len(d["materials"]))
    lines.append(", ".join("`%s`" % m for m in d["materials"]))
    lines.append("\n## Collections / notes\n")
    lines.append("- collections: " + ", ".join(d["collections"]))
    lines.append("- previews: " + ", ".join(d["previews"]) if d["previews"] else "- previews: none")
    lines.append("- objects carry translation-only transforms; rotations are baked "
                 "into the shared meshes; origins bottom-centre.")
    lines.append("- no door meshes anywhere; enterable tiers use open archways / "
                 "missing-glass frontage; tier 1/2 furnished lobby interiors.")
    lines.append("\n## Issues\n")
    for i in d["issues"]:
        lines.append("- %s" % i)
    path = os.path.join(ck.REPORTS_DIR, "civic_report.md")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print("  [civic] markdown report -> %s" % path)


if __name__ == "__main__":
    main()
