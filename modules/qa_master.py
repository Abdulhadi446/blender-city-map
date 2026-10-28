"""QA inspector for out/city_master.blend — read-only.

Run:  blender -b out/city_master.blend -P modules/qa_master.py -- --render 1

Checks
  1. scene census: objects/meshes/tris per top-level City child
  2. materials: missing images, unassigned meshes
  3. render hygiene: Colliders collections/objects still renderable?
  4. footprint: objects outside the 3 km map, geometry below ground
  5. props sanity: SM_Cable_ / kit objects far from origin
  6. optional 3 renders (aerial, market street, downtown) -> out/qa_*.png
Writes reports/qa_master.{json,md}
"""
import bpy
import json
import math
import os
import sys

ROOT = "/home/abdulhadi/Work/city"
OUT = os.path.join(ROOT, "out")
REP = os.path.join(ROOT, "reports")
HALF = 1500.0


def argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def tri_count(ob):
    me = ob.data
    if me is None:
        return 0
    return sum(len(p.vertices) - 2 for p in me.polygons)


def main():
    args = argv()
    do_render = "--render" in args
    scene = bpy.context.scene

    # --- census per top collection -------------------------------------
    city = bpy.data.collections.get("City")
    census = {}
    total_obj = total_tri = 0
    for ob in bpy.data.objects:
        total_obj += 1
        if ob.type == "MESH":
            total_tri += tri_count(ob)
    if city:
        def collect_objs(coll, seen):
            for o in coll.objects:
                if o.name not in seen:
                    seen[o.name] = o
            for ch in coll.children:
                collect_objs(ch, seen)

        for ch in city.children:
            seen = {}
            collect_objs(ch, seen)
            tris = sum(tri_count(o) for o in seen.values() if o.type == "MESH")
            census[ch.name] = {"objects": len(seen), "tris": tris}

    # --- materials / images --------------------------------------------
    missing_imgs = []
    for img in bpy.data.images:
        if img.type != "IMAGE":
            continue
        if img.packed_file:
            continue
        p = bpy.path.abspath(img.filepath) if img.filepath else ""
        if not p or not os.path.exists(p):
            missing_imgs.append({"image": img.name, "path": img.filepath})

    no_mat = [o.name for o in bpy.data.objects
              if o.type == "MESH" and not o.material_slots and not o.name.startswith("COL_")]
    col_render_visible = []
    for coll in bpy.data.collections:
        if coll.name.endswith("Colliders") or "/Colliders" in coll.name:
            if not coll.hide_render:
                col_render_visible.append(coll.name)
    col_obj_visible = [o.name for o in bpy.data.objects
                       if o.name.startswith("COL_") and not o.hide_render]

    # --- footprint ------------------------------------------------------
    outside, below = [], []
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        c = ob.matrix_world.translation
        if abs(c.x) > HALF or abs(c.y) > HALF:
            outside.append({"name": ob.name, "x": round(c.x, 1),
                            "y": round(c.y, 1), "z": round(c.z, 1)})
        try:
            zs = [(ob.matrix_world @ __import__("mathutils").Vector(c)).z for c in ob.bound_box]
            zmin = min(zs)
            if zmin < -1.0:
                below.append({"name": ob.name, "zmin": round(zmin, 2)})
        except Exception:
            pass

    # --- props kit sanity ----------------------------------------------
    far_kit = []
    for ob in bpy.data.objects:
        if ob.type != "MESH" or ob.data.users < 2:
            continue
        c = ob.matrix_world.translation
        if abs(c.x) > 2000 or abs(c.y) > 2000:
            far_kit.append({"name": ob.name, "x": round(c.x, 1),
                            "y": round(c.y, 1), "users": ob.data.users})

    # --- world / sun -----------------------------------------------------
    world = scene.world.name if scene.world else None
    suns = [o.name for o in bpy.data.objects if o.type == "LIGHT" and o.data.type == "SUN"]
    lights = sum(1 for o in bpy.data.objects if o.type == "LIGHT")

    res = {
        "blend": bpy.data.filepath,
        "objects": total_obj,
        "meshes": len(bpy.data.meshes),
        "triangles": total_tri,
        "city_children": census,
        "missing_images": missing_imgs[:50],
        "missing_image_count": len(missing_imgs),
        "meshes_without_material": no_mat[:50],
        "meshes_without_material_count": len(no_mat),
        "colliders_collections_render_visible": col_render_visible,
        "colliders_objects_render_visible": col_obj_visible[:50],
        "colliders_objects_render_visible_count": len(col_obj_visible),
        "objects_outside_map": outside[:50],
        "objects_outside_map_count": len(outside),
        "objects_below_ground": below[:30],
        "objects_below_ground_count": len(below),
        "far_shared_meshes": far_kit[:30],
        "world": world,
        "suns": suns,
        "lights": lights,
        "engine": scene.render.engine,
    }

    # --- renders ---------------------------------------------------------
    if do_render:
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
        cam = bpy.data.objects.get("QA_Cam")
        if cam is None:
            cd = bpy.data.cameras.new("QA_Cam")
            cam = bpy.data.objects.new("QA_Cam", cd)
            scene.collection.objects.link(cam)
        cam.data.clip_start = 0.5
        cam.data.clip_end = 8000
        shots = [
            ("qa_aerial", (900, -900, 620), (0, 0, 0), 35),
            ("qa_market", (760, 760, 24), (700, 790, 6), 24),
            ("qa_downtown", (120, -420, 90), (40, 40, 70), 30),
        ]
        if scene.world is None:
            scene.world = bpy.data.worlds.new("QA_World")
        for name, loc, tgt, lens in shots:
            from mathutils import Vector
            cam.location = loc
            d = Vector(tgt) - Vector(loc)
            cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
            cam.data.lens = lens
            scene.camera = cam
            scene.render.filepath = os.path.join(OUT, name + ".png")
            try:
                bpy.ops.render.render(write_still=True)
                res.setdefault("renders", []).append(name + ".png")
            except Exception as exc:
                res.setdefault("render_errors", []).append("%s:%r" % (name, exc))

    os.makedirs(REP, exist_ok=True)
    with open(os.path.join(REP, "qa_master.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, sort_keys=True, default=str)

    lines = ["# Master scene QA", "",
             "| metric | value |", "|---|---|",
             "| objects | %d |" % total_obj,
             "| meshes | %d |" % len(bpy.data.meshes),
             "| triangles | %d |" % total_tri,
             "| missing images | %d |" % len(missing_imgs),
             "| meshes without material | %d |" % len(no_mat),
             "| collider collections render-visible | %d |" % len(col_render_visible),
             "| collider objects render-visible | %d |" % len(col_obj_visible),
             "| objects outside map | %d |" % len(outside),
             "| objects below ground | %d |" % len(below),
             "| far shared kit meshes | %d |" % len(far_kit),
             "| lights | %d |" % lights,
             "| suns | %s |" % ", ".join(suns),
             "| world | %s |" % world,
             "| engine | %s |" % scene.render.engine,
             "", "## City children", "",
             "| collection | objects | tris |", "|---|---|---|"]
    for k in sorted(census):
        lines.append("| %s | %d | %d |" % (k, census[k]["objects"], census[k]["tris"]))
    if missing_imgs:
        lines += ["", "## Missing images", ""] + \
                 ["- %s (%s)" % (m["image"], m["path"]) for m in missing_imgs[:40]]
    if outside:
        lines += ["", "## Outside map", ""] + \
                 ["- %s @ %.0f,%.0f" % (o["name"], o["x"], o["y"]) for o in outside[:30]]
    with open(os.path.join(REP, "qa_master.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("###QA_JSON")
    print(json.dumps(res, indent=2, sort_keys=True, default=str))


main()
