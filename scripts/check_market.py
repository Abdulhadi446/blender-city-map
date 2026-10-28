#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/abdulhadi/Work/city/scripts')
import bpy, json
from pathlib import Path
from repair_report import ROOT, OUT, REPORTS

blend = OUT / 'market.blend'
bpy.ops.wm.open_mainfile(filepath=str(blend))

info = {}
lt_list = []
for o in bpy.data.objects:
    if o.type == 'LIGHT':
        lt_list.append(o.name)
info['light_total'] = len(lt_list)
info['lights'] = lt_list

lt_in_ml = 0
lt_in_ml_names = []
def find_coll(name):
    for c in bpy.data.collections:
        if c.name == name:
            return c
    return None
mls = find_coll('Market/Lights')
if mls:
    for o in mls.objects:
        if o.type == 'LIGHT':
            lt_in_ml += 1
            lt_in_ml_names.append(o.name)
info['lights_in_Market_Lights'] = lt_in_ml
info['lights_in_Market_Lights_names'] = lt_in_ml_names

info['has_buildable_rect_prop'] = False
for o in bpy.data.objects:
    if 'buildable_rect' in o.keys():
        info['has_buildable_rect_prop'] = True
        break

jpath = REPORTS / 'market_fix_check.json'
with open(jpath,'w') as f:
    json.dump(info,f,indent=2)
print(json.dumps(info))
