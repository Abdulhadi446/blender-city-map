# Props Module Report

- Script: /home/abdulhadi/Work/city/modules/props.py
- Blend: /home/abdulhadi/Work/city/out/props.blend
- Preview: /home/abdulhadi/Work/city/out/props_preview.png
- Street Preview: /home/abdulhadi/Work/city/out/props_street_preview.png

## Counts
- Unique kit meshes: 39 (all mesh datablocks: 73)
- Kit tris total (unique, exact): 1816
- Objects total: 4135
- Tris instanced total (scene, incl. colliders): 254452
- COL_ colliders: 34

## Per type
- bin: 443
- hydrant: 536
- bollard: 312
- bench: 416
- bikerack: 416
- planter: 634
- mailbox: 51
- utilitybox: 0
- postbox: 17
- newsbox: 0
- parkingmeter: 14
- conestack: 5
- workbarrier: 5
- jersey: 0
- streetsign: 317
- busshelter: 25
- tramstop: 0
- pigeonpost: 0
- fireescape: 0
- awningbracket: 0
- cable: 360
- satellitedish: 0
- watertank: 173
- chimney: 71
- acunit: 247
- billboard: 0
- aframe: 0
- marketstall: 0
- crowdbarrier: 0
- phonekiosk: 0
- lifebuoy: 8
- lakerailing: 12
- noticeboard: 0
- catenary: 0

## Materials used
- brick_red
- canvas_tarp
- col_placeholder
- concrete
- dirt
- emissive_warm
- marking_yellow
- metal_painted_dark
- metal_steel
- sign_metal
- wood_old
- wood_painted

## Issues
- Material missing for SM_ConeStack_01_01: orange_cone - Material 'orange_cone' not found in materials.blend; cone/cone-adjacent kit pieces fall back to col_placeholder. State vs 2026-10-28 rebuild.
- Material missing for SM_LifeBuoy_01_01: orange_cone - Material 'orange_cone' not found in materials.blend; lifebuoy ring falls back to col_placeholder. State vs 2026-10-28 rebuild.
- Stray instances far outside the city bounds (bbox min x -50.9 km, max y +21.0 km, max z +3.7 km): mostly SM_Cable_ power-line runs placed far beyond the 3x3 km tile.

## Needs from other agents
- orange_cone material, to replace the col_placeholder fallback on SM_ConeStack_01_01 and SM_LifeBuoy_01_01.
