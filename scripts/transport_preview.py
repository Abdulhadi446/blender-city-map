"""Render the two transport previews after the texture fix.

  aerial oblique over the runway + terminal, and eye level 40 m in front of the
  terminal. Temp asphalt ground, sun and world are added here and never saved.

Usage: blender -b out/transport.blend -P scripts/transport_preview.py
"""
import bpy, os, math
from mathutils import Vector

ROOT = "/home/abdulhadi/Work/city"
OUT = os.path.join(ROOT, "out")
TEX = os.path.join(ROOT, "textures", "asphalt_01")


def look_at(cam, target):
    d = Vector(target) - cam.location
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def asphalt_material():
    mat = bpy.data.materials.new("TEXFIX_temp_asphalt")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    tex = nt.nodes.new("ShaderNodeTexImage")
    img = bpy.data.images.get("asphalt_01_diff_2k.jpg")
    if img is None:
        for cand in ("asphalt_01_diff_2k.jpg", "asphalt_01_diff_2k.png"):
            p = os.path.join(TEX, cand)
            if os.path.exists(p):
                img = bpy.data.images.load(p)
                break
    if img:
        tex.image = img
    tex.location = (-400, 200)
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.location = (-650, -100)
    mp.inputs["Scale"].default_value = (60, 60, 1)
    uv = nt.nodes.new("ShaderNodeTexCoord")
    uv.location = (-850, -100)
    nt.links.new(uv.outputs["UV"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], tex.inputs["Vector"])
    return mat


def main():
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.eevee.taa_render_samples = 32
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'None'

    # grey-blue world
    world = scene.world or bpy.data.worlds.new("TEXFIX_world")
    scene.world = world
    world.use_nodes = True
    bg = next((n for n in world.node_tree.nodes if n.type == 'BACKGROUND'), None)
    if bg:
        bg.inputs["Color"].default_value = (0.36, 0.44, 0.55, 1.0)
        bg.inputs["Strength"].default_value = 1.8

    # temp asphalt ground, 500 x 500 m
    bpy.ops.mesh.primitive_plane_add(size=500, location=(0, -1500, -0.01))
    ground = bpy.context.object
    ground.name = "TEXFIX_ground"
    ground.data.materials.append(asphalt_material())

    # temp sun, 25 degrees elevation
    sun_data = bpy.data.lights.new("TEXFIX_sun", 'SUN')
    sun_data.energy = 3.0
    sun_data.angle = math.radians(3)
    sun = bpy.data.objects.new("TEXFIX_sun", sun_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(65), 0.0, math.radians(35))

    # The Colliders collection is render-visible in this file and its proxies use
    # col_placeholder (pure magenta 1,0,1). Hide it for the preview only.
    hidden = 0
    for o in bpy.data.objects:
        if o.type == 'MESH' and any(s.material and s.material.name == "col_placeholder"
                                    for s in o.material_slots):
            o.hide_render = True
            hidden += 1
    print("###HIDDEN_PLACEHOLDERS", hidden)

    cam_data = bpy.data.cameras.new("TEXFIX_cam")
    cam_data.lens = 35
    cam_data.clip_end = 8000
    cam = bpy.data.objects.new("TEXFIX_cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam

    shots = [
        ("transport_preview.png", (-450, -1640, 110), (120, -1452, 8), 32),
        ("transport_airport_preview.png", (-100, -1518, 1.7), (-100, -1478, 5), 24),
    ]
    for name, loc, target, lens in shots:
        cam.location = loc
        cam_data.lens = lens
        look_at(cam, target)
        scene.render.filepath = os.path.join(OUT, name)
        bpy.ops.render.render(write_still=True)
        print("###RENDERED", scene.render.filepath)


main()
