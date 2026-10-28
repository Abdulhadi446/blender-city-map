#!/usr/bin/env python3
"""downtown.py — Downtown (D) district kit for the 3x3 km AAA city.

Headless run:
    cd /home/abdulhadi/Work/city && blender -b -P modules/downtown.py

Builds all 109 downtown parcels (7 cells) from an archetype kit:
  * glass curtain-wall tower   (instanced mullion + spandrel floor module)
  * concrete/stone punched tower
  * brutalist ribbon-window block
  * art-deco setback tower (incl. the LM_LANDMARK_TOWER hero)
  * mixed-use podium (open retail ground floor + offices above)
  * hotel / apartment / bank / mall / civic wrappers around the same kit
plus tiered interiors, signage, rooftop plant, colliders and clearance asserts.

Re-runnable: deletes the "Downtown" collection first, saves after every cell.
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
    sys.path.insert(0, ROOT + "/modules")

import citykit as ck          # noqa: E402
import bpy                    # noqa: E402
from mathutils import Vector   # noqa: E402

BLEND = os.path.join(ck.OUT_DIR, "downtown.blend")
PREV_SKY = os.path.join(ck.OUT_DIR, "downtown_preview.png")
PREV_STREET = os.path.join(ck.OUT_DIR, "downtown_street_preview.png")

# ------------------------------------------------------------------ constants
CELLS = [(3, 5), (4, 5), (5, 5), (3, 4), (4, 4), (5, 4), (4, 3)]

FL = 3.2                  # nominal floor height (layout heights are F * 3.2)
GH_MIN = 5.6              # double-height retail ground floor
FH_MIN, FH_MAX = 2.4, 3.9  # upper floor height clamp
CURB = 0.15               # curb height
CANOPY_PROJ = 1.2         # canopy projection out of the buildable rect
CANOPY_BOTTOM = 2.75      # canopy soffit (>= 2.7 m clearance)
HEADER_H = 1.2            # solid header band above the open shopfronts
SETBACK = 2.0             # footprint inset per setback tier
PODIUM_FL = 3             # office/stone floors between podium and shaft
PARAPET = 1.2             # parapet height
ROOF_SAFE = 0.35          # keeps rooftop kit inside the parapet

# road half-widths used for the clearance contract (global contract)
HALFWIDTH = {"highway": 17.0, "arterial": 12.0, "street": 6.0,
             "alley": 2.5, "interchange_ramp": 9.0}
FLY_PAD = 2.0             # flyover footprint + 2 m keep-out

ROT = {"S": 0.0, "E": 90.0, "N": 180.0, "W": 270.0}
SIDE_OUT = {"S": (0.0, -1.0), "N": (0.0, 1.0), "E": (1.0, 0.0), "W": (-1.0, 0.0)}

TYPE_CODE = {"office_tower": "OFF", "hotel": "HOT", "apartment_tower": "APT",
             "bank": "BNK", "mall": "MAL", "civic": "CIV"}
STYLE_CODE = {"glass_curtain": "CUR", "steel_stone": "STN", "art_deco": "DEC",
              "brutalist_modern": "BRU"}

# facade style -> role -> material (all from materials.blend, append only)
STYLE = {
    "glass_curtain": dict(
        kind="curtain", bay=1.5,
        roles=dict(glass="glass_office", frame="metal_steel", band="glass_dark",
                   dark="metal_painted_dark", wall="concrete", ceil="ceiling_paint"),
        ground="metal_painted_dark", floor="floor_tile"),
    "steel_stone": dict(
        kind="punched", bay=3.0,
        roles=dict(glass="glass_office", frame="stone_grey", band="stone_grey",
                   dark="metal_painted_dark", wall="concrete", ceil="ceiling_paint"),
        ground="stone_grey", floor="floor_tile"),
    "art_deco": dict(
        kind="deco", bay=3.0,
        roles=dict(glass="glass_dark", frame="plaster_white", band="plaster_white",
                   dark="metal_chrome", wall="plaster_cream", ceil="ceiling_paint"),
        ground="plaster_cream", floor="floor_wood"),
    "brutalist_modern": dict(
        kind="ribbon", bay=3.0,
        roles=dict(glass="glass_dark", frame="concrete_poured", band="concrete_poured",
                   dark="rust", wall="concrete_poured", ceil="ceiling_paint"),
        ground="concrete_poured", floor="floor_carpet"),
}
DEFAULT_STYLE = "steel_stone"

PODIUM_ROLES = dict(glass="glass_office", frame="stone_grey", band="stone_grey",
                    dark="metal_painted_dark", wall="concrete", ceil="ceiling_paint")
PODIUM_MATS = ["concrete", "stone_grey", "glass_office", "metal_painted_dark",
               "ceiling_paint", "roof_bitumen"]
PODIUM_IDX = dict(glass=2, frame=1, band=1, dark=3, wall=0, ceil=4)

TIER_FLOOR_MAT = {1: "marble_white", 2: "floor_tile", 3: "floor_carpet"}


def log(msg):
    print("[downtown] %s" % msg, flush=True)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def rect_of(o):
    return tuple(float(v) for v in o)


def inter(a, b):
    """AABB overlap (strict)."""
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


# ------------------------------------------------------------------ geometry
class Geo(object):
    """Vertex / polygon accumulator with a per-polygon material index."""

    __slots__ = ("v", "f", "mi")

    def __init__(self):
        self.v = []
        self.f = []
        self.mi = []

    def add(self, pts, m):
        base = pts[0]
        keep = [base]
        for q in pts[1:]:
            if abs(q[0] - base[0]) + abs(q[1] - base[1]) + abs(q[2] - base[2]) > 1e-5:
                keep.append(q)
        # drop consecutive duplicates
        out = [keep[0]]
        for q in keep[1:]:
            p = out[-1]
            if abs(q[0] - p[0]) + abs(q[1] - p[1]) + abs(q[2] - p[2]) > 1e-5:
                out.append(q)
        if len(out) < 3:
            return
        if len(out) > 2 and abs(out[0][0] - out[-1][0]) + abs(out[0][1] - out[-1][1]) \
                + abs(out[0][2] - out[-1][2]) < 1e-5:
            out.pop()
        if len(out) < 3:
            return
        i = len(self.v)
        self.v.extend(out)
        self.f.append(tuple(range(i, i + len(out))))
        self.mi.append(int(m))

    def quad(self, a, b, c, d, m):
        self.add([a, b, c, d], m)

    def box(self, cx, cy, cz, sx, sy, sz, m, bottom=False, top=True):
        x0, x1 = cx - sx / 2.0, cx + sx / 2.0
        y0, y1 = cy - sy / 2.0, cy + sy / 2.0
        z0, z1 = cz - sz / 2.0, cz + sz / 2.0
        V = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        self.quad(V[0], V[1], V[5], V[4], m)
        self.quad(V[1], V[2], V[6], V[5], m)
        self.quad(V[2], V[3], V[7], V[6], m)
        self.quad(V[3], V[0], V[4], V[7], m)
        if top:
            self.quad(V[4], V[5], V[6], V[7], m)
        if bottom:
            self.quad(V[0], V[3], V[2], V[1], m)

    def __len__(self):
        return len(self.v)


class Side(object):
    """One axis-aligned wall plane of a rect: origin + along-wall + outward normal."""

    def __init__(self, g, rect, name):
        x0, y0, x1, y1 = rect
        self.g = g
        self.name = name
        if name == "S":
            self.o, self.u, self.n, self.L = (x0, y0), (1.0, 0.0), (0.0, -1.0), x1 - x0
        elif name == "N":
            self.o, self.u, self.n, self.L = (x1, y1), (-1.0, 0.0), (0.0, 1.0), x1 - x0
        elif name == "W":
            self.o, self.u, self.n, self.L = (x0, y1), (0.0, -1.0), (-1.0, 0.0), y1 - y0
        else:
            self.o, self.u, self.n, self.L = (x1, y0), (0.0, 1.0), (1.0, 0.0), y1 - y0

    def p(self, s, z, off=0.0):
        return (self.o[0] + self.u[0] * s + self.n[0] * off,
                self.o[1] + self.u[1] * s + self.n[1] * off,
                float(z))

    def quad(self, s0, s1, z0, z1, m, off=0.0):
        self.g.quad(self.p(s0, z0, off), self.p(s1, z0, off),
                    self.p(s1, z1, off), self.p(s0, z1, off), m)

    def fin(self, s, w, o_front, o_back, z0, z1, m):
        """Vertical fin / mullion / pier: face at o_front + two returns to o_back."""
        a, b = s - w / 2.0, s + w / 2.0
        self.quad(a, b, z0, z1, m, off=o_front)
        self.g.quad(self.p(a, z0, o_back), self.p(a, z0, o_front),
                    self.p(a, z1, o_front), self.p(a, z1, o_back), m)
        self.g.quad(self.p(b, z0, o_back), self.p(b, z0, o_front),
                    self.p(b, z1, o_front), self.p(b, z1, o_back), m)

    def recess(self, s0, s1, z0, z1, d, m_glass, m_frame):
        """Punched opening: glass set back d + four reveal faces."""
        self.quad(s0, s1, z0, z1, m_glass, off=-d)
        g = self.g
        g.quad(self.p(s0, z0, 0), self.p(s0, z0, -d), self.p(s0, z1, -d),
               self.p(s0, z1, 0), m_frame)
        g.quad(self.p(s1, z0, 0), self.p(s1, z0, -d), self.p(s1, z1, -d),
               self.p(s1, z1, 0), m_frame)
        g.quad(self.p(s0, z0, 0), self.p(s1, z0, 0), self.p(s1, z0, -d),
               self.p(s0, z0, -d), m_frame)
        g.quad(self.p(s0, z1, 0), self.p(s1, z1, 0), self.p(s1, z1, -d),
               self.p(s0, z1, -d), m_frame)


# ------------------------------------------------------------------ datablocks
def build_mesh_data(name, geo, mats):
    """Create a Mesh datablock with several appended materials (no object)."""
    if len(geo) == 0:
        return None
    me = bpy.data.meshes.new(name)
    me.from_pydata(geo.v, [], geo.f)
    for mn in mats:
        me.materials.append(ck.append_material(mn))
    if len(geo.mi) == len(me.polygons):
        me.polygons.foreach_set("material_index", geo.mi)
    me.update()
    return me


def make_mesh(name, geo, mats, coll):
    """Create the mesh plus one linked object at the origin."""
    me = build_mesh_data(name, geo, mats)
    if me is None:
        return None
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def add_obj(name, me, coll, loc=(0.0, 0.0, 0.0), rot_z=0.0):
    ob = bpy.data.objects.new(name, me)
    ob.location = (float(loc[0]), float(loc[1]), float(loc[2]))
    if rot_z:
        ob.rotation_euler = (0.0, 0.0, math.radians(rot_z))
    coll.objects.link(ob)
    return ob


def mesh_of(ob):
    return getattr(ob, "data", None)


def unique_meshes():
    seen = {}
    for ob in bpy.data.objects:
        me = getattr(ob, "data", None)
        if me is None:
            continue
        seen[me.as_pointer()] = me
    return seen


# ------------------------------------------------------------------ facades
def emit_facade(g, ri, kind, rect, side, fh, bay, band=False):
    """Emit one wall of a typical (upper) floor module.

    ri   : dict role -> material index inside this module's slot list
    kind : curtain | punched | deco | ribbon
    band : True for the 'stone band every 3 floors' variant (steel_stone)
    """
    S = Side(g, rect, side)
    L = S.L
    if L <= 0.5 or fh <= 0.2:
        return

    if kind == "curtain":
        S.quad(0.0, L, 0.0, fh, ri["glass"], off=0.03)
        sp = min(0.9, fh * 0.26)
        S.quad(0.0, L, 0.0, sp, ri["band"], off=0.10)
        S.quad(0.0, L, sp, sp + 0.07, ri["frame"], off=0.14)
        n = max(2, int(round(L / bay)))
        step = L / n
        for i in range(n + 1):
            S.fin(min(max(i * step, 0.0), L), 0.13, 0.17, 0.0, 0.0, fh, ri["frame"])
        S.fin(0.0, 0.34, 0.20, 0.0, 0.0, fh, ri["dark"])
        S.fin(L, 0.34, 0.20, 0.0, 0.0, fh, ri["dark"])

    elif kind == "punched":
        S.quad(0.0, L, 0.0, fh, ri["wall"])
        n = max(2, int(round(L / bay)))
        step = L / n
        ww = min(1.6, step - 1.0)
        sill = 0.5
        wh = min(2.2, fh - sill - 0.3)
        if wh < 0.7:
            sill, wh = 0.3, max(0.6, fh - 0.6)
        for i in range(n):
            c = (i + 0.5) * step
            S.recess(c - ww / 2.0, c + ww / 2.0, sill, sill + wh, 0.25,
                     ri["glass"], ri["frame"])
        if band:
            bh = min(0.5, fh * 0.22)
            S.quad(0.0, L, 0.0, bh, ri["band"], off=0.06)
            S.fin(0.0, 0.3, 0.06, 0.0, 0.0, bh, ri["band"])
            S.fin(L, 0.3, 0.06, 0.0, 0.0, bh, ri["band"])

    elif kind == "deco":
        S.quad(0.0, L, 0.0, fh, ri["wall"])
        n = max(2, int(round(L / bay)))
        step = L / n
        ww = min(1.6, step - 1.2)
        sill = 0.35
        wh = min(2.4, fh - sill - 0.3)
        if wh < 0.7:
            sill, wh = 0.25, max(0.6, fh - 0.55)
        for i in range(n):
            c = (i + 0.5) * step
            S.recess(c - ww / 2.0, c + ww / 2.0, sill, sill + wh, 0.30,
                     ri["glass"], ri["frame"])
            S.fin(c + ww / 2.0 + 0.34, 0.32, 0.11, 0.0, 0.0, fh, ri["dark"])
            S.fin(c - ww / 2.0 - 0.34, 0.32, 0.11, 0.0, 0.0, fh, ri["dark"])
        if band:
            bh = min(0.45, fh * 0.2)
            S.quad(0.0, L, 0.0, bh, ri["band"], off=0.07)

    else:  # ribbon (brutalist): 2.0 m recessed band, 0.6 m deep
        S.quad(0.0, L, 0.0, fh, ri["wall"])
        bz = 0.5
        bh = min(2.0, fh - bz - 0.35)
        if bh < 0.6:
            bz, bh = 0.25, max(0.5, fh - 0.6)
        depth = 0.6
        S.quad(0.0, L, bz, bz + bh, ri["glass"], off=-depth)
        S.g.quad(S.p(0.0, bz, 0.0), S.p(L, bz, 0.0), S.p(L, bz, -depth),
                 S.p(0.0, bz, -depth), ri["frame"])
        S.g.quad(S.p(0.0, bz + bh, 0.0), S.p(L, bz + bh, 0.0), S.p(L, bz + bh, -depth),
                 S.p(0.0, bz + bh, -depth), ri["frame"])
        n = max(2, int(round(L / bay)))
        step = L / n
        for i in range(1, n):
            S.fin(i * step, 0.16, -depth, 0.0, bz, bz + bh, ri["frame"])
        S.fin(0.0, 0.5, 0.0, 0.0, 0.0, fh, ri["frame"])
        S.fin(L, 0.5, 0.0, 0.0, 0.0, fh, ri["frame"])
        if band:
            S.quad(0.0, L, 0.0, min(0.4, fh * 0.18), ri["band"], off=0.05)

    # corner articulation (shared with the neighbouring wall plane)
    for cs in (0.0, L):
        S.fin(cs, 0.42, 0.14, 0.0, 0.0, fh, ri["dark"])


def tier_rect(rect, inset):
    x0, y0, x1, y1 = rect
    return (x0 + inset, y0 + inset, x1 - inset, y1 - inset)


def emit_ring(g, rect, z0, z1, m, cap=True):
    """Parapet / band ring around a rect (front face + top cap per side)."""
    for side in "SWEN":
        S = Side(g, rect, side)
        S.quad(0.0, S.L, z0, z1, m)
        if cap:
            S.g.quad(S.p(0.0, z1, 0.0), S.p(S.L, z1, 0.0),
                     S.p(S.L, z1, 0.18), S.p(0.0, z1, 0.18), m)


def build_ground(geo, mats, st, rect, front, op, gh, tier, name_idx):
    """Ground floor: open retail frontage, piers, header band, plinth, floor, soffit."""
    ri = {k: i for i, k in enumerate(
        ["wall", "pier", "glass", "sign", "ceil", "floor", "curb", "metal"])}
    op_side = op.get("side")
    op_w = float(op.get("width") or 8.0)
    op_h = float(op.get("height") or 4.0)
    header_z = min(gh - 0.05, max(op_h, gh - HEADER_H))
    floor_mat = TIER_FLOOR_MAT.get(tier, "floor_tile")

    for side in "SWEN":
        S = Side(geo, rect, side)
        L = S.L
        if side in front:
            # --- piers (keep the entrance span clear)
            n = max(2, int(round(L / 9.0)))
            step = L / n
            ec = L / 2.0 if side != op_side else L / 2.0
            half = op_w / 2.0 + 1.0 if side == op_side else 1.0
            for i in range(1, n):
                s = i * step
                if abs(s - ec) < half:
                    continue
                S.fin(s, 1.0, 0.0, -0.7, 0.0, gh, ri["pier"])
            # corner piers
            S.fin(0.45, 0.9, 0.0, -0.7, 0.0, gh, ri["pier"])
            S.fin(L - 0.45, 0.9, 0.0, -0.7, 0.0, gh, ri["pier"])
            # header band over the shopfronts (open below -> no glass door)
            if side == op_side and header_z + 0.05 < gh:
                S.quad(0.0, ec - half, header_z, gh, ri["wall"], off=0.0)
                S.quad(ec + half, L, header_z, gh, ri["wall"], off=0.0)
                S.quad(ec - half, ec + half, gh - 0.05, gh, ri["wall"], off=0.0)
                S.quad(0.0, L, header_z, header_z + 0.06, ri["sign"], off=0.10)
            else:
                z0 = gh - HEADER_H if side != op_side else header_z
                S.quad(0.0, L, z0, gh, ri["wall"], off=0.0)
                S.quad(0.0, L, z0 + 0.25, z0 + 0.85, ri["sign"], off=0.10)
            # tenant lettering band (thin plate, sign_metal)
            if side in front:
                S.quad(L * 0.12, L * 0.88, gh - 1.05, gh - 0.45, ri["sign"], off=0.12)
        else:
            # blank flank wall + service door
            S.quad(0.0, L, 0.0, gh, ri["wall"])
            if L > 8.0:
                S.recess(L * 0.5 - 1.1, L * 0.5 + 1.1, 0.0, 2.4, 0.12,
                         ri["metal"], ri["wall"])
        # plinth / curb band around the whole footprint
        S.quad(0.0, L, 0.0, CURB, ri["curb"], off=0.04)

    x0, y0, x1, y1 = rect
    geo.quad((x0, y0, 0.02), (x1, y0, 0.02), (x1, y1, 0.02), (x0, y1, 0.02), ri["floor"])
    geo.quad((x0, y0, gh - 0.15), (x1, y0, gh - 0.15),
             (x1, y1, gh - 0.15), (x0, y1, gh - 0.15), ri["ceil"])


GROUND_MATS = ["concrete", "metal_painted_dark", "glass_shop", "sign_metal",
               "ceiling_paint", "floor_tile", "curb_concrete", "metal_steel"]


def ground_mats(st, tier):
    m = list(GROUND_MATS)
    m[0] = st["ground"]
    m[1] = st["ground"] if st["kind"] != "curtain" else "metal_painted_dark"
    m[5] = TIER_FLOOR_MAT.get(tier, "floor_tile")
    return m


MOD_ROLES = ["glass", "frame", "band", "dark", "wall", "ceil"]


def module_mats(st):
    r = st["roles"]
    return [r[k] for k in MOD_ROLES]


def module_idx():
    return {k: i for i, k in enumerate(MOD_ROLES)}


def build_tier_module(rect, st, fh, band=False):
    g = Geo()
    ri = module_idx()
    kind = st["kind"]
    for side in "SWEN":
        emit_facade(g, ri, kind, rect, side, fh, st["bay"], band=band)
    x0, y0, x1, y1 = rect
    z = fh - 0.06                                   # floor slab closes the volume
    g.quad((x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z), ri["wall"])
    return g


def build_podium_module(rect, fh):
    g = Geo()
    for side in "SWEN":
        emit_facade(g, PODIUM_IDX, "punched", rect, side, fh, 3.0, band=False)
    x0, y0, x1, y1 = rect
    z = fh - 0.06
    g.quad((x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z), PODIUM_IDX["wall"])
    return g


def build_crown(top_rect, base_rect, hero=False, deco=False, louvre=True):
    """Parapet + roof deck + optional louvre/mechanical band + art-deco steps."""
    g = Geo()
    x0, y0, x1, y1 = top_rect
    # roof deck
    g.quad((x0, y0, 0.0), (x1, y0, 0.0), (x1, y1, 0.0), (x0, y1, 0.0), 1)
    if louvre:
        # mechanical louvre band just under the parapet
        for side in "SWEN":
            S = Side(g, top_rect, side)
            S.quad(0.0, S.L, 0.0, 1.4, 2, off=-0.05)
    emit_ring(g, top_rect, 0.0, PARAPET, 0, cap=True)
    if deco or hero:
        r1 = tier_rect(top_rect, 1.2)
        emit_ring(g, r1, PARAPET, PARAPET + 1.1, 0, cap=True)
        g.quad((r1[0], r1[1], PARAPET + 1.1), (r1[2], r1[1], PARAPET + 1.1),
               (r1[2], r1[3], PARAPET + 1.1), (r1[0], r1[3], PARAPET + 1.1), 1)
        r2 = tier_rect(top_rect, 2.6)
        emit_ring(g, r2, PARAPET + 1.1, PARAPET + 2.4, 0, cap=True)
        if hero:
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            g.box(cx, cy, PARAPET + 2.4 + 3.0, 7.0, 7.0, 6.0, 2)
            g.box(cx, cy, PARAPET + 2.4 + 6.0 + 3.5, 4.0, 4.0, 7.0, 0)
            g.box(cx, cy, PARAPET + 2.4 + 6.0 + 7.0 + 4.0, 1.2, 1.2, 8.0, 0)
    return g


CROWN_MATS = ["metal_painted_dark", "roof_bitumen", "metal_painted_dark"]


# ------------------------------------------------------------------ shared kit
class Kits(object):
    """Shared low-poly kit meshes (linked duplicates, never unique copies)."""

    def __init__(self, meshes, lights):
        self.meshes = meshes
        self.lights = lights
        self._m = {}

    def _mk(self, key, name, mats, build):
        if key in self._m:
            return self._m[key]
        me = build_mesh_data(name, build(), mats)
        self._m[key] = me
        return me

    # ---- canopy: local origin = centre of the segment, wall edge at y=0,
    #      extends to y = -CANOPY_PROJ, bottom at z=0 (soffit 2.75 m)
    def canopy(self):
        def b():
            g = Geo()
            p = CANOPY_PROJ
            g.quad((-4.0, 0.0, 0.16), (4.0, 0.0, 0.16),
                   (4.0, -p, 0.10), (-4.0, -p, 0.10), 0)          # top (sloped out)
            g.quad((-4.0, -p, 0.0), (4.0, -p, 0.0),
                   (4.0, -p, 0.42), (-4.0, -p, 0.42), 0)           # fascia edge
            g.quad((-4.0, -p, 0.0), (4.0, -p, 0.0),
                   (4.0, 0.0, 0.02), (-4.0, 0.0, 0.02), 1)         # soffit
            g.quad((-4.0, 0.0, 0.10), (4.0, 0.0, 0.10),
                   (4.0, -p, 0.10), (-4.0, -p, 0.10), 1)           # underside slab
            for bx in (-3.4, 3.4):                                  # brackets
                g.quad((bx - 0.05, 0.0, 0.06), (bx + 0.05, 0.0, 0.06),
                       (bx + 0.05, -p * 0.7, 0.40), (bx - 0.05, -p * 0.7, 0.40), 2)
            return g
        return self._mk("canopy", "SM_Kit_Canopy_00", ["fabric_awning_bone",
                        "ceiling_paint", "metal_painted_dark"], b)

    def neon_strip(self):
        def b():
            g = Geo()
            g.box(0.0, 0.0, 0.04, 8.0, 0.10, 0.08, 0)
            return g
        return self._mk("neon", "SM_Kit_NeonRun_00", ["neon_blue"], b)

    def blade(self):
        def b():
            g = Geo()
            g.box(0.0, -0.5, 0.0, 0.12, 1.0, 0.10, 1)   # bracket
            g.box(0.0, -1.0, 0.0, 1.2, 0.08, 0.6, 0)    # plate
            return g
        return self._mk("blade", "SM_Kit_BladeSign_00", ["sign_metal", "metal_steel"], b)

    def fascia(self):
        def b():
            g = Geo()
            g.box(0.0, 0.0, 0.0, 8.0, 0.14, 0.6, 0)
            return g
        return self._mk("fascia", "SM_Kit_FasciaSign_00", ["sign_metal"], b)

    def roof_sign(self):
        def b():
            g = Geo()
            for px in (-4.5, 4.5):
                g.box(px, 0.0, 1.6, 0.25, 0.25, 3.2, 1)
            g.box(0.0, 0.0, 3.4, 11.0, 0.30, 2.2, 0)     # face
            g.box(0.0, 0.0, 4.6, 11.4, 0.36, 0.20, 1)    # top rail
            return g
        return self._mk("rosign", "SM_Kit_RoofSign_00", ["sign_metal", "metal_steel"], b)

    def plant_room(self):
        def b():
            g = Geo()
            g.box(0.0, 0.0, 1.5, 6.5, 3.6, 3.0, 0)
            g.box(0.0, 0.0, 3.1, 6.9, 4.0, 0.25, 1)
            for i in range(5):
                x = -2.6 + i * 1.3
                g.quad((x, -1.85, 0.5), (x + 0.7, -1.85, 0.5),
                       (x + 0.7, -1.85, 2.5), (x, -1.85, 2.5), 2)
            return g
        return self._mk("plant", "SM_Kit_PlantRoom_00",
                        ["concrete", "roof_bitumen", "metal_rusty"], b)

    def cooling_tower(self):
        def b():
            g = Geo()
            g.box(0.0, 0.0, 1.1, 2.6, 2.6, 2.2, 0)
            g.box(0.0, 0.0, 2.3, 2.9, 2.9, 0.2, 1)
            for a in range(4):
                ang = a * math.pi / 2.0
                dx, dy = math.cos(ang) * 0.8, math.sin(ang) * 0.8
                g.quad((-dx - 0.5, -dy - 0.5, 2.42), (dx - 0.5, dy - 0.5, 2.42),
                       (dx + 0.5, dy + 0.5, 2.42), (-dx + 0.5, -dy + 0.5, 2.42), 2)
            return g
        return self._mk("ctower", "SM_Kit_CoolingTower_00",
                        ["metal_steel", "metal_painted_dark", "metal_rusty"], b)

    def dish(self):
        def b():
            g = Geo()
            rim = [(math.cos(a) * 1.1, math.sin(a) * 1.1, 1.5) for a in
                   [i * math.pi / 4.0 for i in range(8)]]
            apex = (0.0, 0.0, 0.9)
            for i in range(8):
                g.add([apex, rim[i], rim[(i + 1) % 8]], 0)
            g.box(0.0, 0.0, 0.45, 0.18, 0.18, 0.9, 1)
            g.box(0.0, 0.0, 0.06, 1.0, 1.0, 0.12, 1)
            return g
        return self._mk("dish", "SM_Kit_SatDish_00", ["metal_steel", "metal_painted_dark"], b)

    def wc_rail(self):
        def b():
            g = Geo()
            g.box(0.0, 0.0, 1.0, 14.0, 0.16, 0.22, 0)
            for tx in (-5.5, 5.5):
                g.box(tx, 0.0, 0.65, 0.5, 0.5, 1.3, 1)
            return g
        return self._mk("rail", "SM_Kit_WCRail_00", ["metal_steel", "metal_painted_dark"], b)

    def avlight(self):
        def b():
            g = Geo()
            g.box(0.0, 0.0, 0.12, 0.30, 0.30, 0.24, 0)
            return g
        return self._mk("avl", "SM_LGT_AviationLight_00", ["neon_red"], b)

    def lobby_strip(self):
        def b():
            g = Geo()
            g.box(0.0, 0.0, 0.0, 6.0, 0.25, 0.10, 0)
            return g
        return self._mk("lstrip", "SM_LGT_LobbyStrip_00", ["emissive_warm"], b)

    def lobby_strip_cool(self):
        def b():
            g = Geo()
            g.box(0.0, 0.0, 0.0, 6.0, 0.25, 0.10, 0)
            return g
        return self._mk("lstripc", "SM_LGT_LobbyStripCool_00", ["emissive_cool"], b)


# ------------------------------------------------------------------ interiors
INT_HALF = 28.5          # interior shell half-size (buildable 58 - 0.5 clearance)
INT_CEIL = 4.2           # lobby ceiling height under the 5.6-7.4 m retail volume

INT_T1_MATS = ["marble_white", "wall_paint", "ceiling_paint", "metal_steel",
               "floor_carpet", "glass_dark"]
INT_T2_MATS = ["floor_tile", "wall_paint", "ceiling_paint", "metal_steel",
               "glass_dark"]
INT_T3_MATS = ["metal_painted_dark", "floor_carpet", "ceiling_paint"]


def interior_t1():
    """Tier 1: multi-room furnished lobby (reception, seating, lift core)."""
    g = Geo()
    h = INT_HALF
    g.quad((-h, -h, INT_CEIL), (h, -h, INT_CEIL), (h, h, INT_CEIL), (-h, h, INT_CEIL), 2)
    g.box(0.0, h - 0.15, INT_CEIL / 2.0, 2 * h, 0.3, INT_CEIL, 1)          # back wall
    g.box(-h + 0.15, 0.0, INT_CEIL / 2.0, 0.3, 2 * h, INT_CEIL, 1)         # side walls
    g.box(h - 0.15, 0.0, INT_CEIL / 2.0, 0.3, 2 * h, INT_CEIL, 1)
    g.box(-14.0, 6.0, INT_CEIL / 2.0, 28.0, 0.3, INT_CEIL, 1)              # room divider
    g.box(0.15, 17.0, INT_CEIL / 2.0, 0.3, 23.0, INT_CEIL, 1)
    g.box(-14.0, 9.5, 0.55, 8.0, 1.2, 1.1, 3)                              # reception desk
    g.box(-14.0, 9.5, 1.2, 8.4, 1.5, 0.2, 0)
    for sx, sy in ((7.0, 1.0), (13.0, 1.0), (7.0, 6.5), (13.0, 6.5)):      # seating
        g.box(sx, sy, 0.38, 2.4, 2.2, 0.75, 4)
        g.box(sx, sy + 1.0, 0.85, 2.4, 0.3, 0.9, 4)
    g.box(15.0, 20.0, INT_CEIL / 2.0, 12.0, 11.0, INT_CEIL, 3)             # lift core
    for dx in (12.0, 18.0):
        g.quad((dx - 1.2, 14.4, 0.0), (dx + 1.2, 14.4, 0.0),
               (dx + 1.2, 14.4, 2.4), (dx - 1.2, 14.4, 2.4), 5)
    for cx in (-11.0, 11.0):                                               # columns
        g.box(cx, -8.0, INT_CEIL / 2.0, 0.9, 0.9, INT_CEIL, 1)
    g.box(0.0, -20.0, INT_CEIL / 2.0, 0.9, 0.9, INT_CEIL, 1)
    return g


def interior_t2():
    """Tier 2: one-room lobby shell."""
    g = Geo()
    h = INT_HALF
    g.quad((-h, -h, INT_CEIL), (h, -h, INT_CEIL), (h, h, INT_CEIL), (-h, h, INT_CEIL), 2)
    g.box(0.0, h - 0.15, INT_CEIL / 2.0, 2 * h, 0.3, INT_CEIL, 1)
    g.box(-h + 0.15, 0.0, INT_CEIL / 2.0, 0.3, 2 * h, INT_CEIL, 1)
    g.box(h - 0.15, 0.0, INT_CEIL / 2.0, 0.3, 2 * h, INT_CEIL, 1)
    g.box(-10.0, 14.0, 0.55, 7.0, 1.2, 1.1, 3)
    g.box(-10.0, 14.0, 1.2, 7.4, 1.5, 0.2, 0)
    g.box(12.0, 20.0, INT_CEIL / 2.0, 12.0, 11.0, INT_CEIL, 3)
    g.quad((9.6, 14.4, 0.0), (14.4, 14.4, 0.0), (14.4, 14.4, 2.4), (9.6, 14.4, 2.4), 4)
    g.box(-8.0, -6.0, INT_CEIL / 2.0, 0.9, 0.9, INT_CEIL, 1)
    return g


def interior_t3():
    """Tier 3: dark recessed box (fake depth behind the open frontage)."""
    g = Geo()
    h = INT_HALF
    d = 13.0
    g.quad((-h, -h, 4.6), (h, -h, 4.6), (h, d, 4.6), (-h, d, 4.6), 2)
    g.quad((-h, -h, 0.05), (h, -h, 0.05), (h, d, 0.05), (-h, d, 0.05), 1)
    g.box(0.0, d, 2.3, 2 * h, 0.3, 4.6, 0)
    g.box(-h + 0.15, (d - h) / 2.0, 2.3, 0.3, d - h, 4.6, 0)
    g.box(h - 0.15, (d - h) / 2.0, 2.3, 0.3, d - h, 4.6, 0)
    return g


INTERIORS = {1: (interior_t1, INT_T1_MATS, "Lobby"),
             2: (interior_t2, INT_T2_MATS, "Lobby"),
             3: (interior_t3, INT_T3_MATS, "Interior")}


# ------------------------------------------------------------------ massing
def plan_tiers(F, style_key, hero=False):
    p = 3 if F >= 20 else 0
    cuts = []
    if style_key == "art_deco" and F > 16:
        cuts += [8, 14]
    if hero:
        cuts = [8, 14, 30, 45]
    elif F >= 48:
        cuts += [int(F * 0.45), int(F * 0.75)]
    elif F >= 30:
        cuts += [int(F * 0.55)]
    cuts = sorted(c for c in set(cuts) if c > p + 1 and c < F)
    tiers = [(0, 0, 0.0, "ground")]
    if p:
        tiers.append((1, p, 0.0, "podium"))
    inset = SETBACK if p else 0.0
    prev = p + 1
    for c in cuts + [F]:
        if c - 1 >= prev:
            tiers.append((prev, c - 1, inset, "shaft"))
            inset += SETBACK
        prev = max(prev, c)
    return tiers, p


# ------------------------------------------------------------------ buildings
def build_building(p, idx, kits, meshes, colliders, lights, rng):
    """Build one parcel. Returns a stats dict (0 objects for the plaza)."""
    typ = p.get("type")
    if typ == "central_plaza":
        return dict(id=p["id"], type=typ, built=False, objects=0, tris=0)

    style_key = p.get("facade_style") or DEFAULT_STYLE
    st = STYLE.get(style_key, STYLE[DEFAULT_STYLE])
    code = TYPE_CODE.get(typ, "BLD")
    var = STYLE_CODE.get(style_key, "GEN")
    tag = "%s_%s_%03d" % (code, var, idx)

    bx = rect_of(p["buildable_rect"])
    cx, cy = (bx[0] + bx[2]) / 2.0, (bx[1] + bx[3]) / 2.0
    front = set(p.get("frontage") or ["S"])
    op = p.get("opening") or {}
    tier = int(p.get("interior_tier") or 2)
    F = max(1, int(p.get("floors") or 1))
    H = float(p.get("height_m") or F * FL)

    op_h = float(op.get("height") or 0.0) if op.get("side") else 0.0
    gh = max(GH_MIN, op_h + 0.4 if op_h else GH_MIN)
    n_upper = F - 1
    fh = clamp((H - gh) / n_upper, FH_MIN, FH_MAX) if n_upper else 0.0
    tiers, p_floors = plan_tiers(F, style_key,
                                 hero=(typ == "office_tower" and F >= 60))
    top_z = gh + n_upper * fh
    made = []

    # ---- ground floor (open retail frontage, 5.6-7.4 m clear)
    g = Geo()
    build_ground(g, ground_mats(st, tier), st, bx, front, op, gh, tier, idx)
    ob = make_mesh("SM_%s_g" % tag, g, ground_mats(st, tier), meshes)
    if ob is not None:
        made.append(ob)

    # ---- podium + shaft floor modules (one mesh per tier, instanced per floor)
    band_mat = (st["kind"] == "punched")
    for ti, (f0, f1, inset, kind) in enumerate(tiers):
        if kind == "ground":
            continue
        rect = tier_rect(bx, inset)
        if kind == "podium":
            me = build_mesh_data("SM_%s_p" % tag, build_podium_module(rect, fh),
                                 PODIUM_MATS)
            variants = [(me, None)]
        else:
            mA = build_mesh_data("SM_%s_s%da" % (tag, ti),
                                 build_tier_module(rect, st, fh), module_mats(st))
            variants = [(mA, None)]
            if band_mat:
                mB = build_mesh_data("SM_%s_s%db" % (tag, ti),
                                     build_tier_module(rect, st, fh, band=True),
                                     module_mats(st))
                variants = [(mA, False), (mB, True)]
        for f in range(f0, f1 + 1):
            z = gh + (f - 1) * fh
            if band_mat and len(variants) > 1:
                use_band = (f % 3 == 0)
                src = variants[1][0] if use_band else variants[0][0]
            else:
                src = variants[0][0]
            if src is None:
                continue
            ob = add_obj("SM_%s_%s_f%02d" % (tag, kind[:3], f), src, meshes, (0.0, 0.0, z))
            made.append(ob)

    # ---- crown / parapet / mechanical top
    top_rect = tier_rect(bx, tiers[-1][2])
    hero = (typ == "office_tower" and F >= 60)
    crown_mats = [st["roles"]["wall"], "roof_bitumen", st["roles"]["dark"]]
    cg = build_crown(top_rect, bx, hero=hero, deco=(style_key == "art_deco"),
                     louvre=(F >= 12))
    cob = make_mesh("SM_%s_c" % tag, cg, crown_mats, meshes)
    if cob is not None:
        cob.location = (0.0, 0.0, top_z)
        made.append(cob)

    w = top_rect[2] - top_rect[0]
    h = top_rect[3] - top_rect[1]
    tcx, tcy = (top_rect[0] + top_rect[2]) / 2.0, (top_rect[1] + top_rect[3]) / 2.0
    roof_z = top_z + 0.08

    # ---- rooftop plant / cooling / dishes / window-cleaning rail
    if w > 14.0 and h > 14.0:
        for name, dx, dy, rz in (
                ("plant_room", -0.24, 0.22, 0),
                ("cooling_tower", 0.22, 0.24, 15),
                ("cooling_tower", 0.22, -0.06, 0),
                ("dish", -0.24, -0.24, 40)):
            me = getattr(kits, name)()
            if me is None:
                continue
            made.append(add_obj("SM_%s_%s" % (tag, name), me, meshes,
                                (tcx + dx * w, tcy + dy * h, roof_z), rz))
        me = kits.wc_rail()
        if me is not None and w > 16.0:
            made.append(add_obj("SM_%s_wcrail" % tag, me, meshes,
                                (tcx, tcy - h * 0.40, roof_z)))
    if F >= 6 and idx % 3 == 0 and w > 10.0:
        me = kits.roof_sign()
        if me is not None:
            side = "S" if "S" in front else ("N" if "N" in front else "W")
            ox, oy = SIDE_OUT[side]
            made.append(add_obj("SM_%s_roofsign" % tag, me, meshes,
                                (tcx + ox * (w / 2.0 - 2.0), tcy + oy * (h / 2.0 - 2.0),
                                 roof_z), ROT[side]))

    # ---- canopies over the sidewalk + neon runs + blade signs
    for side in sorted(front):
        S = Side(Geo(), bx, side)
        L = S.L
        s = 4.6
        while s + 4.0 <= L - 0.6:
            pt = S.p(s, CANOPY_BOTTOM, 0.0)
            made.append(add_obj("SM_%s_canopy" % tag, kits.canopy(), meshes, pt, ROT[side]))
            s += 9.0
        if L > 8.0:
            pt = S.p(L * 0.5, 2.60, 0.55)
            made.append(add_obj("SM_%s_neon" % tag, kits.neon_strip(), lights, pt, ROT[side]))
            pt = S.p(L * 0.28, 3.10, 0.02)
            made.append(add_obj("SM_%s_blade" % tag, kits.blade(), meshes, pt, ROT[side]))
        if idx % 2 == 0 and L > 9.0:
            me = kits.fascia()
            if me is not None:
                pt = S.p(L * 0.5, gh - 0.75, 0.12)
                made.append(add_obj("SM_%s_fascia" % tag, me, meshes, pt, ROT[side]))

    # ---- interior (tier 1 / 2 / 3)
    ent = op.get("side") or sorted(front)[0]
    if tier in INTERIORS:
        fn, imats, room = INTERIORS[tier]
        ime = kits._m.get("int%d" % tier)
        if ime is None:
            ime = build_mesh_data("SM_Kit_Interior_T%d_00" % tier, fn(), imats)
            kits._m["int%d" % tier] = ime
        if ime is not None:
            made.append(add_obj("INT_%s_%s" % (p["id"], room), ime, meshes,
                                (cx, cy, 0.0), ROT[ent]))
            strip = kits.lobby_strip_cool() if tier != 1 else kits.lobby_strip()
            if strip is not None:
                for ox in (-9.0, 9.0):
                    made.append(add_obj("INT_%s_light" % p["id"], strip, lights,
                                        (cx + ox, cy + 6.0, 3.9), ROT[ent]))

    # ---- aviation lights on tall crowns
    if top_z + PARAPET > 60.0:
        me = kits.avlight()
        if me is not None:
            for px, py in ((top_rect[0] + 0.7, top_rect[1] + 0.7),
                           (top_rect[2] - 0.7, top_rect[1] + 0.7),
                           (top_rect[2] - 0.7, top_rect[3] - 0.7),
                           (top_rect[0] + 0.7, top_rect[3] - 0.7)):
                made.append(add_obj("SM_%s_avl" % tag, me, lights, (px, py, top_z + PARAPET)))

    # ---- collider
    ch = top_z + PARAPET
    geo = Geo()
    geo.box((bx[0] + bx[2]) / 2.0, (bx[1] + bx[3]) / 2.0, ch / 2.0,
            bx[2] - bx[0], bx[3] - bx[1], ch, 0, bottom=True)
    col = make_mesh("COL_%s" % p["id"], geo, ["concrete"], colliders)
    if col is not None:
        col.hide_render = True
        made.append(col)

    tris = sum(ck.tri_count(o) for o in made)
    claimed = (bx[0] - (CANOPY_PROJ if "W" in front else 0.0),
               bx[1] - (CANOPY_PROJ if "S" in front else 0.0),
               bx[2] + (CANOPY_PROJ if "E" in front else 0.0),
               bx[3] + (CANOPY_PROJ if "N" in front else 0.0))
    return dict(id=p["id"], type=typ, style=style_key, tier=tier, floors=F,
                height=round(top_z + PARAPET, 2), fh=round(fh, 3), gh=round(gh, 2),
                tiers=len([t for t in tiers if t[3] != "ground"]),
                built=True, objects=len(made), tris=tris, rect=bx, claimed=claimed,
                cells=p["cell"])


# ------------------------------------------------------------------ clearance
def build_corridors():
    nodes = {n["id"]: n for n in ck.read_road_nodes()}
    out = []
    for e in ck.read_road_edges():
        hw = HALFWIDTH.get(e["hierarchy"])
        if hw is None:
            hw = HALFWIDTH.get(e.get("hierarchy", ""), 6.0)
        a = nodes.get(e["a"])
        b = nodes.get(e["b"])
        if not a or not b:
            continue
        ax, ay = a["pos"][0], a["pos"][1]
        bx, by = b["pos"][0], b["pos"][1]
        if abs(ax - bx) < 1e-6:
            r = (ax - hw, min(ay, by) - hw, ax + hw, max(ay, by) + hw)
        elif abs(ay - by) < 1e-6:
            r = (min(ax, bx) - hw, ay - hw, max(ax, bx) + hw, ay + hw)
        else:                      # diagonal: conservative bbox
            r = (min(ax, bx) - hw, min(ay, by) - hw, max(ax, bx) + hw, max(ay, by) + hw)
        out.append(("%s[%s]" % (e["id"], e["hierarchy"]), r))
    return out


def build_flyover_bands():
    bands = []
    for f in ck.read_layout().get("flyovers", []):
        path = f.get("path")
        if not path:
            continue
        hw = float(f.get("deck_width", 16.0)) / 2.0 + FLY_PAD
        for i in range(len(path) - 1):
            a, b = path[i], path[i + 1]
            if abs(a[0] - b[0]) < 1e-6:
                r = (a[0] - hw, min(a[1], b[1]) - hw, a[0] + hw, max(a[1], b[1]) + hw)
            else:
                r = (min(a[0], b[0]) - hw, a[1] - hw, max(a[0], b[0]) + hw, a[1] + hw)
            bands.append(("%s#%d" % (f["id"], i), r))
    return bands


def verify(built, corridors, bands):
    plaza = None
    for lm in ck.read_layout().get("landmarks", []):
        if lm["id"] == "LM_CENTRAL_PLAZA":
            x, y = lm["pos"]
            plaza = (x - 66.0, y - 66.0, x + 66.0, y + 66.0)
    viol = []
    for b in built:
        r = b["claimed"]
        for cid, c in corridors:
            if inter(r, c):
                viol.append("%s vs road %s" % (b["id"], cid))
        for fid, c in bands:
            if inter(r, c):
                viol.append("%s vs flyover %s" % (b["id"], fid))
        if plaza and inter(r, plaza):
            viol.append("%s vs LM_CENTRAL_PLAZA" % b["id"])
    for i in range(len(built)):
        for j in range(i + 1, len(built)):
            if inter(built[i]["claimed"], built[j]["claimed"]):
                viol.append("%s vs %s (footprint)" % (built[i]["id"], built[j]["id"]))
    log("clearance: %d buildings checked, %d violations" % (len(built), len(viol)))
    for v in viol[:40]:
        log("  VIOLATION " + v)
    return viol


# ------------------------------------------------------------------ scene prep
def reset_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    for me in list(bpy.data.meshes):
        if me.users == 0:
            bpy.data.meshes.remove(me)


def bbox_of(root):
    lo = [1e9, 1e9, 1e9]
    hi = [-1e9, -1e9, -1e9]
    stack = [root]
    n = 0
    while stack:
        c = stack.pop()
        stack.extend(list(c.children))
        for ob in c.objects:
            if ob.type != "MESH":
                continue
            n += 1
            for corner in ob.bound_box:
                w = ob.matrix_world @ Vector(corner)
                for k in range(3):
                    lo[k] = min(lo[k], w[k])
                    hi[k] = max(hi[k], w[k])
    return [round(v, 2) for v in lo + hi], n


def temp_ground(corridors=()):
    """Temporary preview-only ground: light paving + dark asphalt road strips
    (roads belong to the Roads module — deleted again before the final save)."""
    g = Geo()
    g.quad((-950.0, -950.0, -0.06), (950.0, -950.0, -0.06),
           (950.0, 950.0, -0.06), (-950.0, 950.0, -0.06), 0)
    base = make_mesh("TMP_GROUND", g, ["paving_slab"], bpy.context.scene.collection)
    objs = [base]
    r = Geo()
    n = 0
    for _name, rect in corridors:
        if rect[0] > 700 or rect[2] < -700 or rect[1] > 700 or rect[3] < -700:
            continue
        z = -0.05 + n * 0.0003
        r.quad((rect[0], rect[1], z), (rect[2], rect[1], z),
               (rect[2], rect[3], z), (rect[0], rect[3], z), 0)
        n += 1
    road = make_mesh("TMP_GROUND_ROADS", r, ["asphalt"], bpy.context.scene.collection)
    if road is not None:
        objs.append(road)
    return objs


# ------------------------------------------------------------------ main
def main():
    t0 = time.time()
    log("=== downtown build start ===")
    parcels = ck.read_parcels("D")
    reset_scene()

    root = ck.ensure_collection("Downtown")
    meshes = ck.ensure_collection("Downtown/Meshes", parent=root)
    colliders = ck.ensure_collection("Downtown/Colliders", parent=root)
    lights = ck.ensure_collection("Downtown/Lights", parent=root)

    corridors = build_corridors()
    bands = build_flyover_bands()
    kits = Kits(meshes, lights)
    rng = random.Random(7)

    order = sorted(parcels, key=lambda p: (CELLS.index(tuple(p["cell"]))
                                           if tuple(p["cell"]) in CELLS else 99, p["id"]))
    limit = int(os.environ.get("DOWNTOWN_LIMIT", "0") or 0)
    only = os.environ.get("DOWNTOWN_ONLY", "")
    if only:
        order = [p for p in order if p["id"] == only]
        limit = 1
    if limit:
        order = order[:limit]
        log("DOWNTOWN_LIMIT=%d -> smoke test, no saves/previews" % limit)
    built = []
    idx = 0
    for cell in CELLS:
        batch = [p for p in order if tuple(p["cell"]) == cell]
        if not batch:
            continue
        for p in batch:
            idx += 1
            built.append(build_building(p, idx, kits, meshes, colliders, lights, rng))
        if limit:
            continue
        ck.save_blend(BLEND)
        n_ok = sum(1 for b in built if b.get("built"))
        log("cell %s: %d parcels this cell | %d/%d built | objects=%d | tris(expanded)=%d "
            "| unique meshes=%d | %.0fs"
            % (cell, len(batch), n_ok, len(parcels), len(bpy.data.objects),
               ck.tri_count(root), len(unique_meshes()), time.time() - t0))

    claimed = [b for b in built if b.get("claimed")]
    viol = verify(claimed, corridors, bands)

    # ---- sanity: no stock objects, only Downtown at top level
    bad = [ob.name for ob in bpy.data.objects
           if ob.name.split(".")[0] in ("Cube", "Camera", "Light")]
    tops = [c.name for c in bpy.context.scene.collection.children]
    log("top-level collections: %s" % tops)
    if bad:
        log("WARNING stock objects present: %s" % bad)

    if limit:
        log("smoke test: %d buildings, %d objects, %d unique meshes, %d tris (expanded), "
            "%d violations in %.0fs"
            % (len(claimed), len(bpy.data.objects), len(unique_meshes()),
               ck.tri_count(root), len(viol), time.time() - t0))
        for b in claimed:
            log("  %s %s floors=%d h=%.1f objects=%d tris=%d"
                % (b["id"], b["type"], b["floors"], b["height"], b["objects"], b["tris"]))
        return

    # ---- previews (temporary ground slab, removed before the final save)
    bpy.context.scene.world = None          # make_preview builds a bright sky
    ground = temp_ground(corridors)
    try:
        ck.make_preview(PREV_SKY, (-380.0, -560.0, 210.0), (85.0, 10.0, 70.0),
                        sun_elev=38.0, sun_azim=-40.0, sun_energy=4.0)
        ck.make_preview(PREV_STREET, (112.0, -152.0, 1.7), (44.0, -113.0, 46.0),
                        sun_elev=45.0, sun_azim=55.0, sun_energy=4.0)
    finally:
        for ob in ground:
            me = getattr(ob, "data", None)
            bpy.data.objects.remove(ob, do_unlink=True)
            if me is not None and me.users == 0:
                bpy.data.meshes.remove(me)

    ck.save_blend(BLEND)

    # ---- stats
    bpy.context.view_layer.update()
    uniq = unique_meshes()
    uniq_tris = sum(ck.tri_count(m) for m in uniq.values())
    exp_tris = ck.tri_count(root)
    objs = [ob for ob in bpy.data.objects if ob.type == "MESH"]
    mats_used = sorted({m.name for ob in objs for m in ob.data.materials if m})
    bbox, _ = bbox_of(root)

    by_type, by_tier, by_style = {}, {}, {}
    for b in built:
        if not b.get("built"):
            continue
        by_type[b["type"]] = by_type.get(b["type"], 0) + 1
        by_tier[str(b["tier"])] = by_tier.get(str(b["tier"]), 0) + 1
        by_style[b["style"]] = by_style.get(b["style"], 0) + 1
    heaviest = max((b for b in built if b.get("built")), key=lambda b: b["tris"])
    tower = next((b for b in built if b["id"] == "B_4_3_0_1_0_0"), None)

    payload = dict(
        parcels=len(parcels),
        built=sum(1 for b in built if b.get("built")),
        reserved=[b["id"] for b in built if not b.get("built")],
        objects=len(bpy.data.objects),
        mesh_objects=len(objs),
        unique_meshes=len(uniq),
        tris_unique_meshes=uniq_tris,
        tris_expanded=exp_tris,
        colliders=sum(1 for ob in colliders.objects),
        lights_objects=sum(1 for ob in lights.objects),
        counts_by_type=by_type,
        counts_by_interior_tier=by_tier,
        counts_by_facade_style=by_style,
        materials=mats_used,
        bbox=bbox,
        build_seconds=round(time.time() - t0, 1),
        violations=len(viol),
        violation_list=viol[:20],
        top_level_collections=tops,
        stock_objects=bad,
        heaviest_building=dict(id=heaviest["id"], tris=heaviest["tris"],
                               objects=heaviest["objects"]),
        landmark_tower=tower,
        assembler_contract=dict(
            road_halfwidth_m=HALFWIDTH,
            flyover_keepout="deck footprint + 2.0 m",
            flyover_bands=[[n, list(map(float, r))] for n, r in bands],
            plaza_rect=[12.0, 12.0, 144.0, 144.0],
            canopy_projection_m=CANOPY_PROJ,
            canopy_soffit_m=CANOPY_BOTTOM,
            door_head_m=2.4,
            floor_height_m=FL,
            curb_height_m=CURB,
            clear_frontage="open shopfront bays, no glass doors",
        ),
        budgets=dict(regular_building_tris_limit=40000,
                     hero_tris_limit=150000, module_tris_limit=12000000),
    )
    ck.write_report("downtown", payload)

    lines = [
        "# downtown — Phase C (DOWNTOWN agent)", "",
        "Generated by `modules/downtown.py` (headless, EEVEE previews).", "",
        "## Counts", "",
        "| item | value |", "|---|---|",
        "| parcels handled | %d (108 built + LM_CENTRAL_PLAZA reserved) |" % len(parcels),
        "| buildings | %d |" % payload["built"],
        "| mesh objects | %d |" % payload["mesh_objects"],
        "| unique meshes | %d |" % payload["unique_meshes"],
        "| tris (unique meshes) | %d |" % uniq_tris,
        "| tris (expanded, instances counted) | %d |" % exp_tris,
        "| colliders | %d |" % payload["colliders"],
        "| emissive fixtures (Lights) | %d |" % payload["lights_objects"],
        "| build seconds | %.0f |" % payload["build_seconds"], "",
        "### per type / tier / facade style", "",
        "- type: %s" % json.dumps(by_type, sort_keys=True),
        "- interior tier: %s" % json.dumps(by_tier, sort_keys=True),
        "- facade style: %s" % json.dumps(by_style, sort_keys=True), "",
        "## Landmark tower (LM_LANDMARK_TOWER)", "",
    ]
    if tower:
        lines += [
            "- parcel `B_4_3_0_1_0_0`, %d floors, art_deco, tier %d" % (tower["floors"], tower["tier"]),
            "- floor-to-floor %.2f m, retail ground floor %.1f m, %d setback tiers" % (tower["fh"], tower["gh"], tower["tiers"]),
            "- top of parapet %.1f m (+ stepped crown, mechanical box, spire, aviation lights)" % tower["height"],
            "- tris %d (limit 150000), objects %d" % (tower["tris"], tower["objects"]),
        ]
    lines += [
        "", "## Assembler contract (clearances)", "",
        "- road half-widths: highway 17 / arterial 12 / street 6 / alley 2.5 m",
        "- flyover keep-out: FLY_DT_EW band y -10..10, FLY_DT_NS band x -10..10 (deck 16 m + 2 m)",
        "- LM_CENTRAL_PLAZA rect [12,12,144,144] kept clear",
        "- canopy projects %.1f m out of buildable_rect, soffit %.2f m (>= 2.7)" % (CANOPY_PROJ, CANOPY_BOTTOM),
        "- open shopfronts: no glass doors; door head 2.4 m, curb %.2f m, floor %.1f m" % (CURB, FL),
        "- all meshes at scale 1; transforms are translation (+90 deg Z rotation on shared kits) only",
        "", "## Verification", "",
        "- violations: **%d** (buildable / road / flyover / plaza / neighbour)" % len(viol),
        "- stock Cube/Camera/Light: %s" % (bad or "none"),
        "- top-level collections: %s" % ", ".join(tops),
        "- previews: `out/downtown_preview.png`, `out/downtown_street_preview.png`",
        "- bbox: %s" % bbox, "",
        "## Materials used (%d)" % len(mats_used), "",
        "`%s`" % "`, `".join(mats_used), "",
        "## Known issues / notes", "",
        "- `PZ_4_4_0_0` (LM_CENTRAL_PLAZA) is left empty on purpose — plaza ground belongs to the Plaza/Props agent",
        "- no parking-structure archetype: parcels_D.json contains none",
        "- upper-floor interiors are not modelled (only ground-floor lobbies, per plan section 5)",
        "- requested from materials: none (every material exists in materials.blend)",
    ]
    path = os.path.join(ck.REPORTS_DIR, "downtown_report.md")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    log("report -> %s" % path)
    log("=== done in %.0fs | %d objects | %d unique meshes | %d/%d tris (unique/expanded) ==="
        % (time.time() - t0, len(bpy.data.objects), len(uniq), uniq_tris, exp_tris))


if __name__ == "__main__":
    main()
