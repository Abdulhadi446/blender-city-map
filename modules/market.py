#!/usr/bin/env python3
"""market.py — Market district (M) building kit for the 3x3 km AAA city.

Headless run:
    cd /home/abdulhadi/Work/city && blender -b -P modules/market.py

Builds 1236 market parcels (6 cells) as linked-duplicate archetype meshes plus
shared street props, the tier0 courtyards and the LM_BAZAAR hero landmark.
Re-runnable: deletes the "Market" collection first, saves after every cell.
"""
from __future__ import annotations

import json
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
CELLS = [[5, 6], [6, 6], [7, 6], [5, 7], [6, 7], [7, 7]]

F = 15.31                 # regular buildable footprint
HALF = F / 2.0            # 7.655  plinth edge == buildable edge
SET = 0.45                # plinth depth == max ground prop projection
WH = HALF - SET           # 7.205  wall outer face
WALL_T = 0.25
TRIM = 4.0                # rear depth trim -> rear yard for the external stair
                          # (free depth behind the ground facade = 4.0 m >= 1.6 m)
BAL = 1.2                 # balcony projection (railing 1.06 m above its floor)
STAIR_W = 1.4             # shared external stair width
REAR = WH - TRIM          # 3.205  rear wall outer face on trimmed buildings
REAR_EDGE = HALF - TRIM   # 3.655  rear plinth edge == back of the rear yard
INT_Y1_TRIM = REAR - WALL_T - 0.07   # interior back plane on trimmed buildings

# ---- overhang / clearance contract (verified by verify_clearance()) --------
CLEAR = 2.4               # nothing may hang below this outside buildable_rect
AWN_PROJ = 1.4            # awning projection 1.2-1.5 m
AWN_Z = 3.20              # awning attachment height -> soffit 2.70, low edge 2.60
BLADE_PROJ = 1.0          # blade sign projection 0.8-1.2 m (style_bible: 1.0)
BLADE_Z = 2.80            # blade sign bottom edge (style_bible: 2.8 m)
MIN_REAR_FREE = 1.6       # rear-yard depth needed before an external stair fits
LIGHT_CAP = 250           # hard cap on provisional LT_market_* lights

FL = 3.2                  # floor height
REC = 1.5                 # storefront recess depth
REC_Y = -(WH - REC)       # recess back plane  (-5.705)
CORE = 6.6                # upper-floor solid core half size
OPEN_W = 10.0             # default frontage opening
OPEN_W_WS = 7.0           # workshop frontage opening
ARC_W = 6.0               # pair-side opening
EAVE = 0.40               # pitched-roof eave overhang (<= SET)
CURB = 0.15               # plinth height

ROT = {"S": 0, "E": 90, "N": 180, "W": 270}
# frontage set -> (pattern, rotation)
PAIR_MAP = {
    frozenset(("S", "W")): ("pairL", 0),
    frozenset(("E", "S")): ("pairL", 90),
    frozenset(("N", "W")): ("pairR", 180),
    frozenset(("E", "N")): ("pairR", 90),
}

BASE_WALL = {
    "old_bazaar_brick": "brick_red",
    "painted_plaster": "facade_plaster_terracotta",
    "timber_balcony": "facade_plaster_weathered",
}
PALETTE = {
    "old_bazaar_brick": ["brick_red", "brick_brown", "brick_whitewash",
                         "facade_plaster_terracotta"],
    "painted_plaster": ["facade_plaster_terracotta", "facade_plaster_sand",
                        "facade_plaster_oxblood", "facade_plaster_mustard",
                        "facade_plaster_teal", "facade_plaster_bone"],
    "timber_balcony": ["facade_plaster_weathered", "facade_plaster_sand",
                       "facade_plaster_bone", "facade_plaster_terracotta"],
}
# window rhythm per facade_style (style_bible B.4 / M section)
STYLE = {
    "old_bazaar_brick": dict(spacing=2.4, w=2.0, sill=1.0, h=1.9, arch=True,
                             nfront=5, nside=4, shutter=None),
    "painted_plaster": dict(spacing=2.0, w=1.1, sill=0.9, h=1.6, arch=False,
                            nfront=6, nside=5, shutter="wood_painted"),
    "timber_balcony": dict(spacing=2.4, w=1.6, sill=0.6, h=2.2, arch=False,
                           nfront=5, nside=4, shutter="wood_old"),
}
ROOF_OF = {
    "shop": "flat", "restaurant": "flat", "workshop": "monitor",
    "house_above_shop": "flat", "teahouse": "pitched",
}


def dhash(s):
    h = 2166136261
    for ch in str(s):
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


def wall_rects(u0, u1, z0, z1, ops):
    """Decompose a wall rectangle into solid rects around `ops` openings.

    op = dict(u0,u1,z0,z1[,arch])  -- arch means the top of the void is a
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
            self.f.append(tuple(n + k for k in range(seg)))
            self.mi.append(i)
            self.f.append(tuple(n + seg + k for k in reversed(range(seg))))
            self.mi.append(i)

    def dome(self, cx, cy, z0, r, mat, seg=16, rings=6):
        i = self.midx(mat)
        n = len(self.v)
        for j in range(rings):
            phi = (math.pi * 0.5) * j / rings
            rr, zz = r * math.cos(phi), z0 + r * math.sin(phi)
            for k in range(seg):
                a = 2.0 * math.pi * k / seg
                self.v.append((cx + rr * math.cos(a), cy + rr * math.sin(a), zz))
        pole = len(self.v)
        self.v.append((cx, cy, z0 + r))
        for j in range(rings - 1):
            for k in range(seg):
                k2 = (k + 1) % seg
                self.f.append((n + j * seg + k, n + j * seg + k2,
                               n + (j + 1) * seg + k2, n + (j + 1) * seg + k))
                self.mi.append(i)
        base = n + (rings - 1) * seg
        for k in range(seg):
            k2 = (k + 1) % seg
            self.f.append((base + k, base + k2, pole))
            self.mi.append(i)


class Face(object):
    """One vertical wall plane of a building, in local (u, z) wall space."""

    def __init__(self, bd, axis, d0, d1, out, u0=None, u1=None):
        self.bd = bd
        self.axis = axis          # 'y' -> u is x ; 'x' -> u is y
        self.d0 = d0
        self.d1 = d1
        self.out = out            # +1 / -1 outward along the depth axis
        self.u0 = -WH if u0 is None else u0
        self.u1 = WH if u1 is None else u1

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

    def poly(self, pts, mat, t0, t1):
        lo, hi = self.seg(t0, t1)
        if self.axis == "y":
            self.bd.poly([(p[0], lo, p[1]) for p in pts], mat)
            self.bd.poly([(p[0], hi, p[1]) for p in pts], mat)
        else:
            self.bd.poly([(lo, p[0], p[1]) for p in pts], mat)
            self.bd.poly([(hi, p[0], p[1]) for p in pts], mat)

    def wall(self, z0, z1, ops, mat):
        for (a, c, b, d) in wall_rects(self.u0, self.u1, z0, z1, ops):
            self.rect(a, c, b, d, mat)

    # ------------------------------------------------------------- openings
    def window(self, cu, z0, z1, w, arch, main, style):
        u0, u1 = cu - w * 0.5, cu + w * 0.5
        r = w * 0.5
        if arch:
            pts = [(u0, z0), (u1, z0), (u1, z1 - r)]
            for k in range(1, 9):
                a = math.pi * k / 8.0
                pts.append((cu + r * math.cos(a), z1 - r + r * math.sin(a)))
            pts.append((u0, z1 - r))
            self.poly(pts, "glass_dark", 0.10, 0.13)
        else:
            self.rect(u0, z0, u1, z1, "glass_dark", 0.10, 0.13)
        # sill
        self.rect(u0 - 0.11, z0 - 0.13, u1 + 0.11, z0, "stone_grey", -0.07, 0.06)
        # frame
        fw = 0.09
        self.rect(u0 - fw, z0, u0, z1 - (r if arch else 0.0), "wood_painted", -0.03, 0.05)
        self.rect(u1, z0, u1 + fw, z1 - (r if arch else 0.0), "wood_painted", -0.03, 0.05)
        if arch:
            self.rect(cu - 0.13, z1 - 0.30, cu + 0.13, z1 + 0.06, "stone_grey", -0.06, 0.07)
        else:
            self.rect(u0 - fw, z1, u1 + fw, z1 + fw, "wood_painted", -0.03, 0.05)
        # shutters (front face only)
        sh = STYLE[style]["shutter"]
        if sh and main:
            sp = STYLE[style]["spacing"]
            sw = min(0.40, (sp - w) * 0.5 - 0.08)
            if sw > 0.16:
                self.rect(u0 - 0.07 - sw, z0, u0 - 0.07, z1, sh, -0.08, -0.02)
                self.rect(u1 + 0.07, z0, u1 + 0.07 + sw, z1, sh, -0.08, -0.02)


# ---------------------------------------------------------------- mesh plumbing
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
    """Caches archetype meshes and their baked Z-rotations.

    Rotation is baked into the mesh datablock so every placed object carries a
    pure translation (origin bottom-centre, scale 1) while still sharing one
    mesh per (archetype, rotation) — i.e. still fully instanced.
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
            self.base[key] = b
        if rot == 0:
            m = b
        else:
            m = b.copy()
            m.transform(Matrix.Rotation(math.radians(rot), 4, "Z"))
            m.name = "%s_%s_r%d" % (self.tag, str(key).replace(" ", ""), rot)
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
        except Exception as exc:      # pragma: no cover
            print("  [market] slot override failed for %s: %s" % (name, exc))
    return ob


# ------------------------------------------------------------------- roofs
def gable_roof(bd, top, rise=2.4, back=None):
    DO = WH + EAVE
    DB = (WH if back is None else back) + EAVE
    XO = WH + EAVE
    A = (-XO, -DO, top); B = (XO, -DO, top)
    C = (XO, DB, top); D = (-XO, DB, top)
    R0 = (-XO, 0.0, top + rise); R1 = (XO, 0.0, top + rise)
    bd.poly([A, B, R1, R0], "roof_tile_red")
    bd.poly([D, R0, R1, C], "roof_tile_red")
    bd.poly([A, D, C, B], "roof_tile_red")
    bd.poly([A, R0, D], "roof_tile_red")
    bd.poly([B, C, R1], "roof_tile_red")
    bd.box(-XO, DB - 0.12, top - 0.22, XO, DB, top + 0.05, "wood_old")
    bd.box(-XO, -DO, top - 0.22, XO, -DO + 0.12, top + 0.05, "wood_old")
    bd.box(-XO - 0.02, -0.12, top + rise - 0.08, XO + 0.02, 0.12,
           top + rise + 0.06, "metal_rusty")


def flat_roof(bd, top, wm, parapet=1.0, back=None, hatch=0.0):
    """hatch > 0 leaves a gap of `hatch` metres centred on x=0 in the REAR (+Y)
    parapet and its coping: the roof-access opening the external stair lands on
    for single-storey buildings (stair top landing z == roof level)."""
    BK = WH if back is None else back
    bd.box(-WH, -WH, top - 0.06, WH, BK, top + 0.03, "roof_bitumen")
    t = 0.25
    bd.box(-WH, -WH, top, WH, -WH + t, top + parapet, wm)
    if hatch > 0.0:                       # rear parapet, split around the hatch
        g = hatch * 0.5
        bd.box(-WH, BK - t, top, -g, BK, top + parapet, wm)
        bd.box(g, BK - t, top, WH, BK, top + parapet, wm)
    else:
        bd.box(-WH, BK - t, top, WH, BK, top + parapet, wm)
    bd.box(-WH, -WH + t, top, -WH + t, BK - t, top + parapet, wm)
    bd.box(WH - t, -WH + t, top, WH, BK - t, top + parapet, wm)
    c = 0.05
    if hatch > 0.0:                       # matching gap in the rear coping
        g = hatch * 0.5
        bd.box(-WH - c, BK - t - c, top + parapet, -g, BK + c, top + parapet + 0.12,
               "stone_grey")
        bd.box(g, BK - t - c, top + parapet, WH + c, BK + c, top + parapet + 0.12,
               "stone_grey")
    else:
        bd.box(-WH - c, BK - t - c, top + parapet, WH + c, BK + c, top + parapet + 0.12, "stone_grey")
    bd.box(-WH - c, -WH - c, top + parapet, WH + c, -WH + t + c, top + parapet + 0.12, "stone_grey")
    bd.box(-WH - c, -WH + t + c, top + parapet, -WH + t + c, BK - t - c, top + parapet + 0.12, "stone_grey")
    bd.box(WH - t - c, -WH + t + c, top + parapet, WH + c, BK - t - c, top + parapet + 0.12, "stone_grey")


def roof_monitor(bd, top):
    bd.box(-4.0, -1.3, top, 4.0, 1.3, top + 1.1, "metal_painted_dark")
    bd.box(-4.0, -1.36, top + 0.3, 4.0, -1.3, top + 1.0, "glass_dark")
    bd.box(-4.0, 1.3, top + 0.3, 4.0, 1.36, top + 1.0, "glass_dark")
    bd.box(-4.12, -1.42, top + 1.05, 4.12, 1.42, top + 1.22, "metal_rusty")


# ------------------------------------------------------------- archetype shell
def build_shell(btype, style, floors, pattern, yard=True):
    """yard=True trims the REAR (+Y) by TRIM so a rear yard + external stair fit
    inside buildable_rect. Front and side faces stay on the buildable edge.

    Single-storey shells get a roof-access gap in the rear parapet (the external
    stair lands on the roof); multi-storey shells get the 2.4 m rear door at
    first-floor level instead (see the fnum==1 branch below)."""
    bd = Builder()
    wm = BASE_WALL[style]
    st = STYLE[style]
    wb = (WH - TRIM) if yard else WH        # rear wall outer face
    op_w = OPEN_W_WS if btype == "workshop" else OPEN_W

    fS = Face(bd, "y", -WH, -WH + WALL_T, -1)
    fN = Face(bd, "y", wb - WALL_T, wb, +1)
    fW = Face(bd, "x", -WH, -WH + WALL_T, -1, -WH, wb)
    fE = Face(bd, "x", WH - WALL_T, WH, +1, -WH, wb)
    faces = {"S": fS, "N": fN, "E": fE, "W": fW}

    gops = {"S": [], "N": [], "E": [], "W": []}
    if btype == "teahouse":
        gops["S"] = [dict(u0=c - 1.5, u1=c + 1.5, z0=0.0, z1=FL, arch=True)
                     for c in (-4.0, 0.0, 4.0)]
        oh = 5.5
    else:
        gops["S"] = [dict(u0=-op_w * 0.5, u1=op_w * 0.5, z0=0.0, z1=FL)]
        oh = op_w * 0.5
    if pattern == "pairL":
        gops["W"] = [dict(u0=-ARC_W * 0.5, u1=ARC_W * 0.5, z0=0.0, z1=FL)]
    elif pattern == "pairR":
        gops["E"] = [dict(u0=-ARC_W * 0.5, u1=ARC_W * 0.5, z0=0.0, z1=FL)]
    if btype == "restaurant":
        gops["S"].append(dict(u0=5.35, u1=7.0, z0=1.15, z1=2.15))

    # ---- ground floor walls
    for k, f in faces.items():
        f.wall(0.0, FL, gops[k], wm)

    # ---- storefront recess (returns + soffit + shop floor)
    bd.box(-oh - 0.25, -WH, 0.0, -oh, REC_Y, FL, wm)
    bd.box(oh, -WH, 0.0, oh + 0.25, REC_Y, FL, wm)
    bd.box(-oh, -WH, FL - 0.15, oh, REC_Y + 0.01, FL, wm)
    bd.box(-oh, -WH, 0.0, oh, REC_Y, 0.04, "floor_tile")

    # ---- restaurant service-counter niche
    if btype == "restaurant":
        bd.box(5.35, -WH + 0.45, 1.15, 7.0, -WH + 0.5, 2.15, wm)
        bd.box(5.35, -WH, 1.0, 7.0, -WH + 0.45, 1.15, "stone_grey")
        bd.box(5.35, -WH, 0.0, 7.0, -WH + 0.45, 0.15, "stone_grey")

    # ---- upper floors
    for fnum in range(1, floors):
        z0 = fnum * FL
        z1 = z0 + FL
        for side, face in faces.items():
            n = st["nfront"] if side == "S" else st["nside"]
            sp, w = st["spacing"], st["w"]
            total = (n - 1) * sp
            mid = (face.u0 + face.u1) * 0.5      # centre the rhythm on THIS face
            ops = []
            for i in range(n):
                cu = mid - total * 0.5 + i * sp
                ops.append(dict(u0=cu - w * 0.5, u1=cu + w * 0.5,
                                z0=z0 + st["sill"], z1=z0 + st["sill"] + st["h"],
                                arch=st["arch"]))
            door = None
            if yard and side == "N" and fnum == 1:
                # external-stair door: 2.4 m opening height, over the stair top
                door = dict(u0=-STAIR_W * 0.5, u1=STAIR_W * 0.5, z0=FL, z1=FL + 2.4)
                ops.append(door)
            face.wall(z0, z1, ops, wm)
            for op in ops:
                if op is door:
                    face.rect(op["u0"], op["z0"], op["u1"], op["z1"], "wood_old", 0.06, 0.10)
                    face.rect(op["u0"] - 0.06, op["z0"], op["u1"] + 0.06, op["z1"] + 0.06,
                              "stone_grey", -0.04, 0.04)
                    continue
                face.window((op["u0"] + op["u1"]) * 0.5, op["z0"], op["z1"],
                            op["u1"] - op["u0"], st["arch"], side == "S", style)

    # ---- solid core so upper windows do not see straight through
    if floors > 1:
        bd.box(-CORE, -CORE, FL, CORE, min(CORE, wb - WALL_T), floors * FL - 0.15,
               "wall_paint")

    # ---- balcony (timber_balcony style or teahouse) - projects 1.2 m, railed 1.06 m
    #      half-width 5.0 keeps clear of the blade sign placed at |x| = 6.0
    if floors >= 2 and (style == "timber_balcony" or btype == "teahouse"):
        z0 = FL
        bw = 5.0
        fS.rect(-bw, z0 - 0.16, bw, z0, "wood_old", -BAL, 0.0)                 # slab
        fS.rect(-bw, z0 - 0.34, bw, z0 - 0.16, "wood_old", -BAL, -BAL + 0.14)  # fascia
        fS.rect(-bw, z0 - 0.05, bw, z0 + 0.06, "wood_painted", -BAL, 0.0)      # floor trim
        fS.rect(-bw, z0 + 0.06, bw, z0 + 0.95, "wood_old", -BAL + 0.01, -BAL + 0.08)
        fS.rect(-bw, z0 + 0.95, bw, z0 + 1.06, "wood_painted", -BAL, -BAL + 0.11)
        # corner cheeks closing the balcony box
        for cx0 in (-bw, bw - 0.12):
            fS.rect(cx0, z0 - 0.16, cx0 + 0.12, z0 + 1.06, "wood_old", -BAL, 0.0)

    # ---- plinth (0.15 m base course, flush with buildable edge)
    for k, f in faces.items():
        for (a, c, b, d) in wall_rects(f.u0, f.u1, 0.0, CURB, gops[k]):
            f.rect(a, c, b, d, "stone_grey", -SET, 0.0)

    # ---- cornice
    top = floors * FL
    for f in faces.values():
        f.rect(f.u0, top - 0.35, f.u1, top, "stone_grey", -0.09, 0.0)

    # ---- roof
    kind = ROOF_OF[btype]
    if kind == "pitched":
        gable_roof(bd, top, back=wb)
    else:
        # single-storey + external stair -> roof-access gap over the stair top
        hatch = (STAIR_W + 0.2) if (yard and floors == 1) else 0.0
        flat_roof(bd, top, wm, parapet=1.0 if btype != "workshop" else 0.7,
                  back=wb, hatch=hatch)
        if kind == "monitor":
            roof_monitor(bd, top)
    return bd


# ------------------------------------------------------------------ interiors
def build_interior(tier, yard=True):
    """tier 3 = fake-depth box, 2 = one furnished room, 1 = multi-room shell.

    yard=True shortens the shell to the trimmed rear wall (see build_shell)."""
    bd = Builder()
    x = 6.935
    y0 = REC_Y
    y1 = INT_Y1_TRIM if yard else 6.90
    bd.box(-x, y0, 0.0, x, y1, 0.03, "int_wood_floor")
    bd.box(-x, y0, FL - 0.13, x, y1, FL - 0.03, "ceiling_paint")
    bd.box(-x - 0.07, y0, 0.0, -x, y1, FL - 0.03, "int_wall_paint_bone")
    bd.box(x, y0, 0.0, x + 0.07, y1, FL - 0.03, "int_wall_paint_bone")
    bd.box(-x, y1, 0.0, x, y1 + 0.07, FL - 0.03, "int_wall_paint_sand")
    if tier >= 3:
        return bd
    # front room partition with a 1.1 m doorway
    yp = 1.4
    bd.box(-x, yp, 0.0, -0.55, yp + 0.12, 2.1, "int_wall_paint_bone")
    bd.box(0.55, yp, 0.0, x, yp + 0.12, 2.1, "int_wall_paint_bone")
    bd.box(-x, yp, 2.1, x, yp + 0.12, FL - 0.13, "int_wall_paint_bone")
    bd.box(-x, yp, 0.0, x, yp + 0.12, 0.03, "floor_tile")
    if tier == 1 and y1 > 5.0:
        yp2 = 4.2
        bd.box(-x, yp2, 0.0, 1.45, yp2 + 0.12, 2.1, "int_wall_paint_sand")
        bd.box(2.55, yp2, 0.0, x, yp2 + 0.12, 2.1, "int_wall_paint_sand")
        bd.box(-x, yp2, 2.1, x, yp2 + 0.12, FL - 0.13, "int_wall_paint_sand")
        bd.box(-x, yp2, 0.0, x, yp2 + 0.12, 0.03, "floor_tile")
    return bd


def build_furn(which, yard=True):
    bd = Builder()
    if which == "shop":
        bd.box(-3.0, -5.1, 0.0, -0.6, -4.4, 1.05, "int_laminate_counter")
        bd.box(-3.0, -5.1, 1.05, -0.6, -4.4, 1.12, "marble_white")
        bd.box(2.2, -4.6, 0.0, 4.6, -4.2, 2.3, "wood_old")
        bd.box(2.2, -4.6, 2.3, 4.6, -4.1, 2.42, "wood_old")
        bd.box(-1.4, -3.0, 0.0, 1.4, -1.6, 0.76, "wood_planks")
        bd.box(-1.3, -2.9, 0.76, 1.3, -1.7, 0.84, "wood_planks")
        bd.box(-3.4, -1.2, 0.0, -2.2, -0.1, 0.85, "wood_old")
    else:
        # back-room kit: compressed onto the yard-trimmed depth so nothing
        # pokes through the rear wall into the external stair yard
        k = (INT_Y1_TRIM if yard else 6.90) / 6.90
        bd.box(-4.6, 2.2 * k, 0.0, -3.0, 3.6 * k, 1.1, "wood_old")
        bd.box(-1.4, 2.4 * k, 0.0, 1.4, 4.0 * k, 0.76, "wood_planks")
        bd.box(2.6, 2.4 * k, 0.0, 4.4, 4.2 * k, 1.6, "wood_old")
        bd.box(4.8, 5.0 * k, 0.0, 6.0, 6.0 * k, 0.7, "canvas_tarp")
    return bd


# ------------------------------------------------------------------ courtyard
def build_courtyard():
    """Tier-0 parcel: perimeter ring + open hardscape courtyard + gate arch."""
    bd = Builder()
    H = 15.81                 # buildable half (31.62 footprint)
    w = H - SET               # 15.36 outer wall face
    t = 0.35
    ci = 10.2                 # courtyard half-size
    top = FL

    outs = [Face(bd, "y", -w, -w + t, -1, -w, w),
            Face(bd, "y", w - t, w, +1, -w, w),
            Face(bd, "x", -w, -w + t, -1, -w, w),
            Face(bd, "x", w - t, w, +1, -w, w)]
    # gate arch (built facing -Y, rotated per parcel)
    gate = dict(u0=-1.7, u1=1.7, z0=0.0, z1=3.1, arch=True)
    for idx, f in enumerate(outs):
        ops = [gate] if idx == 0 else []
        for cu in (-6.4, 6.4):
            ops.append(dict(u0=cu - 0.55, u1=cu + 0.55, z0=1.5, z1=2.7))
        f.wall(0.0, top, ops, "facade_plaster_sand")
        # gate surround bands
        if idx == 0:
            f.rect(-2.6, 0.15, 2.6, 0.55, "brick_brown", -SET, 0.0)
            f.rect(-2.6, 3.35, 2.6, 3.75, "brick_brown", -0.08, 0.0)
        for (a, c, b, d) in wall_rects(f.u0, f.u1, 0.0, CURB, ops):
            f.rect(a, c, b, d, "stone_grey", -SET, 0.0)

    # inner (courtyard-facing) walls with arcade openings
    ins = [Face(bd, "y", -ci - t, -ci, +1, -ci - t, ci + t),
           Face(bd, "y", ci, ci + t, -1, -ci - t, ci + t),
           Face(bd, "x", -ci - t, -ci, +1, -ci - t, ci + t),
           Face(bd, "x", ci, ci + t, -1, -ci - t, ci + t)]
    span = (ci + t) - (-ci - t)
    n = 4
    margin = 2.4
    sp = (span - 2 * margin) / n
    centers = [(-ci - t) + margin + sp * (i + 0.5) for i in range(n)]
    for idx, f in enumerate(ins):
        ops = []
        if idx == 0:
            ops.append(gate)
            ops.append(dict(u0=-6.6, u1=-4.0, z0=0.15, z1=3.0, arch=True))
            ops.append(dict(u0=4.0, u1=6.6, z0=0.15, z1=3.0, arch=True))
        else:
            for cu in centers:
                ops.append(dict(u0=cu - 1.3, u1=cu + 1.3, z0=0.15, z1=3.0, arch=True))
        f.wall(0.15, top, ops, "facade_plaster_bone")

    # ring rooms floor + courtyard hardscape
    bd.box(-w, -w, 0.0, w, w, 0.03, "paving_slab")
    bd.box(-ci, -ci, 0.02, ci, ci, 0.06, "paving_slab")
    # low planter edge (hardscape only - Nature adds the plants)
    pw, ph = 0.6, 0.45
    a = ci - 2.2
    bd.box(-a - pw, -a - pw, 0.06, a + pw, -a, ph, "stone_grey")
    bd.box(-a - pw, a, 0.06, a + pw, a + pw, ph, "stone_grey")
    bd.box(-a - pw, -a, 0.06, -a, a, ph, "stone_grey")
    bd.box(a, -a, 0.06, a + pw, a, ph, "stone_grey")

    # ring roof + parapets
    bd.box(-w, -w, top, w, -ci, top + 0.12, "roof_bitumen")
    bd.box(-w, ci, top, w, w, top + 0.12, "roof_bitumen")
    bd.box(-w, -ci, top, -ci, ci, top + 0.12, "roof_bitumen")
    bd.box(ci, -ci, top, w, ci, top + 0.12, "roof_bitumen")
    par = 0.9
    bd.box(-w, -w, top, w, -w + t, top + par, "facade_plaster_sand")
    bd.box(-w, w - t, top, w, w, top + par, "facade_plaster_sand")
    bd.box(-w, -w + t, top, -w + t, w - t, top + par, "facade_plaster_sand")
    bd.box(w - t, -w + t, top, w, w - t, top + par, "facade_plaster_sand")
    c = 0.05
    bd.box(-w - c, -w - c, top + par, w + c, -w + t + c, top + par + 0.12, "stone_grey")
    bd.box(-w - c, w - t - c, top + par, w + c, w + c, top + par + 0.12, "stone_grey")
    bd.box(-w - c, -w + t + c, top + par, -w + t + c, w - t - c, top + par + 0.12, "stone_grey")
    bd.box(w - t - c, -w + t + c, top + par, w + c, w - t - c, top + par + 0.12, "stone_grey")
    # inner (courtyard) parapet
    ip = 0.7
    bd.box(-ci - t, -ci - t, top, ci + t, -ci, top + ip, "facade_plaster_bone")
    bd.box(-ci - t, ci, top, ci + t, ci + t, top + ip, "facade_plaster_bone")
    bd.box(-ci - t, -ci, top, -ci, ci, top + ip, "facade_plaster_bone")
    bd.box(ci, -ci, top, ci + t, ci, top + ip, "facade_plaster_bone")
    return bd


# ------------------------------------------------------- LM_BAZAAR hero hall
BAZ = dict(h=32.125, wf=31.675, mw=28.5, arc_top=5.0, main_top=10.0,
           lantern=8.0, turret_r=2.1)


def _baz_openings(wf):
    n, margin = 13, 4.6
    span = 2.0 * wf - 2.0 * margin
    sp = span / n
    centers = [-wf + margin + sp * (i + 0.5) for i in range(n)]
    piers = [-wf + margin + sp * i for i in range(1, n)]
    return centers, piers


def build_bazaar():
    bd = Builder()
    H, wf, mw = BAZ["h"], BAZ["wf"], BAZ["mw"]
    at, mt = BAZ["arc_top"], BAZ["main_top"]
    centers, piers = _baz_openings(wf)

    # podium / plinth (also the hall floor base)
    bd.box(-H, -H, 0.0, H, H, CURB, "stone_grey")
    bd.box(-mw, -mw, CURB, mw, mw, CURB + 0.04, "paving_slab")

    # ---- outer arched colonnade
    arc_out = [Face(bd, "y", -wf, -wf + 1.0, -1, -wf, wf),
               Face(bd, "y", wf - 1.0, wf, +1, -wf, wf),
               Face(bd, "x", -wf, -wf + 1.0, -1, -wf, wf),
               Face(bd, "x", wf - 1.0, wf, +1, -wf, wf)]
    aops = [dict(u0=c - 1.5, u1=c + 1.5, z0=CURB, z1=4.75, arch=True)
            for c in centers]
    for f in arc_out:
        f.wall(CURB, at, aops, "brick_red")
        # striped brickwork on every pier
        for i, pc in enumerate(piers):
            z = 0.75
            while z < 3.9:
                f.rect(pc - 0.72, z, pc + 0.72, z + 0.34,
                       "brick_brown" if int(z * 10) % 2 else "stone_grey",
                       -0.07, 0.0)
                z += 0.72
        f.rect(f.u0, at - 0.4, f.u1, at, "stone_grey", -0.14, 0.0)

    # ---- main hall wall (recessed behind the arcade)
    main_out = [Face(bd, "y", -mw, -mw + 0.8, -1, -mw, mw),
                Face(bd, "y", mw - 0.8, mw, +1, -mw, mw),
                Face(bd, "x", -mw, -mw + 0.8, -1, -mw, mw),
                Face(bd, "x", mw - 0.8, mw, +1, -mw, mw)]
    mops = [dict(u0=-6.0, u1=-3.0, z0=CURB, z1=4.4, arch=True),
            dict(u0=3.0, u1=6.0, z0=CURB, z1=4.4, arch=True)]
    for cu in (-16.0, -8.0, 0.0, 8.0, 16.0):
        mops.append(dict(u0=cu - 1.1, u1=cu + 1.1, z0=6.2, z1=8.6, arch=True))
    for f in main_out:
        f.wall(CURB, mt, mops, "brick_red")
        for op in mops:
            cu = (op["u0"] + op["u1"]) * 0.5
            r = (op["u1"] - op["u0"]) * 0.5
            z0, z1 = op["z0"], op["z1"]
            pts = [(op["u0"], z0), (op["u1"], z0), (op["u1"], z1 - r)]
            for k in range(1, 9):
                a = math.pi * k / 8.0
                pts.append((cu + r * math.cos(a), z1 - r + r * math.sin(a)))
            pts.append((op["u0"], z1 - r))
            f.poly(pts, "glass_dark", 0.12, 0.15)
        f.rect(f.u0, mt - 0.5, f.u1, mt, "stone_grey", -0.18, 0.0)

    # ---- upper storey band: closes the gallery above the arcade
    band_top = mt + 0.6                       # 10.6 = underside of the main roof
    b_out = [Face(bd, "y", -wf, -wf + 0.8, -1, -wf, wf),
             Face(bd, "y", wf - 0.8, wf, +1, -wf, wf),
             Face(bd, "x", -wf, -wf + 0.8, -1, -wf, wf),
             Face(bd, "x", wf - 0.8, wf, +1, -wf, wf)]
    bops = [dict(u0=cu - 1.6, u1=cu + 1.6, z0=6.4, z1=9.4, arch=True)
            for cu in (-24.0, -12.0, 0.0, 12.0, 24.0)]
    for f in b_out:
        f.wall(at, band_top, bops, "brick_red")
        for op in bops:
            cu = (op["u0"] + op["u1"]) * 0.5
            r = (op["u1"] - op["u0"]) * 0.5
            z0, z1 = op["z0"], op["z1"]
            pts = [(op["u0"], z0), (op["u1"], z0), (op["u1"], z1 - r)]
            for k in range(1, 9):
                a = math.pi * k / 8.0
                pts.append((cu + r * math.cos(a), z1 - r + r * math.sin(a)))
            pts.append((op["u0"], z1 - r))
            f.poly(pts, "glass_dark", 0.12, 0.15)
        # string course on top of the arcade cornice + cornice under the roof
        f.rect(f.u0, at, f.u1, at + 0.22, "stone_grey", -0.15, 0.0)
        f.rect(f.u0, band_top - 0.6, f.u1, band_top, "stone_grey", -0.19, 0.0)

    # ---- aisle ceiling + main roof
    bd.box(-wf, -wf, at, wf, -mw, at + 0.3, "plaster_white")
    bd.box(-wf, mw, at, wf, wf, at + 0.3, "plaster_white")
    bd.box(-wf, -mw, at, -mw, mw, at + 0.3, "plaster_white")
    bd.box(mw, -mw, at, wf, mw, at + 0.3, "plaster_white")
    bd.box(-wf, -wf, mt, wf, wf, mt + 0.6, "roof_bitumen")
    # parapet + coping
    pt, t = 1.0, 0.5
    bd.box(-wf, -wf, mt + 0.6, wf, -wf + t, mt + 0.6 + pt, "brick_red")
    bd.box(-wf, wf - t, mt + 0.6, wf, wf, mt + 0.6 + pt, "brick_red")
    bd.box(-wf, -wf + t, mt + 0.6, -wf + t, wf - t, mt + 0.6 + pt, "brick_red")
    bd.box(wf - t, -wf + t, mt + 0.6, wf, wf - t, mt + 0.6 + pt, "brick_red")
    c = 0.08
    for x0, y0, x1, y1 in ((-wf - c, -wf - c, wf + c, -wf + t + c),
                           (-wf - c, wf - t - c, wf + c, wf + c),
                           (-wf - c, -wf + t + c, -wf + t + c, wf - t - c),
                           (wf - t - c, -wf + t + c, wf + c, wf - t - c)):
        bd.box(x0, y0, mt + 0.6 + pt, x1, y1, mt + 0.6 + pt + 0.14, "stone_grey")

    # ---- clerestory lantern
    lz0, lz1 = mt + 0.6, 13.6
    lh = BAZ["lantern"]
    lout = [Face(bd, "y", -lh, -lh + 0.5, -1, -lh, lh),
            Face(bd, "y", lh - 0.5, lh, +1, -lh, lh),
            Face(bd, "x", -lh, -lh + 0.5, -1, -lh, lh),
            Face(bd, "x", lh - 0.5, lh, +1, -lh, lh)]
    lops = []
    for cu in (-6.0, -3.0, 0.0, 3.0, 6.0):
        lops.append(dict(u0=cu - 1.0, u1=cu + 1.0, z0=lz0 + 0.4, z1=lz1 - 0.3,
                         arch=True))
    for f in lout:
        f.wall(lz0, lz1, lops, "brick_red")
        for op in lops:
            cu = (op["u0"] + op["u1"]) * 0.5
            r = (op["u1"] - op["u0"]) * 0.5
            z0, z1 = op["z0"], op["z1"]
            pts = [(op["u0"], z0), (op["u1"], z0), (op["u1"], z1 - r)]
            for k in range(1, 9):
                a = math.pi * k / 8.0
                pts.append((cu + r * math.cos(a), z1 - r + r * math.sin(a)))
            pts.append((op["u0"], z1 - r))
            f.poly(pts, "glass_dark", 0.10, 0.13)
        f.rect(f.u0, lz1 - 0.35, f.u1, lz1, "stone_grey", -0.16, 0.0)
    bd.box(-lh - 0.2, -lh - 0.2, lz1, lh + 0.2, lh + 0.2, lz1 + 0.3, "roof_bitumen")

    # ---- dome
    bd.cyl(0.0, 0.0, lz1 + 0.3, lz1 + 1.3, 6.5, "brick_red", seg=18)
    bd.dome(0.0, 0.0, lz1 + 1.3, 6.5, "roof_tile_red", seg=18, rings=7)
    bd.cyl(0.0, 0.0, lz1 + 7.6, lz1 + 8.4, 0.35, "metal_rusty", seg=8)
    bd.dome(0.0, 0.0, lz1 + 8.4, 0.7, "metal_rusty", seg=8, rings=3)

    # ---- corner turrets
    for sx in (-1, 1):
        for sy in (-1, 1):
            tx, ty = sx * (wf - BAZ["turret_r"]), sy * (wf - BAZ["turret_r"])
            bd.cyl(tx, ty, CURB, 16.0, BAZ["turret_r"], "brick_red", seg=14)
            for z in (3.2, 5.6, 8.0, 10.4, 12.8):
                bd.cyl(tx, ty, z, z + 0.4, BAZ["turret_r"] + 0.07,
                       "stone_grey" if int(z) % 2 else "brick_brown", seg=14, cap=False)
            bd.cyl(tx, ty, 16.0, 16.5, BAZ["turret_r"] + 0.15, "stone_grey", seg=14)
            # conical cap
            seg, r, base = 14, BAZ["turret_r"] + 0.1, 16.5
            apex = (tx, ty, base + 3.6)
            ring = []
            for k in range(seg):
                a = 2.0 * math.pi * k / seg
                ring.append((tx + r * math.cos(a), ty + r * math.sin(a), base))
            for k in range(seg):
                k2 = (k + 1) % seg
                bd.poly([ring[k], ring[k2], apex], "roof_tile_red")
            bd.cyl(tx, ty, base + 3.6, base + 4.4, 0.18, "metal_rusty", seg=6)
    return bd


# ------------------------------------------------------------------- props
def fan_disc(bd, cx, cy, cz, r, tilt, mat, seg=12):
    """Flat disc whose normal points outward+up by `tilt` degrees (dish)."""
    t = math.radians(tilt)
    nx, ny, nz = 0.0, -math.cos(t), math.sin(t)
    ux, uy, uz = 1.0, 0.0, 0.0
    vx, vy, vz = 0.0, nz, -ny
    i = bd.midx(mat)
    c = len(bd.v)
    bd.v.append((cx, cy, cz))
    for k in range(seg):
        a = 2.0 * math.pi * k / seg
        bd.v.append((cx + ux * r * math.cos(a) + vx * r * math.sin(a),
                     cy + uy * r * math.cos(a) + vy * r * math.sin(a),
                     cz + uz * r * math.cos(a) + vz * r * math.sin(a)))
    for k in range(seg):
        bd.f.append((c, c + 1 + k, c + 1 + (k + 1) % seg))
        bd.mi.append(i)


def p_sign_fascia(neon):
    bd = Builder()
    bd.box(-2.85, -0.10, -0.05, 2.85, 0.0, 0.77, "wood_old")
    bd.box(-2.75, -0.14, 0.0, 2.75, -0.10, 0.72, "sign_metal")
    bd.box(-2.25, -0.19, 0.14, -1.0, -0.14, 0.58, neon)
    bd.box(-0.65, -0.19, 0.14, 0.35, -0.14, 0.58, neon)
    bd.box(0.8, -0.19, 0.14, 2.2, -0.14, 0.58, neon)
    return bd


def p_sign_blade(neon, proj=1.0):
    """Perpendicular hanging sign: `proj` metres out from the facade (0.8-1.2 m),
    two bracket arms at the top, panel hanging below (bottom clears ground by z_plc)."""
    bd = Builder()
    y0, y1 = -proj, -proj + 0.12          # panel plate
    bd.box(-0.6, y0, 0.0, 0.6, y1, 0.6, "sign_metal")
    bd.box(-0.52, y0 - 0.03, 0.08, 0.52, y1, 0.52, neon)
    # bracket arms back to the wall
    for ax in (-0.5, 0.5):
        bd.box(ax - 0.05, -proj, 0.6, ax + 0.05, 0.0, 0.68, "metal_steel")
        bd.box(ax - 0.04, -proj, 0.06, ax + 0.04, -proj + 0.08, 0.68, "metal_steel")
        bd.box(ax - 0.05, -0.10, 0.30, ax + 0.05, 0.0, 0.66, "metal_steel")
    return bd


def beam_yz(bd, x0, x1, y0, z0, y1, z1, t, mat):
    """Rectangular bar of thickness `t` running from (y0,z0) to (y1,z1) over x0..x1."""
    dy, dz = y1 - y0, z1 - z0
    L = math.hypot(dy, dz) or 1.0
    oy, oz = -dz / L * t * 0.5, dy / L * t * 0.5
    a = [(y0 + oy, z0 + oz), (y1 + oy, z1 + oz), (y1 - oy, z1 - oz), (y0 - oy, z0 - oz)]
    bd.poly([(x0, p[0], p[1]) for p in a], mat)
    bd.poly([(x1, p[0], p[1]) for p in reversed(a)], mat)
    for k in range(4):
        p, q = a[k], a[(k + 1) % 4]
        bd.poly([(x0, p[0], p[1]), (x1, p[0], p[1]), (x1, q[0], q[1]), (x0, q[0], q[1])], mat)


def p_awning(mat, proj=1.4):
    """Sloped shop awning, `proj` metres out from the wall plane.

    Attached at z=0 (placed at AWN_Z = 3.20): soffit = -0.50 -> 2.70 m,
    lowest vertex (valance) = -0.60 -> 2.60 m.  Both >= 2.6 m, and the top
    rail sits 0.15 m under the fascia sign at 3.35 m."""
    bd = Builder()
    xa, xb = -1.6, 1.6
    drop = 0.40
    top = [(xa, 0.0, 0.0), (xb, 0.0, 0.0), (xb, -proj, -drop), (xa, -proj, -drop)]
    bot = [(xa, 0.0, -0.10), (xb, 0.0, -0.10), (xb, -proj, -drop - 0.10),
           (xa, -proj, -drop - 0.10)]
    bd.poly(top, mat)
    bd.poly(list(reversed(bot)), mat)
    bd.poly([top[3], top[2], bot[2], bot[3]], mat)
    bd.poly([top[0], bot[0], bot[1], top[1]], mat)
    bd.box(xa, -proj - 0.02, -0.60, xb, -proj + 0.04, -0.50, mat)               # valance
    bd.box(xa, -proj - 0.03, -0.56, xb, -proj + 0.05, -0.51, "metal_steel")     # strip
    for sx in (-1.5, 1.44):                       # diagonal brackets
        beam_yz(bd, sx, sx + 0.06, -0.02, -0.06, -proj + 0.06, -drop - 0.06, 0.06,
                "metal_steel")
    return bd


def p_lamp():
    bd = Builder()
    bd.box(-0.04, -0.30, -0.04, 0.04, 0.0, 0.04, "metal_steel")
    bd.box(-0.03, -0.30, 0.04, 0.03, -0.26, 0.18, "metal_steel")
    bd.box(-0.18, -0.44, 0.10, 0.18, -0.22, 0.18, "metal_painted_dark")
    bd.box(-0.14, -0.42, -0.06, 0.14, -0.26, 0.10, "emissive_warm")
    return bd


def p_pipe(height):
    bd = Builder()
    bd.cyl(-0.07, -0.06, 0.0, height, 0.06, "metal_rusty", seg=8, cap=False)
    z = 0.4
    while z < height - 0.2:
        bd.box(-0.16, -0.10, z, 0.02, 0.0, z + 0.09, "metal_steel")
        z += 2.6
    bd.box(-0.14, -0.12, height, 0.0, 0.0, height + 0.14, "metal_steel")
    return bd


def p_ac():
    bd = Builder()
    bd.box(-0.42, -0.44, -0.3, 0.42, 0.0, 0.3, "metal_steel")
    bd.box(-0.34, -0.47, -0.22, 0.34, -0.44, 0.22, "metal_painted_dark")
    bd.box(-0.4, -0.1, -0.4, 0.4, 0.0, -0.34, "metal_steel")
    bd.box(-0.4, -0.1, 0.34, 0.4, 0.0, 0.4, "metal_steel")
    return bd


def p_dish():
    bd = Builder()
    bd.box(-0.05, -0.3, -0.12, 0.05, 0.0, 0.12, "metal_steel")
    bd.box(-0.1, -0.34, -0.16, 0.1, -0.26, 0.16, "metal_steel")
    fan_disc(bd, 0.0, -0.4, 0.16, 0.36, 40.0, "metal_steel", seg=12)
    return bd


def p_crate():
    bd = Builder()
    bd.box(-0.42, -0.43, 0.0, 0.42, 0.0, 0.5, "wood_old")
    bd.box(-0.45, -0.44, 0.5, 0.45, 0.03, 0.56, "wood_planks")
    bd.box(-0.44, -0.44, 0.16, 0.44, -0.40, 0.22, "wood_planks")
    return bd


def p_stall():
    bd = Builder()
    bd.box(-0.85, -0.43, 0.0, 0.85, 0.0, 0.9, "wood_old")
    bd.box(-0.9, -0.44, 0.9, 0.9, 0.02, 0.97, "wood_planks")
    bd.box(-0.8, -0.4, 0.97, 0.8, -0.06, 1.06, "canvas_tarp")
    bd.box(-0.85, -0.42, 0.2, 0.85, -0.38, 0.26, "wood_planks")
    return bd


def p_vent():
    bd = Builder()
    bd.box(-0.45, -0.44, 0.0, 0.45, 0.0, 0.55, "metal_rusty")
    bd.box(-0.4, -0.48, 0.08, 0.4, -0.44, 0.47, "metal_steel")
    bd.cyl(0.0, -0.24, 0.55, 2.4, 0.14, "metal_rusty", seg=8, cap=False)
    return bd


def p_chimney():
    bd = Builder()
    bd.box(-0.3, -0.3, 0.0, 0.3, 0.3, 1.3, "brick_red")
    bd.box(-0.38, -0.38, 1.3, 0.38, 0.38, 1.44, "stone_grey")
    bd.cyl(0.0, 0.0, 1.44, 1.7, 0.12, "metal_rusty", seg=8)
    return bd


def p_tank():
    bd = Builder()
    for sx in (-0.4, 0.4):
        for sy in (-0.4, 0.4):
            bd.box(sx - 0.05, sy - 0.05, 0.0, sx + 0.05, sy + 0.05, 0.6, "metal_steel")
    bd.cyl(0.0, 0.0, 0.6, 1.8, 0.6, "metal_rusty", seg=12)
    bd.cyl(0.0, 0.0, 1.8, 1.92, 0.5, "metal_steel", seg=12)
    return bd


def p_roofac():
    bd = Builder()
    bd.box(-0.5, -0.35, 0.0, 0.5, 0.35, 0.55, "metal_steel")
    bd.box(-0.42, -0.38, 0.55, 0.42, 0.38, 0.62, "metal_painted_dark")
    bd.cyl(0.0, 0.0, 0.62, 0.86, 0.22, "metal_steel", seg=10)
    return bd


def p_lantern():
    bd = Builder()
    bd.box(-0.02, -0.02, -0.55, 0.02, 0.02, 0.0, "metal_steel")
    bd.cyl(0.0, 0.0, -0.95, -0.58, 0.17, "emissive_warm", seg=8)
    bd.cyl(0.0, 0.0, -0.55, -0.5, 0.2, "metal_painted_dark", seg=8)
    bd.cyl(0.0, 0.0, -1.05, -0.95, 0.07, "metal_painted_dark", seg=6)
    return bd


def p_banner():
    bd = Builder()
    bd.box(-1.5, -0.1, -1.4, 1.5, 0.0, 0.0, "sign_metal")
    bd.box(-1.4, -0.14, -1.2, 1.4, -0.1, -0.9, "neon_pink")
    bd.box(-1.4, -0.14, -0.5, 1.4, -0.1, -0.28, "emissive_warm")
    bd.box(-1.55, -0.16, -0.1, 1.55, 0.0, 0.06, "metal_steel")
    return bd


def p_bstall():
    bd = Builder()
    bd.box(-1.3, -0.7, 0.0, 1.3, 0.0, 0.95, "wood_old")
    bd.box(-1.35, -0.75, 0.95, 1.35, 0.05, 1.02, "wood_planks")
    for sx in (-1.3, 1.3):
        bd.box(sx - 0.06, -0.72, 0.0, sx + 0.06, -0.6, 2.3, "wood_old")
    bd.box(-1.45, -0.8, 2.3, 1.45, 0.05, 2.42, "awning_fabric_stripe")
    bd.box(-1.2, -0.6, 1.02, 1.2, -0.1, 1.1, "canvas_tarp")
    return bd


# ------------------------------------------------------------------ placement
def put(kit, key, fn, name, cx, cy, xl, yl, z, prot, coll, rot=0, slot=None):
    mesh = kit.get(key, (int(rot) + int(prot)) % 360, fn)
    a = math.radians(rot)
    c, s = math.cos(a), math.sin(a)
    wx = cx + xl * c - yl * s
    wy = cy + xl * s + yl * c
    return new_obj(name, mesh, (wx, wy, z), coll, slot)


class Ctx(object):
    def __init__(self, layout, parcels):
        self.layout = layout
        self.parcels = parcels
        self.root = ck.ensure_collection("Market")
        self.meshes = ck.ensure_collection("Meshes", parent=self.root)
        self.colliders = ck.ensure_collection("Colliders", parent=self.root)
        self.lights = ck.ensure_collection("Lights", parent=self.root)
        self.shell = Kit("SM_Bldg")
        self.inter = Kit("INT")
        self.prop = Kit("SM_Prop")
        self.coll = Kit("COL")
        self.stair = Kit("SM_Stair_Ext")
        self.count = {}
        self.tier_tris = {0: 0, 1: 0, 2: 0, 3: 0}
        self.tier_count = {0: 0, 1: 0, 2: 0, 3: 0}
        self.placed = 0
        self.tris = 0
        self.props = 0
        self.buildings = 0          # parcels with a building (int)
        self.stairs = 0             # external stairs placed
        self.stair_hatch = 0        # ...of which roof-access (single-storey)
        self.light_specs = []       # provisional LT_market_* points (pos/kind/...)
        self.colliders_n = 0
        self.collider_tris = 0
        self.parcel_ids = set()     # every parcel that got something
        self.bboxes = []            # ((x0,y0,x1,y1), parcel_id)
        self.parcel_tris = []       # (tier, tris spent on that parcel)
        self.bazaar_tris = 0
        self.violations = []
        self.mat_used = set()
        self.road = build_road_grid(layout)

    def uniq(self, prefix, key):
        n = self.count.get(key, 0) + 1
        self.count[key] = n
        return "%s_%03d" % (prefix, n)

    def add(self, ob, tier):
        self.placed += 1
        t = mesh_tris(ob.data)
        self.tris += t
        self.tier_tris[tier] = self.tier_tris.get(tier, 0) + t
        for m in ob.data.materials:
            if m is not None:
                self.mat_used.add(m.name)
        return ob


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
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        if x1 < 260 or x0 > 1240 or y1 < 560 or y0 > 1240:
            continue
        r = float(e.get("width", 6.0)) * 0.5
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
    """Return the compass side of `p` that faces the closest road segment."""
    x0, y0, x1, y1 = p["rect"]
    cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
    best, bside = 1e18, "S"
    for (ax, ay, bx, by, r) in segs:
        # distance from centre to segment
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


def frontage_pattern(front):
    fs = frozenset(front)
    if len(fs) == 0:
        return "single", 0
    if len(fs) == 1:
        return "single", ROT[list(fs)[0]]
    if len(fs) == 2 and fs in PAIR_MAP:
        return PAIR_MAP[fs]
    if len(fs) >= 4:
        return "single", 0
    return "single", ROT[list(fs)[0]]


def _abbr(s):
    return "".join(w[0] for w in str(s).split("_"))[:6].upper()


SETBACK = {"R": 3.0, "D": 4.0, "E": 2.0, "M": 0.5, "I": 6.0}   # generate_layout.py:127
CIVIC_FULL_LOT = ("covered_bazaar_hall",)     # civic landmark builds to the lot line


def buildable_rect_for(p):
    """Buildable rect for ANY parcel, using the one rule generate_layout.py uses.

    generate_layout.py:416 is the source of truth:

        "buildable_rect": rect_inset(rect, SETBACK.get(d, 0.0)) if ptype != "yard" else rect

    A single exemption, applied here too:
      * ptype == "yard"  -> the lot itself (no setback)

    Everything else - including the civic bazaar lot - takes the district
    setback, exactly as generate_layout.py computes it (verified: all 1236
    shipped buildable_rect values equal rect +/- setback, 0 mismatches).

    The 95 courtyard parcels and BZ_6_6_1_1 ship `buildable_rect: null` in
    parcels_M.json; they are NOT special-cased - they follow exactly the same
    rule as every other parcel, so the rect of a courtyard parcel describes the
    OUTER footprint of its ring block (the courtyard hole stays open: it is
    open ground inside that rect, never filled).
    """
    r = [float(v) for v in p["rect"]]
    if p.get("type") == "yard":
        return r
    s = SETBACK.get(p.get("district", "M"), 0.0)
    if s <= 0.0:
        return r
    return [r[0] + s, r[1] + s, r[2] - s, r[3] - s]


def brect(p):
    """Back-compat alias - one rule for every parcel (see buildable_rect_for)."""
    return buildable_rect_for(p)


def decorate(ctx, cx, cy, rot, typ, style, floors, pattern, rng, roof_kind, top):
    """Instance shared street props onto one building (local frame + rot)."""
    P = ctx.prop

    def pp(key, fn, nm, xl, yl, z, prot=0, coll=None, slot=None):
        mesh = P.get(key, (int(rot) + int(prot)) % 360, fn)
        a = math.radians(rot)
        c, s = math.cos(a), math.sin(a)
        ob = new_obj(nm, mesh, (cx + xl * c - yl * s, cy + xl * s + yl * c, z),
                     coll or ctx.meshes, slot)
        ctx.placed += 1
        ctx.props += 1
        ctx.tris += mesh_tris(mesh)
        for m in mesh.materials:
            if m is not None:
                ctx.mat_used.add(m.name)
        return ob

    neon = rng.choice(["neon_red", "neon_green", "neon_blue", "neon_pink"])
    pipe_side = 1 if rng.random() < 0.5 else -1
    lamp_side = -pipe_side
    has_bal = floors >= 2 and (style == "timber_balcony" or typ == "teahouse")
    awn_z = AWN_Z

    # fascia sign (front)
    if style != "timber_balcony" and rng.random() < 0.85:
        pp(("fas", neon), lambda: make_mesh("fas", p_sign_fascia(neon)),
           "SM_Sign_Fascia_%s" % neon, rng.uniform(-0.9, 0.9), -WH, 3.35)
    # hanging bracket sign
    if rng.random() < 0.55:
        bn = rng.choice(["neon_red", "neon_blue", "neon_pink", "neon_green"])
        pp(("bla", bn), lambda: make_mesh("bla", p_sign_blade(bn)),
           "SM_Sign_Blade_%s" % bn,
           rng.choice([-6.0, 6.0]) * (1 if pipe_side < 0 else 1), -WH, 2.8)
    # awning (skipped where a balcony occupies the same band)
    if not has_bal and rng.random() < 0.7:
        am = rng.choice(["awning_fabric_red", "awning_fabric_green",
                         "awning_fabric_stripe"])
        pp(("awn", am), lambda: make_mesh("awn", p_awning(am)),
           "SM_Awning_%s" % am, rng.uniform(-1.0, 1.0), -WH, awn_z)
    # wall lamps  (Lights collection - emissive fixtures, no real light objects)
    for u in (lamp_side * 4.6, pipe_side * 6.6):
        if u == pipe_side * 6.6 and rng.random() > 0.5:
            continue
        pp("lamp", lambda: make_mesh("lamp", p_lamp()), "SM_WallLamp_01",
           u, -WH, 4.7 if u == pipe_side * 6.6 else 2.95, 0, ctx.lights)
    # downpipe (full height, one per building)
    ph = float(floors) * FL
    pp(("pipe", ph), lambda: make_mesh("pipe", p_pipe(ph)), "SM_Downpipe_01",
       pipe_side * 7.02, -WH, 0.0)
    # AC unit / satellite dish (upper floors)
    if floors >= 2:
        if rng.random() < 0.55:
            pp("ac", lambda: make_mesh("ac", p_ac()), "SM_ACUnit_01",
               lamp_side * 6.2, -WH, FL + 1.7)
        if rng.random() < 0.35:
            pp("dish", lambda: make_mesh("dish", p_dish()), "SM_SatDish_01",
               pipe_side * 6.2, -WH, FL + 2.4)
    # crates / stall stubs against the wall (<=0.44 m projection)
    if rng.random() < 0.45:
        pp("crate", lambda: make_mesh("crate", p_crate()), "SM_Crate_01",
           lamp_side * 5.9, -WH, CURB)
    if rng.random() < 0.3:
        pp("stall", lambda: make_mesh("stall", p_stall()), "SM_StallStub_01",
           pipe_side * 5.9, -WH, CURB)
    # restaurant extractor vents
    if typ == "restaurant":
        pp("vent", lambda: make_mesh("vent", p_vent()), "SM_ExtractorVent_01",
           pipe_side * 6.3, -WH, 2.5)
    # workshop rolling shutter + facade pipes
    if typ == "workshop":
        pp("wsh", lambda: make_mesh("wsh", p_wshutter()), "SM_RollerShutter_01",
           -1.75, -WH + 0.05, 0.0)
        for u in (-4.1, 4.1):
            pp(("pipe", ph), lambda: make_mesh("pipe", p_pipe(ph)),
               "SM_Pipe_01", u, -WH, 0.0)

    # ---- props on the side frontage (pair patterns)
    if pattern in ("pairL", "pairR"):
        xl = -WH if pattern == "pairL" else WH
        prot = 270 if pattern == "pairL" else 90
        pp("lamp", lambda: make_mesh("lamp", p_lamp()), "SM_WallLamp_01",
           xl, -6.4, 3.0, prot)
        pp(("pipe", ph), lambda: make_mesh("pipe", p_pipe(ph)),
           "SM_Downpipe_01", xl, 2.9, 0.0, prot)
        if rng.random() < 0.6:
            bn = rng.choice(["neon_red", "neon_green", "neon_pink"])
            pp(("bla", bn), lambda: make_mesh("bla", p_sign_blade(bn)),
               "SM_Sign_Blade_%s" % bn, xl, 2.0, 2.8, prot)
        if rng.random() < 0.5:
            am = rng.choice(["awning_fabric_red", "awning_fabric_stripe"])
            pp(("awn", am), lambda: make_mesh("awn", p_awning(am)),
               "SM_Awning_%s" % am, xl, 0.0, awn_z, prot)
        if rng.random() < 0.4:
            pp("crate", lambda: make_mesh("crate", p_crate()), "SM_Crate_01",
               xl, -4.4, CURB, prot)

    # ---- roof clutter
    slots = [(-4.4, -3.8), (4.3, -3.4), (-3.6, 2.2), (4.5, 2.3), (0.4, -5.0)]
    rng.shuffle(slots)
    if roof_kind == "pitched":
        if rng.random() < 0.5:
            pp("chim", lambda: make_mesh("chim", p_chimney()), "SM_Chimney_01",
               slots[0][0] * 0.2, 0.0, top + 0.6)
    else:
        i = 0
        if rng.random() < 0.7:
            pp("chim", lambda: make_mesh("chim", p_chimney()), "SM_Chimney_01",
               slots[0][0], slots[0][1], top)
            i = 1
        if rng.random() < 0.4:
            pp("tank", lambda: make_mesh("tank", p_tank()), "SM_WaterTank_01",
               slots[i][0], slots[i][1], top)
            i += 1
        if rng.random() < 0.6 and i < len(slots):
            pp("rfac", lambda: make_mesh("rfac", p_roofac()), "SM_RoofAC_01",
               slots[i][0], slots[i][1], top)


def p_stair():
    """Shared external stair (one mesh, linked instances).

    Local frame: y = 0 at the rear WALL face, running out into the rear yard.
    16 risers of 0.2 m: a 0.45 m top landing (== SET, it sits exactly on the
    rear plinth cap, which is SET deep and CURB high) + 15 treads of 0.25 m
    = 0.45 + 3.75 = 4.20 m run.  Free rear depth is HALF - REAR = 4.45 m, so
    the footprint stops 0.25 m short of the buildable edge - nothing here can
    cross buildable_rect, and the flight stays clear of the facing facade.

    Top of flight z = 3.2 == FL: first-floor door threshold on multi-storey
    shells, roof-deck level on single-storey shells (through the parapet
    access hatch)."""
    bd = Builder()
    x0, x1 = -STAIR_W * 0.5, STAIR_W * 0.5
    land = SET                       # 0.45 top landing == rear plinth depth
    tread, riser = 0.25, 0.2
    top = FL                         # 3.2 -> door threshold / roof deck
    n = int(round(top / riser))      # 16 risers
    y = 0.0
    for k in range(n + 1):
        z = top - riser * k
        if z <= 1e-6:                # the last riser lands on grade
            break
        w = land if k == 0 else tread
        y_a, y_b = y, y + w
        bd.box(x0 - 0.06, y_a, CURB if y_a < land else 0.0,
               x1 + 0.06, y_b, z, "stone_grey")
        if k > 0:                    # nosing lip
            bd.box(x0 - 0.06, y_b - 0.03, z - 0.02, x1 + 0.06, y_b, z + 0.02,
                   "stone_grey")
        y = y_b
    # stringers + handrails (start at the end of the landing so they run
    # parallel to the flight; the -0.03 keeps the bar's 0.07 section inside)
    for sx in (-1, 1):
        bx0, bx1 = sorted((sx * (STAIR_W * 0.5), sx * (STAIR_W * 0.5 + 0.08)))
        beam_yz(bd, bx0, bx1, land, top + 1.0, y - 0.03, riser + 1.0, 0.07,
                "metal_steel")
        p = land
        while p < y - 0.12:          # posts, one every 1.1 m along the flight
            zz = top - (top - riser) * ((p - land) / max(y - land, 1e-6)) + 0.05
            bd.box(bx0, p, zz, bx1, p + 0.07, zz + 0.95, "metal_steel")
            p += 1.1
    return bd


def p_wshutter():
    bd = Builder()
    bd.box(-1.75, -0.02, 0.0, 1.75, 0.06, 3.05, "metal_painted_dark")
    z = 0.35
    while z < 3.0:
        bd.box(-1.75, -0.05, z, 1.75, 0.07, z + 0.07, "metal_steel")
        z += 0.42
    bd.box(-1.85, -0.06, 3.05, 1.85, 0.12, 3.3, "metal_rusty")
    bd.box(-1.8, -0.04, 0.0, -1.7, 0.08, 3.1, "metal_steel")
    bd.box(1.7, -0.04, 0.0, 1.8, 0.08, 3.1, "metal_steel")
    return bd


# ------------------------------------------------------------- parcel placing
def collider_mesh(rect, h):
    """Box collider built in the parcel's local frame (Z-rotation is baked in
    by the Kit, the object only carries a translation to the rect centre).

    `rect` is (x0, y0, x1, y1): regular buildings use the trimmed envelope
    (-HALF, -HALF, HALF, REAR_EDGE) so the collider never covers the rear yard
    / external stair; the bazaar uses its whole buildable_rect."""
    bd = Builder()
    bd.box(rect[0], rect[1], 0.0, rect[2], rect[3], h, "concrete")
    return make_mesh("COL_box", bd)


def place_collider(ctx, p, rect, h, bb, rot=0):
    k = ("col", tuple(round(v, 3) for v in rect), round(h, 2))
    mesh = ctx.coll.get(k, rot, lambda: collider_mesh(rect, h))
    ob = new_obj("COL_%s" % p["id"], mesh,
                 ((bb[0] + bb[2]) * 0.5, (bb[1] + bb[3]) * 0.5, 0.0), ctx.colliders)
    ob.hide_render = True
    ctx.colliders_n += 1
    ctx.collider_tris += mesh_tris(mesh)


def check_rect(ctx, p, bb, name):
    br = brect(p)
    eps = 0.002
    if (bb[0] < br[0] - eps or bb[1] < br[1] - eps or
            bb[2] > br[2] + eps or bb[3] > br[3] + eps):
        ctx.violations.append(["buildable", name, p["id"],
                               [round(v, 3) for v in bb], list(br)])
    hits = road_hits(bb, ctx.road)
    if hits:
        ctx.violations.append(["road", name, p["id"], hits[:2]])
    ctx.bboxes.append((bb, p["id"]))


def place_interior(ctx, p, cx, cy, rot, tier):
    pid = p["id"]
    mesh = ctx.inter.get(("int", tier), rot,
                         lambda: make_mesh("INT_Shell_t%d" % tier,
                                           build_interior(tier)))
    nm = {3: "Depth", 2: "ShopRoom", 1: "Room1"}[tier]
    ob = new_obj("INT_%s_%s" % (pid, nm), mesh, (cx, cy, 0.0), ctx.meshes)
    ctx.add(ob, tier)
    if tier <= 2:
        f = ctx.inter.get(("furn", "shop"), rot,
                          lambda: make_mesh("INT_FurnShop", build_furn("shop")))
        ob = new_obj("INT_%s_ShopFurn" % pid, f, (cx, cy, 0.0), ctx.meshes)
        ctx.add(ob, tier)
    if tier == 1:
        f = ctx.inter.get(("furn", "back"), rot,
                          lambda: make_mesh("INT_FurnBack", build_furn("back")))
        ob = new_obj("INT_%s_Room2Furn" % pid, f, (cx, cy, 0.0), ctx.meshes)
        ctx.add(ob, tier)


def place_regular(ctx, p, rng):
    t_start = ctx.tris
    pid = p["id"]
    typ = p["type"]
    style = p.get("facade_style") or "painted_plaster"
    floors = max(1, int(p.get("floors") or 1))
    tier = int(p.get("interior_tier", 3))
    br = brect(p)
    cx = (br[0] + br[2]) * 0.5
    cy = (br[1] + br[3]) * 0.5
    pattern, rot = frontage_pattern(p.get("frontage") or [])
    a = math.radians(rot)
    ca, sa = math.cos(a), math.sin(a)
    key = (typ, style, floors, pattern)
    mesh = ctx.shell.get(key, rot, lambda: make_mesh(
        "SM_Bldg_%s_%s" % (_abbr(typ), _abbr(style)),
        build_shell(typ, style, floors, pattern)))
    pal = PALETTE[style]
    slot = pal[dhash("%d|%d" % (int(cx // 48), int(cy // 48))) % len(pal)]
    pref = "SM_Bldg_%s_%s" % (_abbr(typ), _abbr(style))
    ob = new_obj(ctx.uniq(pref, pref), mesh, (cx, cy, 0.0), ctx.meshes, slot)
    ctx.add(ob, tier)
    bb = (cx - HALF, cy - HALF, cx + HALF, cy + HALF)
    check_rect(ctx, p, bb, ob.name)
    place_interior(ctx, p, cx, cy, rot, tier)
    roof = ROOF_OF[typ]
    decorate(ctx, cx, cy, rot, typ, style, floors, pattern, rng, roof, floors * FL)

    # ---- external stair in the rear yard (see p_stair)
    #      free depth = buildable edge - rear wall face, on the rear axis
    axis_half = (br[3] - br[1]) * 0.5 if rot % 180 == 0 else (br[2] - br[0]) * 0.5
    free = axis_half - REAR
    if free >= MIN_REAR_FREE and (floors >= 2 or roof != "pitched"):
        smesh = ctx.stair.get("ext", rot, lambda: make_mesh("SM_Stair_Ext",
                                                            p_stair()))
        sob = new_obj(ctx.uniq("SM_Stair_Ext", "stair"), smesh,
                      (cx - REAR * sa, cy + REAR * ca, 0.0), ctx.meshes)
        ctx.add(sob, tier)
        ctx.stairs += 1
        if floors < 2:
            ctx.stair_hatch += 1

    # ---- provisional storefront light (t1/t2 frontages only)
    if tier in (1, 2):
        lx, ly = 0.0, -WH - 0.55
        ctx.light_specs.append(dict(
            pos=(cx + lx * ca - ly * sa, cy + lx * sa + ly * ca, 2.9),
            kind="storefront", color=(1.0, 0.78, 0.52), power=70.0, size=0.35))

    place_collider(ctx, p, (-HALF, -HALF, HALF, REAR_EDGE),
                   floors * FL + (2.7 if roof == "pitched" else 1.3), bb, rot)
    ctx.parcel_ids.add(pid)
    ctx.buildings += 1
    ctx.tier_count[tier] += 1
    ctx.parcel_tris.append((tier, ctx.tris - t_start))


def place_courtyard(ctx, p, rng):
    t_start = ctx.tris
    pid = p["id"]
    br = brect(p)
    cx = (br[0] + br[2]) * 0.5
    cy = (br[1] + br[3]) * 0.5
    side = nearest_side(p, ctx.road[2])
    rot = ROT[side]
    half = (br[2] - br[0]) * 0.5
    mesh = ctx.shell.get(("courtyard",), rot,
                         lambda: make_mesh("SM_CtYard_Hardscape", build_courtyard()))
    ob = new_obj(ctx.uniq("SM_CtYard_Hardscape", "ctyd"), mesh,
                 (cx, cy, 0.0), ctx.meshes, "facade_plaster_sand")
    ctx.add(ob, 0)
    bb = (cx - half, cy - half, cx + half, cy + half)
    check_rect(ctx, p, bb, ob.name)
    # one wall lamp beside the gate
    a = math.radians(rot)
    c, s = math.cos(a), math.sin(a)
    xl, yl = 3.2, -15.36
    mesh2 = ctx.prop.get("lamp", rot, lambda: make_mesh("lamp", p_lamp()))
    ob2 = new_obj("SM_WallLamp_01_%s" % pid[-3:], mesh2,
                  (cx + xl * c - yl * s, cy + xl * s + yl * c, 3.1), ctx.lights)
    ctx.placed += 1
    ctx.props += 1
    ctx.tris += mesh_tris(mesh2)
    q = int(rot) % 360
    hx, hy = ((br[2] - br[0]) * 0.5, (br[3] - br[1]) * 0.5)
    if q in (90, 270):                      # local axes swap with the shell
        hx, hy = hy, hx
    place_collider(ctx, p, (-hx, -hy, hx, hy), 4.6, bb, rot)
    ctx.parcel_ids.add(pid)
    ctx.buildings += 1
    ctx.tier_count[0] += 1
    ctx.parcel_tris.append((0, ctx.tris - t_start))


def place_bazaar(ctx, p):
    t_start = ctx.tris
    pid = p["id"]
    br = brect(p)
    cx = (br[0] + br[2]) * 0.5
    cy = (br[1] + br[3]) * 0.5
    half = (br[2] - br[0]) * 0.5
    mesh = ctx.shell.get(("bazaar",), 0,
                         lambda: make_mesh("SM_Landmark_CoveredBazaar", build_bazaar()))
    ob = new_obj("SM_Landmark_CoveredBazaar_001", mesh, (cx, cy, 0.0), ctx.meshes)
    ctx.add(ob, 1)
    bb = (cx - half, cy - half, cx + half, cy + half)
    check_rect(ctx, p, bb, ob.name)

    wf = BAZ["wf"]
    centers, _pier = _baz_openings(wf)
    # hanging lanterns under the arcade
    lm = ctx.prop.get("lantern", 0, lambda: make_mesh("lantern", p_lantern()))
    i = 0
    for (prot, xl, yl) in ((0, None, -(wf - 0.5)), (0, None, (wf - 0.5)),
                           (90, (wf - 0.5), None), (270, -(wf - 0.5), None)):
        for u in centers:
            if prot == 0:
                X, Y = u, yl
            elif prot == 90:
                X, Y = xl, u
            else:
                X, Y = xl, u
            a = math.radians(prot)
            c, s = math.cos(a), math.sin(a)
            wx, wy = cx + X * c - Y * s, cy + X * s + Y * c
            ob2 = new_obj("SM_Lantern_L%02d" % i, lm, (wx, wy, 4.35), ctx.lights)
            # provisional point light sitting inside the lantern body
            ctx.light_specs.append(dict(pos=(wx, wy, 3.57), kind="bazaar_lantern",
                                        color=(1.0, 0.70, 0.34), power=45.0,
                                        size=0.26))
            i += 1
            ctx.placed += 1
            ctx.props += 1
            ctx.tris += mesh_tris(lm)
    # one provisional light over the main (south) entrance arch
    ctx.light_specs.append(dict(pos=(cx, cy - (BAZ["mw"] - 1.0), 4.2),
                                kind="bazaar_arch", color=(1.0, 0.76, 0.44),
                                power=150.0, size=1.0))
    # banner signs on the upper storey
    for n, (prot, X, Y) in enumerate(((0, -14.0, -wf - 0.05), (0, 14.0, -wf - 0.05),
                                      (0, -14.0, wf + 0.05), (0, 14.0, wf + 0.05),
                                      (90, wf + 0.05, -14.0), (90, wf + 0.05, 14.0),
                                      (270, -wf - 0.05, -14.0), (270, -wf - 0.05, 14.0))):
        bm = ctx.prop.get("banner", prot, lambda: make_mesh("banner", p_banner()))
        a = math.radians(prot)
        c, s = math.cos(a), math.sin(a)
        ob3 = new_obj("SM_Banner_%02d" % n, bm,
                      (cx + X * c - Y * s, cy + X * s + Y * c, 9.4), ctx.meshes)
        ctx.placed += 1
        ctx.props += 1
        ctx.tris += mesh_tris(bm)
    # interior stalls
    sm = ctx.inter.get(("bstall",), 0, lambda: make_mesh("INT_FurnStall", p_bstall()))
    n = 0
    for row in (-16.0, -8.0, 8.0, 16.0):
        for col in (-20.0, -12.0, 12.0, 20.0):
            if abs(row) == 16.0 and abs(col) == 12.0:
                continue
            ob4 = new_obj("INT_%s_Stall%02d" % (pid, n), sm,
                          (cx + col, cy + row, CURB + 0.04), ctx.meshes)
            n += 1
            ctx.add(ob4, 1)
    place_collider(ctx, p, (-half, -half, half, half), 14.0, bb, 0)
    ctx.parcel_ids.add(pid)
    ctx.buildings += 1
    ctx.tier_count[1] += 1
    ctx.bazaar_tris = ctx.tris - t_start
    ctx.parcel_tris.append((1, ctx.bazaar_tris))


# ------------------------------------------------------------------ teardown
def purge_market():
    coll = bpy.data.collections.get("Market")
    if coll is None:
        return
    for ob in list(coll.all_objects):
        try:
            bpy.data.objects.remove(ob, do_unlink=True)
        except Exception as exc:
            print("  [market] purge object failed:", exc)

    def rm(c):
        for ch in list(c.children):
            rm(ch)
        try:
            bpy.data.collections.remove(c)
        except Exception as exc:
            print("  [market] purge collection failed:", exc)

    rm(coll)
    print("  [market] removed previous 'Market' collection")
    for ld in list(bpy.data.lights):
        if ld.name.startswith("LT_market_"):
            try:
                bpy.data.lights.remove(ld)
            except Exception as exc:
                print("  [market] could not remove light data:", exc)


def overlap_check(bboxes):
    """bboxes: ((x0,y0,x1,y1), parcel_id) - sweep along x, test y overlap."""
    viol = []
    items = sorted(bboxes, key=lambda b: b[0][0])
    for i, (a, ida) in enumerate(items):
        for j in range(i + 1, len(items)):
            b, idb = items[j]
            if b[0] >= a[2] - 1e-6:
                break
            if b[1] < a[3] - 1e-6 and a[1] < b[3] - 1e-6:
                viol.append((ida, idb))
    return viol


def module_bbox(bboxes):
    x0 = min(b[0][0] for b in bboxes)
    y0 = min(b[0][1] for b in bboxes)
    x1 = max(b[0][2] for b in bboxes)
    y1 = max(b[0][3] for b in bboxes)
    z1 = max((o.dimensions.z + o.location.z)
             for o in bpy.data.objects if o.type == "MESH" and not o.hide_render)
    return [round(v, 2) for v in (x0, y0, 0.0, x1, y1, z1)]


# ----------------------------------------------------------- clearance audit
def parcel_index(parcels, cell=32.0):
    """Spatial hash of every buildable_rect.

    find(x, y) -> (rect, exact): the parcel whose buildable_rect CONTAINS the
    point (rects are disjoint), falling back to the nearest parcel centre for
    the odd object whose origin sits just outside its own lot."""
    grid = {}
    items = []
    for p in parcels:
        r = brect(p)
        i = len(items)
        items.append((r, (0.5 * (r[0] + r[2]), 0.5 * (r[1] + r[3]))))
        for ix in range(int(math.floor(r[0] / cell)), int(math.floor(r[2] / cell)) + 1):
            for iy in range(int(math.floor(r[1] / cell)), int(math.floor(r[3] / cell)) + 1):
                grid.setdefault((ix, iy), []).append(i)

    def find(x, y, pad=1.0):
        cands = set()
        for ix in range(int(math.floor((x - pad) / cell)),
                        int(math.floor((x + pad) / cell)) + 1):
            for iy in range(int(math.floor((y - pad) / cell)),
                            int(math.floor((y + pad) / cell)) + 1):
                cands.update(grid.get((ix, iy), ()))
        best = None
        bestd = 1e18
        for i in cands:
            r, c = items[i]
            if r[0] - 1e-6 <= x <= r[2] + 1e-6 and r[1] - 1e-6 <= y <= r[3] + 1e-6:
                return r, True                   # rects are disjoint: this is it
        for i in cands:                          # fallback: nearest lot centre
            r, c = items[i]
            d = (x - c[0]) ** 2 + (y - c[1]) ** 2
            if d < bestd:
                bestd, best = d, i
        if best is None:
            return None, False
        return items[best][0], False

    return find


def centre_hits(bbox, road, tol=0.05):
    """True when the box covers (or nearly touches) a road CENTRELINE sample."""
    grid, cell, _ = road
    x0, y0, x1, y1 = bbox
    for ix in range(int(math.floor((x0 - tol) / cell)),
                    int(math.floor((x1 + tol) / cell)) + 1):
        for iy in range(int(math.floor((y0 - tol) / cell)),
                        int(math.floor((y1 + tol) / cell)) + 1):
            for (px, py, r) in grid.get((ix, iy), ()):
                dx = max(x0 - px, 0.0, px - x1)
                dy = max(y0 - py, 0.0, py - y1)
                if math.hypot(dx, dy) < tol:
                    return (round(px, 2), round(py, 2), round(r, 2))
    return None


def mesh_bounds(me, cache):
    """Local (AABB, ground footprint) of a mesh, computed once per datablock.

    The ground footprint is the plan AABB of every vertex below CLEAR - i.e.
    the part of the object that could ever touch the pavement or the road."""
    k = me.as_pointer()
    b = cache.get(k)
    if b is not None:
        return b
    lo = [1e18, 1e18, 1e18]
    hi = [-1e18, -1e18, -1e18]
    g = [1e18, 1e18, -1e18, -1e18]
    any_g = False
    for v in me.vertices:
        x, y, z = v.co[0], v.co[1], v.co[2]
        if x < lo[0]:
            lo[0] = x
        if y < lo[1]:
            lo[1] = y
        if z < lo[2]:
            lo[2] = z
        if x > hi[0]:
            hi[0] = x
        if y > hi[1]:
            hi[1] = y
        if z > hi[2]:
            hi[2] = z
        if z < CLEAR:
            any_g = True
            if x < g[0]:
                g[0] = x
            if y < g[1]:
                g[1] = y
            if x > g[2]:
                g[2] = x
            if y > g[3]:
                g[3] = y
    if not me.vertices:
        lo, hi, any_g = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], False
    b = ((lo[0], lo[1], lo[2], hi[0], hi[1], hi[2]),
         (g if any_g else None))
    cache[k] = b
    return b


def verify_clearance(ctx, parcels):
    """Geometry audit of every mesh object under Market/Meshes + Market/Lights.

    Rules (style_bible + module contract):
      1. every vertex below CLEAR (2.4 m) sits INSIDE its parcel's
         buildable_rect -> footprints and ground props never touch the
         pavement or the carriageway;
      2. geometry that DOES leave buildable_rect (awnings, blade signs,
         balconies, satellite dishes) is an overhang: it must hang at >= 2.4 m
         and must never reach a road centreline - overhanging the pavement is
         the whole point, crossing the centreline is not;
      3. awning: projection 1.2-1.5 m from the facade, lowest point >= 2.6 m;
      4. blade sign: projection 0.8-1.2 m, lowest point >= 2.4 m;
      5. balcony: projection <= 1.2 m from the facade.
    """
    t0 = time.time()
    find = parcel_index(parcels)
    cache = {}
    eps = 0.005
    st = dict(objects=0, grounded=0, inside=0, escaped=0, aabb_only=0,
              overhang=0, ground_out=0, ground_road=0, clearance=0,
              centreline=0, transform=0, noparcel=0, fallback=0,
              awning=0, blade=0, bldg=0,
              awn_z=1e9, awn_p0=1e9, awn_p1=-1e9,
              blade_z=1e9, blade_p0=1e9, blade_p1=-1e9,
              bal_p=-1e9, min_overhang_z=1e9)
    viol = []
    targets = list(ctx.meshes.objects) + list(ctx.lights.objects)
    for ob in targets:
        st["objects"] += 1
        if ob.type != "MESH":
            continue
        loc = ob.location
        if (ob.parent is not None or
                abs(ob.scale[0] - 1.0) > 1e-9 or abs(ob.scale[1] - 1.0) > 1e-9 or
                abs(ob.scale[2] - 1.0) > 1e-9 or
                abs(ob.rotation_euler[0]) > 1e-9 or abs(ob.rotation_euler[1]) > 1e-9 or
                abs(ob.rotation_euler[2]) > 1e-9):
            st["transform"] += 1
            viol.append(["transform", ob.name])
        br, exact = find(loc[0], loc[1])
        if br is None:
            st["noparcel"] += 1
            viol.append(["noparcel", ob.name, [round(v, 2) for v in loc]])
            continue
        if not exact:
            st["fallback"] += 1
        (x0, y0, z0, x1, y1, z1), g = mesh_bounds(ob.data, cache)
        # ---- 1) ground footprint (vertices < 2.4 m) inside buildable_rect
        if g is not None and z0 + loc[2] < CLEAR - eps:
            st["grounded"] += 1
            gx0, gy0 = g[0] + loc[0], g[1] + loc[1]
            gx1, gy1 = g[2] + loc[0], g[3] + loc[1]
            if (gx0 < br[0] - eps or gy0 < br[1] - eps or
                    gx1 > br[2] + eps or gy1 > br[3] + eps):
                st["ground_out"] += 1
                viol.append(["ground_out", ob.name,
                             [round(v, 3) for v in (gx0, gy0, gx1, gy1)],
                             [round(v, 3) for v in br]])
            elif road_hits((gx0, gy0, gx1, gy1), ctx.road):
                st["ground_road"] += 1
                viol.append(["ground_road", ob.name])
        # ---- 2) does the object leave buildable_rect at all?
        wx0, wy0, wz0 = x0 + loc[0], y0 + loc[1], z0 + loc[2]
        wx1, wy1, wz1 = x1 + loc[0], y1 + loc[1], z1 + loc[2]
        if (wx0 >= br[0] - eps and wy0 >= br[1] - eps and
                wx1 <= br[2] + eps and wy1 <= br[3] + eps):
            st["inside"] += 1
            continue
        st["escaped"] += 1
        # ---- audit the escaping part vertex by vertex
        ox0 = oy0 = oz0 = 1e18
        ox1 = oy1 = oz1 = -1e18
        found = False
        low = 0
        lowz = 1e18
        for v in ob.data.vertices:
            wx = v.co[0] + loc[0]
            wy = v.co[1] + loc[1]
            wz = v.co[2] + loc[2]
            if (br[0] - eps <= wx <= br[2] + eps and
                    br[1] - eps <= wy <= br[3] + eps):
                continue
            found = True
            if wx < ox0:
                ox0 = wx
            if wy < oy0:
                oy0 = wy
            if wz < oz0:
                oz0 = wz
            if wx > ox1:
                ox1 = wx
            if wy > oy1:
                oy1 = wy
            if wz > oz1:
                oz1 = wz
            if wz < CLEAR - eps:
                low += 1
                if wz < lowz:
                    lowz = wz
        if not found:
            st["aabb_only"] += 1            # bounding-box over-estimate only
            continue
        st["overhang"] += 1
        if low:
            st["clearance"] += low
            viol.append(["clearance", ob.name, round(lowz, 3), low])
        hit = centre_hits((ox0, oy0, ox1, oy1), ctx.road)
        if hit:
            st["centreline"] += 1
            viol.append(["centreline", ob.name, hit])
        st["min_overhang_z"] = min(st["min_overhang_z"], oz0)
        # ---- 3..5) per-kind projection contract
        excess = max(br[0] - ox0, br[1] - oy0, ox1 - br[2], oy1 - br[3])
        proj = excess + SET                    # facade sits SET inside the rect
        nm = ob.name
        if nm.startswith("SM_Awning_"):
            st["awning"] += 1
            st["awn_z"] = min(st["awn_z"], oz0)
            st["awn_p0"] = min(st["awn_p0"], proj)
            st["awn_p1"] = max(st["awn_p1"], proj)
            if proj < 1.2 - 1e-6 or proj > 1.5 + 1e-6:
                viol.append(["awning_projection", ob.name, round(proj, 3)])
            if oz0 < 2.6 - 1e-3:
                viol.append(["awning_clearance", ob.name, round(oz0, 3)])
        elif nm.startswith("SM_Sign_Blade_"):
            st["blade"] += 1
            st["blade_z"] = min(st["blade_z"], oz0)
            st["blade_p0"] = min(st["blade_p0"], proj)
            st["blade_p1"] = max(st["blade_p1"], proj)
            if proj < 0.8 - 1e-6 or proj > 1.2 + 1e-6:
                viol.append(["blade_projection", ob.name, round(proj, 3)])
            if oz0 < 2.4 - 1e-3:
                viol.append(["blade_clearance", ob.name, round(oz0, 3)])
        elif nm.startswith("SM_Bldg_"):
            st["bldg"] += 1
            st["bal_p"] = max(st["bal_p"], proj)
            if proj > 1.2 + 1e-6:
                viol.append(["balcony_projection", ob.name, round(proj, 3)])
    st["min_overhang_z"] = 0.0 if st["min_overhang_z"] > 1e8 else st["min_overhang_z"]
    for k in ("awn_p0", "awn_p1", "blade_p0", "blade_p1"):
        if st[k] > 1e8 or st[k] < -1e8:
            st[k] = 0.0
    st["bal_p"] = max(0.0, st["bal_p"])
    st["violations"] = len(viol)
    st["seconds"] = round(time.time() - t0, 2)
    ctx.violations.extend(viol)
    return st


def print_clearance(st):
    print("[market] CLEARANCE objects=%d ground(<2.4m)=%d fully_inside=%d "
          "escaped_aabb=%d real_overhangs=%d"
          % (st["objects"], st["grounded"], st["inside"], st["escaped"],
             st["overhang"]))
    print("[market] CLEARANCE awnings=%d proj=%.2f-%.2f m (need 1.20-1.50) "
          "lowest=%.2f m (need >=2.60)"
          % (st["awning"], st["awn_p0"], st["awn_p1"], st["awn_z"]))
    print("[market] CLEARANCE blade_signs=%d proj=%.2f-%.2f m (need 0.80-1.20) "
          "lowest=%.2f m (need >=2.40)"
          % (st["blade"], st["blade_p0"], st["blade_p1"], st["blade_z"]))
    print("[market] CLEARANCE balconies=%d max_proj=%.2f m (need <=1.20) | "
          "min overhang z=%.2f m (need >=2.40)"
          % (st["bldg"], st["bal_p"], st["min_overhang_z"]))
    print("[market] CLEARANCE violations: outside_rect=%d road_corridor=%d "
          "under_clearance=%d centreline=%d transform=%d noparcel=%d "
          "(fallback=%d, %.2fs)"
          % (st["ground_out"], st["ground_road"], st["clearance"],
             st["centreline"], st["transform"], st["noparcel"],
             st["fallback"], st["seconds"]))


def _kind_counts(specs):
    out = {}
    for sp in specs:
        out[sp["kind"]] = out.get(sp["kind"], 0) + 1
    return out


def build_provisional_lights(ctx):
    """Create the LT_market_* point lights (see the Lighting module brief).

    Built AFTER the previews so the daytime renders stay fast; every light is
    a shadow-less placeholder flagged with a `provisional` custom property."""
    specs = ctx.light_specs
    assert len(specs) <= LIGHT_CAP, "provisional light cap exceeded: %d > %d" % (
        len(specs), LIGHT_CAP)
    for ld in list(bpy.data.lights):
        if ld.name.startswith("LT_market_"):
            bpy.data.lights.remove(ld)
    coll = ctx.lights
    for i, sp in enumerate(specs, 1):
        nm = "LT_market_%03d" % i
        ld = bpy.data.lights.new(nm, type="POINT")
        ld.energy = float(sp["power"])
        ld.color = tuple(sp["color"])
        ld.shadow_soft_size = float(sp["size"])
        try:
            ld.use_shadow = False
        except Exception:
            pass
        ob = bpy.data.objects.new(nm, ld)
        ob.location = tuple(sp["pos"])
        ob["provisional"] = True
        ob["kind"] = sp["kind"]
        ob["module"] = "market"
        coll.objects.link(ob)
    by_kind = {}
    for sp in specs:
        by_kind[sp["kind"]] = by_kind.get(sp["kind"], 0) + 1
    print("[market] LIGHTS provisional=%d/%d %s (no shadow, provisional=True)"
          % (len(specs), LIGHT_CAP, by_kind))
    return len(specs)


_OLD_SKY = [None]


def temp_ground(on):
    """A preview-only ground slab so the streets do not read as white voids.

    It lives in the scene collection (never in Market) and is deleted right
    after the renders, so the saved .blend still contains no road/ground
    geometry - that belongs to the Roads module.
    """
    if on:
        if bpy.data.objects.get("TMP_GROUND") is not None:
            return
        bd = Builder()
        bd.box(288.0, 588.0, -0.4, 1212.0, 1212.0, 0.0, "asphalt")
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


def sky(on):
    """Temporarily brighten the world background for the preview renders
    (restored afterwards so the saved .blend keeps the stock world)."""
    w = bpy.context.scene.world
    if w is None or not getattr(w, "use_nodes", False) or w.node_tree is None:
        return
    bg = next((n for n in w.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg is None:
        return
    if on:
        _OLD_SKY[0] = (tuple(bg.inputs[0].default_value),
                       float(bg.inputs[1].default_value))
        bg.inputs[0].default_value = (0.45, 0.55, 0.72, 1.0)
        bg.inputs[1].default_value = 0.7
    elif _OLD_SKY[0] is not None:
        bg.inputs[0].default_value = _OLD_SKY[0][0]
        bg.inputs[1].default_value = _OLD_SKY[0][1]


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


def main():
    import random
    t0 = time.time()
    layout = ck.read_layout()
    parcels = ck.read_parcels("M")
    purge_market()
    # drop the stock startup objects - this blend must only contain the module
    for nm in ("Cube", "Camera", "Light"):
        ob = bpy.data.objects.get(nm)
        if ob is not None:
            bpy.data.objects.remove(ob, do_unlink=True)
    # ...and the stock (empty) startup collection
    for c in list(bpy.data.collections):
        if c.name == "Market" or len(c.objects) or len(c.children):
            continue
        try:
            bpy.data.collections.remove(c)
            print("  [market] removed empty startup collection")
        except Exception as exc:
            print("  [market] could not remove collection:", exc)
    ctx = Ctx(layout, parcels)
    print("[market] %d parcels, %d road corridor samples"
          % (len(parcels), sum(len(v) for v in ctx.road[0].values())))

    by_cell = {}
    for p in parcels:
        by_cell.setdefault(tuple(p["cell"]), []).append(p)

    for cell in CELLS:
        sub = by_cell.get(tuple(cell), [])
        sub = sorted(sub, key=lambda q: 0 if q["type"] == "covered_bazaar_hall" else 1)
        for p in sub:
            rng = random.Random(dhash(p["id"]))
            typ = p["type"]
            if typ == "covered_bazaar_hall":
                place_bazaar(ctx, p)
            elif typ == "courtyard":
                place_courtyard(ctx, p, rng)
            else:
                place_regular(ctx, p, rng)
        ck.save_blend(os.path.join(ck.OUT_DIR, "market.blend"))
        print("[market] cell %s: %d/%d parcels | %d objects | %d tris | %.0fs"
              % (cell, ctx.buildings, len(parcels), ctx.placed, ctx.tris,
                 time.time() - t0))

    # ------------------------------------------------------------ verify
    missing = [p["id"] for p in parcels if p["id"] not in ctx.parcel_ids]
    overlaps = overlap_check(ctx.bboxes)
    clr = verify_clearance(ctx, parcels)
    n_obj = len(bpy.data.objects)
    uniq_tris = ck.scene_tri_count()
    n_meshes = len([m for m in bpy.data.meshes if m.users > 0])
    n_build_viol = len([v for v in ctx.violations if v[0] == "buildable"])
    n_road_viol = len([v for v in ctx.violations if v[0] == "road"])
    t3 = [t for (tier, t) in ctx.parcel_tris if tier == 3]
    t2 = [t for (tier, t) in ctx.parcel_tris if tier == 2]
    t0t = [t for (tier, t) in ctx.parcel_tris if tier == 0]
    max_t3 = max(t3) if t3 else 0
    max_t2 = max(t2) if t2 else 0
    max_t0 = max(t0t) if t0t else 0
    prev1 = os.path.join(ck.OUT_DIR, "market_preview.png")
    prev2 = os.path.join(ck.OUT_DIR, "market_street_preview.png")

    print("[market] VERIFY objects=%d instanced_tris=%d unique_tris=%d "
          "buildable_viol=%d road_viol=%d overlaps=%d missing=%d (%d/%d parcels)"
          % (n_obj, ctx.tris, uniq_tris, n_build_viol, n_road_viol,
             len(overlaps), len(missing), len(parcels) - len(missing),
             len(parcels)))
    print_clearance(clr)
    print("[market] STAIRS external=%d (hatch/roof-access=%d, first-floor-door=%d) "
          "rear_free=%.2f m >= %.2f m required"
          % (ctx.stairs, ctx.stair_hatch, ctx.stairs - ctx.stair_hatch,
             HALF - REAR, MIN_REAR_FREE))
    print("[market] BUDGET meshes=%d max_t3=%d (<=8000) max_t2=%d (<=40000) "
          "bazaar=%d (<=150000) module=%d (<=15000000)"
          % (n_meshes, max_t3, max_t2, ctx.bazaar_tris, uniq_tris))
    for v in ctx.violations[:10]:
        print("   VIOLATION", v)
    for o in overlaps[:10]:
        print("   OVERLAP", o)

    # ----------------------------------------------------------- previews
    eng = pick_engine()
    print("[market] preview engine:", eng)
    sky(True)
    temp_ground(True)
    try:
        try:
            ck.make_preview(prev1, (842.0, 588.0, 56.0), (714.88, 714.88, 11.0),
                            engine=eng, res=(1920, 1080),
                            sun_elev=38.0, sun_azim=-55.0, sun_energy=4.0, samples=32)
        except Exception as exc:
            print("[market] preview 1 failed:", exc)
            prev1 = None
        try:
            ck.make_preview(prev2, (750.0, 628.0, 1.7), (750.0, 742.0, 5.0),
                            engine=eng, res=(1920, 1080),
                            sun_elev=30.0, sun_azim=-40.0, sun_energy=3.5, samples=32)
        except Exception as exc:
            print("[market] preview 2 failed:", exc)
            prev2 = None
    finally:
        sky(False)
        temp_ground(False)

    left = [o.name for o in bpy.data.objects if o.name.startswith("TMP_")]
    if left:
        print("[market] WARNING temp preview objects still in scene:", left)

    # ------------------------------------------- provisional lights (post-render)
    n_lights = build_provisional_lights(ctx)
    n_obj = len(bpy.data.objects)          # now includes the LT_market_* points

    ck.save_blend(os.path.join(ck.OUT_DIR, "market.blend"))

    # ------------------------------------------------------------- report
    bbox = module_bbox(ctx.bboxes)
    # Blender 5.x dropped Collection.parent - derive the tree from users_collection
    tops = sorted(c.name for c in bpy.data.collections if not c.users_collection)
    subs = sorted(c.name for c in bpy.data.collections if c.users_collection)
    stock = sorted(o.name for o in bpy.data.objects
                   if o.name in ("Cube", "Camera", "Light"))
    print("[market] COLLECTIONS top=%s sub=%s | stock objects: %s"
          % (tops, subs, stock or "none"))
    issues = []
    if tops != ["Market"] or subs != ["Colliders", "Lights", "Meshes"]:
        issues.append("unexpected collection tree: top=%s sub=%s (want Market/"
                      "Meshes+Colliders+Lights)" % (tops, subs))
    if stock:
        issues.append("stock startup objects left in the blend: %s" % ", ".join(stock))
    if ctx.violations:
        issues.append("%d geometry violations (buildable/road corridor/clearance)"
                      % len(ctx.violations))
    if overlaps:
        issues.append("%d parcel bbox overlaps" % len(overlaps))
    if missing:
        issues.append("%d parcels without a building" % len(missing))
    if max_t3 > 8000:
        issues.append("t3 tri budget exceeded on %d buildings (max %d > 8000)"
                      % (len([t for t in t3 if t > 8000]), max_t3))
    if ctx.bazaar_tris > 150000:
        issues.append("bazaar tri budget exceeded (%d > 150000)" % ctx.bazaar_tris)
    if uniq_tris > 15000000:
        issues.append("module tri budget exceeded (%d > 15000000)" % uniq_tris)
    if prev1 is None or prev2 is None:
        issues.append("one or both previews failed to render")
    issues.append(
        "overhangs are not limited to the 0.5 m setback: awnings project "
        "%.2f-%.2f m, blade signs %.2f-%.2f m and balconies %.2f m from the "
        "facade, so they cover the pavement - clearance audit: lowest overhang "
        "%.2f m >= 2.40 m, %d road-centreline crossings"
        % (clr["awn_p0"], clr["awn_p1"], clr["blade_p0"], clr["blade_p1"],
           clr["bal_p"], clr["min_overhang_z"], clr["centreline"]))
    issues.append(
        "external stair on all %d buildings (rear free depth %.2f m >= %.2f m "
        "required): %d single-storey shells reach the roof through a parapet "
        "access hatch, %d multi-storey shells use the first-floor rear door"
        % (ctx.stairs, HALF - REAR, MIN_REAR_FREE, ctx.stair_hatch,
           ctx.stairs - ctx.stair_hatch))
    issues.append(
        "%d provisional point lights (LT_market_*, shadow-less, "
        "provisional=True) stand in for the Lighting module"
        % n_lights)
    issues.append("previews rendered with a temporary ground slab (deleted before "
                  "saving) - roads/ground belong to the Roads module")
    issues.append("object transforms = translation only (rotation baked into the shared "
                  "mesh variant, scale 1) - required for linked instancing")

    payload = {
        "parcels": len(parcels),
        "buildings": ctx.buildings,
        "objects": n_obj,
        "objects_geometry": n_obj - n_lights,
        "prop_objects": ctx.props,
        "collider_objects": ctx.colliders_n,
        "unique_meshes": n_meshes,
        "tris_instanced": ctx.tris,
        "tris_unique_meshes": uniq_tris,
        "collider_tris": ctx.collider_tris,
        "tier_counts": ctx.tier_count,
        "tier_tris": ctx.tier_tris,
        "budget_max_tris": {"t3": max_t3, "t2": max_t2, "t0": max_t0,
                            "bazaar": ctx.bazaar_tris},
        "engine": eng,
        "materials": sorted(ctx.mat_used),
        "violations": ctx.violations[:40],
        "overlaps": overlaps[:40],
        "missing_parcels": missing,
        "bbox": bbox,
        "collections": ["Market", "Market/Meshes", "Market/Colliders", "Market/Lights"],
        "previews": [p for p in (prev1, prev2) if p],
        "clearance": clr,
        "stairs": {"count": ctx.stairs, "roof_access_hatches": ctx.stair_hatch,
                   "first_floor_doors": ctx.stairs - ctx.stair_hatch,
                   "rear_free_depth": round(HALF - REAR, 3),
                   "required_free_depth": MIN_REAR_FREE,
                   "run": 4.20, "width": STAIR_W, "risers": 16},
        "lights": {"provisional": n_lights, "cap": LIGHT_CAP,
                   "by_kind": _kind_counts(ctx.light_specs),
                   "collections": "Market/Lights", "shadow": False},
        "assembler_contract": [
            "units = metres, Z-up, transforms applied (scale 1, rotation baked "
            "into the shared mesh variant, origin bottom-centre)",
            "single top-level collection 'Market' with 'Meshes', 'Colliders' "
            "and 'Lights'",
            "materials only via citykit.append_material (%d used)" % len(ctx.mat_used),
            "naming SM_/COL_/INT_/LT_ , instancing only - no unique copies "
            "(%d mesh datablocks serve %d objects)" % (n_meshes, n_obj),
            "footprints inside buildable_rect, ground props off pavement and "
            "road, overhangs >= 2.4 m clear and short of every centreline",
        ],
        "issues": issues,
        "build_seconds": round(time.time() - t0, 1),
    }
    ck.write_report("market", payload)
    write_md(payload)

    print("[market] DONE in %.0fs  buildings=%d objects=%d lights=%d "
          "tris(instanced)=%d"
          % (time.time() - t0, ctx.buildings, n_obj, n_lights, ctx.tris))
    print("[market] bbox", bbox)


def write_md(d):
    c = d.get("clearance", {})
    s = d.get("stairs", {})
    lt = d.get("lights", {})
    lines = []
    lines.append("# Market module report (Phase C-pilot)\n")
    lines.append("Generated by `modules/market.py` (headless, EEVEE previews).\n")
    lines.append("## Counts\n")
    lines.append("| item | value |")
    lines.append("|---|---|")
    for k in ("parcels", "buildings", "objects", "objects_geometry", "prop_objects",
              "collider_objects", "unique_meshes", "tris_instanced",
              "tris_unique_meshes", "collider_tris", "build_seconds"):
        lines.append("| %s | %s |" % (k, d.get(k)))
    lines.append("| provisional lights | %s |" % lt.get("provisional"))
    lines.append("| external stairs | %s |" % s.get("count"))
    lines.append("\n## Per tier\n")
    lines.append("| tier | parcels | tris (building + interior) |")
    lines.append("|---|---|---|")
    for t in (0, 1, 2, 3):
        lines.append("| t%s | %s | %s |" % (t, d["tier_counts"].get(t),
                                            d["tier_tris"].get(t)))
    b = d.get("budget_max_tris", {})
    lines.append("\n## Budgets\n")
    lines.append("| item | tris | limit |")
    lines.append("|---|---|---|")
    lines.append("| heaviest t3 building | %s | 8000 |" % b.get("t3"))
    lines.append("| heaviest t2 building | %s | 40000 |" % b.get("t2"))
    lines.append("| LM_BAZAAR hero | %s | 150000 |" % b.get("bazaar"))
    lines.append("| whole module (unique meshes) | %s | 15000000 |"
                 % d.get("tris_unique_meshes"))
    lines.append("| render engine | %s | EEVEE |" % d.get("engine"))
    lines.append("\n## Materials used (%d)\n" % len(d["materials"]))
    lines.append(", ".join("`%s`" % m for m in d["materials"]))
    lines.append("\n## Collections / bounding box\n")
    lines.append("- collections: %s" % ", ".join(d["collections"]))
    lines.append("- module bbox (x0,y0,z0,x1,y1,z1): %s" % d["bbox"])
    lines.append("- previews: %s" % ", ".join(d["previews"]))
    lines.append("\n## Verification\n")
    lines.append("- buildable_rect violations: %d"
                 % len([v for v in d["violations"] if v[0] == "buildable"]))
    lines.append("- road corridor violations: %d"
                 % len([v for v in d["violations"] if v[0] == "road"]))
    lines.append("- parcel bbox overlaps: %d" % len(d["overlaps"]))
    lines.append("- parcels without a building: %d (of %d)"
                 % (len(d["missing_parcels"]), d["parcels"]))
    lines.append("- clearance violations: %d" % c.get("violations", 0))
    lines.append("\n## Clearance audit (%s s)\n" % c.get("seconds"))
    lines.append("| check | measured | required |")
    lines.append("|---|---|---|")
    lines.append("| awning projection | %.2f-%.2f m (%d awnings) | 1.20-1.50 m |"
                 % (c.get("awn_p0", 0), c.get("awn_p1", 0), c.get("awning", 0)))
    lines.append("| awning lowest point | %.2f m | >= 2.60 m |"
                 % c.get("awn_z", 0))
    lines.append("| blade-sign projection | %.2f-%.2f m (%d signs) | 0.80-1.20 m |"
                 % (c.get("blade_p0", 0), c.get("blade_p1", 0), c.get("blade", 0)))
    lines.append("| blade-sign lowest point | %.2f m | >= 2.40 m |"
                 % c.get("blade_z", 0))
    lines.append("| balcony projection | %.2f m (%d buildings) | <= 1.20 m |"
                 % (c.get("bal_p", 0), c.get("bldg", 0)))
    lines.append("| lowest overhang (any) | %.2f m | >= 2.40 m |"
                 % c.get("min_overhang_z", 0))
    lines.append("| ground geometry outside buildable_rect | %d | 0 |"
                 % c.get("ground_out", 0))
    lines.append("| ground geometry on a road corridor | %d | 0 |"
                 % c.get("ground_road", 0))
    lines.append("| geometry crossing a road centreline | %d | 0 |"
                 % c.get("centreline", 0))
    lines.append("| objects audited / with ground geometry / leaving the rect | "
                 "%d / %d / %d | all |"
                 % (c.get("objects", 0), c.get("grounded", 0), c.get("overhang", 0)))
    lines.append("\n## External stairs\n")
    lines.append("- placed: %s of %s buildings with rear free depth >= %.2f m"
                 % (s.get("count"), d.get("buildings"), s.get("required_free_depth", 0)))
    lines.append("- rear free depth available: %.2f m, stair run %.2f m, width %.2f m, "
                 "%s risers of 0.2 m" % (s.get("rear_free_depth", 0), s.get("run", 0),
                                          s.get("width", 0), s.get("risers", 0)))
    lines.append("- single-storey shells reach the roof through a parapet access "
                 "hatch: %s" % s.get("roof_access_hatches"))
    lines.append("- multi-storey shells use the 2.4 m first-floor rear door: %s"
                 % s.get("first_floor_doors"))
    lines.append("\n## Provisional lights\n")
    lines.append("- %s / %s point lights in `%s` (shadow-less), by kind: %s"
                 % (lt.get("provisional"), lt.get("cap"), lt.get("collections"),
                    ", ".join("%s=%s" % kv for kv in
                              sorted((lt.get("by_kind") or {}).items()))))
    lines.append("- every light object carries `provisional = true` and "
                 "`module = market`")
    lines.append("\n## Assembler contract\n")
    for a in d.get("assembler_contract", []):
        lines.append("- %s" % a)
    lines.append("\n## Known issues / notes\n")
    for i in d["issues"]:
        lines.append("- %s" % i)
    path = os.path.join(ck.REPORTS_DIR, "market_report.md")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("  [market] markdown report -> %s" % path)


if __name__ == "__main__":
    main()
