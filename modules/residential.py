#!/usr/bin/env python3
"""residential.py - Residential district (R) building kit for the 3x3 km AAA city.

Headless run:
    cd /home/abdulhadi/Work/city && timeout 5400 blender -b -P modules/residential.py

Builds all 844 parcels of parcels_R.json as linked-duplicate archetype meshes:

    house (484)          detached / terraced house, 1-2 floors, garden + fence
    house_large (128)    villa, 2-3 floors, driveway + garage + garden wall
    apartment_low (147)  3-5 floor walk-up with balconies, flat parapet roof
    corner_shop (9)      shop-house, open frontage + awning + fascia sign
    courtyard (64)       walled garden courtyard with an annex house
    pocket_park (12)     fenced green with a pavilion (the parcel "building")

Every kit piece keeps its origin at bottom-centre; instanced meshes are shared
(one mesh per archetype signature x 4 baked rotations) and objects carry a pure
translation (scale 1). Re-runnable: the `Residential` collection is deleted
first and the blend is re-saved after every cell.
"""
from __future__ import annotations

import json
import math
import os
import random
import sys
import time

ROOT = "/home/abdulhadi/Work/city"
if ROOT not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "modules"))

import citykit as ck          # noqa: E402
import bpy                    # noqa: E402

# ------------------------------------------------------------------ constants
CURB = 0.15                  # plinth / curb height (scale rule)
DOOR_H = 2.4                 # door / opening head (scale rule)
EAVE = 0.45                  # pitched-roof eave overhang
FIN = 0.6                    # fence inset from the lot edge (off the road corridor)
GIN = 0.3                    # garden ground inset from the lot edge
SETBACK_LOT = 3.0            # generate_layout.py R setback -> buildable_rect
WALL_T = 0.20                # reveal depth behind the facade plane
BAL_P = 1.1                  # balcony projection (<= 1.2)
ROT = {"N": 0, "E": 270, "S": 180, "W": 90}
VEC = {"N": (0.0, 1.0), "E": (1.0, 0.0), "S": (0.0, -1.0), "W": (-1.0, 0.0)}
OUT_BLEND = os.path.join(ck.OUT_DIR, "residential.blend")
PREV1 = os.path.join(ck.OUT_DIR, "residential_preview.png")
PREV2 = os.path.join(ck.OUT_DIR, "residential_street_preview.png")

# ------------------------------------------------------- facade style bible R
# spacing = bay module, w/h = window size, sill = sill height above floor level
STYLE = {
    "suburban_brick": dict(
        spacing=3.4, w=1.2, sill=0.9, h=1.6, arch=False, pair=False,
        wall="facade_brick_red", roofmat="roof_clay_tile", roof="pitched",
        frame="wood_painted", shutter=None, trim="stone_grey", glass="glass_dark"),
    "stucco_modern": dict(
        spacing=4.2, w=2.6, sill=1.1, h=1.5, arch=False, pair=False,
        wall="facade_plaster_bone", roofmat="roof_bitumen", roof="flat",
        frame="metal_painted_charcoal", shutter=None, trim="stone_grey",
        glass="glass_dark"),
    "timber_cottage": dict(
        spacing=3.6, w=0.9, sill=1.0, h=1.5, arch=False, pair=True,
        wall="facade_timber_cladding", roofmat="roof_clay_tile", roof="pitched",
        frame="wood_painted", shutter="wood_painted", trim="stone_grey",
        glass="glass_dark"),
    "modern_minimal": dict(
        spacing=3.0, w=2.8, sill=0.4, h=2.5, arch=False, pair=False,
        wall="facade_plaster_stone", roofmat="roof_bitumen", roof="flat",
        frame="metal_painted_charcoal", shutter=None, trim="concrete",
        glass="glass_dark"),
}
STYLES = list(STYLE)

# per-parcel facade colour: one palette colour per street run (style_bible 5R)
PALETTE = {
    "suburban_brick": ["facade_brick_red"],
    "stucco_modern": ["facade_plaster_bone", "facade_plaster_sand",
                      "facade_plaster_sage", "facade_plaster_terracotta"],
    "timber_cottage": ["facade_timber_cladding"],
    "modern_minimal": ["facade_plaster_stone", "facade_plaster_bone",
                       "facade_plaster_sand"],
}

# footprint variants (W across the front x D deep), all inside the 27 m buildable
SIZES = {
    "house": [(13.0, 10.0), (11.5, 10.5)],
    "house_large": [(16.5, 13.0), (15.0, 14.5)],
    "apartment_low": [(21.0, 17.0), (19.0, 18.5)],
    "corner_shop": [(20.0, 15.0), (18.0, 16.0)],
}
# front setback range / side / back clearances (metres, inside buildable_rect)
TPAR = {
    "house": dict(sf=(5.0, 7.5), sb=3.5, ss=3.0, sec=3.5, garage=False),
    "house_large": dict(sf=(3.5, 5.5), sb=3.0, ss=3.0, sec=3.5, garage=True),
    "apartment_low": dict(sf=(3.0, 4.5), sb=3.0, ss=3.0, sec=3.5, garage=False),
    "corner_shop": dict(sf=(1.2, 1.8), sb=4.0, ss=3.0, sec=2.0, garage=False),
}
GARAGE = (3.6, 5.5, 2.6)     # W x D x H


def dhash(s):
    h = 2166136261
    for ch in str(s):
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def local_side(world_side, rot):
    """Which local direction (F/B/L/R) a compass side maps to at rotation `rot`."""
    vx, vy = VEC[world_side]
    a = math.radians(rot)
    c, s = math.cos(-a), math.sin(-a)
    lx, ly = vx * c - vy * s, vx * s + vy * c
    if abs(ly) >= abs(lx):
        return "F" if ly > 0 else "B"
    return "R" if lx > 0 else "L"


# ------------------------------------------------------------ wall decomposition
def wall_rects(u0, u1, z0, z1, ops):
    """Decompose a wall rectangle into solid rects around `ops` openings.

    op = dict(u0,u1,z0,z1[,arch]) -- arch means the top of the void is a
    semicircle of radius (u1-u0)/2 whose springline sits at z1-r.
    """
    zs = {z0, z1}
    for o in ops:
        zs.add(max(z0, o["z0"]))
        zs.add(min(z1, o["z1"]))
        if o.get("arch"):
            r = (o["u1"] - o["u0"]) * 0.5
            zs.add(min(z1, max(z0, o["z1"] - r)))
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
            if o.get("arch"):
                r = (o["u1"] - o["u0"]) * 0.5
                zsp = o["z1"] - r
                if za >= zsp - 1e-9:
                    t = za - zsp
                    hw = math.sqrt(max(0.0, r * r - t * t))
                    if hw <= 1e-4:
                        continue
                    ivs.append((o["u0"] + (r - hw), o["u1"] - (r - hw)))
                else:
                    ivs.append((o["u0"], o["u1"]))
            else:
                ivs.append((o["u0"], o["u1"]))
        ivs = [(max(a, u0), min(b, u1)) for (a, b) in ivs]
        ivs = [(a, b) for (a, b) in ivs if b > a + 1e-6]
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
    """Collect verts / faces / material indices for one mesh datablock."""

    def __init__(self, first=None):
        self.v, self.f, self.mi, self.mats = [], [], [], []
        if first is not None:
            self.mats.append(first)          # slot 0 -> per-parcel override

    def midx(self, name):
        m = self.mats
        if name in m:
            return m.index(name)
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

    def cyl(self, cx, cy, z0, z1, r, mat, seg=10, cap=True):
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
            self.f.append(tuple(n + k for k in reversed(range(seg))))
            self.mi.append(i)
            self.f.append(tuple(n + seg + k for k in range(seg)))
            self.mi.append(i)


def face_y(bd, y, x0, x1, z0, z1, out, mat):
    """Flat quad on a y = const plane, normal along +y (out>0) / -y."""
    if x1 < x0:
        x0, x1 = x1, x0
    if z1 < z0:
        z0, z1 = z1, z0
    if out >= 0:
        pts = [(x0, y, z0), (x0, y, z1), (x1, y, z1), (x1, y, z0)]
    else:
        pts = [(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)]
    bd.poly(pts, mat)


def face_x(bd, x, y0, y1, z0, z1, out, mat):
    if y1 < y0:
        y0, y1 = y1, y0
    if z1 < z0:
        z0, z1 = z1, z0
    if out >= 0:
        pts = [(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)]
    else:
        pts = [(x, y0, z0), (x, y0, z1), (x, y1, z1), (x, y1, z0)]
    bd.poly(pts, mat)


def face_z(bd, z, x0, x1, y0, y1, up, mat):
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    if up:
        pts = [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)]
    else:
        pts = [(x0, y0, z), (x0, y1, z), (x1, y1, z), (x1, y0, z)]
    bd.poly(pts, mat)


def wall(bd, axis, plane, u0, u1, z0, z1, ops, out, mat, reveal=WALL_T):
    """One facade: flat outer face with holes + reveal jambs around each opening.

    axis 'y': wall spans u=x at y=plane ; axis 'x': wall spans u=y at x=plane.
    `out` = +1/-1 outward normal direction along that axis.
    """
    for (ua, za, ub, zb) in wall_rects(u0, u1, z0, z1, ops):
        if axis == "y":
            face_y(bd, plane, ua, ub, za, zb, out, mat)
        else:
            face_x(bd, plane, ua, ub, za, zb, out, mat)
    for o in ops:
        a, b = max(o["u0"], u0), min(o["u1"], u1)
        c, d = max(o["z0"], z0), min(o["z1"], z1)
        if b - a < 1e-4 or d - c < 1e-4:
            continue
        far = plane - out * reveal
        lo, hi = (plane, far) if plane < far else (far, plane)
        if axis == "y":
            face_z(bd, d, a, b, lo, hi, up=False, mat=mat)      # head reveal
            face_z(bd, c, a, b, lo, hi, up=True, mat=mat)       # cill reveal
            face_x(bd, a, lo, hi, c, d, out=+1, mat=mat)        # jamb L
            face_x(bd, b, lo, hi, c, d, out=-1, mat=mat)        # jamb R
        else:
            face_z(bd, d, lo, hi, a, b, up=False, mat=mat)
            face_z(bd, c, lo, hi, a, b, up=True, mat=mat)
            face_y(bd, a, lo, hi, c, d, out=+1, mat=mat)
            face_y(bd, b, lo, hi, c, d, out=-1, mat=mat)


# --------------------------------------------------------------- mesh plumbing
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


_BND = {}


def mesh_bounds(me):
    """Local AABB (x0,y0,z0,x1,y1,z1) of a mesh datablock, computed once."""
    k = me.as_pointer()
    b = _BND.get(k)
    if b is None:
        if len(me.vertices):
            xs = [v.co[0] for v in me.vertices]
            ys = [v.co[1] for v in me.vertices]
            zs = [v.co[2] for v in me.vertices]
            b = (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))
        else:
            b = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        _BND[k] = b
    return b


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
    """Caches archetype meshes and their baked Z-rotations.

    Rotation is baked into the mesh datablock, so every placed object carries a
    pure translation (origin bottom-centre, scale 1) while still sharing one
    mesh per (archetype, rotation) - i.e. still fully instanced.
    """

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
            if isinstance(b, Builder):           # raw builder -> mesh datablock
                b = make_mesh("%s_%s" % (self.tag, str(key).replace(" ", "")[:44]), b)
            self.base[key] = b
        if rot == 0:
            m = b
        else:
            m = b.copy()
            m.transform(_rotmat(rot))
            m.name = "%s_%s_r%d" % (self.tag, str(key).replace(" ", "")[:48], rot)
        m.use_fake_user = True
        self.cache[ck_] = m
        return m


def _rotmat(rot):
    from mathutils import Matrix
    return Matrix.Rotation(math.radians(rot), 4, "Z")


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
            print("  [residential] slot override failed for %s: %s" % (name, exc))
    return ob


def place(kit, key, fn, name, bx, by, rot, lx, ly, z, coll, slot=None, prot=0):
    """Instantiate a kit piece: local (lx,ly) in the building frame at (bx,by)."""
    mesh = kit.get(key, (int(rot) + int(prot)) % 360, fn)
    a = math.radians(rot)
    c, s = math.cos(a), math.sin(a)
    wx = bx + lx * c - ly * s
    wy = by + lx * s + ly * c
    return new_obj(name, mesh, (wx, wy, z), coll, slot)


def poly_o(bd, pts, mat, want):
    """Emit a polygon, flipping the winding so its normal points along `want`."""
    p0, p1, p2 = pts[0], pts[1], pts[2]
    ux, uy, uz = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
    vx, vy, vz = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    if nx * want[0] + ny * want[1] + nz * want[2] < 0:
        pts = list(reversed(pts))
    bd.poly(pts, mat)


# ------------------------------------------------------------------------ roofs
def roof_gable(bd, xh, yh, top, rise, along, wallmat, roofmat):
    X, Y = xh + EAVE, yh + EAVE
    if along == "x":                       # ridge along X, slopes face +/-Y
        A, B = (-X, -Y, top), (X, -Y, top)
        C, D = (X, Y, top), (-X, Y, top)
        R0, R1 = (-X, 0.0, top + rise), (X, 0.0, top + rise)
        poly_o(bd, [A, B, R1, R0], roofmat, (0.0, -1.0, 0.6))
        poly_o(bd, [C, D, R0, R1], roofmat, (0.0, 1.0, 0.6))
        poly_o(bd, [B, C, R1], wallmat, (1.0, 0.0, 0.0))
        poly_o(bd, [D, A, R0], wallmat, (-1.0, 0.0, 0.0))
        bd.box(-X, -0.11, top + rise - 0.07, X, 0.11, top + rise + 0.07, "metal_steel")
    else:                                  # ridge along Y, slopes face +/-X
        A, B = (-X, -Y, top), (X, -Y, top)
        C, D = (X, Y, top), (-X, Y, top)
        R0, R1 = (0.0, -Y, top + rise), (0.0, Y, top + rise)
        poly_o(bd, [A, R0, R1, D], roofmat, (-1.0, 0.0, 0.6))
        poly_o(bd, [B, C, R1, R0], roofmat, (1.0, 0.0, 0.6))
        poly_o(bd, [A, B, R0], wallmat, (0.0, -1.0, 0.0))
        poly_o(bd, [C, D, R1], wallmat, (0.0, 1.0, 0.0))
        bd.box(-0.11, -Y, top + rise - 0.07, 0.11, Y, top + rise + 0.07, "metal_steel")


def roof_hip(bd, xh, yh, top, rise, wallmat, roofmat):
    X, Y = xh + EAVE, yh + EAVE
    if X >= Y - 1e-6:
        rx = max(0.0, X - Y)
        poly_o(bd, [(-X, -Y, top), (X, -Y, top), (rx, 0.0, top + rise),
                    (-rx, 0.0, top + rise)], roofmat, (0.0, -1.0, 0.6))
        poly_o(bd, [(X, Y, top), (-X, Y, top), (-rx, 0.0, top + rise),
                    (rx, 0.0, top + rise)], roofmat, (0.0, 1.0, 0.6))
        poly_o(bd, [(-X, -Y, top), (-rx, 0.0, top + rise), (-X, Y, top)],
               roofmat, (-1.0, 0.0, 0.6))
        poly_o(bd, [(X, Y, top), (rx, 0.0, top + rise), (X, -Y, top)],
               roofmat, (1.0, 0.0, 0.6))
        if rx > 0.05:
            bd.box(-rx, -0.11, top + rise - 0.07, rx, 0.11, top + rise + 0.07,
                   "metal_steel")
    else:
        ry = Y - X
        poly_o(bd, [(-X, -Y, top), (-X, Y, top), (0.0, ry, top + rise),
                    (0.0, -ry, top + rise)], roofmat, (-1.0, 0.0, 0.6))
        poly_o(bd, [(X, Y, top), (X, -Y, top), (0.0, -ry, top + rise),
                    (0.0, ry, top + rise)], roofmat, (1.0, 0.0, 0.6))
        poly_o(bd, [(-X, -Y, top), (0.0, -ry, top + rise), (X, -Y, top)],
               roofmat, (0.0, -1.0, 0.6))
        poly_o(bd, [(X, Y, top), (0.0, ry, top + rise), (-X, Y, top)],
               roofmat, (0.0, 1.0, 0.6))
        if ry > 0.05:
            bd.box(-0.11, -ry, top + rise - 0.07, 0.11, ry, top + rise + 0.07,
                   "metal_steel")


def roof_flat(bd, xh, yh, top, wallmat, parapet=0.9):
    e = 0.10
    bd.box(-xh - e, -yh - e, top - 0.14, xh + e, yh + e, top + 0.04, "roof_bitumen")
    t = 0.22
    z0, z1 = top + 0.04, top + parapet
    bd.box(-xh - e, -yh - e, z0, xh + e, -yh - e + t, z1, wallmat)
    bd.box(-xh - e, yh + e - t, z0, xh + e, yh + e, z1, wallmat)
    bd.box(-xh - e, -yh - e, z0, -xh - e + t, yh + e, z1, wallmat)
    bd.box(xh + e - t, -yh - e, z0, xh + e, yh + e, z1, wallmat)
    c = 0.05
    bd.box(-xh - e - c, -yh - e - c, z1, xh + e + c, -yh - e + t + c, z1 + 0.10,
           "stone_grey")
    bd.box(-xh - e - c, yh + e - t - c, z1, xh + e + c, yh + e + c, z1 + 0.10,
           "stone_grey")
    bd.box(-xh - e - c, -yh - e + t + c, z1, -xh - e + t + c, yh + e - t - c,
           z1 + 0.10, "stone_grey")
    bd.box(xh + e - t - c, -yh - e + t + c, z1, xh + e + c, yh + e - t - c,
           z1 + 0.10, "stone_grey")


# ------------------------------------------------------------- window / openings
def bays(L, margin, spacing):
    usable = L - 2.0 * margin
    n = max(1, int(usable / spacing))
    step = usable / n
    return [margin + step * (i + 0.5) for i in range(n)], step


def std_windows(style, L, zf, fh, excludes=()):
    """Standard window row for one floor band, centred on the facade."""
    st = STYLE[style]
    cs, step = bays(L, 1.1, st["spacing"])
    h = min(st["h"], fh - st["sill"] - 0.30)
    h = max(0.7, h)
    if st["pair"] and step >= 2.9:
        centers = []
        for c in cs:
            centers += [c - 0.9, c + 0.9]
    else:
        centers = list(cs)
    w = st["w"] if st["pair"] else max(0.8, min(st["w"], step - 0.55))
    out = []
    for cu in centers:
        u0, u1 = cu - w * 0.5, cu + w * 0.5
        if u0 < -L * 0.5 + 0.45 or u1 > L * 0.5 - 0.45:
            continue
        if any(u1 > e0 - 0.35 and u0 < e1 + 0.35 for (e0, e1) in excludes):
            continue
        out.append(dict(u0=u0, u1=u1, z0=zf + st["sill"], z1=zf + st["sill"] + h,
                        kind="window", main=True))
    return out


def gen_ops(W, D, top, fh, floors, style, typ, door, balc_xs, sec_local):
    """Openings for all four facades (local frame, front = +Y)."""
    ops = {"F": [], "B": [], "L": [], "R": []}
    ex = [(door["u0"], door["u1"])] if door else []
    if door:
        ops["F"].append(door)
    # ---- front
    for f in range(0, floors):
        zf = f * fh
        if f == 0:
            ops["F"] += std_windows(style, W, zf, fh, excludes=ex)
        elif typ == "apartment_low":
            to, exb = [], []
            for bx in balc_xs:
                w = 1.6
                to.append(dict(u0=bx - w * 0.5, u1=bx + w * 0.5, z0=zf + 0.35,
                               z1=zf + 0.35 + min(2.15, fh - 0.6), kind="window",
                               main=True))
                exb.append((bx - w * 0.5, bx + w * 0.5))
            ops["F"] += to + std_windows(style, W, zf, fh, excludes=exb)
        else:
            ops["F"] += std_windows(style, W, zf, fh)
    # ---- back (houses get a service door)
    bex = []
    if typ in ("house", "house_large"):
        d = dict(u0=-W * 0.25 - 0.5, u1=-W * 0.25 + 0.5, z0=0.0, z1=DOOR_H,
                 kind="door")
        ops["B"].append(d)
        bex = [(d["u0"], d["u1"])]
    for f in range(0, floors):
        ops["B"] += std_windows(style, W, f * fh, fh, excludes=bex)
    # ---- sides
    for s in ("L", "R"):
        for f in range(0, floors):
            ops[s] += std_windows(style, D, f * fh, fh)
    if typ == "corner_shop" and sec_local:
        s = sec_local[0]
        half_shop = min(2.4, D * 0.30)
        ops[s].append(dict(u0=-half_shop, u1=half_shop, z0=0.30, z1=2.95,
                           kind="shop", main=True))
        # drop plain ground windows that clash with the shopfront
        ops[s] = [o for o in ops[s]
                  if not (o.get("kind") == "window" and o["z0"] < fh
                          and o["u1"] > -half_shop - 0.4
                          and o["u0"] < half_shop + 0.4)]
    return ops


def deco(bd, axis, plane, out, o, sp):
    """Glass, frames, sills, shutters, surrounds for one opening."""
    st = STYLE[sp["style"]]
    kind = o.get("kind", "window")
    a, b, c, d = o["u0"], o["u1"], o["z0"], o["z1"]
    L = o.get("L", 12.0)

    def fq(u0, u1, z0, z1, dist, mat, sign=None):
        s = out if sign is None else sign
        if axis == "y":
            face_y(bd, plane + out * dist, u0, u1, z0, z1, s, mat)
        else:
            face_x(bd, plane + out * dist, u0, u1, z0, z1, s, mat)

    if kind in ("window", "shop"):
        fq(a, b, c, d, -0.12, st["glass"])                     # glass pane
        fd, fw = 0.035, 0.08                                   # frame ring
        fq(a - fw, b + fw, c - fw, c, fd, st["frame"])
        fq(a - fw, b + fw, d, d + fw, fd, st["frame"])
        fq(a - fw, a, c, d, fd, st["frame"])
        fq(b, b + fw, c, d, fd, st["frame"])
        if axis == "y":                                        # cill
            bd.box(a - 0.10, plane + out * 0.06, c - 0.13, b + 0.10,
                   plane - out * 0.17, c, st["trim"])
        else:
            bd.box(plane + out * 0.06, a - 0.10, c - 0.13, plane - out * 0.17,
                   b + 0.10, c, st["trim"])
        if axis == "y":                                        # lintel band
            bd.box(a - 0.10, plane + out * 0.03, d, b + 0.10,
                   plane - out * 0.05, d + 0.10, st["trim"])
        else:
            bd.box(plane + out * 0.03, a - 0.10, d, plane - out * 0.05,
                   b + 0.10, d + 0.10, st["trim"])
        sh = st["shutter"]
        if sh and o.get("main"):
            sw = 0.42
            for (s0, s1) in ((a - 0.07 - sw, a - 0.07), (b + 0.07, b + 0.07 + sw)):
                if s0 < -L * 0.5 + 0.1 or s1 > L * 0.5 - 0.1:
                    continue
                fq(s0, s1, c, d, 0.05, sh)
        if kind == "shop":                                     # shopfront fascia
            zb = min(d + 0.10, sp["top"] - 0.20)
            zt = min(d + 0.65, sp["top"] - 0.06)
            if zt - zb >= 0.12:
                if axis == "y":
                    bd.box(a - 0.3, plane + out * 0.02, zb, b + 0.3,
                           plane + out * 0.28, zt, "sign_metal")
                else:
                    bd.box(plane + out * 0.02, a - 0.3, zb, plane + out * 0.28,
                           b + 0.3, zt, "sign_metal")
    elif kind in ("door", "arch", "open", "porch"):
        fw = 0.14                                              # surround band
        fq(a - fw, b + fw, d, d + fw, 0.04, st["trim"])
        fq(a - fw, a, c, d, 0.04, st["trim"])
        fq(b, b + fw, c, d, 0.04, st["trim"])
        if kind in ("door", "arch"):
            if axis == "y":                                    # threshold step
                bd.box(a - 0.05, plane + out * 0.30, 0.0, b + 0.05,
                       plane - out * 0.22, 0.05, st["trim"])
            else:
                bd.box(plane + out * 0.30, a - 0.05, 0.0, plane - out * 0.22,
                       b + 0.05, 0.05, st["trim"])
        if kind == "open":                                     # shop sign band
            zb = min(d + 0.15, sp["top"] - 0.24)
            zt = min(d + 0.75, sp["top"] - 0.06)
            if zt - zb >= 0.12:
                if axis == "y":
                    bd.box(a - 0.4, plane + out * 0.02, zb, b + 0.4,
                           plane + out * 0.30, zt, "sign_metal")
                else:
                    bd.box(plane + out * 0.02, a - 0.4, zb, plane + out * 0.30,
                           b + 0.4, zt, "sign_metal")


# ------------------------------------------------------------------ shell meshes
def build_shell(sp):
    st = STYLE[sp["style"]]
    W, D, top, fh = sp["W"], sp["D"], sp["top"], sp["fh"]
    xh, yh = W * 0.5, D * 0.5
    bd = Builder(st["wall"])
    ops = sp["ops"]
    tagged = [(s, o) for s in ("F", "B") for o in ops[s]]
    tagged += [(s, o) for s in ("L", "R") for o in ops[s]]
    for s, o in tagged:
        o["L"] = W if s in ("F", "B") else D
    wall(bd, "y", yh, -xh, xh, 0.0, top, ops["F"], +1, st["wall"])
    wall(bd, "y", -yh, -xh, xh, 0.0, top, ops["B"], -1, st["wall"])
    wall(bd, "x", xh, -yh, yh, 0.0, top, ops["R"], +1, st["wall"])
    wall(bd, "x", -xh, -yh, yh, 0.0, top, ops["L"], -1, st["wall"])
    for s, o in tagged:
        if s == "F":
            deco(bd, "y", yh, +1, o, sp)
        elif s == "B":
            deco(bd, "y", -yh, -1, o, sp)
        elif s == "R":
            deco(bd, "x", xh, +1, o, sp)
        else:
            deco(bd, "x", -xh, -1, o, sp)
    # plinth (0.15 m base course) + cornice band
    bd.box(-xh - 0.15, -yh - 0.15, 0.0, xh + 0.15, yh + 0.15, CURB, st["trim"])
    bd.box(-xh - 0.09, -yh - 0.09, top - 0.28, xh + 0.09, yh + 0.09, top,
           st["trim"])
    # roof
    kind = sp["roof"]
    if kind == "flat":
        roof_flat(bd, xh, yh, top, st["wall"], parapet=sp.get("parapet", 0.9))
    else:
        rise = sp["pitch"] * (D if sp["ridge"] == "x" else W) * 0.5
        if kind == "gable":
            roof_gable(bd, xh, yh, top, rise, sp["ridge"], st["wall"], st["roofmat"])
        else:
            roof_hip(bd, xh, yh, top, rise, st["wall"], st["roofmat"])
    return bd


# ---------------------------------------------------------------------- props
def p_lamp():
    bd = Builder("metal_painted_charcoal")
    bd.box(-0.05, 0.0, -0.03, 0.05, 0.34, 0.03, "metal_painted_charcoal")
    bd.box(-0.20, 0.20, -0.14, 0.20, 0.52, 0.16, "metal_painted_charcoal")
    face_z(bd, -0.14, -0.16, 0.16, 0.24, 0.48, up=False, mat="emissive_warm")
    return bd


def p_meter():
    bd = Builder("metal_steel")
    bd.box(-0.16, 0.0, 0.0, 0.16, 0.14, 0.34, "metal_steel")
    bd.box(-0.13, 0.14, 0.06, 0.13, 0.16, 0.28, "glass_dark")
    return bd


def p_mail():
    bd = Builder("wood_old")
    bd.box(-0.05, -0.05, 0.0, 0.05, 0.05, 0.95, "wood_old")
    bd.box(-0.19, -0.13, 0.95, 0.19, 0.13, 1.25, "metal_painted_dark")
    bd.box(-0.21, -0.15, 1.25, 0.21, 0.15, 1.30, "metal_painted_dark")
    return bd


def p_bin():
    bd = Builder("metal_painted_sage")
    bd.box(-0.30, -0.38, 0.10, 0.30, 0.38, 1.05, "metal_painted_sage")
    bd.box(-0.33, -0.41, 1.05, 0.33, 0.41, 1.14, "metal_painted_charcoal")
    bd.box(-0.30, 0.38, 0.14, 0.30, 0.46, 0.95, "metal_painted_charcoal")
    return bd


def p_ac():
    bd = Builder("metal_steel")
    bd.box(-0.43, 0.0, 0.0, 0.43, 0.36, 0.56, "metal_steel")
    bd.box(-0.46, 0.0, -0.06, -0.30, 0.10, 0.0, "metal_painted_charcoal")
    bd.box(0.30, 0.0, -0.06, 0.46, 0.10, 0.0, "metal_painted_charcoal")
    face_y(bd, 0.37, -0.34, 0.34, 0.08, 0.48, out=+1, mat="metal_painted_charcoal")
    return bd


def p_pipe(h):
    bd = Builder("metal_painted_charcoal")
    bd.cyl(0.0, 0.0, 0.0, h, 0.055, "metal_painted_charcoal", seg=6, cap=False)
    for z in (h * 0.25, h * 0.7):
        bd.box(-0.09, -0.09, z - 0.03, 0.09, 0.09, z + 0.03, "metal_painted_charcoal")
    return bd


def p_dish():
    bd = Builder("metal_steel")
    bd.cyl(0.0, 0.0, 0.0, 0.45, 0.04, "metal_steel", seg=6, cap=False)
    bd.box(-0.28, 0.0, 0.45, 0.28, 0.06, 0.51, "metal_steel")
    # dish: shallow cone facing +Y
    n, r = 10, 0.34
    pole = len(bd.v)
    bd.v.append((0.0, 0.16, 0.86))
    ring = len(bd.v)
    for k in range(n):
        a = 2.0 * math.pi * k / n
        bd.v.append((r * math.cos(a), 0.0, 0.86 + r * math.sin(a)))
    di = bd.midx("metal_steel")
    for k in range(n):
        k2 = (k + 1) % n
        bd.f.append((pole, ring + k, ring + k2))
        bd.mi.append(di)
        bd.f.append((pole, ring + k2, ring + k))
        bd.mi.append(di)
    bd.box(-0.06, 0.0, 0.45, 0.06, 0.2, 0.78, "metal_steel")
    return bd


def p_tank():
    bd = Builder("metal_steel")
    for x in (-0.4, 0.4):
        for y in (-0.4, 0.4):
            bd.box(x - 0.06, y - 0.06, 0.0, x + 0.06, y + 0.06, 0.42, "metal_steel")
    bd.cyl(0.0, 0.0, 0.42, 1.5, 0.62, "metal_steel", seg=12)
    bd.cyl(0.0, 0.0, 1.5, 1.62, 0.5, "metal_rusty", seg=12)
    return bd


def p_chimney():
    bd = Builder("brick_red")
    bd.box(-0.26, -0.26, 0.0, 0.26, 0.26, 1.3, "brick_red")
    bd.box(-0.36, -0.36, 1.3, 0.36, 0.36, 1.44, "stone_grey")
    return bd


def p_antenna():
    bd = Builder("metal_steel")
    bd.cyl(0.0, 0.0, 0.0, 2.0, 0.035, "metal_steel", seg=6, cap=False)
    for i, z in enumerate((1.3, 1.55, 1.8)):
        w = 0.55 - i * 0.12
        bd.box(-w, -0.02, z - 0.02, w, 0.02, z + 0.02, "metal_steel")
    return bd


def _disc_y(bd, cy, cz, r, thick, mat, seg=10):
    """Vertical wheel disc (axis along Y), resting on z=0 when cz == r."""
    i = bd.midx(mat)
    n = len(bd.v)
    for y in (cy - thick * 0.5, cy + thick * 0.5):
        for k in range(seg):
            a = 2.0 * math.pi * k / seg
            bd.v.append((r * math.cos(a), y, cz + r * math.sin(a)))
    for k in range(seg):
        k2 = (k + 1) % seg
        bd.f.append((n + k, n + k2, n + seg + k2, n + seg + k))
        bd.mi.append(i)
    bd.f.append(tuple(n + k for k in reversed(range(seg))))
    bd.mi.append(i)
    bd.f.append(tuple(n + seg + k for k in range(seg)))
    bd.mi.append(i)


def p_bike():
    bd = Builder("metal_painted_charcoal")
    for y in (-0.52, 0.52):
        _disc_y(bd, y, 0.34, 0.34, 0.06, "metal_painted_charcoal", seg=10)
    bd.box(-0.05, -0.45, 0.32, 0.05, 0.45, 0.42, "metal_painted_oxblood")
    bd.box(-0.04, -0.10, 0.42, 0.04, 0.35, 0.52, "metal_painted_oxblood")
    bd.box(-0.03, -0.55, 0.78, 0.03, -0.45, 0.86, "metal_painted_charcoal")
    bd.box(-0.22, 0.42, 0.80, 0.22, 0.46, 0.85, "metal_painted_charcoal")
    return bd


def p_canopy(w, h):
    """Entrance canopy: slab at height h + two slim posts (wall plane at y=0)."""
    bd = Builder("concrete")
    proj = 1.15
    bd.box(-w * 0.5, 0.0, h - 0.16, w * 0.5, proj, h, "concrete")
    bd.box(-w * 0.5, proj - 0.10, h, w * 0.5, proj + 0.04, h + 0.14, "stone_grey")
    for x in (-w * 0.5 + 0.16, w * 0.5 - 0.16):
        bd.box(x - 0.07, proj - 0.22, 0.0, x + 0.07, proj - 0.08, h - 0.16,
               "concrete")
    return bd


def p_gate(w, h):
    bd = Builder("metal_painted_charcoal")
    t = 0.06
    bd.box(-w * 0.5, -t, 0.0, w * 0.5, t, h, "metal_painted_charcoal")
    bd.box(-w * 0.5 + 0.06, -t * 0.6, 0.10, w * 0.5 - 0.06, t * 0.6, h - 0.10,
           "metal_painted_sage")
    n = max(3, int(w / 0.28))
    for i in range(n):
        x = -w * 0.5 + 0.12 + i * (w - 0.24) / max(1, n - 1)
        bd.box(x - 0.025, -0.03, 0.10, x + 0.025, 0.03, h - 0.10,
               "metal_painted_charcoal")
    bd.box(-w * 0.5, -0.05, h - 0.16, w * 0.5, 0.05, h - 0.06, "metal_painted_charcoal")
    return bd


def p_awning(w, proj, mat, z0=3.05):
    bd = Builder(mat)
    drop = 0.42
    bd.poly([(-w * 0.5, 0.0, z0), (w * 0.5, 0.0, z0), (w * 0.5, proj, z0 - drop),
             (-w * 0.5, proj, z0 - drop)], mat)
    bd.poly([(-w * 0.5, proj, z0 - drop), (w * 0.5, proj, z0 - drop),
             (w * 0.5, proj, z0 - drop - 0.26), (-w * 0.5, proj, z0 - drop - 0.26)],
            mat)
    bd.poly([(-w * 0.5, 0.0, z0), (-w * 0.5, proj, z0 - drop),
             (-w * 0.5, proj, z0 - drop - 0.26), (-w * 0.5, 0.0, z0 - 0.26)], mat)
    bd.poly([(w * 0.5, 0.0, z0), (w * 0.5, 0.0, z0 - 0.26),
             (w * 0.5, proj, z0 - drop - 0.26), (w * 0.5, proj, z0 - drop)], mat)
    for x in (-w * 0.5 + 0.1, w * 0.5 - 0.1):
        bd.box(x - 0.03, 0.0, z0 - 0.5, x + 0.03, proj * 0.9, z0 - 0.44,
               "metal_steel")
    return bd


# ------------------------------------------------------- lot: fence / ground
def segments(lo, hi, openings):
    """Solid spans of [lo,hi] after removing `opening` intervals."""
    cuts = sorted((max(lo, a), min(hi, b)) for (a, b) in openings)
    out, cur = [], lo
    for a, b in cuts:
        if b <= cur:
            continue
        if a > cur + 1e-6:
            out.append((cur, min(a, hi)))
        cur = max(cur, b)
    if cur < hi - 1e-6:
        out.append((cur, hi))
    return out


def build_fence(sp):
    """Front garden wall (1.1 m) + side/back walls (1.5 m) with gate openings."""
    e = sp["half"] - FIN
    t = 0.25
    hf, hs = sp.get("fh_front", 1.1), sp.get("fh_side", 1.5)
    bd = Builder(sp["wall"])
    opens = [(sp["gate_x"] - sp["gate_w"] * 0.5, sp["gate_x"] + sp["gate_w"] * 0.5)]
    if sp.get("drv_w"):
        opens.append((sp["drv_x"] - sp["drv_w"] * 0.5, sp["drv_x"] + sp["drv_w"] * 0.5))
    for (a, b) in segments(-e, e, opens):
        bd.box(a, e - t * 0.5, 0.0, b, e + t * 0.5, hf, sp["wall"])
        bd.box(a - 0.04, e - t * 0.5 - 0.04, hf, b + 0.04, e + t * 0.5 + 0.04,
               hf + 0.07, "stone_grey")
    for (a, b) in opens:                                    # gate piers
        for x in (a - 0.18, b + 0.18):
            bd.box(x - 0.18, e - 0.22, 0.0, x + 0.18, e + 0.22, hf + 0.28,
                   sp["wall"])
            bd.box(x - 0.23, e - 0.27, hf + 0.28, x + 0.23, e + 0.27, hf + 0.38,
                   "stone_grey")
    bd.box(-e - t * 0.5, -e, 0.0, -e + t * 0.5, e, hs, sp["wall"])     # sides
    bd.box(e - t * 0.5, -e, 0.0, e + t * 0.5, e, hs, sp["wall"])
    bd.box(-e - t * 0.5, -e - t * 0.5, 0.0, e + t * 0.5, -e + t * 0.5, hs,
           sp["wall"])                                                # back
    for s in (-1, 1):                                                # side caps
        bd.box(s * e - t * 0.5 - 0.04, -e - 0.04, hs, s * e + t * 0.5 + 0.04,
               e + 0.04, hs + 0.07, "stone_grey")
    bd.box(-e - t * 0.5 - 0.04, -e - t * 0.5 - 0.04, hs, e + t * 0.5 + 0.04,
           -e + t * 0.5 + 0.04, hs + 0.07, "stone_grey")
    return bd


def build_lot_ground(sp):
    """Lawn + front path + driveway + forecourt pad, all inside the lot rect."""
    half = sp["half"]
    i = GIN
    bd = Builder("grass")
    bd.box(-half + i, -half + i, 0.0, half - i, half - i, 0.02, "grass")
    for r in sp.get("pads", []):
        bd.box(r[0], r[1], 0.005, r[2], r[3], 0.04, "paving_slab")
    return bd


def build_garage(sp):
    W, D, H = sp["W"], sp["D"], sp["H"]
    xh, yh = W * 0.5, D * 0.5
    bd = Builder(sp["wall"])
    door = dict(u0=-1.3, u1=1.3, z0=0.0, z1=2.2, kind="door")
    wall(bd, "y", yh, -xh, xh, 0.0, H, [door], +1, sp["wall"])
    wall(bd, "y", -yh, -xh, xh, 0.0, H, [], -1, sp["wall"])
    wall(bd, "x", xh, -yh, yh, 0.0, H, [], +1, sp["wall"])
    wall(bd, "x", -xh, -yh, yh, 0.0, H, [], -1, sp["wall"])
    bd.box(-1.34, yh - 0.14, 0.0, 1.34, yh + 0.03, 2.24, "metal_painted_dark")
    for k in range(4):                                        # panel ribs
        z = 0.2 + k * 0.55
        bd.box(-1.3, yh + 0.03, z, 1.3, yh + 0.06, z + 0.06, "metal_steel")
    bd.box(-1.45, yh + 0.02, 2.24, 1.45, yh + 0.10, 2.40, "stone_grey")
    bd.box(-xh - 0.15, -yh - 0.15, 0.0, xh + 0.15, yh + 0.15, CURB, "stone_grey")
    roof_flat(bd, xh, yh, H, sp["wall"], parapet=0.45)
    return bd


# ------------------------------------------------------------------ interiors
def build_int_depth(sp):
    """tier 3: one dark recessed box behind every opening (facade-only interior)."""
    bd = Builder("int_carpet")
    xh = sp["W"] * 0.5 - 0.38
    yh = sp["D"] * 0.5 - 0.38
    bd.box(-xh, -yh, 0.14, xh, yh, sp["top"] - 0.30, "int_carpet")
    return bd


def build_int_room(sp):
    """tier 2: shell + one furnished room at the front, dark depth behind it."""
    bd = Builder("int_wall_paint_bone")
    W, D, fh = sp["W"], sp["D"], sp["fh"]
    xh, yh = W * 0.5 - 0.38, D * 0.5 - 0.38
    room_d = min(D * 0.5, 6.0)
    yb = yh - room_d
    z0 = 0.14
    bd.box(-xh, yb, z0, xh, yh, z0 + 0.04, "int_wood_floor")
    bd.box(-xh, yb, fh - 0.30, xh, yh, fh - 0.16, "ceiling_paint")
    bd.box(-xh - 0.16, yb, z0, -xh, yh, fh - 0.16, "int_wall_paint_bone")
    bd.box(xh, yb, z0, xh + 0.16, yh, fh - 0.16, "int_wall_paint_bone")
    dw = 0.6                                              # partition + doorway
    bd.box(-xh - 0.16, yb, z0, -dw, yb + 0.14, fh - 0.16, "int_wall_paint_sand")
    bd.box(dw, yb, z0, xh + 0.16, yb + 0.14, fh - 0.16, "int_wall_paint_sand")
    bd.box(-xh - 0.16, yb, z0 + 2.4, xh + 0.16, yb + 0.14, fh - 0.16,
           "int_wall_paint_sand")
    bd.box(-xh - 0.16, yb, z0, xh + 0.16, yb + 0.14, z0 + 0.04, "floor_tile")
    bd.box(-xh, -yh, z0, xh, yb, sp["top"] - 0.30, "int_carpet")   # dark depth
    # furniture: table + two chairs + floor lamp
    bd.box(-0.75, yb + 1.0, z0, 0.75, yb + 1.9, z0 + 0.74, "wood_planks")
    for x in (-1.25, 1.25):
        bd.box(x - 0.22, yb + 1.2, z0, x + 0.22, yb + 1.6, z0 + 0.45, "wood_old")
        bd.box(x - 0.22, yb + 1.6, z0, x + 0.22, yb + 1.68, z0 + 0.95, "wood_old")
    bd.cyl(-xh + 0.5, yh - 0.6, z0, z0 + 1.4, 0.05, "metal_steel", seg=6)
    bd.cyl(-xh + 0.5, yh - 0.6, z0 + 1.4, z0 + 1.7, 0.18, "emissive_warm", seg=8)
    return bd


def build_int_living(sp):
    """tier 1, room A: living room shell + sofa + coffee table."""
    bd = Builder("int_wall_paint_bone")
    W, D, fh = sp["W"], sp["D"], sp["fh"]
    xh, yh = W * 0.5 - 0.38, D * 0.5 - 0.38
    yb = max(-yh + 3.0, yh - min(D * 0.5, 5.4))
    z0 = 0.14
    bd.box(-xh, yb, z0, xh, yh, z0 + 0.04, "int_wood_floor")
    bd.box(-xh, yb, fh - 0.30, xh, yh, fh - 0.16, "ceiling_paint")
    bd.box(-xh - 0.16, yb, z0, -xh, yh, fh - 0.16, "int_wall_paint_bone")
    bd.box(xh, yb, z0, xh + 0.16, yh, fh - 0.16, "int_wall_paint_bone")
    dw = 0.6
    bd.box(-xh - 0.16, yb, z0, -dw, yb + 0.14, fh - 0.16, "int_wall_paint_sand")
    bd.box(dw, yb, z0, xh + 0.16, yb + 0.14, fh - 0.16, "int_wall_paint_sand")
    bd.box(-xh - 0.16, yb, z0 + 2.4, xh + 0.16, yb + 0.14, fh - 0.16,
           "int_wall_paint_sand")
    # sofa
    bd.box(-xh + 0.3, yb + 0.5, z0, -xh + 0.3 + 2.1, yb + 1.35, z0 + 0.42,
           "int_upholstery")
    bd.box(-xh + 0.3, yb + 1.2, z0 + 0.42, -xh + 2.4, yb + 1.35, z0 + 0.85,
           "int_upholstery")
    bd.box(-xh + 0.3, yb + 0.5, z0 + 0.42, -xh + 0.45, yb + 1.35, z0 + 0.62,
           "int_upholstery")
    # coffee table + rug
    bd.box(-xh + 0.9, yb + 2.0, z0, -xh + 2.4, yb + 3.0, z0 + 0.42, "wood_planks")
    bd.box(-xh + 0.2, yb + 1.6, z0 + 0.04, -xh + 3.1, yb + 3.5, z0 + 0.06,
           "floor_carpet")
    # floor lamp
    bd.cyl(xh - 0.6, yb + 0.7, z0, z0 + 1.5, 0.05, "metal_steel", seg=6)
    bd.cyl(xh - 0.6, yb + 0.7, z0 + 1.5, z0 + 1.8, 0.19, "emissive_warm", seg=8)
    return bd


def build_int_bedroom(sp):
    """tier 1, room B: bedroom shell + bed + wardrobe."""
    bd = Builder("int_wall_paint_sand")
    W, D, fh = sp["W"], sp["D"], sp["fh"]
    xh, yh = W * 0.5 - 0.38, D * 0.5 - 0.38
    yb = max(-yh + 3.0, yh - min(D * 0.5, 5.4))
    z0 = 0.14
    bd.box(-xh - 0.16, -yh, z0, -0.07, yb, z0 + 0.04, "floor_wood")
    bd.box(-xh - 0.16, -yh, fh - 0.30, -0.07, yb, fh - 0.16, "ceiling_paint")
    bd.box(-xh - 0.16, -yh, z0, xh + 0.16, -yh + 0.16, fh - 0.16,
           "int_wall_paint_bone")
    bd.box(-0.14, -yh, z0, 0.0, yb, fh - 0.16, "int_wall_paint_bone")   # party wall
    # bed
    bx = -xh + 0.4
    bd.box(bx, -yh + 0.5, z0, bx + 1.7, -yh + 2.7, z0 + 0.30, "wood_old")
    bd.box(bx + 0.06, -yh + 0.56, z0 + 0.30, bx + 1.64, -yh + 2.64, z0 + 0.55,
           "int_upholstery")
    bd.box(bx + 0.06, -yh + 0.56, z0 + 0.55, bx + 1.64, -yh + 1.1, z0 + 0.68,
           "canvas_tarp")
    bd.box(bx - 0.06, -yh + 0.4, z0, bx + 1.76, -yh + 0.5, z0 + 1.0, "wood_old")
    # wardrobe
    bd.box(-xh + 0.2, yb - 1.7, z0, -xh + 1.1, yb - 0.2, z0 + 2.1, "wood_old")
    return bd


def build_int_kitchen(sp):
    """tier 1, room C: kitchen shell + counter + table."""
    bd = Builder("int_wall_paint_bone")
    W, D, fh = sp["W"], sp["D"], sp["fh"]
    xh, yh = W * 0.5 - 0.38, D * 0.5 - 0.38
    yb = max(-yh + 3.0, yh - min(D * 0.5, 5.4))
    z0 = 0.14
    bd.box(0.0, -yh, z0, xh + 0.16, yb, z0 + 0.04, "int_tile_floor")
    bd.box(0.0, -yh, fh - 0.30, xh + 0.16, yb, fh - 0.16, "ceiling_paint")
    bd.box(xh, -yh, z0, xh + 0.16, yb, fh - 0.16, "int_wall_paint_bone")
    bd.box(0.0, -yh, z0, xh + 0.16, -yh + 0.16, fh - 0.16, "int_wall_paint_bone")
    bd.box(0.0, -yh + 0.16, z0, xh - 0.4, -yh + 0.75, z0 + 0.9,
           "int_laminate_counter")
    bd.box(0.0, -yh + 0.16, z0 + 0.9, xh - 0.4, -yh + 0.72, z0 + 0.96,
           "marble_white")
    bd.box(0.0, -yh, z0 + 1.4, xh - 0.4, -yh + 0.35, z0 + 2.0, "wood_painted")
    bd.box(0.9, yb - 2.4, z0, 2.4, yb - 1.2, z0 + 0.75, "wood_planks")
    for x in (0.5, 2.8):
        bd.box(x - 0.2, yb - 2.1, z0, x + 0.2, yb - 1.7, z0 + 0.45, "wood_old")
    return bd


# ------------------------------------------------- courtyard / pocket park
def build_court_wall(sp):
    """Walled courtyard perimeter (2.1 m) with a gate arch on the road side."""
    e = sp["half"] - FIN
    t = 0.32
    h = 2.1
    gw = sp.get("gate_w", 3.2)
    bd = Builder(sp["wall"])
    for (a, b) in segments(-e, e, [(-gw * 0.5, gw * 0.5)]):
        bd.box(a, e - t * 0.5, 0.0, b, e + t * 0.5, h, sp["wall"])
        bd.box(a - 0.05, e - t * 0.5 - 0.05, h, b + 0.05, e + t * 0.5 + 0.05,
               h + 0.09, "stone_grey")
    for x in (-gw * 0.5 - 0.3, gw * 0.5 + 0.3):                 # gate piers
        bd.box(x - 0.3, e - 0.35, 0.0, x + 0.3, e + 0.35, h + 0.9, sp["wall"])
        bd.box(x - 0.36, e - 0.41, h + 0.9, x + 0.36, e + 0.41, h + 1.05,
               "stone_grey")
    # arch head between the piers (open below 3.0 m)
    bd.box(-gw * 0.5 - 0.3, e - t * 0.5, 3.0, gw * 0.5 + 0.3, e + t * 0.5, 3.5,
           sp["wall"])
    bd.box(-gw * 0.5 - 0.36, e - t * 0.5 - 0.06, 3.5, gw * 0.5 + 0.36,
           e + t * 0.5 + 0.06, 3.62, "stone_grey")
    for xs in (-1, 1):                                           # sides + back
        bd.box(xs * e - t * 0.5, -e, 0.0, xs * e + t * 0.5, e, h, sp["wall"])
        bd.box(xs * e - t * 0.5 - 0.05, -e - 0.05, h, xs * e + t * 0.5 + 0.05,
               e + 0.05, h + 0.09, "stone_grey")
    bd.box(-e - t * 0.5, -e - t * 0.5, 0.0, e + t * 0.5, -e + t * 0.5, h,
           sp["wall"])
    bd.box(-e - t * 0.5 - 0.05, -e - t * 0.5 - 0.05, h, e + t * 0.5 + 0.05,
           -e + t * 0.5 + 0.05, h + 0.09, "stone_grey")
    return bd


def build_court_ground(sp):
    half = sp["half"]
    i = 1.0
    bd = Builder("grass")
    bd.box(-half + i, -half + i, 0.0, half - i, half - i, 0.02, "grass")
    bd.box(-1.2, 12.0, 0.01, 1.2, half - i, 0.05, "paving_slab")     # gate path
    bd.box(-5.5, 9.4, 0.01, 5.5, 12.0, 0.05, "paving_slab")          # terrace
    for (x0, y0, x1, y1) in sp.get("beds", []):
        bd.box(x0, y0, 0.01, x1, y1, 0.35, "stone_grey")
        bd.box(x0 + 0.2, y0 + 0.2, 0.02, x1 - 0.2, y1 - 0.2, 0.33, "dirt")
    return bd


def build_park_ground(sp):
    half = sp["half"]
    i = 1.5
    bd = Builder("grass")
    bd.box(-half + i, -half + i, 0.0, half - i, half - i, 0.02, "grass")
    w = 2.2
    bd.box(-w, -half + i, 0.01, w, half - i, 0.05, "paving_slab")
    bd.box(-half + i, -w, 0.01, half - i, w, 0.05, "paving_slab")
    bd.box(-5.0, -5.0, 0.01, 5.0, 5.0, 0.06, "paving_slab")
    for (x0, y0, x1, y1) in sp.get("beds", []):
        bd.box(x0, y0, 0.01, x1, y1, 0.40, "stone_grey")
        bd.box(x0 + 0.25, y0 + 0.25, 0.02, x1 - 0.25, y1 - 0.25, 0.38, "dirt")
    return bd


def build_park_fence(sp):
    """Low park fence (1.0 m) with a 3 m opening on every road side."""
    e = sp["half"] - FIN
    t = 0.22
    h = 1.0
    gw = sp.get("gate_w", 3.0)
    bd = Builder("metal_painted_charcoal")
    op = (-gw * 0.5, gw * 0.5)
    for (a, b) in segments(-e, e, [op]):                          # front / back
        bd.box(a, e - t * 0.5, 0.0, b, e + t * 0.5, 0.12, "stone_grey")
        bd.box(a, e - t * 0.5, 0.12, b, e + t * 0.5, h - 0.1, "metal_painted_charcoal")
        bd.box(a - 0.02, e - t * 0.5 - 0.02, h - 0.1, b + 0.02, e + t * 0.5 + 0.02,
               h, "metal_painted_charcoal")
        bd.box(a, -e + t * 0.5, 0.0, b, -e - t * 0.5 + t, 0.12, "stone_grey")
        bd.box(a, -e - t * 0.5, 0.12, b, -e + t * 0.5, h - 0.1,
               "metal_painted_charcoal")
        bd.box(a - 0.02, -e - t * 0.5 - 0.02, h - 0.1, b + 0.02,
               -e + t * 0.5 + 0.02, h, "metal_painted_charcoal")
    for xs in (-1, 1):                                             # sides
        for (a, b) in segments(-e, e, [op]):
            x0 = xs * e - (t * 0.5 if xs > 0 else -t * 0.5)
            lo, hi = (xs * e - t * 0.5, xs * e + t * 0.5)
            bd.box(lo, a, 0.0, hi, b, 0.12, "stone_grey")
            bd.box(lo, a, 0.12, hi, b, h - 0.1, "metal_painted_charcoal")
            bd.box(lo - 0.02, a - 0.02, h - 0.1, hi + 0.02, b + 0.02, h,
                   "metal_painted_charcoal")
    for s in (-1, 1):                                              # posts at gates
        for c in (s * gw * 0.5 + s * 0.25, ):
            bd.box(c - 0.12, e - 0.12, 0.0, c + 0.12, e + 0.12, h + 0.25,
                   "stone_grey")
    return bd


def build_pavilion(sp):
    """Pocket-park pavilion: deck, four posts, beams, gabled tile roof."""
    bd = Builder("stone_grey")
    S = 3.25
    bd.box(-S - 0.4, -S - 0.4, 0.0, S + 0.4, S + 0.4, 0.18, "paving_slab")
    for x in (-S, S):
        for y in (-S, S):
            bd.box(x - 0.17, y - 0.17, 0.18, x + 0.17, y + 0.17, 3.0, "wood_old")
    for y in (-S, S):
        bd.box(-S - 0.2, y - 0.12, 3.0, S + 0.2, y + 0.12, 3.3, "wood_old")
    for x in (-S, S):
        bd.box(x - 0.12, -S - 0.2, 3.0, x + 0.12, S + 0.2, 3.24, "wood_old")
    roof_gable(bd, S + 0.3, S + 0.3, 3.3, 1.3, "y", "wood_old", "roof_clay_tile")
    return bd


# --------------------------------------------------------------- plumbing helpers
def build_road_grid(layout):
    nodes = {n["id"]: n["pos"] for n in layout["road_nodes"]}
    cell, grid, segs = 8.0, {}, []
    for e in layout["road_edges"]:
        a, b = nodes.get(e.get("a")), nodes.get(e.get("b"))
        if not a or not b:
            continue
        r = float(e.get("width", 6.0)) * 0.5
        segs.append((a[0], a[1], b[0], b[1], r, e.get("hierarchy", "street")))
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        steps = max(1, int(L / 2.0))
        for i in range(steps + 1):
            t = i / float(steps)
            x = a[0] + (b[0] - a[0]) * t
            y = a[1] + (b[1] - a[1]) * t
            grid.setdefault((int(math.floor(x / cell)), int(math.floor(y / cell))),
                            []).append((x, y, r))
    return grid, cell, segs


def road_hits(bbox, road, eps=0.02):
    grid, cell, _ = road
    x0, y0, x1, y1 = bbox
    hits = []
    for ix in range(int(math.floor(x0 / cell)), int(math.floor(x1 / cell)) + 1):
        for iy in range(int(math.floor(y0 / cell)), int(math.floor(y1 / cell)) + 1):
            for (px, py, r) in grid.get((ix, iy), ()):
                dx = max(x0 - px, 0.0, px - x1)
                dy = max(y0 - py, 0.0, py - y1)
                if math.hypot(dx, dy) < r - eps:
                    hits.append((round(px, 2), round(py, 2), round(r, 2)))
    return hits


def nearest_side(p, segs):
    x0, y0, x1, y1 = p["rect"]
    cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
    best, bside = 1e18, "S"
    for (ax, ay, bx, by, r, _h) in segs:
        vx, vy = bx - ax, by - ay
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((cx - ax) * vx + (cy - ay) * vy) / L2))
        dx, dy = ax + vx * t - cx, ay + vy * t - cy
        d = math.hypot(dx, dy) - r
        if d < best:
            best = d
            if abs(dx) > abs(dy):
                bside = "E" if dx > 0 else "W"
            else:
                bside = "N" if dy > 0 else "S"
    return bside


def overlap_check(bboxes):
    items = sorted(bboxes, key=lambda b: b[0][0])
    viol = []
    for i, (a, ida) in enumerate(items):
        for j in range(i + 1, len(items)):
            b, idb = items[j]
            if b[0] >= a[2] - 1e-6:
                break
            if b[1] < a[3] - 1e-6 and a[1] < b[3] - 1e-6:
                viol.append((ida, idb))
    return viol


def abbr(s):
    return "".join(w[0] for w in str(s).split("_"))[:6].upper()


def palette_for(style, p, front):
    """One palette colour per 66 m street run (style_bible 5R: no mixing)."""
    pal = PALETTE[style]
    if len(pal) == 1:
        return pal[0]
    c = p["center"]
    k = int(math.floor(c[1] / 66.0)) if front in ("N", "S") else int(math.floor(c[0] / 66.0))
    return pal[dhash("%s|%d" % (style, k)) % len(pal)]


class Ctx(object):
    def __init__(self, layout, parcels):
        self.layout = layout
        self.parcels = parcels
        self.root = ck.ensure_collection("Residential")
        self.meshes = ck.ensure_collection("Meshes", parent=self.root)
        self.colliders = ck.ensure_collection("Colliders", parent=self.root)
        self.lights = ck.ensure_collection("Lights", parent=self.root)
        self.shell = Kit("SM_Res")
        self.lot = Kit("SM_Lot")
        self.prop = Kit("SM_Prop")
        self.inter = Kit("INT")
        self.coll = Kit("COL")
        self.count = {}
        self.tier_tris = {0: 0, 1: 0, 2: 0, 3: 0}
        self.tier_count = {0: 0, 1: 0, 2: 0, 3: 0}
        self.type_count = {}
        self.style_count = {}
        self.placed = 0
        self.tris = 0
        self.props = 0
        self.buildings = 0
        self.colliders_n = 0
        self.collider_tris = 0
        self.parcel_ids = set()
        self.bboxes = []
        self.parcel_tris = []
        self.violations = []
        self.mat_used = set()
        self.road = build_road_grid(layout)

    def uniq(self, prefix, key):
        n = self.count.get(key, 0) + 1
        self.count[key] = n
        return "%s_%03d" % (prefix, n)

    def add(self, ob, tier, prop=False):
        self.placed += 1
        if prop:
            self.props += 1
        t = mesh_tris(ob.data)
        self.tris += t
        self.tier_tris[tier] = self.tier_tris.get(tier, 0) + t
        for m in ob.data.materials:
            if m is not None:
                self.mat_used.add(m.name)
        return ob


def check_rect(ctx, p, bb, name, rect=None, ground=False, track=True):
    """Assert `bb` stays inside the buildable rect (or the lot rect when
    `ground=True`, which also tests the road corridor). `track` adds the box
    to the cross-parcel overlap audit - only one box per parcel is tracked."""
    r = rect if rect is not None else (p.get("buildable_rect") or p["rect"])
    eps = 0.002
    if (bb[0] < r[0] - eps or bb[1] < r[1] - eps or bb[2] > r[2] + eps
            or bb[3] > r[3] + eps):
        ctx.violations.append(["buildable" if not ground else "lot", name, p["id"],
                               [round(v, 3) for v in bb], [round(v, 3) for v in r]])
    if ground:
        hits = road_hits(bb, ctx.road)
        if hits:
            ctx.violations.append(["road", name, p["id"], hits[:2]])
    if track:
        ctx.bboxes.append((bb, p["id"]))


def rot_point(cx, cy, rot, lx, ly):
    a = math.radians(rot)
    c, s = math.cos(a), math.sin(a)
    return cx + lx * c - ly * s, cy + lx * s + ly * c


def rect_from_local(cx, cy, rot, lx0, ly0, lx1, ly1):
    pts = [rot_point(cx, cy, rot, x, y) for (x, y) in
           ((lx0, ly0), (lx1, ly0), (lx1, ly1), (lx0, ly1))]
    xs = [q[0] for q in pts]
    ys = [q[1] for q in pts]
    return [min(xs), min(ys), max(xs), max(ys)]


def collider(ctx, p, cx, cy, rot, w, d, h, tag=""):
    key = ("col", round(w, 1), round(d, 1), round(h, 1))
    mesh = ctx.coll.get(key, rot, lambda: make_mesh(
        "COL_box", _col_builder(w, d, h)))
    ob = new_obj("COL_%s%s" % (p["id"], tag), mesh, (cx, cy, 0.0), ctx.colliders)
    ob.hide_render = True
    ctx.colliders_n += 1
    ctx.collider_tris += mesh_tris(mesh)
    return ob


def _col_builder(w, d, h):
    bd = Builder()
    bd.box(-w * 0.5, -d * 0.5, 0.0, w * 0.5, d * 0.5, h, "concrete")
    return bd


def make_shell_spec(p, typ, style, floors, top, fh, W, D, door, balc_xs,
                    sec_local, variant, roof, pitch, ridge, parapet):
    ops = gen_ops(W, D, top, fh, floors, style, typ, door, balc_xs, sec_local)
    key = (typ, style, floors, round(W, 2), round(D, 2), round(top, 2),
           round(fh, 3), variant, round(door["u1"] - door["u0"], 2),
           round(door["z1"], 2), door["kind"],
           tuple(round(v, 2) for v in balc_xs), tuple(sorted(sec_local)),
           roof, round(pitch, 2), ridge, round(parapet, 2))
    return dict(key=key, typ=typ, style=style, floors=floors, top=top, fh=fh,
                W=W, D=D, ops=ops, roof=roof, pitch=pitch, ridge=ridge,
                parapet=parapet, door=door, balc_xs=balc_xs, p=p)


def place_building(ctx, p, rng):
    t_start = ctx.tris
    pid = p["id"]
    typ = p["type"]
    style = p.get("facade_style")
    if style not in STYLE:
        style = STYLES[dhash(pid) % len(STYLES)]
    floors = max(1, int(p.get("floors") or 1))
    top = float(p.get("height_m") or floors * 3.2)
    fh = top / floors
    tier = int(p.get("interior_tier", 3))
    lot = p["rect"]
    half = (lot[2] - lot[0]) * 0.5
    lcx, lcy = (lot[0] + lot[2]) * 0.5, (lot[1] + lot[3]) * 0.5
    opening = p.get("opening")
    front = opening["side"] if opening else ((p.get("frontage") or ["N"])[0])
    rot = ROT[front]
    others = [s for s in (p.get("frontage") or []) if s != front]
    ls = sorted(set(local_side(s, rot) for s in others))
    tp = TPAR[typ]
    half_b = half - SETBACK_LOT
    TW, TD = SIZES[typ][dhash(pid + "sz") % len(SIZES[typ])]
    garage = bool(tp["garage"])
    drv_w, drv_x = (3.6, half_b - 1.8) if garage else (0.0, 0.0)
    cl, cr, cb = tp["ss"], tp["ss"], tp["sb"]
    if "L" in ls:
        cl = max(cl, tp["sec"])
    if "R" in ls:
        cr = max(cr, tp["sec"])
    if "B" in ls:
        cb = max(cb, tp["sec"])
    if garage:
        cr = max(cr, tp["ss"] + drv_w + 0.6)
    sf = clamp(0.55 * (2 * half_b - TD), tp["sf"][0], tp["sf"][1])
    x0, x1 = -half_b + cl, half_b - cr
    y1 = half_b - sf
    W = min(TW, x1 - x0)
    D = min(TD, y1 - (-half_b + cb))
    if "L" in ls:
        cx_l = x0 + W * 0.5
    elif "R" in ls:
        cx_l = x1 - W * 0.5
    else:
        cx_l = (x0 + x1) * 0.5
    cy_l = y1 - D * 0.5

    # ---- door / opening (open doorway, never a door mesh)
    if opening:
        dw = min(float(opening["width"]), W * 0.6)
        dh = max(DOOR_H, float(opening["height"]))
        ot = opening["type"]
        kind = "arch" if ot == "archway" else ("open" if ot == "open_frontage"
                                               else "door")
    else:
        dw = 1.6 if typ == "apartment_low" else 1.1
        dh, kind = DOOR_H, "door"
    door = dict(u0=-dw * 0.5, u1=dw * 0.5, z0=0.0, z1=dh, kind=kind, main=True)
    balc = []
    if typ == "apartment_low" and floors >= 2:
        balc = [-W * 0.25, W * 0.25] if W >= 18.0 else [0.0]

    # ---- roof
    variant = dhash(pid + "v") % 2
    st = STYLE[style]
    if typ == "apartment_low" or st["roof"] == "flat":
        roof, ridge, pitch, parapet = "flat", "x", 0.0, 0.9
    else:
        parapet = 0.0
        long_x = W >= D
        if style == "timber_cottage":
            roof, ridge = "gable", ("y" if variant else "x")
        elif variant:
            roof, ridge = "hip", ("x" if long_x else "y")
        else:
            roof, ridge = "gable", ("x" if long_x else "y")
        pitch = 0.36 if variant == 0 else 0.46
    if roof == "flat":
        rtop = top + parapet + 0.16
        rise = 0.0
    else:
        rise = pitch * (D if ridge == "x" else W) * 0.5
        rtop = top + rise + 0.08

    spec = make_shell_spec(p, typ, style, floors, top, fh, W, D, door, balc, ls,
                           variant, roof, pitch, ridge, parapet)
    pal = palette_for(style, p, front)
    bx, by = rot_point(lcx, lcy, rot, cx_l, cy_l)
    pref = "SM_Bldg_%s_%s" % (abbr(typ), abbr(style))
    mesh = ctx.shell.get(spec["key"], rot, lambda: make_mesh(
        "SM_Bldg_%s_%s" % (abbr(typ), abbr(style)), build_shell(spec)))
    ob = new_obj(ctx.uniq(pref, pref), mesh, (bx, by, 0.0), ctx.meshes, pal)
    ctx.add(ob, tier)

    proj = 0.0
    if balc:
        proj = BAL_P + 0.15
    if kind in ("open", "arch", "porch"):
        proj = max(proj, 1.25)
    bb = rect_from_local(bx, by, rot, -W * 0.5 - 0.15, -D * 0.5 - 0.15,
                         W * 0.5 + 0.15, D * 0.5 + 0.15 + proj)
    check_rect(ctx, p, bb, ob.name)

    # ---- interior by tier
    ib = (round(W, 1), round(D, 1), round(top, 1), round(fh, 2))
    if tier == 3:
        m = ctx.inter.get(("d",) + ib, rot, lambda: make_mesh("INT_Depth",
                                                               build_int_depth(spec)))
        ctx.add(new_obj("INT_%s_Depth" % pid, m, (bx, by, 0.0), ctx.meshes), tier)
    elif tier == 2:
        m = ctx.inter.get(("r",) + ib, rot, lambda: make_mesh("INT_Room",
                                                               build_int_room(spec)))
        ctx.add(new_obj("INT_%s_Room" % pid, m, (bx, by, 0.0), ctx.meshes), tier)
    else:
        for nm, fn in (("Living", build_int_living), ("Bedroom", build_int_bedroom),
                       ("Kitchen", build_int_kitchen)):
            m = ctx.inter.get((nm,) + ib, rot, lambda fn=fn: make_mesh("INT_" + nm,
                                                                       fn(spec)))
            ctx.add(new_obj("INT_%s_%s" % (pid, nm), m, (bx, by, 0.0), ctx.meshes),
                    tier)

    # ---- balconies (project 1.1 m, clearance under the slab 3.0 m)
    if balc:
        bmesh = ctx.prop.get(("balc", 4.0), rot, lambda: make_mesh("SM_Balcony_01",
                                                                   p_balcony(4.0)))
        for f in range(1, floors):
            for xx in balc:
                ctx.add(place(ctx.prop, ("balc", 4.0), lambda: None,
                              "SM_Balcony_%02d" % f, bx, by, rot, xx, D * 0.5,
                              f * fh, ctx.meshes, prot=0), tier)

    # ---- lot ground / fence / gate  (everything stays inside the lot rect)
    gy = half - FIN
    gate_w, gate_x = 1.6, cx_l
    pads = []
    front_y = cy_l + D * 0.5
    if typ == "apartment_low":
        pads.append((cx_l - 4.0, front_y, cx_l + 4.0, gy))
    elif typ != "corner_shop":
        pads.append((cx_l - 0.75, front_y, cx_l + 0.75, gy))
    pads.append((cx_l - 1.7, front_y, cx_l + 1.7, front_y + 1.9))
    if garage:
        pads.append((drv_x - drv_w * 0.5, front_y, drv_x + drv_w * 0.5, -5.4))
    pads = [tuple(round(v * 2.0) / 2.0 for v in r) for r in pads]
    gkey = ("ground", round(half, 1), tuple(pads))
    gmesh = ctx.lot.get(gkey, 0, lambda: make_mesh(
        "SM_Lot_Ground", build_lot_ground(dict(half=half, pads=pads))))
    P = ctx.prop
    brect = p.get("buildable_rect") or p["rect"]

    def put(key, fn, name, lx, ly, z, coll=None, prot=0, org=None):
        """Place a prop: (lx,ly) is building-local unless `org`=(ox,oy) is the
        frame origin (lot-level items use the lot centre). Every prop footprint
        is audited against the rect it belongs to."""
        ox, oy = org if org else (bx, by)
        ob = place(P, key, fn, name, ox, oy, rot, lx, ly, z,
                   ctx.meshes if coll is None else coll, prot=prot)
        ctx.add(ob, tier, prop=True)
        gx0, gy0, gx1, gy1 = mesh_bounds(ob.data)[:4]
        check_rect(ctx, p, [gx0 + ox, gy0 + oy, gx1 + ox, gy1 + oy], name,
                   rect=(p["rect"] if org else brect), ground=True, track=False)
        return ob

    ctx.add(new_obj(ctx.uniq("SM_Lot_Ground", gkey), gmesh, (lcx, lcy, 0.0),
                    ctx.meshes), tier)

    if typ != "corner_shop":
        fsp = dict(half=half, wall=pal, gate_w=gate_w,
                   gate_x=gate_x, drv_w=drv_w, drv_x=drv_x,
                   fh_front=1.0 if typ == "apartment_low" else 1.1,
                   fh_side=1.3 if typ == "apartment_low" else 1.5)
        fkey = ("fence", round(half, 1), gate_w, round(gate_x, 1), round(drv_w, 1),
                round(drv_x, 1), fsp["fh_front"], fsp["fh_side"], pal)
        fmesh = ctx.lot.get(fkey, rot, lambda: make_mesh("SM_Lot_Fence",
                                                         build_fence(fsp)))
        ctx.add(new_obj(ctx.uniq("SM_Lot_Fence", fkey), fmesh, (lcx, lcy, 0.0),
                        ctx.meshes), tier)
        put(("gate", round(gate_w, 1)),
            lambda: make_mesh("SM_Gate_01",
                              p_gate(gate_w - 0.1, fsp["fh_front"] - 0.05)),
            "SM_Gate_01", gate_x, gy, 0.0, org=(lcx, lcy))

    lot_bb = [lcx - half + GIN, lcy - half + GIN, lcx + half - GIN, lcy + half - GIN]
    check_rect(ctx, p, lot_bb, "%s_lot" % pid, rect=lot, ground=True, track=False)

    # ---- density detail (building-mounted + lot items)
    put(("lamp",), p_lamp, "SM_WallLamp_%s" % pid[-4:], dw * 0.5 + 0.5, D * 0.5,
        2.75, coll=ctx.lights)
    put(("meter",), p_meter, "SM_Meter_%s" % pid[-4:], -dw * 0.5 - 0.5, D * 0.5, 1.25)
    if typ != "corner_shop":
        put(("mail",), p_mail, "SM_Mailbox_%s" % pid[-4:], gate_x - 1.15, gy - 0.55,
            0.0, org=(lcx, lcy))
        put(("bin",), p_bin, "SM_Bin_%s" % pid[-4:], gate_x + 1.5, gy - 1.1, 0.0,
            org=(lcx, lcy))
    if p["enterable"] and kind in ("door", "arch", "porch"):
        put(("canopy", round(dw + 1.0, 1), round(dh, 1)),
            lambda: p_canopy(dw + 1.0, dh), "SM_Canopy_%s" % pid[-4:],
            0.0, D * 0.5, 0.0)
    # downpipes at the rear corners
    for sx in (-1, 1):
        put(("pipe", round(rtop, 1)), lambda: make_mesh("SM_Downpipe_01", p_pipe(rtop)),
            "SM_Downpipe_%s%d" % (pid[-3:], sx),
            sx * (W * 0.5 - 0.09), -D * 0.5 + 0.04, 0.0)
    # AC units on the rear facade (the unit faces +Y, so it is baked 180 deg)
    ac_p = 0.55 if typ == "apartment_low" else 0.28
    if rng.random() < ac_p:
        nac = 2 if (typ == "apartment_low" and floors >= 4) else 1
        for k in range(nac):
            put(("ac",), lambda: make_mesh("SM_AC_01", p_ac()), "SM_AC_%s%d" % (pid[-3:], k),
                rng.uniform(-W * 0.32, W * 0.32), -D * 0.5, fh * (k + 1) - 1.0,
                prot=180)
    # satellite dish on a side wall
    if rng.random() < 0.4:
        side = "R" if "R" in ls or "L" not in ls else "L"
        sx = 1 if side == "R" else -1
        put(("dish",), lambda: make_mesh("SM_Dish_01", p_dish()),
            "SM_Dish_%s" % pid[-4:], sx * W * 0.5, rng.uniform(-D * 0.3, D * 0.3),
            max(2.6, top - 2.2), prot=(270 if sx > 0 else 90))
    # roof plant
    if roof == "flat":
        for sx in (-1, 1):
            put(("tank",), lambda: make_mesh("SM_WaterTank_01", p_tank()),
                "SM_WaterTank_%s%d" % (pid[-3:], sx), sx * W * 0.26, -D * 0.18,
                top + 0.04)
        if rng.random() < 0.5:
            put(("antenna",), p_antenna, "SM_Antenna_%s" % pid[-4:],
                W * 0.3, D * 0.22, top + 0.04)
    else:
        put(("chimney",), p_chimney, "SM_Chimney_%s" % pid[-4:],
            (W * 0.2 if ridge == "x" else 0.0),
            (0.0 if ridge == "x" else D * 0.2), top + rise - 0.5)
        if rng.random() < 0.45:
            put(("antenna",), p_antenna, "SM_Antenna_%s" % pid[-4:],
                (-W * 0.3 if ridge == "x" else 0.0),
                (0.0 if ridge == "x" else -D * 0.3), top + rise - 0.3)
    # parked bikes in the forecourt
    if typ == "apartment_low" and rng.random() < 0.6:
        for k in range(2):
            put(("bike",), p_bike, "SM_Bike_%s%d" % (pid[-3:], k),
                4.6 + k * 1.1, D * 0.5 + 1.4 + k * 0.5, 0.04,
                prot=(0 if k % 2 == 0 else 180))
    # corner shop: awnings on both frontages (1.0 m projection keeps them
    # inside the buildable rect - the shop setback is only 1.2-1.8 m)
    if typ == "corner_shop":
        z0 = clamp(min(3.05, top - 0.35), 2.4, 3.05)
        mat = "fabric_awning_sage" if dhash(pid) % 2 else "fabric_awning_terracotta"
        aw = 6.0
        put(("awn", mat, round(z0, 1), aw), lambda: p_awning(aw, 1.0, mat, z0),
            "SM_Awning_%s" % pid[-4:], 0.0, D * 0.5, 0.0)
        if ls:
            s = 1 if ls[0] == "R" else -1
            put(("awn", mat, round(z0, 1), aw), lambda: p_awning(aw, 1.0, mat, z0),
                "SM_AwningS_%s" % pid[-4:], s * W * 0.5, 0.0, 0.0,
                prot=(270 if s > 0 else 90))

    # collider: centred on the shell INCLUDING the front projection
    ccx, ccy = rot_point(bx, by, rot, 0.0, proj * 0.5)
    collider(ctx, p, ccx, ccy, rot, W + 0.3, D + 0.3 + proj, rtop)
    ctx.parcel_ids.add(pid)
    ctx.buildings += 1
    ctx.tier_count[tier] += 1
    ctx.type_count[typ] = ctx.type_count.get(typ, 0) + 1
    ctx.style_count[style] = ctx.style_count.get(style, 0) + 1
    ctx.parcel_tris.append((tier, ctx.tris - t_start))


def p_balcony(w):
    """Slab 1.1 m deep + 1.05 m railing, attached to the facade plane at y=0."""
    bd = Builder("concrete")
    p = BAL_P
    bd.box(-w * 0.5, 0.0, -0.18, w * 0.5, p, 0.0, "concrete")
    bd.box(-w * 0.5 - 0.04, 0.0, -0.30, w * 0.5 + 0.04, p, -0.18, "stone_grey")
    h = 1.05
    bd.box(-w * 0.5, p - 0.07, 0.0, w * 0.5, p, h - 0.06, "metal_painted_charcoal")
    bd.box(-w * 0.5 - 0.06, 0.0, 0.0, -w * 0.5, p, h - 0.06, "metal_painted_charcoal")
    bd.box(w * 0.5, 0.0, 0.0, w * 0.5 + 0.06, p, h - 0.06, "metal_painted_charcoal")
    bd.box(-w * 0.5 - 0.06, p - 0.07, h - 0.06, w * 0.5 + 0.06, p, h,
           "metal_painted_charcoal")
    n = max(3, int(w / 0.34))
    for i in range(n):
        x = -w * 0.5 + 0.14 + i * (w - 0.28) / max(1, n - 1)
        bd.box(x - 0.02, p - 0.05, 0.0, x + 0.02, p - 0.01, h - 0.06,
               "metal_painted_charcoal")
    return bd


def put_prop(ctx, p, tier, key, fn, name, ox, oy, rot, lx, ly, z, rect,
             coll=None, prot=0):
    """Place an instanced prop in the frame of (ox,oy) and audit its footprint.

    Rotation is baked into the shared mesh (`prot` = extra rotation inside the
    building frame), so the object itself only ever carries a translation.
    """
    ob = place(ctx.prop, key, fn, name, ox, oy, rot, lx, ly, z,
               ctx.meshes if coll is None else coll, prot=prot)
    ctx.add(ob, tier, prop=True)
    gx0, gy0, gx1, gy1 = mesh_bounds(ob.data)[:4]
    check_rect(ctx, p, [gx0 + ox, gy0 + oy, gx1 + ox, gy1 + oy], name,
               rect=rect, ground=True, track=False)
    return ob


def p_bench():
    """Park bench, origin bottom-centre, seat facing -Y (back at +Y)."""
    bd = Builder("wood_old")
    for i in range(3):
        y = -0.44 + i * 0.29
        bd.box(-0.9, y, 0.40, 0.9, y + 0.21, 0.48, "wood_old")
    for x in (-0.78, 0.78):
        bd.box(x - 0.05, -0.5, 0.0, x + 0.05, 0.44, 0.42, "metal_painted_charcoal")
        bd.box(x - 0.05, 0.32, 0.42, x + 0.05, 0.44, 1.02, "metal_painted_charcoal")
    for i in range(2):
        z = 0.62 + i * 0.24
        bd.box(-0.9, 0.33, z, 0.9, 0.44, z + 0.17, "wood_old")
    return bd


def p_post_lamp():
    """4.5 m park lamp post with a warm emissive head (origin at the ground)."""
    bd = Builder("metal_painted_charcoal")
    bd.cyl(0.0, 0.0, 0.0, 0.18, 0.22, "metal_painted_charcoal", seg=10)
    bd.cyl(0.0, 0.0, 0.18, 4.16, 0.075, "metal_painted_charcoal", seg=8, cap=False)
    bd.box(-0.30, -0.30, 4.16, 0.30, 0.30, 4.38, "metal_painted_charcoal")
    bd.box(-0.24, -0.24, 4.38, 0.24, 0.24, 4.52, "emissive_warm")
    bd.box(-0.34, -0.34, 4.52, 0.34, 0.34, 4.60, "metal_painted_charcoal")
    return bd


def world_front(p):
    """Compass side of the parcel's street frontage (door side first)."""
    op = p.get("opening")
    if isinstance(op, dict) and op.get("side") in ROT:
        return op["side"]
    for s in (p.get("frontage") or []):
        if s in ROT:
            return s
    return None


def place_courtyard(ctx, p, rng):
    """Walled back-yard courtyard: perimeter wall + gate arch + annex wing."""
    t_start = ctx.tris
    pid = p["id"]
    lot = p["rect"]
    half = (lot[2] - lot[0]) * 0.5
    lcx, lcy = (lot[0] + lot[2]) * 0.5, (lot[1] + lot[3]) * 0.5
    front = world_front(p) or nearest_side(p, ctx.road[2])
    rot = ROT[front]
    style = p.get("facade_style")
    if style not in STYLE:
        style = STYLES[dhash(pid) % len(STYLES)]
    pal = palette_for(style, p, front)
    st = STYLE[style]
    tier = int(p.get("interior_tier", 0))
    brect_r = p.get("buildable_rect") or lot

    # ---- perimeter wall (2.1 m) with a gate arch on the road side
    gw = 3.2
    e = half - FIN
    wkey = ("courtw", round(half, 1), gw, pal)
    wmesh = ctx.lot.get(wkey, rot, lambda: make_mesh(
        "SM_CourtWall", build_court_wall(dict(half=half, wall=pal, gate_w=gw))))
    ctx.add(new_obj(ctx.uniq("SM_CourtWall", wkey), wmesh, (lcx, lcy, 0.0),
                    ctx.meshes), tier)
    check_rect(ctx, p, [lcx - e - 0.3, lcy - e - 0.3, lcx + e + 0.3, lcy + e + 0.3],
               pid + "_wall", rect=lot, ground=True, track=False)
    # gate leaves
    gmesh = ctx.prop.get(("gate", round(gw, 1)), rot,
                         lambda: make_mesh("SM_Gate_02", p_gate(gw - 0.2, 2.0)))
    gx, gy = rot_point(lcx, lcy, rot, 0.0, e)
    ctx.add(new_obj("SM_Gate_%s" % pid[-4:], gmesh, (gx, gy, 0.0), ctx.meshes), tier,
            prop=True)

    # ---- garden ground: gate path, terrace, two planting beds
    beds = [(-20.0, -16.0, -8.0, 4.0), (8.0, -16.0, 20.0, 4.0)]
    gkey = ("courtg", round(half, 1), tuple(beds))
    gmesh = ctx.lot.get(gkey, rot, lambda: make_mesh(
        "SM_Court_Ground", build_court_ground(dict(half=half, beds=beds))))
    ctx.add(new_obj(ctx.uniq("SM_Court_Ground", gkey), gmesh, (lcx, lcy, 0.0),
                    ctx.meshes), tier)
    check_rect(ctx, p, [lcx - half + 1.0, lcy - half + 1.0,
                        lcx + half - 1.0, lcy + half - 1.0],
               pid + "_ground", rect=lot, ground=True, track=False)

    # ---- annex wing fronting the terrace (this parcel's "building")
    W, D = 17.0, 9.5
    if st["roof"] == "flat":
        top, roof, ridge, pitch, parapet = 4.1, "flat", "x", 0.0, 0.7
    else:
        top, roof, ridge, pitch, parapet = 3.9, "gable", "x", 0.38, 0.0
    floors, fh = 1, top
    door = dict(u0=-1.2, u1=1.2, z0=0.0, z1=DOOR_H, kind="door", main=True)
    spec = make_shell_spec(p, "courtyard", style, floors, top, fh, W, D, door,
                           [], [], 0, roof, pitch, ridge, parapet)
    bx, by = rot_point(lcx, lcy, rot, 0.0, 9.4 - D * 0.5)
    pref = "SM_Bldg_CY_%s" % abbr(style)
    mesh = ctx.shell.get(spec["key"], rot, lambda: make_mesh(pref, build_shell(spec)))
    ob = new_obj(ctx.uniq(pref, spec["key"]), mesh, (bx, by, 0.0), ctx.meshes, pal)
    ctx.add(ob, tier)
    check_rect(ctx, p, rect_from_local(bx, by, rot, -W * 0.5 - 0.15, -D * 0.5 - 0.15,
                                       W * 0.5 + 0.15, D * 0.5 + 0.15),
               ob.name)

    # ---- annex detail
    put_prop(ctx, p, tier, ("lamp",), p_lamp, "SM_WallLamp_%s" % pid[-4:],
             bx, by, rot, -W * 0.34, D * 0.5, 2.75, brect_r, coll=ctx.lights)
    put_prop(ctx, p, tier, ("lamp",), p_lamp, "SM_WallLamp_%s" % pid[-4:],
             bx, by, rot, W * 0.34, D * 0.5, 2.75, brect_r, coll=ctx.lights)
    put_prop(ctx, p, tier, ("meter",), p_meter, "SM_Meter_%s" % pid[-4:],
             bx, by, rot, -1.9, D * 0.5, 1.25, brect_r)
    put_prop(ctx, p, tier, ("canopy", 4.4, DOOR_H),
             lambda: p_canopy(4.4, DOOR_H), "SM_Canopy_%s" % pid[-4:],
             bx, by, rot, 0.0, D * 0.5, 0.0, brect_r)
    for sx in (-1, 1):
        put_prop(ctx, p, tier, ("pipe", round(top, 1)),
                 lambda: make_mesh("SM_Downpipe_01", p_pipe(top)),
                 "SM_Downpipe_%s%d" % (pid[-3:], sx),
                 bx, by, rot, sx * (W * 0.5 - 0.09), -D * 0.5 + 0.04, 0.0, brect_r)
    put_prop(ctx, p, tier, ("mail",), p_mail, "SM_Mailbox_%s" % pid[-4:],
             lcx, lcy, rot, -1.3, e - 1.1, 0.0, lot)
    put_prop(ctx, p, tier, ("bin",), p_bin, "SM_Bin_%s" % pid[-4:],
             lcx, lcy, rot, 1.6, e - 1.4, 0.0, lot)
    if roof == "flat":
        for sx in (-1, 1):
            put_prop(ctx, p, tier, ("tank",),
                     lambda: make_mesh("SM_WaterTank_01", p_tank()),
                     "SM_WaterTank_%s%d" % (pid[-3:], sx),
                     bx, by, rot, sx * W * 0.26, -D * 0.18, top + 0.04, brect_r)
    else:
        put_prop(ctx, p, tier, ("chimney",), p_chimney, "SM_Chimney_%s" % pid[-4:],
                 bx, by, rot, W * 0.22, 0.0, top + pitch * D * 0.5 - 0.5, brect_r)
        put_prop(ctx, p, tier, ("antenna",), p_antenna, "SM_Antenna_%s" % pid[-4:],
                 bx, by, rot, -W * 0.3, 0.0, top + pitch * D * 0.5 - 0.3, brect_r)

    collider(ctx, p, bx, by, rot, W + 0.3, D + 0.3, top + (0.8 if roof == "flat" else 1.4))
    ctx.parcel_ids.add(pid)
    ctx.buildings += 1
    ctx.tier_count[tier] += 1
    ctx.type_count["courtyard"] = ctx.type_count.get("courtyard", 0) + 1
    ctx.style_count[style] = ctx.style_count.get(style, 0) + 1
    ctx.parcel_tris.append((tier, ctx.tris - t_start))


def place_park(ctx, p, rng):
    """Pocket park: fenced green, cross paths, flower beds, pavilion + benches."""
    t_start = ctx.tris
    pid = p["id"]
    lot = p["rect"]
    half = (lot[2] - lot[0]) * 0.5
    lcx, lcy = (lot[0] + lot[2]) * 0.5, (lot[1] + lot[3]) * 0.5
    front = world_front(p) or nearest_side(p, ctx.road[2])
    rot = ROT[front]
    tier = 0
    e = half - FIN

    # ---- ground: lawn + cross paths + plaza + four flower beds
    beds = [(11.0, 11.0, 30.0, 30.0), (-30.0, 11.0, -11.0, 30.0),
            (-30.0, -30.0, -11.0, -11.0), (11.0, -30.0, 30.0, -11.0)]
    gkey = ("parkg", round(half, 1), tuple(beds))
    gmesh = ctx.lot.get(gkey, rot, lambda: make_mesh(
        "SM_Park_Ground", build_park_ground(dict(half=half, beds=beds))))
    ctx.add(new_obj(ctx.uniq("SM_Park_Ground", gkey), gmesh, (lcx, lcy, 0.0),
                    ctx.meshes), tier)
    check_rect(ctx, p, [lcx - half + 1.5, lcy - half + 1.5,
                        lcx + half - 1.5, lcy + half - 1.5],
               pid + "_ground", rect=lot, ground=True, track=False)

    # ---- fence (1.0 m) with a 3 m gate on every road side
    fkey = ("parkf", round(half, 1), 3.0)
    fmesh = ctx.lot.get(fkey, rot, lambda: make_mesh(
        "SM_Park_Fence", build_park_fence(dict(half=half, gate_w=3.0))))
    ctx.add(new_obj(ctx.uniq("SM_Park_Fence", fkey), fmesh, (lcx, lcy, 0.0),
                    ctx.meshes), tier)
    check_rect(ctx, p, [lcx - e - 0.2, lcy - e - 0.2, lcx + e + 0.2, lcy + e + 0.2],
               pid + "_fence", rect=lot, ground=True, track=False)

    # ---- pavilion (this parcel's "building")
    pmesh = ctx.lot.get(("pavilion",), rot, lambda: make_mesh("SM_Pavilion",
                                                              build_pavilion({})))
    pav = new_obj(ctx.uniq("SM_Pavilion", ("pavilion",)), pmesh, (lcx, lcy, 0.0),
                  ctx.meshes)
    ctx.add(pav, tier)
    check_rect(ctx, p, [lcx - 3.7, lcy - 3.7, lcx + 3.7, lcy + 3.7], pav.name)

    # ---- benches around the plaza + lamp posts along the paths
    for (lx, ly, prot) in ((0.0, 9.5, 0), (0.0, -9.5, 180), (9.5, 0.0, 270),
                           (-9.5, 0.0, 90), (14.0, 6.5, 270), (-14.0, -6.5, 90)):
        put_prop(ctx, p, tier, ("bench",), p_bench, "SM_Bench_%s" % pid[-3:],
                 lcx, lcy, rot, lx, ly, 0.05, lot, prot=prot)
    for (lx, ly) in ((4.6, 20.0), (-4.6, -20.0), (20.0, -4.6), (-20.0, 4.6)):
        put_prop(ctx, p, tier, ("plamp",), p_post_lamp, "SM_ParkLamp_%s" % pid[-3:],
                 lcx, lcy, rot, lx, ly, 0.0, lot)
    for (lx, ly, prot) in ((16.0, 16.0, 135), (-16.0, -16.0, -45),
                           (16.0, -16.0, -135), (-16.0, 16.0, 45)):
        put_prop(ctx, p, tier, ("bench",), p_bench, "SM_Bench_%s" % pid[-3:],
                 lcx, lcy, rot, lx, ly, 0.05, lot, prot=prot)

    collider(ctx, p, lcx, lcy, rot, 7.4, 7.4, 4.7)
    ctx.parcel_ids.add(pid)
    ctx.buildings += 1
    ctx.tier_count[tier] += 1
    ctx.type_count["pocket_park"] = ctx.type_count.get("pocket_park", 0) + 1
    ctx.style_count["pavilion"] = ctx.style_count.get("pavilion", 0) + 1
    ctx.parcel_tris.append((tier, ctx.tris - t_start))


# ------------------------------------------------------------ previews / teardown
def _corridor_r(centre, segs):
    """Half-width (m) of the road corridor whose edge passes through `centre`."""
    best, br = 1e18, 6.0
    for (ax, ay, bx, by, r, _h) in segs:
        vx, vy = bx - ax, by - ay
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 <= 0 else max(0.0, min(1.0,
                                             ((centre[0] - ax) * vx +
                                              (centre[1] - ay) * vy) / L2))
        d = math.hypot(ax + vx * t - centre[0], ay + vy * t - centre[1]) - r
        if d < best:
            best, br = d, r
    return br


def pick_spot(parcels, segs=()):
    """Find the street run with the richest mix of types / styles / tiers and
    return both camera setups (45 degree oblique + 1.7 m eye level)."""
    groups = {}
    for p in parcels:
        if p["type"] in ("courtyard", "pocket_park"):
            continue
        f = world_front(p)
        if f is None:
            continue
        x0, y0, x1, y1 = p["rect"]
        if f in ("N", "S"):
            key, pos = ("x", f, round(y1 if f == "N" else y0, 1)), (x0 + x1) * 0.5
        else:
            key, pos = ("y", f, round(x1 if f == "E" else x0, 1)), (y0 + y1) * 0.5
        groups.setdefault(key, []).append((pos, p))
    best, bs = None, -1.0
    for key, items in groups.items():
        if len(items) < 6:
            continue
        types = {q["type"] for (_x, q) in items}
        styles = {q.get("facade_style") for (_x, q) in items}
        tiers = {q.get("interior_tier") for (_x, q) in items}
        score = len(items) + 6.0 * len(types) + 3.0 * len(styles) + 2.0 * len(tiers)
        if score > bs:
            bs, best = score, (key, items)
    if best is None:
        return None
    (axis, front, edge), items = best
    pos = sorted(q for (q, _p) in items)
    mid = pos[len(pos) // 2]
    d = (-VEC[front][0], -VEC[front][1])   # street -> buildings (front points
    #                                      # from the parcel out to its street)
    a = (1.0, 0.0) if axis == "x" else (0.0, 1.0)   # along the street
    centre = (mid, edge) if axis == "x" else (edge, mid)
    rr = _corridor_r(centre, segs) if segs else 6.0
    kerb = min(1.2 * rr, 6.0)          # stand on the carriageway, never a lot

    def at(fa, fd, z):
        return (centre[0] + fa * a[0] + fd * d[0],
                centre[1] + fa * a[1] + fd * d[1], z)

    return dict(axis=axis, front=front, edge=edge, mid=mid, score=bs, corridor=rr,
                types=sorted({q["type"] for (_x, q) in items}),
                styles=sorted({str(q.get("facade_style")) for (_x, q) in items}),
                n=len(items),
                cam1=at(-75.0, -45.0, 85.0), tgt1=at(25.0, 10.0, 6.0),
                cam2=at(-30.0, -kerb, 1.7), tgt2=at(26.0, 6.0, -1.5))


_TMP = {"ground": None, "sky": None, "box": None}


def temp_ground(on):
    """Preview-only ground slab (roads belong to the Roads module). It lives in
    the scene collection, never in Residential, and is deleted right after the
    renders so the saved .blend keeps no road geometry."""
    if on:
        if bpy.data.objects.get("TMP_GROUND") is not None:
            return
        b = _TMP["box"] or (-1500.0, -1500.0, 1500.0, 1500.0)
        bd = Builder("asphalt")
        bd.box(b[0] - 60.0, b[1] - 60.0, -0.5, b[2] + 60.0, b[3] + 60.0, 0.0,
               "asphalt")
        me = make_mesh("TMP_GROUND", bd)
        ob = bpy.data.objects.new("TMP_GROUND", me)
        bpy.context.scene.collection.objects.link(ob)
        _TMP["ground"] = ob
    else:
        ob = bpy.data.objects.get("TMP_GROUND")
        if ob is not None:
            bpy.data.objects.remove(ob, do_unlink=True)
        me = bpy.data.meshes.get("TMP_GROUND")
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)


def sky(on):
    """Brighten the world for the previews, restoring the stock world after."""
    w = bpy.context.scene.world
    if w is None or not getattr(w, "use_nodes", False) or w.node_tree is None:
        return
    bg = next((n for n in w.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg is None:
        return
    if on:
        _TMP["sky"] = (tuple(bg.inputs[0].default_value),
                       float(bg.inputs[1].default_value))
        bg.inputs[0].default_value = (0.45, 0.55, 0.72, 1.0)
        bg.inputs[1].default_value = 0.75
    elif _TMP["sky"] is not None:
        bg.inputs[0].default_value = _TMP["sky"][0]
        bg.inputs[1].default_value = _TMP["sky"][1]


def pick_engine():
    """Blender renamed the EEVEE engine id across versions - ask, don't guess."""
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


def purge_residential():
    """Re-runnability: drop the previous Residential collection (and its data)."""
    coll = bpy.data.collections.get("Residential")
    if coll is None:
        return
    for ob in list(coll.all_objects):
        try:
            bpy.data.objects.remove(ob, do_unlink=True)
        except Exception as exc:
            print("  [residential] purge object failed:", exc)

    def rm(c):
        for ch in list(c.children):
            rm(ch)
        try:
            bpy.data.collections.remove(c)
        except Exception as exc:
            print("  [residential] purge collection failed:", exc)

    rm(coll)
    print("  [residential] removed previous 'Residential' collection")
    for ld in list(bpy.data.lights):
        if ld.name.startswith("LT_res_"):
            try:
                bpy.data.lights.remove(ld)
            except Exception as exc:
                print("  [residential] could not remove light data:", exc)


def module_bbox(bboxes):
    x0 = min(b[0][0] for b in bboxes)
    y0 = min(b[0][1] for b in bboxes)
    x1 = max(b[0][2] for b in bboxes)
    y1 = max(b[0][3] for b in bboxes)
    z1 = 0.0
    for o in bpy.data.objects:
        if o.type == "MESH" and not o.hide_render:
            z1 = max(z1, float(o.dimensions.z) + float(o.location.z))
    return [round(v, 2) for v in (x0, y0, 0.0, x1, y1, z1)]


def main():
    t0 = time.time()
    layout = ck.read_layout()
    parcels = ck.read_parcels("R")
    purge_residential()
    # the blend must only contain this module - drop the stock startup objects
    for nm in ("Cube", "Camera", "Light"):
        ob = bpy.data.objects.get(nm)
        if ob is not None:
            bpy.data.objects.remove(ob, do_unlink=True)
    for c in list(bpy.data.collections):
        if c.name == "Residential" or len(c.objects) or len(c.children):
            continue
        try:
            bpy.data.collections.remove(c)
            print("  [residential] removed empty startup collection")
        except Exception as exc:
            print("  [residential] could not remove collection:", exc)

    ctx = Ctx(layout, parcels)
    print("[residential] %d parcels, %d road corridor samples"
          % (len(parcels), sum(len(v) for v in ctx.road[0].values())))

    by_cell = {}
    for p in parcels:
        by_cell.setdefault(tuple(p["cell"]), []).append(p)
    cells = sorted(by_cell)
    print("[residential] cells (%d): %s" % (len(cells), cells))

    for cell in cells:
        sub = sorted(by_cell[cell],
                     key=lambda q: 0 if q["type"] in ("pocket_park", "courtyard") else 1)
        for p in sub:
            rng = random.Random(dhash(p["id"]))
            typ = p["type"]
            if typ == "courtyard":
                place_courtyard(ctx, p, rng)
            elif typ == "pocket_park":
                place_park(ctx, p, rng)
            else:
                place_building(ctx, p, rng)
        ck.save_blend(OUT_BLEND)
        print("[residential] cell %s: %d/%d parcels | %d objects | %d tris | %.0fs"
              % (cell, ctx.buildings, len(parcels), ctx.placed, ctx.tris,
                 time.time() - t0))

    # ------------------------------------------------------------- verify
    missing = [p["id"] for p in parcels if p["id"] not in ctx.parcel_ids]
    overlaps = overlap_check(ctx.bboxes)
    n_obj = len(bpy.data.objects)
    uniq_tris = ck.scene_tri_count()
    used = set()
    for ob in bpy.data.objects:
        if ob.type == "MESH" and ob.data is not None:
            used.add(ob.data.as_pointer())
    n_meshes = len(used)
    n_build_viol = len([v for v in ctx.violations if v[0] == "buildable"])
    n_lot_viol = len([v for v in ctx.violations if v[0] == "lot"])
    n_road_viol = len([v for v in ctx.violations if v[0] == "road"])
    t1 = [t for (tier, t) in ctx.parcel_tris if tier == 1]
    t2 = [t for (tier, t) in ctx.parcel_tris if tier == 2]
    t3 = [t for (tier, t) in ctx.parcel_tris if tier == 3]
    max_t1, max_t2, max_t3 = (max(t1) if t1 else 0, max(t2) if t2 else 0,
                               max(t3) if t3 else 0)

    print("[residential] VERIFY objects=%d meshes=%d instanced_tris=%d "
          "unique_tris=%d buildable_viol=%d lot_viol=%d road_viol=%d overlaps=%d "
          "missing=%d (%d/%d parcels)"
          % (n_obj, n_meshes, ctx.tris, uniq_tris, n_build_viol, n_lot_viol,
             n_road_viol, len(overlaps), len(missing), len(parcels) - len(missing),
             len(parcels)))
    print("[residential] TYPES %s" % dict(sorted(ctx.type_count.items())))
    print("[residential] STYLES %s" % dict(sorted(ctx.style_count.items())))
    print("[residential] BUDGET meshes=%d max_t3=%d (<=8000) max_t2=%d (<=40000) "
          "max_t1=%d (<=150000) module=%d (<=15000000)"
          % (n_meshes, max_t3, max_t2, max_t1, uniq_tris))
    for v in ctx.violations[:12]:
        print("   VIOLATION", v)
    for o in overlaps[:12]:
        print("   OVERLAP", o)

    # ----------------------------------------------------------- previews
    box = (min(p["rect"][0] for p in parcels), min(p["rect"][1] for p in parcels),
           max(p["rect"][2] for p in parcels), max(p["rect"][3] for p in parcels))
    _TMP["box"] = box
    spot = pick_spot(parcels, ctx.road[2])
    if spot is None:
        spot = dict(cam1=(box[0] + 200.0, box[1] - 120.0, 42.0),
                    tgt1=(box[0] + 260.0, box[1] + 40.0, 6.0),
                    cam2=(box[0] + 220.0, box[1] - 3.5, 1.7),
                    tgt2=(box[0] + 260.0, box[1] + 8.0, 4.5),
                    axis="x", front="N", edge=box[1], mid=box[0] + 240.0, n=0,
                    types=[], styles=[], score=0.0)
    print("[residential] camera spot: axis=%s front=%s edge=%.1f along=%.1f "
          "score=%.0f n=%d types=%s styles=%s"
          % (spot["axis"], spot["front"], spot["edge"], spot["mid"], spot["score"],
             spot["n"], spot["types"], spot["styles"]))
    eng = pick_engine()
    print("[residential] preview engine:", eng)
    prev1, prev2 = PREV1, PREV2
    sky(True)
    temp_ground(True)
    try:
        try:
            ck.make_preview(prev1, spot["cam1"], spot["tgt1"], engine=eng,
                            res=(1920, 1080), sun_elev=42.0, sun_azim=-60.0,
                            sun_energy=4.0, samples=32)
        except Exception as exc:
            print("[residential] preview 1 failed:", exc)
            prev1 = None
        try:
            ck.make_preview(prev2, spot["cam2"], spot["tgt2"], engine=eng,
                            res=(1920, 1080), sun_elev=36.0, sun_azim=-50.0,
                            sun_energy=4.0, samples=32)
        except Exception as exc:
            print("[residential] preview 2 failed:", exc)
            prev2 = None
    finally:
        sky(False)
        temp_ground(False)
    left = [o.name for o in bpy.data.objects if o.name.startswith("TMP_")]
    if left:
        print("[residential] WARNING temp preview objects still in scene:", left)

    ck.save_blend(OUT_BLEND)

    # ------------------------------------------------------------- report
    bbox = module_bbox(ctx.bboxes)
    # Blender's Collection has no .parent: derive the tree from children links
    allc = list(bpy.data.collections)
    child_names = set()
    for c in allc:
        for ch in c.children:
            child_names.add(ch.name)
    tops = sorted(c.name for c in allc if c.name not in child_names)
    subs = sorted(c.name for c in allc if c.name in child_names)
    stock = sorted(o.name for o in bpy.data.objects
                   if o.name in ("Cube", "Camera", "Light"))
    print("[residential] COLLECTIONS top=%s sub=%s | stock objects: %s"
          % (tops, subs, stock or "none"))
    n_mesh_obj = len([o for o in bpy.data.objects if o.type == "MESH"])

    issues = []
    if tops != ["Residential"] or subs != ["Colliders", "Lights", "Meshes"]:
        issues.append("unexpected collection tree: top=%s sub=%s (want Residential/"
                      "Meshes+Colliders+Lights)" % (tops, subs))
    if stock:
        issues.append("stock startup objects left in the blend: %s" % ", ".join(stock))
    if ctx.violations:
        issues.append("%d geometry violations (%d buildable / %d lot / %d road "
                      "corridor)" % (len(ctx.violations), n_build_viol, n_lot_viol,
                                     n_road_viol))
    if overlaps:
        issues.append("%d parcel bbox overlaps" % len(overlaps))
    if missing:
        issues.append("%d parcels without a building" % len(missing))
    if max_t3 > 8000:
        issues.append("tier3 tri budget exceeded (%d > 8000)" % max_t3)
    if max_t2 > 40000:
        issues.append("tier2 tri budget exceeded (%d > 40000)" % max_t2)
    if max_t1 > 150000:
        issues.append("tier1 tri budget exceeded (%d > 150000)" % max_t1)
    if uniq_tris > 15000000:
        issues.append("module tri budget exceeded (%d > 15000000)" % uniq_tris)
    if prev1 is None or prev2 is None:
        issues.append("one or both previews failed to render")
    issues.append(
        "data-driven cells: parcels_R.json ships %d cells %s - every one of them "
        "is built (the brief listed 16 cells, the data has %d)"
        % (len(cells), [list(c) for c in cells], len(cells)))
    issues.append(
        "massing truth = height_m from the parcel data: houses ship %.1f m per "
        "floor rather than the 3.2 m scale rule (floor-to-floor for shops and "
        "apartments is 3.2 m); door/opening heads stay at %.1f m"
        % (3.0, DOOR_H))
    issues.append(
        "courtyard (64) and pocket_park (12) parcels carry no buildable_rect, so "
        "their geometry is audited against the parcel rect; the pavilion is the "
        "pocket park's 'building'")
    issues.append(
        "corner-shop awnings project 1.0 m (shop setback 1.2-1.8 m) so no "
        "geometry leaves buildable_rect; balconies project %.1f m, entrance "
        "canopies 1.15 m" % BAL_P)
    issues.append(
        "facade colour = one palette colour per 66 m street run (style_bible 5R), "
        "applied as an OBJECT-level slot-0 material override on the shell mesh")
    issues.append(
        "previews rendered with a temporary ground slab (deleted before saving) - "
        "roads/ground belong to the Roads module")
    issues.append(
        "Lights holds the emissive fixtures (wall lamps, park lamps); no point "
        "lights are created - the Lighting module owns those")
    issues.append(
        "no planting: trees / hedges belong to the Nature module, so the pocket "
        "park ships lawn, flower beds, benches, lamps and the pavilion only")
    issues.append(
        "object transforms = translation only (rotation baked into the shared "
        "mesh variant, scale 1) - required for linked instancing")

    payload = {
        "parcels": len(parcels),
        "buildings": ctx.buildings,
        "objects": n_obj,
        "objects_geometry": n_mesh_obj,
        "prop_objects": ctx.props,
        "collider_objects": ctx.colliders_n,
        "unique_meshes": n_meshes,
        "mesh_datablocks": len(bpy.data.meshes),
        "tris_instanced": ctx.tris,
        "tris_unique_meshes": uniq_tris,
        "collider_tris": ctx.collider_tris,
        "type_counts": dict(sorted(ctx.type_count.items())),
        "style_counts": dict(sorted(ctx.style_count.items())),
        "tier_counts": {str(k): v for k, v in sorted(ctx.tier_count.items())},
        "tier_tris": {str(k): v for k, v in sorted(ctx.tier_tris.items())},
        "budget_max_tris": {"t1": max_t1, "t2": max_t2, "t3": max_t3},
        "cells": [list(c) for c in cells],
        "engine": eng,
        "materials": sorted(ctx.mat_used),
        "violations": ctx.violations[:40],
        "overlaps": overlaps[:40],
        "missing_parcels": missing,
        "bbox": bbox,
        "collections": ["Residential", "Residential/Meshes",
                        "Residential/Colliders", "Residential/Lights"],
        "previews": [p for p in (prev1, prev2) if p],
        "camera_spot": {k: spot[k] for k in
                        ("axis", "front", "edge", "mid", "n", "types", "styles")},
        "assembler_contract": [
            "units = metres, Z-up, transforms applied (scale 1, rotation baked "
            "into the shared mesh variant, origin bottom-centre)",
            "single top-level collection 'Residential' with 'Meshes', 'Colliders' "
            "and 'Lights'",
            "materials only via citykit.append_material (%d used), no material is "
            "created here" % len(ctx.mat_used),
            "naming SM_/COL_/INT_ , instancing only - %d mesh datablocks serve %d "
            "objects" % (n_meshes, n_mesh_obj),
            "door_mesh = false: doorways and archways are open voids with a "
            "reveal + surround, never a door leaf",
            "scale rules: opening 2.4 m, floor %.2f m, curb %.2f m, sidewalk 2.5 m, "
            "lane 3.5 m" % (3.2, CURB),
            "every footprint inside buildable_rect (parcel rect for the two "
            "open-space types) and clear of every road corridor",
        ],
        "issues": issues,
        "build_seconds": round(time.time() - t0, 1),
    }
    ck.write_report("residential", payload)
    write_md(payload)

    print("[residential] DONE in %.0fs buildings=%d objects=%d meshes=%d "
          "tris(instanced)=%d unique=%d"
          % (time.time() - t0, ctx.buildings, n_obj, n_meshes, ctx.tris, uniq_tris))
    print("[residential] bbox", bbox)


def write_md(d):
    lines = []
    lines.append("# Residential module report (Phase C)\n")
    lines.append("Generated by `modules/residential.py` (headless, EEVEE "
                 "previews).\n")
    lines.append("## Counts\n")
    lines.append("| item | value |")
    lines.append("|---|---|")
    for k in ("parcels", "buildings", "objects", "objects_geometry", "prop_objects",
              "collider_objects", "unique_meshes", "mesh_datablocks",
              "tris_instanced", "tris_unique_meshes", "collider_tris",
              "build_seconds"):
        lines.append("| %s | %s |" % (k, d.get(k)))
    lines.append("| cells | %d |" % len(d.get("cells", [])))
    lines.append("\n### Per parcel type\n")
    lines.append("| type | parcels |")
    lines.append("|---|---|")
    for k, v in d["type_counts"].items():
        lines.append("| %s | %s |" % (k, v))
    lines.append("\n### Per facade style\n")
    lines.append("| style | shells |")
    lines.append("|---|---|")
    for k, v in d["style_counts"].items():
        lines.append("| %s | %s |" % (k, v))
    lines.append("\n## Per interior tier\n")
    lines.append("| tier | parcels | tris (building + lot + interior) |")
    lines.append("|---|---|---|")
    for t in ("0", "1", "2", "3"):
        lines.append("| t%s | %s | %s |" % (t, d["tier_counts"].get(t),
                                            d["tier_tris"].get(t)))
    b = d.get("budget_max_tris", {})
    lines.append("\n## Budgets\n")
    lines.append("| item | tris | limit |")
    lines.append("|---|---|---|")
    lines.append("| heaviest tier3 parcel | %s | 8000 |" % b.get("t3"))
    lines.append("| heaviest tier2 parcel | %s | 40000 |" % b.get("t2"))
    lines.append("| heaviest tier1 parcel | %s | 150000 |" % b.get("t1"))
    lines.append("| whole module (unique meshes) | %s | 15000000 |"
                 % d.get("tris_unique_meshes"))
    lines.append("| render engine | %s | EEVEE |" % d.get("engine"))
    lines.append("\n## Materials used (%d)\n" % len(d["materials"]))
    lines.append(", ".join("`%s`" % m for m in d["materials"]))
    lines.append("\n## Collections / bounding box\n")
    lines.append("- collections: %s" % ", ".join(d["collections"]))
    lines.append("- module bbox (x0,y0,z0,x1,y1,z1): %s" % d["bbox"])
    lines.append("- previews: %s" % ", ".join(d["previews"]))
    cs = d.get("camera_spot", {})
    lines.append("- camera spot: street axis %s, frontage %s at %.1f, run centred "
                 "on %.1f, %d parcels, types %s, styles %s"
                 % (cs.get("axis"), cs.get("front"), cs.get("edge") or 0,
                    cs.get("mid") or 0, cs.get("n") or 0, cs.get("types"),
                    cs.get("styles")))
    lines.append("\n## Verification\n")
    lines.append("- buildable_rect violations: %d"
                 % len([v for v in d["violations"] if v[0] == "buildable"]))
    lines.append("- lot violations: %d"
                 % len([v for v in d["violations"] if v[0] == "lot"]))
    lines.append("- road corridor violations: %d"
                 % len([v for v in d["violations"] if v[0] == "road"]))
    lines.append("- parcel bbox overlaps: %d" % len(d["overlaps"]))
    lines.append("- parcels without a building: %d (of %d)"
                 % (len(d["missing_parcels"]), d["parcels"]))
    lines.append("- cells built: %s" % ", ".join(str(c) for c in d["cells"]))
    lines.append("\n## Assembler contract\n")
    for a in d.get("assembler_contract", []):
        lines.append("- %s" % a)
    lines.append("\n## Known issues / notes\n")
    for i in d["issues"]:
        lines.append("- %s" % i)
    path = os.path.join(ck.REPORTS_DIR, "residential_report.md")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("  [residential] markdown report -> %s" % path)


if __name__ == "__main__":
    main()
