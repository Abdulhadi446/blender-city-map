#!/usr/bin/env python3
"""material_fix_previews.py — re-render the traffic + transport previews with real materials.

Temporary render-only rig (ground plane, sun, world) is removed afterwards and the
blend is never saved. EEVEE, 1920x1080.

    blender -b -P modules/material_fix_previews.py -- traffic_aerial
    blender -b -P modules/material_fix_previews.py -- traffic_street
    blender -b -P modules/material_fix_previews.py -- transport_aerial
    blender -b -P modules/material_fix_previews.py -- transport_airport
"""
from __future__ import annotations

import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

ROOT = "/home/abdulhadi/Work/city"
sys.path.insert(0, os.path.join(ROOT, "modules"))
import citykit as ck  # noqa: E402

OUT = os.path.join(ROOT, "out")
RES = (1920, 1080)


def world_bbox(objs):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for o in objs:
        if o.type != "MESH":
            continue
        for c in o.bound_box:
            p = o.matrix_world @ Vector(c)
            for i in range(3):
                lo[i] = min(lo[i], p[i])
                hi[i] = max(hi[i], p[i])
    return lo, hi


def aim(cam, target):
    d = Vector(target) - cam.location
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def setup(scene, target, size=300.0, sun_energy=3.0):
    # --- temp ground -------------------------------------------------------
    mesh = bpy.data.meshes.new("TMP_ground_mesh")
    s = size / 2.0
    mesh.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [],
                     [(0, 1, 2, 3)])
    mesh.update()
    ob = bpy.data.objects.new("TMP_ground", mesh)
    scene.collection.objects.link(ob)
    ob.location = (target[0], target[1], 0.0)
    mat = None
    for nm in ("asphalt", "concrete_pavement", "concrete_pavement_02"):
        try:
            mat = ck.append_material(nm)
            break
        except Exception:
            continue
    if mat:
        ob.data.materials.append(mat)
    # --- temp sun + world --------------------------------------------------
    lt = bpy.data.lights.new("TMP_sun", type="SUN")
    lt.energy = sun_energy
    lt.angle = math.radians(3.0)
    sun = bpy.data.objects.new("TMP_sun", lt)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(52), 0.0, math.radians(35))
    w = bpy.data.worlds.new("TMP_world")
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs[0].default_value = (0.45, 0.55, 0.68, 1.0)
    bg.inputs[1].default_value = 1.0
    scene.world = w
    return [ob, sun]


def render(scene, cam_loc, target, path, lens=50.0):
    cam_data = bpy.data.cameras.new("TMP_cam")
    cam_data.lens = lens
    cam_data.clip_end = 8000.0
    cam = bpy.data.objects.new("TMP_cam", cam_data)
    scene.collection.objects.link(cam)
    cam.location = Vector(cam_loc)
    aim(cam, target)
    scene.camera = cam
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return cam


def measure(path):
    img = bpy.data.images.load(path, check_existing=False)
    arr = np.array(img.pixels[:], dtype=np.float32).reshape(-1, 4)[:, :3]
    std = float(arr.std())
    magenta = float(np.mean((arr[:, 0] > 0.45) & (arr[:, 2] > 0.45)
                            & (arr[:, 1] < 0.30)))
    bpy.data.images.remove(img)
    return std, magenta


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    mode = argv[0] if argv else "traffic_aerial"
    key = "traffic" if mode.startswith("traffic") else "transport"
    bpy.ops.wm.open_mainfile(filepath=os.path.join(OUT, key + ".blend"))
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE"
    except TypeError:
        scene.render.engine = [i.identifier for i in
                               bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items][0]
    scene.render.resolution_x, scene.render.resolution_y = RES
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    if hasattr(scene, "eevee"):
        scene.eevee.taa_render_samples = 24
    before = {o.name for o in bpy.data.objects}
    info = {"mode": mode, "engine": scene.render.engine}

    if key == "traffic":
        veh = [o for o in bpy.data.objects if o.type == "MESH"
               and (o.name.startswith("SM_") or o.name.startswith("LOD1_SM"))
               and not o.hide_render]
        pts = [o.matrix_world.translation for o in veh]
        near = [p for p in pts if abs(p[0] - 600) < 320 and abs(p[1] - 1200) < 300]
        target = (sum(p[0] for p in near) / len(near),
                  sum(p[1] for p in near) / len(near), 0.0) if near else (600.0, 1200.0, 0.0)
        info["cars_in_frame_zone"] = len(near)
        tmp = setup(scene, target, 300.0)
        if mode == "traffic_aerial":
            tight = [p for p in pts if abs(p[0] - 600) < 150 and abs(p[1] - 1200) < 150]
            if len(tight) < 8:
                tight = near
            tgt = (sum(p[0] for p in tight) / len(tight),
                   sum(p[1] for p in tight) / len(tight), 0.0)
            info["cars_in_closeup"] = len(tight)
            d = 78.0
            cam_loc = (tgt[0] - 0.55 * d, tgt[1] - 0.70 * d, 0.42 * d)
            out = os.path.join(OUT, "traffic_preview.png")
            render(scene, cam_loc, (tgt[0], tgt[1], 1.05), out, lens=45)
            info["closeup_target"] = list(tgt)
        else:
            # eye level at the market kerb, looking along the parked row
            kerb = min(near, key=lambda p: p[1]) if near else Vector(target)
            cam_loc = (kerb[0] - 11.0, kerb[1] - 13.0, 1.7)
            out = os.path.join(OUT, "traffic_street_preview.png")
            render(scene, cam_loc, (kerb[0], kerb[1] + 4.0, 1.2), out, lens=30)
        info["target"] = list(target)
    else:
        trn = [o for o in bpy.data.objects if o.type == "MESH"]
        air = [o for o in trn if "AIR" in o.name or "TERM" in o.name.upper()]
        alo, ahi = world_bbox(air) if air else world_bbox(trn)
        info["terminal_bbox"] = [round(v, 1) for v in list(alo) + list(ahi)]
        rlo, rhi = world_bbox([o for o in trn if "RUNWAY" in o.name])
        info["runway_bbox"] = [round(v, 1) for v in list(rlo) + list(rhi)]
        target = ((rlo.x + rhi.x) / 2, (rlo.y + rhi.y) / 2, 0.0)
        tmp = setup(scene, target, 400.0)
        if mode == "transport_aerial":
            d = 780.0
            cam_loc = (target[0] + 0.40 * d, target[1] - 0.78 * d, 0.50 * d)
            out = os.path.join(OUT, "transport_preview.png")
            render(scene, cam_loc, (target[0], target[1], 0.0), out, lens=45)
        else:
            cx = (alo.x + ahi.x) / 2
            cy = (alo.y + ahi.y) / 2
            cam_loc = (cx, alo.y - 40.0, 1.7)
            out = os.path.join(OUT, "transport_airport_preview.png")
            render(scene, cam_loc, (cx, cy, max(6.0, (alo.z + ahi.z) / 2)), out, lens=35)
        info["target"] = list(target)

    std, magenta = measure(out)
    info.update({"preview": out, "stddev": round(std, 4),
                 "magenta_fraction": round(magenta, 5)})
    # remove temp rig, never save
    for nm in [o.name for o in bpy.data.objects if o.name not in before]:
        ob = bpy.data.objects.get(nm)
        if ob:
            bpy.data.objects.remove(ob, do_unlink=True)
    info["temp_objects_left"] = [o.name for o in bpy.data.objects
                                 if o.name.startswith("TMP_")]
    print("PREVIEW", json.dumps(info))
    json.dump(info, open("/tmp/opencode/mf/%s.json" % mode, "w"), indent=1)


if __name__ == "__main__":
    main()
