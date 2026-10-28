# Roads module report — FULL network (454 edges)

Generated: 2026-10-27T15:10:06

Files

- script: `modules/roads.py`
- blend: `out/roads.blend`
- preview: `out/roads_preview.png` (1920x1080, EEVEE)
- pilot reference blend: `/tmp/opencode/roads_pilot_ref.blend`

## Scope (layout.json)

* arterial: **134** edges, 40 km
* street: **148** edges, 22 km
* alley: **144** edges, 10 km
* highway: **16** edges, 11 km
* interchange_ramp: **12** edges, 2 km
* total: **454** edges / **322** nodes

## Counts

| item | value |
|---|---|
| objects in module | 5144 |
| triangles unique (whole file) | 69882 |
| triangles instanced (module) | 122886 |
| colliders | 1137 |
| zebra crosswalks (legs / lights) | 409 / 111 |
| access spurs | 108 |
| infield facilities (Track access, no spur) | 17 |
| ramp connectors (ring aprons) | 12 |
| junction patches (quads) | {'arterial': 292, 'street': 148, 'alley': 216} |
| curb-return fillets | 376 |
| manhole/drain instances | 1938 |
| build seconds | 52.6 |

## PILOT PARITY

Reference: pilot blend snapshot + facts extracted per edge (/home/abdulhadi/Work/city/reports/roads_pilot_reference.json).

- status: **PASS** — 149/149 pilot edges identical (0 failed)
- checks: z levels, materials, lateral envelope, per-kind cross-section, alley clip distance

The pilot's 5 arterial edges and 144 market alleys keep the exact same cross-section: carriageway top z=0, kerb/sidewalk top z=0.15, median 3.0 m raised 0.15, markings z=0.005, crosswalks z=0.007, arterial envelope 12.0 m (carriageway 9.5 + sidewalk 2.5), alley envelope 2.5 m cobble clipped 12 m off the arterial centreline. What changed on those edges is only the number of junction cuts (the rest of the network now exists) and the crosswalk positions at the newly built perpendicular legs.

## Geometry facts for the Assembler

* carriageway top **z = 0.0**; kerb / sidewalk / median top **z = 0.15**; markings **z = 0.005**; zebra stripes **z = 0.007**
* arterial: envelope halfwidth **12.0** (carriageway 9.5 + 2.5 sidewalk), 3.0 m median raised 0.15, 2 lanes each way
* street: envelope halfwidth **6.0** (carriageway 3.5 + 2.5 sidewalk), one lane each way, dashed centre line
* alley: envelope halfwidth **2.5**, cobble, ends clipped **12 m** off every arterial centreline
* highway ring: ground service road z=0, asphalt 10 m wide (u +/-5), gravel verge to u=14, dirt to u=20 (both z=-0.05); ring deck at z=8 is Flyover's
* ring bands are trimmed at the 4 square corners by their own half-width (asphalt 5 m, gravel 14 m, dirt 20 m) and closed with nested dirt/gravel/asphalt corner patches, so the asphalt is continuous
* access spurs: 108 x 8 m asphalt outside the circuit zone, z=0, perpendicular to the nearest road, flush with the facility rect edge, plus a 8.5 m dropped-kerb opening; the 17 infield facilities use Track's gated access road + bridge
* 12 interchange sites: ring apron (8 x 30 m, z=0) + 18 m foot pad where the ramp reaches the ground (11 pads; X_N_600 is Flyover's)
* everything under collection **Roads** with sub-collections Meshes / Colliders / Lights; instances keep their placement transforms
* preview: `citykit.make_preview` now derives camera clip_start / clip_end from the camera-target distance, so 1920x1080 aerial views are no longer cut off by the 100 m default clip

## Materials used (12)

* `asphalt`
* `asphalt_highway`
* `asphalt_worn`
* `cobble_stone`
* `curb_concrete`
* `dirt`
* `gravel`
* `marking_white`
* `marking_yellow`
* `metal_steel`
* `rust`
* `sidewalk_concrete`

## Known issues

* The Flyover module already builds a ground band for H_07/H_08 (its NE ring corner). This module builds all 16 ring segments as contracted, so H_07/H_08 ground bands exist twice; the objects carry dedupe_with_flyover=True. The Assembler should keep ONE copy (our ground band is square-cornered per layout.json, Flyover's NE corner is a 120 m arc) - dropping our H_07/H_08 objects is the safer choice.
* Elevated decks for the other 11 ramps are not built anywhere yet: this module only provides their ground tie-ins (ring apron + 18 m foot pad).
* Ramp X_N_600 already has a landing flare from the Flyover module, so its foot pad is not duplicated here (its ring apron is).
* Spurs: strict geometric adjacency finds 125 landlocked facilities (the brief said 124). 108 get a new 8 m spur, none of which enters the circuit corridor or the racing surface. The other 17 sit inside the circuit zone and are served by the Track module's gated access road + bridge at (612,-1040) and its infield loop; Roads does not lay asphalt across the track. That loop serves the pit / paddock / museum / fan-zone block; the east infield (karting, parking, skid pad, scoring tower, floodlight B) and the north stand still need infield service roads from Track.
* Alley mouths keep the pilot ramp (0 at the outer kerb line rising to 0.15 at the carriageway edge); street mouths are flush, filled by the street's own asphalt and sidewalk tongues.
* Sidewalk / kerb strips are shells (top z=0.15, faces to z=0); this module contains no ground plane.
* Manhole / drain instances keep their placement transforms on purpose (baking them would move the single shared mesh).
* Zebra crosswalk stripes are one merged mesh (SM_Crosswalk_01), not instances: 5 quads per leg is cheaper than 5 instanced objects.
* Sidewalk openings are cut for every crossing leg, so the pedestrian route across a junction uses the zebra ramps rather than a continuous raised footway.

json report: `reports/roads_report.json`
