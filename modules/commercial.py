#!/usr/bin/env python3
"""commercial.py — Commercial module rebuild (COMMERCIAL-REBUILD), headless.

Rebuilds every Commercial facility listed in reports/program.json as solid box
massing: base plinth, closed walls on ALL four sides, floor slabs, roof slab +
parapet. Retail = open storefront arcades (no glass, no doors); office/hotel =
storefront glazing with a recessed lobby on the road-facing side; industrial =
solid walls with a dark service opening. Upper storeys get glazing bands on
all four sides. Tier 1 heroes get a furnished ground-floor room, tier 2 one
room, tier 3 a dark recess. Heroes get <=6 LT_com_* point lights; every mass
gets emissive signage. COL_com_<id> colliders per building.

Conventions: mesh data built around a local origin at the footprint bottom
centre; object transform = translation only (rotation baked into the shared
mesh), matching market/civic/residential modules; metres, Z-up; every
material appended from /city/materials.blend.

Run:  cd /home/abdulhadi/Work/city && blender -b --factory-startup -P modules/commercial.py
"""
from __future__ import annotations

import json
import math
import os
import sys

ROOT = "/home/abdulhadi/Work/city"
if not os.path.isdir(ROOT):
    raise RuntimeError("city root missing: %s" % ROOT)
sys.path.insert(0, ROOT + "/modules")

import citykit as ck  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

MODULE = "Commercial"

# ------------------------------------------------------------------ constants
FLOOR = 3.2
SLAB = 0.30
CURB = 0.15
TW = 0.25
HX = 0.25          # mullion pier width
DOOR_H = 2.4
PARAPET = 1.0
CIRCUIT = (612.0, -1188.0, 1188.0, -12.0)
BUDGET = {"hero": 150000, "regular": 40000, "prop": 5000}

# ------------------------------------------------------------------ archetypes
RETAIL = {"RET_MALL", "RET_SUPERMARKET", "RET_SHOPS", "RET_CORNER_SHOP",
          "RET_RESTAURANT", "RET_CAFE", "DEPARTMENT_STORE", "RET_WHOLESALER",
          "RET_MOTOR_TRADE", "REC_FARMERS_MARKET", "TRK_FOOD_COURT", "TRK_MERCH_HALL"}
OFFICE = {"OFF_TOWER", "OFF_MIDRISE", "OFFICE_COWORKING", "FIN_BANK",
          "WRK_TECH_PARK", "WRK_DATA_CENTRE", "ICON_TOWER", "MED_BROADCAST"}
HOTEL = {"HOT_HOTEL", "HOT_AIRPORT_HOTEL", "HOT_MOTEL", "HOSTEL", "BANQUET_HALL"}
IND = {"IND_WAREHOUSE", "IND_FACTORY", "BREWERY", "COLD_STORAGE",
       "WORKSHOP_FABRICATION", "WRK_LOGISTICS_HUB", "WRK_CONSTRUCTION_YARD",
       "MED_FILM_STUDIO"}
HALL = {"CONFERENCE_CENTRE"}


def cat_of(fid):
    for grp, c in ((RETAIL, "retail"), (OFFICE, "office"), (HOTEL, "hotel"),
                   (IND, "industrial"), (HALL, "hall")):
        if fid in grp:
            return c
    return "retail"


TYPES = {
    "RET_MALL": ("Retail", "Mall"), "RET_SUPERMARKET": ("Retail", "Supermarket"),
    "RET_SHOPS": ("Retail", "Shops"), "RET_CORNER_SHOP": ("Retail", "CornerShop"),
    "RET_RESTAURANT": ("Retail", "Restaurant"), "RET_CAFE": ("Retail", "Cafe"),
    "DEPARTMENT_STORE": ("Retail", "DepartmentStore"),
    "RET_WHOLESALER": ("Retail", "Wholesaler"),
    "RET_MOTOR_TRADE": ("Retail", "MotorTrade"),
    "REC_FARMERS_MARKET": ("Retail", "FarmersMarket"),
    "TRK_FOOD_COURT": ("Retail", "FoodCourt"), "TRK_MERCH_HALL": ("Retail", "MerchHall"),
    "OFF_TOWER": ("Office", "Tower"), "OFF_MIDRISE": ("Office", "Midrise"),
    "OFFICE_COWORKING": ("Office", "Coworking"), "FIN_BANK": ("Office", "Bank"),
    "WRK_TECH_PARK": ("Office", "TechPark"), "WRK_DATA_CENTRE": ("Office", "DataCentre"),
    "ICON_TOWER": ("Icon", "Tower"), "HOT_HOTEL": ("Hotel", "Highrise"),
    "HOT_AIRPORT_HOTEL": ("Hotel", "Airport"), "HOT_MOTEL": ("Hotel", "Motel"),
    "HOSTEL": ("Hotel", "Hostel"), "BANQUET_HALL": ("Hotel", "Banquet"),
    "CONFERENCE_CENTRE": ("Civic", "Conference"),
    "IND_WAREHOUSE": ("Ind", "Warehouse"), "IND_FACTORY": ("Ind", "Factory"),
    "BREWERY": ("Ind", "Brewery"), "COLD_STORAGE": ("Ind", "ColdStore"),
    "WORKSHOP_FABRICATION": ("Ind", "Workshop"), "WRK_LOGISTICS_HUB": ("Ind", "Logistics"),
    "WRK_CONSTRUCTION_YARD": ("Ind", "YardOffice"),
    "MED_FILM_STUDIO": ("Ind", "FilmStudio"), "MED_BROADCAST": ("Media", "Broadcast"),
}
FLOOR_MAX = {"OFF_TOWER": 30, "HOT_HOTEL": 8}     # per contract (~96 m, 8 fl)
ROOM = {"RET_MALL": "Atrium", "OFF_TOWER": "Lobby", "HOT_HOTEL": "Lobby",
        "DEPARTMENT_STORE": "Atrium", "CONFERENCE_CENTRE": "Hall",
        "BANQUET_HALL": "Hall", "HOT_AIRPORT_HOTEL": "Lobby", "ICON_TOWER": "Foyer",
        "BREWERY": "TapHall", "MED_BROADCAST": "Studio", "HOT_MOTEL": "Lobby",
        "WRK_TECH_PARK": "Lobby", "WRK_LOGISTICS_HUB": "Office",
        "TRK_SPECTATOR_VILLAGE": "Village", "RET_WHOLESALER": "Hall"}
ROOM_DEFAULT = {"retail": "Mart", "office": "Lobby", "hotel": "Lobby",
                "industrial": "Office", "hall": "Hall"}


class Ctx:
    pass


ctx = Ctx()
ctx.built = []
ctx.skipped = []
ctx.violations = []
ctx.mats_used = set()
ctx.meshes = []            # (name, mesh) unique data blocks
ctx.props = {}             # kind -> mesh
ctx.prop_proto_tris = {}
ctx.prop_instances = 0
ctx.instanced_tris = 0
ctx.light_n = 0
ctx.collider_n = 0
ctx.unique_tris = 0
ctx.type_seq = {}


# ------------------------------------------------------------------ builder
class BD:
    """Builder with named material slots; boxes with outward normals."""

    def __init__(self):
        self.v = []
        self.f = []
        self.mi = []
        self.mats = []
        self._m = {}

    def mi_of(self, name):
        i = self._m.get(name)
        if i is None:
            i = len(self.mats)
            self._m[name] = i
            self.mats.append(name)
        return i

    def box(self, x0, x1, y0, y1, z0, z1, mat):
        x0, x1 = min(x0, x1), max(x0, x1)
        y0, y1 = min(y0, y1), max(y0, y1)
        z0, z1 = min(z0, z1), max(z0, z1)
        n = len(self.v)
        self.v.extend([(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                       (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)])
        i = self.mi_of(mat)
        quads = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                 (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))
        for q in quads:
            self.f.append((n + q[0], n + q[1], n + q[2]))
            self.f.append((n + q[0], n + q[2], n + q[3]))
            self.mi.append(i)
            self.mi.append(i)


def emit_mesh(name, bd):
    me = bpy.data.meshes.new(name)
    me.from_pydata(bd.v, [], bd.f)
    me.validate(verbose=False)
    me.update()
    for mn in bd.mats:
        ck.append_material(mn)
        me.materials.append(bpy.data.materials[mn])
    for p, mi in zip(me.polygons, bd.mi):
        p.material_index = int(mi)
    return me


def new_obj(name, me, loc, coll):
    ob = bpy.data.objects.new(name, me)
    ob.location = (float(loc[0]), float(loc[1]), float(loc[2] if len(loc) > 2 else 0.0))
    ck.link_obj(ob, coll)
    return ob


# --------------------------------------------------------------------- kits
WANT = ["facade_plaster_bone", "facade_concrete_slab", "facade_brick_red", "brick_brown",
        "glass_tinted_office", "glass_dark", "glass_shop", "glass_office",
        "roof_bitumen_flat", "concrete", "concrete_poured", "sidewalk_concrete",
        "metal_steel", "metal_painted_charcoal", "metal_painted_navy",
        "metal_painted_oxblood", "metal_painted_sand", "facade_plaster_charcoal",
        "facade_plaster_sand", "facade_metal_panel", "facade_concrete_weathered",
        "neon_oxblood", "neon_mustard", "neon_teal", "emissive_warm", "emissive_cool",
        "int_wall_paint_bone", "int_wall_paint_sand", "int_laminate_counter",
        "int_tile_floor", "floor_tile", "floor_carpet", "wood_painted", "wood_planks",
        "sign_white", "metal_rusty"]


def prep_kit():
    with bpy.data.libraries.load(ck.MATERIALS_BLEND, link=False) as (src, _dst):
        avail = {n for n in src.materials if n}
    ok = {w for w in WANT if w in avail}
    missing = [w for w in WANT if w not in avail]
    if missing:
        print("[commercial] WARNING unavailable: %s" % ", ".join(missing))

    def need(*names):
        for n in names:
            if n in ok:
                return n
        raise RuntimeError("materials missing: %s (have %d of WANT)"
                           % (names, len(ok)))

    kits = {}
    walls_by = {
        "retail": [need("facade_brick_red"), need("facade_plaster_bone"),
                   need("brick_brown"), need("facade_concrete_slab"),
                   need("facade_plaster_sand")],
        "office": [need("facade_concrete_slab"), need("facade_plaster_bone"),
                   need("facade_metal_panel"), need("facade_plaster_charcoal")],
        "hotel": [need("facade_concrete_slab"), need("facade_plaster_bone"),
                  need("facade_plaster_charcoal"), need("facade_metal_panel")],
        "industrial": [need("concrete"), need("concrete_poured"),
                       need("facade_metal_panel"), need("facade_concrete_weathered")],
        "hall": [need("facade_concrete_slab"), need("facade_plaster_bone")],
    }
    for cat, walls in walls_by.items():
        kits[cat] = dict(
            wall=walls,
            glasses=[need("glass_tinted_office"), need("glass_dark"), need("glass_office")],
            shop_glass=[need("glass_shop"), need("glass_dark")],
            frame=need("metal_painted_charcoal"),
            coping=need("metal_painted_charcoal"),
            plinth=need("sidewalk_concrete"),
            slab=need("concrete_poured"),
            roof=need("roof_bitumen_flat"),
            steel=need("metal_steel"),
            neon=[need("neon_oxblood"), need("neon_mustard"), need("neon_teal")],
            emis=[need("emissive_warm"), need("emissive_cool")],
            int_wall=[need("int_wall_paint_bone"), need("int_wall_paint_sand")],
            dark=need("facade_plaster_charcoal"),
            int_floor=[need("int_tile_floor"), need("floor_tile"), need("floor_carpet")],
            counter=need("int_laminate_counter"),
            wood=need("wood_planks"), pwood=need("wood_painted"),
            sign=need("sign_white"),
        )
    return kits, sorted(ok), missing


KIT, AVAIL, MISSING = prep_kit()


def rng_for(seed):
    st = 2166136261
    for ch in str(seed):
        st = ((st ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    st &= 0x7FFFFFFF

    def r():
        nonlocal st
        st = (1103515245 * st + 12345) & 0x7FFFFFFF
        return st

    return r


# ------------------------------------------------------------------ geometry
def faces4(bx):
    x0, x1, y0, y1 = bx
    return [
        dict(ax="x", outer=x1, idir=-1, s0=y0, s1=y1),               # 0 E (+x)
        dict(ax="x", outer=x0, idir=+1, s0=y0, s1=y1),               # 1 W (-x)
        dict(ax="y", outer=y1, idir=-1, s0=x0 + TW, s1=x1 - TW),     # 2 N (+y)
        dict(ax="y", outer=y0, idir=+1, s0=x0 + TW, s1=x1 - TW),     # 3 S (-y)
    ]


def fbox(bd, f, u0, u1, z0, z1, mat, d0=0.0, d1=TW):
    """Wall piece on face f: u along the face span, depth d0..d1 inward."""
    if u1 - u0 < 1e-6 or z1 - z0 < 1e-6 or d1 - d0 < 1e-6:
        return
    a = f["outer"] + f["idir"] * d0
    b = f["outer"] + f["idir"] * d1
    if f["ax"] == "x":
        bd.box(min(a, b), max(a, b), u0, u1, z0, z1, mat)
    else:
        bd.box(u0, u1, min(a, b), max(a, b), z0, z1, mat)


def bays(span, nbays, pier_w, corner_w):
    """OPEN intervals (the voids between piers)."""
    span = max(0.0, span - 2 * corner_w)
    nbays = max(1, min(int(nbays), 60))
    pitch = (span - pier_w * (nbays - 1)) / nbays
    out = []
    u = 0.0
    for _ in range(nbays):
        if pitch > 0.35:
            out.append((u, u + pitch))
        u += pitch + pier_w
    return out


def slats(span, nbays, pier_w, corner_w):
    """PIER intervals between the open bays (complement of bays())."""
    nbays = max(1, min(int(nbays), 60))
    ob = (span - 2 * corner_w - pier_w * (nbays - 1)) / nbays
    if ob <= 0.25:
        return []
    out = []
    u = corner_w + ob
    for _ in range(nbays - 1):
        out.append((u, u + pier_w))
        u += ob + pier_w
    return out


def ground_arcade(bd, f, kit, z_top, wt=0.5, bay_t=3.4):
    """Open storefront arcade: masonry piers between open bays, no glass, no doors."""
    s0, s1 = f["s0"], f["s1"]
    fbox(bd, f, s0, s1, CURB + DOOR_H, z_top, kit["wall"][0])         # fascia band
    fbox(bd, f, s0, s0 + wt, CURB, CURB + DOOR_H, kit["wall"][0])     # end piers
    fbox(bd, f, s1 - wt, s1, CURB, CURB + DOOR_H, kit["wall"][0])
    for (p0, p1) in slats(s1 - s0, int(round((s1 - s0) / bay_t)), wt, wt):
        fbox(bd, f, s0 + p0, s0 + p1, CURB, CURB + DOOR_H, kit["wall"][0])


def ground_storefront(bd, f, kit, z_top, recess=None, glassless=False):
    """Glazed ground storey: masonry sill, glazing band, masonry fascia.
    recess=(centre_frac, halffrac) -> recessed lobby on this face."""
    s0, s1 = f["s0"], f["s1"]
    gm = kit["shop_glass"][0]
    fbox(bd, f, s0, s1, CURB, CURB + 0.60, kit["wall"][0])            # sill
    fbox(bd, f, s0, s1, CURB + DOOR_H, z_top, kit["wall"][0])         # header

    def glaze(o0, o1):
        if o1 - o0 < 0.8:
            return
        nb = max(1, int(round((o1 - o0) / 3.0)))
        for (p0, p1) in slats(o1 - o0, nb, HX, 0.0):       # mullion piers
            fbox(bd, f, o0 + p0, o0 + p1, CURB + 0.60, CURB + DOOR_H,
                 kit["frame"], d0=0.0, d1=0.22)
        for (u0, u1) in bays(o1 - o0, nb, HX, 0.0):        # glazing panes
            if not glassless:
                fbox(bd, f, o0 + u0 + 0.05, o0 + u1 - 0.05, CURB + 0.60,
                     CURB + DOOR_H, gm, d0=0.55, d1=0.63)

    if recess:
        span = s1 - s0
        r0 = s0 + span * (recess[0] - recess[1])
        r1 = s0 + span * (recess[0] + recess[1])
        glaze(s0, r0)
        glaze(r1, s1)
        # recessed glass plane, open front in between (no doors)
        fbox(bd, f, r0, r1, CURB + 0.60, CURB + DOOR_H, gm, d0=1.90, d1=1.98)
        for u in (r0, r1 - 0.25):     # return walls closing the recess
            fbox(bd, f, u, u + 0.25, CURB + 0.60, z_top, kit["wall"][0],
                 d0=0.0, d1=2.0)
    else:
        glaze(s0, s1)


def ground_industrial(bd, f, kit, z_top, opening):
    """Solid wall; dark service bay (dark recess, no doors) on entrance face."""
    s0, s1 = f["s0"], f["s1"]
    if not opening:
        fbox(bd, f, s0, s1, CURB, z_top, kit["wall"][0])
        return
    w = min(4.2, (s1 - s0) * 0.35)
    o0 = (s0 + s1) * 0.5 - w * 0.5
    o1 = o0 + w
    fbox(bd, f, s0, o0, CURB, z_top, kit["wall"][0])
    fbox(bd, f, o1, s1, CURB, z_top, kit["wall"][0])
    fbox(bd, f, o0, o1, CURB + DOOR_H + 0.15, z_top, kit["wall"][0])
    d0, d1 = 0.90, 1.05
    a = f["outer"] + f["idir"] * d0
    b = f["outer"] + f["idir"] * d1
    lo, hi = min(a, b), max(a, b)
    if f["ax"] == "x":
        bd.box(lo, hi, o0, o1, CURB, CURB + DOOR_H + 0.15, kit["dark"])
    else:
        bd.box(o0, o1, lo, hi, CURB, CURB + DOOR_H + 0.15, kit["dark"])


def upper_ring(bd, f, kit, zb, industrial=False):
    """One upper storey: masonry sill, glazing band, masonry header."""
    s0, s1 = f["s0"], f["s1"]
    g0, g1 = zb + 0.95, zb + 2.60
    fbox(bd, f, s0, s1, zb, g0, kit["wall"][0])
    fbox(bd, f, s0, s1, g1, zb + 2.90, kit["wall"][0])
    span = s1 - s0
    div = max(4.5 if industrial else 3.0, span / 14.0)
    nb = max(1, int(round(span / div)))
    for (p0, p1) in slats(span, nb, 0.45, 0.45):           # mullion piers
        fbox(bd, f, s0 + p0, s0 + p1, g0, g1, kit["frame"], d0=0.0, d1=0.22)
    for i, (u0, u1) in enumerate(bays(span, nb, 0.45, 0.45)):
        if industrial and i % 2:
            fbox(bd, f, s0 + u0, s0 + u1, g0, g1, kit["wall"][0])
            continue
        gm = kit["glasses"][i % len(kit["glasses"])]
        fbox(bd, f, s0 + u0 + 0.06, s0 + u1 - 0.06, g0, g1, gm, d0=0.55, d1=0.63)


def interior_hall(bd, bx, kit):
    """Ground-floor room: 4 walls inset 1.3 m, entry gap on the S side (2.4 m)."""
    x0, x1, y0, y1 = bx
    ii = 1.3
    hx0, hx1, hy0, hy1 = x0 + ii, x1 - ii, y0 + ii, y1 - ii
    m = kit["int_wall"][0]
    cxm = (hx0 + hx1) * 0.5
    gg = min(3.0, (hx1 - hx0) * 0.25)
    z0, z1 = 0.30, CURB + FLOOR     # from interior floor top to ground ceiling
    bd.box(hx0, hx0 + 0.2, hy0, hy1, z0, z1, m)
    bd.box(hx1 - 0.2, hx1, hy0, hy1, z0, z1, m)
    bd.box(hx0, hx1, hy1 - 0.2, hy1, z0, z1, m)
    bd.box(hx0, cxm - gg * 0.5, hy0, hy0 + 0.2, z0, z1, m)
    bd.box(cxm + gg * 0.5, hx1, hy0, hy0 + 0.2, z0, z1, m)
    bd.box(cxm - gg * 0.5, cxm + gg * 0.5, hy0, hy0 + 0.2, z0 + DOOR_H, z1, m)
    return (hx0, hy0, hx1, hy1)


def core_dark(bd, bx, kit):
    """Tier 3: dark inner mass so ground openings read as a dark recess."""
    x0, x1, y0, y1 = bx
    bd.box(x0 + 1.0, x1 - 1.0, y0 + 1.0, y1 - 1.0, CURB, CURB + FLOOR - 0.15,
           kit["dark"])


def sign_splits(s0, s1, hero):
    L = s1 - s0
    if hero:
        return [(s0 + 0.14 * L, s0 + 0.86 * L)]
    return [(s0 + 0.05 * L, s0 + 0.42 * L), (s0 + 0.58 * L, s0 + 0.95 * L)]


# ------------------------------------------------------------- road distance
_SEGMENTS = None


def road_segments():
    global _SEGMENTS
    if _SEGMENTS is not None:
        return _SEGMENTS
    lay = ck.read_layout()
    pos = {n["id"]: (n["pos"][0], n["pos"][1]) for n in lay["road_nodes"]}
    segs = []
    for e in lay["road_edges"]:
        a, b = pos.get(e["a"]), pos.get(e["b"])
        if a and b:
            segs.append((a[0], a[1], b[0], b[1]))
    _SEGMENTS = segs
    return segs


def dist_pt_seg(px, py, sx, sy, ex, ey):
    dx, dy = ex - sx, ey - sy
    L2 = dx * dx + dy * dy
    if L2 < 1e-9:
        return math.hypot(px - sx, py - sy)
    t = max(0.0, min(1.0, ((px - sx) * dx + (py - sy) * dy) / L2))
    return math.hypot(px - (sx + t * dx), py - (sy + t * dy))


def entrance_face(rect, segs):
    """Face index of the rect side closest to a road corridor (E=0,W=1,N=2,S=3)."""
    x0, y0, x1, y1 = rect
    mids = [(x1, (y0 + y1) * 0.5), (x0, (y0 + y1) * 0.5),
            ((x0 + x1) * 0.5, y1), ((x0 + x1) * 0.5, y0)]
    dists = [min(dist_pt_seg(px, py, *s) for s in segs) for px, py in mids]
    best = min(range(4), key=lambda i: dists[i])
    if dists[3] <= dists[best] + 0.5:   # prefer the S face on ties
        return 3
    return best


def rect_road_clearance(rect, segs):
    x0, y0, x1, y1 = rect
    mids = [(x1, (y0 + y1) * 0.5), (x0, (y0 + y1) * 0.5),
            ((x0 + x1) * 0.5, y1), ((x0 + x1) * 0.5, y0)]
    return min(min(dist_pt_seg(px, py, *s) for s in segs) for px, py in mids)


def rect_overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


# ------------------------------------------------------------- prop kit
def make_prop_proto(kind):
    bd = BD()
    r = KIT["retail"]
    o = KIT["office"]
    if kind == "counter":
        bd.box(-1.6, 1.6, -0.38, 0.38, 0.0, 0.95, r["wood"])
        bd.box(-1.66, 1.66, -0.44, 0.44, 0.95, 1.07, r["counter"])
    elif kind == "desk":
        bd.box(-0.85, 0.85, -0.40, 0.40, 0.64, 0.74, r["wood"])
        for sx in (-0.78, 0.68):
            bd.box(sx, sx + 0.10, -0.35, 0.35, 0.0, 0.64, o["frame"])
    elif kind == "bin":
        bd.box(-0.28, 0.28, -0.28, 0.28, 0.0, 0.95, o["steel"])
        bd.box(-0.33, 0.33, -0.33, 0.33, 0.95, 1.03, r["frame"])
    elif kind == "shelf":
        for sy in (-0.28, 0.28):
            bd.box(-1.90, 1.90, sy - 0.03, sy + 0.03, 0.0, 2.0, r["frame"])
        for k in range(4):
            bd.box(-1.85, 1.85, -0.26, 0.26, 0.28 + k * 0.50, 0.34 + k * 0.50, r["wood"])
    return emit_mesh("SM_Prop_%s_01" % kind.capitalize(), bd)


def furnish(fid, info, tail=0):
    """Linked-duplicate props inside the hall. Returns instance count."""
    if info["tier"] == 1:
        plan = [("counter", 1), ("desk", 3), ("bin", 2)]
        if info["cat"] == "retail":
            plan += [("shelf", 3)]
    elif info["tier"] == 2:
        plan = [("counter", 1), ("desk", 1)]
    else:
        return 0
    r = rng_for("P" + fid)
    hx0, hy0, hx1, hy1 = info["hall"]
    cx, cy = info["cx"], info["cy"]
    z = 0.30
    n = 0
    for kind, cnt in plan:
        me = ctx.props.get(kind)
        if me is None:
            me = make_prop_proto(kind)
            ctx.props[kind] = me
            ctx.meshes.append((me.name, me))
            ctx.prop_proto_tris[kind] = ck.tri_count(me)
        for _ in range(cnt):
            n += 1
            px = cx + (r() % 1000 / 1000.0 - 0.5) * max(1.0, (hx1 - hx0) - 5.0)
            py = cy + (r() % 1000 / 1000.0 - 0.5) * max(1.0, (hy1 - hy0) - 5.0)
            new_obj("SM_Prop_%s_%s_%02d" % (kind.capitalize(), fid[:14], tail + n),
                    me, (px, py, z), ctx.meshes_coll)
            ctx.prop_instances += 1
            ctx.instanced_tris += ctx.prop_proto_tris[kind]
    return n


# --------------------------------------------------------------- facility
def build_facility(fd, segs):
    fid = fd["id"]
    tx, ts = TYPES.get(fid, ("Mixed", fid.title()))
    nn = ctx.type_seq[(tx, ts)] = ctx.type_seq.get((tx, ts), 0) + 1
    name = "SM_%s_%s_%02d" % (tx, ts, nn)
    cat = cat_of(fid)
    kit = KIT[cat]
    rect = list((fd.get("placement") or {}).get("rect") or [0, 0, 10, 10])

    # OFF_TOWER + OFF_MIDRISE share the [12,-288,78,-222] superlot: split it
    if fid == "OFF_TOWER":
        rect = [(rect[0] + rect[2]) * 0.5, rect[1] + 3.0, rect[2] - 3.0, rect[3] - 3.0]
    elif fid == "OFF_MIDRISE":
        rect = [rect[0] + 3.0, rect[1] + 3.0, (rect[0] + rect[2]) * 0.5, rect[3] - 3.0]
    else:
        rect = [rect[0] + 3.0, rect[1] + 3.0, rect[2] - 3.0, rect[3] - 3.0]
    width, dep = rect[2] - rect[0], rect[3] - rect[1]
    if width < 8.0 or dep < 8.0:
        raise RuntimeError("footprint too small %.1fx%.1f" % (width, dep))

    if fid in FLOOR_MAX:
        n_fl = FLOOR_MAX[fid]
    else:
        h, fl = fd.get("height_m"), fd.get("floors")
        if h and fl:
            n_fl = max(2, max(int(fl), int(round(h / FLOOR))))
        elif h:
            n_fl = max(2, int(round(h / FLOOR)))
        elif fl:
            n_fl = max(2, int(fl))
        else:
            n_fl = 2
        n_fl = min(n_fl, 60)
    tier = fd.get("interior_tier") or 3
    hero = fd.get("budget_class") == "hero"

    x0, y0, x1, y1 = rect
    cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
    bx = (x0, x1, y0, y1)
    bb = faces4(bx)
    side = entrance_face(rect, segs)
    bd = BD()

    # plinth (ground 0..0.15, slight outset = curb) + interior floor slab
    bd.box(x0 - 0.12, x1 + 0.12, y0 - 0.12, y1 + 0.12, 0.0, CURB, kit["plinth"])
    fmid = kit["int_floor"][0] if cat == "retail" else kit["int_floor"][1]
    bd.box(x0 + 0.85, x1 - 0.85, y0 + 0.85, y1 - 0.85, CURB, CURB + 0.15, fmid)

    # ground storey walls, all four sides
    ztop_g = CURB + FLOOR
    for i, f in enumerate(bb):
        if cat == "retail":
            ground_arcade(bd, f, kit, ztop_g,
                          wt=0.7 if hero else 0.5, bay_t=4.6 if hero else 3.4)
        elif cat == "industrial":
            ground_industrial(bd, f, kit, ztop_g, opening=(i == side))
        else:
            recess = (0.47, 0.18) if (i == side and tier <= 2) else None
            ground_storefront(bd, f, kit, ztop_g, recess=recess, glassless=(tier >= 3))

    # interior tier: furnished hall (t1), one room (t2), dark recess core (t3)
    hall = interior_hall(bd, bx, kit) if tier <= 2 else None
    if tier >= 3:
        core_dark(bd, bx, kit)

    # upper storeys: level slab then walls with glazing bands (all four sides)
    for k in range(1, n_fl):
        sz = CURB + k * FLOOR                       # level slab base (tessellates)
        bd.box(x0 - 0.05, x1 + 0.05, y0 - 0.05, y1 + 0.05, sz, sz + SLAB, kit["slab"])
        zb = sz + SLAB
        for f in bb:
            upper_ring(bd, f, kit, zb, industrial=(cat == "industrial"))

    # roof slab + parapet + coping
    rbase = CURB + n_fl * FLOOR
    bd.box(x0 - 0.05, x1 + 0.05, y0 - 0.05, y1 + 0.05, rbase, rbase + SLAB, kit["roof"])
    for f in bb:
        fbox(bd, f, f["s0"], f["s1"], rbase + SLAB, rbase + SLAB + PARAPET - 0.15,
             kit["wall"][0])
        fbox(bd, f, f["s0"], f["s1"], rbase + SLAB + PARAPET - 0.15,
             rbase + SLAB + PARAPET, kit["coping"], d0=-0.05, d1=0.10)
    height = rbase + SLAB + PARAPET

    # emissive signage on entrance face + blade sign for heroes
    fe = bb[side]
    ri = rng_for("S" + fid)()
    smat = kit["neon"][ri % len(kit["neon"])] if ri % 3 else kit["emis"][ri % 2]
    for (a, b) in sign_splits(fe["s0"], fe["s1"], hero):
        fbox(bd, fe, a, b, CURB + FLOOR - 0.45, CURB + FLOOR - 0.05, smat,
             d0=-0.10, d1=0.0)
    if hero:
        L = fe["s1"] - fe["s0"]
        u = fe["s0"] + L * 0.14
        sz0 = max(rbase + SLAB - 8.0, CURB + 2.55)
        sz1 = max(rbase + SLAB - 2.0, sz0 + 2.4)
        fbox(bd, fe, u, u + min(1.8, L * 0.08), sz0, sz1,
             kit["neon"][(ri + 1) % len(kit["neon"])], d0=-0.55, d1=-0.30)

    me = emit_mesh(name, bd)
    # origin at bottom-centre: bake the footprint centre into the mesh data,
    # keep the object transform a pure translation to (cx, cy)
    me.transform(Matrix.Translation((-cx, -cy, 0.0)))
    me.update()
    ctx.meshes.append((name, me))
    tg = ck.tri_count(me)
    ctx.unique_tris += tg
    new_obj(name, me, (cx, cy, 0.0), ctx.meshes_coll)

    # props (linked duplicates)
    nprops = 0
    if hall is not None:
        nprops = furnish(fid, dict(tier=tier, cat=cat, hall=hall, cx=cx, cy=cy),
                         tail=n_fl + 1)

    # colliders
    cb = BD()
    cb.box(-width * 0.5 + 0.10, width * 0.5 - 0.10, -dep * 0.5 + 0.10,
           dep * 0.5 - 0.10, 0.0, height, kit["slab"])
    cme = emit_mesh("COL_com_%s" % fid, cb)
    cob = new_obj("COL_com_%s" % fid, cme, (cx, cy, 0.0), ctx.colliders_coll)
    cob.hide_render = True
    ctx.collider_n += 1
    ctx.unique_tris += 12

    # point lights (heroes only, <=6 each)
    hero_lights = 0
    if hero:
        dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        dx, dy = dirs[side]
        ex, ey = (x1 if dx > 0 else x0 if dx < 0 else cx), (y1 if dy > 0 else y0 if dy < 0 else cy)
        pts = [
            (ex + dx * 1.2, ey + dy * 1.2, 2.8),
            (cx - width * 0.18, cy - dep * 0.15, 2.8),
            (cx + width * 0.18, cy + dep * 0.15, 2.8),
            (cx - width * 0.22, cy + dep * 0.20, 2.8),
            (cx + width * 0.22, cy - dep * 0.20, 2.8),
            (ex + dx * 2.0, ey + dy * 2.0, 2.4),
        ]
        for i, (px, py, pz) in enumerate(pts[:6]):
            ctx.light_n += 1
            nm = "LT_com_%03d" % ctx.light_n
            ld = bpy.data.lights.new(nm, "POINT")
            ld.energy = 60.0 if i < 2 else 40.0
            ld.shadow_soft_size = 3.5
            ld.color = (1.0, 0.92, 0.80)
            lob = bpy.data.objects.new(nm, ld)
            lob.location = (px, py, pz)
            ctx.lights_coll.objects.link(lob)
            hero_lights += 1

    clear = rect_road_clearance(rect, segs)
    row = dict(name=name, id=fid, label=fd.get("label", ""), district=fd.get("district"),
               mode=(fd.get("placement") or {}).get("mode").strip("`"),
               rect=rect, n_fl=n_fl, height_m=round(height, 2), tier=tier,
               budget=fd.get("budget_class"), tris=tg, prop_instances=nprops,
               lights=hero_lights, side="EWNS"[side],
               road_clear=round(clear, 2), materials=sorted(bd.mats),
               room=ROOM.get(fid, ROOM_DEFAULT.get(cat, "Room")))
    for mn in bd.mats:
        ctx.mats_used.add(mn)
    cap = BUDGET.get(fd.get("budget_class") or "regular", 400000)
    if tg > cap:
        ctx.violations.append((fid, "tris %d over budget %d" % (tg, cap)))
    if clear < 2.5:
        ctx.violations.append((fid, "road clearance %.2f < 2.5 m" % clear))
    ctx.built.append(row)
    return row


def load_program():
    p = os.path.join(ROOT, "reports", "program.json")
    with open(p) as f:
        d = json.load(f)
    return [f for f in d["facilities"] if f.get("owning_module") == "Commercial"]


# ------------------------------------------------------------- verification
def verify():
    ok = True
    print("[commercial] verification...")
    ck.update_view()  # refresh matrix_world of newly placed objects
    ob_by_mesh = {}
    for ob in bpy.data.objects:
        if isinstance(getattr(ob, "data", None), bpy.types.Mesh):
            ob_by_mesh.setdefault(ob.data.name, []).append(ob)
    for (name, me) in ctx.meshes:
        if not name.startswith("SM_"):
            continue
        ob = (ob_by_mesh.get(me.name) or [None])[0]
        if ob is None:
            ctx.violations.append((name, "mesh without object"))
            continue
        row = next((r for r in ctx.built if r.get("name") == name), None)
        if row is None:
            continue
        mw = ob.matrix_world
        vs = [mw @ v.co for v in me.vertices]
        if not vs:
            ctx.violations.append((name, "empty mesh"))
            ok = False
            continue
        zmin, zmax = min(v.z for v in vs), max(v.z for v in vs)
        if not (-0.06 <= zmin <= 0.30):
            ctx.violations.append((name, "zmin %.2f outside grounding band" % zmin))
            ok = False
        x0, y0, x1, y1 = row["rect"]
        probe = max(2.5, (zmax - zmin) * 0.6)
        for planes in (("x", x1, "E"), ("x", x0, "W"), ("y", y1, "N"), ("y", y0, "S")):
            ai = 0 if planes[0] == "x" else 1
            edge, tag = planes[1], planes[2]
            if not any(abs(v[ai] - edge) < 0.45 and CURB < v.z < probe for v in vs):
                ctx.violations.append((name, "no wall on %s face at %.1f" % (tag, edge)))
                ok = False
    rects = [(b["id"], b["rect"]) for b in ctx.built]
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            if rect_overlap(rects[i][1], rects[j][1]):
                ctx.violations.append((rects[i][0], "overlaps %s" % rects[j][0]))
                ok = False
    root = bpy.data.collections.get("Commercial")
    if root is None or {c.name for c in root.children} != {"Meshes", "Colliders", "Lights"}:
        ctx.violations.append(("collections", "Commercial root/children wrong"))
        ok = False
    print("[commercial] verification %s (%d violations)" %
          ("OK" if ok else "FAILED", len(ctx.violations)))
    return ok


# ------------------------------------------------------------------- main
def main():
    print("=== commercial rebuild ===")
    facilities = load_program()
    segs = road_segments()
    root_coll = ck.ensure_collection("Commercial")
    ctx.meshes_coll = ck.ensure_collection("Meshes", parent=root_coll)
    ctx.colliders_coll = ck.ensure_collection("Colliders", parent=root_coll)
    ctx.lights_coll = ck.ensure_collection("Lights", parent=root_coll)

    for fd in sorted(facilities, key=lambda f: f["id"]):
        fid = fd["id"]
        dist = fd.get("district")
        rect = (fd.get("placement") or {}).get("rect")
        if dist == "M":
            ctx.skipped.append(dict(id=fid, reason="district M (market already built)"))
            continue
        if fid == "RET_BAZAAR":
            ctx.skipped.append(dict(id=fid, reason="RET_BAZAAR (market already built)"))
            continue
        if rect and rect_overlap(list(rect), CIRCUIT):
            ctx.skipped.append(dict(id=fid, reason="inside track circuit zone"))
            continue
        try:
            row = build_facility(fd, segs)
            print("  %s: %.1f m, %d fl, tier %d, %d tris, %d props, %d lights" %
                  (fid, row["height_m"], row["n_fl"], row["tier"], row["tris"],
                   row["prop_instances"], row["lights"]))
        except Exception as e:
            ctx.violations.append((fid, "build failed: %s" % e))
            import traceback
            traceback.print_exc()
            print("  FAILED %s: %s" % (fid, e))

    # disallow any object outside our three collections
    ours = {"Meshes", "Colliders", "Lights"}
    for ob in list(bpy.data.objects):
        if ob.users_collection == () or not {c.name for c in ob.users_collection} & ours:
            bpy.data.objects.remove(ob, do_unlink=True)

    if not verify():
        print("[commercial] violations detected (see report)")

    total = ctx.unique_tris + ctx.instanced_tris
    payload = dict(
        module="Commercial",
        built=ctx.built,
        skipped=ctx.skipped,
        violations=[list(v) for v in ctx.violations],
        stats=dict(
            buildings=len(ctx.built),
            skipped=len(ctx.skipped),
            unique_tris=ctx.unique_tris,
            colliders=ctx.collider_n,
            lights=ctx.light_n,
            prop_protos=len(ctx.props),
            prop_proto_tris=dict(ctx.prop_proto_tris),
            prop_instances=ctx.prop_instances,
            instanced_tris=ctx.instanced_tris,
            total_tris=total,
            budget_cap=900000,
            budget_ok=total <= 900000,
            materials_missing=[m for m in WANT if m not in AVAIL],
        ),
        materials=sorted(ctx.mats_used),
        previews=dict(status="pending"),
        notes=[
            "solid box massing: walls on all four sides + floor slabs + roof slab + parapet",
            "ground: retail arcade (no glass, no doors), storefront + recessed lobby, industrial dark bay",
            "tier1 furnished hall, tier2 one room, tier3 dark recess; interiors INT named rooms",
            "no door meshes; origins bottom-centre; translation-only object transforms",
            "materials appended from materials.blend (textures packed, no dead paths)",
        ],
    )
    ck.write_report("commercial", payload)
    md_report()

    ck.save_blend(os.path.join(ROOT, "out", "commercial.blend"))
    print("[commercial] unique tris %d | prop instances %d (+%d tris) | total %d / 900000" %
          (ctx.unique_tris, ctx.prop_instances, ctx.instanced_tris, total))
    print("[commercial] done")


def md_report():
    L = ["# Commercial rebuild report", ""]
    b = {r["id"]: r for r in ctx.built}
    L.append("| Facility | District | Mode | Floors | Height m | Tier | Class | "
             "Tris | Props | Lights |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in ctx.built:
        L.append("| %s | %s | %s | %d | %.1f | %d | %s | %d | %d | %d |" %
                 (r["id"], r["district"], str(r["mode"]), r["n_fl"], r["height_m"],
                  r["tier"], r["budget"] or "-", r["tris"], r["prop_instances"],
                  r["lights"]))
    L.append("")
    L.append("## Skipped (%d)" % len(ctx.skipped))
    for s in ctx.skipped:
        L.append("- %s: %s" % (s["id"], s["reason"]))
    total = ctx.unique_tris + ctx.instanced_tris
    L.extend(["", "## Budgets",
              "- unique tris: %d; prop instances: %d (+%d tris); module total: %d / 900,000"
              % (ctx.unique_tris, ctx.prop_instances, ctx.instanced_tris, total),
              "- hero cap 150,000 tris, regular 40,000, props 5,000: "
              + ("OK" if not ctx.violations else "see violations")])
    L.extend(["", "## Verification",
              "- grounding band [-0.06, 0.30] m for every unique mesh: "
              + ("fail" if any("zmin" in v[1] for v in ctx.violations) else "pass"),
              "- walls present on all 4 faces (E/W/N/S probe): "
              + ("fail" if any("no wall" in v[1] for v in ctx.violations) else "pass"),
              "- no footprint overlaps: "
              + ("fail" if any("overlap" in v[1] for v in ctx.violations) else "pass"),
              "- road clearance >= 2.5 m: "
              + ("fail" if any("clearance" in v[1] for v in ctx.violations) else "pass")])
    L.extend(["", "## Materials (%d, all from /city/materials.blend)" % len(ctx.mats_used)])
    L.append(", ".join("`%s`" % m for m in sorted(ctx.mats_used)))
    L.extend(["", "## Collections", "- Commercial > Meshes, Colliders, Lights",
              "- colliders: %d (COL_com_<id>, hidden from render) ; lights: %d "
              "(LT_com_<nn>, heroes only, <=6 per hero)" % (ctx.collider_n, ctx.light_n)])
    L.extend(["", "## Issues / remaining problems"])
    for v in ctx.violations:
        L.append("- %s: %s" % (v[0], v[1]))
    if not ctx.violations:
        L.append("- none")
    L.extend(["", "(previews written by modules/commercial_previews.py; see "
              "commercial_report.json 'previews' for the verification numbers)"])
    with open(os.path.join(ck.REPORTS_DIR, "commercial_report.md"), "w") as fh:
        fh.write("\n".join(L) + "\n")
    print("[commercial] md report written")


if __name__ == "__main__":
    main()
