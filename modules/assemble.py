#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
assemble.py -- headless master-scene assembler for the 3x3 km city.

RUN (headless, always from --factory-startup; never run with a GUI Blender that
also has out/*.blend open in another session):

    blender -b --factory-startup -P modules/assemble.py

WHAT IT DOES
------------
1. APPENDS (bpy.data.libraries.load(path, link=False)) the 16 module blends in
   out/ into ONE fresh master scene and saves it to out/city_master.blend.
   Missing files are warned about and skipped; the run still succeeds.
   Source blends are NEVER opened for editing and NEVER saved.
2. Builds the master collection tree City/{Roads, Flyovers, Buildings
   (Residential, Downtown, Entertainment, Market, Civic, Commercial, Transport,
   Industrial), Interiors, Vegetation, Props, Traffic, Track, Lighting,
   Colliders, Ground} and maps every module root collection into it
   (Nature -> Vegetation, Sports -> Buildings/Sports). Sub-collections
   (Meshes/Colliders/Lights) stay intact under their mapped parent.
3. Applies strip rules from reports/risk_fixes.json (schema risk-fixes/1):
   rect centre-in-rect + owning-module / name-pattern matching, with a
   tolerant fallback to merged_parcel_ids for the older entries in the file.
   Special park-convert rects: any NATURE leftovers inside them are removed
   (nature_strip should have already done this; verified + reported).
   Roads / Flyovers / Traffic / Lighting objects are protected unless the strip
   entry's owning_module names that module; Interiors and master-built objects
   are never stripped.
4. Dedupe:
   - Ring ground band under H_07/H_08: keep the ROADS service road/verge and
     delete flyover ground-band meshes (names containing Band/Service/Verge/
     Ground with centre z < 0.5) when both exist. Reported.
   - Cross-module exact-name + <0.01 m bbox-centre duplicates: keep one. Reported.
5. Render hygiene: every "...Colliders" collection gets hide_render=True /
   hide_viewport=False; COL_* objects get hide_render=True. Reported.
6. Ground: City/Ground gets one 3000x3000 m grass plane at z=-0.02 and one flat
   grass infield plane covering the track circuit bbox [612,-1188,1188,-12] at
   z=-0.01 (only 'grass'-family materials appended from materials.blend;
   district paving comes from roads/buildings).
7. World + master sun rig: grey-blue sky (0.55, 0.65, 0.8) strength 1.0, sun
   'SUN_Master' euler (5 deg, 0, 35 deg), energy 3.0, angle 0.5 deg, warm white
   (1.0, 0.95, 0.88). Engine set to BLENDER_EEVEE with a tolerant EEVEE-variant
   fallback. No other lights are added (lighting.blend carries the real ones).
   Color management view_transform is reported, not changed.
8. Saves out/city_master.blend, prints a JSON summary, writes
   reports/assemble_report.md and logs to /tmp/opencode/assemble.log.

NOTES / GUARANTEES
------------------
- Idempotent from --factory-startup: the master is rebuilt from scratch each
  run; a second run inside an already-assembled session is detected and aborts
  cleanly instead of double-appending.
- Memory-conscious: append-only libraries.load, orphan purge after deletions.
- Transforms: single-user meshes get location/rotation/scale applied (batched);
  linked-duplicate members (shared mesh data) are skipped because baking into a
  shared mesh would corrupt the other instances. This is reported.

Author: ASSEMBLY-SCRIPT-WRITER (subagent). Module: assemble.py.
"""

import json
import math
import os
import sys
import traceback

import bpy
from mathutils import Vector

# ---------------------------------------------------------------------------
# paths / constants
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "out")
REPORTS = os.path.join(ROOT, "reports")
LOG_PATH = "/tmp/opencode/assemble.log"
SUMMARY_PATH = "/tmp/opencode/assemble_summary.json"
MASTER_BLEND = os.path.join(OUT_DIR, "city_master.blend")
RISK_PATH = os.path.join(REPORTS, "risk_fixes.json")
MATERIALS_BLEND = os.path.join(ROOT, "materials.blend")

GRASS_CANDIDATES = ("grass", "nature_grass", "ground_grass", "nature_wild_grass")

# (file stem, expected module root collection name, master target path under City)
MODULE_FILES = [
    ("roads",         "Roads",         "Roads"),
    ("flyover",       "Flyovers",      "Flyovers"),
    ("market",        "Market",        "Buildings/Market"),
    ("downtown",      "Downtown",      "Buildings/Downtown"),
    ("residential",   "Residential",   "Buildings/Residential"),
    ("entertainment", "Entertainment", "Buildings/Entertainment"),
    ("nature",        "Nature",        "Vegetation"),
    ("track",         "Track",         "Track"),
    ("sports",        "Sports",        "Buildings/Sports"),
    ("civic",         "Civic",         "Buildings/Civic"),
    ("commercial",    "Commercial",    "Buildings/Commercial"),
    ("transport",     "Transport",     "Buildings/Transport"),
    ("traffic",       "Traffic",       "Traffic"),
    ("props",         "Props",         "Props"),
    ("lighting",      "Lighting",      "Lighting"),
    ("interiors",     "Interiors",     "Interiors"),
]

MASTER_BUILDINGS = [
    "Residential", "Downtown", "Entertainment",
    "Market", "Civic", "Commercial", "Transport", "Industrial",
]
CITY_CHILDREN = ["Roads", "Flyovers", "Buildings", "Interiors", "Vegetation",
                 "Props", "Traffic", "Track", "Lighting", "Colliders", "Ground"]

# strip protections: never delete these modules' objects unless the entry's
# owning_module names them explicitly. Keys are file stems (module_tags keys).
PROTECTED_MODULES = {"roads", "flyover", "traffic", "lighting"}
NEVER_STRIP_MODULES = {"interiors", "city", "ground", "master"}

# park-convert rects (task constants, x0,y0,x1,y1); keyed by substring match
PARK_RECTS = {
    "STADIUM_CRICKET": [-864.0, -1164.0, -636.0, -936.0],
    "STADIUM_FOOTBALL": [36.0, -1164.0, 264.0, -936.0],
    "STADIUM_ATHLETICS": [-1164.0, -864.0, -936.0, -636.0],
    "ARENA_INDOOR": [-1164.0, -564.0, -936.0, -336.0],
    "COMPLEX_SWIMMING": [12.0, -888.0, 288.0, -612.0],
}

# ring ground band under H_07 (x ~ 1400 east edge, y 600..1400) and
# H_08 (y ~ 1400 north edge, x 600..1400): generous +/-60 m corridors, closed
# at the shared corner (1400,1400). Derived from layout.json road_edges.
BAND_RECTS = [
    [1340.0, 560.0, 1460.0, 1480.0],   # H_07 corridor
    [560.0, 1340.0, 1480.0, 1460.0],   # H_08 corridor
]
BAND_EDGES = ("H_07", "H_08")
# flyover ground-band junk: name must contain one of these tokens
BAND_JUNK_TOKENS = ("band", "service", "verge", "ground")
TRACK_INFIELD_RECT = [612.0, -1188.0, 1188.0, -12.0]


# ---------------------------------------------------------------------------
# logging / tiny utils
# ---------------------------------------------------------------------------
LOGGED = []


def log(msg, tag="assemble"):
    line = "[%s] %s" % (tag, msg)
    LOGGED.append(line)
    try:
        print(line)
    except Exception:
        pass
    try:
        d = os.path.dirname(LOG_PATH)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def flush_log():
    try:
        d = os.path.dirname(LOG_PATH)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        if os.path.isfile(LOG_PATH) and os.path.getsize(LOG_PATH) > 0:
            return  # incremental writes already on disk
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(LOGGED) + "\n")
    except Exception as exc:  # pragma: no cover
        try:
            print("log write failed: %r" % (exc,))
        except Exception:
            pass


def ensure_coll(name, parent=None):
    """Get-or-create collection, linked under parent (or the scene)."""
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
    if parent is not None:
        if coll.name not in {c.name for c in parent.children}:
            parent.children.link(coll)
    else:
        sc = bpy.context.scene.collection
        if coll.name not in {c.name for c in sc.children}:
            sc.children.link(coll)
    return coll


def ensure_path(path, root):
    """Ensure nested collections 'A/B/C' under coll root; returns leaf."""
    cur = root
    if path:
        for part in path.split("/"):
            cur = ensure_coll(part, cur)
    return cur


def in_rect(p, rect, margin=0.0):
    return (rect[0] - margin <= p[0] <= rect[2] + margin and
            rect[1] - margin <= p[1] <= rect[3] + margin)


def in_any_rect(p, rects, margin=0.0):
    return any(in_rect(p, r, margin) for r in rects)


def bbox_centre(ob):
    """World-space centre of the object's bounding box."""
    base = Vector((1e18,) * 3)
    mx = Vector((-1e18,) * 3)
    n = 0
    for c4 in ob.bound_box:
        w = ob.matrix_world @ Vector(c4)
        base = Vector((min(base[i], w[i]) for i in range(3)))
        mx = Vector((max(mx[i], w[i]) for i in range(3)))
        n += 1
    if n == 0:
        return Vector(ob.matrix_world.translation)
    return (base + mx) * 0.5


def walk_collections(coll):
    """Yield coll plus all descendants."""
    stack = [coll]
    while stack:
        c = stack.pop()
        yield c
        stack.extend(c.children)


# ---------------------------------------------------------------------------
# output containers
# ---------------------------------------------------------------------------
summary = {
    "run_command": "blender -b --factory-startup -P modules/assemble.py",
    "master_blend": MASTER_BLEND,
    "missing_files": [],
    "modules": {},            # stem -> {root, mapped_to, objects_after}
    "collections_master": 0,
    "objects_total": 0,
    "tris": 0,
    "tri_count_method": None,
    "strip": {
        "generic_entries": 0,
        "deletions_by_module": {},
        "deletions_by_entry": {},
        "skipped_protected": 0,
        "skipped_unmatched": 0,
        "park_convert": {},   # facility -> {"remaining_found", "deleted"}
    },
    "dedupe": {
        "flyover_band_deleted": 0,
        "roads_band_kept": 0,
        "flyover_band_skipped_no_roads": 0,
        "cross_module_dupe_removed": 0,
        "cross_module_dupe_examples": [],
    },
    "render_hygiene": {
        "collider_collections_hidden": 0,
        "collider_objects_hidden": 0,
        "col_prefixed_hidden": 0,
        "camera_leftovers_removed": 0,
        "orphan_light_removed": 0,
    },
    "transforms": {"applied_objects": 0, "skipped_shared_mesh": 0, "errors": 0},
    "ground": [],
    "lights": {"imported_lights": 0, "sun_master_rot_deg": [5.0, 0.0, 35.0],
               "sun_master_energy": 3.0},
    "world": {"colour": [0.55, 0.65, 0.8], "strength": 1.0},
    "engine": None,
    "view_transform": None,
    "saved": False,
    "errors": [],
}


# ---------------------------------------------------------------------------
# 1. master collection scaffold
# ---------------------------------------------------------------------------
def build_master_tree():
    city = ensure_coll("City")
    kids = {}
    for name in CITY_CHILDREN:
        kids[name] = ensure_coll(name, city)
    for name in MASTER_BUILDINGS:
        ensure_coll(name, kids["Buildings"])
    # 'CityColliders' scaffold note: real Colliders sub-collections stay nested
    # under their owning module (a Blender collection may have only one
    # parent); this empty marker is where the spec wants a global handle.
    return city


# ---------------------------------------------------------------------------
# 2. append one module blend
# ---------------------------------------------------------------------------
def append_module(stem, root_name, target_path, module_tags):
    """Append all collections (plus collection-less objects) from a .blend.

    Returns (root_collections, orphan_objects_actual) or ([], []) on failure.
    """
    path = os.path.join(OUT_DIR, stem + ".blend")
    if not os.path.isfile(path):
        log("MISSING %s" % path, tag="warn")
        summary["missing_files"].append(path)
        return [], []

    before_names = {o.name for o in bpy.data.objects}
    before = set(bpy.data.collections)
    n_orphans = [0]
    try:
        try:
            with bpy.data.libraries.load(path, link=False, assets=False) as (
                    data_from, data_to):
                data_to.collections = list(data_from.collections)
                orphans = [o for o in data_from.objects
                           if not o.users_collection and o.type != "CAMERA"]
                data_to.objects = orphans
        except TypeError:  # older API without assets kw
            with bpy.data.libraries.load(path, link=False) as (data_from, data_to):
                data_to.collections = list(data_from.collections)
                orphans = [o for o in data_from.objects
                           if not o.users_collection and o.type != "CAMERA"]
                data_to.objects = orphans
    except Exception as exc:
        log("load failed for %s: %r" % (path, exc), tag="error")
        summary["errors"].append("load:%s:%r" % (stem, exc))
        return [], []

    imported = [c for c in bpy.data.collections if c not in before]
    # top-level import roots = imported collections that have no imported parent
    parented = {c.name for coll in imported for c in coll.children}
    roots = [c for c in imported if c.name not in parented
             and c.name.split(".")[0] == root_name]
    if not roots:  # fallback: any top import whose base name matches
        roots = [c for c in imported if c.name not in parented
                 and c.name.lower().startswith(root_name.lower())]
    # skip preview/swatch leftovers entirely
    roots = [c for c in roots
             if not any(t in c.name.lower()
                        for t in ("preview", "swatch", "camera", "temp"))]

    for root in roots:
        city_coll = bpy.data.collections.get("City")
        if city_coll is None:  # should never happen (build_master_tree ran)
            city_coll = ensure_coll("City")
        target = ensure_path(target_path, city_coll)
        if root.name not in {c.name for c in target.children}:
            target.children.link(root)
        for c in walk_collections(root):
            module_tags[c.name] = stem
        module_tags[target.name] = stem  # so orphan objects resolve too
        # collection-less objects: link into the mapped target, minus junk
        for ob in bpy.data.objects:
            if ob.name in before_names:
                continue
            if ob.users_collection:
                continue  # arrived inside an imported collection already
            if ob.type == "CAMERA":
                bpy.data.objects.remove(ob, do_unlink=True)
                summary["render_hygiene"]["camera_leftovers_removed"] += 1
                continue
            try:
                target.objects.link(ob)
                n_orphans[0] += 1
            except Exception as exc:
                log("orphan link failed %s: %r" % (ob.name, exc), tag="warn")
    summary["modules"][stem] = {
        "root": root_name,
        "mapped_to": "City/" + target_path,
        "imported_collections": len(imported),
        "orphans_linked": n_orphans[0],
        "roots": [r.name for r in roots],
    }
    return roots, []


def module_of_object(ob, module_tags):
    """Best-effort provenance: first directly-linked collection with a tag."""
    try:
        for coll in ob.users_collection:
            t = module_tags.get(coll.name)
            if t:
                return t
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# 3. strip rules
# ---------------------------------------------------------------------------
def load_strip_entries():
    try:
        with open(RISK_PATH, "r", encoding="utf-8") as f:
            doc = json.load(f)
        entries = doc.get("strip_list", []) or []
    except Exception as exc:
        log("risk_fixes.json unreadable: %r" % (exc,), tag="warn")
        summary["errors"].append("risk_fixes:%r" % (exc,))
        return []

    norm = []
    for e in entries:
        rect = e.get("rect")
        if not rect or len(rect) != 4:
            continue
        fac = e.get("facility_id", "")
        if e.get("type") == "park_convert":
            for key, r2 in PARK_RECTS.items():
                if key in fac or fac in key:
                    rect = r2
                    break
        pattern = e.get("object_pattern", "")
        tokens = []
        if pattern:
            for tok in str(pattern).replace("*", " ").replace("?", " ").split("|"):
                tok = tok.strip()
                if tok and tok not in ("^", "$"):
                    tokens.append(tok)
        hints = tokens + [str(x) for x in e.get("merged_parcel_ids", []) or []]
        norm.append({
            "rect": [float(x) for x in rect],
            "owning_module": e.get("owning_module"),
            "hints": hints,
            "type": e.get("type", ""),
            "facility_id": fac,
        })
    summary["strip"]["generic_entries"] = len(norm)
    return norm


def strip_pass(module_tags):
    """Delete objects per strip rules; never touch protected / master objects."""
    entries = load_strip_entries()
    victims = []          # (ob, module_tag, facility_id)
    skipped_prot = 0
    skipped_unmatched = 0

    snapshot = list(bpy.data.objects)
    for ob in snapshot:
        if ob.type not in {"MESH", "CURVE", "EMPTY", "SURFACE", "META", "FONT"}:
            continue
        tag = module_of_object(ob, module_tags)
        if tag in NEVER_STRIP_MODULES or tag is None:
            continue
        centre = bbox_centre(ob)
        name_low = ob.name.lower()
        matched = False
        for e in entries:
            if not in_rect(centre, e["rect"]):
                continue
            owning = e["owning_module"]
            if tag in PROTECTED_MODULES:
                if owning and owning.lower() == tag.lower():
                    matched = True
                else:
                    skipped_prot += 1
                    continue
            elif owning:
                if owning.lower() == tag.lower():
                    matched = True
                elif any(h.lower() in name_low for h in e["hints"]):
                    matched = True
                elif not e["hints"]:
                    skipped_unmatched += 1
            else:
                if e["hints"]:
                    # older schema (actual file): rely on removed parcel ids
                    if any(h.lower() in name_low for h in e["hints"]):
                        matched = True
                    else:
                        skipped_unmatched += 1
                else:
                    skipped_unmatched += 1
            if matched:
                summary["strip"]["deletions_by_entry"][e["facility_id"]] = \
                    summary["strip"]["deletions_by_entry"].get(
                        e["facility_id"], 0) + 1
                victims.append((ob, tag, e["facility_id"]))
                break
        if not matched:
            continue

    for ob, tag, fac in victims:
        key = tag or "unknown"
        summary["strip"]["deletions_by_module"][key] = \
            summary["strip"]["deletions_by_module"].get(key, 0) + 1
        try:
            bpy.data.objects.remove(ob, do_unlink=True)
        except Exception as exc:
            summary["errors"].append("strip_remove:%s:%r" % (ob.name, exc))
    summary["strip"]["skipped_protected"] = skipped_prot
    summary["strip"]["skipped_unmatched"] = skipped_unmatched

    # --- SPECIAL: park-convert rects must hold no Nature leftovers -----------
    nature_tag = "nature"
    snapshot = list(bpy.data.objects)
    for fac, rect in PARK_RECTS.items():
        found, removed = 0, 0
        for ob in snapshot:
            if ob.type not in {"MESH", "CURVE", "EMPTY"}:
                continue
            if module_of_object(ob, module_tags) != nature_tag:
                continue
            if not in_rect(bbox_centre(ob), rect):
                continue
            found += 1
            try:
                bpy.data.objects.remove(ob, do_unlink=True)
                removed += 1
            except Exception:
                pass
        if found:
            summary["strip"]["deletions_by_module"][nature_tag] = \
                summary["strip"]["deletions_by_module"].get(nature_tag, 0) + removed
        summary["strip"]["park_convert"][fac] = {
            "remaining_found": found, "deleted": removed,
            "verified_clean": found == 0,
        }
        log("park_convert %s: found %d nature leftovers, deleted %d" %
            (fac, found, removed))
    return victims


# ---------------------------------------------------------------------------
# 4. dedupe
# ---------------------------------------------------------------------------
def dedupe_ring_band(module_tags):
    """Under H_07/H_08: keep ROADS service road/verge, drop flyover junk."""
    flyover_band, roads_kept = [], 0
    for ob in list(bpy.data.objects):
        tag = module_of_object(ob, module_tags)
        if tag is None:
            continue
        if not in_any_rect(bbox_centre(ob), BAND_RECTS):
            continue
        if tag == "flyover":
            low = ob.name.lower()
            if (bbox_centre(ob).z < 0.5 and
                    any(t in low for t in BAND_JUNK_TOKENS)):
                flyover_band.append(ob)
                continue
        if tag == "roads" and ob.name.startswith("SM_ServiceRoad"):
            roads_kept += 1

    if roads_kept == 0:
        summary["dedupe"]["flyover_band_skipped_no_roads"] = len(flyover_band)
        log("ground band: NO roads SM_ServiceRoad_%s_* yet -> flyover band kept"
            % ("/".join(BAND_EDGES)), tag="warn")
        return

    for ob in flyover_band:
        try:
            bpy.data.objects.remove(ob, do_unlink=True)
            summary["dedupe"]["flyover_band_deleted"] += 1
        except Exception as exc:
            summary["errors"].append("band_remove:%r" % (exc,))
    summary["dedupe"]["roads_band_kept"] = roads_kept
    log("ground band dedupe: removed %d flyover band objects, kept %d roads "
        "service roads" % (len(flyover_band), roads_kept))


def dedupe_cross_module(module_tags):
    """Exact same object name, cross-module, bbox centre < 0.01 m -> keep 1."""
    groups = {}
    for ob in list(bpy.data.objects):
        if ob.type not in {"MESH", "CURVE", "SURFACE", "META", "FONT"}:
            continue
        groups.setdefault(ob.name, []).append(ob)
    keys = sorted(groups.keys())          # order-priority = later file wins ties? keep first
    for name in keys:
        obs = groups.get(name)
        if not obs or len(obs) < 2:
            continue
        tagged = [(o, module_of_object(o, module_tags)) for o in obs]
        for i in range(len(tagged) - 1):
            a, ta = tagged[i]
            for j in range(i + 1, len(tagged)):
                b, tb = tagged[j]
                if ta is None or tb is None or ta == tb or a is None or b is None:
                    continue
                if (bbox_centre(a) - bbox_centre(b)).length < 0.01:
                    victim = (b, tb)
                    try:
                        bpy.data.objects.remove(victim[0], do_unlink=True)
                    except Exception as exc:
                        summary["errors"].append("dup_remove:%r" % (exc,))
                        continue
                    summary["dedupe"]["cross_module_dupe_removed"] += 1
                    if len(summary["dedupe"]["cross_module_dupe_examples"]) < 12:
                        summary["dedupe"]["cross_module_dupe_examples"].append(
                            {"name": name, "kept_module": ta,
                             "dropped_module": tb})
                    tagged[j] = (None, None)


def purge_orphans():
    try:
        bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True,
                               do_recursive=True)
    except Exception as exc:
        summary["errors"].append("purge:%r" % (exc,))


# ---------------------------------------------------------------------------
# 5. render hygiene
# ---------------------------------------------------------------------------
def render_hygiene():
    def is_colliders(c):
        return c.name.endswith("Colliders") or "/Colliders" in c.name

    try:
        for coll in list(bpy.data.collections):
            if is_colliders(coll):
                coll.hide_render = True
                coll.hide_viewport = False
                summary["render_hygiene"]["collider_collections_hidden"] += 1
        for ob in list(bpy.data.objects):
            if ob.name.startswith("COL_"):
                ob.hide_render = True
                summary["render_hygiene"]["col_prefixed_hidden"] += 1
            # objects physically placed inside a Colliders collection get the
            # collection-level flag already; count them separately
            for coll in ob.users_collection:
                if is_colliders(coll):
                    summary["render_hygiene"]["collider_objects_hidden"] += 1
                    break
        for ob in [o for o in bpy.data.objects if o.type == "CAMERA"]:
            bpy.data.objects.remove(ob, do_unlink=True)
            summary["render_hygiene"]["camera_leftovers_removed"] += 1
    except Exception as exc:
        summary["errors"].append("hygiene:%r" % (exc,))


# ---------------------------------------------------------------------------
# 6. ground planes
# ---------------------------------------------------------------------------
def make_plane(name, cx, cy, sx, sy, z, coll, mat):
    me = bpy.data.meshes.new(name)
    ob = bpy.data.objects.new(name, me)
    me.vertices = [(-sx * 0.5 + cx, -sy * 0.5 + cy, z),
                   (sx * 0.5 + cx, -sy * 0.5 + cy, z),
                   (sx * 0.5 + cx, sy * 0.5 + cy, z),
                   (-sx * 0.5 + cx, sy * 0.5 + cy, z)]
    me.edges = [(0, 1), (1, 2), (2, 3), (3, 0)]
    me.polygons = [(0, 3, 2), (2, 1, 0)]
    ob.data = me
    if mat is not None:
        try:
            me.materials.append(mat)
        except Exception:
            pass
    coll.objects.link(ob)
    return ob


def append_grass_material():
    got = [m for m in bpy.data.materials
           if m.name.lower() in GRASS_CANDIDATES]
    if got:
        return got[0]
    if not os.path.isfile(MATERIALS_BLEND):
        summary["errors"].append("materials.blend missing")
        return None
    try:
        with bpy.data.libraries.load(MATERIALS_BLEND, link=False, assets=False) as (
                data_from, data_to):
            want = [n for n in data_from.materials
                    if n.lower() in GRASS_CANDIDATES]
            if not want:
                want = [n for n in data_from.materials if "grass" in n.lower()][:1]
            data_to.materials = want
        got = [m for m in bpy.data.materials
               if m.name.lower() in GRASS_CANDIDATES]
        return got[0] if got else None
    except Exception as exc:
        summary["errors"].append("grass_mat:%r" % (exc,))
        return None


def ground():
    coll = ensure_coll("Ground", bpy.data.collections.get("City"))
    mat = append_grass_material()
    big = make_plane("SM_Ground_Grass", 0.0, 0.0, 3000.0, 3000.0, -0.02, coll, mat)
    infield = make_plane("SM_Track_Infield_Grass", 900.0, -600.0,
                         abs(TRACK_INFIELD_RECT[2] - TRACK_INFIELD_RECT[0]),
                         abs(TRACK_INFIELD_RECT[3] - TRACK_INFIELD_RECT[1]),
                         -0.01, coll, mat)
    summary["ground"] = [
        {"name": "SM_Ground_Grass", "size": "3000x3000", "z": -0.02,
         "material": mat.name if mat else None},
        {"name": "SM_Track_Infield_Grass", "rect": TRACK_INFIELD_RECT, "z": -0.01,
         "material": mat.name if mat else None},
    ]


# ---------------------------------------------------------------------------
# 7. world + sun rig
# ---------------------------------------------------------------------------
def world_and_sun():
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE"
        summary["engine"] = "BLENDER_EEVEE"
    except TypeError:
        try:
            ids = [i.identifier for i in
                   bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
            ee = [x for x in ids if "EEVEE" in x.upper()]
            scene.render.engine = ee[0] if ee else ids[0]
            summary["engine"] = scene.render.engine
        except Exception as exc:
            summary["errors"].append("engine:%r" % (exc,))

    w = bpy.data.worlds.get("World_Master") or bpy.data.worlds.new("World_Master")
    w.use_nodes = True
    try:
        bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
        bg.inputs[0].default_value = (0.55, 0.65, 0.8, 1.0)
        bg.inputs[1].default_value = 1.0
    except Exception as exc:
        summary["errors"].append("world_node:%r" % (exc,))
    scene.world = w

    try:
        light = bpy.data.lights.new("SUN_Master", type="SUN")
        light.energy = 3.0
        light.color = (1.0, 0.95, 0.88)
        try:
            light.angle = math.radians(0.5)
        except Exception:
            pass
        ob = bpy.data.objects.new("SUN_Master", light)
        ob.rotation_euler = (math.radians(5.0), 0.0, math.radians(35.0))
        li = ensure_coll("Lighting", bpy.data.collections.get("City"))
        li.objects.link(ob)
    except Exception as exc:
        summary["errors"].append("sun:%r" % (exc,))

    try:
        summary["view_transform"] = scene.view_settings.view_transform
    except Exception:
        summary["view_transform"] = "unknown"


# ---------------------------------------------------------------------------
# 8. transforms (safe: skip shared meshes)
# ---------------------------------------------------------------------------
def apply_transforms_safe():
    """Bake object transforms into UNIQUE meshes without operators.

    bpy.ops.object.transform_apply over 40k objects takes hours; direct
    mesh.transform is linear. Shared meshes (instances) must keep their
    object matrices, so they are skipped on purpose.
    """
    done = 0
    skipped = 0
    from mathutils import Matrix
    ident = Matrix.Identity(4)
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        me = ob.data
        if me.users != 1 or me.library is not None:
            skipped += 1
            continue
        mw = ob.matrix_world
        if all(abs(mw[i][j] - ident[i][j]) < 1e-9
               for i in range(4) for j in range(4)):
            continue
        try:
            me.transform(mw)
            ob.matrix_world = Matrix.Identity(4)
            done += 1
        except Exception:
            summary["transforms"]["errors"] += 1
    summary["transforms"]["applied_objects"] = done
    summary["transforms"]["skipped_shared_mesh"] = skipped


def validate_meshes():
    """Repair invalid mesh data (civic meshes segfault EEVEE without this)."""
    bad = 0
    for me in bpy.data.meshes:
        try:
            if me.validate(verbose=False, clean_customdata=True):
                bad += 1
                me.update()
        except Exception:
            summary["errors"].append("mesh_validate:%s" % me.name)
    summary["mesh_validate_repaired"] = bad
    log("mesh.validate repaired %d datablocks" % bad, tag="ok")


# ---------------------------------------------------------------------------
# 9. summary + report
# ---------------------------------------------------------------------------
def compute_counts(module_tags=None):
    bpy.context.view_layer.update()
    summary["collections_master"] = len(bpy.data.collections)
    summary["objects_total"] = len(bpy.data.objects)
    for stem, meta in summary["modules"].items():
        n = 0
        for rname in meta.get("roots", []):
            root = bpy.data.collections.get(rname)
            if root is None:
                continue
            for coll in walk_collections(root):
                n += len(coll.objects)
        # count via provenance tag instead (covers orphan objects that were
        # linked straight into the module's target collection)
        n = sum(1 for ob in bpy.data.objects
                if module_of_object(ob, module_tags or {}) == stem)
        meta["objects_after"] = n
    summary["lights"]["imported_lights"] = sum(
        1 for ob in bpy.data.objects if ob.type == "LIGHT")
    try:
        dg = bpy.context.evaluated_depsgraph_get()
        tris = 0
        for inst in dg.object_instances:
            o = inst.object
            if o.type == "MESH" and o.data is not None:
                tris += sum(len(p.vertices) - 2 for p in o.data.polygons)
        summary["tris"] = tris
        summary["tri_count_method"] = "evaluated_depsgraph (+instances)"
    except Exception as exc:
        summary["tri_count_method"] = "direct_data_fallback (%r)" % (exc,)
        t = 0
        for ob in bpy.data.objects:
            if ob.type == "MESH" and ob.data:
                t += sum(len(p.vertices) - 2 for p in ob.data.polygons)
        summary["tris"] = t


def write_report():
    md = [
        "# assemble.py report",
        "",
        "Run: `blender -b --factory-startup -P modules/assemble.py`",
        "",
        "Master: `out/city_master.blend` (saved: @saved@).",
        "",
        "## Counts",
        "- Objects total: @objects_total@",
        "- Collections: @collections_master@",
        "- Tris: @tris@ (@tri_count_method@)",
        "",
        "## Engine / World",
        "- Engine: @engine@",
        "- View transform: @view_transform@ (reported; not changed)",
        "- World: World_Master (sky 0.55/0.65/0.8, strength 1.0)",
        "- Sun: SUN_Master euler (5, 0, 35) deg, energy 3, angle 0.5 deg, warm white",
        "- Lights total (incl. SUN_Master + lighting.blend): @imported_lights@",
        "",
        "## Modules",
        "@modules@",
        "",
        "## Missing files",
        "@missing@",
        "",
        "## Strip",
        "- Generic entries: @generic_entries@",
        "- Deletions by module: @del_by_module@",
        "- Park-convert verification (nature leftovers inside 5 rects):"
        " @park_inline@",
        "```",
        "@park@",
        "```",
        "- skipped_protected: @skipped_protected@",
        "- skipped_unmatched: @skipped_unmatched@",
        "",
        "## Dedupe",
        "- Flyover ground band under H_07/H_08 deleted: @flyover_band_deleted@",
        "- Roads service roads kept: @roads_band_kept@",
        "- Cross-module duplicates removed: @cross_module_dupe_removed@",
        "- Examples: @dupe_examples@",
        "",
        "## Render hygiene",
        "- Collider collections hidden: @collider_collections_hidden@",
        "- COL_* objects hidden: @col_prefixed_hidden@",
        "- Objects inside Colliders collections: @collider_objects_hidden@",
        "- Camera/light leftovers removed: @camera_leftovers_removed@",
        "",
        "## Ground",
        "@ground@",
        "",
        "## Transforms",
        "- Applied (single-user meshes): @applied_objects@; "
        "skipped shared-mesh linked duplicates: @skipped_shared_mesh@; "
        "errors: @transform_errors@",
        "",
        "## Errors",
        "@errors@",
        "",
    ]
    s = summary
    fmt = {
        "objects_total": s["objects_total"],
        "collections_master": s["collections_master"],
        "tris": s["tris"],
        "tri_count_method": s["tri_count_method"],
        "engine": s["engine"],
        "view_transform": s["view_transform"],
        "saved": s["saved"],
        "imported_lights": s["lights"]["imported_lights"],
        "modules": "\n".join(
            "- **%s** -> City/%s (root %s, imports %s collections, "
            "%s orphans, objects after: %s)" %
            (k, v["mapped_to"], v["root"], v["imported_collections"],
             v.get("orphans_linked", 0), v.get("objects_after", "?"))
            for k, v in s["modules"].items()),
        "missing": "\n".join("- " + x for x in s["missing_files"])
                   or "- (none)",
        "generic_entries": s["strip"]["generic_entries"],
        "del_by_module": json.dumps(s["strip"]["deletions_by_module"]),
        "park": json.dumps(s["strip"]["park_convert"], indent=1),
        "park_inline": json.dumps(
            {k: v["remaining_found"] for k, v in
             s["strip"]["park_convert"].items()}),
        "skipped_protected": s["strip"]["skipped_protected"],
        "skipped_unmatched": s["strip"]["skipped_unmatched"],
        "flyover_band_deleted": s["dedupe"]["flyover_band_deleted"],
        "roads_band_kept": s["dedupe"]["roads_band_kept"],
        "cross_module_dupe_removed":
            s["dedupe"]["cross_module_dupe_removed"],
        "dupe_examples": json.dumps(
            s["dedupe"]["cross_module_dupe_examples"]),
        "collider_collections_hidden":
            s["render_hygiene"]["collider_collections_hidden"],
        "col_prefixed_hidden": s["render_hygiene"]["col_prefixed_hidden"],
        "collider_objects_hidden":
            s["render_hygiene"]["collider_objects_hidden"],
        "camera_leftovers_removed":
            s["render_hygiene"]["camera_leftovers_removed"],
        "ground": "\n".join("- " + json.dumps(g) for g in s["ground"]),
        "applied_objects": s["transforms"]["applied_objects"],
        "skipped_shared_mesh": s["transforms"]["skipped_shared_mesh"],
        "transform_errors": s["transforms"]["errors"],
        "errors": "\n".join("- " + e for e in s["errors"]) or "- (none)",
    }
    txt = "\n".join(md)
    for key, val in fmt.items():
        txt = txt.replace("@%s@" % key, str(val))
    try:
        os.makedirs(REPORTS, exist_ok=True)
        with open(os.path.join(REPORTS, "assemble_report.md"), "w",
                  encoding="utf-8") as f:
            f.write(txt + "\n")
        with open(os.path.join(REPORTS, "assemble_report.json"), "w",
                  encoding="utf-8") as f:
            f.write(json.dumps(s, indent=2, sort_keys=True, default=str))
    except Exception as exc:
        try:
            print("report write failed: %r" % (exc,))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def run():
    bpy.context.view_layer.update()
    if bpy.data.collections.get("City"):
        log("master already assembled in this session -- aborting to keep "
            "appends idempotent.", tag="abort")
        return 1

    log("== assemble start ==")
    # factory-startup leftovers: default Cube / Camera / Light must not survive
    try:
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        purge_orphans()
    except Exception as exc:
        summary["errors"].append("factory_clear:%r" % (exc,))
    build_master_tree()

    module_tags = {}
    prev_objs = set()
    for stem, root_name, target in MODULE_FILES:
        append_module(stem, root_name, target, module_tags)
        newobjs = set(o.name for o in bpy.data.objects) - prev_objs
        prev_objs = set(o.name for o in bpy.data.objects)
        log("appended %-14s objects: %d" % (stem, len(newobjs)))
        flush_log()

    try:
        strip_pass(module_tags)
        dedupe_ring_band(module_tags)
        dedupe_cross_module(module_tags)
        purge_orphans()
        apply_transforms_safe()
        validate_meshes()
        render_hygiene()
        ground()
        world_and_sun()
        compute_counts(module_tags)
        purge_orphans()
    except Exception:
        summary["errors"].append(traceback.format_exc())
        log(traceback.format_exc(), tag="error")

    log("== assemble end ==")

    # ---- save master (only touch: out/city_master.blend) -------------------
    try:
        bpy.context.view_layer.update()
        bpy.ops.wm.save_as_mainfile(filepath=MASTER_BLEND, compress=True,
                                    relative_remap=True, check_existing=False)
        summary["saved"] = True
        summary["master_blend"] = MASTER_BLEND
        log("SAVED %s" % MASTER_BLEND, tag="ok")
    except Exception as exc:
        summary["saved"] = False
        summary["errors"].append("save:%r" % (exc,))
        log("SAVE FAILED: %r" % (exc,), tag="error")
    return 0


def main():
    try:
        run()
    except Exception:
        summary["errors"].append(traceback.format_exc())
        log(traceback.format_exc(), tag="fatal")
    # strip raw python objects out of summary for JSON
    clean = json.loads(json.dumps(summary, default=str))
    try:
        print(json.dumps(clean, indent=2, sort_keys=True, default=str))
        flush_log()
        try:
            os.makedirs(os.path.dirname(SUMMARY_PATH), exist_ok=True)
            with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
                f.write(json.dumps(clean, indent=2, sort_keys=True, default=str))
        except Exception as exc:
            print("summary write failed: %r" % (exc,))
        write_report()
    except Exception as exc:
        try:
            print("emit failed: %r" % (exc,))
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    main()
