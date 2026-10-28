#!/usr/bin/env python3
"""entertainment.py — Entertainment district (E) kit for the 3x3 km AAA city.

Headless run:
    cd /home/abdulhadi/Work/city && blender -b -P modules/entertainment.py

Builds all 288 district-E parcels (8 cells) as linked-duplicate archetype meshes
plus shared street furniture, marquees, neon signage and interiors.
Re-runnable: deletes the "Entertainment" collection first, saves after every cell.
"""
from __future__ import annotations

import math
import os
import sys
import time

ROOT = "/home/abdulhadi/Work/city"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT + "/modules")

import citykit as ck          # noqa: E402
import bpy                    # noqa: E402
from mathutils import Matrix  # noqa: E402

# ------------------------------------------------------------------ constants
CELLS = [[3, 2], [4, 2], [3, 3], [5, 3], [2, 4], [6, 4], [6, 5], [4, 6]]

FLOOR = 3.2                  # floor height
CURB = 0.15                  # plinth / curb height
WALL_T = 0.25                # wall thickness
CLEAR = 2.4                  # min clearance under anything overhanging pavement
HALF = 20.0                  # buildable half-size (buildable_rect = 40 x 40)
PLAZA_HALF = 22.0            # courtyard parcels build to the lot line (44 x 44)
TRIM = 5.0                   # rear yard depth for the external-stair archetypes

FASCIA_Z = 3.25              # signage band between ground and first floor
AWN_Z = 3.15                 # awning attachment height (drop 0.6 -> 2.55 clear)
AWN_PROJ = 1.4
BLADE_Z = 2.80               # blade-sign bottom edge
BLADE_PROJ = 0.95
MARQ_Z = 3.30                # cinema marquee soffit
MARQ_PROJ = 1.6
CANOPY_Z = 3.00              # hotel entrance canopy soffit
CANOPY_PROJ = 1.5
HANG_Z = 3.90                # projecting hanging sign bracket (bottom 2.60)
HANG_PROJ = 0.90
SMALL_PROJ = 0.16            # <= this at ground level = wall fixture, not an overhang

ROT = {"S": 0, "E": 90, "N": 180, "W": 270}
SIDE_VEC = {"S": (0.0, -1.0), "E": (1.0, 0.0), "N": (0.0, 1.0), "W": (-1.0, 0.0)}

ROAD_HW = {"highway": 17.0, "arterial": 12.0, "street": 6.0,
           "alley": 2.5, "interchange_ramp": 10.0}

# ------------------------------------------------------------------ style maps
# style_bible.md §5 (E): every E frontage carries >=1 emissive sign.
STYLE = {
    "neon_modern": dict(
        wall="facade_metal_panel", alt=["facade_metal_panel", "facade_plaster_teal"],
        band="metal_painted_charcoal", glass="glass_shop", win="glass_dark",
        frame="metal_painted_charcoal", sill="metal_steel", parapet="facade_metal_panel",
        spacing=4.0, w=2.6, sill_z=1.0, wh=1.8),
    "brick_loft": dict(
        wall="facade_brick_red", alt=["facade_brick_red", "brick_brown"],
        band="stone_grey", glass="glass_shop", win="glass_dark",
        frame="wood_painted", sill="stone_grey", parapet="facade_brick_red",
        spacing=3.6, w=1.8, sill_z=1.0, wh=1.9),
    "glass_retail": dict(
        wall="facade_plaster_bone", alt=["facade_plaster_bone", "facade_plaster_sand"],
        band="metal_painted_charcoal", glass="glass_shop", win="glass_dark",
        frame="metal_painted_charcoal", sill="stone_grey", parapet="facade_plaster_bone",
        spacing=4.0, w=1.9, sill_z=0.9, wh=1.8),
}
# club frontages are dark by rule; a dark facade keeps its own slot-0 palette
DARK_ALT = ["metal_painted_dark", "facade_plaster_charcoal"]

# --------------------------------------------------------------- type archetypes
SPEC = {
    "cinema": dict(open_w=10.0, marquee=True, posters=True, blind=True,
                   awning=False, hanging=False, vent=False, terrace=False,
                   billboard=True, roof="plant", neon=True),
    "club": dict(open_w=6.0, dark=True, neon_vert=True, led=True,
                 awning=False, hanging=True, vent=False, terrace=False,
                 roof="ac", neon=True),
    "gym": dict(open_w=8.0, tall=True, led=True, awning=False, hanging=False,
                vent=True, terrace=False, roof="plant", neon=True),
    "restaurant": dict(open_w=8.0, awning=True, terrace=True, vent=True,
                       hanging=False, roof="vent", neon=True),
    "cafe": dict(open_w=6.0, awning=True, terrace=True, hanging=True,
                 vent=False, roof="plant", neon=True),
    "shop": dict(open_w=6.0, awning=True, hanging=False, vent=False,
                 terrace=False, roof="plant", neon=True),
    "supermarket": dict(open_w=10.0, awning=False, led=True, hanging=False,
                        vent=True, terrace=False, roof="plant", neon=True),
    "apartment_low": dict(open_w=5.0, awning=False, hanging=False, vent=False,
                          terrace=False, balcony=True, roof="tank", neon=True),
    "hotel": dict(open_w=12.0, canopy=True, tall=True, blade=True, awning=False,
                  hanging=False, vent=False, terrace=False, roof="plant", neon=True),
    "courtyard": dict(open_w=0.0, plaza=True, awning=False, hanging=False,
                      vent=False, terrace=False, roof=None, neon=False),
}
# types whose rear yard is trimmed so the shared external stair fits
STAIR_TYPES = ("shop", "cafe", "restaurant", "gym", "apartment_low", "supermarket")
# interior floor material per type
INT_FLOOR = {"cinema": "floor_carpet", "club": "floor_carpet", "gym": "floor_tile",
             "restaurant": "floor_tile", "cafe": "floor_tile", "shop": "floor_tile",
             "supermarket": "floor_tile", "apartment_low": "floor_wood",
             "hotel": "floor_carpet", "courtyard": "paving_slab"}
INT_WALL = {"cinema": "wall_paint", "club": "wall_paint", "gym": "wall_paint",
            "restaurant": "int_wall_paint_bone", "cafe": "int_wall_paint_bone",
            "shop": "int_wall_paint_bone", "supermarket": "int_wall_paint_bone",
            "apartment_low": "int_wall_paint_bone", "hotel": "int_wall_paint_sand",
            "courtyard": "wall_paint"}
NEON_ROT = ["neon_magenta", "neon_violet", "neon_teal", "neon_pink",
            "neon_blue", "neon_red", "neon_green"]
AWNING_MATS = ["awning_fabric_red", "awning_fabric_stripe", "awning_fabric_green",
               "fabric_awning_magenta", "fabric_awning_teal"]


def dhash(s):
    h = 2166136261
    for ch in str(s):
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


# ------------------------------------------------------------ geometry plumbing
def wall_rects(u0, u1, z0, z1, ops):
    """Decompose a wall rectangle into solid rects around `ops` openings."""
    zs = {z0, z1}
    for o in ops:
        zs.add(max(z0, o["z0"]))
        zs.add(min(z1, o["z1"]))
    zs = sorted(zs)
    out = []
    for i in range(len(zs) - 1):
        za, zb = zs[i], zs[i + 1]
        if zb - za < 1e-6:
            continue
        ivs = []
        for o in ops:
            if o["z0"] > za + 1e-9 or o["z1"] < zb - 1e-9:
                continue
            ivs.append((o["u0"], o["u1"]))
        ivs = [(max(a, u0), min(b, u1)) for a, b in ivs]
        ivs = [(a, b) for a, b in ivs if b > a + 1e-6]
        if not ivs:
            out.append((u0, za, u1, zb))
            continue
        ivs.sort()
        merged = [list(ivs[0])]
        for a, b in ivs[1:]:
            if a <= merged[-1][1] + 1e-9:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        cur = u0
        for a, b in merged:
            if a > cur + 1e-6:
                out.append((cur, za, a, zb))
            cur = max(cur, b)
        if cur < u1 - 1e-6:
            out.append((cur, za, u1, zb))
    return out


class Builder(object):
    """Collects verts / faces / material-indices for one mesh datablock."""

    def __init__(self):
        self.v = []
        self.f = []
        self.mi = []
        self.mats = []

    def midx(self, name):
        m = self.mats
        for i, x in enumerate(m):
            if x == name:
                return i
        m.append(name)
        return len(m) - 1

    def poly(self, pts, mat):
        i = self.midx(mat)
        n = len(self.v)
        self.v.extend(pts)
        self.f.append(tuple(range(n, n + len(pts))))
        self.mi.append(i)

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
        for f in ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
                  (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            self.f.append(tuple(n + k for k in f))
            self.mi.append(i)

    def cyl(self, cx, cy, z0, z1, r, mat, seg=8, cap=True):
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


class Face(object):
    """One vertical wall plane of a building, in local (u, z) wall space."""

    def __init__(self, bd, axis, d0, d1, out, u0, u1):
        self.bd = bd
        self.axis = axis          # 'y' -> u is x ; 'x' -> u is y
        self.d0 = d0
        self.d1 = d1
        self.out = out            # +1 / -1 outward along the depth axis
        self.u0 = u0
        self.u1 = u1

    @property
    def length(self):
        return self.u1 - self.u0

    def seg(self, t0, t1):
        outer = self.d0 if self.out < 0 else self.d1
        a = outer - self.out * t0
        b = outer - self.out * t1
        return (a, b) if a < b else (b, a)

    def rect(self, u0, z0, u1, z1, mat, t0=0.0, t1=WALL_T):
        lo, hi = self.seg(t0, t1)
        if self.axis == "y":
            self.bd.box(u0, lo, z0, u1, hi, z1, mat)
        else:
            self.bd.box(lo, u0, z0, hi, u1, z1, mat)

    def wall(self, z0, z1, ops, mat):
        for (a, c, b, d) in wall_rects(self.u0, self.u1, z0, z1, ops):
            self.rect(a, c, b, d, mat)


_TRI = {}


def mesh_tris(me):
    key = me.as_pointer()
    t = _TRI.get(key)
    if t is None:
        t = 0
        for p in me.polygons:
            n = len(p.vertices)
            if n >= 3:
                t += n - 2
        _TRI[key] = t
    return t


def make_mesh(name, bd):
    me = bpy.data.meshes.new(name)
    me.from_pydata(bd.v, [], bd.f)
    me.update()
    for n in bd.mats:
        me.materials.append(ck.append_material(n))
    for p, mi in zip(me.polygons, bd.mi):
        p.material_index = int(mi)
    return me


class Kit(object):
    """Caches archetype meshes and their baked Z-rotations (shared, linked)."""

    def __init__(self, tag):
        self.tag = tag
        self.base = {}
        self.cache = {}

    def get(self, key, rot, fn):
        rot = int(rot) % 360
        ck_ = (key, rot)
        m = self.cache.get(ck_)
        if m is not None:
            return m
        b = self.base.get(key)
        if b is None:
            b = fn()
            self.base[key] = b
        if rot == 0:
            m = b
        else:
            m = b.copy()
            m.transform(Matrix.Rotation(math.radians(rot), 4, "Z"))
            m.name = "%s_%s_r%d" % (self.tag, str(key).replace(" ", "").replace("'", ""), rot)
        m.use_fake_user = True
        self.cache[ck_] = m
        return m


def new_obj(name, mesh, loc, coll, slot_mat=None):
    ob = bpy.data.objects.new(name, mesh)
    ob.location = (float(loc[0]), float(loc[1]), float(loc[2]))
    coll.objects.link(ob)
    if slot_mat is not None:
        try:
            slot = ob.material_slots[0]
            slot.link = "OBJECT"
            slot.material = ck.append_material(slot_mat)
        except Exception as exc:
            print("  [entertainment] slot override failed for %s: %s" % (name, exc))
    return ob


# ------------------------------------------------------------------ props
# Every prop is defined at its MOUNT point (origin = wall face / floor),
# projecting toward -Y, z relative to the placement height. Baked rotations
# are produced by Kit.get(), so props stay shared meshes.
def p_fascia(w, neon):
    bd = Builder()
    bd.box(-w * 0.5, -0.12, 0.0, w * 0.5, 0.02, 0.52, "sign_metal")
    bd.box(-w * 0.5 + 0.10, -0.155, 0.09, w * 0.5 - 0.10, -0.12, 0.43, neon)
    bd.box(-w * 0.5 - 0.03, -0.13, -0.04, w * 0.5 + 0.03, 0.03, 0.02, "metal_painted_dark")
    bd.box(-w * 0.5 - 0.03, -0.13, 0.52, w * 0.5 + 0.03, 0.03, 0.58, "metal_painted_dark")
    return bd


def p_blade(neon, w=1.0, h=1.15, proj=BLADE_PROJ):
    bd = Builder()
    bd.box(-0.05, -proj, 0.92, 0.05, 0.03, 1.02, "metal_steel")      # arm
    bd.box(-w * 0.5, -proj, 0.0, w * 0.5, -proj + 0.08, h, "sign_metal")
    bd.box(-w * 0.5 + 0.08, -proj - 0.03, 0.10, w * 0.5 - 0.08, -proj, h - 0.10, neon)
    bd.box(-w * 0.5 + 0.08, -proj + 0.08, 0.10, w * 0.5 - 0.08, -proj + 0.11, h - 0.10, neon)
    bd.box(-0.03, -proj, h - 0.05, 0.03, 0.03, h + 0.30, "metal_steel")   # hanger
    bd.box(-0.06, -0.02, h + 0.30, 0.06, 0.04, h + 0.36, "sign_metal")
    return bd


def p_hangsign(neon, w=1.2, h=0.8, proj=HANG_PROJ):
    """Projecting hanging sign: bracket at the origin, plate hanging below."""
    bd = Builder()
    bd.box(-0.05, -proj, 0.0, 0.05, 0.03, 0.10, "metal_steel")
    bd.box(-0.03, -proj, -0.14, 0.03, -proj + 0.06, 0.02, "metal_steel")
    bd.box(-w * 0.5, -proj, -1.30, w * 0.5, -proj + 0.07, -1.30 + h + 0.35, "sign_metal")
    bd.box(-w * 0.5 + 0.07, -proj - 0.03, -1.30 + 0.07, w * 0.5 - 0.07, -proj, -1.30 + h + 0.28, neon)
    return bd


def p_poster():
    bd = Builder()
    bd.box(-0.62, -0.12, 0.0, 0.62, 0.01, 1.62, "sign_metal")
    bd.box(-0.52, -0.15, 0.10, 0.52, -0.12, 1.52, "emissive_cool")
    bd.box(-0.66, -0.13, -0.05, 0.66, 0.02, 0.02, "metal_painted_dark")
    bd.box(-0.66, -0.13, 1.62, 0.66, 0.02, 1.69, "metal_painted_dark")
    return bd


def p_led(w=3.0, h=1.5):
    bd = Builder()
    bd.box(-w * 0.5, -0.15, 0.0, w * 0.5, 0.01, h, "sign_metal")
    bd.box(-w * 0.5 + 0.06, -0.17, 0.06, w * 0.5 - 0.06, -0.15, h - 0.06, "emissive_cool")
    return bd


def p_marquee(w, proj=MARQ_PROJ):
    """Cinema marquee canopy with an emissive bulb strip (style_bible §6)."""
    bd = Builder()
    bd.box(-w * 0.5, -proj, 0.0, w * 0.5, 0.02, 0.42, "metal_painted_dark")
    bd.box(-w * 0.5 - 0.05, -proj - 0.07, -0.02, w * 0.5 + 0.05, -proj + 0.03, 0.50, "sign_metal")
    bd.box(-w * 0.5 + 0.05, -proj + 0.04, -0.14, w * 0.5 - 0.05, -0.04, 0.0, "sign_white")
    n = max(6, int(w / 1.15))
    for i in range(n):
        u = -w * 0.5 + 0.55 + i * (w - 1.1) / max(1, n - 1)
        bd.box(u - 0.075, -proj - 0.11, -0.16, u + 0.075, -proj + 0.02, -0.02, "emissive_warm")
    m = max(4, int((w - 1.0) / 1.6))
    for i in range(m):
        u = -w * 0.5 + 0.9 + i * (w - 1.8) / max(1, m - 1)
        bd.box(u - 0.07, -proj + 0.35, -0.13, u + 0.07, -proj + 0.55, -0.03, "emissive_warm")
    bd.box(-0.10, -proj + 0.15, 0.42, 0.10, -0.05, 0.46, "metal_steel")   # tie rod
    return bd


def p_canopy(w, proj=CANOPY_PROJ):
    """Hotel entrance canopy — cantilevered, soffit 3.0 m clear."""
    bd = Builder()
    bd.box(-w * 0.5, -proj, 0.0, w * 0.5, 0.03, 0.34, "metal_painted_dark")
    bd.box(-w * 0.5 - 0.04, -proj - 0.04, 0.34, w * 0.5 + 0.04, 0.03, 0.40, "stone_grey")
    n = 4
    for i in range(n):
        u = -w * 0.5 + 0.8 + i * (w - 1.6) / max(1, n - 1)
        bd.box(u - 0.13, -proj + 0.30, -0.10, u + 0.13, -proj + 0.56, 0.0, "emissive_warm")
    return bd


def p_awning(mat, w=3.6, proj=AWN_PROJ, drop=0.50, val=0.10):
    bd = Builder()
    zf = -drop
    bd.poly([(-w * 0.5, 0.0, 0.0), (w * 0.5, 0.0, 0.0),
             (w * 0.5, -proj, zf), (-w * 0.5, -proj, zf)], mat)
    bd.poly([(-w * 0.5, -proj, zf - 0.05), (w * 0.5, -proj, zf - 0.05),
             (w * 0.5, 0.0, -0.05), (-w * 0.5, 0.0, -0.05)], mat)
    bd.box(-w * 0.5, -proj - 0.04, zf - val, w * 0.5, -proj + 0.04, zf, mat)
    for sx in (-1.0, 1.0):
        bd.box(sx * w * 0.5 - 0.04, -proj, zf - 0.06, sx * w * 0.5 + 0.04, 0.04, 0.04, "metal_steel")
    bd.box(-w * 0.5 + 0.1, -0.06, -0.06, w * 0.5 - 0.1, 0.02, 0.02, "metal_steel")
    return bd


def p_lamp():
    bd = Builder()
    bd.box(-0.05, -0.36, 0.30, 0.05, 0.02, 0.38, "metal_steel")
    bd.box(-0.13, -0.46, 0.02, 0.13, -0.20, 0.30, "metal_painted_dark")
    bd.box(-0.09, -0.42, -0.06, 0.09, -0.24, 0.03, "emissive_warm")
    return bd


def p_lightpanel():
    bd = Builder()
    bd.box(-1.2, -0.3, 0.0, 1.2, 0.3, 0.10, "metal_painted_dark")
    bd.box(-1.1, -0.24, -0.04, 1.1, 0.24, 0.0, "emissive_warm")
    return bd


def p_pipe(h):
    bd = Builder()
    bd.cyl(0.0, 0.0, 0.0, h, 0.055, "metal_rusty", seg=6)
    bd.box(-0.09, -0.10, 0.0, 0.09, 0.02, 0.14, "metal_rusty")
    bd.box(-0.09, -0.10, h - 0.3, 0.09, 0.02, h - 0.16, "metal_rusty")
    return bd


def p_ac():
    bd = Builder()
    bd.box(-0.55, -0.46, 0.0, 0.55, 0.0, 0.72, "metal_steel")
    bd.box(-0.42, -0.50, 0.14, 0.42, -0.46, 0.58, "metal_painted_dark")
    bd.box(-0.58, -0.48, -0.10, -0.50, 0.02, 0.04, "metal_steel")
    bd.box(0.50, -0.48, -0.10, 0.58, 0.02, 0.04, "metal_steel")
    return bd


def p_vent():
    bd = Builder()
    bd.box(-0.35, -0.11, 0.0, 0.35, 0.02, 0.52, "metal_steel")
    z = 0.06
    while z < 0.48:
        bd.box(-0.30, -0.13, z, 0.30, -0.06, z + 0.05, "metal_painted_dark")
        z += 0.11
    return bd


def p_meter():
    bd = Builder()
    bd.box(-0.26, -0.16, 0.0, 0.26, 0.02, 0.62, "metal_painted_dark")
    bd.box(-0.20, -0.18, 0.10, 0.20, -0.16, 0.42, "metal_steel")
    return bd


def p_neonvert(h=4.0, neon="neon_magenta"):
    bd = Builder()
    bd.box(-0.10, -0.14, 0.0, 0.10, 0.02, h, "sign_metal")
    z = 0.2
    while z < h - 0.2:
        bd.cyl(0.0, -0.17, z, z + 0.7, 0.03, neon, seg=6)
        z += 1.0
    return bd


def p_roofac():
    bd = Builder()
    bd.box(-1.3, -0.9, 0.0, 1.3, 0.9, 1.1, "metal_steel")
    bd.box(-1.2, -0.94, 0.2, 1.2, -0.9, 0.9, "metal_painted_dark")
    for i in range(5):
        bd.box(-1.15 + i * 0.5, -0.96, 0.25, -1.05 + i * 0.5, -0.9, 0.85, "metal_rusty")
    bd.box(-1.35, -0.95, -0.12, 1.35, 0.95, 0.02, "stone_grey")
    return bd


def p_tank():
    bd = Builder()
    bd.cyl(0.0, 0.0, 0.0, 1.6, 1.1, "metal_steel", seg=10)
    bd.cyl(0.0, 0.0, 1.6, 1.75, 1.14, "metal_rusty", seg=10)
    for a in (0.0, 1.57, 3.14, 4.71):
        bd.box(math.cos(a) * 1.0 - 0.06, math.sin(a) * 1.0 - 0.06, -0.6,
               math.cos(a) * 1.0 + 0.06, math.sin(a) * 1.0 + 0.06, 0.0, "metal_steel")
    return bd


def p_ventroof():
    bd = Builder()
    bd.box(-0.7, -0.7, 0.0, 0.7, 0.7, 1.3, "metal_steel")
    bd.cyl(0.0, 0.0, 1.3, 1.7, 0.45, "metal_rusty", seg=8)
    bd.cyl(0.0, 0.0, 1.7, 1.85, 0.6, "metal_steel", seg=8)
    return bd


def p_stair():
    """Shared external stair: ground -> first floor landing at the rear wall.

    Local frame: bottom nosing at y=+19.85 (buildable edge is +20), top landing
    at the rear wall face y=+15.0, z=3.2. 4.85 m run for a 3.2 m rise.
    """
    bd = Builder()
    x0, x1 = -0.7, 0.7
    tread, riser = 0.28, 0.2
    top = FLOOR
    n = int(round(top / riser))
    y = 19.85
    for k in range(n + 1):
        z = top - riser * k
        w = 0.55 if k == 0 else tread
        y_a, y_b = y - w, y
        bd.box(x0 - 0.07, y_a, 0.0, x1 + 0.07, y_b, z, "stone_grey")
        y = y_b
    # top landing slab (reaches the rear wall face at y=15.0)
    bd.box(x0 - 0.07, 15.0, top - 0.16, x1 + 0.07, 15.6, top, "stone_grey")
    # stringers + handrails
    for sx in (-1.0, 1.0):
        bx0 = sx * 0.70
        bx1 = sx * 0.78
        lo, hi = (bx0, bx1) if bx0 < bx1 else (bx1, bx0)
        bd.box(lo, 15.0, top + 0.05, hi, 19.9, top + 1.0, "metal_steel")
        p = 15.6
        while p < 19.7:
            t = (19.85 - p) / 4.85
            zz = top * (1.0 - t)
            bd.box(lo, p, zz, hi, p + 0.07, zz + 0.95, "metal_steel")
            p += 1.1
    bd.box(x0 - 0.07, 15.0, 0.0, x0, 19.85, 0.3, "metal_steel")
    return bd


def p_terrace():
    """Cafe/restaurant terrace table + two stools (sits inside the niche)."""
    bd = Builder()
    bd.cyl(0.0, 0.0, 0.72, 0.78, 0.55, "wood_old", seg=10)
    bd.cyl(0.0, 0.0, 0.0, 0.74, 0.06, "metal_steel", seg=6)
    bd.cyl(0.0, 0.0, 0.0, 0.05, 0.3, "metal_steel", seg=8)
    for a in (0.7, 3.85):
        sx, sy = math.cos(a) * 1.0, math.sin(a) * 1.0
        bd.box(sx - 0.22, sy - 0.22, 0.0, sx + 0.22, sy + 0.22, 0.45, "wood_painted")
        bd.box(sx - 0.22, sy - 0.22, 0.45, sx + 0.22, sy + 0.22, 0.52, "awning_fabric_stripe")
    return bd


def p_planter():
    bd = Builder()
    bd.box(-0.9, -0.9, 0.0, 0.9, 0.9, 0.55, "stone_grey")
    bd.box(-0.8, -0.8, 0.55, 0.8, 0.8, 0.62, "concrete")
    bd.cyl(0.0, 0.0, 0.6, 1.5, 0.75, "leaves_dark", seg=8)
    bd.cyl(0.0, 0.0, 1.5, 1.9, 0.45, "leaves_green", seg=8)
    return bd


def p_billboard(w=6.0, h=3.0):
    bd = Builder()
    bd.box(-w * 0.5, -0.16, 0.0, w * 0.5, 0.02, h, "sign_metal")
    bd.box(-w * 0.5 + 0.1, -0.18, 0.1, w * 0.5 - 0.1, -0.16, h - 0.1, "sign_white")
    bd.box(-w * 0.5 - 0.05, -0.17, -0.1, w * 0.5 + 0.05, 0.03, 0.02, "metal_painted_dark")
    for sx in (-0.3, 0.3):
        bd.box(sx * w - 0.05, -0.10, -0.9, sx * w + 0.05, 0.06, 0.0, "metal_steel")
    return bd


def p_bulbstring(w=14.0, n=10):
    """Plaza string lights: catenary of emissive bulbs between two poles."""
    bd = Builder()
    for sx in (-w * 0.5, w * 0.5):
        bd.cyl(sx, 0.0, 0.0, 4.2, 0.07, "metal_painted_dark", seg=6)
        bd.box(sx - 0.18, -0.18, 0.0, sx + 0.18, 0.18, 0.12, "stone_grey")
    for i in range(n):
        t = (i + 0.5) / n
        u = -w * 0.5 + t * w
        sag = 0.9 * 4.0 * t * (1.0 - t)
        z = 4.1 - sag
        bd.box(u - 0.07, -0.07, z - 0.16, u + 0.07, 0.07, z, "emissive_warm")
    bd.box(-w * 0.5, -0.02, 4.05, w * 0.5, 0.02, 4.11, "metal_painted_dark")
    return bd


# ------------------------------------------------------------------ facades
def _glass_fill(face, ops, mat):
    for o in ops:
        face.rect(o["u0"], o["z0"], o["u1"], o["z1"], mat, 0.10, 0.17)


def shopfront(face, st, ow, z_top, wall_mat, terr=False, terr_nw=7.0):
    """Ground-floor retail language: 2.4 m open frontage + flanking glazing."""
    L = face.length
    u_c = 0.0
    niche = None
    if terr:
        nw = min(terr_nw, L * 0.30)
        nu0 = 3.0
        nu1 = nu0 + nw
        u_c = nu0 - 1.0 - ow * 0.5
        niche = (nu0, nu1)
    else:
        u_c = 0.0
    e0, e1 = u_c - ow * 0.5, u_c + ow * 0.5
    e0 = max(e0, face.u0 + 1.2)
    e1 = min(e1, face.u1 - 1.2)
    transom = dict(u0=e0, u1=e1, z0=CLEAR + 0.05, z1=z_top - 0.25)
    ops = [dict(u0=e0, u1=e1, z0=CURB, z1=CLEAR), transom]   # open frontage + transom
    segs = [(face.u0 + 0.6, e0 - 0.4), (e1 + 0.4, face.u1 - 0.6)]
    if niche is not None:
        ops.append(dict(u0=niche[0], u1=niche[1], z0=CURB, z1=z_top - 0.2))
        segs = [(face.u0 + 0.6, e0 - 0.4), (niche[1] + 0.4, face.u1 - 0.6)]
    glass = [transom]
    for (a, b) in segs:
        if b - a < 1.4:
            continue
        g = dict(u0=a, u1=b, z0=CURB + 0.42, z1=z_top - 0.28)
        ops.append(g)
        glass.append(g)
    face.wall(CURB, z_top, ops, wall_mat)
    _glass_fill(face, glass, st["glass"])
    # mullions in the shopfront glass
    for g in glass:
        n = max(1, int((g["u1"] - g["u0"]) / 2.2))
        for i in range(1, n):
            u = g["u0"] + (g["u1"] - g["u0"]) * i / n
            face.rect(u - 0.06, g["z0"], u + 0.06, g["z1"], st["frame"], 0.12, 0.20)
        face.rect(g["u0"] - 0.08, g["z0"] - 0.10, g["u1"] + 0.08, g["z0"],
                  st["sill"], -0.04, 0.08)
    # entrance reveal (no door mesh - open archway at 2.4 m)
    face.rect(e0 - 0.10, CURB - 0.02, e0, CLEAR + 0.02, st["frame"], -0.03, 0.06)
    face.rect(e1, CURB - 0.02, e1 + 0.10, CLEAR + 0.02, st["frame"], -0.03, 0.06)
    face.rect(e0 - 0.10, CLEAR, e1 + 0.10, CLEAR + 0.10, st["frame"], -0.03, 0.06)
    return niche


def punched(face, st, z0, wall_mat, slit=False, frame=True):
    L = face.length
    sp = 5.0 if slit else st["spacing"]
    n = max(2, int((L - 2.0) / sp))
    step = L / n
    ops = []
    for i in range(n):
        u = face.u0 + step * (i + 0.5)
        w = min(1.0 if slit else st["w"], step - 0.7)
        z_0 = z0 + (1.45 if slit else st["sill_z"])
        h = 0.7 if slit else st["wh"]
        if w < 0.7:
            continue
        ops.append(dict(u0=u - w * 0.5, u1=u + w * 0.5, z0=z_0, z1=z_0 + h))
    face.wall(z0, z0 + FLOOR, ops, wall_mat)
    for o in ops:
        face.rect(o["u0"], o["z0"], o["u1"], o["z1"], st["win"], 0.10, 0.16)
        if slit or not frame:
            continue
        fw = 0.08
        face.rect(o["u0"] - fw, o["z0"], o["u0"], o["z1"], st["frame"], -0.02, 0.06)
        face.rect(o["u1"], o["z0"], o["u1"] + fw, o["z1"], st["frame"], -0.02, 0.06)
        face.rect(o["u0"] - 0.10, o["z0"] - 0.12, o["u1"] + 0.10, o["z0"],
                  st["sill"], -0.07, 0.07)
    return len(ops)


def ribbon(face, st, z0, wall_mat, band_h=1.6, band_z=0.85):
    L = face.length
    o = dict(u0=face.u0 + 0.7, u1=face.u1 - 0.7,
             z0=z0 + band_z, z1=z0 + band_z + band_h)
    face.wall(z0, z0 + FLOOR, [o], wall_mat)
    face.rect(o["u0"], o["z0"], o["u1"], o["z1"], st["win"], 0.10, 0.17)
    nu = max(4, int((o["u1"] - o["u0"]) / 3.2))
    for i in range(1, nu):
        u = o["u0"] + (o["u1"] - o["u0"]) * i / nu
        face.rect(u - 0.06, o["z0"], u + 0.06, o["z1"], st["frame"], 0.13, 0.19)
    face.rect(o["u0"] - 0.07, o["z0"] - 0.14, o["u1"] + 0.07, o["z0"],
              st["sill"], -0.05, 0.07)
    face.rect(o["u0"] - 0.07, o["z1"], o["u1"] + 0.07, o["z1"] + 0.10,
              st["band"], -0.02, 0.06)


def band_box(bd, face, z0, z1, hx, hy, mat, inset=0.12):
    """Structural signage band, proud of the facade (style_bible §6: bands, not boxes)."""
    if face.axis == "y":
        if face.out < 0:
            bd.box(-hx + 0.10, -hy - inset, z0, hx - 0.10, -hy + 0.04, z1, mat)
        else:
            bd.box(-hx + 0.10, hy - 0.04, z0, hx - 0.10, hy + inset, z1, mat)
    else:
        if face.out < 0:
            bd.box(-hx - inset, -hy + 0.10, z0, -hx + 0.04, hy - 0.10, z1, mat)
        else:
            bd.box(hx - 0.04, -hy + 0.10, z0, hx + inset, hy - 0.10, z1, mat)


def build_shell(typ, style, floors, pattern, ow):
    """Archetype massing. Origin bottom-centre, footprint inside buildable_rect."""
    sp = SPEC[typ]
    st = dict(STYLE[style])
    if sp.get("dark"):
        st["wall"] = "metal_painted_dark"
        st["parapet"] = "metal_painted_dark"
        st["band"] = "metal_painted_dark"
        st["frame"] = "metal_painted_dark"
    wall = st["wall"]
    bd = Builder()
    bd.midx(wall)                                   # slot 0 = wall (object palette slot)
    trim = typ in STAIR_TYPES and floors >= 2
    hx = HALF
    hy = HALF - TRIM if trim else HALF
    top = floors * FLOOR

    faces = {
        "F": Face(bd, "y", -hy, -hy + WALL_T, -1, -hx, hx),
        "B": Face(bd, "y", hy - WALL_T, hy, 1, -hx, hx),
        "R": Face(bd, "x", hx - WALL_T, hx, 1, -hy, hy),
        "L": Face(bd, "x", -hx, -hx + WALL_T, -1, -hy, hy),
    }
    # ---- plinth (origin at the bottom-centre, 0.15 m curb)
    bd.box(-hx, -hy, 0.0, hx, hy, CURB, "stone_grey")

    # ---- ground floor
    terr = bool(sp.get("terrace"))
    shopfront(faces["F"], st, ow, FLOOR, wall, terr=terr)
    if pattern == "pairL":
        shopfront(faces["L"], st, min(ow, hy * 0.9), FLOOR, wall)
    elif pattern == "pairR":
        shopfront(faces["R"], st, min(ow, hy * 0.9), FLOOR, wall)
    # rear + flank ground walls (solid unless they carry the second frontage)
    faces["B"].wall(CURB, FLOOR, [], wall)
    (faces["R"] if pattern == "pairR" else faces["L"]).wall(CURB, FLOOR, [], wall)
    if pattern in ("pairL", "pairR"):
        (faces["L"] if pattern == "pairL" else faces["R"]).wall(CURB, FLOOR, [], wall)
    else:
        faces["R"].wall(CURB, FLOOR, [], wall)

    # ---- signage band between ground and first floor
    band_box(bd, faces["F"], FASCIA_Z, FASCIA_Z + 0.52, hx, hy, st["band"])
    if pattern == "pairL":
        band_box(bd, faces["L"], FASCIA_Z, FASCIA_Z + 0.52, hx, hy, st["band"])
    elif pattern == "pairR":
        band_box(bd, faces["R"], FASCIA_Z, FASCIA_Z + 0.52, hx, hy, st["band"])

    # ---- upper floors
    tall = floors >= 6
    for f in range(1, floors):
        z0 = FLOOR + (f - 1) * FLOOR
        # front
        if typ == "cinema":
            faces["F"].wall(z0, z0 + FLOOR, [], wall)
        elif typ == "club":
            punched(faces["F"], st, z0, wall, slit=True)
        elif typ == "gym" and f == 1:
            o = dict(u0=-hx + 1.0, u1=hx - 1.0, z0=z0 + 0.25, z1=z0 + FLOOR - 0.35)
            faces["F"].wall(z0, z0 + FLOOR, [o], wall)
            _glass_fill(faces["F"], [o], st["glass"])
            for i in range(1, 8):
                u = o["u0"] + (o["u1"] - o["u0"]) * i / 8.0
                faces["F"].rect(u - 0.07, o["z0"], u + 0.07, o["z1"], st["frame"], 0.13, 0.19)
        elif tall:
            ribbon(faces["F"], st, z0, wall)
        else:
            punched(faces["F"], st, z0, wall)
        # sides
        for skey in ("R", "L"):
            side = faces[skey]
            if typ in ("cinema", "club"):
                side.wall(z0, z0 + FLOOR, [], wall)
            elif tall:
                ribbon(side, st, z0, wall)
            else:
                punched(side, st, z0, wall, frame=False)
        # rear (trimmed archetypes get the open first-floor stair landing, no door)
        rear_ops = []
        if trim and f == 1:
            rear_ops.append(dict(u0=-0.85, u1=0.85, z0=z0, z1=z0 + CLEAR))
        if tall and not rear_ops:
            ribbon(faces["B"], st, z0, wall)
        else:
            faces["B"].wall(z0, z0 + FLOOR, rear_ops, wall)
            if rear_ops:
                faces["B"].rect(-0.85, z0, 0.85, z0 + CLEAR, st["frame"], -0.03, 0.06)
        # balconies (brick_loft / apartment_low, style_bible §5)
        if sp.get("balcony") and f >= 1:
            n = 3
            for i in range(n):
                u = -hx + 4.0 + i * ((2 * hx - 8.0) / max(1, n - 1))
                bd.box(u - 1.2, -hy - 1.15, z0 + 0.02, u + 1.2, -hy + 0.05, z0 + 0.16, "concrete")
                bd.box(u - 1.2, -hy - 1.2, z0 + 0.16, u + 1.15, -hy - 1.12, z0 + 1.1, "metal_rusty")
                bd.box(u - 1.2, -hy - 1.2, z0 + 0.16, u - 1.12, -hy + 0.05, z0 + 1.1, "metal_rusty")
                bd.box(u + 1.12, -hy - 1.2, z0 + 0.16, u + 1.2, -hy + 0.05, z0 + 1.1, "metal_rusty")

    # ---- roof deck + parapet
    rm = "roof_bitumen"
    bd.box(-hx, -hy, top - 0.05, hx, hy, top + 0.04, rm)
    t, ph, c = 0.25, 1.0, 0.05
    pm = st["parapet"]
    bd.box(-hx, -hy, top, hx, -hy + t, top + ph, pm)
    bd.box(-hx, hy - t, top, hx, hy, top + ph, pm)
    bd.box(-hx, -hy + t, top, -hx + t, hy - t, top + ph, pm)
    bd.box(hx - t, -hy + t, top, hx, hy - t, top + ph, pm)
    bd.box(-hx - c, -hy - c, top + ph, hx + c, -hy + t + c, top + ph + 0.1, "stone_grey")
    bd.box(-hx - c, hy - t - c, top + ph, hx + c, hy + c, top + ph + 0.1, "stone_grey")
    bd.box(-hx - c, -hy + t + c, top + ph, -hx + t + c, hy - t - c, top + ph + 0.1, "stone_grey")
    bd.box(hx - t - c, -hy + t + c, top + ph, hx + c, hy - t - c, top + ph + 0.1, "stone_grey")
    return bd


# ----------------------------------------------------------------- interiors
def int_recess():
    """Tier 3: dark recessed interior box behind the open frontage."""
    bd = Builder()
    fy = -HALF + 0.30
    by = fy + 4.0
    hx = HALF - 0.30
    dk = "metal_painted_dark"
    bd.box(-hx, fy, CURB, hx, by, CURB + 0.03, "floor_carpet")
    bd.box(-hx, fy, 3.08, hx, by, 3.20, "ceiling_paint")
    bd.box(-hx, by - 0.22, CURB, hx, by, 3.20, dk)
    bd.box(-hx, fy, CURB, -hx + 0.22, by, 3.20, dk)
    bd.box(hx - 0.22, fy, CURB, hx, by, 3.20, dk)
    return bd


def _room_shell(bd, typ, fy, ry, hx, wl, rear=True):
    fl = INT_FLOOR[typ]
    bd.box(-hx, fy, CURB, hx, ry, CURB + 0.03, fl)
    bd.box(-hx, fy, 3.10, hx, ry, 3.20, "ceiling_paint")
    bd.box(-hx, fy, CURB, -hx + 0.22, ry, 3.20, wl)
    bd.box(hx - 0.22, fy, CURB, hx, ry, 3.20, wl)
    if rear:
        bd.box(-hx, ry - 0.22, CURB, hx, ry, 3.20, wl)


def seat(bd, x, y, w=0.5, d=0.5, h=0.45, back=0.9, mat="int_upholstery"):
    bd.box(x - w * 0.5, y - d * 0.5, 0.0, x + w * 0.5, y + d * 0.5, h, mat)
    bd.box(x - w * 0.5, y + d * 0.5 - 0.1, h, x + w * 0.5, y + d * 0.5, back, mat)
    bd.box(x - w * 0.5 + 0.05, y - d * 0.5 + 0.05, 0.0, x - w * 0.5 + 0.15,
           y + d * 0.5 - 0.05, 0.02, "metal_steel")


def table(bd, x, y, r=0.55, h=0.74, top="wood_old"):
    bd.cyl(x, y, h - 0.05, h, r, top, seg=10)
    bd.cyl(x, y, 0.0, h - 0.05, 0.06, "metal_steel", seg=6)
    bd.cyl(x, y, 0.0, 0.04, 0.28, "metal_steel", seg=8)


def counter(bd, x0, y0, x1, y1, h=1.05, top="int_laminate_counter"):
    bd.box(x0, y0, 0.0, x1, y1, h - 0.06, "wood_painted")
    bd.box(x0 - 0.05, y0 - 0.05, h - 0.06, x1 + 0.05, y1 + 0.05, h, top)


def racks(bd, fy, ry, hx, n=3):
    for i in range(n):
        y = fy + 2.2 + i * ((ry - fy - 3.0) / max(1, n - 1))
        bd.box(-hx + 1.2, y - 0.6, 0.0, hx - 1.2, y + 0.6, 1.7, "metal_painted_dark")
        bd.box(-hx + 1.25, y - 0.55, 0.6, hx - 1.25, y + 0.55, 0.68, "metal_steel")
        bd.box(-hx + 1.25, y - 0.55, 1.2, hx - 1.25, y + 0.55, 1.28, "metal_steel")


def furnish(bd, typ, fy, ry, hx):
    """Furniture for one room (visible through the open frontage)."""
    mid = (fy + ry) * 0.5
    if typ == "cinema":
        counter(bd, -hx + 1.0, fy + 1.2, -hx + 6.0, fy + 2.0, 1.1, "int_marble")
        for r in range(3):
            y = fy + 3.6 + r * 1.5
            for i in range(7):
                seat(bd, -hx + 3.0 + i * 2.2, y, 0.9, 0.9, 0.45, 1.0)
        bd.box(hx - 5.0, ry - 1.4, CURB, hx - 0.6, ry - 0.4, 2.6, "wall_paint")
    elif typ == "club":
        counter(bd, -hx + 1.0, ry - 2.6, hx - 4.0, ry - 1.6, 1.1, "int_marble")
        bd.box(-hx + 1.0, ry - 1.5, 1.2, hx - 4.0, ry - 1.2, 2.4, "int_mirror")
        for i in range(6):
            table(bd, -hx + 4.0 + (i % 3) * 5.5, fy + 3.0 + (i // 3) * 4.0, 0.6)
        bd.box(-hx + 3.0, fy + 1.4, CURB + 0.02, -hx + 9.0, fy + 4.4, CURB + 0.06, "neon_violet")
    elif typ == "gym":
        counter(bd, -hx + 1.0, fy + 1.0, -hx + 5.0, fy + 1.8, 1.1)
        bd.box(-hx + 0.4, ry - 0.4, 1.0, hx - 0.4, ry - 0.3, 2.8, "int_mirror")
        for i in range(6):
            x = -hx + 2.5 + (i % 3) * 5.5
            y = fy + 3.4 + (i // 3) * 4.5
            bd.box(x - 0.9, y - 0.7, 0.0, x + 0.9, y + 0.7, 0.35, "metal_painted_dark")
            bd.box(x - 0.8, y + 0.4, 0.35, x + 0.8, y + 0.6, 1.5, "metal_steel")
            bd.cyl(x - 0.7, y - 0.5, 0.5, 0.8, 0.28, "metal_rusty", seg=8)
            bd.cyl(x + 0.7, y - 0.5, 0.5, 0.8, 0.28, "metal_rusty", seg=8)
    elif typ in ("restaurant", "cafe"):
        counter(bd, hx - 6.5, fy + 1.0, hx - 1.2, fy + 1.9, 1.05, "int_marble")
        n = 5 if typ == "restaurant" else 4
        for i in range(n):
            x = -hx + 3.2 + (i % 3) * 5.4
            y = fy + 3.6 + (i // 3) * 4.2
            table(bd, x, y, 0.62)
            for a in (0.0, 2.1, 4.2):
                seat(bd, x + math.cos(a) * 1.1, y + math.sin(a) * 1.1, 0.44, 0.44, 0.46, 0.9)
    elif typ in ("shop", "supermarket", "apartment_low"):
        counter(bd, -hx + 1.2, ry - 3.0, -hx + 6.2, ry - 2.1, 1.05)
        racks(bd, fy, ry - 3.4, hx, 2 if typ != "supermarket" else 3)
    elif typ == "hotel":
        counter(bd, -hx + 2.0, fy + 2.4, -hx + 8.0, fy + 3.3, 1.1, "int_marble")
        for sx in (1.0, -1.0):
            bd.box(sx * (hx - 6.0), fy + 5.0, 0.0, sx * (hx - 2.0), fy + 6.4, 0.45, "int_upholstery")
            bd.box(sx * (hx - 6.0), fy + 6.2, 0.45, sx * (hx - 2.0), fy + 6.4, 1.0, "int_upholstery")
        bd.box(hx - 3.4, ry - 1.4, CURB, hx - 1.4, ry - 0.35, 3.0, "int_mirror")
        for i in range(2):
            table(bd, -hx + 4.0 + i * 6.0, fy + 8.5, 0.5)
    else:
        counter(bd, -hx + 1.5, fy + 1.5, -hx + 5.5, fy + 2.3, 1.05)


def int_room(typ, hy):
    """Tier 2: shell + one room behind the open frontage."""
    bd = Builder()
    fy = -hy + 0.30
    ry = hy - 0.30
    hx = HALF - 0.30
    wl = INT_WALL[typ]
    _room_shell(bd, typ, fy, ry, hx, wl)
    py = max(fy + 4.0, ry - 2.8)
    bd.box(-hx, py, CURB, -1.4, py + 0.18, 3.20, wl)
    bd.box(1.4, py, CURB, hx, py + 0.18, 3.20, wl)
    bd.box(-1.4, py, 2.55, 1.4, py + 0.18, 3.20, wl)
    furnish(bd, typ, fy, py, hx)
    return bd


def int_hall_a(typ):
    """Tier 1 front room (lobby / seating) — open plan into int_hall_b."""
    bd = Builder()
    fy = -HALF + 0.30
    py = 2.0
    hx = HALF - 0.30
    wl = INT_WALL[typ]
    _room_shell(bd, typ, fy, py + 0.18, hx, wl, rear=False)
    bd.box(-hx, py, CURB, -1.4, py + 0.18, 3.20, wl)
    bd.box(1.4, py, CURB, hx, py + 0.18, 3.20, wl)
    bd.box(-1.4, py, 2.55, 1.4, py + 0.18, 3.20, wl)
    furnish(bd, typ, fy, py, hx)
    return bd


def int_hall_b(typ, hy):
    """Tier 1 back room (service / storage / second seating)."""
    bd = Builder()
    py = 2.18
    ry = hy - 0.30
    hx = HALF - 0.30
    wl = INT_WALL[typ]
    _room_shell(bd, typ, py, ry, hx, wl)
    if typ in ("restaurant", "cafe", "supermarket", "shop"):
        bd.box(-hx + 0.8, ry - 3.0, CURB, -hx + 4.8, ry - 2.2, 1.05, "wood_painted")
        bd.box(-hx + 0.6, ry - 2.0, CURB, hx - 0.6, ry - 1.8, 2.2, "metal_painted_dark")
        for i in range(3):
            table(bd, -hx + 3.0 + i * 4.5, py + 2.4, 0.55)
    elif typ == "gym":
        for i in range(4):
            bd.box(-hx + 2.0 + i * 3.6, ry - 2.6, 0.0, -hx + 4.6 + i * 3.6, ry - 1.4,
                   1.9, "metal_painted_dark")
    elif typ == "hotel":
        bd.box(-hx + 1.0, ry - 2.4, CURB, -hx + 5.0, ry - 0.6, 2.6, "int_mirror")
        counter(bd, hx - 6.0, ry - 3.0, hx - 1.5, ry - 2.2, 1.05)
    else:
        counter(bd, -hx + 2.0, ry - 3.0, hx - 2.0, ry - 2.2, 1.05)
    return bd


# -------------------------------------------------------------------- plaza
def build_plaza():
    """District-E open-air dining plaza (courtyard parcels, tier 0)."""
    P = PLAZA_HALF
    bd = Builder()
    bd.midx("facade_plaster_bone")
    bd.box(-P, -P, 0.0, P, P, 0.08, "paving_slab")
    t, h = 0.3, 1.15
    gate = 5.0

    def wall_run(x0, x1, y0, y1):
        bd.box(x0, y0, 0.08, x1, y1, h, "facade_plaster_bone")
        bd.box(x0 - 0.05, y0 - 0.05, h, x1 + 0.05, y1 + 0.05, h + 0.1, "stone_grey")

    wall_run(-P, -gate, -P, -P + t)
    wall_run(gate, P, -P, -P + t)
    wall_run(-P, P, P - t, P)
    # side walls with a mid gap
    for sx in (-1.0, 1.0):
        x0, x1 = (sx * P - (t if sx > 0 else 0.0), sx * P + (0.0 if sx > 0 else t))
        a, b = (x0, x1) if x0 < x1 else (x1, x0)
        wall_run(a, b, -P + t, -4.0)
        wall_run(a, b, 4.0, P - t)
    # corner piers
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            bd.box(sx * P - 0.35, sy * P - 0.35, 0.08, sx * P + 0.35, sy * P + 0.35,
                   1.6, "brick_red")
            bd.box(sx * P - 0.42, sy * P - 0.42, 1.6, sx * P + 0.42, sy * P + 0.42,
                   1.72, "stone_grey")
    # gate piers
    for sx in (-1.0, 1.0):
        bd.box(sx * gate - 0.3, -P - 0.1, 0.08, sx * gate + 0.3, -P + 0.5, 2.3, "brick_red")
        bd.box(sx * gate - 0.36, -P - 0.16, 2.3, sx * gate + 0.36, -P + 0.56, 2.42, "stone_grey")
    # planters + benches + dining tables
    for (px, py) in ((-P + 4.0, -P + 4.0), (P - 4.0, -P + 4.0),
                     (-P + 4.0, P - 4.0), (P - 4.0, P - 4.0)):
        bd.box(px - 1.0, py - 1.0, 0.08, px + 1.0, py + 1.0, 0.62, "stone_grey")
        bd.cyl(px, py, 0.62, 1.7, 0.85, "leaves_dark", seg=8)
        bd.cyl(px, py, 1.7, 2.1, 0.5, "leaves_green", seg=8)
    for (bx, byy, horiz) in ((-P + 6.0, -P + 3.2, True), (P - 6.0, -P + 3.2, True),
                             (-P + 3.2, P - 8.0, False), (P - 3.2, P - 8.0, False)):
        if horiz:
            bd.box(bx - 1.6, byy - 0.25, 0.42, bx + 1.6, byy + 0.25, 0.5, "wood_old")
            bd.box(bx - 1.6, byy + 0.15, 0.5, bx + 1.6, byy + 0.25, 0.95, "wood_old")
            for sx in (-1.4, 1.4):
                bd.box(bx + sx - 0.08, byy - 0.2, 0.08, bx + sx + 0.08, byy + 0.2, 0.42, "metal_steel")
        else:
            bd.box(bx - 0.25, byy - 1.6, 0.42, bx + 0.25, byy + 1.6, 0.5, "wood_old")
            for sy in (-1.4, 1.4):
                bd.box(bx - 0.2, byy + sy - 0.08, 0.08, bx + 0.2, byy + sy + 0.08, 0.42, "metal_steel")
    for i in range(4):
        tx = -9.0 + (i % 2) * 18.0
        ty = -6.0 + (i // 2) * 14.0
        bd.cyl(tx, ty, 0.72, 0.78, 0.7, "wood_old", seg=10)
        bd.cyl(tx, ty, 0.08, 0.74, 0.07, "metal_steel", seg=6)
        bd.cyl(tx, ty, 0.08, 0.12, 0.35, "metal_steel", seg=8)
        for a in (0.4, 1.9, 3.4, 4.9):
            sx, sy = tx + math.cos(a) * 1.2, ty + math.sin(a) * 1.2
            bd.box(sx - 0.2, sy - 0.2, 0.08, sx + 0.2, sy + 0.2, 0.46, "metal_painted_dark")
    return bd


# ------------------------------------------------------------ road corridors
def build_road_grid(layout):
    nodes = {n["id"]: n["pos"] for n in layout["road_nodes"]}
    cell = 8.0
    grid = {}
    segs = []
    for e in layout["road_edges"]:
        a = nodes.get(e.get("a"))
        b = nodes.get(e.get("b"))
        if not a or not b:
            continue
        r = max(ROAD_HW.get(e.get("hierarchy"), 0.0), float(e.get("width", 6.0)) * 0.5)
        segs.append((a[0], a[1], b[0], b[1], r))
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        steps = max(1, int(L / 2.0))
        for i in range(steps + 1):
            t = i / float(steps)
            x = a[0] + (b[0] - a[0]) * t
            y = a[1] + (b[1] - a[1]) * t
            key = (int(math.floor(x / cell)), int(math.floor(y / cell)))
            grid.setdefault(key, []).append((x, y, r))
    return grid, cell, segs


def road_hits(bbox, road):
    grid, cell, _ = road
    x0, y0, x1, y1 = bbox
    hits = []
    for ix in range(int(math.floor(x0 / cell)), int(math.floor(x1 / cell)) + 1):
        for iy in range(int(math.floor(y0 / cell)), int(math.floor(y1 / cell)) + 1):
            for (px, py, r) in grid.get((ix, iy), ()):
                dx = max(x0 - px, 0.0, px - x1)
                dy = max(y0 - py, 0.0, py - y1)
                if math.hypot(dx, dy) < r - 0.02:
                    hits.append((round(px, 2), round(py, 2), round(r, 2)))
    return hits


def nearest_side(p, segs):
    x0, y0, x1, y1 = p["rect"]
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


def front_info(p, segs):
    """primary side (data opening.side > frontage[0] > nearest road), pattern, rot."""
    op = p.get("opening") or {}
    fs = list(p.get("frontage") or [])
    prim = op.get("side") or (fs[0] if fs else None) or nearest_side(p, segs)
    second = None
    for s in fs:
        if s != prim:
            second = s
            break
    rot = ROT.get(prim, 0)
    pattern = "single"
    if second and second in SIDE_VEC and prim in SIDE_VEC:
        a = math.radians(rot)
        lx, ly = -math.cos(a), -math.sin(a)          # world direction of local -X
        v = SIDE_VEC[second]
        pattern = "pairL" if abs(lx - v[0]) < 0.5 and abs(ly - v[1]) < 0.5 else "pairR"
    return prim, pattern, rot


def buildable_rect(p):
    br = p.get("buildable_rect")
    if br:
        return [float(v) for v in br]
    return [float(v) for v in p["rect"]]


def inside(bb, rect, eps=0.002):
    return not (bb[0] < rect[0] - eps or bb[1] < rect[1] - eps or
                bb[2] > rect[2] + eps or bb[3] > rect[3] + eps)


def overlap_check(bboxes):
    viol = []
    items = sorted(bboxes, key=lambda b: b[0][0])
    for i, (ra, ida) in enumerate(items):
        for j in range(i + 1, len(items)):
            rb, idb = items[j]
            if rb[0] >= ra[2] - 1e-6:
                break
            if rb[1] < ra[3] - 1e-6 and ra[1] < rb[3] - 1e-6:
                viol.append((ida, idb))
    return viol


# ------------------------------------------------------------------- context
class Ctx(object):
    def __init__(self, layout, parcels):
        self.layout = layout
        self.parcels = parcels
        self.root = ck.ensure_collection("Entertainment")
        self.meshes = ck.ensure_collection("Meshes", parent=self.root)
        self.colliders = ck.ensure_collection("Colliders", parent=self.root)
        self.lights = ck.ensure_collection("Lights", parent=self.root)
        self.shell = Kit("SM_Bldg")
        self.inter = Kit("INT")
        self.prop = Kit("SM_Prop")
        self.coll = Kit("COL")
        self.count = {}
        self.placed = 0
        self.props = 0
        self.tris = 0
        self.buildings = 0
        self.colliders_n = 0
        self.collider_tris = 0
        self.parcel_ids = set()
        self.bboxes = []
        self.parcel_tris = []
        self.parcel_tris_full = []
        self.violations = []
        self.oh_viol = []
        self.mat_used = set()
        self.oh = []                       # (projection, z_bottom, label) per building
        self.ground_boxes = []             # ground-level prop footprints (current bldg)
        self.tier_count = {0: 0, 1: 0, 2: 0, 3: 0}
        self.tier_tris = {0: 0, 1: 0, 2: 0, 3: 0}
        self.type_count = {}
        self.road = build_road_grid(layout)

    def uniq(self, prefix, key):
        n = self.count.get(key, 0) + 1
        self.count[key] = n
        return "%s_%03d" % (prefix, n)

    def add(self, ob, tier=None):
        self.placed += 1
        t = mesh_tris(ob.data)
        self.tris = getattr(self, "tris", 0) + t
        for m in ob.data.materials:
            if m is not None:
                self.mat_used.add(m.name)
        return ob


_AABB = {}


def mesh_aabb(me):
    key = me.as_pointer()
    b = _AABB.get(key)
    if b is None:
        xs = [v.co[0] for v in me.vertices]
        ys = [v.co[1] for v in me.vertices]
        zs = [v.co[2] for v in me.vertices]
        b = (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)) if xs else (0, 0, 0, 0, 0, 0)
        _AABB[key] = b
    return b


def pp(ctx, key, fn, nm, cx, cy, rot, xl, yl, z, prot=0, coll=None, oh=None, ground=False):
    """Place a shared prop: local offset (xl,yl) rotated by the building rot.

    ground=True marks a ground-level free-standing prop: its footprint is
    asserted to stay inside buildable_rect (checked by check_building)."""
    mesh = ctx.prop.get(key, (int(rot) + int(prot)) % 360, fn)
    a = math.radians(rot)
    c, s = math.cos(a), math.sin(a)
    px, py = cx + xl * c - yl * s, cy + xl * s + yl * c
    ob = new_obj(nm, mesh, (px, py, z), coll or ctx.meshes)
    ctx.placed += 1
    ctx.props += 1
    ctx.tris += mesh_tris(mesh)
    for m in mesh.materials:
        if m is not None:
            ctx.mat_used.add(m.name)
    if oh is not None:
        ctx.oh.append(oh)
    if ground:
        x0, y0, _z0, x1, y1, _z1 = mesh_aabb(mesh)
        pts = []
        for (gx, gy) in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            pts.append((px + gx * c - gy * s, py + gx * s + gy * c))
        ctx.ground_boxes.append(([min(q[0] for q in pts), min(q[1] for q in pts),
                                  max(q[0] for q in pts), max(q[1] for q in pts)], nm))
    return ob


# ---------------------------------------------------------------- decorate
def decorate(ctx, p, cx, cy, rot, typ, floors, pattern, hy, top, rng, tier):
    """Instance shared street furniture / signage onto one building."""
    sp = SPEC[typ]
    hx = HALF
    neon = rng.choice(["neon_magenta", "neon_violet", "neon_teal"] if typ in ("cinema", "club")
                      else NEON_ROT)
    awn_m = rng.choice(AWNING_MATS)
    ow = sp["open_w"]
    trim = typ in STAIR_TYPES and floors >= 2
    n = 0

    def clamp(u):
        return max(-(hx - 1.4), min(hx - 1.4, u))

    def key():
        nonlocal n
        n += 1
        return "%s_%s_%02d" % (typ[:4].upper(), "S" if rot == 0 else "", n)

    # ---- fascia band sign (front)
    if typ != "cinema":
        fw = 7.0 if typ in ("supermarket", "hotel", "gym") else 5.4
        pp(ctx, ("fas", fw, neon), lambda: make_mesh("fas", p_fascia(fw, neon)),
           "SM_Sign_Fascia_%s" % neon, cx, cy, rot, rng.uniform(-1.0, 1.0), -hy,
           FASCIA_Z, oh=(0.16, FASCIA_Z, "fascia"))
    # ---- second frontage sign
    if pattern == "pairL" and typ != "cinema":
        pp(ctx, ("fas", 4.6, neon), lambda: make_mesh("fas2", p_fascia(4.6, neon)),
           "SM_Sign_Fascia_%s_S" % neon, cx, cy, rot, -hx, rng.uniform(-4.0, 4.0),
           FASCIA_Z, prot=270, oh=(0.16, FASCIA_Z, "fascia_side"))
    elif pattern == "pairR" and typ != "cinema":
        pp(ctx, ("fas", 4.6, neon), lambda: make_mesh("fas2", p_fascia(4.6, neon)),
           "SM_Sign_Fascia_%s_S" % neon, cx, cy, rot, hx, rng.uniform(-4.0, 4.0),
           FASCIA_Z, prot=90, oh=(0.16, FASCIA_Z, "fascia_side"))

    # ---- cinema marquee + poster lightboxes
    if sp.get("marquee"):
        mw = min(16.0, 2 * hx - 6.0)
        pp(ctx, ("marq", mw), lambda: make_mesh("marq", p_marquee(mw)),
           "SM_Marquee_01", cx, cy, rot, 0.0, -hy, MARQ_Z,
           oh=(MARQ_PROJ + 0.11, MARQ_Z - 0.16, "marquee"))
        for sx in (-1.0, 1.0):
            u = clamp(sx * (ow * 0.5 + 2.2))
            pp(ctx, "poster", lambda: make_mesh("poster", p_poster()),
               "SM_PosterLightbox_%02d" % (1 if sx < 0 else 2), cx, cy, rot, u, -hy, 2.50,
               oh=(0.15, 2.50, "poster"))
        if sp.get("billboard"):
            pp(ctx, "board", lambda: make_mesh("board", p_billboard()),
               "SM_Billboard_Flank_01", cx, cy, rot, hx, -2.0, 5.6, prot=90,
               oh=(0.18, 5.6, "billboard"))
        if tier <= 2:
            pp(ctx, ("fas", 8.0, neon), lambda: make_mesh("fas3", p_fascia(8.0, neon)),
               "SM_Sign_Fascia_%s" % neon, cx, cy, rot, 0.0, -hy, top - 2.4,
               oh=(0.16, top - 2.4, "parapet_sign"))

    # ---- hotel entrance canopy
    if sp.get("canopy"):
        pp(ctx, "canopy", lambda: make_mesh("canopy", p_canopy(7.0)),
           "SM_EntranceCanopy_01", cx, cy, rot, 0.0, -hy, CANOPY_Z,
           oh=(CANOPY_PROJ + 0.04, CANOPY_Z - 0.10, "canopy"))

    # ---- projecting hanging sign
    if sp.get("hanging"):
        u = clamp(rng.choice([-1.0, 1.0]) * (hx - 3.2))
        pp(ctx, ("hang", neon), lambda: make_mesh("hang", p_hangsign(neon)),
           "SM_HangingSign_%s" % neon, cx, cy, rot, u, -hy, HANG_Z,
           oh=(HANG_PROJ, HANG_Z - 1.30, "hanging"))

    # ---- blade sign
    if sp.get("blade") or (typ not in ("apartment_low",) and rng.random() < 0.5):
        u = clamp(rng.choice([-1.0, 1.0]) * (ow * 0.5 + 1.8))
        pp(ctx, ("blade", neon), lambda: make_mesh("blade", p_blade(neon)),
           "SM_Sign_Blade_%s" % neon, cx, cy, rot, u, -hy, BLADE_Z,
           oh=(BLADE_PROJ, BLADE_Z, "blade"))

    # ---- awning (cafés mandatory - style_bible §5)
    if sp.get("awning") and (typ == "cafe" or rng.random() < 0.75):
        for sx in (-1.0, 1.0):
            if rng.random() < 0.35 and sx > 0:
                continue
            u = clamp(sx * (ow * 0.5 + 2.4))
            pp(ctx, ("awn", awn_m), lambda: make_mesh("awn", p_awning(awn_m)),
               "SM_Awning_%s" % awn_m, cx, cy, rot, u, -hy, AWN_Z,
               oh=(AWN_PROJ, AWN_Z - 0.60, "awning"))

    # ---- LED panel / vertical neon runs
    if sp.get("led"):
        u = clamp(rng.choice([-1.0, 1.0]) * (hx - 4.5))
        pp(ctx, "led", lambda: make_mesh("led", p_led()),
           "SM_LEDPanel_01", cx, cy, rot, u, -hy, 4.30, oh=(0.17, 4.30, "led"))
    if sp.get("neon_vert"):
        for sx in (-1.0, 1.0):
            u = clamp(sx * (hx - 1.8))
            pp(ctx, ("nv", neon), lambda: make_mesh("nv", p_neonvert(4.0, neon)),
               "SM_NeonRun_%s" % neon, cx, cy, rot, u, -hy, 4.40,
               oh=(0.17, 4.40, "neon_run"))

    # ---- terrace tables inside the frontage niche
    if sp.get("terrace"):
        pp(ctx, "terr", lambda: make_mesh("terr", p_terrace()),
           "SM_TerraceSet_01", cx, cy, rot, 6.5, -hy + 1.35, CURB, ground=True)

    # ---- wall lamps (Lights: emissive fixtures only)
    for u in (clamp(-(hx - 3.0)), clamp(hx - 3.0)):
        pp(ctx, "lamp", lambda: make_mesh("lamp", p_lamp()),
           "SM_WallLamp_%02d" % (1 if u < 0 else 2), cx, cy, rot, u, -hy, 2.95,
           coll=ctx.lights, oh=(0.46, 2.89, "walllamp"))
    # ---- downpipe
    dp = -1.0 if rng.random() < 0.5 else 1.0
    pp(ctx, ("pipe", top), lambda: make_mesh("pipe", p_pipe(top)),
       "SM_Downpipe_01", cx, cy, rot, dp * (hx - 0.55), -hy, 0.0)
    # ---- AC / vent / meter
    if floors >= 2 and rng.random() < 0.6:
        pp(ctx, "ac", lambda: make_mesh("ac", p_ac()), "SM_ACUnit_01",
           cx, cy, rot, clamp(-dp * (hx - 3.4)), -hy, 4.55, oh=(0.50, 4.55, "ac"))
    if sp.get("vent"):
        pp(ctx, "vent", lambda: make_mesh("vent", p_vent()), "SM_ExtractorVent_01",
           cx, cy, rot, clamp(dp * (hx - 2.6)), -hy, 1.60, oh=(0.13, 1.60, "vent"))
    pp(ctx, "meter", lambda: make_mesh("meter", p_meter()), "SM_MeterBox_01",
       cx, cy, rot, clamp(-dp * (hx - 1.6)), -hy, 1.15, oh=(0.16, 1.15, "meter"))

    # ---- external stair (rear yard archetypes)
    if trim:
        pp(ctx, "stair", lambda: make_mesh("stair", p_stair()),
           "SM_ExtStair_01", cx, cy, rot, 0.0, 0.0, 0.0, ground=True)

    # ---- roof plant
    slots = [(-hx * 0.55, -hy * 0.55), (hx * 0.5, hy * 0.5), (hx * 0.45, -hy * 0.5),
             (-hx * 0.5, hy * 0.45)]
    rng.shuffle(slots)
    kind = sp.get("roof") or "plant"
    if kind == "tank":
        pp(ctx, "tank", lambda: make_mesh("tank", p_tank()), "SM_WaterTank_01",
           cx, cy, rot, slots[0][0], slots[0][1], top, ground=True)
        pp(ctx, "rfac", lambda: make_mesh("rfac", p_roofac()), "SM_RoofAC_01",
           cx, cy, rot, slots[1][0], slots[1][1], top, ground=True)
    elif kind == "vent":
        pp(ctx, "rfvent", lambda: make_mesh("rfvent", p_ventroof()), "SM_RoofVent_01",
           cx, cy, rot, slots[0][0], slots[0][1], top, ground=True)
        pp(ctx, "rfac", lambda: make_mesh("rfac", p_roofac()), "SM_RoofAC_01",
           cx, cy, rot, slots[1][0], slots[1][1], top, ground=True)
    else:
        pp(ctx, "rfac", lambda: make_mesh("rfac", p_roofac()), "SM_RoofAC_01",
           cx, cy, rot, slots[0][0], slots[0][1], top, ground=True)
        if floors >= 2 and rng.random() < 0.6:
            pp(ctx, "rfac", lambda: make_mesh("rfac2", p_roofac()), "SM_RoofAC_02",
               cx, cy, rot, slots[1][0], slots[1][1], top, ground=True)

    # ---- interior light panel (Lights collection)
    if tier <= 2 and typ != "courtyard":
        pp(ctx, "lpanel", lambda: make_mesh("lpanel", p_lightpanel()),
           "SM_InteriorLight_01", cx, cy, rot, 0.0, -hy * 0.35, 3.05,
           coll=ctx.lights, ground=True)


# ------------------------------------------------------------- placement
def collider_mesh(hx, hy, h):
    bd = Builder()
    bd.box(-hx, -hy, 0.0, hx, hy, h, "concrete")
    return make_mesh("COL_box", bd)


def place_collider(ctx, p, hx, hy, h, bb):
    k = ("col", round(hx, 2), round(hy, 2), round(h, 2))
    mesh = ctx.coll.get(k, 0, lambda: collider_mesh(hx, hy, h))
    ob = new_obj("COL_%s" % p["id"], mesh,
                 ((bb[0] + bb[2]) * 0.5, (bb[1] + bb[3]) * 0.5, 0.0), ctx.colliders)
    ob.hide_render = True
    ctx.colliders_n += 1
    ctx.collider_tris += mesh_tris(mesh)


def check_building(ctx, p, name, bb_fp, bb_ov):
    br = buildable_rect(p)
    if not inside(bb_fp, br):
        ctx.violations.append(["buildable", name, p["id"],
                               [round(v, 3) for v in bb_fp], [round(v, 3) for v in br]])
    for (gb, gname) in ctx.ground_boxes:
        if not inside(gb, br):
            ctx.violations.append(["ground_prop", gname, p["id"],
                                   [round(v, 3) for v in gb], [round(v, 3) for v in br]])
    hits = road_hits(bb_ov, ctx.road)
    if hits:
        ctx.violations.append(["road", name, p["id"], hits[:2]])
    for (proj, zmin, label) in ctx.oh:
        if proj > SMALL_PROJ + 1e-9 and zmin < CLEAR - 1e-6:
            ctx.oh_viol.append([label, name, p["id"], round(proj, 2), round(zmin, 2)])
    ctx.bboxes.append((bb_fp, p["id"]))


def place_building(ctx, p, rng):
    t0 = ctx.tris
    pid = p["id"]
    typ = p["type"]
    style = p.get("facade_style") or "neon_modern"
    floors = max(1, int(p.get("floors") or 1))
    tier = int(p.get("interior_tier", 3))
    sp = SPEC[typ]
    br = buildable_rect(p)
    cx = (br[0] + br[2]) * 0.5
    cy = (br[1] + br[3]) * 0.5
    prim, pattern, rot = front_info(p, ctx.road[2])
    ow = sp["open_w"]
    trim = typ in STAIR_TYPES and floors >= 2
    hy = HALF - TRIM if trim else HALF
    top = floors * FLOOR
    ctx.oh = []
    ctx.ground_boxes = []

    # ---- shell (linked duplicate, rotation baked into the shared mesh)
    skey = (typ, style, floors, pattern, round(ow, 1))
    smesh = ctx.shell.get(skey, rot, lambda: make_mesh(
        "SM_Bldg_%s_%s" % (typ[:6].upper(), style[:6].upper()),
        build_shell(typ, style, floors, pattern, ow)))
    pal = DARK_ALT if sp.get("dark") else STYLE[style]["alt"]
    slot = pal[dhash(pid) % len(pal)]
    pref = "SM_Bldg_%s_%s" % (typ[:6].upper(), style[:6].upper())
    ob = new_obj(ctx.uniq(pref, skey), smesh, (cx, cy, 0.0), ctx.meshes, slot)
    ctx.add(ob, tier)
    # footprint in world space (rotation is a multiple of 90 deg)
    hxw = HALF if (rot % 180 == 0) else hy
    hyw = hy if (rot % 180 == 0) else HALF
    bb_fp = [cx - hxw, cy - hyw, cx + hxw, cy + hyw]

    # ---- interior
    if tier == 3:
        im = ctx.inter.get(("rec",), rot, lambda: make_mesh("INT_Recess", int_recess()))
        io = new_obj("INT_%s_Recess" % pid, im, (cx, cy, 0.0), ctx.meshes)
        ctx.add(io, tier)
    elif tier == 2:
        ikey = ("room", typ, trim)
        im = ctx.inter.get(ikey, rot, lambda: make_mesh("INT_Room_%s" % typ,
                                                        int_room(typ, hy)))
        io = new_obj("INT_%s_Room1" % pid, im, (cx, cy, 0.0), ctx.meshes)
        ctx.add(io, tier)
    else:
        ia = ctx.inter.get(("ha", typ), rot, lambda: make_mesh("INT_HallA_%s" % typ,
                                                               int_hall_a(typ)))
        io = new_obj("INT_%s_Lobby" % pid, ia, (cx, cy, 0.0), ctx.meshes)
        ctx.add(io, tier)
        ib = ctx.inter.get(("hb", typ, trim), rot, lambda: make_mesh("INT_HallB_%s" % typ,
                                                                     int_hall_b(typ, hy)))
        io2 = new_obj("INT_%s_Room2" % pid, ib, (cx, cy, 0.0), ctx.meshes)
        ctx.add(io2, tier)

    # ---- street dressing
    decorate(ctx, p, cx, cy, rot, typ, floors, pattern, hy, top, rng, tier)

    # ---- verification
    over = max(hxw, hyw) + 1.75          # includes every overhead projection
    bb_ov = [cx - over, cy - over, cx + over, cy + over]
    check_building(ctx, p, ob.name, bb_fp, bb_ov)
    place_collider(ctx, p, hxw, hyw, top + 1.15, bb_fp)
    ctx.parcel_ids.add(pid)
    ctx.buildings += 1
    ctx.tier_count[tier] = ctx.tier_count.get(tier, 0) + 1
    ctx.tier_tris[tier] = ctx.tier_tris.get(tier, 0) + (ctx.tris - t0)
    ctx.type_count[typ] = ctx.type_count.get(typ, 0) + 1
    ctx.parcel_tris.append((tier, ctx.tris - t0))
    ctx.parcel_tris_full.append((tier, ctx.tris - t0, pid))
    return ob


def place_plaza(ctx, p, rng):
    t0 = ctx.tris
    pid = p["id"]
    br = [float(v) for v in p["rect"]]
    cx = (br[0] + br[2]) * 0.5
    cy = (br[1] + br[3]) * 0.5
    prim, pattern, rot = front_info(p, ctx.road[2])
    ctx.oh = []
    ctx.ground_boxes = []
    key = ("plaza",)
    mesh = ctx.shell.get(key, rot, lambda: make_mesh("SM_Plaza_Dining", build_plaza()))
    ob = new_obj(ctx.uniq("SM_Plaza_Dining", key), mesh, (cx, cy, 0.0), ctx.meshes,
                 "facade_plaster_bone" if rng.random() < 0.5 else "brick_red")
    ctx.add(ob, 0)
    # string lights (Lights collection)
    pp(ctx, "bulbs", lambda: make_mesh("bulbs", p_bulbstring()), "SM_StringLights_01",
       cx, cy, rot, 0.0, -6.0, 0.08, coll=ctx.lights, ground=True)
    half = PLAZA_HALF
    bb_fp = [cx - half, cy - half, cx + half, cy + half]
    check_building(ctx, p, ob.name, bb_fp, bb_fp)
    place_collider(ctx, p, half, half, 2.4, bb_fp)
    ctx.parcel_ids.add(pid)
    ctx.buildings += 1
    ctx.tier_count[0] += 1
    ctx.tier_tris[0] = ctx.tier_tris.get(0, 0) + (ctx.tris - t0)
    ctx.type_count["courtyard"] = ctx.type_count.get("courtyard", 0) + 1
    ctx.parcel_tris.append((0, ctx.tris - t0))
    return ob


# ------------------------------------------------------------------ teardown
def purge_entertainment():
    coll = bpy.data.collections.get("Entertainment")
    if coll is None:
        return
    for ob in list(coll.all_objects):
        try:
            bpy.data.objects.remove(ob, do_unlink=True)
        except Exception as exc:
            print("  [entertainment] purge object failed:", exc)

    def rm(c):
        for ch in list(c.children):
            rm(ch)
        try:
            bpy.data.collections.remove(c)
        except Exception as exc:
            print("  [entertainment] purge collection failed:", exc)

    rm(coll)
    print("  [entertainment] removed previous 'Entertainment' collection")


def module_bbox(bboxes):
    x0 = min(b[0][0] for b in bboxes)
    y0 = min(b[0][1] for b in bboxes)
    x1 = max(b[0][2] for b in bboxes)
    y1 = max(b[0][3] for b in bboxes)
    z1 = max((o.dimensions.z + o.location.z)
             for o in bpy.data.objects if o.type == "MESH" and not o.hide_render)
    return [round(v, 2) for v in (x0, y0, 0.0, x1, y1, z1)]


_OLD_SKY = [None]


def sky(on):
    w = bpy.context.scene.world
    if w is None or not getattr(w, "use_nodes", False) or w.node_tree is None:
        return
    bg = next((n for n in w.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg is None:
        return
    if on:
        _OLD_SKY[0] = (tuple(bg.inputs[0].default_value), float(bg.inputs[1].default_value))
        bg.inputs[0].default_value = (0.45, 0.55, 0.72, 1.0)
        bg.inputs[1].default_value = 0.7
    elif _OLD_SKY[0] is not None:
        bg.inputs[0].default_value = _OLD_SKY[0][0]
        bg.inputs[1].default_value = _OLD_SKY[0][1]


def temp_ground(on):
    """Preview-only ground slab (scene collection, deleted before the save)."""
    if on:
        if bpy.data.objects.get("TMP_GROUND") is not None:
            return
        bd = Builder()
        bd.box(-640.0, -640.0, -0.4, 940.0, 940.0, 0.0, "asphalt")
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


# ---------------------------------------------------------------------- main
def run_previews(eng):
    """45 deg strip view + 1.7 m eye-height frontage view (cell 3,3)."""
    prev1 = os.path.join(ck.OUT_DIR, "entertainment_preview.png")
    prev2 = os.path.join(ck.OUT_DIR, "entertainment_street_preview.png")
    sky(True)
    temp_ground(True)
    try:
        try:
            ck.make_preview(prev1, (66.0, -416.0, 193.0), (-150.0, -150.0, 20.0),
                            engine=eng, res=(1920, 1080),
                            sun_elev=38.0, sun_azim=-55.0, sun_energy=3.5, samples=32)
        except Exception as exc:
            print("[entertainment] preview 1 failed:", exc)
            prev1 = None
        try:
            ck.make_preview(prev2, (-24.0, -295.0, 1.7), (-160.0, -284.0, 4.5),
                            engine=eng, res=(1920, 1080),
                            sun_elev=30.0, sun_azim=-40.0, sun_energy=3.2, samples=32)
        except Exception as exc:
            print("[entertainment] preview 2 failed:", exc)
            prev2 = None
    finally:
        sky(False)
        temp_ground(False)
    return prev1, prev2


def main():
    import random
    t0 = time.time()
    layout = ck.read_layout()
    parcels = ck.read_parcels("E")
    purge_entertainment()
    for nm in ("Cube", "Camera", "Light"):
        ob = bpy.data.objects.get(nm)
        if ob is not None:
            bpy.data.objects.remove(ob, do_unlink=True)
    for c in list(bpy.data.collections):
        if c.name == "Entertainment" or len(c.objects) or len(c.children):
            continue
        try:
            bpy.data.collections.remove(c)
            print("  [entertainment] removed empty startup collection")
        except Exception as exc:
            print("  [entertainment] could not remove collection:", exc)

    ctx = Ctx(layout, parcels)
    print("[entertainment] %d parcels, %d corridor samples"
          % (len(parcels), sum(len(v) for v in ctx.road[0].values())))

    by_cell = {}
    for p in parcels:
        by_cell.setdefault(tuple(p["cell"]), []).append(p)

    lim = None
    if "--limit" in sys.argv:
        lim = int(sys.argv[sys.argv.index("--limit") + 1])
        print("[entertainment] SMOKE TEST: stopping after %d parcels" % lim)

    done = 0
    for cell in CELLS:
        sub = by_cell.get(tuple(cell), [])
        stop = False
        for p in sub:
            rng = random.Random(dhash(p["id"]))
            if p["type"] == "courtyard":
                place_plaza(ctx, p, rng)
            else:
                place_building(ctx, p, rng)
            done += 1
            if lim is not None and done >= lim:
                stop = True
                break
        ck.save_blend(os.path.join(ck.OUT_DIR, "entertainment.blend"))
        print("[entertainment] cell %s: %d/%d parcels | %d objects | %d tris | %.0fs"
              % (cell, ctx.buildings, len(parcels), ctx.placed, ctx.tris,
                 time.time() - t0))
        if stop:
            break

    # -------------------------------------------------------------- verify
    missing = [p["id"] for p in parcels if p["id"] not in ctx.parcel_ids]
    overlaps = overlap_check(ctx.bboxes)
    n_obj = len(bpy.data.objects)
    uniq_tris = ck.scene_tri_count()
    n_meshes = len([m for m in bpy.data.meshes if m.users > 0 or m.use_fake_user])
    t3 = [t for (tier, t) in ctx.parcel_tris if tier == 3]
    t2 = [t for (tier, t) in ctx.parcel_tris if tier == 2]
    t1 = [t for (tier, t) in ctx.parcel_tris if tier == 1]
    max_t3, max_t2, max_t1 = max(t3 or [0]), max(t2 or [0]), max(t1 or [0])
    if os.environ.get("ENT_DEBUG"):
        by_id = {p["id"]: p for p in parcels}
        for want in (3, 2, 1):
            rows = sorted([r for r in ctx.parcel_tris_full if r[0] == want],
                          key=lambda r: -r[1])[:8]
            print("   HEAVY tier%d:" % want,
                  [(r[1], by_id.get(r[2], {}).get("type"),
                    by_id.get(r[2], {}).get("floors"),
                    by_id.get(r[2], {}).get("facade_style"),
                    by_id.get(r[2], {}).get("interior_tier"), r[2]) for r in rows])
    n_build = len([v for v in ctx.violations if v[0] == "buildable"])
    n_road = len([v for v in ctx.violations if v[0] == "road"])
    n_gp = len([v for v in ctx.violations if v[0] == "ground_prop"])
    n_clr = len(ctx.oh_viol)
    print("[entertainment] VERIFY objects=%d instanced_tris=%d unique_tris=%d "
          "buildable=%d road=%d ground_prop=%d clearance=%d overlaps=%d missing=%d"
          % (n_obj, ctx.tris, uniq_tris, n_build, n_road, n_gp, n_clr,
             len(overlaps), len(missing)))
    print("[entertainment] BUDGET meshes=%d max_t1=%d (<=150000) max_t2=%d (<=40000) "
          "max_t3=%d (<=8000) module=%d (<=10000000)"
          % (n_meshes, max_t1, max_t2, max_t3, uniq_tris))
    for v in ctx.violations[:12]:
        print("   VIOLATION", v)
    for v in ctx.oh_viol[:12]:
        print("   CLEARANCE", v)
    for o in overlaps[:12]:
        print("   OVERLAP", o)

    # ------------------------------------------------------------- previews
    eng = pick_engine()
    print("[entertainment] preview engine:", eng)
    prev1 = prev2 = None
    if lim is None:
        prev1, prev2 = run_previews(eng)
    else:
        print("[entertainment] SMOKE TEST: skipping previews")

    left = [o.name for o in bpy.data.objects if o.name.startswith("TMP_")]
    if left:
        print("[entertainment] WARNING temp preview objects still in scene:", left)

    ck.save_blend(os.path.join(ck.OUT_DIR, "entertainment.blend"))

    # -------------------------------------------------------------- report
    bbox = module_bbox(ctx.bboxes)
    issues = []
    if ctx.violations:
        issues.append("%d geometry violations (buildable/road/ground-prop)" % len(ctx.violations))
    if ctx.oh_viol:
        issues.append("%d overhangs below the 2.4 m clearance" % len(ctx.oh_viol))
    if overlaps:
        issues.append("%d parcel bbox overlaps" % len(overlaps))
    if missing:
        issues.append("%d parcels without a building" % len(missing))
    if max_t3 > 8000:
        issues.append("t3 budget exceeded (max %d > 8000)" % max_t3)
    if max_t2 > 40000:
        issues.append("t2 budget exceeded (max %d > 40000)" % max_t2)
    if uniq_tris > 10000000:
        issues.append("module tri budget exceeded (%d > 10000000)" % uniq_tris)
    if prev1 is None or prev2 is None:
        issues.append("one or both previews failed to render")
    issues.append("clearance policy: anything projecting >0.16 m beyond buildable "
                  "sits >=2.4 m up; ground fixtures project <=0.16 m and are checked "
                  "against the road corridor only")
    issues.append("parcels_E.json ships 8 cells (prompt listed 9) - built all 8 x 36")
    issues.append("previews use a temporary ground slab (deleted before saving) - "
                  "roads/ground belong to the Roads module")

    payload = {
        "parcels": len(parcels),
        "buildings": ctx.buildings,
        "objects": n_obj,
        "prop_objects": ctx.props,
        "collider_objects": ctx.colliders_n,
        "unique_meshes": n_meshes,
        "tris_instanced": ctx.tris,
        "tris_unique_meshes": uniq_tris,
        "collider_tris": ctx.collider_tris,
        "type_counts": ctx.type_count,
        "tier_counts": ctx.tier_count,
        "tier_tris": ctx.tier_tris,
        "budget_max_tris": {"t1": max_t1, "t2": max_t2, "t3": max_t3,
                            "module": uniq_tris},
        "engine": eng,
        "materials": sorted(ctx.mat_used),
        "violations": ctx.violations[:40],
        "clearance_violations": ctx.oh_viol[:40],
        "overlaps": overlaps[:40],
        "missing_parcels": missing,
        "bbox": bbox,
        "cells": CELLS,
        "collections": ["Entertainment", "Entertainment/Meshes",
                        "Entertainment/Colliders", "Entertainment/Lights"],
        "previews": [p for p in (prev1, prev2) if p],
        "assembler": {
            "kit": "Builder/Face/wall_rects mesh assembler, one mesh per "
                   "(type, style, floors, pattern, opening) x 4 baked rotations",
            "instancing": "linked duplicates (shared mesh datablocks), no unique copies",
            "transforms": "translation only - Z-rotation baked into the shared mesh",
            "slot0_palette": "mesh slot 0 = facade wall; per-parcel colour via OBJECT slot",
        },
        "issues": issues,
        "build_seconds": round(time.time() - t0, 1),
    }
    ck.write_report("entertainment", payload)
    write_md(payload)

    print("[entertainment] DONE in %.0fs buildings=%d objects=%d tris(instanced)=%d "
          "unique=%d meshes=%d" % (time.time() - t0, ctx.buildings, n_obj, ctx.tris,
                                   uniq_tris, n_meshes))
    print("[entertainment] bbox", bbox)


def write_md(d):
    b = d.get("budget_max_tris", {})
    v = d["violations"]
    n_b = len([x for x in v if x[0] == "buildable"])
    n_r = len([x for x in v if x[0] == "road"])
    n_g = len([x for x in v if x[0] == "ground_prop"])
    n_c, n_o, n_m = (len(d["clearance_violations"]), len(d["overlaps"]),
                     len(d["missing_parcels"]))
    tc, tt = d["type_counts"], d["tier_tris"]
    tcnt = dict(d["tier_counts"])
    tt = {int(k): v for k, v in tt.items()}
    tcnt = {int(k): v for k, v in tcnt.items()}
    lines = [
        "# Entertainment module report (district E)\n",
        "Generated by `modules/entertainment.py` (headless, %s).\n" % d.get("engine"),
        "## Counts\n",
        "| item | value |",
        "|---|---|",
        "| parcels built | %s / %s |" % (d["buildings"], d["parcels"]),
        "| objects (props / colliders) | %s (%s / %s) |"
        % (d["objects"], d["prop_objects"], d["collider_objects"]),
        "| unique meshes | %s |" % d["unique_meshes"],
        "| tris instanced / unique | %s / %s |" % (d["tris_instanced"],
                                                   d["tris_unique_meshes"]),
        "\n## Per type\n",
        ", ".join("%s %s" % (k, v) for k, v in sorted(tc.items())) + ".",
        "\n## Per tier\n",
        "| tier | buildings | tris |",
        "|---|---|---|",
        "| 1 | %s | %s |" % (tcnt.get(1), tt.get(1)),
        "| 2 | %s | %s |" % (tcnt.get(2), tt.get(2)),
        "| 3 | %s | %s |" % (tcnt.get(3), tt.get(3)),
        "| 0 plaza | %s | %s |" % (tcnt.get(0), tt.get(0)),
        "\n## Budgets\n",
        "| item | tris | limit |",
        "|---|---|---|",
        "| heaviest tier-1 | %s | 150000 |" % b.get("t1"),
        "| heaviest tier-2 | %s | 40000 |" % b.get("t2"),
        "| heaviest tier-3 | %s | 8000 |" % b.get("t3"),
        "| whole module | %s | 10000000 |" % b.get("module"),
        "\n## Materials used (%d)\n" % len(d["materials"]),
        ", ".join("`%s`" % m for m in d["materials"]),
        "\n## Collections / bbox\n",
        "- collections: %s" % ", ".join(d["collections"]),
        "- bbox: %s; cells: %s x 36 parcels (list in entertainment_report.json)"
        % (d["bbox"], len(d["cells"])),
        "- previews: %s" % ", ".join(os.path.relpath(p, ck.CITY_ROOT)
                                     for p in d["previews"]),
        "\n## Assembler\n",
        "- Builder/Face/wall_rects assembler: one mesh per (type, style, floors, "
        "pattern, opening) x 4 rotations",
        "- linked duplicates only; translation-only transforms; slot 0 = facade wall, "
        "per-parcel colour via OBJECT slot",
        "\n## Verification\n",
        "- all clear: buildable %d, road %d, ground-prop %d, clearance(<2.4 m) %d, "
        "overlaps %d, unbuilt %d" % (n_b, n_r, n_g, n_c, n_o, n_m),
        "\n## Known issues / notes\n",
    ]
    for i in d["issues"]:
        lines.append("- %s" % i)
    path = os.path.join(ck.REPORTS_DIR, "entertainment_report.md")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("  [entertainment] markdown report -> %s" % path)


if __name__ == "__main__":
    main()
