#!/usr/bin/env python3
import json, os
from pathlib import Path
from datetime import datetime

ROOT = Path('/home/abdulhadi/Work/city')
OUT = ROOT / 'out'
REPORTS = ROOT / 'reports'

rows = []
for blend in sorted(OUT.glob('*.blend')):
    name = blend.stem
    # find report
    rj = REPORTS / f'{name}_report.json'
    rm = REPORTS / f'{name}_report.md'
    row = {
        'module': name,
        'blend': str(blend),
        'blend_size': blend.stat().st_size,
        'blend_mtime': blend.stat().st_mtime,
        'report_json': rj.exists(),
        'report_md': rm.exists(),
        'report_mtime': None,
    }
    if rj.exists():
        row['report_mtime'] = rj.stat().st_mtime
    # try to read counts
    try:
        if rj.exists():
            with open(rj) as f:
                d = json.load(f)
            row['tris_total'] = d.get('tris_total') or d.get('tris_instanced') or d.get('tris_instanced_total') or None
            row['object_count'] = d.get('object_count') or d.get('objects') or None
            row['issues'] = d.get('issues', [])
    except Exception as e:
        row['read_err'] = str(e)
    rows.append(row)

# write inventory
out = []
out.append('# Inventory\n\n')
out.append('| module | blend size (MB) | tris | objects | report json/md | report older than blend | previews present |\n')
out.append('|---|---|---|---|---|---|---|\n')
for r in rows:
    mb = round(r['blend_size']/1024/1024,1)
    tris = r.get('tris_total') or '-'
    objs = r.get('object_count') or '-'
    rstat = 'Y/Y' if r['report_json'] and r['report_md'] else ('Y/N' if r['report_json'] else 'N/N')
    older = 'n/a'
    if r['report_mtime'] and r['blend_mtime']:
        older = 'YES' if r['report_mtime'] < r['blend_mtime'] else 'NO'
    prev = []
    for p in [OUT/f"{r['module']}_preview.png", OUT/f"{r['module']}_street_preview.png"]:
        if p.exists(): prev.append(p.name)
    out.append(f"| {r['module']} | {mb} | {tris} | {objs} | {rstat} | {older} | {','.join(prev) or '-'} |\n")

with open(REPORTS / 'inventory.md', 'w') as f:
    f.writelines(out)
print('done')
