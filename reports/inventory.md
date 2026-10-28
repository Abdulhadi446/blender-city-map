# Out-blend inventory (measured 2026-10-28T16:57:49)

One blender process per file, read-only pass (`blender -b <file> -P measure.py`), no saves, no renders.
`out/city_master.blend` intentionally NOT opened (under construction by another process).
Triangles are exact per-datablock sums (triangulated); "instanced" = sum over all mesh objects
(incl. colliders and kit source objects). Engine of every file: BLENDER_EEVEE. Missing images: none.

| module | size MB | objects | mesh objects | meshes | tris unique | tris instanced | lights | colliders | cameras | missing imgs | report status | previews | report issues |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| civic | 86.4 | 686 | 618 | 192 | 128386 | 156234 | 68 | 40 | 0 | 0 | fresh-verified (counts match blend) | 2 | 6 |
| commercial | 32.2 | 300 | 198 | 74 | 328368 | 332808 | 102 | 35 | 0 | 0 | fresh | 2 | 0 |
| downtown | 22.7 | 5586 | 5586 | 705 | 299894 | 2209642 | 0 | 108 | 0 | 0 | STALE (objects/meshes/tris differ from measured) | 2 | 0 |
| entertainment | 46.0 | 3823 | 3823 | 519 | 528780 | 948136 | 0 | 288 | 0 | 0 | STALE (counts behind rebuild) | 2 | 3 |
| flyover | 21.3 | 1243 | 1243 | 33 | 23592 | 44680 | 0 | 52 | 0 | 0 | fresh-verified (counts match blend) | 2 | 4 |
| interiors | 14.6 | 194 | 184 | 156 | 2724 | 3360 | 10 | 6 | 0 | 0 | fresh-verified (counts match blend) | 2 | 1 |
| lighting | 2.8 | 3634 | 3532 | 16 | 1152 | 384200 | 102 | 8 | 0 | 0 | fresh-verified (counts match blend) | 2 | 0 |
| market | 53.2 | 15291 | 15044 | 431 | 682410 | 4316886 | 247 | 1236 | 0 | 0 | refreshed 2026-10-28 (materials list pruned to blend usage) | 2 | 0 |
| nature | 25.7 | 27304 | 27304 | 92 | 42804 | 4971676 | 0 | 12585 | 0 | 0 | STALE (count fields behind rebuild) | 2 | 0 |
| props | 11.2 | 4135 | 4135 | 73 | 2224 | 254452 | 0 | 34 | 0 | 0 | refreshed 2026-10-28 (full regen) | 2 | 3 |
| residential | 66.9 | 14581 | 14581 | 994 | 476420 | 1618110 | 0 | 844 | 0 | 0 | refreshed 2026-10-28 (full regen) | 2 | 0 |
| roads | 25.6 | 5146 | 5144 | 3208 | 69882 | 122886 | 1 | 1137 | 1 | 0 | fresh-verified (counts match blend) | 1 | 9 |
| sports | 17.7 | 1373 | 1356 | 50 | 3412 | 101036 | 17 | 17 | 0 | 0 | fresh-verified (counts match blend) | 2 | 0 |
| track | 26.8 | 1216 | 1208 | 968 | 153256 | 163946 | 8 | 11 | 0 | 0 | STALE (report 2026-10-26, blend rebuilt 16:28) | 2 | 0 |
| traffic | 0.5 | 4855 | 4853 | 28 | 1644 | 560992 | 2 | 13 | 0 | 0 | fresh-verified (counts match blend) | 2 | 0 |
| transport | 16.8 | 184 | 171 | 69 | 20688 | 23232 | 12 | 31 | 1 | 0 | refreshed 2026-10-28 (objects/lights/tris/expanded) | 2 | 2 |

## Known issues harvested from reports

- props: `orange_cone` material still missing (col_placeholder fallback on cone stack + lifebuoy kit); stray cable instances far outside the 3x3 km tile.
- roads: 9 notes (ground band overlap with flyover on ring / 11 elevated ramp decks not yet built / landlocked facilities needing spurs / street-alley kerb assumptions / sidewalk openings cut for crossings).
- flyover: ramp start inside ring deck by 1 cm; ramp swept by raised-cosine bulge; terminus overlap wedge; instance transforms intentionally not applied.
- civic: 6 facilities' rects touch a road corridor (ARCADE_GAMES, CASINO, CIVIC_TOWN_OFFICES, GALLERY_ART, MUSEUM_CITY, UNIVERSITY_FACULTY).
- entertainment: clearance policy note; parcels_E ships 8 cells not 9; previews had a temporary ground slab (removed).
- interiors: kit sources keep translation-only transforms (instancing convention).
- transport: no road geometry by design; TRK_* ownership per program (verify with Track agent).
- residential: no camera in the blend (preview_error captured in residential_report.json).

## Reports refreshed vs left untouched in this catch-up pass

- FULL REGEN: residential_report (.json/.md), props_report (.json/.md).
- COUNT/META REFRESH: market_report (materials usage pruned), transport_report (objects/lights/tris/expanded counts).
- LEFT UNTOUCHED after verification against the blend (all key counts reproduce): civic, flyover, interiors, lighting, roads, sports, traffic.
- NOT IN SCOPE but stale (leave to owning agents): downtown, entertainment, nature, track reports; commercial_report is current.
