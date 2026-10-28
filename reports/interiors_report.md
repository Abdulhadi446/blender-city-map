# Interiors module report

Module: `interiors`  |  blend: `out/interiors.blend`  |  engine: BLENDER_EEVEE  |  units: metres, Z-up

## Program.json facilities (Interiors owning module)

| id | district | interior_tier | budget_class |
|---|---|---|---|
| INT_HERO_INTERIORS | R | 1 | regular |
| INT_SHELL_INTERIORS | I | 1 | regular |
| INT_MALL_FITOUT | D | 1 | regular |

All three are 'no new footprint' passes over already-placed buildings; this module provides the shared kits and reference rooms only. Building shells remain with their district modules.

## INT_HERO_INTERIORS -> market parcels (skip_list)

INT_HERO_INTERIORS references 39 parcels (E15 / D11 / M7 / R6). The 7 market-district parcels are exactly market's 7 tier-1 parcels, already fitted by the market module, so they are **skipped** to avoid duplication.
Skipped ids: BZ_6_6_1_1, B_7_6_2_0_0_0, B_5_7_1_0_0_3, B_5_7_0_2_3_0, B_5_7_1_3_2_3, B_6_7_3_3_0_2, B_7_7_1_3_2_0
Remaining 32 parcels (E/D/R) are district-owned; kits are provided for the Assembler to place there.

| skip id | district | reason |
|---|---|---|
| BZ_6_6_1_1 | M | market t1 interior already built by market module - skipped to avoid duplication |
| B_7_6_2_0_0_0 | M | market t1 interior already built by market module - skipped to avoid duplication |
| B_5_7_1_0_0_3 | M | market t1 interior already built by market module - skipped to avoid duplication |
| B_5_7_0_2_3_0 | M | market t1 interior already built by market module - skipped to avoid duplication |
| B_5_7_1_3_2_3 | M | market t1 interior already built by market module - skipped to avoid duplication |
| B_6_7_3_3_0_2 | M | market t1 interior already built by market module - skipped to avoid duplication |
| B_7_7_1_3_2_0 | M | market t1 interior already built by market module - skipped to avoid duplication |

## Shared interior kits

Six kit families (office, hotel, gym, restaurant, shop, home). One source mesh per family/part, named `INT_<kit>_<part>_<nn>`, instanced via linked duplicates (shared datablock). Each part <= 5 k tris.

| family | parts | unique tris |
|---|---|---|
| office | 24 | 440 |
| hotel | 22 | 428 |
| gym | 18 | 356 |
| restaurant | 22 | 416 |
| shop | 19 | 368 |
| home | 27 | 428 |

| family | part | tris |
|---|---|---|
| office | wall_paint | 12 |
| office | wall_wallpaper | 12 |
| office | floor_tile | 12 |
| office | floor_carpet | 12 |
| office | floor_wood | 12 |
| office | ceiling | 12 |
| office | door_frame_arch | 36 |
| office | counter | 12 |
| office | reception_desk | 12 |
| office | shelving | 72 |
| office | table | 24 |
| office | chair | 36 |
| office | sofa | 24 |
| office | coffee_table | 12 |
| office | partition | 12 |
| office | wall_shelf | 12 |
| office | rug | 12 |
| office | pendant_lamp | 32 |
| office | framed_art | 12 |
| office | mirror | 12 |
| office | curtain | 12 |
| office | plant | 12 |
| office | tv_dark | 12 |
| office | tv_screen | 12 |
| hotel | wall_paint | 12 |
| hotel | wall_wallpaper | 12 |
| hotel | floor_tile | 12 |
| hotel | floor_carpet | 12 |
| hotel | floor_wood | 12 |
| hotel | ceiling | 12 |
| hotel | door_frame_arch | 36 |
| hotel | reception_desk | 12 |
| hotel | shelving | 72 |
| hotel | table | 24 |
| hotel | chair | 36 |
| hotel | sofa | 24 |
| hotel | coffee_table | 12 |
| hotel | bed | 24 |
| hotel | partition | 12 |
| hotel | wall_shelf | 12 |
| hotel | rug | 12 |
| hotel | pendant_lamp | 32 |
| hotel | framed_art | 12 |
| hotel | mirror | 12 |
| hotel | curtain | 12 |
| hotel | plant | 12 |
| gym | wall_paint | 12 |
| gym | wall_wallpaper | 12 |
| gym | floor_tile | 12 |
| gym | floor_wood | 12 |
| gym | ceiling | 12 |
| gym | door_frame_arch | 36 |
| gym | shelving | 72 |
| gym | table | 24 |
| gym | chair | 36 |
| gym | partition | 12 |
| gym | wall_shelf | 12 |
| gym | rug | 12 |
| gym | pendant_lamp | 32 |
| gym | mirror | 12 |
| gym | curtain | 12 |
| gym | plant | 12 |
| gym | tv_dark | 12 |
| gym | tv_screen | 12 |
| restaurant | wall_paint | 12 |
| restaurant | wall_wallpaper | 12 |
| restaurant | floor_tile | 12 |
| restaurant | floor_wood | 12 |
| restaurant | ceiling | 12 |
| restaurant | door_frame_arch | 36 |
| restaurant | counter | 12 |
| restaurant | shelving | 72 |
| restaurant | table | 24 |
| restaurant | chair | 36 |
| restaurant | sofa | 24 |
| restaurant | coffee_table | 12 |
| restaurant | partition | 12 |
| restaurant | wall_shelf | 12 |
| restaurant | rug | 12 |
| restaurant | pendant_lamp | 32 |
| restaurant | framed_art | 12 |
| restaurant | mirror | 12 |
| restaurant | curtain | 12 |
| restaurant | plant | 12 |
| restaurant | tv_dark | 12 |
| restaurant | tv_screen | 12 |
| shop | wall_paint | 12 |
| shop | wall_wallpaper | 12 |
| shop | floor_tile | 12 |
| shop | floor_wood | 12 |
| shop | ceiling | 12 |
| shop | door_frame_arch | 36 |
| shop | counter | 12 |
| shop | shelving | 72 |
| shop | table | 24 |
| shop | chair | 36 |
| shop | partition | 12 |
| shop | wall_shelf | 12 |
| shop | rug | 12 |
| shop | pendant_lamp | 32 |
| shop | framed_art | 12 |
| shop | mirror | 12 |
| shop | curtain | 12 |
| shop | plant | 12 |
| shop | tv_dark | 12 |
| home | wall_paint | 12 |
| home | wall_wallpaper | 12 |
| home | floor_tile | 12 |
| home | floor_carpet | 12 |
| home | floor_wood | 12 |
| home | ceiling | 12 |
| home | door_frame_arch | 36 |
| home | counter | 12 |
| home | kitchen_unit | 12 |
| home | table | 24 |
| home | chair | 36 |
| home | sofa | 24 |
| home | coffee_table | 12 |
| home | bed | 24 |
| home | toilet | 12 |
| home | sink | 12 |
| home | shower | 12 |
| home | partition | 12 |
| home | wall_shelf | 12 |
| home | rug | 12 |
| home | pendant_lamp | 32 |
| home | framed_art | 12 |
| home | mirror | 12 |
| home | curtain | 12 |
| home | plant | 12 |
| home | tv_dark | 12 |
| home | tv_screen | 12 |

Kit parts total: 132 parts, 2436 unique tris.

Kit family part lists cover: walls (paint/wallpaper), floor slabs (tile/carpet/wood), ceilings, open archway door frames (2.4 m high, no door meshes), counters, reception desks, shelving, table+chair, sofa+coffee table, beds, kitchen units, bathroom fixtures (toilet/sink/shower), partition screens, wall shelves, rugs, pendant lamps (emissive), framed art, mirrors (int_mirror), curtains, plants (leaves_*), TVs (dark glass + emissive screen).

## Reference rooms (furnished demonstrations)

program.json Interiors rects are null, so the three rooms sit inside the first 3 tier-1 anchors of parcels_D.json (stated; all are office_tower civic parcels in district D, furnished as office lobby / restaurant / home using the kits).

| room | anchor | type | buildable_rect | objects | tris | floor z |
|---|---|---|---|---|---|---|
| OfficeLobby | B_4_3_0_1_0_0 | office_tower | [16.0, -140.0, 74.0, -82.0] | 14 | 240 | 0.15 |
| RestaurantDining | B_3_4_1_0_0_0 | office_tower | [-140.0, 16.0, -82.0, 74.0] | 16 | 324 | 0.15 |
| HomeLiving | B_3_4_1_1_1_1 | office_tower | [-74.0, 226.0, -16.0, 284.0] | 16 | 288 | 0.15 |

Furniture is built from kit parts (shared datablocks) at local z=CURB=0.15 (finished floor z=0.15), ceiling 3.2, matching entertainment.py's ground-floor convention. Objects at world z=0.0.

## Colliders

One box proxy per kit family under `Interiors/Colliders`, named `COL_int_kit_<family>_01`.
| collider | tris |
|---|---|
| 6 families | 72 tris |

## Lights

10 real point lights (pendants/patches) under `Interiors/Lights`, named `LT_int_<nn>` (limit 40). Emissive props (pendant_lamp meshes, tv_screen) use emissive materials elsewhere.

## Gap audit (report-only, no geometry)

| district | parcels | t1 | t2 | t3 | t0 | enterable | report t1 | status |
|---|---|---|---|---|---|---|---|---|
| R | 844 | 6 | 71 | 691 | 76 | 77 | - | unaudited_no_report |
| D | 109 | 11 | 91 | 6 | 1 | 102 | 11 | ok |
| E | 288 | 15 | 154 | 87 | 32 | 169 | 15 | ok |
| M | 1236 | 7 | 188 | 946 | 95 | 195 | - | no_tier_field |
| G | 13 | 0 | 0 | 0 | 13 | 0 | - | unaudited |
| I | 48 | 0 | 11 | 37 | 0 | 11 | - | unaudited |
| T | 7 | 0 | 3 | 4 | 0 | 3 | - | unaudited |

Headline: D 11/11; E 15/15; M (report lacks tier count; parcel t1=7); R (no district report; parcel t1=6). No district reports fewer t1 interiors than the parcel file; market's current report exposes no tier count (market previously reported 7 t1 = 7 parcels), residential is unaudited.

## Materials

Appended only from `/city/materials.blend` — no new materials created. Used: wall_paint, int_wall_paint_bone, floor_tile, floor_carpet, floor_wood, ceiling_paint, wood_painted, int_laminate_counter, metal_painted_dark, wood_old, int_upholstery, int_marble, metal_steel, glass_frosted, int_carpet, emissive_warm, emissive_cool, plaster_white, int_mirror, canvas_tarp, leaves_green, glass_dark, col_placeholder. `int_mirror` exists and is used for mirrors.

## Naming / collections / transforms

Collections: `Interiors` > `Meshes` (kit parts per family + `Ref_<room>`), `Colliders`, `Lights`. Naming: `INT_<kit>_<part>_<nn>`, `INT_REF_<room>_<part>_<nn>`, `COL_int_kit_<family>_01`, `LT_int_<nn>`. Every kit piece origin at bottom-centre. Linked duplicates / shared datablocks for anything repeated — no unique copies. Transforms kept as translation (shared datablocks require instancing; codebase convention).

## Keepouts

No M-district shells, no circuit zone [612,-1188,1188,-12], no LAKE_1, no 5 stadium rects touched: nothing is built outside the three D-district reference rooms (all inside their buildable_rects).

## Budgets

| item | tris |
|---|---|
| kit unique meshes | 2436 |
| colliders | 72 |
| reference rooms | 852 |

## Issues / needs from Assembler

- kit sources keep translation-only transforms (shared datablocks require instancing — codebase convention, see market report); transforms not baked on instances
- INT_HERO_INTERIORS / INT_SHELL_INTERIORS / INT_MALL_FITOUT are district-owned fit-out passes over already-placed buildings; the Assembler places kit instances into those shells using these kits.
- Residential district has no tier report; its 6 t1 parcels are unaudited.

