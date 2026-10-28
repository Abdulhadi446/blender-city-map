# Lighting Module Report

- Script: /home/abdulhadi/Work/city/modules/lighting.py
- Blend: /home/abdulhadi/Work/city/out/lighting.blend
- Preview (aerial night): /home/abdulhadi/Work/city/out/lighting_preview.png
- Preview (street night): /home/abdulhadi/Work/city/out/lighting_street_preview.png

## Counts per kit type
- SM_Lamp_Arterial_01: 1072 instances (136 tris/mesh)
- SM_Lamp_Street_01: 592 instances (92 tris/mesh)
- SM_Lamp_Wall_01: 288 instances (76 tris/mesh)
- SM_Lamp_Highway_01: 230 instances (92 tris/mesh)
- SM_Signal_01: 386 instances (152 tris/mesh)
- SM_BollardLight_01: 900 instances (84 tris/mesh)
- SM_Uplight_01: 38 instances (84 tris/mesh)
- SM_FloodTower_01: 10 instances (228 tris/mesh)

- Unique meshes: 16
- Kit tris total (unique meshes): 944
- Instances total: 3516
- Tris unique: 1152
- Tris instanced: 384200
- Real lights: 102
- Emissive instances: 3516

## Real-vs-emissive split
- Real light objects: 102 (named LT_light_<nn>)
- Emissive instances: 3516 (lamp heads etc.)
- Signal lenses are emissive-only (no real lights).
- 60 spot lights for arterial lamp heads (sampled), 40 spot uplights for landmarks.

## ASSEMBLER NIGHT-RIG NOTES
- Recommended sun angle: low (5 deg) or off; haze moderate.
- Emissive multipliers: neon x4-8 per style bible; emissive_warm lamp heads x3-5.
- World/TOD owned by Assembler; this module's previews use a temporary dark world.
- Real lights budget used: 102 / 300.
