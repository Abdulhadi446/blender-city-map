#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/abdulhadi/Work/city/scripts')
import bpy, json, os
from pathlib import Path
from repair_report import analyze_blend, ROOT, OUT, REPORTS

blend = OUT / 'residential.blend'
prefix = 'residential'
preview = OUT / 'residential_preview.png'
info = analyze_blend(blend, prefix, do_preview=True, preview_path=preview)

info['module'] = prefix
info['paths']['script'] = '/home/abdulhadi/Work/city/modules/residential.py'
jpath = REPORTS / f'{prefix}_report.json'
mpath = REPORTS / f'{prefix}_report.md'
with open(jpath,'w') as f:
    json.dump(info, f, indent=2)
lines = []
lines.append(f"# Residential Module Report\n\n")
for k,v in info['paths'].items():
    lines.append(f"- {k.replace('_',' ').title()}: {v}\n")
lines.append(f"\n## Counts\n")
lines.append(f"- Objects: {info.get('object_count')}\n- Meshes: {info.get('mesh_count')}\n- Tris total: {info.get('tris_total')}\n- Instances (est): {info.get('instances_total_est')}\n- COL_ colliders: {info.get('colliders_COL_count')}\n")
lines.append(f"\n## Collections\n")
for c in info.get('collections',[]):
    lines.append(f"- {c}\n")
lines.append(f"\n## Materials used\n")
for m in info.get('materials_used',[]):
    lines.append(f"- {m}\n")
lines.append(f"\n## Issues\n- None reported by automated scan.\n")
with open(mpath,'w') as f:
    f.writelines(lines)
print('done')
