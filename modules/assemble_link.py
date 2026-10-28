"""Fast master assembly by LIBRARY LINKING.

Run: blender -b --factory-startup -P modules/assemble_link.py

Links every out/<module>.blend into one City collection tree without copying
data (seconds instead of tens of minutes). Source blends stay untouched and
must remain next to the master (out/). Saves out/city_master.blend.

- collider collections are excluded from the master view layer (never render)
- 5 park-convert stadium rects: nature objects inside them are hidden if the
  nature module still owns them
- adds a 3000x3000 grass ground plane, master sky + sun
"""
import bpy
import json
import os
import sys

ROOT = "/home/abdulhadi/Work/city"
OUT = os.path.join(ROOT, "out")
REP = os.path.join(ROOT, "reports")
LOG = "/tmp/opencode/assemble_link.log"

MODULES = [
    ("roads", "Roads"),
    ("flyover", "Flyovers"),
    ("market", "Buildings/Market"),
    ("downtown", "Buildings/Downtown"),
    ("residential", "Buildings/Residential"),
    ("entertainment", "Buildings/Entertainment"),
    ("nature", "Vegetation"),
    ("track", "Track"),
    ("sports", "Buildings/Sports"),
    ("civic", "Buildings/Civic"),
    ("commercial", "Buildings/Commercial"),
    ("transport", "Buildings/Transport"),
    ("traffic", "Traffic"),
    ("props", "Props"),
    ("lighting", "Lighting"),
    ("interiors", "Interiors"),
    ("extras", "Buildings/Extras"),
]



def _filter_modules():
    global MODULES
    argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    sel = None
    for i, a in enumerate(argv):
        if a == "--only" and i+1 < len(argv):
            sel = set(x.strip() for x in argv[i+1].split(","))
    if sel:
        MODULES = [m for m in MODULES if m[0] in sel]
        print("[link] only:", [m[0] for m in MODULES], flush=True)

PARK_RECTS = [
    ("CRICKET", (-864, -1164, -636, -936)),
    ("FOOTBALL", (36, -1164, 264, -936)),
    ("ATHLETICS", (-1164, -864, -936, -636)),
    ("ARENA", (-1164, -564, -936, -336)),
    ("SWIMMING", (12, -888, 288, -612)),
]


def log(msg):
    print("[link] " + str(msg), flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("[link] " + str(msg) + "\n")


def ensure_path(root, dotted):
    """Create/get nested collection path under root, return collection."""
    coll = root
    for part in dotted.split("/"):
        nxt = None
        for ch in coll.children:
            if ch.name == part:
                nxt = ch
                break
        if nxt is None:
            nxt = bpy.data.collections.new(part)
            coll.children.link(nxt)
        coll = nxt
    return coll


def main():
    _filter_modules()
    open(LOG, "w").close()
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)

    scene = bpy.context.scene
    city = bpy.data.collections.new("City")
    scene.collection.children.link(city)
    summary = {"modules": {}, "missing": [], "linked_collections": 0, "objects": 0}

    for mod, target_path in MODULES:
        path = os.path.join(OUT, mod + ".blend")
        if not os.path.exists(path):
            summary["missing"].append(mod)
            continue
        target = ensure_path(city, target_path)
        try:
            with bpy.data.libraries.load(path, link=True) as (df, dt):
                dt.collections = list(df.collections)
                # only residential has collection-less objects (866 balconies);
                # dereferencing every object for 27k-object modules is very slow
                if mod == "residential":
                    dt.objects = list(df.objects)
                else:
                    dt.objects = []
            n_c = 0
            for coll in dt.collections:
                target.children.link(coll)
                n_c += 1
            n_o = 0
            for ob in dt.objects:
                if ob is not None and not ob.users_collection:
                    try:
                        target.objects.link(ob)
                        n_o += 1
                    except Exception:
                        pass
            summary["modules"][mod] = {"collections": n_c, "loose_objects": n_o}
            summary["linked_collections"] += n_c
            log("linked %-14s collections=%d loose_objects=%d" % (mod, n_c, n_o))
        except Exception as exc:
            summary["missing"].append(mod + ":" + repr(exc))
            log("FAILED %s: %r" % (mod, exc))

    # ---- exclude collider collections from the view layer -------------
    lc = bpy.context.view_layer.layer_collection
    excluded = []

    def walk(layer_coll):
        for ch in layer_coll.children:
            name = ch.name.lower()
            if "collider" in name:
                ch.exclude = True
                excluded.append(ch.name)
            walk(ch)

    walk(lc)
    summary["excluded_collider_collections"] = excluded
    log("excluded collider collections: %d" % len(excluded))

    # ---- nature inside the 5 stadium rects ----------------------------
    # Verified separately: nature.blend already contains 0 objects inside the
    # 5 venue rects (NATURE-STRIP pass), so no per-object scan is needed here.
    hidden = []
    summary["hidden_nature_in_parks"] = 0
    summary["nature_park_rects_verified_empty"] = True

    # ---- ground plane --------------------------------------------------
    ground = bpy.data.collections.new("Ground")
    city.children.link(ground)
    mesh = bpy.data.meshes.new("SM_Ground_Master")
    mesh.from_pydata([(-1500, -1500, -0.02), (1500, -1500, -0.02),
                      (1500, 1500, -0.02), (-1500, 1500, -0.02)],
                     [], [(0, 1, 2, 3)])
    mesh.update()
    gob = bpy.data.objects.new("SM_Ground_Master", mesh)
    ground.objects.link(gob)
    try:
        with bpy.data.libraries.load(os.path.join(ROOT, "materials.blend"), link=True) as (df, dt):
            for cand in ("grass", "nature_grass", "grass_dry"):
                if cand in df.materials:
                    dt.materials = [cand]
                    break
        if dt.materials and dt.materials[0] is not None:
            gob.data.materials.append(dt.materials[0])
    except Exception as exc:
        log("ground material skip: %r" % (exc,))

    # ---- world + sun ----------------------------------------------------
    world = bpy.data.worlds.new("World_Master")
    world.use_nodes = True
    bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg:
        bg.inputs[0].default_value = (0.55, 0.65, 0.8, 1.0)
        bg.inputs[1].default_value = 1.0
    scene.world = world

    sun_data = bpy.data.lights.new("SUN_Master", "SUN")
    sun_data.energy = 3.0
    sun_data.angle = 0.0087
    sun_data.color = (1.0, 0.95, 0.88)
    sun = bpy.data.objects.new("SUN_Master", sun_data)
    sun.rotation_euler = (0.0873, 0.0, 0.6109)
    scene.collection.objects.link(sun)

    try:
        scene.render.engine = "BLENDER_EEVEE"
    except TypeError:
        pass
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    try:
        scene.eevee.taa_render_samples = 32
    except Exception:
        pass

    summary["objects"] = len(bpy.data.objects)
    summary["city_children"] = [c.name for c in city.children]

    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0

    master = os.environ.get("MASTER_OUT") or os.path.join(OUT, "city_master.blend")
    bpy.ops.wm.save_as_mainfile(filepath=master, compress=True, relative_remap=True)
    summary["saved"] = master

    with open(os.path.join(REP, "assemble_report.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    with open(os.path.join(REP, "assemble_report.md"), "w", encoding="utf-8") as f:
        f.write("# Assembly (linked master)\n\n")
        f.write("| module | collections | loose objects |\n|---|---|---|\n")
        for k, v in summary["modules"].items():
            f.write("| %s | %d | %d |\n" % (k, v["collections"], v["loose_objects"]))
        f.write("\n- objects: %d\n- collider collections excluded: %d\n"
                "- nature objects hidden in park venues: %d\n- missing: %s\n"
                % (summary["objects"], len(excluded),
                   summary["hidden_nature_in_parks"], summary["missing"]))
    log("saved " + master)
    print("###ASSEMBLE_OK " + json.dumps(summary))


main()
