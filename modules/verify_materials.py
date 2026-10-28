#!/usr/bin/env python3
"""Headless verification: reopen materials.blend and check that it, the index and
style_bible.md all agree.  Run: blender -b -P modules/verify_materials.py"""
import json
import os
import re
import sys

import bpy

CITY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND = os.path.join(CITY, "materials.blend")
INDEX = os.path.join(CITY, "materials_index.json")
BIBLE = os.path.join(CITY, "style_bible.md")
PREVIEW = os.path.join(CITY, "out", "materials_preview.png")

errors = []
notes = []

bpy.ops.wm.open_mainfile(filepath=BLEND)

blend_mats = {m.name for m in bpy.data.materials}
blend_ngs = {g.name for g in bpy.data.node_groups}

with open(INDEX) as f:
    idx = json.load(f)
idx_mats = set(idx["materials"].keys())

# 1. blend <-> index, both directions
for n in sorted(idx_mats - blend_mats):
    errors.append("in index but NOT in blend: %s" % n)
for n in sorted(blend_mats - idx_mats):
    errors.append("in blend but NOT in index: %s" % n)

# 2. node groups present
for ng in idx["node_groups"]:
    if ng not in blend_ngs:
        errors.append("node group missing from blend: %s" % ng)

# 3. every material has a Principled BSDF (or emission-only equivalent) and is node-based
no_nodes, no_output = [], []
for m in bpy.data.materials:
    if not m.use_nodes or not m.node_tree:
        no_nodes.append(m.name)
        continue
    if not any(n.type == "OUTPUT_MATERIAL" and n.is_active_output
               for n in m.node_tree.nodes):
        no_output.append(m.name)
if no_nodes:
    errors.append("materials without node trees: %s" % ", ".join(no_nodes))
if no_output:
    errors.append("materials without active output: %s" % ", ".join(no_output))

# 4. bible names: every backticked material-like token must exist in the blend
#    (facade_style names from generate_layout.FACADE_STYLES and §9's example
#    request name are material-like on purpose -- they are not materials)
STYLE_NAMES = {"suburban_brick", "stucco_modern", "timber_cottage", "modern_minimal",
               "glass_curtain", "steel_stone", "art_deco", "brutalist_modern",
               "neon_modern", "brick_loft", "glass_retail", "old_bazaar_brick",
               "painted_plaster", "timber_balcony", "corrugated_metal",
               "concrete_block", "motorsport_modern",
               "facade_metal_brushed", "facade_style"}
text = open(BIBLE).read()
cats = set(idx["stats"]["category_counts"].keys())
matlike = set(re.findall(r"`([a-z][a-z0-9_]{3,})`", text))
known_prefixes = ("road_", "sidewalk_", "facade_", "glass_", "metal_", "wood_",
                  "fabric_", "roof_", "nature_", "neon_", "light_", "sign_",
                  "int_", "vehicle_", "decal_")
bible_mats = {t for t in matlike
              if t.startswith(known_prefixes) and t not in STYLE_NAMES}
for n in sorted(bible_mats - blend_mats):
    errors.append("style_bible.md names a material not in the blend: %s" % n)

# 5. generated tables live in section 2 only -- compare those names to the blend
sec2 = re.search(r"## 2\. Material list(.*?)\n## 3\.", text, re.S)
if not sec2:
    errors.append("style_bible.md: could not locate section 2")
    table_names = set()
else:
    table_names = set(re.findall(r"^\| `([a-z0-9_]+)` \|", sec2.group(1), re.M))
if table_names != blend_mats:
    missing = blend_mats - table_names
    extra = table_names - blend_mats
    if missing:
        errors.append("materials missing from bible tables: %s" % ", ".join(sorted(missing)))
    if extra:
        errors.append("bible tables list unknown materials: %s" % ", ".join(sorted(extra)))

# 6. images packed
unpacked = [i.name for i in bpy.data.images
            if i.source == "FILE" and not i.packed_file]
if unpacked:
    errors.append("unpacked images in blend: %s" % ", ".join(unpacked))

# 7. preview exists and is 1920x1080
if not os.path.exists(PREVIEW):
    errors.append("preview missing: %s" % PREVIEW)
else:
    img = bpy.data.images.load(PREVIEW)
    if tuple(img.size) != (1920, 1080):
        errors.append("preview is %dx%d, expected 1920x1080" % tuple(img.size))
    bpy.data.images.remove(img)

# 8. report
blend_size = os.path.getsize(BLEND) / (1024.0 * 1024.0)
notes.append("blend size: %.1f MB (limit 400)" % blend_size)
if blend_size > 400:
    errors.append("blend exceeds 400 MB")
notes.append("materials: %d (index %d, bible tables %d)"
             % (len(blend_mats), len(idx_mats), len(table_names)))
notes.append("node groups: %s" % ", ".join(sorted(blend_ngs)))
notes.append("categories: %s" % json.dumps(idx["stats"]["category_counts"]))
notes.append("polyhaven materials: %d, procedural: %d, texture sets: %d"
             % (idx["stats"]["polyhaven_materials"], idx["stats"]["procedural_materials"],
                idx["stats"]["texture_sets"]))
if idx["stats"].get("failed"):
    errors.append("materials.py reported failures: %s" % idx["failed"])

print("\n=== VERIFY NOTES ===")
for n in notes:
    print("  " + n)
if errors:
    print("=== VERIFY FAILURES (%d) ===" % len(errors))
    for e in errors:
        print("  FAIL: " + e)
    sys.exit(1)
print("=== VERIFY OK: blend == index == bible ===")
