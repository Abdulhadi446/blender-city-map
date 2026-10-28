"""citykit — shared helper library for every city-building agent.

Import it at the top of your module script:

    import sys, os
    sys.path.insert(0, "/home/abdulhadi/Work/city/modules")   # if not already on sys.path
    import citykit as ck

    layout = ck.read_layout()
    mats   = ck.read_parcels("R")
    coll   = ck.ensure_collection("MyModule", parent="Meshes")
    ob     = ck.dup_mesh(src, "SM_Wall_01", matrix=loc)
    ck.assign(ob, "brick_red")
    ck.apply_all_transforms(ob)
    ck.save_blend(ck.OUT_DIR / "my_module.blend")
    ck.write_report("my_module", {"tris": ck.tri_count(coll)})

Everything is defensive: wrong inputs raise RuntimeError with an actionable message
(never a bare KeyError / AttributeError).
"""
from __future__ import annotations

import json
import math
import os
import time

# --------------------------------------------------------------------------
# paths  ("/city" does not exist — the canonical root is this directory)
# --------------------------------------------------------------------------
CITY_ROOT = "/home/abdulhadi/Work/city"
OUT_DIR = os.path.join(CITY_ROOT, "out")
MODULES_DIR = os.path.join(CITY_ROOT, "modules")
REPORTS_DIR = os.path.join(CITY_ROOT, "reports")
LAYOUT_PATH = os.path.join(CITY_ROOT, "layout.json")
MATERIALS_BLEND = os.path.join(CITY_ROOT, "materials.blend")
MATERIALS_INDEX = os.path.join(CITY_ROOT, "materials.json")
PARCEL_DIR = CITY_ROOT

for _d in (OUT_DIR, MODULES_DIR, REPORTS_DIR):
    if not os.path.isdir(_d):
        os.makedirs(_d, exist_ok=True)

try:
    import bpy
    from mathutils import Matrix, Vector
except Exception:  # allow importing outside Blender (layout reading only)
    bpy = None
    Matrix = Vector = None


# --------------------------------------------------------------------------
# layout access
# --------------------------------------------------------------------------
_LAYOUT_CACHE = {}


def read_layout(force=False):
    """Return the parsed layout.json (cached). Raises RuntimeError if missing/broken."""
    if not force and "layout" in _LAYOUT_CACHE:
        return _LAYOUT_CACHE["layout"]
    if not os.path.isfile(LAYOUT_PATH):
        raise RuntimeError(
            "layout.json not found at %s. Run: cd %s && python3 generate_layout.py --split"
            % (LAYOUT_PATH, CITY_ROOT))
    try:
        with open(LAYOUT_PATH) as f:
            d = json.load(f)
    except Exception as e:
        raise RuntimeError("layout.json is not valid JSON (%s): %s" % (LAYOUT_PATH, e))
    for key in ("parcels", "road_edges", "road_nodes", "districts", "stats"):
        if key not in d:
            raise RuntimeError("layout.json is missing top-level key %r" % key)
    _LAYOUT_CACHE["layout"] = d
    return d


_DISTRICT_KEYS = ("R", "D", "E", "M", "G", "I", "T")


def read_parcels(district_key):
    """Return the parcel list for one district, reading parcels_<key>.json when present
    (falls back to filtering layout.json)."""
    key = str(district_key).strip().upper()
    if key not in _DISTRICT_KEYS:
        raise RuntimeError("Unknown district %r — expected one of %s"
                           % (district_key, ", ".join(_DISTRICT_KEYS)))
    if key in _LAYOUT_CACHE:
        return _LAYOUT_CACHE[key]
    path = os.path.join(PARCEL_DIR, "parcels_%s.json" % key)
    if os.path.isfile(path):
        with open(path) as f:
            data = json.load(f)
        parcels = data["parcels"] if isinstance(data, dict) else data
        wrong = [p.get("id") for p in parcels if p.get("district") != key]
        if wrong:
            raise RuntimeError("%s contains %d parcels of another district (e.g. %s)"
                               % (path, len(wrong), wrong[0]))
    else:
        parcels = [p for p in read_layout()["parcels"] if p.get("district") == key]
    _LAYOUT_CACHE[key] = parcels
    return parcels


def read_road_edges():
    return read_layout()["road_edges"]


def read_road_nodes():
    return read_layout()["road_nodes"]


# --------------------------------------------------------------------------
# materials
# --------------------------------------------------------------------------
_MAT_CACHE = {}
_AVAIL_CACHE = None


def _available_materials(refresh=False):
    """Names present in materials.blend (cached)."""
    global _AVAIL_CACHE
    if _AVAIL_CACHE is not None and not refresh:
        return _AVAIL_CACHE
    if not os.path.isfile(MATERIALS_BLEND):
        raise RuntimeError("materials.blend missing at %s — the material library must be "
                           "built first (blender -b -P modules/materials_lib.py)" % MATERIALS_BLEND)
    if bpy is None:
        raise RuntimeError("append_material() needs Blender — run this inside blender -b -P")
    with bpy.data.libraries.load(MATERIALS_BLEND, link=False) as (src, _dst):
        _AVAIL_CACHE = sorted(n for n in src.materials if n)
    return _AVAIL_CACHE


def append_material(name):
    """Append one material from materials.blend (cached). Raises RuntimeError listing every
    available name when `name` does not exist."""
    if not isinstance(name, str) or not name:
        raise RuntimeError("append_material(name) needs a non-empty material name, got %r" % (name,))
    if name in _MAT_CACHE:
        return _MAT_CACHE[name]
    if bpy is None:
        raise RuntimeError("append_material() needs Blender — run this inside blender -b -P")
    existing = bpy.data.materials.get(name)
    if existing is not None and existing.library is None:
        _MAT_CACHE[name] = existing
        return existing
    available = _available_materials()
    if name not in available:
        raise RuntimeError(
            "Material %r not found in %s (%d available).\nAvailable: %s\n"
            "If you need a new one, request it in your report — do not create materials."
            % (name, MATERIALS_BLEND, len(available), ", ".join(available)))
    with bpy.data.libraries.load(MATERIALS_BLEND, link=False) as (src, dst):
        dst.materials = [name]
    m = bpy.data.materials.get(name)
    if m is None:
        raise RuntimeError("Append of %r reported success but bpy.data.materials has no such entry"
                           % name)
    _MAT_CACHE[name] = m
    return m


def assign(obj, mat_name):
    """Assign a library material to an object (or directly to a Mesh/curve data block).

    Materials live on the mesh data, so linked duplicates created with dup_mesh() share
    the slot. To give ONE duplicate its own material, do:
        slot = obj.material_slots[0]; slot.link = 'OBJECT'; slot.material = ck.append_material(m)
    """
    m = append_material(mat_name)
    data = getattr(obj, "data", obj)
    mats = getattr(data, "materials", None)
    if mats is None:
        raise RuntimeError("assign(): %r has no material slots (type=%s)"
                           % (getattr(obj, "name", obj), getattr(data, "name", "?")))
    if len(mats) == 0:
        mats.append(m)
    else:
        mats[0] = m
        if getattr(obj, "type", None) == "MESH":
            for p in data.polygons:
                p.material_index = 0
    return m


# --------------------------------------------------------------------------
# collections / objects
# --------------------------------------------------------------------------
def ensure_collection(name, parent=None):
    """Get-or-create a collection (optionally child of another collection) and link it
    into the scene. `parent` may be a Collection or a collection name."""
    if bpy is None:
        raise RuntimeError("ensure_collection() needs Blender — run this inside blender -b -P")
    if not isinstance(name, str) or not name:
        raise RuntimeError("ensure_collection(name) needs a name, got %r" % (name,))
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        created = True
    else:
        created = False
    if parent is not None:
        parent_coll = parent if hasattr(parent, "children") else bpy.data.collections.get(str(parent))
        if parent_coll is None:
            raise RuntimeError("ensure_collection(): parent collection %r does not exist" % (parent,))
        if coll.name not in {c.name for c in parent_coll.children}:
            parent_coll.children.link(coll)
    else:
        scene = bpy.context.scene
        if scene is not None and coll.name not in {c.name for c in scene.collection.children} \
                and coll is not scene.collection and coll.name != scene.collection.name:
            if not any(c == coll for c in scene.collection.children):
                scene.collection.children.link(coll)
    if created:
        print("  [citykit] created collection %s" % name)
    return coll


def link_obj(obj, coll):
    """Link an object into a collection (idempotent). Returns the object."""
    if obj is None:
        raise RuntimeError("link_obj(): obj is None")
    if coll is None:
        raise RuntimeError("link_obj(): collection is None")
    if hasattr(coll, "objects") is False:
        raise RuntimeError("link_obj(): %r is not a collection" % (coll,))
    if obj.name not in coll.objects:
        coll.objects.link(obj)
    return obj


def dup_mesh(src_obj, name, matrix=None):
    """Linked duplicate: shares the Mesh data with src_obj (never a unique copy)."""
    if src_obj is None:
        raise RuntimeError("dup_mesh(): src_obj is None")
    if getattr(src_obj, "data", None) is None:
        raise RuntimeError("dup_mesh(): %r has no data block to share" % (src_obj.name,))
    new = bpy.data.objects.new(name, src_obj.data)
    if matrix is not None:
        new.matrix_world = Matrix(matrix) if not hasattr(matrix, "copy") else matrix.copy()
    else:
        new.matrix_world = src_obj.matrix_world.copy()
    # copy display / visibility flags that matter for rendering
    for attr in ("hide_render", "hide_viewport"):
        try:
            setattr(new, attr, getattr(src_obj, attr))
        except Exception:
            pass
    scene = bpy.context.scene
    if scene is not None:
        link_obj(new, scene.collection)
    return new


def instance_collection(src_coll, name, loc, rot_z=0.0, scale=1.0):
    """Collection-instance empty at loc/rot/scale (the cheap way to repeat a kit)."""
    if src_coll is None:
        raise RuntimeError("instance_collection(): src_coll is None")
    if hasattr(src_coll, "objects") is False:
        raise RuntimeError("instance_collection(): %r is not a collection" % (src_coll,))
    empty = bpy.data.objects.new(name, None)
    empty.instance_type = "COLLECTION"
    empty.instance_collection = src_coll
    empty.location = (float(loc[0]), float(loc[1]), float(loc[2]) if len(loc) > 2 else 0.0)
    empty.rotation_euler = (0.0, 0.0, float(rot_z))
    s = float(scale)
    empty.scale = (s, s, s)
    scene = bpy.context.scene
    if scene is not None:
        link_obj(empty, scene.collection)
    return empty


def update_view():
    """Force a depsgraph evaluation so Object.matrix_world reflects the last
    apply_all_transforms() call. Cheap enough to call once after a batch; Blender
    does it automatically before rendering/export anyway."""
    if bpy is None:
        raise RuntimeError("update_view() needs Blender")
    bpy.context.view_layer.update()


def apply_all_transforms(obj):
    """Bake the object's local transform into its mesh, exactly like Blender's
    Object > Apply > All Transforms (world-space geometry is unchanged; the origin ends
    up at the world origin). Returns True. Empties / collection instances keep their
    transform on purpose — zeroing them would move the whole instanced kit — so they
    return False without error. Note: Object.matrix_world is only refreshed by the next
    depsgraph evaluation — call update_view() if you need it straight away."""
    if obj is None:
        raise RuntimeError("apply_all_transforms(): obj is None")
    data = getattr(obj, "data", None)
    if data is None or not hasattr(data, "transform"):
        return False
    mat = obj.matrix_basis.copy()
    data.transform(mat)
    data.update()
    obj.matrix_basis = Matrix.Identity(4)
    return True


# --------------------------------------------------------------------------
# stats / reporting
# --------------------------------------------------------------------------
def tri_count(obj_or_collection):
    """Triangle count (ngons are fan-triangulated). Accepts an object, a mesh, a
    collection, or None. Collection instances are NOT expanded — count the source once."""
    if obj_or_collection is None:
        return 0
    o = obj_or_collection
    # collection?
    if hasattr(o, "objects") and hasattr(o, "children"):
        total = 0
        for ob in o.objects:
            total += tri_count(ob)
        for ch in o.children:
            total += tri_count(ch)
        return total
    data = getattr(o, "data", o)
    polys = getattr(data, "polygons", None)
    if polys is None:
        return 0
    total = 0
    for p in polys:
        n = len(p.vertices)
        if n >= 3:
            total += n - 2
    return total


def scene_tri_count():
    """Triangle count of every unique data block in the file (instances counted once)."""
    if bpy is None:
        raise RuntimeError("scene_tri_count() needs Blender")
    seen = set()
    total = 0
    for ob in bpy.data.objects:
        data = getattr(ob, "data", None)
        key = data.as_pointer() if data is not None else ("empty", ob.as_pointer())
        if key in seen:
            continue
        seen.add(key)
        total += tri_count(ob)
    return total


def save_blend(path=None):
    """Save the current file (default: out/<blend name>.blend). Returns the path."""
    if bpy is None:
        raise RuntimeError("save_blend() needs Blender")
    if path is None:
        path = os.path.join(OUT_DIR, "untitled.blend")
    path = os.path.abspath(path)
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
    print("  [citykit] saved %s (%.1f MB)" % (path, os.path.getsize(path) / 1e6))
    return path


def write_report(module_name, payload):
    """Write reports/<module_name>_report.json (payload must be JSON-serialisable)."""
    if not isinstance(module_name, str) or not module_name:
        raise RuntimeError("write_report(module_name, payload): bad module name %r" % (module_name,))
    safe = "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in module_name)
    path = os.path.join(REPORTS_DIR, "%s_report.json" % safe)
    data = dict(payload)
    data["_module"] = safe
    data["_written"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(path, "w") as f:
        json.dump(data, f, indent=1, default=str)
    print("  [citykit] report -> %s" % path)
    return path


def make_preview(path, cam_pos, cam_target, engine="BLENDER_EEVEE", res=(1920, 1080),
                 sun_elev=35.0, sun_azim=-40.0, sun_energy=3.5, samples=32, lens=35.0):
    """Render a preview still. A temporary camera + sun (+ world) are created and removed
    again, so the saved .blend stays clean. Returns the image path."""
    if bpy is None:
        raise RuntimeError("make_preview() needs Blender")
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    scene = bpy.context.scene
    prev = dict(engine=scene.render.engine, x=scene.render.resolution_x,
                y=scene.render.resolution_y, fp=scene.render.filepath,
                vs=scene.view_settings.view_transform, cam=scene.camera)
    tmp = []
    made_world = False
    try:
        cam_data = bpy.data.cameras.new("TMP_PREVIEW_CAM")
        cam_data.lens = float(lens)
        p, t = Vector(cam_pos), Vector(cam_target)
        # aerial previews sit hundreds of metres from their target: the default
        # 100 m clip_end would render an empty frame
        dist = (t - p).length
        cam_data.clip_start = max(0.1, dist / 2000.0)
        cam_data.clip_end = max(1000.0, dist * 4.0)
        cam = bpy.data.objects.new("TMP_PREVIEW_CAM", cam_data)
        scene.collection.objects.link(cam)
        tmp.append(cam)
        cam.location = p
        cam.rotation_euler = (t - p).to_track_quat("-Z", "Y").to_euler()
        scene.camera = cam

        sun_data = bpy.data.lights.new("TMP_PREVIEW_SUN", type="SUN")
        sun_data.energy = sun_energy
        sun_data.angle = math.radians(1.5)
        sun = bpy.data.objects.new("TMP_PREVIEW_SUN", sun_data)
        sun.rotation_euler = (math.radians(90.0 - sun_elev), 0.0, math.radians(sun_azim))
        scene.collection.objects.link(sun)
        tmp.append(sun)

        world = scene.world
        if world is None:
            world = bpy.data.worlds.new("TMP_PREVIEW_WORLD")
            scene.world = world
            tmp.append(world)
            made_world = True
        if made_world:
            world.use_nodes = True
            bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
            if bg is not None:
                bg.inputs[0].default_value = (0.45, 0.55, 0.72, 1.0)
                bg.inputs[1].default_value = 0.7

        try:
            scene.render.engine = engine
        except Exception as e:
            raise RuntimeError("make_preview(): unknown engine %r (%s)" % (engine, e))
        scene.render.resolution_x, scene.render.resolution_y = int(res[0]), int(res[1])
        scene.render.resolution_percentage = 100
        scene.render.filepath = path
        if engine == "BLENDER_EEVEE":
            for attr, val in (("taa_render_samples", samples),):
                try:
                    setattr(scene.eevee, attr, val)
                except Exception:
                    pass
        bpy.ops.render.render(write_still=True)
    finally:
        for item in tmp:
            try:
                if isinstance(item, bpy.types.Object):
                    bpy.data.objects.remove(item, do_unlink=True)
                elif isinstance(item, bpy.types.World):
                    if scene.world is item:
                        scene.world = None
                    bpy.data.worlds.remove(item)
            except Exception as e:
                print("  [citykit] preview cleanup warning:", e)
        scene.camera = prev["cam"]
        scene.render.engine = prev["engine"]
        scene.render.resolution_x, scene.render.resolution_y = prev["x"], prev["y"]
        scene.render.filepath = prev["fp"]
        try:
            scene.view_settings.view_transform = prev["vs"]
        except Exception:
            pass
    if not os.path.isfile(path):
        raise RuntimeError("make_preview(): render produced no file at %s" % path)
    print("  [citykit] preview -> %s" % path)
    return path


__all__ = [
    "CITY_ROOT", "OUT_DIR", "MODULES_DIR", "REPORTS_DIR", "LAYOUT_PATH", "MATERIALS_BLEND",
    "read_layout", "read_parcels", "read_road_edges", "read_road_nodes",
    "append_material", "assign", "ensure_collection", "link_obj", "dup_mesh",
    "instance_collection", "apply_all_transforms", "update_view", "tri_count", "scene_tri_count",
    "save_blend", "write_report", "make_preview",
]
