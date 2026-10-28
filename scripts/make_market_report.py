#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/abdulhadi/Work/city/scripts')
import bpy, json, os
from pathlib import Path
from repair_report import analyze_blend, ROOT, OUT, REPORTS

blend = OUT / 'market.blend'
prefix = 'market'
info = analyze_blend(blend, prefix, do_preview=False)

info['module'] = prefix
info['paths']['script'] = '/home/abdulhadi/Work/city/modules/market.py'
try:
    with open(REPORTS / 'market_fix_check.json') as f:
        fx = json.load(f)
    info['fix_checks'] = fx
    info['fix_lights_le_250'] = fx.get('light_total', 999) <= 250
    info['fix_lights_in_Market_Lights'] = fx.get('lights_in_Market_Lights', -1)
    info['fix_has_buildable_rect_prop_detected'] = fx.get('has_buildable_rect_prop', False)
except Exception as e:
    info['fix_checks_error'] = str(e)

jpath = REPORTS / f'{prefix}_report.json'
mpath = REPORTS / f'{prefix}_report.md'
with open(jpath, 'w') as f:
    json.dump(info, f, indent=2)

lines = []
lines.append('# Market Module Report\n\n')
for k, v in info['paths'].items():
    lines.append(f"- {k.replace('_',' ').title()}: {v}\n")
lines.append('\n## Counts\n')
lines.append(f"- Objects: {info.get('object_count')}\n- Meshes: {info.get('mesh_count')}\n- Tris total: {info.get('tris_total')}\n- Instances (est): {info.get('instances_total_est')}\n")
lines.append('\n## Collections\n')
for c in info.get('collections', []):
    lines.append(f"- {c}\n")
lines.append('\n## Materials used\n')
for m in info.get('materials_used', []):
    lines.append(f"- {m}\n")
lines.append('\n## Fix verification\n')
fc = info.get('fix_checks', {})
lines.append(f"- Lights total (LT_market_*): {fc.get('light_total')}\n")
lines.append(f"- Lights in Market/Lights collection: {fc.get('lights_in_Market_Lights')}\n")
lines.append(f"- Lights in Market/Lights names count: {len(fc.get('lights_in_Market_Lights_names', []))}\n")
lines.append(f"- buildable_rect prop detected on objects: {fc.get('has_buildable_rect_prop')}\n")
lines.append(f"- PASS/FAIL lights_le_250 (<=250): {'PASS' if info.get('fix_lights_le_250') else 'FAIL'}\n")
lines.append(f"- PASS/FAIL lights_in_Market_Lights (reported): {'INFO' if fc.get('lights_in_Market_Lights') == 0 else 'CHECK'}\n")
lines.append('\n## Issues\n- Automated scan only; see fix_checks above.\n')
with open(mpath, 'w') as f:
    f.writelines(lines)
print('done')
