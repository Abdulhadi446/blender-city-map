#!/usr/bin/env python3
"""material_fix_traffic.py — give the traffic kit real materials.

out/traffic.blend was saved with every mesh stripped of material slots (1 unused
material in the file, 4 853 / 4 855 objects with 0 slots), so the whole vehicle
fleet rendered untextured white/black.

The kit meshes are merged part islands (body, cabin, 4 wheels, 2 lights, roof
extras) with no per-part names left, so parts are recovered from connected
components and their bounding boxes, then assigned by material ROLE:

    body / cab / cargo        -> metal_painted_* (9 variants, cycled per model)
    cabin / window band       -> glass_dark
    tyres                     -> metal_painted_dark  (blackest painted metal)
    head lights (+X)          -> emissive_warm
    tail lights (-X)          -> neon_red
    taxi roof sign            -> sign_white
    police light bar          -> neon_red
    underbody (body bottom)   -> metal_steel
    COL_* collider boxes      -> col_placeholder

Materials are appended from /city/materials.blend (citykit.append_material); no
material is created. Slots live on the MESH datablock, so the ~4 850 linked
duplicates share them.

    blender -b -P modules/material_fix_traffic.py
"""
from __future__ import annotations

import json
import os
import sys

import bpy

ROOT = "/home/abdulhadi/Work/city"
sys.path.insert(0, os.path.join(ROOT, "modules"))
import citykit as ck  # noqa: E402

BLEND = os.path.join(ROOT, "out", "traffic.blend")
PAINTS = ["metal_painted_charcoal", "metal_painted_navy", "metal_painted_teal",
          "metal_painted_sand", "metal_painted_sage", "metal_painted_oxblood",
          "metal_painted_bone", "metal_painted_mustard"]
# keep the obvious liveries readable in previews
FORCED_PAINT = {"Taxi": "metal_painted_mustard", "Police": "metal_painted_charcoal",
                "Ambulance": "metal_painted_bone", "Bus": "metal_painted_teal",
                "Coach": "metal_painted_bone"}
SLOTS = ["paint", "glass", "tyre", "headlight", "taillight", "sign", "steel"]
SLOT_MAT = {"paint": None, "glass": "glass_dark", "tyre": "metal_painted_dark",
            "headlight": "emissive_warm", "taillight": "neon_red",
            "sign": "sign_white", "steel": "metal_steel"}
GLASS_TYPES = ("Sedan", "Hatchback", "SUV", "Taxi", "Police", "Ambulance", "Bus", "Coach")


def islands(me):
    """Connected components of the mesh; returns list of lists of face indices."""
    n = len(me.vertices)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for e in me.edges:
        union(e.vertices[0], e.vertices[1])
    groups = {}
    for p in me.polygons:
        groups.setdefault(find(p.vertices[0]), []).append(p.index)
    return list(groups.values())


def bbox(me, faces):
    vs = {v for f in faces for v in me.polygons[f].vertices}
    co = [me.vertices[v].co for v in vs]
    return (min(c.x for c in co), max(c.x for c in co),
            min(c.y for c in co), max(c.y for c in co),
            min(c.z for c in co), max(c.z for c in co))


def classify(me, name):
    """Return (island_material_key, body_island_faces) for one vehicle mesh."""
    isl = islands(me)
    boxes = [bbox(me, f) for f in isl]
    x0 = min(b[0] for b in boxes); x1 = max(b[1] for b in boxes)
    y0 = min(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
    z0 = min(b[4] for b in boxes); z1 = max(b[5] for b in boxes)
    L, W, H = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6), max(z1 - z0, 1e-6)
    vol = [max((b[1] - b[0]) * (b[3] - b[2]) * (b[5] - b[4]), 0.0) for b in boxes]
    two_wheel = ("Bicycle" in name or "Motorcycle" in name)
    if two_wheel:
        # frame / tank is the only island that does not touch the ground
        body_i = max(range(len(isl)), key=lambda i: boxes[i][4])
    else:
        body_i = max(range(len(isl)), key=lambda i: vol[i])
    bb = boxes[body_i]
    Lb, Wb, Hb = bb[1] - bb[0], bb[3] - bb[2], max(bb[5] - bb[4], 1e-6)
    out = {}
    for i, b in enumerate(boxes):
        ex, ey, ez = b[1] - b[0], b[3] - b[2], b[5] - b[4]
        cx, cy, cz = (b[0] + b[1]) / 2, (b[2] + b[3]) / 2, (b[4] + b[5]) / 2
        key = "paint"
        if i == body_i:
            key = "paint"
        elif two_wheel and b[4] <= 0.06 * H:
            key = "tyre"
        elif (b[4] <= 0.15 * H and ex <= 0.45 * L and ey <= 0.85 * Wb
              and ez <= 0.98 * H):
            key = "tyre"
        elif (any(t in name for t in GLASS_TYPES) and ey < Wb - 0.09
              and ey >= 0.5 * Wb and ez >= 0.15 * Hb and b[5] >= 0.5 * H):
            key = "glass"
        elif (max(ex, ey, ez) <= 0.55 and abs(cx) >= 0.45 * L
              and cz >= 0.3 * H):
            key = "headlight" if cx > 0 else "taillight"
        elif b[4] >= 0.72 * H:
            key = "taillight" if "Police" in name else "sign"
        out[i] = key
    return out, isl, body_i


def main():
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    mats = {}
    for key, nm in SLOT_MAT.items():
        if nm:
            mats[key] = ck.append_material(nm)
    mats["col"] = ck.append_material("col_placeholder")

    report = {"meshes": {}, "materials_existing": sorted(m.name for m in bpy.data.materials)}
    meshes = list(bpy.data.meshes)
    for mi, me in enumerate(sorted(meshes, key=lambda m: m.name)):
        name = me.name
        me.materials.clear()
        for p in me.polygons:
            p.material_index = 0
        if name.startswith("COL_"):
            me.materials.append(mats["col"])
            report["meshes"][name] = {"kind": "collider", "faces": len(me.polygons)}
            continue
        base = name.replace("LOD1_", "").replace("LOD2_", "")
        vehicle = next((v for v in FORCED_PAINT if v in base), None)
        if vehicle:
            paint_name = FORCED_PAINT[vehicle]
        else:
            paint_name = PAINTS[mi % len(PAINTS)]
        mats["paint"] = ck.append_material(paint_name)
        for s in SLOTS:
            me.materials.append(mats[s])
        idx = {s: i for i, s in enumerate(SLOTS)}
        parts, isl, body_i = classify(me, name)
        for i, faces in enumerate(isl):
            key = parts.get(i, "paint")
            for f in faces:
                me.polygons[f].material_index = idx[key]
        # underbody / chassis trim of the body island -> metal_steel
        body_faces = isl[body_i]
        for f in body_faces:
            p = me.polygons[f]
            if p.normal.z < -0.7:
                p.material_index = idx["steel"]
        counts = {}
        for p in me.polygons:
            counts[SLOTS[p.material_index]] = counts.get(SLOTS[p.material_index], 0) + 1
        report["meshes"][name] = {"kind": "vehicle", "paint": paint_name,
                                  "faces": len(me.polygons), "parts": counts,
                                  "islands": len(isl)}
        me.update()
    # assign -> mesh data slots propagate to every object
    report["paint_variants"] = PAINTS
    report["objects"] = len(bpy.data.objects)
    bad = [o.name for o in bpy.data.objects if o.type == "MESH"
           and (len(o.material_slots) == 0 or any(s.material is None for s in o.material_slots))]
    report["objects_without_material"] = len(bad)
    report["objects_without_material_sample"] = bad[:10]
    report["materials_after"] = sorted(m.name for m in bpy.data.materials)
    bpy.ops.wm.save_mainfile(filepath=BLEND)
    json.dump(report, open("/tmp/opencode/mf/traffic_mats.json", "w"), indent=1)
    print("TRAFFIC_MATS", json.dumps({k: v for k, v in report.items() if k != "meshes"}))
    for k, v in report["meshes"].items():
        print("MESH", k, json.dumps(v))
    print("BAD", len(bad))


if __name__ == "__main__":
    main()
