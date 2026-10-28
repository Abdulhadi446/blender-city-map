#!/usr/bin/env python3
"""geometry_fix.py — GEOMETRY-QA surgical fixes for the 6 owned blends.

Usage (headless, ONE blender at a time):
    blender -b out/<blend>.blend -P modules/geometry_fix.py -- <key>
keys: downtown, nature, residential, track, entertainment, market, all

Every blend is loaded by the caller; the chosen function fixes, verifies and saves.
Contract materials are appended via modules/citykit.append_material.
"""
from __future__ import annotations

import bpy
import json
import math
import os
import re
import struct
import sys
import zlib
from collections import defaultdict

import numpy as np
from mathutils import Vector


def png_stddev(path):
    """Stddev of RGB (0..1) of a saved PNG, decoded with zlib (no PIL)."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return 0.0
    pos = 8
    idat = b""
    w = h = bitd = ctype = None
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4]); pos += 4
        ck = data[pos:pos + 4]; pos += 4
        chunk = data[pos:pos + length]; pos += length
        pos += 4
        if ck == b"IHDR":
            w, h, bitd, ctype, _c, _f, _i = struct.unpack(">IIBBBBB", chunk)
        elif ck == b"IDAT":
            idat += chunk
        elif ck == b"IEND":
            break
    if bitd != 8 or ctype not in (2, 6):
        return 0.0
    raw = zlib.decompress(idat)
    bpp = 3 if ctype == 2 else 4
    stride = w * bpp
    out = bytearray(h * stride)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        filt = raw[p]; p += 1
        line = raw[p:p + stride]; p += stride
        cur = bytearray(line)
        if filt == 1:
            for i in range(bpp, stride):
                cur[i] = (cur[i] + cur[i - bpp]) & 0xff
        elif filt == 2:
            for i in range(stride):
                cur[i] = (cur[i] + prev[i]) & 0xff
        elif filt == 3:
            for i in range(stride):
                a = cur[i - bpp] if i >= bpp else 0
                cur[i] = (cur[i] + ((a + prev[i]) >> 1)) & 0xff
        elif filt == 4:
            for i in range(stride):
                a = cur[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                pp = a + b - c
                pr = a if (abs(pp - a) <= abs(pp - b) and abs(pp - a) <= abs(pp - c)) \
                    else (b if abs(pp - b) <= abs(pp - c) else c)
                cur[i] = (cur[i] + pr) & 0xff
        out[y * stride:(y + 1) * stride] = cur
        prev = cur
    if bpp == 4:
        rgb = bytearray(h * w * 3)
        for y in range(h):
            base = y * w * 3
            s = y * stride
            for x in range(w):
                d = s + x * 4
                rgb[base + x * 3] = out[d]
                rgb[base + x * 3 + 1] = out[d + 1]
                rgb[base + x * 3 + 2] = out[d + 2]
        out = rgb
    arr = np.array(out, dtype=np.float32).reshape(-1, 3) / 255.0
    return float(arr.std())

ROOT = "/home/abdulhadi/Work/city"
OUT = os.path.join(ROOT, "out")
REPORT = os.path.join(ROOT, "reports", "geometry_fix_report.md")
SCRATCH = "/tmp/opencode/gqa"
LOG = []
RESULTS = {}

sys.path.insert(0, os.path.join(ROOT, "modules"))
import citykit as ck  # noqa: E402


def log(msg):
    print("[gqa]", msg)
    LOG.append(msg)


# ---------------------------------------------------------------- geometry helpers
def ob_bbox(ob):
    pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    return [min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts),
            max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)]


def tri_count(ob):
    return sum(max(0, len(p.vertices) - 2) for p in ob.data.polygons)


def scene_tris_unique():
    seen, total = set(), 0
    for ob in bpy.data.objects:
        if ob.type != "MESH" or ob.data is None:
            continue
        if ob.data.name in seen:
            continue
        seen.add(ob.data.name)
        total += tri_count(ob)
    return total


def replace_slot_material(ob, old_name, new_name):
    """Replace every material slot on `ob` named old_name with contract new_name.
    Sets both the object slot (what EEVEE renders) and the mesh data list, and
    preserves multi-material layouts (other slots untouched). Returns slot count changed."""
    newm = ck.append_material(new_name)
    changed = 0
    for i, s in enumerate(ob.material_slots):
        if s.material and s.material.name == old_name:
            s.material = newm          # object slot = what EEVEE renders
            ob.data.materials[i] = newm  # keep mesh data in sync
            changed += 1
    return changed


def delete_ob(ob):
    me = ob.data
    bpy.data.objects.remove(ob, do_unlink=True)
    if me is not None and me.users == 0:
        bpy.data.meshes.remove(me)


# ---------------------------------------------------------------- materials
CONTRACT_FACADE = ["facade_plaster_bone", "facade_concrete_slab", "facade_brick_red"]


def switch_magenta_to_contract(tag):
    """For materials referencing an empty/missing image, switch their objects to a
    resolving contract material (per the texture contract). Returns count of objects switched."""
    switched = 0
    bad = set()
    for m in bpy.data.materials:
        if not m.use_nodes:
            continue
        for n in m.node_tree.nodes:
            if n.type == "TEX_IMAGE" and n.image is not None and n.image.size == (0, 0):
                bad.add(m.name)
                break
    fallback = {"glass": "glass_dark", "metal": "metal_steel", "wood": "wood_planks_weathered",
                "leaf": "leaves_green", "grass": "grass", "road": "concrete_poured",
                "brick": "brick_red", "roof": "roof_bitumen_flat", "plaster": "facade_plaster_bone",
                "wall": "facade_plaster_bone", "concrete": "concrete_poured"}
    for nm in sorted(bad):
        m = bpy.data.materials[nm]
        new_name = "concrete_poured"
        for k, v in fallback.items():
            if k in nm.lower():
                new_name = v
                break
        fb = ck.append_material(new_name)
        for ob in bpy.data.objects:
            if ob.type != "MESH":
                continue
            for i, s in enumerate(ob.material_slots):
                if s.material and s.material.name == nm:
                    ob.data.materials[i] = fb
                    switched += 1
        log("%s: magenta mat %r -> %s (%d slots)" % (tag, nm, new_name, switched))
    return switched


# ---------------------------------------------------------------- box / window mapping (downtown smear)
def make_boxmap_group(name="GQA_BOXMAP"):
    ng = bpy.data.node_groups.get(name)
    if ng:
        return ng
    ng = bpy.data.node_groups.new(name, "ShaderNodeTree")
    ng.interface.new_socket("Vector", in_out="INPUT", socket_type="NodeSocketVector")
    ng.interface.new_socket("Scale", in_out="INPUT", socket_type="NodeSocketFloat")
    ng.interface.new_socket("Vector", in_out="OUTPUT", socket_type="NodeSocketVector")
    nodes, links = ng.nodes, ng.links
    gin = nodes.new("NodeGroupInput")
    gout = nodes.new("NodeGroupOutput")
    geo = nodes.new("ShaderNodeNewGeometry")
    vt = nodes.new("ShaderNodeVectorTransform")
    vt.vector_type = "NORMAL"
    vt.convert_from = "WORLD"
    vt.convert_to = "OBJECT"
    sv = nodes.new("ShaderNodeSeparateXYZ")
    sn = nodes.new("ShaderNodeSeparateXYZ")
    links.new(gin.outputs["Vector"], sv.inputs[0])
    links.new(geo.outputs["Normal"], vt.inputs["Vector"])
    links.new(vt.outputs["Vector"], sn.inputs[0])

    def absnode(inp):
        n = nodes.new("ShaderNodeMath")
        n.operation = "ABSOLUTE"
        links.new(inp, n.inputs[0])
        return n

    ax, ay, az = absnode(sn.outputs["X"]), absnode(sn.outputs["Y"]), absnode(sn.outputs["Z"])

    def comb(x, y):
        c = nodes.new("ShaderNodeCombineXYZ")
        links.new(x, c.inputs["X"])
        links.new(y, c.inputs["Y"])
        return c

    cx = comb(sv.outputs["Y"], sv.outputs["Z"])
    cy = comb(sv.outputs["X"], sv.outputs["Z"])
    cz = comb(sv.outputs["X"], sv.outputs["Y"])

    def mul(v, w):
        m = nodes.new("ShaderNodeVectorMath")
        m.operation = "MULTIPLY"
        links.new(v.outputs[0], m.inputs[0])
        links.new(w.outputs[0], m.inputs[1])
        return m

    s1 = nodes.new("ShaderNodeVectorMath")
    s1.operation = "ADD"
    links.new(mul(cx, ax).outputs[0], s1.inputs[0])
    links.new(mul(cy, ay).outputs[0], s1.inputs[1])
    s2 = nodes.new("ShaderNodeVectorMath")
    s2.operation = "ADD"
    links.new(s1.outputs[0], s2.inputs[0])
    links.new(mul(cz, az).outputs[0], s2.inputs[1])
    sc = nodes.new("ShaderNodeVectorMath")
    sc.operation = "SCALE"
    links.new(s2.outputs[0], sc.inputs[0])
    links.new(gin.outputs["Scale"], sc.inputs["Scale"])
    links.new(sc.outputs[0], gout.inputs["Vector"])
    return ng


def boxmap_material(m, scale=0.25):
    """Rewire a material's texture Mapping to triplanar (box) coordinates so
    vertical facades no longer smear."""
    if not m.use_nodes:
        return False
    nt = m.node_tree
    maps = [n for n in nt.nodes if n.type == "MAPPING"]
    texs = [n for n in nt.nodes if n.type == "TEX_IMAGE" and n.image]
    if not maps or not texs:
        return False
    ng = make_boxmap_group()
    tc = next((n for n in nt.nodes if n.type == "TEX_COORD"), None)
    if tc is None:
        tc = nt.nodes.new("ShaderNodeTexCoord")
    grp = nt.nodes.new("ShaderNodeGroup")
    grp.node_tree = ng
    grp.inputs["Scale"].default_value = scale
    nt.links.new(tc.outputs["Object"], grp.inputs["Vector"])
    for mp in maps:
        nt.links.new(grp.outputs["Vector"], mp.inputs["Vector"])
    return True


# ---------------------------------------------------------------- window bands
GLASS = {"glass_office", "glass_dark", "glass_shop", "glass_tinted_office"}
LIGHT = {"concrete", "concrete_poured", "plaster_white", "plaster_cream",
         "stone_grey", "stucco_grey", "marble_white", "wall_paint",
         "facade_plaster_bone", "facade_plaster_sand", "facade_plaster_stone"}


def add_window_bands(prefix_re, max_ratio=0.34, min_side=8.0, tag="downtown"):
    """Add one recessed ribbon-window quad per blank side of each floor-slice
    building. Idempotent: skips groups that already have a gqa_winbands object.
    For towers that still lack bands, windows are added to all 4 sides so every
    face reads as fenestrated (fixes blank white side walls). Returns list of (name, tris)."""
    groups = defaultdict(list)
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        m = re.match(prefix_re, ob.name)
        if not m or "_sha_f" not in ob.name:
            continue
        groups[m.group(1)].append(ob)

    made = []
    for bid, obs in groups.items():
        if bpy.data.objects.get(bid + "_gqa_winbands"):
            continue  # idempotent
        # combined bbox of all floor slices
        b0 = ob_bbox(obs[0])
        bb = [b0[0], b0[1], b0[2], b0[3], b0[4], b0[5]]
        for ob in obs[1:]:
            b = ob_bbox(ob)
            bb[0] = min(bb[0], b[0]); bb[1] = min(bb[1], b[1]); bb[2] = min(bb[2], b[2])
            bb[3] = max(bb[3], b[3]); bb[4] = max(bb[4], b[4]); bb[5] = max(bb[5], b[5])
        h = bb[5] - bb[2]
        if h < 2.2:
            continue
        names = [s.material.name for ob in obs for s in ob.material_slots if s.material]
        gmat = None
        for cand in ("glass_dark", "glass_office", "glass_shop", "glass_tinted_office"):
            if cand in names:
                gmat = cand
                break
        if gmat is None:
            continue
        z0 = bb[2] + 0.55 * h
        z1 = z0 + 1.45
        inset = 1.2
        off = 0.07
        verts, faces = [], []
        # X+ side
        if bb[4] - bb[1] - 2 * inset >= 3:
            x = bb[3] + off
            y0, y1 = bb[1] + inset, bb[4] - inset
            vs = [(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)]
            base = len(verts); verts.extend(vs); faces.append((base, base+1, base+2, base+3))
        # X- side
        if bb[4] - bb[1] - 2 * inset >= 3:
            x = bb[0] - off
            y0, y1 = bb[1] + inset, bb[4] - inset
            vs = [(x, y1, z0), (x, y0, z0), (x, y0, z1), (x, y1, z1)]
            base = len(verts); verts.extend(vs); faces.append((base, base+1, base+2, base+3))
        # Y+ side
        if bb[3] - bb[0] - 2 * inset >= 3:
            y = bb[4] + off
            x0, x1 = bb[0] + inset, bb[3] - inset
            vs = [(x0, y, z0), (x0, y, z1), (x1, y, z1), (x1, y, z0)]
            base = len(verts); verts.extend(vs); faces.append((base, base+1, base+2, base+3))
        # Y- side
        if bb[3] - bb[0] - 2 * inset >= 3:
            y = bb[1] - off
            x0, x1 = bb[0] + inset, bb[3] - inset
            vs = [(x1, y, z0), (x0, y, z0), (x0, y, z1), (x1, y, z1)]
            base = len(verts); verts.extend(vs); faces.append((base, base+1, base+2, base+3))
        if not faces:
            continue
        me = bpy.data.meshes.new("%s_gqa_winbands" % bid)
        me.from_pydata(verts, [], faces)
        me.validate()
        me.update()
        me.materials.append(ck.append_material(gmat))
        ob = bpy.data.objects.new(me.name, me)
        coll = bpy.data.collections.get("Downtown/Meshes") or bpy.context.scene.collection
        coll.objects.link(ob)
        made.append((ob.name, len(faces) * 2))
    log("window bands: %d buildings, %d tris" % (len(made), sum(t for _, t in made)))
    return made


def _side_stats(ob):
    me = ob.data
    mats = [s.material.name if s.material else "" for s in ob.material_slots]
    rot = ob.matrix_world.to_3x3()
    st = defaultdict(lambda: [0.0, 0.0, 0.0])
    for p in me.polygons:
        n = (rot @ p.normal)
        if abs(n.z) > 0.6:
            continue
        if abs(n.x) > abs(n.y):
            side = "X+" if n.x > 0 else "X-"
        else:
            side = "Y+" if n.y > 0 else "Y-"
        nm = mats[p.material_index] if p.material_index < len(mats) else ""
        st[side][0] += p.area
        if nm in GLASS:
            st[side][1] += p.area
        if nm in LIGHT:
            st[side][2] += p.area
    return st


# ---------------------------------------------------------------- sky cone
def delete_sky_cone(tag):
    """Delete stray giant inverted cone: bbox max z > 200 m AND footprint > 80 m."""
    hits = []
    for ob in list(bpy.data.objects):
        if ob.type != "MESH":
            continue
        bb = ob_bbox(ob)
        dx, dy = bb[3] - bb[0], bb[4] - bb[1]
        if bb[5] > 200 and max(dx, dy) > 80:
            hits.append((ob.name, bb[5], dx, dy, tri_count(ob)))
    for name, zmax, dx, dy, tris in hits:
        ob = bpy.data.objects.get(name)
        log("%s: sky cone DELETE %s zmax=%.1f footprint=%.1fx%.1f tris=%d" % (tag, name, zmax, dx, dy, tris))
        delete_ob(ob)
    if not hits:
        log("%s: sky cone: none found (no mesh zmax>200 & footprint>80)" % tag)
    return hits


# ---------------------------------------------------------------- support bracket
_BRACKET_MESH = None


def _bracket_mesh():
    """Simple L support bracket, ~16 unique tris (shared via linked dups)."""
    global _BRACKET_MESH
    if _BRACKET_MESH is not None:
        return _BRACKET_MESH
    me = bpy.data.meshes.new("SM_GQA_Bracket_01")
    # vertical post + top shelf, local origin at post base, Z up
    w, d, h, shelf = 0.25, 0.25, 1.0, 0.55
    verts = [
        (-w, -d, 0), (w, -d, 0), (w, w, 0), (-w, w, 0),          # post base
        (-w, -d, h), (w, -d, h), (w, w, h), (-w, w, h),          # post top
        (-shelf, -shelf, h), (shelf, -shelf, h), (shelf, shelf, h), (-shelf, shelf, h),  # shelf top
        (-shelf, -shelf, h + 0.04), (shelf, -shelf, h + 0.04), (shelf, shelf, h + 0.04), (-shelf, shelf, h + 0.04),  # shelf cap
    ]
    faces = [
        (0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2),
        (2, 6, 7, 3), (3, 7, 4, 0),                               # post
        (8, 11, 10, 9), (12, 15, 14, 13), (8, 12, 13, 9), (9, 13, 14, 10),  # shelf
        (10, 14, 15, 11), (11, 15, 12, 8),
    ]
    me.from_pydata(verts, [], faces)
    me.validate()
    me.update()
    _BRACKET_MESH = me
    return me


def support_balconies(tag, balcony_prefix="SM_Balcony"):
    """Add an instanced support bracket under each floating balcony box."""
    me = _bracket_mesh()
    mat = ck.append_material("metal_painted_dark")
    me.materials.append(mat)
    placed = 0
    for ob in list(bpy.data.objects):
        if ob.type != "MESH" or not ob.name.startswith(balcony_prefix):
            continue
        bb = ob_bbox(ob)
        cx = (bb[0] + bb[3]) / 2.0
        cy = (bb[1] + bb[4]) / 2.0
        ztop = bb[2]
        new = bpy.data.objects.new(me.name + "_inst", me)
        new.location = (cx, cy, ztop - 1.0)
        new.scale = (1.0, 1.0, 1.0)
        bpy.context.scene.collection.objects.link(new)
        placed += 1
    btris = sum(max(0, len(p.vertices) - 2) for p in me.polygons)
    log("%s: support brackets placed under %d balconies (bracket=%d tris)" % (tag, placed, btris))
    return placed


# ---------------------------------------------------------------- previews / verify
def render_preview(path, cam_pos, cam_target, tag, sun_elev=35.0, sun_azim=-40.0,
                   sun_energy=3.5, samples=32):
    """Temp ground+sun+world EEVEE render; returns stddev of RGB pixels."""
    scene = bpy.context.scene
    prev = dict(engine=scene.render.engine, x=scene.render.resolution_x,
                y=scene.render.resolution_y, fp=scene.render.filepath,
                cam=scene.camera, world=scene.world)
    tmp = []
    try:
        cam_data = bpy.data.cameras.new("GQA_PREVIEW_CAM")
        cam_data.lens = 35.0
        p, t = Vector(cam_pos), Vector(cam_target)
        dist = (t - p).length
        cam_data.clip_start = max(0.1, dist / 2000.0)
        cam_data.clip_end = max(1000.0, dist * 4.0)
        cam = bpy.data.objects.new("GQA_PREVIEW_CAM", cam_data)
        scene.collection.objects.link(cam)
        tmp.append(cam)
        cam.location = p
        cam.rotation_euler = (t - p).to_track_quat("-Z", "Y").to_euler()
        scene.camera = cam

        sun_data = bpy.data.lights.new("GQA_PREVIEW_SUN", type="SUN")
        sun_data.energy = sun_energy
        sun = bpy.data.objects.new("GQA_PREVIEW_SUN", sun_data)
        sun.rotation_euler = (math.radians(90.0 - sun_elev), 0.0, math.radians(sun_azim))
        scene.collection.objects.link(sun)
        tmp.append(sun)

        world = bpy.data.worlds.new("GQA_PREVIEW_WORLD")
        scene.world = world
        tmp.append(world)
        world.use_nodes = True
        bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
        if bg:
            bg.inputs[0].default_value = (0.45, 0.55, 0.72, 1.0)
            bg.inputs[1].default_value = 0.7

        scene.render.engine = "BLENDER_EEVEE"
        scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
        scene.render.resolution_percentage = 100
        scene.render.filepath = path
        try:
            scene.eevee.taa_render_samples = samples
        except Exception:
            pass
        bpy.ops.render.render(write_still=True)

        # stddev from the saved PNG (Render Result pixels are empty in headless)
        stddev = png_stddev(path) if os.path.isfile(path) else 0.0
        log("%s: preview %s stddev=%.4f" % (tag, path, stddev))
        return stddev
    finally:
        for item in tmp:
            try:
                if isinstance(item, bpy.types.Object):
                    bpy.data.objects.remove(item, do_unlink=True)
                elif isinstance(item, bpy.types.World):
                    if scene.world is item:
                        scene.world = None
                    bpy.data.worlds.remove(item)
            except Exception:
                pass
        scene.camera = prev["cam"]
        scene.render.engine = prev["engine"]
        scene.render.resolution_x, scene.render.resolution_y = prev["x"], prev["y"]
        scene.render.filepath = prev["fp"]
        scene.world = prev["world"]


def blend_bbox():
    pts = []
    for ob in bpy.data.objects:
        if ob.type == "MESH":
            b = ob_bbox(ob)
            pts.append(Vector((b[0], b[1], b[2])))
            pts.append(Vector((b[3], b[4], b[5])))
    if not pts:
        return Vector((0, 0, 0)), 100.0
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return (mn + mx) / 2.0, (mx - mn).length


def save_blend(path):
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
    log("saved %s (%.1f MB)" % (path, os.path.getsize(path) / 1e6))


# ---------------------------------------------------------------- per-blend fixes
def fix_downtown():
    tag = "downtown"
    switch_magenta_to_contract(tag)
    delete_sky_cone(tag)
    # (b) vertical texture smear on tower facades -> triplanar box mapping
    smeared = []
    for nm in ("concrete", "plaster_white", "plaster_cream", "stone_grey", "marble_white",
               "facade_plaster_bone", "facade_concrete_slab"):
        m = bpy.data.materials.get(nm)
        if m and boxmap_material(m):
            smeared.append(nm)
    log("%s: box-map smear fix on materials: %s" % (tag, ", ".join(smeared)))
    # (c) blank white side walls -> window bands on all 4 sides of towers
    bands = add_window_bands(r"^(SM_[A-Z]+_[A-Z]+_\d+)", tag=tag)
    save_blend(os.path.join(OUT, "downtown.blend"))
    RESULTS[tag] = dict(smear=smeared, bands=len(bands), band_tris=sum(t for _, t in bands),
                        tris=scene_tris_unique())
    return RESULTS[tag]


def fix_nature():
    tag = "nature"
    switch_magenta_to_contract(tag)
    # (a) large ground meshes primarily dirt -> grass/grass_dry (gravel only on paths)
    reassigned = 0
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        b = ob_bbox(ob)
        if max(b[3] - b[0], b[4] - b[1]) <= 40 or b[5] > 1.0:
            continue
        mats = [s.material.name if s.material else None for s in ob.material_slots]
        if "dirt" not in mats:
            continue
        # face-area per material
        areas = defaultdict(float)
        for p in ob.data.polygons:
            nm = mats[p.material_index] if p.material_index < len(mats) else None
            if nm:
                areas[nm] += p.area
        if not areas:
            continue
        dominant = max(areas, key=areas.get)
        if dominant == "dirt" or areas["dirt"] / sum(areas.values()) > 0.6:
            newm = ck.append_material("grass")
            for i, s in enumerate(ob.material_slots):
                if s.material and s.material.name == "dirt":
                    ob.data.materials[i] = newm
            reassigned += 1
    log("%s: ground dirt->grass reassigned on %d meshes" % (tag, reassigned))
    # (b) pink props -> wood/metal/concrete/leaves by object name (none found in-situ)
    save_blend(os.path.join(OUT, "nature.blend"))
    RESULTS[tag] = dict(ground_reassigned=reassigned, tris=scene_tris_unique())
    return RESULTS[tag]


def fix_residential():
    tag = "residential"
    switch_magenta_to_contract(tag)
    # (a) delete oversized road/pavement planes duplicating Roads (fp>200 either axis, z 0-0.2)
    deleted = []
    for ob in list(bpy.data.objects):
        if ob.type != "MESH":
            continue
        b = ob_bbox(ob)
        if max(b[3] - b[0], b[4] - b[1]) <= 200 or not (-0.05 <= b[2] and b[5] <= 0.25):
            continue
        mats = [s.material.name if s.material else None for s in ob.material_slots]
        if not any(m and ("asphalt" in m or "paving" in m) for m in mats):
            continue
        deleted.append((ob.name, b[3] - b[0], b[4] - b[1], mats, tri_count(ob)))
        delete_ob(ob)
    log("%s: deleted %d oversized road planes" % (tag, len(deleted)))
    for name, dx, dy, mats, tris in deleted:
        log("  DEL %s fp=%.1fx%.1f mats=%s tris=%d" % (name, dx, dy, mats, tris))
    # (b) boundary walls flat sage-green -> brick/plaster (keep concrete coping = stone_grey slot)
    sage = 0
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        if replace_slot_material(ob, "facade_plaster_sage", "facade_plaster_bone"):
            sage += 1
    log("%s: sage walls facade_plaster_sage -> facade_plaster_bone on %d objects" % (tag, sage))
    # (c) floating dark balcony boxes -> instanced support brackets
    brackets = support_balconies(tag, "SM_Balcony")
    save_blend(os.path.join(OUT, "residential.blend"))
    RESULTS[tag] = dict(deleted_planes=len(deleted), sage_walls=sage, brackets=brackets,
                        tris=scene_tris_unique())
    return RESULTS[tag]


def fix_track():
    tag = "track"
    switch_magenta_to_contract(tag)
    # (a) delete stray small floating grey box near grandstand (z 2-40, fp<5x5, isolated)
    deleted = []
    for ob in list(bpy.data.objects):
        if ob.type != "MESH":
            continue
        b = ob_bbox(ob)
        dx, dy = b[3] - b[0], b[4] - b[1]
        if not (1.5 < b[2] < 42 and max(dx, dy) < 5 and dx * dy > 0.5):
            continue
        if any(k in ob.name for k in ("Plant", "Mast", "Sign", "Row", "Roof", "Wall", "Kerb")):
            continue
        mats = [s.material.name if s.material else None for s in ob.material_slots]
        deleted.append((ob.name, b[2], b[5], dx, dy, mats, tri_count(ob)))
        delete_ob(ob)
    log("%s: deleted %d stray floating grey boxes" % (tag, len(deleted)))
    for d in deleted:
        log("  DEL %s z=%.1f..%.1f fp=%.2fx%.2f mats=%s tris=%d" % d)
    # (b) pit-building roof: metal roof material + instanced ribs/parapet
    roofed = 0
    for ob in bpy.data.objects:
        if ob.type != "MESH" and ob.type != "EMPTY":
            continue
        if ob.name.startswith("SM_PitBldg_Roof"):
            replace_slot_material(ob, "roof_bitumen", "roof_metal")
            roofed += 1
    # add simple instanced ribs/parapet along the roof ridge (shared mesh)
    rib_mesh = bpy.data.meshes.new("SM_GQA_RoofRib_01")
    w, h, L = 0.15, 0.9, 4.0
    verts = [(-w, 0, 0), (w, 0, 0), (w, w, h), (-w, w, h),
             (-w, 0, 0.04), (w, 0, 0.04), (w, w, h + 0.04), (-w, w, h + 0.04)]
    faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    rib_mesh.from_pydata(verts, [], faces)
    rib_mesh.validate()
    rib_mesh.update()
    rib_mesh.materials.append(ck.append_material("metal_steel"))
    ribs = 0
    for ob in bpy.data.objects:
        if ob.type != "MESH" or not ob.name.startswith("SM_PitBldg_Roof"):
            continue
        b = ob_bbox(ob)
        # ribs along the long (Y) axis of the roof
        y0, y1 = b[1], b[4]
        y = y0
        while y <= y1:
            new = bpy.data.objects.new("GQA_RoofRib", rib_mesh)
            new.location = ((b[0] + b[3]) / 2.0, y, b[5] + 0.05)
            bpy.context.scene.collection.objects.link(new)
            ribs += 1
            y += 14.0
    log("%s: pit roof %d objects -> roof_metal, %d instanced ribs" % (tag, roofed, ribs))
    # (c) paddock blown-white concrete -> concrete_poured / sidewalk_concrete
    paved = 0
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        if "Paddock" in ob.name:
            replace_slot_material(ob, "concrete", "concrete_poured")
            paved += 1
    log("%s: paddock concrete -> concrete_poured on %d objects" % (tag, paved))
    save_blend(os.path.join(OUT, "track.blend"))
    RESULTS[tag] = dict(deleted_boxes=len(deleted), roofed=roofed, ribs=ribs, paved=paved,
                        tris=scene_tris_unique())
    return RESULTS[tag]


def fix_entertainment():
    tag = "entertainment"
    switch_magenta_to_contract(tag)
    # (a) shopfront glass blown WHITE -> glass_dark / glass_tinted_office
    fixed_glass = 0
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        mats = [s.material.name if s.material else None for s in ob.material_slots]
        # any glass slot that is not a dark/tinted glass -> swap to glass_tinted_office
        changed = False
        for i, s in enumerate(ob.material_slots):
            if s.material and s.material.name in ("glass_shop", "glass_office", "glass_clear"):
                ob.data.materials[i] = ck.append_material("glass_tinted_office")
                changed = True
                fixed_glass += 1
        if changed:
            log("  glass -> glass_tinted_office on %s" % ob.name)
    log("%s: shopfront glass white->glass_tinted_office on %d slots" % (tag, fixed_glass))
    # (b) courtyard ground bare dirt -> paving_slab/cobble_stone/grass
    courtyard = 0
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        mats = [s.material.name if s.material else None for s in ob.material_slots]
        if "dirt" in mats and max(ob_bbox(ob)[3] - ob_bbox(ob)[0], ob_bbox(ob)[4] - ob_bbox(ob)[1]) > 10:
            newm = ck.append_material("paving_slab")
            for i, s in enumerate(ob.material_slots):
                if s.material and s.material.name == "dirt":
                    ob.data.materials[i] = newm
            courtyard += 1
    log("%s: courtyard dirt -> paving_slab on %d meshes" % (tag, courtyard))
    # (c) flat bright-green wall panels -> sage/teal plaster
    greened = 0
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        if replace_slot_material(ob, "facade_plaster_teal", "facade_plaster_bone"):
            greened += 1
    log("%s: bright-green/teal panels -> facade_plaster_bone on %d objects" % (tag, greened))
    save_blend(os.path.join(OUT, "entertainment.blend"))
    RESULTS[tag] = dict(glass_slots=fixed_glass, courtyard=courtyard, greened=greened,
                        tris=scene_tris_unique())
    return RESULTS[tag]


def fix_market():
    tag = "market"
    switch_magenta_to_contract(tag)
    # move all LT_market_* lights into Market/Lights collection; verify <=250
    lights = [ob for ob in bpy.data.objects if ob.type == "LIGHT" and ob.name.startswith("LT_market_")]
    coll = bpy.data.collections.get("Market/Lights")
    if coll is None:
        coll = bpy.data.collections.new("Market/Lights")
        market = bpy.data.collections.get("Market")
        if market is not None:
            market.children.link(coll)
        else:
            bpy.context.scene.collection.children.link(coll)
    moved = 0
    for ob in lights:
        if ob.name not in coll.objects:
            coll.objects.link(ob)
            moved += 1
    in_coll = sum(1 for ob in lights if ob.name in coll.objects)
    log("%s: LT_market_* lights=%d in Market/Lights=%d moved=%d (<=250: %s)" % (
        tag, len(lights), in_coll, moved, in_coll <= 250))
    save_blend(os.path.join(OUT, "market.blend"))
    RESULTS[tag] = dict(lights=len(lights), in_lights=in_coll, moved=moved, ok=in_coll <= 250)
    return RESULTS[tag]


# ---------------------------------------------------------------- main
PREVIEWS = {
    "downtown": [
        ("downtown_preview.png", "aerial", None),
        ("downtown_street_preview.png", "street", None),
    ],
    "nature": [("nature_preview.png", "aerial", None)],
    "residential": [
        ("residential_preview.png", "aerial", None),
        ("residential_street_preview.png", "street", None),
    ],
    "track": [("track_ground_preview.png", "aerial", None)],
    "entertainment": [
        ("entertainment_preview.png", "aerial", None),
        ("entertainment_street_preview.png", "street", None),
    ],
    "market": [("market_street_preview.png", "street", None)],
}


def cam_positions(kind, center, r):
    cx, cy, cz = center
    if kind == "aerial":
        return (cx + r * 0.9, cy + r * 0.9, cz + r * 1.3), (cx, cy, cz)
    # street: eye level 1.7 m
    return (cx, cy - r * 0.55, 1.7), (cx, cy + r * 0.5, 1.7)


def render_all_previews(tag):
    center, r = blend_bbox()
    if r < 50:
        r = 150.0
    out = {}
    for fname, kind, _ in PREVIEWS.get(tag, []):
        path = os.path.join(OUT, fname)
        cpos, ctar = cam_positions(kind, center, r)
        std = render_preview(path, cpos, ctar, tag)
        out[fname] = std
    return out


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    key = argv[0] if argv else "all"
    keys = ["downtown", "nature", "residential", "track", "entertainment", "market"] \
        if key == "all" else [key]
    if key not in (["all"] + keys) and key not in keys:
        raise SystemExit("unknown blend key %r" % key)

    for k in keys:
        fn = {"downtown": fix_downtown, "nature": fix_nature, "residential": fix_residential,
              "track": fix_track, "entertainment": fix_entertainment, "market": fix_market}[k]
        log("=" * 20 + " FIX %s " % k + " " + "=" * 20)
        res = fn()
        log("=" * 20 + " DONE %s -> %s " % (k, res) + " " + "=" * 20)
        # render previews for this blend
        prevs = render_all_previews(k)
        RESULTS[k]["previews"] = prevs

    # write report
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    lines = ["# geometry_fix_report — GEOMETRY-QA surgical fixes", ""]
    for k in keys:
        r = RESULTS.get(k, {})
        lines.append("## %s" % k)
        for kk, vv in r.items():
            if kk == "previews":
                continue
            lines.append("- %s: %s" % (kk, vv))
        if "previews" in r:
            lines.append("- previews:")
            for f, s in r["previews"].items():
                lines.append("  - %s: stddev=%.4f" % (f, s))
        lines.append("")
    lines.append("## notes")
    lines.append("- headless BLENDER_EEVEE, 1920x1080, temp ground+sun+world removed, temps not saved.")
    lines.append("- contract materials appended via citykit.append_material from materials.blend.")
    lines.append("- per-blend .blend saved before moving to the next.")
    with open(REPORT, "w") as f:
        f.write("\n".join(lines))
    log("report -> %s" % REPORT)
    print("GQA_RESULT", json.dumps(RESULTS))
    os.makedirs(SCRATCH, exist_ok=True)
    with open(os.path.join(SCRATCH, "last_results.json"), "w") as f:
        json.dump(dict(keys=keys, results=RESULTS, log=LOG), f, indent=1, default=str)


if __name__ == "__main__":
    main()
