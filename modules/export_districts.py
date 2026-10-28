#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_districts.py -- split out/city_master.blend into 9 streamable district
exports (glTF .glb + binary FBX) with per-district and top-level manifests.

RUN (documented command, headless, master is opened by Blender itself):

    blender -b out/city_master.blend -P modules/export_districts.py -- --out exports

WHY IT LOOKS THE WAY IT DOES
----------------------------
* District membership is decided by the object's WORLD bbox CENTRE against the
  layout.json cell rects (district cells R/D/E/M/G/I/T), the highway ring band
  (|x| > 1200 or |y| > 1200, corners excluded) and a final "civic / remaining"
  catch-all.  Every object gets exactly one district, so the exports tile the
  city without duplicates; the only exceptions are direction-only sun lights
  (shipped in all nine) and parent empties pulled in to keep a node hierarchy
  intact.  Priority order is documented in the manifests.
* Blender in `-b` mode has NO window, so `bpy.context.window.scene = scene` is
  impossible and `bpy.data.scenes.new()` can never become the active scene.
  glTF would then export the whole master (or every scene in the file).  So the
  isolation is done the way that always works headless and is far cheaper:
  build one temporary collection holding the district objects, temporarily
  unlink the master's scene-root children, link only the temp collection,
  export, then put the master tree back EXACTLY as it was.  Equivalent to
  "link the master into a new scene and delete everything outside the rect",
  without the un-activatable scene.  The master .blend on disk is never saved
  and never touched; all of this is in-memory only.
* Nothing outside `--out` is written (plus reports/ and /tmp/opencode/export.log).
* Idempotent: stale district output files are removed before each export and
  all manifests are rewritten.  Re-running produces the same tree.
* Memory-conscious: one district at a time, evaluated meshes are only touched
  while that district alone is linked in the scene, and orphans are purged
  after every district (never while the master tree is unlinked).

COLLIDERS: objects in any collection whose name contains "Colliders" and every
COL_* object are excluded from the exports (they stay hidden in the master).

LIGHTS: included.  glTF exports them through KHR_lights_punctual, FBX as light
nodes.  Sun lights are direction-only, so they are put in EVERY district;
positional lights (point/spot/area) follow the normal rect rule.

Author: EXPORT-SCRIPT-WRITER (subagent). Module: export_districts.py.
"""

import datetime
import json
import os
import sys
import time
import traceback

import bpy
from mathutils import Vector

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAYOUT_PATH = os.path.join(ROOT, "layout.json")
REPORTS_DIR = os.path.join(ROOT, "reports")
DEFAULT_OUT_DIR = os.path.join(ROOT, "exports")
LOG_PATH = "/tmp/opencode/export.log"
SUMMARY_PATH = "/tmp/opencode/export_summary.json"

SCHEMA = "city-export/1"
RING_HALF_M = 1200.0          # highway ring inner edge
MAP_EXTENT_M = 1500.0         # map half extent (layout.json meta)
MAPWIDE_SPAN_M = 1500.0       # objects bigger than this = map backdrop
DISTRICT_ORDER = ["downtown", "market", "residential", "entertainment",
                  "green", "industrial", "track", "highway", "civic"]

DISTRICT_LABEL = {
    "downtown": "Downtown core",
    "market": "Market quarter",
    "residential": "Residential",
    "entertainment": "Entertainment strip",
    "green": "Green belt",
    "industrial": "Industrial",
    "track": "Race circuit",
    "highway": "Highway ring",
    "civic": "Civic / remaining",
}

# layout district key -> export district name (cell based districts)
CELL_DISTRICTS = [("D", "downtown"), ("M", "market"), ("R", "residential"),
                  ("E", "entertainment"), ("G", "green"), ("I", "industrial"),
                  ("T", "track")]

STALE_EXT = (".glb", ".gltf", ".fbx", ".bin")
ADDONS = {
    "gltf": ("io_scene_gltf2", "bl_ext.blender_org.gltf2", "gltf2"),
    "fbx": ("io_scene_fbx", "bl_ext.blender_org.fbx", "fbx"),
}

# kwargs we hand to the exporters; anything not present in the operator's RNA is
# dropped (Blender 5.2.3 moved/renamed several of these).
GLTF_KWARGS = {
    "export_format": "GLB",
    "use_selection": False,
    "export_apply": True,
    "export_yup": True,
    "export_cameras": False,
    "export_lights": True,
    "export_animations": False,
    "export_extras": False,
    "export_materials": "EXPORT",
    "use_active_scene": True,
}
FBX_KWARGS = {
    "use_selection": False,
    "path_mode": "COPY",
    "embed_textures": True,
    "apply_scale_options": "FBX_SCALE_ALL",
    "object_types": {"MESH", "LIGHT", "EMPTY"},
    "use_mesh_modifiers": True,
    "bake_anim": False,
    "bake_animations": False,
    "add_leaf_bones": False,
    "axis_forward": "-Z",
    "axis_up": "Y",
}

# dropped one at a time (last first) when an exporter rejects/breaks on them
DROP_ORDER = ["export_apply", "export_animations", "export_extras",
              "export_materials", "use_active_scene", "export_lights",
              "export_cameras", "export_yup", "object_types",
              "use_mesh_modifiers", "embed_textures", "apply_scale_options",
              "path_mode", "bake_anim", "bake_animations", "add_leaf_bones",
              "axis_forward", "axis_up", "use_selection"]

# ---------------------------------------------------------------------------
# logging
# ---------------------------------------------------------------------------
_LOG_FH = None
_UNKNOWN_LOGGED = set()


def log(msg, tag="info"):
    """Append one timestamped line to /tmp/opencode/export.log and stdout."""
    global _LOG_FH
    line = "%s [%-4s] %s" % (time.strftime("%Y-%m-%dT%H:%M:%S"), tag.upper(), msg)
    print(line, flush=True)
    if _LOG_FH is None:
        try:
            d = os.path.dirname(LOG_PATH)
            if d:
                os.makedirs(d, exist_ok=True)
            _LOG_FH = open(LOG_PATH, "a", buffering=1)
        except Exception:
            _LOG_FH = False
    if _LOG_FH:
        try:
            _LOG_FH.write(line + "\n")
        except Exception:
            pass


def iso_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# command line (everything after "--")
# ---------------------------------------------------------------------------
def parse_args(argv):
    opts = {"out": DEFAULT_OUT_DIR, "districts": list(DISTRICT_ORDER),
            "glb": True, "fbx": True, "dry_run": False, "purge": True}
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--out", "-o") and i + 1 < len(argv):
            opts["out"] = os.path.abspath(argv[i + 1])
            i += 2
        elif a == "--districts" and i + 1 < len(argv):
            wanted = [x.strip().lower() for x in argv[i + 1].split(",") if x.strip()]
            bad = [x for x in wanted if x not in DISTRICT_ORDER]
            if bad:
                raise SystemExit("unknown district(s): %s (valid: %s)"
                                 % (", ".join(bad), ", ".join(DISTRICT_ORDER)))
            opts["districts"] = wanted
            i += 2
        elif a == "--no-glb":
            opts["glb"] = False
            i += 1
        elif a == "--no-fbx":
            opts["fbx"] = False
            i += 1
        elif a == "--dry-run":
            opts["dry_run"] = True
            i += 1
        elif a == "--no-purge":
            opts["purge"] = False
            i += 1
        elif a in ("-h", "--help"):
            raise SystemExit(__doc__)
        else:
            raise SystemExit("unknown argument %r\n\n%s" % (a, __doc__))
    if not opts["glb"] and not opts["fbx"]:
        raise SystemExit("nothing to do: both glb and fbx disabled")
    return opts


# ---------------------------------------------------------------------------
# layout / district geometry
# ---------------------------------------------------------------------------
def read_layout():
    if not os.path.isfile(LAYOUT_PATH):
        raise RuntimeError("layout.json not found at %s" % LAYOUT_PATH)
    with open(LAYOUT_PATH) as f:
        layout = json.load(f)
    for key in ("districts", "meta"):
        if key not in layout:
            raise RuntimeError("layout.json is missing %r" % key)
    return layout


def rect_bbox(rects):
    return [min(r[0] for r in rects), min(r[1] for r in rects),
            max(r[2] for r in rects), max(r[3] for r in rects)]


def in_rect(x, y, r, eps=0.0):
    return (r[0] - eps) <= x <= (r[2] + eps) and (r[1] - eps) <= y <= (r[3] + eps)


class DistrictIndex(object):
    """Membership rules + rect metadata for the 9 exports."""

    def __init__(self, layout):
        self.cells = {}
        self.rects = {}
        by_id = {d["id"]: d for d in layout["districts"]}
        for key, name in CELL_DISTRICTS:
            d = by_id.get(key)
            if d is None:
                raise RuntimeError("layout.json has no district %r" % key)
            rs = [tuple(float(v) for v in r) for r in d["cell_rects"]]
            self.cells[name] = rs
            self.rects[name] = rect_bbox(rs)
        # highway + civic are not cell districts: their rect is the whole map
        self.rects["highway"] = [-MAP_EXTENT_M, -MAP_EXTENT_M,
                                 MAP_EXTENT_M, MAP_EXTENT_M]
        self.rects["civic"] = [-MAP_EXTENT_M, -MAP_EXTENT_M,
                               MAP_EXTENT_M, MAP_EXTENT_M]

    def classify(self, x, y, span_x=0.0, span_y=0.0):
        """Return the single district name for a bbox centre (+ bbox span)."""
        # map-wide backdrops (3000 m ground plane, full ring loops) are exported
        # exactly once, in the highway chunk, instead of overlapping every chunk
        if max(span_x, span_y) >= MAPWIDE_SPAN_M:
            return "highway"
        for key, name in CELL_DISTRICTS:
            for r in self.cells[name]:
                if in_rect(x, y, r):
                    return name
        in_band = abs(x) > RING_HALF_M or abs(y) > RING_HALF_M
        corner = abs(x) > RING_HALF_M and abs(y) > RING_HALF_M
        if in_band and not corner:
            return "highway"
        return "civic"

    def rule_note(self, name):
        if name == "highway":
            return ("ring band |x|>%g or |y|>%g, corners excluded; map-wide "
                    "objects (bbox span >= %g m) also land here"
                    % (RING_HALF_M, RING_HALF_M, MAPWIDE_SPAN_M))
        if name == "civic":
            return ("remainder district: everything not claimed by another "
                    "district; rect is the map extent, membership is by "
                    "exclusion")
        if name == "downtown":
            return ("union of the 7 layout D cells (bbox x -300..600, "
                    "y -300..600; the innermost cells cover x/y -300..300)")
        return ("bbox centre inside the %d layout %s cell rect(s); rect is "
                "their bounding box" % (len(self.cells[name]), name))

    def cell_rects(self, name):
        return [[round(v, 2) for v in r] for r in self.cells.get(name, [])]


# ---------------------------------------------------------------------------
# Blender helpers
# ---------------------------------------------------------------------------
def city_root_collection():
    """Top-level collection the Assembler builds: 'City' (fallback: scene roots)."""
    city = bpy.data.collections.get("City")
    if city is not None:
        return city
    scene = bpy.context.scene
    kids = list(scene.collection.children)
    return kids[0] if len(kids) == 1 else None


def is_collider(ob):
    if ob.name.startswith("COL_"):
        return True
    for coll in ob.users_collection:
        if "Colliders" in coll.name:
            return True
    return False


def is_sun(ob):
    return (ob.type == "LIGHT" and ob.data is not None
            and getattr(ob.data, "type", "") == "SUN")


def world_bbox(ob):
    """World-space AABB (x0,y0,z0,x1,y1,z1). Empties/lights collapse to a point."""
    try:
        mw = ob.matrix_world
    except Exception:
        mw = None
    if mw is None or ob.type in {"LIGHT", "CAMERA", "EMPTY", "SPEAKER", "ARMATURE"} \
            or not getattr(ob, "bound_box", None):
        p = mw.translation if mw is not None else Vector((0.0, 0.0, 0.0))
        return (p.x, p.y, p.z, p.x, p.y, p.z)
    pts = [mw @ Vector(c) for c in ob.bound_box]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def scene_objects(scene):
    """Every object reachable from the scene collection tree (no duplicates)."""
    out, seen = [], set()
    try:
        objs = list(scene.collection.all_objects)
    except Exception:
        objs = []
        stack = [scene.collection]
        while stack:
            c = stack.pop()
            objs.extend(c.objects)
            stack.extend(c.children)
    for ob in objs:
        key = ob.as_pointer()
        if key in seen:
            continue
        seen.add(key)
        out.append(ob)
    return out


def collection_owner_map(city):
    """pointer -> top-level City child name, built ONCE (cheap per-object lookups)."""
    top = {}
    if city is None:
        return top

    def mark(coll, name):
        top[coll.as_pointer()] = name
        for ch in coll.children:
            mark(ch, name)

    for ch in city.children:
        mark(ch, ch.name)
    top[city.as_pointer()] = "City"
    return top


def source_top_collection(ob, owner_map):
    """Which top-level City child (Roads, Buildings, ...) owns this object."""
    for coll in ob.users_collection:
        name = owner_map.get(coll.as_pointer())
        if name:
            return name
    return "(unlinked)" if owner_map else "(none)"


def attach_parent_empties(objs):
    """Add missing EMPTY parents (anchors/handles) so no node hierarchy breaks.

    Only empties are pulled in: a mesh parent would duplicate geometry across
    chunks, which is worse than a re-parented node. Returns how many were added.
    """
    seen = set(ob.as_pointer() for ob in objs)
    queue = list(objs)
    added = 0
    while queue:
        ob = queue.pop()
        parent = ob.parent
        if parent is None:
            continue
        key = parent.as_pointer()
        if key in seen or parent.type != "EMPTY":
            continue
        seen.add(key)
        objs.append(parent)
        queue.append(parent)
        added += 1
    return added


# ---------------------------------------------------------------------------
# tri counting / measuring (evaluated, modifiers applied like export_apply)
# ---------------------------------------------------------------------------
def _mesh_tris(me):
    n = len(me.polygons)
    if n == 0:
        return 0
    try:
        totals = [0] * n
        me.polygons.foreach_get("loop_total", totals)
        return sum(totals) - 2 * n
    except Exception:
        return sum(len(p.vertices) - 2 for p in me.polygons)


def measure(objs):
    """Evaluated triangle / mesh / material / light counts for one district.

    Called while only this district is linked in the scene, so the depsgraph
    stays small even for a 3x3 km master.
    """
    try:
        dg = bpy.context.evaluated_depsgraph_get()
    except Exception:
        dg = None
    tris = meshes = lights = empties = verts = 0
    other = 0
    mats = set()
    for ob in objs:
        if ob.type == "MESH":
            me = None
            if dg is not None:
                try:
                    me = ob.evaluated_get(dg).data
                except Exception:
                    me = None
            if me is None:
                me = ob.data
            if me is not None:
                meshes += 1
                tris += _mesh_tris(me)
                verts += len(me.vertices)
                for slot in getattr(ob, "material_slots", []):
                    if slot.material is not None:
                        mats.add(slot.material.name)
        elif ob.type == "LIGHT":
            lights += 1
        elif ob.type == "EMPTY":
            empties += 1
        else:                      # curves / surfaces / fonts / armatures
            other += 1
    return {"triangle_count": int(tris), "mesh_count": meshes,
            "vertex_count": int(verts), "light_count": lights,
            "empty_count": empties, "other_count": other,
            "materials": sorted(mats)}


def lin_to_srgb(c):
    c = max(0.0, min(1.0, float(c)))
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1.0 / 2.4)) - 0.055


def material_record(m):
    rec = {"hex": None, "linear_rgb": None, "roughness": None,
           "metallic": None, "emissive": None}
    try:
        if not m.use_nodes or m.node_tree is None:
            return rec
        bsdf = next((n for n in m.node_tree.nodes
                     if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf is None:
            return rec
        inp = bsdf.inputs.get("Base Color")
        if inp is not None and hasattr(inp, "default_value"):
            col = [float(v) for v in inp.default_value[:3]]
            rec["linear_rgb"] = [round(v, 5) for v in col]
            rec["hex"] = "#" + "".join(
                "%02x" % int(round(lin_to_srgb(v) * 255.0)) for v in col)
        for key, name in (("roughness", "Roughness"), ("metallic", "Metallic")):
            sock = bsdf.inputs.get(name)
            if sock is not None and hasattr(sock, "default_value"):
                rec[key] = round(float(sock.default_value), 4)
        for name in ("Emission Color", "Emission"):
            sock = bsdf.inputs.get(name)
            if sock is not None and hasattr(sock, "default_value"):
                try:
                    rec["emissive"] = [round(float(v), 4)
                                       for v in sock.default_value[:3]]
                except Exception:
                    pass
                break
    except Exception:
        pass
    return rec


# ---------------------------------------------------------------------------
# scene isolation (works headless: no new/active scene needed)
# ---------------------------------------------------------------------------
def snapshot_scene_root(scene):
    """Remember the scene root exactly (children + directly linked objects)."""
    root = scene.collection
    return {"children": list(root.children), "objects": list(root.objects)}


def isolate(scene, temp_coll, saved):
    """Link ONLY temp_coll into the scene (saved comes from snapshot_scene_root)."""
    root = scene.collection
    for coll in saved["children"]:
        root.children.unlink(coll)
    for ob in saved["objects"]:
        root.objects.unlink(ob)
    root.children.link(temp_coll)
    bpy.context.view_layer.update()


def restore(scene, temp_coll, saved):
    """Put the master scene root back exactly as snapshotted, then verify."""
    root = scene.collection
    try:
        root.children.unlink(temp_coll)
    except Exception:
        pass
    for coll in saved["children"]:
        try:
            root.children.link(coll)
        except Exception:
            pass
    for ob in saved["objects"]:
        try:
            root.objects.link(ob)
        except Exception:
            pass
    bpy.context.view_layer.update()
    now_children = [c.name for c in root.children]
    want_children = [c.name for c in saved["children"]]
    ok = sorted(now_children) == sorted(want_children)
    return ok, {"children_before": want_children,
                "children_after": now_children,
                "objects_before": len(saved["objects"]),
                "objects_after": len(list(root.objects))}


# ---------------------------------------------------------------------------
# exporters
# ---------------------------------------------------------------------------
def op_for(kind):
    try:
        op = getattr(bpy.ops.export_scene, "gltf" if kind == "gltf" else "fbx")
    except Exception:
        return None
    return op


def ensure_exporter(kind):
    """Return the export operator, enabling the bundled add-on/extension if needed."""
    op = op_for(kind)
    if op is not None:
        return op
    for mod in ADDONS[kind]:
        try:
            bpy.ops.preferences.addon_enable(module=mod)
            log("enabled exporter add-on %r" % mod)
        except Exception as exc:
            log("could not enable %r (%s)" % (mod, exc), "warn")
            continue
        op = op_for(kind)
        if op is not None:
            return op
    return None


def filter_kwargs(op, kwargs):
    try:
        props = op.get_rna_type().properties
        allowed = set(p.identifier for p in props)
    except Exception:
        return dict(kwargs), None
    kept = {k: v for k, v in kwargs.items() if k in allowed or k == "filepath"}
    dropped = sorted(set(kwargs) - set(kept))
    return kept, dropped


def call_export(op, kwargs, label):
    """Call the exporter, pruning kwargs it does not know / rejects.

    Returns (ok, error_message_or_None, removed_kwargs, used_kwargs).
    Blender 5.2.3 renamed a few exporter options and some enums are stricter
    than before, so every attempt is fully logged instead of trusted.
    """
    kw, unknown = filter_kwargs(op, kwargs)
    if unknown:
        key = (label.split("/")[-1].rsplit(".", 1)[-1], tuple(unknown))
        if key not in _UNKNOWN_LOGGED:
            _UNKNOWN_LOGGED.add(key)
            log("exporter does not accept %s (dropped for every district)"
                % ", ".join(unknown))
    removed = []
    last_err = None
    for attempt in range(1, 12):
        try:
            op(**kw)
            return True, None, removed, kw
        except Exception as exc:
            last_err = "%s: %s" % (type(exc).__name__, exc)
            log("%s attempt %d failed: %s" % (label, attempt, last_err), "warn")
            msg = str(exc).lower()
            bad = None
            for k in list(kw):
                if k != "filepath" and k.lower() in msg:
                    bad = k
                    break
            if bad is None:
                for cand in DROP_ORDER:
                    if cand in kw:
                        bad = cand
                        break
            if bad is None or bad == "filepath":
                break
            kw.pop(bad, None)
            removed.append(bad)
            log("%s retrying without %r" % (label, bad), "warn")
    return False, last_err, removed, kw


def file_info(path):
    if not os.path.isfile(path):
        return None
    size = os.path.getsize(path)
    if size <= 0:
        return None
    return {"bytes": int(size), "mb": round(size / (1024.0 * 1024.0), 3)}


# ---------------------------------------------------------------------------
# manifests
# ---------------------------------------------------------------------------
def district_manifest(index, name, objs, counts, files, sizes, extra, notes):
    return {
        "schema": SCHEMA,
        "district": name,
        "district_label": DISTRICT_LABEL.get(name, name),
        "generated_at": iso_now(),
        "rect": [round(v, 2) for v in index.rects[name]],
        "unit": "metres",
        "files": files,
        "file_sizes_mb": sizes,
        "object_count": len(objs),
        "mesh_count": counts["mesh_count"],
        "triangle_count": counts["triangle_count"],
        "vertex_count": counts["vertex_count"],
        "light_count": counts["light_count"],
        "empty_count": counts["empty_count"],
        "other_count": counts.get("other_count", 0),
        "materials": counts["materials"],
        "material_count": len(counts["materials"]),
        "source_collections": extra.get("source_collections", {}),
        "cell_rects": index.cell_rects(name),
        "colliders_hidden": True,
        "collider_objects_excluded": extra.get("collider_excluded", 0),
        "membership_rule": index.rule_note(name),
        "notes": notes,
    }


def top_manifest(per_district, palette, totals, opts, warnings):
    return {
        "schema": SCHEMA,
        "generated_at": iso_now(),
        "generator": "modules/export_districts.py",
        "source": {"blend": os.path.relpath(
            os.path.join(ROOT, "out", "city_master.blend"), ROOT),
            "layout": "layout.json"},
        "run_command": ("blender -b out/city_master.blend "
                        "-P modules/export_districts.py -- --out exports"),
        "coordinate_system": {
            "units": "metres",
            "blender": "Z-up, 1 Blender unit = 1 m, +X east, +Y north",
            "gltf": ("glTF 2.0 is Y-up by definition; exported with "
                     "export_yup=True, so the glTF node transforms carry the "
                     "Z-up -> Y-up conversion. Meters stay meters."),
            "fbx": ("binary FBX 7.4, axis_forward='-Z', axis_up='Y', "
                    "apply_scale_options='FBX_SCALE_ALL' (FBX_* units, scale baked in)"),
            "origin": "world origin = layout.json map centre",
        },
        "schema_notes": {
            "files": "map of format -> path relative to this exports directory",
            "rect": "[x0, y0, x1, y1] in metres; membership is bbox-centre based",
            "triangle_count": "evaluated (modifiers applied), fan triangulation",
        },
        "district_order": list(DISTRICT_ORDER),
        "districts": per_district,
        "totals": totals,
        "palette": palette,
        "notes": notes_list(),
        "colliders_hidden": True,
        "lights_included": True,
        "options": opts,
        "warnings": warnings,
    }


def notes_list():
    return [
        "District membership: object bounding-box CENTRE against layout.json "
        "cell rects, then the highway ring band, then civic/remaining. Every "
        "object belongs to exactly one district, except direction-only sun "
        "lights, which ship in all nine so each chunk is lit on its own.",
        "Colliders excluded: objects in *Colliders* collections and COL_* "
        "objects are not exported and stay hidden in the master scene.",
        "Lights included (glTF KHR_lights_punctual / FBX light nodes). Sun "
        "lights are direction-only and ship in every district; positional "
        "lights follow the rect rule.",
        "Map-wide objects (bbox span >= %g m, e.g. the 3000 m ground plane and "
        "full ring decks) are exported once, in the highway chunk." % MAPWIDE_SPAN_M,
        "Empty objects (INT_ANCHOR_*, LOD handles) are exported as nodes so an "
        "engine can hook interiors up; they carry no geometry.",
        "triangle_count is evaluated (modifiers applied, fan triangulation); "
        "geometry-node instances are counted once, at their source mesh.",
        "The world/environment is not part of either format: glTF has no "
        "world node and FBX carries no sky, so the engine supplies ambient "
        "lighting; sun lamps are included per chunk.",
        "The master .blend is opened read-only by this script: it is never "
        "saved or modified on disk.",
    ]


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------
def fmt_rect(r):
    return "x %.0f..%.0f, y %.0f..%.0f" % (r[0], r[2], r[1], r[3])


def write_report(results, totals, failures, warnings, opts):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    lines = [
        "# export_districts.py report",
        "",
        "Run: `blender -b out/city_master.blend -P modules/export_districts.py"
        " -- --out %s`" % os.path.relpath(opts["out"], ROOT),
        "",
        "Output: `%s` (glTF .glb embedded + binary FBX per district)."
        % os.path.relpath(opts["out"], ROOT),
        "Master scene was NOT saved; all isolation happened in memory.",
        "",
        "## Per district",
        "",
        "| District | Rect (m) | Objects | Meshes | Tris | Lights | GLB MB | FBX MB | Status |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for name in DISTRICT_ORDER:
        r = results.get(name)
        if r is None:
            lines.append("| %s | - | - | - | - | - | - | - | not run |" % name)
            continue
        glb = r["files"].get("glb") or {}
        fbx = r["files"].get("fbx") or {}
        status = "ok" if r.get("ok") else "FAILED"
        if r.get("skipped"):
            status = "skipped"
        lines.append("| %s | %s | %d | %d | %d | %d | %s | %s | %s |" % (
            name, fmt_rect(r["rect"]), r["object_count"], r["mesh_count"],
            r["triangle_count"], r["light_count"],
            ("%.1f" % glb["mb"]) if glb else "-",
            ("%.1f" % fbx["mb"]) if fbx else "-", status))
    lines += [
        "",
        "## Totals",
        "",
        "- Districts exported: %d / 9" % totals["districts"],
        "- Objects: %d (meshes %d, lights %d)" % (
            totals["objects"], totals["meshes"], totals["lights"]),
        "- Triangles (evaluated): %d" % totals["triangles"],
        "- Materials: %d" % totals["materials"],
        "- GLB: %.1f MB, FBX: %.1f MB" % (totals["glb_mb"], totals["fbx_mb"]),
        "",
        "## Membership rules",
        "",
    ]
    for name in DISTRICT_ORDER:
        lines.append("- **%s** -- %s" % (name, DISTRICT_RULE_CACHE.get(name, "")))
    lines += ["", "## Failures", ""]
    lines += ["- %s" % f for f in failures] if failures else ["- none"]
    lines += ["", "## Warnings", ""]
    lines += ["- %s" % w for w in warnings] if warnings else ["- none"]
    lines += [
        "",
        "## Notes",
        "",
        "- Colliders excluded from every export (`colliders_hidden: true`).",
        "- Lights included; sun lights are direction-only and appear in every "
        "district, so lighting is consistent per streamed chunk.",
        "- Map-wide objects (ground backdrop, ring decks with >= %g m span) "
        "ship once in the highway chunk." % MAPWIDE_SPAN_M,
        "- Re-running is idempotent: stale district files are deleted first and "
        "all manifests are rewritten.",
        "",
    ]
    path = os.path.join(REPORTS_DIR, "export_report.md")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    log("report -> %s" % path)
    return path


DISTRICT_RULE_CACHE = {}


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    t0 = time.time()
    opts = parse_args(list(sys.argv))
    log("=" * 70)
    log("export_districts.py start (blender %s, pid %d)"
        % (bpy.app.version_string, os.getpid()))
    log("out=%s districts=%s glb=%s fbx=%s dry_run=%s"
        % (opts["out"], ",".join(opts["districts"]), opts["glb"], opts["fbx"],
           opts["dry_run"]))

    layout = read_layout()
    index = DistrictIndex(layout)
    for name in DISTRICT_ORDER:
        DISTRICT_RULE_CACHE[name] = index.rule_note(name)

    scene = bpy.context.scene
    if scene is None:
        raise RuntimeError("no active scene -- open out/city_master.blend first")
    if len(bpy.data.scenes) > 1:
        names = ", ".join(s.name for s in bpy.data.scenes)
        log("file has %d scenes (%s); glTF export is limited to the active one "
            "via use_active_scene where supported" % (len(bpy.data.scenes), names),
            "warn")

    city = city_root_collection()
    if city is None:
        raise RuntimeError(
            "no 'City' collection found -- this script expects the assembled "
            "master (out/city_master.blend). Run modules/assemble.py first.")
    top_level = [c.name for c in city.children]
    owner_map = collection_owner_map(city)
    log("City top-level collections: %s" % (", ".join(top_level) or "(none)"))

    if not opts["dry_run"]:
        os.makedirs(opts["out"], exist_ok=True)
        os.makedirs(REPORTS_DIR, exist_ok=True)

    # ---- classification pass ------------------------------------------------
    bpy.context.view_layer.update()
    try:
        objects = scene_objects(scene)
    except Exception as exc:
        raise RuntimeError("could not enumerate scene objects: %r" % (exc,))
    log("master objects in scene: %d" % len(objects))

    buckets = dict((n, []) for n in DISTRICT_ORDER)
    collider_excluded = 0
    cameras = 0
    no_bbox = 0
    suns = 0
    mapwide = []
    for ob in objects:
        if ob.type == "CAMERA":
            cameras += 1
            continue
        if is_collider(ob):
            collider_excluded += 1
            continue
        try:
            x0, y0, z0, x1, y1, z1 = world_bbox(ob)
        except Exception:
            no_bbox += 1
            continue
        cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
        sx, sy = abs(x1 - x0), abs(y1 - y0)
        if max(sx, sy) >= MAPWIDE_SPAN_M:
            mapwide.append((ob.name, round(sx, 1), round(sy, 1)))
        if is_sun(ob):
            # direction-only: one sun per chunk keeps each export lit on its own
            suns += 1
            for n in DISTRICT_ORDER:
                buckets[n].append(ob)
            continue
        name = index.classify(cx, cy, sx, sy)
        buckets[name].append(ob)

    # per-district source-collection breakdown is built later, per district
    log("classified: %s" % ", ".join(
        "%s=%d" % (n, len(buckets[n])) for n in DISTRICT_ORDER))
    log("colliders excluded: %d, cameras skipped: %d, no-bbox skipped: %d"
        % (collider_excluded, cameras, no_bbox))
    if mapwide:
        log("map-wide objects (-> highway): %s"
            % ", ".join("%s(%.0fx%.0f m)" % m for m in mapwide[:8]),
            "warn" if len(mapwide) > 8 else "info")

    if opts["dry_run"]:
        for name in DISTRICT_ORDER:
            msg = "DRY %-14s %4d objects rect=%s" % (
                name, len(buckets[name]), index.rects[name])
            log(msg)
        log("dry run finished in %.1fs" % (time.time() - t0))
        return 0

    # ---- exporters ---------------------------------------------------------
    gltf_op = ensure_exporter("gltf") if opts["glb"] else None
    fbx_op = ensure_exporter("fbx") if opts["fbx"] else None
    if opts["glb"] and gltf_op is None:
        log("glTF exporter unavailable; glb files will be skipped", "error")
    if opts["fbx"] and fbx_op is None:
        log("FBX exporter unavailable; fbx files will be skipped", "error")

    results = {}
    failures = []
    warnings = []
    if opts["glb"] and gltf_op is None:
        failures.append("glTF exporter operator unavailable (add-on missing)")
    if opts["fbx"] and fbx_op is None:
        failures.append("FBX exporter operator unavailable (add-on missing)")
    if no_bbox:
        warnings.append("%d objects had no usable bbox and were skipped" % no_bbox)
    if cameras:
        warnings.append("%d camera objects were not exported" % cameras)

    used_mats = set()

    for name in opts["districts"]:
        objs = list(buckets[name])
        parent_empties = attach_parent_empties(objs)
        if parent_empties:
            log("[%s] +%d parent empty(s) pulled in to keep the node hierarchy "
                "intact" % (name, parent_empties))
        ddir = os.path.join(opts["out"], name)
        os.makedirs(ddir, exist_ok=True)
        # idempotency: remove previous outputs for this district
        for fn in os.listdir(ddir):
            if fn.lower().endswith(STALE_EXT):
                try:
                    os.remove(os.path.join(ddir, fn))
                except Exception as exc:
                    log("could not remove stale %s (%s)" % (fn, exc), "warn")
        log("-" * 66)
        log("[%s] %d objects -> %s" % (name, len(objs), ddir))

        result = {
            "district": name,
            "rect": index.rects[name],
            "object_count": len(objs),
            "mesh_count": 0,
            "triangle_count": 0,
            "vertex_count": 0,
            "light_count": 0,
            "empty_count": 0,
            "other_count": 0,
            "materials": [],
            "files": {},
            "ok": False,
            "skipped": False,
            "errors": [],
        }
        results[name] = result
        if not objs:
            log("[%s] no objects inside the rect -- empty export skipped" % name,
                "warn")
            result["skipped"] = True
            warnings.append("%s: no objects matched, nothing exported" % name)
            empty_counts = {"mesh_count": 0, "triangle_count": 0,
                            "vertex_count": 0, "light_count": 0,
                            "empty_count": 0, "other_count": 0,
                            "materials": []}
            mf = district_manifest(index, name, objs, empty_counts, {}, {},
                                   {"source_collections": {},
                                    "collider_excluded": collider_excluded},
                                   ["no objects matched this district's rect",
                                    index.rule_note(name)])
            mf["ok"] = False
            mf["errors"] = ["no objects matched"]
            with open(os.path.join(ddir, "manifest.json"), "w") as f:
                json.dump(mf, f, indent=1)
            continue

        temp = bpy.data.collections.new("EXPORT_TMP_%s" % name)
        saved = snapshot_scene_root(scene)
        restored_ok = True
        try:
            for ob in objs:
                try:
                    temp.objects.link(ob)
                except Exception:
                    pass
            isolate(scene, temp, saved)
            log("[%s] isolated: scene root now holds only %s" % (name, temp.name))

            # evaluated counts while the depsgraph holds this district only
            counts = measure(objs)
            result.update({k: counts[k] for k in
                           ("mesh_count", "triangle_count", "vertex_count",
                            "light_count", "empty_count", "other_count",
                            "materials")})
            used_mats.update(counts["materials"])
            log("[%s] %d tris, %d meshes, %d materials, %d lights"
                % (name, counts["triangle_count"], counts["mesh_count"],
                   len(counts["materials"]), counts["light_count"]))

            files = {}
            for kind, op, base in (("glb", gltf_op, GLTF_KWARGS),
                                   ("fbx", fbx_op, FBX_KWARGS)):
                if op is None:
                    continue
                ext = ".glb" if kind == "glb" else ".fbx"
                path = os.path.join(ddir, name + ext)
                kw = dict(base)
                kw["filepath"] = path
                label = "%s/%s%s" % (name, name, ext)
                t1 = time.time()
                ok, err, removed, used = call_export(op, kw, label)
                info = file_info(path)
                if ok and info is None:
                    ok, err = False, "exporter reported success but wrote no file"
                if ok:
                    files[kind] = "%s/%s%s" % (name, name, ext)
                    result["files"][kind] = info
                    log("[%s] %s %.2f MB in %.1fs"
                        % (label, kind, info["mb"], time.time() - t1))
                    if removed:
                        warnings.append("%s: dropped unsupported options %s"
                                        % (label, ", ".join(removed)))
                else:
                    result["errors"].append("%s: %s" % (kind, err))
                    failures.append("%s %s export failed: %s" % (name, kind, err))
                    log("[%s] FAILED %s: %s" % (label, kind, err), "error")
                    # never leave a half-written storey behind
                    if os.path.isfile(path):
                        try:
                            os.remove(path)
                        except Exception:
                            pass

            result["ok"] = bool(result["files"]) and not result["errors"]
            result["file_map"] = files
            sizes = dict((k, v["mb"]) for k, v in result["files"].items())

            # ---- per-district manifest
            src = {}
            for ob in objs:
                k = source_top_collection(ob, owner_map)
                src[k] = src.get(k, 0) + 1
            extra = {"source_collections": dict(sorted(src.items())),
                     "collider_excluded": collider_excluded}
            notes = [index.rule_note(name),
                     "triangle_count is evaluated (modifiers applied)",
                     "colliders excluded (colliders_hidden: true)"]
            if result["light_count"]:
                notes.append("includes %d light(s) (KHR_lights_punctual in glTF)"
                             % result["light_count"])
            if name == "highway" and mapwide:
                notes.append("includes %d map-wide object(s) exported once here"
                             % len(mapwide))
            if parent_empties:
                notes.append("%d parent empty/anchor node(s) pulled in from "
                             "outside the rect so no child node is orphaned"
                             % parent_empties)
            mf = district_manifest(index, name, objs, counts, result["file_map"],
                                   sizes, extra, notes)
            mf["errors"] = result["errors"]
            mf["ok"] = result["ok"]
            with open(os.path.join(ddir, "manifest.json"), "w") as f:
                json.dump(mf, f, indent=1)
            log("[%s] manifest -> %s" % (name, os.path.join(ddir, "manifest.json")))
        except Exception as exc:
            tb = traceback.format_exc()
            result["errors"].append("export: %r" % (exc,))
            failures.append("%s: %r" % (name, exc))
            log("[%s] EXCEPTION %r\n%s" % (name, exc, tb), "error")
            # leave a manifest that explains the partial result
            try:
                bad_counts = dict((k, result.get(k, 0)) for k in
                                  ("mesh_count", "triangle_count",
                                   "vertex_count", "light_count",
                                   "empty_count", "other_count"))
                bad_counts["materials"] = result.get("materials", [])
                mf = district_manifest(
                    index, name, objs, bad_counts, result.get("file_map", {}),
                    {}, {"source_collections": {},
                         "collider_excluded": collider_excluded},
                    ["export raised: %r" % (exc,)])
                mf["ok"] = False
                mf["errors"] = result["errors"]
                with open(os.path.join(ddir, "manifest.json"), "w") as f:
                    json.dump(mf, f, indent=1)
            except Exception:
                pass
        finally:
            # ALWAYS restore the master scene root, even after an exception
            # (restore is idempotent, so it is safe when isolation never ran)
            try:
                restored_ok, rinfo = restore(scene, temp, saved)
                if not restored_ok:
                    log("[%s] scene root NOT restored correctly: %s"
                        % (name, rinfo), "error")
                    failures.append("%s: scene root restore mismatch" % name)
            except Exception as exc:
                restored_ok = False
                log("[%s] restore failed: %r" % (name, exc), "error")
                failures.append("%s: restore failed: %r" % (name, exc))
            try:
                bpy.data.collections.remove(temp)
            except Exception:
                pass
            bpy.context.view_layer.update()
            # cheap sanity check: the object census must be exactly what it was
            try:
                now_n = len(scene_objects(scene))
                if now_n != len(objects):
                    log("[%s] scene object census changed: %d -> %d "
                        "(reported, not fatal)" % (name, len(objects), now_n),
                        "warn")
                    warnings.append("%s: object census %d -> %d"
                                    % (name, len(objects), now_n))
            except Exception:
                pass

        if opts["purge"]:
            try:
                before = (len(bpy.data.meshes), len(bpy.data.materials))
                bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=False,
                                       do_recursive=True)
                after = (len(bpy.data.meshes), len(bpy.data.materials))
                if before != after:
                    log("[%s] purged orphans (meshes %d->%d, materials %d->%d)"
                        % (name, before[0], after[0], before[1], after[1]))
            except Exception as exc:
                log("[%s] orphan purge skipped (%r)" % (name, exc), "warn")

        if not restored_ok:
            failures.append("aborted remaining districts after restore failure")
            log("aborting: master scene root is inconsistent", "error")
            break

    # ---- top-level manifest -------------------------------------------------
    per = []
    for name in opts["districts"]:
        r = results.get(name)
        if r is None:
            continue
        per.append({
            "district": name,
            "label": DISTRICT_LABEL.get(name, name),
            "rect": [round(v, 2) for v in r["rect"]],
            "object_count": r["object_count"],
            "mesh_count": r["mesh_count"],
            "triangle_count": r["triangle_count"],
            "light_count": r["light_count"],
            "files": dict((k, "%s/%s%s" % (name, name,
                                           ".glb" if k == "glb" else ".fbx"))
                          for k in r["files"]),
            "file_sizes_mb": dict((k, v["mb"]) for k, v in r["files"].items()),
            "ok": r["ok"],
            "skipped": r.get("skipped", False),
            "manifest": "%s/manifest.json" % name,
        })

    palette = {}
    for m in bpy.data.materials:
        if m is None or m.name not in used_mats:
            continue
        palette[m.name] = material_record(m)

    # sun lights appear in every chunk: subtract the duplicate copies so the
    # totals describe unique city objects
    overlap = suns * max(0, len(opts["districts"]) - 1)
    totals = {
        "districts": sum(1 for p in per if p["ok"]),
        "districts_total": len(DISTRICT_ORDER),
        "objects": sum(r["object_count"] for r in results.values()) - overlap,
        "meshes": sum(r["mesh_count"] for r in results.values()),
        "triangles": sum(r["triangle_count"] for r in results.values()),
        "lights": sum(r["light_count"] for r in results.values()) - overlap,
        "sun_lights_per_chunk": suns,
        "materials": len(used_mats),
        "glb_mb": round(sum(v["mb"] for r in results.values()
                            for k, v in r["files"].items() if k == "glb"), 2),
        "fbx_mb": round(sum(v["mb"] for r in results.values()
                            for k, v in r["files"].items() if k == "fbx"), 2),
    }

    top = top_manifest(per, dict(sorted(palette.items())), totals,
                       {"out": os.path.relpath(opts["out"], ROOT),
                        "districts": opts["districts"],
                        "formats": [f for f, on in (("glb", opts["glb"]),
                                                    ("fbx", opts["fbx"])) if on],
                        "dry_run": False},
                       warnings)
    top["failures"] = failures
    with open(os.path.join(opts["out"], "manifest.json"), "w") as f:
        json.dump(top, f, indent=1)
    log("top-level manifest -> %s"
        % os.path.join(opts["out"], "manifest.json"))

    write_report(results, totals, failures, warnings, opts)

    summary = {"ok": not failures, "totals": totals,
               "failures": failures, "warnings": warnings,
               "out": opts["out"],
               "elapsed_s": round(time.time() - t0, 1)}
    try:
        with open(SUMMARY_PATH, "w") as f:
            json.dump(summary, f, indent=1)
    except Exception:
        pass

    log("done: %d/%d districts ok, %d tris, %.1f MB glb + %.1f MB fbx, %.1fs"
        % (totals["districts"], len(opts["districts"]), totals["triangles"],
           totals["glb_mb"], totals["fbx_mb"], time.time() - t0))
    if failures:
        log("%d failure(s)" % len(failures), "error")
    log("master .blend NOT saved (in-memory isolation only)")
    return 0 if not failures else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        log("FATAL: %r\n%s" % (exc, traceback.format_exc()), "error")
        sys.exit(1)
