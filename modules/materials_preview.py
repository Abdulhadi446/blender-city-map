"""Render the material swatch grid for the library.

Run:  cd /home/abdulhadi/Work/city && blender -b -P modules/materials_preview.py
Out:  /home/abdulhadi/Work/city/out/materials_preview.png  (1920x1080, EEVEE)
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bpy
import citykit as ck

COLS, ROWS = 16, 4
CW, CH = 2.0, 3.6          # cell width / height (m)
R = 0.85                   # swatch sphere radius


def wrap(name, width=13):
    """Split a snake_case material name into at most 2 centred lines."""
    lines, cur = [], ""
    for part in name.split("_"):
        cand = (cur + "_" + part) if cur else part
        if len(cand) <= width or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = part
    if cur:
        lines.append(cur)
    if len(lines) > 2:
        lines = [lines[0], "_".join(lines[1:])]
    return "\n".join(lines)


def main():
    index = json.load(open(ck.MATERIALS_BLEND.replace("materials.blend", "materials.json")))
    names = index["materials"]            # the 64 contract names, in category order
    print("rendering %d material swatches" % len(names))

    bpy.ops.wm.open_mainfile(filepath=ck.MATERIALS_BLEND)
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)

    missing = [n for n in names if n not in bpy.data.materials]
    if missing:
        raise RuntimeError("materials.blend is missing: %s" % missing)

    coll = ck.ensure_collection("MaterialSwatches")
    label_coll = ck.ensure_collection("SwatchLabels")

    total_w, total_h = COLS * CW, ROWS * CH
    for i, name in enumerate(names):
        r, c = divmod(i, COLS)
        x = (c - (COLS - 1) / 2.0) * CW
        top = ((ROWS - 1) / 2.0 - r) * CH
        z = top - 1.05

        bpy.ops.mesh.primitive_uv_sphere_add(segments=40, ring_count=24,
                                             radius=R, location=(x, 0.0, z))
        sw = bpy.context.active_object
        sw.name = "SW_%s" % name
        bpy.ops.object.shade_smooth()
        sw.data.materials.append(bpy.data.materials[name])
        ck.link_obj(sw, coll)

        body = wrap(name)
        fc = bpy.data.curves.new("LBL_%s" % name, type="FONT")
        fc.body = body
        fc.size = 0.27
        fc.align_x = "CENTER"
        fc.align_y = "TOP"
        fc.extrude = 0.004
        txt = bpy.data.objects.new("LBL_%s" % name, fc)
        txt.location = (x, -R - 0.05, top - 2.05)
        txt.rotation_euler = (math.radians(90.0), 0.0, 0.0)
        txt.data.materials.append(bpy.data.materials["marking_white"])
        ck.link_obj(txt, label_coll)

    # title
    t = bpy.data.curves.new("TITLE", type="FONT")
    t.body = "CITY MATERIAL LIBRARY  —  %d contract materials  (materials.json)" % len(names)
    t.size = 0.75
    t.align_x = "CENTER"
    t.extrude = 0.01
    title = bpy.data.objects.new("TITLE", t)
    title.location = (0.0, 0.0, total_h / 2.0 + 1.2)
    title.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    title.data.materials.append(bpy.data.materials["marking_white"])
    ck.link_obj(title, label_coll)

    # ground plane so reflections/ambient have something to come from
    bpy.ops.mesh.primitive_plane_add(size=160.0, location=(0.0, 0.0, -total_h / 2.0 - 1.6))
    floor = bpy.context.active_object
    floor.name = "SW_floor"
    floor.data.materials.append(bpy.data.materials["concrete"])
    ck.link_obj(floor, coll)

    try:
        bpy.context.scene.view_settings.view_transform = "Standard"
    except Exception as e:
        print("view transform:", e)

    out = os.path.join(ck.OUT_DIR, "materials_preview.png")
    ck.make_preview(out, (0.0, -33.0, 0.0), (0.0, 0.0, 0.0),
                    engine="BLENDER_EEVEE", res=(1920, 1080),
                    sun_elev=38.0, sun_azim=-35.0, sun_energy=4.0, samples=64)
    print("objects:", len(bpy.data.objects), "tris:", ck.scene_tri_count())
    return out


if __name__ == "__main__":
    main()
