#!/usr/bin/env python3
"""commercial_previews.py — render the two Commercial previews + verify pixels.

Adds TEMP ground + sun + world only (never saved), renders:
  out/commercial_preview.png        aerial oblique over RET_MALL + OFF_TOWER
  out/commercial_street_preview.png eye-level 1.7 m, 25 m from RET_MALL entrance
Then reads back both PNGs: pixel stddev and magenta-pixel (missing material)
count, and writes results into reports/commercial_report.json ('previews') +
updates reports/commercial_report.md.

Run:  cd /home/abdulhadi/Work/city && blender -b out/commercial.blend -P modules/commercial_previews.py
"""
from __future__ import annotations

import json
import os
import sys

ROOT = "/home/abdulhadi/Work/city"
sys.path.insert(0, ROOT + "/modules")
import citykit as ck  # noqa: E402
import bpy  # noqa: E402

AERIAL = ((340.0, -470.0, 250.0), (92.0, -250.0, 25.0))
STREET = ((111.0, -310.2, 1.7), (111.0, -285.0, 5.5))


def temp_env():
    """Temp sun + sky world + ground plane; returns list for cleanup."""
    tmp = []
    # world
    world = bpy.data.worlds.new("TMP_COM_WORLD")
    world.use_nodes = True
    bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs[0].default_value = (0.52, 0.64, 0.86, 1.0)
    bg.inputs[1].default_value = 0.85
    bpy.context.scene.world = world
    tmp.append(world)
    # sun
    sd = bpy.data.lights.new("TMP_COM_SUN", "SUN")
    sd.energy = 3.2
    sd.angle = 0.0262
    so = bpy.data.objects.new("TMP_COM_SUN", sd)
    so.rotation_euler = (0.96, 0.0, 0.7)   # ~35 deg elevation, from the SE
    bpy.context.scene.collection.objects.link(so)
    tmp.append(so)
    # ground plane (library material only; never saved)
    me_ground = bpy.data.meshes.new("TMP_COM_GROUND")
    import bmesh  # noqa: E401
    me_ground.from_pydata(
        [(-2600.0, -2600.0, -0.02), (2600.0, -2600.0, -0.02),
         (2600.0, 2600.0, -0.02), (-2600.0, 2600.0, -0.02)],
        [], [(0, 3, 2), (0, 2, 1)])
    me_ground.update()
    mat = ck.append_material("concrete")
    me_ground.materials.append(mat)
    go = bpy.data.objects.new("TMP_COM_GROUND", me_ground)
    bpy.context.scene.collection.objects.link(go)
    tmp.append(go)
    return tmp


def strip_env(tmp):
    scene = bpy.context.scene
    for item in tmp:
        if isinstance(item, bpy.types.World):
            if scene.world is item:
                scene.world = None
            bpy.data.worlds.remove(item)
        else:
            try:
                bpy.data.objects.remove(item, do_unlink=True)
            except Exception:
                pass


def analyse(path):
    img = bpy.data.images.load(path, check_existing=False)
    import numpy as np
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    lum = 0.2126 * px[:, :, 0] + 0.7152 * px[:, :, 1] + 0.0722 * px[:, :, 2]
    std = float(lum.std())
    magenta = int(((px[:, :, 0] > 0.8) & (px[:, :, 1] < 0.2) & (px[:, :, 2] > 0.8)).sum())
    mean = [float(px[:, :, i].mean()) for i in range(3)]
    bpy.data.images.remove(img)
    return dict(path=path, size=[w, h], luminance_std=round(std, 4),
                mean_rgb=[round(m, 3) for m in mean],
                magenta_pixels=magenta, std_ok=std > 0.02, magenta_ok=magenta < 50)


def main():
    scene = bpy.context.scene
    res = (1920, 1080)
    tmp = temp_env()
    previews = {}
    try:
        for key, (pos, target) in (("aerial", AERIAL), ("street", STREET)):
            path = os.path.join(ROOT, "out",
                                "commercial_preview.png" if key == "aerial"
                                else "commercial_street_preview.png")
            ck.make_preview(path, pos, target, engine="BLENDER_EEVEE", res=res,
                            sun_elev=35.0, sun_azim=40.0, sun_energy=3.2, samples=48,
                            lens=24.0 if key == "street" else 35.0)
            previews[key] = analyse(path)
    finally:
        strip_env(tmp)
    for k, v in previews.items():
        print("[commercial_previews] %s -> std %.4f magenta %d size %s" %
              (k, v["luminance_std"], v["magenta_pixels"], v["size"]))

    jpath = os.path.join(ROOT, "reports", "commercial_report.json")
    with open(jpath) as f:
        data = json.load(f)
    data["previews"] = dict(
        engine="BLENDER_EEVEE", resolution=[1920, 1080],
        aerial=previews.get("aerial"), street=previews.get("street"),
        ground_and_sun="temp only, removed, file not re-saved",
        notes="aerial over RET_MALL+OFF_TOWER cluster; street eye-level 1.7 m at 25 m "
              "from RET_MALL south entrance",
    )
    with open(jpath, "w") as f:
        json.dump(data, f, indent=1)
    ok_all = all(p["std_ok"] and p["magenta_ok"] for p in previews.values())
    mpath = os.path.join(ROOT, "reports", "commercial_report.md")
    with open(mpath, "a") as fh:
        fh.write("\n## Previews (EEVEE 1920x1080)\n")
        for k in ("aerial", "street"):
            p = previews.get(k, {})
            fh.write("- %s: `%s` std %.4f (need >0.02), magenta pixels %d\n"
                     % (k, p.get("path", "?"), p.get("luminance_std", -1),
                        p.get("magenta_pixels", -1)))
        fh.write("- verification: " + ("PASS (no magenta, both frames vary)\n"
                                       if ok_all else "FAIL\n"))
    print("[commercial_previews] %s" % ("PASS" if ok_all else "FAIL"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    rc = main()
    sys.exit(rc)
