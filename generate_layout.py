#!/usr/bin/env python3
"""
generate_layout.py  --  deterministic city layout generator (Agent 0 helper)

Produces layout.json for the 3x3 km Blender city:
  districts, road graph, flyovers, traffic lights, parcels (with interior tiers
  and door-less openings), parks, lake, race track, landmarks, stats.

Usage:
  python generate_layout.py                      # writes ./layout.json
  python generate_layout.py --out /city/layout.json --seed 1337
  python generate_layout.py --split              # also writes parcels_<district>.json

Coordinates: metres, Z-up, origin at map centre. X = east, Y = north.
Same seed -> byte-identical output.
"""
import argparse
import json
import math
import os
import random
import sys
from collections import Counter, defaultdict

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------
CELL = 300.0                 # block cell pitch (arterial centre to arterial centre)
NCELL = 8                    # 8 x 8 cells => 2400 x 2400 m inner city
ORIGIN = -1200.0             # inner city min corner (x and y)
RING = 1400.0                # highway ring half-extent
ARTERIAL_W = 24.0
STREET_W = 12.0
ALLEY_W = 5.0
HIGHWAY_W = 34.0
USABLE = CELL - ARTERIAL_W   # 276 m usable inside each cell

# Row 0 = northernmost cell row (cy = 7); column 0 = westernmost (cx = 0)
# R residential, D downtown, E entertainment, M market, G green, I industrial, T race track
GRID = [
    "RRRRGMMM",  # cy 7
    "RRRREMMM",  # cy 6
    "RRRDDDER",  # cy 5
    "RREDDDER",  # cy 4
    "RRREDETT",  # cy 3
    "GGREEITT",  # cy 2
    "GGGGGITT",  # cy 1
    "GGGGGITT",  # cy 0
]

DISTRICT_NAMES = {
    "R": "Residential", "D": "Downtown core", "E": "Entertainment strip",
    "M": "Market quarter", "G": "Green belt", "I": "Industrial", "T": "Race circuit",
}

FACADE_STYLES = {
    "R": ["suburban_brick", "stucco_modern", "timber_cottage", "modern_minimal"],
    "D": ["glass_curtain", "steel_stone", "art_deco", "brutalist_modern"],
    "E": ["neon_modern", "brick_loft", "glass_retail"],
    "M": ["old_bazaar_brick", "painted_plaster", "timber_balcony"],
    "I": ["corrugated_metal", "concrete_block"],
    "T": ["motorsport_modern"],
}

# building-type tables: (type, weight)
TYPES = {
    "R": [("house", 62), ("house_large", 16), ("apartment_low", 18), ("corner_shop", 4)],
    "D": [("office_tower", 56), ("hotel", 12), ("apartment_tower", 10), ("mall", 5),
          ("civic", 4), ("bank", 13)],
    "E": [("restaurant", 26), ("shop", 22), ("cafe", 14), ("gym", 11), ("hotel", 8),
          ("club", 5), ("supermarket", 5), ("cinema", 3), ("apartment_low", 6)],
    "M": [("shop", 40), ("restaurant", 12), ("teahouse", 8), ("workshop", 9),
          ("house_above_shop", 31)],
    "I": [("warehouse", 60), ("factory", 20), ("depot", 8), ("yard", 12)],
}

FLOORS = {
    "house": (1, 2), "house_large": (2, 3), "apartment_low": (3, 5), "corner_shop": (1, 2),
    "office_tower": (12, 45), "hotel": (10, 25), "apartment_tower": (12, 30), "mall": (3, 5),
    "civic": (3, 6), "bank": (4, 8),
    "restaurant": (1, 2), "shop": (1, 3), "cafe": (1, 2), "gym": (1, 3), "club": (2, 3),
    "supermarket": (1, 2), "cinema": (2, 4), "teahouse": (2, 3), "workshop": (1, 2),
    "house_above_shop": (2, 4), "warehouse": (1, 2), "factory": (1, 3), "depot": (1, 2),
    "yard": (0, 0),
}
FLOORS_HOTEL_E = (6, 14)

PUBLIC = {"office_tower", "hotel", "mall", "civic", "bank", "restaurant", "shop", "cafe",
          "gym", "club", "supermarket", "cinema", "teahouse", "workshop", "corner_shop",
          "warehouse", "factory", "depot"}

# probability that a PUBLIC type is enterable (gets a real interior) in a district
ENTER_PROB = {
    "D": {"*": 1.0},
    "E": {"shop": 0.35, "cafe": 0.5, "restaurant": 0.8, "club": 0.8, "*": 1.0},
    "M": {"shop": 0.15, "workshop": 0.1, "restaurant": 0.6, "teahouse": 0.5, "*": 1.0},
    "R": {"corner_shop": 1.0, "*": 1.0},
    "I": {"warehouse": 0.4, "factory": 0.5, "depot": 0.4, "*": 0.0},
}
HOME_ENTER_PROB = {"house": 0.08, "house_large": 0.12, "apartment_low": 0.05}

# hero (tier 1) quotas: (district, type) -> count
TIER1_QUOTAS = {
    ("D", "office_tower"): 5, ("D", "hotel"): 3, ("D", "civic"): 1, ("D", "mall"): 1,
    ("E", "gym"): 4, ("E", "restaurant"): 5, ("E", "hotel"): 2, ("E", "cinema"): 1,
    ("E", "shop"): 3,
    ("M", "restaurant"): 3, ("M", "shop"): 3,
    ("R", "house"): 5, ("R", "apartment_low"): 1,
}

OPENINGS = {   # type -> (opening_type, width, height)
    "office_tower": ("open_atrium_lobby", 12.0, 6.0), "hotel": ("open_atrium_lobby", 12.0, 6.0),
    "mall": ("open_atrium_lobby", 16.0, 6.5), "civic": ("open_atrium_lobby", 14.0, 7.0),
    "bank": ("open_atrium_lobby", 8.0, 4.5), "cinema": ("open_atrium_lobby", 10.0, 5.0),
    "apartment_tower": ("archway", 5.0, 4.0),
    "restaurant": ("open_frontage", 8.0, 3.4), "cafe": ("open_frontage", 6.0, 3.2),
    "shop": ("open_frontage", 6.0, 3.2), "club": ("open_frontage", 6.0, 3.4),
    "supermarket": ("open_frontage", 10.0, 3.6), "gym": ("open_frontage", 8.0, 3.5),
    "teahouse": ("open_frontage", 4.0, 3.0), "workshop": ("open_frontage", 4.0, 3.0),
    "corner_shop": ("open_frontage", 4.5, 3.0),
    "warehouse": ("open_bay", 8.0, 5.0), "factory": ("open_bay", 8.0, 5.0),
    "depot": ("open_bay", 8.0, 5.0),
    "house": ("open_porch", 3.5, 2.6), "house_large": ("open_porch", 4.5, 2.8),
    "apartment_low": ("archway", 4.0, 3.2), "house_above_shop": ("open_frontage", 3.5, 3.0),
}

SETBACK = {"R": 3.0, "D": 4.0, "E": 2.0, "M": 0.5, "I": 6.0}

SIDE_VEC = {"N": (0, 1), "S": (0, -1), "E": (1, 0), "W": (-1, 0)}

# normalised (u, v) control points of the circuit inside the track zone, closed loop
TRACK_UV = [
    (0.15, 0.10), (0.15, 0.30), (0.15, 0.55), (0.15, 0.80),
    (0.20, 0.92), (0.40, 0.95), (0.60, 0.90),
    (0.75, 0.82), (0.88, 0.88), (0.92, 0.75),
    (0.80, 0.65), (0.62, 0.68), (0.52, 0.58),
    (0.60, 0.48), (0.82, 0.45), (0.90, 0.32),
    (0.80, 0.18), (0.60, 0.22), (0.45, 0.32), (0.35, 0.22), (0.40, 0.08), (0.25, 0.05),
]


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------
def r2(v):
    return round(float(v), 2)


def rect_inset(r, d):
    return [r2(r[0] + d), r2(r[1] + d), r2(r[2] - d), r2(r[3] - d)]


def rect_center(r):
    return [r2((r[0] + r[2]) / 2), r2((r[1] + r[3]) / 2)]


def rect_area(r):
    return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])


def rect_overlap(a, b, eps=0.01):
    return a[0] < b[2] - eps and b[0] < a[2] - eps and a[1] < b[3] - eps and b[1] < a[3] - eps


def cell_district(cx, cy):
    if 0 <= cx < NCELL and 0 <= cy < NCELL:
        return GRID[NCELL - 1 - cy][cx]
    return None


def cell_origin(cx, cy):
    return ORIGIN + CELL * cx, ORIGIN + CELL * cy


def cell_usable(cx, cy):
    x0, y0 = cell_origin(cx, cy)
    h = ARTERIAL_W / 2
    return [x0 + h, y0 + h, x0 + CELL - h, y0 + CELL - h]


def wchoice(rng, table):
    total = sum(w for _, w in table)
    t = rng.uniform(0, total)
    acc = 0.0
    for item, w in table:
        acc += w
        if t <= acc:
            return item
    return table[-1][0]


def dist_pt_seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def dist_pt_rect(px, py, r):
    dx = max(r[0] - px, 0, px - r[2])
    dy = max(r[1] - py, 0, py - r[3])
    return math.hypot(dx, dy)


def seg_intersect(p1, p2, p3, p4):
    def ccw(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])
    return ccw(p1, p3, p4) != ccw(p2, p3, p4) and ccw(p1, p2, p3) != ccw(p1, p2, p4)


# ----------------------------------------------------------------------------
# Road graph
# ----------------------------------------------------------------------------
class RoadGraph:
    def __init__(self):
        self.nodes = {}
        self.edges = []

    def node(self, nid, x, y, kind, z=0.0):
        if nid not in self.nodes:
            self.nodes[nid] = {"id": nid, "pos": [r2(x), r2(y), r2(z)], "kind": kind}
        return nid

    def edge(self, eid, a, b, hierarchy, lanes_each_way, width, **extra):
        pa, pb = self.nodes[a]["pos"], self.nodes[b]["pos"]
        length = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
        e = {"id": eid, "a": a, "b": b, "hierarchy": hierarchy,
             "lanes_each_way": lanes_each_way, "width": width, "length": r2(length)}
        e.update(extra)
        self.edges.append(e)
        return e

    def degree(self):
        d = Counter()
        for e in self.edges:
            d[e["a"]] += 1
            d[e["b"]] += 1
        return d


def art_id(i, j):
    return "N_%d_%d" % (i, j)


def build_roads():
    g = RoadGraph()
    lines = [ORIGIN + CELL * k for k in range(NCELL + 1)]

    # --- arterial grid (skip segments buried inside the race-track zone)
    for j in range(NCELL + 1):          # horizontal lines
        for i in range(NCELL):
            below = cell_district(i, j - 1)
            above = cell_district(i, j)
            if below == "T" and above == "T":
                continue
            for (ii, jj) in ((i, j), (i + 1, j)):
                g.node(art_id(ii, jj), lines[ii], lines[jj], "arterial_intersection")
            g.edge("A_H_%d_%d" % (i, j), art_id(i, j), art_id(i + 1, j), "arterial", 2, ARTERIAL_W,
                   median=3.0, sidewalk=2.5, elevated=False)
    for i in range(NCELL + 1):          # vertical lines
        for j in range(NCELL):
            left = cell_district(i - 1, j)
            right = cell_district(i, j)
            if left == "T" and right == "T":
                continue
            for (ii, jj) in ((i, j), (i, j + 1)):
                g.node(art_id(ii, jj), lines[ii], lines[jj], "arterial_intersection")
            g.edge("A_V_%d_%d" % (i, j), art_id(i, j), art_id(i, j + 1), "arterial", 2, ARTERIAL_W,
                   median=3.0, sidewalk=2.5, elevated=False)

    # --- local streets and alleys per cell
    for cy in range(NCELL):
        for cx in range(NCELL):
            d = cell_district(cx, cy)
            x0, y0 = cell_origin(cx, cy)
            x1, y1 = x0 + CELL, y0 + CELL
            if d in ("R", "D", "E", "I"):
                xm, ym = x0 + CELL / 2, y0 + CELL / 2
                c = g.node("C_%d_%d" % (cx, cy), xm, ym, "street_crossing")
                jw = g.node("J_%g_%g" % (x0, ym), x0, ym, "t_junction")
                je = g.node("J_%g_%g" % (x1, ym), x1, ym, "t_junction")
                js = g.node("J_%g_%g" % (xm, y0), xm, y0, "t_junction")
                jn = g.node("J_%g_%g" % (xm, y1), xm, y1, "t_junction")
                for tag, (a, b) in (("W", (jw, c)), ("E", (c, je)), ("S", (js, c)), ("N", (c, jn))):
                    g.edge("S_%d_%d_%s" % (cx, cy, tag), a, b, "street", 1, STREET_W,
                           sidewalk=2.0, district=d, elevated=False)
            elif d == "M":
                s = (USABLE - 3 * ALLEY_W) / 4.0
                ux0, uy0 = x0 + ARTERIAL_W / 2, y0 + ARTERIAL_W / 2
                offs = [(k + 1) * s + k * ALLEY_W + ALLEY_W / 2 for k in range(3)]
                xs = [ux0 + o for o in offs]
                ys = [uy0 + o for o in offs]
                for k, ax in enumerate(xs):          # N-S alleys
                    chain = [g.node("J_%g_%g" % (ax, y0), ax, y0, "t_junction")]
                    for l, ay in enumerate(ys):
                        chain.append(g.node("A_%d_%d_%d_%d" % (cx, cy, k, l), ax, ay, "alley_crossing"))
                    chain.append(g.node("J_%g_%g" % (ax, y1), ax, y1, "t_junction"))
                    for n in range(len(chain) - 1):
                        g.edge("L_%d_%d_V%d_%d" % (cx, cy, k, n), chain[n], chain[n + 1], "alley", 1,
                               ALLEY_W, pedestrian_first=True, district="M", elevated=False)
                for l, ay in enumerate(ys):          # E-W alleys
                    chain = [g.node("J_%g_%g" % (x0, ay), x0, ay, "t_junction")]
                    for k, ax in enumerate(xs):
                        chain.append(g.node("A_%d_%d_%d_%d" % (cx, cy, k, l), ax, ay, "alley_crossing"))
                    chain.append(g.node("J_%g_%g" % (x1, ay), x1, ay, "t_junction"))
                    for n in range(len(chain) - 1):
                        g.edge("L_%d_%d_H%d_%d" % (cx, cy, l, n), chain[n], chain[n + 1], "alley", 1,
                               ALLEY_W, pedestrian_first=True, district="M", elevated=False)

    # --- highway ring (elevated) + interchange ramps
    side_pos = [-RING, -600.0, 0.0, 600.0, RING]
    ring_seq = []
    ring_seq += [(x, -RING) for x in side_pos]
    ring_seq += [(RING, y) for y in side_pos[1:]]
    ring_seq += [(x, RING) for x in reversed(side_pos[:-1])]
    ring_seq += [(-RING, y) for y in reversed(side_pos[1:-1])]
    ring_ids = []
    for (x, y) in ring_seq:
        nid = "R_%g_%g" % (x, y)
        kind = "ring_corner" if abs(x) == RING and abs(y) == RING else "ring_interchange"
        g.node(nid, x, y, kind, z=8.0)
        ring_ids.append(nid)
    for n in range(len(ring_ids)):
        a, b = ring_ids[n], ring_ids[(n + 1) % len(ring_ids)]
        g.edge("H_%02d" % n, a, b, "highway", 3, HIGHWAY_W, median=4.0, elevated=True,
               deck_z=8.0, shoulder=2.5)
    ramp_ids = []
    for c in (-600.0, 0.0, 600.0):
        jc = int(round((c - ORIGIN) / CELL))
        pairs = [
            ("R_%g_%g" % (RING, c), art_id(NCELL, jc), "E"),
            ("R_%g_%g" % (-RING, c), art_id(0, jc), "W"),
            ("R_%g_%g" % (c, RING), art_id(jc, NCELL), "N"),
            ("R_%g_%g" % (c, -RING), art_id(jc, 0), "S"),
        ]
        for ra, ar, side in pairs:
            eid = "X_%s_%g" % (side, c)
            g.edge(eid, ra, ar, "interchange_ramp", 2, 18.0, elevated=True, z_start=8.0, z_end=0.0,
                   gradient_pct=r2(8.0 / 200.0 * 100))
            ramp_ids.append(eid)
    return g, ring_ids, ramp_ids


def build_flyovers(g, ring_ids, ramp_ids):
    fl = [
        {"id": "FLY_RING", "type": "highway_ring", "deck_width": 34.0, "deck_z": 8.0,
         "edges": ["H_%02d" % n for n in range(len(ring_ids))], "pillar_spacing": 35.0,
         "barrier": "concrete_jersey", "corner_radius": 120.0},
        {"id": "FLY_RAMPS", "type": "interchange_ramps", "edges": ramp_ids, "deck_width": 18.0,
         "max_gradient_pct": 4.0, "pillar_spacing": 28.0},
        {"id": "FLY_DT_EW", "type": "downtown_overpass", "deck_width": 16.0, "level": 1,
         "path": [[-600, 0, 0], [-480, 0, 7], [480, 0, 7], [600, 0, 0]],
         "max_gradient_pct": r2(7.0 / 120.0 * 100), "pillar_spacing": 30.0,
         "runs_over": "arterial y=0 (ground arterial continues underneath)"},
        {"id": "FLY_DT_NS", "type": "downtown_overpass", "deck_width": 16.0, "level": 2,
         "path": [[0, -600, 0], [0, -345, 14], [0, 345, 14], [0, 600, 0]],
         "max_gradient_pct": r2(14.0 / 255.0 * 100), "pillar_spacing": 30.0,
         "runs_over": "arterial x=0 (ground arterial continues underneath)"},
    ]
    stack = {"id": "STACK_DOWNTOWN", "type": "stack_interchange", "position": [0, 0],
             "levels": {"ground": 0.0, "level_1_deck_z": 7.0, "level_2_deck_z": 14.0},
             "note": "FLY_DT_EW crosses under FLY_DT_NS at the origin; keep 5.5 m+ clearance"}
    return fl, stack


def build_traffic_lights(g):
    deg = g.degree()
    lights = []
    for nid, n in sorted(g.nodes.items()):
        k = n["kind"]
        if k == "arterial_intersection" and deg[nid] >= 3:
            lights.append({"id": "TL_" + nid, "node": nid, "pos": n["pos"][:2], "approaches": deg[nid],
                           "kind": "arterial_signal", "pedestrian_signals": True, "cycle_s": 90})
        elif k == "t_junction" and deg[nid] >= 2:
            # junctions on D/E streets get a signal where they meet the arterial
            pass
    # signals at D / E street junctions
    for e in g.edges:
        if e["hierarchy"] == "street" and e.get("district") in ("D", "E"):
            for end in (e["a"], e["b"]):
                n = g.nodes[end]
                if n["kind"] == "t_junction" and "TL_" + end not in {l["id"] for l in lights}:
                    lights.append({"id": "TL_" + end, "node": end, "pos": n["pos"][:2],
                                   "approaches": max(3, deg[end]), "kind": "junction_signal",
                                   "pedestrian_signals": True, "cycle_s": 75})
    return lights


# ----------------------------------------------------------------------------
# Parcels
# ----------------------------------------------------------------------------
def split_subblocks(cx, cy, n, street_w):
    u = cell_usable(cx, cy)
    s = (USABLE - (n - 1) * street_w) / n
    out = []
    for sy in range(n):
        for sx in range(n):
            x0 = u[0] + sx * (s + street_w)
            y0 = u[1] + sy * (s + street_w)
            out.append(((sx, sy), [x0, y0, x0 + s, y0 + s]))
    return out


def make_parcel(pid, d, cell, ptype, rect, sides, rng, extra=None):
    rect = [r2(v) for v in rect]
    w, dd = rect[2] - rect[0], rect[3] - rect[1]
    lo, hi = FLOORS.get(ptype, (1, 1))
    if ptype == "hotel" and d == "E":
        lo, hi = FLOORS_HOTEL_E
    floors = rng.randint(lo, hi) if hi > 0 else 0
    p = {
        "id": pid, "district": d, "cell": list(cell), "type": ptype, "rect": rect,
        "center": rect_center(rect), "size": [r2(w), r2(dd)],
        "buildable_rect": rect_inset(rect, SETBACK.get(d, 0.0)) if ptype != "yard" else rect,
        "floors": floors, "height_m": r2(floors * (3.0 if ptype in ("house", "house_large") else 3.2)),
        "frontage": sides, "facade_style": rng.choice(FACADE_STYLES.get(d, ["generic"])),
        "enterable": False, "interior_tier": 3, "door_mesh": False, "opening": None,
        "interior_anchor": None,
    }
    if extra:
        p.update(extra)
    return p


def lot_grid(rect, nx, ny):
    w = (rect[2] - rect[0]) / nx
    h = (rect[3] - rect[1]) / ny
    for iy in range(ny):
        for ix in range(nx):
            r = [rect[0] + ix * w, rect[1] + iy * h, rect[0] + (ix + 1) * w, rect[1] + (iy + 1) * h]
            sides = []
            if iy == 0:
                sides.append("S")
            if iy == ny - 1:
                sides.append("N")
            if ix == 0:
                sides.append("W")
            if ix == nx - 1:
                sides.append("E")
            yield ix, iy, r, sides


def build_parcels(rng):
    parcels = []
    parks = []
    water = []
    landmarks = []

    def add_courtyard(pid, d, cell, rect, kind):
        parcels.append({
            "id": pid, "district": d, "cell": list(cell), "type": "courtyard", "subtype": kind,
            "rect": [r2(v) for v in rect], "center": rect_center(rect),
            "size": [r2(rect[2] - rect[0]), r2(rect[3] - rect[1])], "floors": 0, "height_m": 0.0,
            "frontage": [], "enterable": False, "interior_tier": 0, "door_mesh": False,
            "opening": None, "interior_anchor": None, "public_open_air": True,
        })

    park_features_pool = ["jogging_path", "benches", "playground", "picnic_area", "sports_field",
                          "fountain", "pavilion_cafe", "outdoor_gym", "pond", "flower_beds",
                          "amphitheatre", "skate_area"]

    for cy in range(NCELL):
        for cx in range(NCELL):
            d = cell_district(cx, cy)
            tag = "%d_%d" % (cx, cy)
            if d == "G":
                u = cell_usable(cx, cy)
                feats = rng.sample(park_features_pool, 5)
                feats = sorted(set(feats + ["jogging_path", "benches"]))
                name = "park_%s" % tag
                extra = {"features": feats, "tree_density": "high", "public_open_air": True}
                if (cx, cy) == (2, 1):
                    name = "central_park"
                    extra["features"] = ["jogging_path", "benches", "playground", "picnic_area",
                                         "sports_field", "fountain", "pavilion_cafe", "amphitheatre",
                                         "outdoor_gym", "flower_beds"]
                    landmarks.append({"id": "LM_CENTRAL_PARK", "type": "central_park",
                                      "pos": rect_center(u), "parcel": "PK_" + tag})
                p = {"id": "PK_" + tag, "district": "G", "cell": [cx, cy], "type": "park",
                     "name": name, "rect": [r2(v) for v in u], "center": rect_center(u),
                     "size": [r2(u[2] - u[0]), r2(u[3] - u[1])], "floors": 0, "height_m": 0.0,
                     "frontage": ["N", "S", "E", "W"], "enterable": False, "interior_tier": 0,
                     "door_mesh": False, "opening": None, "interior_anchor": None}
                p.update(extra)
                parcels.append(p)
                parks.append({"parcel": p["id"], "name": name, "features": p["features"]})
                if (cx, cy) == (2, 0):
                    c = rect_center(u)
                    pts = []
                    for k in range(24):
                        a = 2 * math.pi * k / 24
                        rr = 105 + 14 * math.sin(3 * a + 0.7)
                        pts.append([r2(c[0] + rr * math.cos(a)), r2(c[1] + 0.8 * rr * math.sin(a))])
                    water.append({"id": "LAKE_1", "type": "lake", "polygon": pts, "depth_m": 3.0,
                                  "shore": "gentle", "bridge_suggested": True, "parent_park": p["id"]})
                    p["features"] = sorted(set(p["features"] + ["lake", "boardwalk", "bridge"]))
                    landmarks.append({"id": "LM_LAKE", "type": "lake", "pos": c, "parcel": p["id"]})
                continue

            if d == "T":
                continue  # handled by track builder

            if d in ("R", "D", "E", "I"):
                n, sw = 2, STREET_W
            else:  # M
                n, sw = 4, ALLEY_W

            for (sx, sy), sb in split_subblocks(cx, cy, n, sw):
                sbid = "%s_%d_%d" % (tag, sx, sy)

                # ---- special sub-blocks
                if d == "R" and rng.random() < 0.12:
                    pid = "PK_" + sbid
                    p = {"id": pid, "district": "R", "cell": [cx, cy], "type": "pocket_park",
                         "rect": [r2(v) for v in sb], "center": rect_center(sb),
                         "size": [r2(sb[2] - sb[0]), r2(sb[3] - sb[1])], "floors": 0, "height_m": 0.0,
                         "frontage": ["N", "S", "E", "W"], "enterable": False, "interior_tier": 0,
                         "door_mesh": False, "opening": None, "interior_anchor": None,
                         "features": ["benches", "playground", "flower_beds", "small_pavilion"],
                         "public_open_air": True, "tree_density": "medium"}
                    parcels.append(p)
                    parks.append({"parcel": pid, "name": pid, "features": p["features"]})
                    continue
                if d == "D" and (cx, cy) == (4, 4) and (sx, sy) == (0, 0):
                    pid = "PZ_" + sbid
                    p = {"id": pid, "district": "D", "cell": [cx, cy], "type": "central_plaza",
                         "rect": [r2(v) for v in sb], "center": rect_center(sb),
                         "size": [r2(sb[2] - sb[0]), r2(sb[3] - sb[1])], "floors": 0, "height_m": 0.0,
                         "frontage": ["N", "S", "E", "W"], "enterable": False, "interior_tier": 0,
                         "door_mesh": False, "opening": None, "interior_anchor": None,
                         "features": ["fountain", "seating", "trees_in_grates", "event_stage",
                                      "kiosks"], "public_open_air": True}
                    parcels.append(p)
                    parks.append({"parcel": pid, "name": "central_plaza", "features": p["features"]})
                    landmarks.append({"id": "LM_CENTRAL_PLAZA", "type": "plaza", "pos": p["center"],
                                      "parcel": pid})
                    continue
                if d == "M" and (cx, cy) == (6, 6) and (sx, sy) == (1, 1):
                    pid = "BZ_" + sbid
                    p = {"id": pid, "district": "M", "cell": [cx, cy], "type": "covered_bazaar_hall",
                         "rect": [r2(v) for v in sb], "center": rect_center(sb),
                         "size": [r2(sb[2] - sb[0]), r2(sb[3] - sb[1])], "floors": 2, "height_m": 12.0,
                         "frontage": ["N", "S", "E", "W"], "enterable": True, "interior_tier": 1,
                         "door_mesh": False,
                         "opening": {"type": "open_arcade", "side": "S", "width": 10.0, "height": 5.0,
                                     "sides_open": ["N", "S", "E", "W"]},
                         "interior_anchor": "INT_ANCHOR_" + pid, "facade_style": "old_bazaar_brick",
                         "anchor_pos": [p_center for p_center in rect_center(sb)]}
                    parcels.append(p)
                    landmarks.append({"id": "LM_BAZAAR", "type": "covered_bazaar", "pos": p["center"],
                                      "parcel": pid})
                    continue

                # ---- regular sub-block
                if d == "R":
                    nx = ny = 4
                elif d == "D":
                    nx = ny = 2
                elif d == "E":
                    nx = ny = 3
                elif d == "M":
                    nx = ny = 4
                else:  # I
                    nx = ny = 2

                for ix, iy, r, sides in lot_grid(sb, nx, ny):
                    interior_lot = (nx > 2 and ny > 2 and 0 < ix < nx - 1 and 0 < iy < ny - 1)
                    if interior_lot:
                        continue  # merged into one courtyard below
                    pid = "B_%s_%d_%d" % (sbid, ix, iy)
                    ptype = wchoice(rng, TYPES[d])
                    # corner shops only on corner lots in R
                    if d == "R" and ptype == "corner_shop" and len(sides) < 2:
                        ptype = "house"
                    parcels.append(make_parcel(pid, d, (cx, cy), ptype, r, sides, rng))

                if nx > 2 and ny > 2:
                    w = (sb[2] - sb[0]) / nx
                    h = (sb[3] - sb[1]) / ny
                    cr = [sb[0] + w, sb[1] + h, sb[2] - w, sb[3] - h]
                    kind = {"R": "backyard_garden", "E": "plaza_dining", "M": "covered_courtyard"}.get(d, "yard")
                    add_courtyard("CY_" + sbid, d, (cx, cy), cr, kind)

    return parcels, parks, water, landmarks


def assign_interiors(parcels, rng):
    # 1) enterable flags + tier 2/3
    for p in parcels:
        t, d = p["type"], p["district"]
        if t in ("courtyard", "park", "pocket_park", "central_plaza", "covered_bazaar_hall"):
            continue
        enter = False
        tier = 3
        if t in PUBLIC:
            probs = ENTER_PROB.get(d, {"*": 1.0})
            pr = probs.get(t, probs.get("*", 0.0))
            enter = rng.random() < pr
        elif t in HOME_ENTER_PROB:
            enter = rng.random() < HOME_ENTER_PROB[t]
        elif t == "apartment_tower":
            enter = rng.random() < 0.5
        if enter:
            tier = 2
        p["enterable"] = enter
        p["interior_tier"] = tier if enter else 3

    # 2) hero (tier 1) quotas
    pool = defaultdict(list)
    for p in parcels:
        if p["enterable"] and p["interior_tier"] == 2:
            pool[(p["district"], p["type"])].append(p)
    for key, count in TIER1_QUOTAS.items():
        cand = sorted(pool.get(key, []), key=lambda q: q["id"])
        rng.shuffle(cand)
        for p in cand[:count]:
            p["interior_tier"] = 1

    # 3) openings + anchors
    for p in parcels:
        if not p["enterable"] or p.get("opening") is not None:
            continue
        side = p["frontage"][0] if p["frontage"] else "S"
        otype, ow, oh = OPENINGS.get(p["type"], ("open_frontage", 4.0, 3.0))
        ow = min(ow, p["size"][0] * 0.8 if side in ("N", "S") else p["size"][1] * 0.8)
        p["opening"] = {"type": otype, "side": side, "width": r2(ow), "height": r2(oh)}
        x0, y0, x1, y1 = p["rect"]
        cxm, cym = p["center"]
        pos = {"S": [cxm, y0], "N": [cxm, y1], "W": [x0, cym], "E": [x1, cym]}[side]
        p["interior_anchor"] = "INT_ANCHOR_" + p["id"]
        p["anchor_pos"] = [r2(pos[0]), r2(pos[1])]
    # bazaar hall anchor
    for p in parcels:
        if p["type"] == "covered_bazaar_hall":
            p["anchor_pos"] = p["center"]


# ----------------------------------------------------------------------------
# Landmarks on D parcels
# ----------------------------------------------------------------------------
def pick_landmark_tower(parcels, landmarks):
    best, bd = None, 1e18
    for p in parcels:
        if p["district"] == "D" and p["type"] == "office_tower":
            dd = math.hypot(*p["center"])
            if dd < bd:
                best, bd = p, dd
    if best:
        best["floors"] = 60
        best["height_m"] = r2(60 * 3.2)
        best["landmark"] = True
        best["interior_tier"] = 1
        best["enterable"] = True
        if not best.get("opening"):
            side = best["frontage"][0] if best["frontage"] else "S"
            best["opening"] = {"type": "open_atrium_lobby", "side": side, "width": 14.0, "height": 7.0}
            x0, y0, x1, y1 = best["rect"]
            cxm, cym = best["center"]
            best["interior_anchor"] = "INT_ANCHOR_" + best["id"]
            best["anchor_pos"] = [r2(v) for v in {"S": [cxm, y0], "N": [cxm, y1],
                                                  "W": [x0, cym], "E": [x1, cym]}[side]]
        landmarks.append({"id": "LM_LANDMARK_TOWER", "type": "tower", "pos": best["center"],
                          "parcel": best["id"], "floors": 60})


# ----------------------------------------------------------------------------
# Race track
# ----------------------------------------------------------------------------
def catmull_closed(pts, per_seg=24):
    n = len(pts)
    out = []
    for i in range(n):
        p0, p1, p2, p3 = pts[(i - 1) % n], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        for s in range(per_seg):
            t = s / per_seg
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    return out


def build_track(rng):
    # zone = union of T cells inset by half arterial width
    tcells = [(cx, cy) for cy in range(NCELL) for cx in range(NCELL) if cell_district(cx, cy) == "T"]
    xs0 = min(cell_origin(cx, cy)[0] for cx, cy in tcells) + ARTERIAL_W / 2
    ys0 = min(cell_origin(cx, cy)[1] for cx, cy in tcells) + ARTERIAL_W / 2
    xs1 = max(cell_origin(cx, cy)[0] for cx, cy in tcells) + CELL - ARTERIAL_W / 2
    ys1 = max(cell_origin(cx, cy)[1] for cx, cy in tcells) + CELL - ARTERIAL_W / 2
    zone = [xs0, ys0, xs1, ys1]
    W, H = xs1 - xs0, ys1 - ys0
    ctrl = [(xs0 + u * W, ys0 + v * H) for u, v in TRACK_UV]
    centerline = catmull_closed(ctrl)
    length = sum(math.hypot(centerline[(i + 1) % len(centerline)][0] - centerline[i][0],
                            centerline[(i + 1) % len(centerline)][1] - centerline[i][1])
                 for i in range(len(centerline)))
    xstraight = xs0 + TRACK_UV[0][0] * W
    y_a = ys0 + 0.25 * H
    y_b = ys0 + 0.75 * H

    structures = [
        ("TRK_PIT_BUILDING", "pit_building", [xstraight + 40, y_a, xstraight + 70, y_b], ["W"], 2, True, 2),
        ("TRK_GRANDSTAND_MAIN", "grandstand", [xstraight - 62, ys0 + 0.28 * H, xstraight - 36, ys0 + 0.65 * H], ["E"], 4, False, 3),
        ("TRK_CONTROL_TOWER", "control_tower", [xstraight + 74, ys0 + 0.47 * H, xstraight + 90, ys0 + 0.47 * H + 16], ["W"], 5, True, 2),
        ("TRK_PADDOCK", "paddock", [xstraight + 74, ys0 + 0.40 * H, xstraight + 120, ys0 + 0.40 * H + 70], ["W"], 1, True, 2),
        ("TRK_PARKING_A", "parking_lot", [xs1 - 100, ys1 - 70, xs1 - 12, ys1 - 12], ["S"], 0, False, 3),
        ("TRK_PARKING_B", "parking_lot", [xs1 - 120, ys0 + 8, xs1 - 8, ys0 + 90], ["N"], 0, False, 3),
        ("TRK_HAIRPIN_STAND", "grandstand", [xs0 + 0.93 * W + 22, ys0 + 0.70 * H, xs0 + 0.93 * W + 40, ys0 + 0.80 * H], ["W"], 3, False, 3),
    ]
    parcels = []
    for pid, ptype, rect, sides, floors, enter, tier in structures:
        rect = [r2(v) for v in rect]
        p = {"id": pid, "district": "T", "cell": [], "type": ptype, "rect": rect,
             "center": rect_center(rect), "size": [r2(rect[2] - rect[0]), r2(rect[3] - rect[1])],
             "floors": floors, "height_m": r2(floors * 3.2), "frontage": sides,
             "facade_style": "motorsport_modern", "enterable": enter, "interior_tier": tier if enter else 3,
             "door_mesh": False, "opening": None, "interior_anchor": None}
        if enter:
            p["opening"] = {"type": "open_frontage" if ptype != "pit_building" else "open_bay_row",
                            "side": sides[0], "width": r2(min(20, p["size"][1] * 0.8)), "height": 4.0}
            p["interior_anchor"] = "INT_ANCHOR_" + pid
            p["anchor_pos"] = p["center"]
        parcels.append(p)

    track = {
        "id": "TRACK_1", "zone_rect": [r2(v) for v in zone], "control_points": [[r2(x), r2(y)] for x, y in ctrl],
        "spline": "catmull_rom_closed", "centerline_sample": [[r2(x), r2(y)] for x, y in centerline[::6]],
        "length_m": r2(length), "width_m": 14.0, "kerb_width_m": 1.2, "runoff_width_m": 15.0,
        "barrier": "tyre_wall_and_catch_fence", "direction": "counter_clockwise_start_on_west_straight",
        "start_finish": {"pos": [r2(xstraight), r2(ys0 + 0.40 * H)], "heading": "north", "gantry": True},
        "pit_lane": {"x": r2(xstraight + 24), "y_from": r2(y_a), "y_to": r2(y_b), "width_m": 12.0,
                     "garages": 14, "garage_front": "open_bay_no_door"},
        "structures": [s[0] for s in structures],
        "surface": "asphalt_racing_wear", "elevation_m": 0.0,
    }
    return track, parcels, centerline, zone


# ----------------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------------
def validate(parcels, centerline, track_parcels, graph):
    problems = []
    # 1) overlap check via spatial hash
    bucket = defaultdict(list)
    B = 50.0
    for idx, p in enumerate(parcels):
        r = p["rect"]
        for bx in range(int(math.floor(r[0] / B)), int(math.floor(r[2] / B)) + 1):
            for by in range(int(math.floor(r[1] / B)), int(math.floor(r[3] / B)) + 1):
                bucket[(bx, by)].append(idx)
    seen = set()
    for lst in bucket.values():
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                a, b = lst[i], lst[j]
                if (a, b) in seen:
                    continue
                seen.add((a, b))
                if rect_overlap(parcels[a]["rect"], parcels[b]["rect"]):
                    problems.append("overlap %s / %s" % (parcels[a]["id"], parcels[b]["id"]))
    # 2) bounds
    for p in parcels:
        r = p["rect"]
        if r[0] < ORIGIN or r[1] < ORIGIN or r[2] > -ORIGIN or r[3] > -ORIGIN:
            problems.append("out of bounds %s" % p["id"])
    # 3) track self-intersection and clearance
    n = len(centerline)
    for i in range(n):
        for j in range(i + 3, n):
            if i == 0 and j >= n - 2:
                continue
            if seg_intersect(centerline[i], centerline[(i + 1) % n], centerline[j], centerline[(j + 1) % n]):
                problems.append("track self-intersection near sample %d/%d" % (i, j))
                break
    for p in track_parcels:
        md = min(dist_pt_rect(x, y, p["rect"]) for x, y in centerline)
        if md < 12.0 and p["type"] not in ("grandstand", "pit_building"):
            problems.append("track clearance %.1f m to %s" % (md, p["id"]))
        if md < 5.0:
            problems.append("track too close to %s (%.1f m)" % (p["id"], md))
    # 4) every non-T cell has coverage
    cover = defaultdict(float)
    for p in parcels:
        if p["cell"]:
            cover[tuple(p["cell"])] += rect_area(p["rect"])
    low = []
    for cy in range(NCELL):
        for cx in range(NCELL):
            d = cell_district(cx, cy)
            if d == "T":
                continue
            area = USABLE * USABLE
            if d in ("R", "D", "E", "I"):
                area -= STREET_W * USABLE * 2 - STREET_W * STREET_W
            elif d == "M":
                area -= ALLEY_W * USABLE * 6 - 9 * ALLEY_W * ALLEY_W
            ratio = cover[(cx, cy)] / area
            if ratio < 0.97:
                low.append(((cx, cy), round(ratio, 3)))
    if low:
        problems.append("low coverage cells: %s" % low)
    return problems


# ----------------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------------
def dump_pretty(obj, f):
    """Top-level keys on their own lines; list items one per line."""
    f.write("{\n")
    keys = list(obj.keys())
    for ki, k in enumerate(keys):
        v = obj[k]
        f.write(json.dumps(k) + ": ")
        if isinstance(v, list) and v and isinstance(v[0], dict):
            f.write("[\n")
            for i, item in enumerate(v):
                f.write("  " + json.dumps(item, separators=(",", ":")))
                f.write(",\n" if i < len(v) - 1 else "\n")
            f.write("]")
        elif isinstance(v, dict):
            f.write(json.dumps(v, indent=1))
        else:
            f.write(json.dumps(v, separators=(",", ":")))
        f.write(",\n" if ki < len(keys) - 1 else "\n")
    f.write("}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="layout.json")
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--split", action="store_true", help="also write parcels_<district>.json files")
    args = ap.parse_args()
    rng = random.Random(args.seed)

    graph, ring_ids, ramp_ids = build_roads()
    flyovers, stack = build_flyovers(graph, ring_ids, ramp_ids)
    lights = build_traffic_lights(graph)

    parcels, parks, water, landmarks = build_parcels(rng)
    assign_interiors(parcels, rng)
    pick_landmark_tower(parcels, landmarks)

    track, track_parcels, centerline, zone = build_track(rng)
    all_parcels = parcels + track_parcels

    problems = validate(all_parcels, centerline, track_parcels, graph)

    # districts block
    districts = []
    for dk, name in DISTRICT_NAMES.items():
        cells = [[cx, cy] for cy in range(NCELL) for cx in range(NCELL) if cell_district(cx, cy) == dk]
        rects = []
        for cx, cy in cells:
            x0, y0 = cell_origin(cx, cy)
            rects.append([x0, y0, x0 + CELL, y0 + CELL])
        districts.append({"id": dk, "name": name, "cells": cells, "cell_rects": rects,
                          "facade_styles": FACADE_STYLES.get(dk, [])})

    # stats
    by_dist = Counter(p["district"] for p in all_parcels)
    by_type = Counter(p["type"] for p in all_parcels)
    tiers = Counter(p["interior_tier"] for p in all_parcels if p["type"] not in
                    ("courtyard", "park", "pocket_park", "central_plaza"))
    hier = Counter(e["hierarchy"] for e in graph.edges)
    road_len = defaultdict(float)
    for e in graph.edges:
        road_len[e["hierarchy"]] += e["length"]
    stats = {
        "parcels_total": len(all_parcels),
        "parcels_by_district": dict(by_dist),
        "parcels_by_type": dict(sorted(by_type.items())),
        "interior_tiers": {"tier1_hero": tiers[1], "tier2_shell": tiers[2], "tier3_facade_only": tiers[3]},
        "enterable_total": sum(1 for p in all_parcels if p["enterable"]),
        "road_edges_by_hierarchy": dict(hier),
        "road_km_by_hierarchy": {k: r2(v / 1000.0) for k, v in road_len.items()},
        "traffic_lights": len(lights),
        "parks": len(parks),
        "track_length_m": track["length_m"],
        "validation_problems": problems,
    }

    layout = {
        "meta": {
            "name": "AAA City", "version": 1, "seed": args.seed, "units": "metres", "up_axis": "Z",
            "origin": "map centre; +X east, +Y north", "map_extent_m": [-1500, 1500],
            "inner_city_extent_m": [ORIGIN, -ORIGIN], "highway_ring_half_extent_m": RING,
            "cell_pitch_m": CELL, "grid": GRID, "grid_legend": DISTRICT_NAMES,
            "road_widths_m": {"highway": HIGHWAY_W, "arterial": ARTERIAL_W, "street": STREET_W,
                              "alley": ALLEY_W},
            "rules": [
                "No door meshes anywhere: enterable buildings use the parcel's 'opening' (archway, open frontage, atrium, porch, bay).",
                "interior_tier 1 = full hero interior, 2 = shell (one furnished room + simple plan), 3 = facade only.",
                "Place each interior at the parcel's interior_anchor (empty named INT_ANCHOR_<parcel id>) at anchor_pos.",
                "Parcels never overlap; build inside 'buildable_rect'; never cross 'rect'.",
                "Parks, plazas and courtyards are open-air (public_open_air) and need no door.",
                "Every cell is filled; do not leave empty land."],
            "generator": "generate_layout.py",
        },
        "districts": districts,
        "road_nodes": sorted(graph.nodes.values(), key=lambda n: n["id"]),
        "road_edges": graph.edges,
        "flyovers": flyovers,
        "stack_interchange": stack,
        "traffic_lights": lights,
        "parcels": all_parcels,
        "parks": parks,
        "water": water,
        "track": track,
        "landmarks": landmarks,
        "vegetation_rules": {
            "street_trees": {"hierarchies": ["arterial", "street"], "spacing_m": 14, "offset_from_curb_m": 1.5,
                             "districts": ["R", "E", "G", "D"], "skip_near_junction_m": 12},
            "park_scatter": {"parcel_types": ["park", "pocket_park"], "density_per_100m2": 1.2},
            "courtyard_scatter": {"subtypes": ["backyard_garden", "plaza_dining"], "density_per_100m2": 0.8},
            "market": {"trees": "few_large_shade_trees_in_plazas_only"},
        },
        "stats": stats,
    }

    with open(args.out, "w") as f:
        dump_pretty(layout, f)

    if args.split:
        base = os.path.dirname(os.path.abspath(args.out))
        for dk in DISTRICT_NAMES:
            sub = [p for p in all_parcels if p["district"] == dk]
            with open(os.path.join(base, "parcels_%s.json" % dk), "w") as f:
                dump_pretty({"district": dk, "parcels": sub}, f)

    print(json.dumps(stats, indent=2))
    if problems:
        print("VALIDATION PROBLEMS:", file=sys.stderr)
        for p in problems:
            print("  -", p, file=sys.stderr)
        sys.exit(1)
    print("OK -> %s (%.1f KB)" % (args.out, os.path.getsize(args.out) / 1024.0))


if __name__ == "__main__":
    main()
