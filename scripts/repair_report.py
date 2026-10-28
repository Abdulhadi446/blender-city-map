#!/usr/bin/env python3
import bpy, json, os, math
from pathlib import Path

ROOT = Path('/home/abdulhadi/Work/city')
OUT = ROOT / 'out'
REPORTS = ROOT / 'reports'

def count_mesh_tris(me):
    try:
        if me is None: return 0
        # triangulate not strictly required if already triangulated, but count polygon tris
        tris = 0
        for p in me.polygons:
            tris += len(p.vertices) - 2 if len(p.vertices) >= 3 else 0
        return tris
    except Exception:
        return 0

def analyze_blend(blend_path, report_prefix, do_preview=False, preview_path=None):
    # open blend
    bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    info = {}
    info['module'] = report_prefix
    info['paths'] = {
        'blend': str(blend_path),
    }
    if preview_path:
        info['paths']['preview'] = str(preview_path)
    # counts
    objects = list(bpy.data.objects)
    meshes = list(bpy.data.meshes)
    info['object_count'] = len(objects)
    info['mesh_count'] = len(meshes)
    # tris
    total_tris = 0
    for me in meshes:
        total_tris += count_mesh_tris(me)
    info['tris_total'] = total_tris
    # instances rough: objects sharing mesh
    inst_map = {}
    for o in objects:
        if o.type == 'MESH' and o.data:
            key = o.data.name
            inst_map[key] = inst_map.get(key, 0) + 1
    info['instances_by_mesh'] = {k:v for k,v in sorted(inst_map.items(), key=lambda x:-x[1])[:50]}
    info['instances_total_est'] = sum(inst_map.values())
    # collections
    colls = []
    for c in bpy.data.collections:
        colls.append(c.name)
    info['collections'] = sorted(colls)
    # materials
    mats = set()
    for o in objects:
        for ms in getattr(o.data, 'materials', []) or []:
            if ms and ms.name:
                mats.add(ms.name)
        # slots
        try:
            for slot in o.material_slots:
                if slot.material and slot.material.name:
                    mats.add(slot.material.name)
        except Exception:
            pass
    info['materials_used'] = sorted(list(mats))
    # colliders
    coll_count = 0
    for o in objects:
        if o.name.startswith('COL_'):
            coll_count += 1
    info['colliders_COL_count'] = coll_count
    # preview
    if do_preview and preview_path:
        try:
            os.makedirs(os.path.dirname(str(preview_path)), exist_ok=True)
            scene = bpy.context.scene
            scene.render.engine = 'BLENDER_EEVEE'
            scene.render.resolution_x = 1920
            scene.render.resolution_y = 1080
            scene.render.filepath = str(preview_path)
            bpy.ops.render.render(write_still=True)
            info['paths']['preview_rendered'] = True
        except Exception as e:
            info['paths']['preview_error'] = str(e)
    return info
