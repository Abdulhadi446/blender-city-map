# Commercial rebuild report

| Facility | District | Mode | Floors | Height m | Tier | Class | Tris | Props | Lights |
|---|---|---|---|---|---|---|---|---|---|
| BANQUET_HALL | E | superlot | 3 | 11.1 | 1 | hero | 6780 | 6 | 6 |
| BREWERY | I | superlot | 5 | 17.4 | 2 | hero | 5928 | 2 | 6 |
| COLD_STORAGE | I | superlot | 4 | 14.2 | 2 | regular | 4524 | 2 | 0 |
| CONFERENCE_CENTRE | D | superlot | 4 | 14.2 | 1 | hero | 8184 | 6 | 6 |
| DEPARTMENT_STORE | D | superlot | 5 | 17.4 | 1 | hero | 7236 | 9 | 6 |
| FIN_BANK | D | existing_parcels | 8 | 27.1 | 1 | regular | 11880 | 6 | 0 |
| HOSTEL | R | superlot | 3 | 11.1 | 2 | regular | 6780 | 2 | 0 |
| HOT_AIRPORT_HOTEL | OUTER | district_cell | 8 | 27.1 | 1 | hero | 13968 | 6 | 6 |
| HOT_HOTEL | E | existing_parcels | 8 | 27.1 | 1 | hero | 11880 | 6 | 6 |
| HOT_MOTEL | OUTER | district_cell | 2 | 7.8 | 2 | hero | 6024 | 2 | 6 |
| ICON_TOWER | OUTER | district_cell | 56 | 180.7 | 3 | hero | 79740 | 0 | 6 |
| IND_FACTORY | I | existing_parcels | 3 | 11.1 | 3 | regular | 2868 | 0 | 0 |
| IND_WAREHOUSE | I | existing_parcels | 2 | 7.8 | 3 | regular | 1560 | 0 | 0 |
| MED_BROADCAST | OUTER | district_cell | 4 | 14.2 | 2 | hero | 8256 | 2 | 6 |
| MED_FILM_STUDIO | OUTER | district_cell | 4 | 14.2 | 3 | hero | 4464 | 0 | 6 |
| OFFICE_COWORKING | D | superlot | 8 | 27.1 | 1 | regular | 13800 | 6 | 0 |
| OFF_MIDRISE | D | existing_parcels | 20 | 65.5 | 2 | regular | 24672 | 2 | 0 |
| OFF_TOWER | D | existing_parcels | 30 | 97.5 | 1 | hero | 36792 | 6 | 6 |
| REC_FARMERS_MARKET | OUTER | district_cell | 2 | 7.8 | 1 | regular | 4080 | 9 | 0 |
| RET_CAFE | E | existing_parcels | 2 | 7.8 | 3 | prop | 2052 | 0 | 0 |
| RET_CORNER_SHOP | R | existing_parcels | 2 | 7.8 | 3 | prop | 1572 | 0 | 0 |
| RET_MALL | D | existing_parcels | 5 | 17.4 | 1 | hero | 6564 | 9 | 6 |
| RET_MOTOR_TRADE | OUTER | district_cell | 3 | 11.1 | 2 | regular | 5196 | 2 | 0 |
| RET_RESTAURANT | E | existing_parcels | 2 | 7.8 | 2 | regular | 2112 | 2 | 0 |
| RET_SHOPS | E | existing_parcels | 3 | 11.1 | 2 | regular | 3372 | 2 | 0 |
| RET_SUPERMARKET | E | existing_parcels | 2 | 7.8 | 1 | regular | 2112 | 9 | 0 |
| RET_WHOLESALER | OUTER | district_cell | 4 | 14.2 | 2 | hero | 6144 | 2 | 6 |
| TRK_FOOD_COURT | OUTER | district_cell | 2 | 7.8 | 1 | regular | 3696 | 9 | 0 |
| TRK_MERCH_HALL | OUTER | district_cell | 2 | 7.8 | 1 | regular | 3624 | 9 | 0 |
| TRK_SPECTATOR_VILLAGE | OUTER | district_cell | 3 | 11.1 | 2 | hero | 4548 | 2 | 6 |
| WORKSHOP_FABRICATION | I | superlot | 5 | 17.4 | 1 | regular | 5928 | 6 | 0 |
| WRK_CONSTRUCTION_YARD | OUTER | district_cell | 2 | 7.8 | 3 | regular | 1656 | 0 | 0 |
| WRK_DATA_CENTRE | OUTER | district_cell | 3 | 11.1 | 3 | hero | 5568 | 0 | 6 |
| WRK_LOGISTICS_HUB | OUTER | district_cell | 4 | 14.2 | 2 | hero | 4524 | 2 | 6 |
| WRK_TECH_PARK | OUTER | district_cell | 5 | 17.4 | 2 | hero | 9708 | 2 | 6 |

## Skipped (5)
- RES_SHOPHOUSE: district M (market already built)
- RET_BAZAAR: district M (market already built)
- RET_TEAHOUSE: district M (market already built)
- RET_WORKSHOP_STALL: district M (market already built)
- TRK_FAN_ZONE: inside track circuit zone

## Budgets
- unique tris: 328212; prop instances: 128 (+4596 tris); module total: 332808 / 900,000
- hero cap 150,000 tris, regular 40,000, props 5,000: OK

## Verification
- grounding band [-0.06, 0.30] m for every unique mesh: pass
- walls present on all 4 faces (E/W/N/S probe): pass
- no footprint overlaps: pass
- road clearance >= 2.5 m: pass

## Materials (20, all from /city/materials.blend)
`concrete`, `concrete_poured`, `emissive_cool`, `emissive_warm`, `facade_brick_red`, `facade_concrete_slab`, `facade_plaster_charcoal`, `floor_tile`, `glass_dark`, `glass_office`, `glass_shop`, `glass_tinted_office`, `int_tile_floor`, `int_wall_paint_bone`, `metal_painted_charcoal`, `neon_mustard`, `neon_oxblood`, `neon_teal`, `roof_bitumen_flat`, `sidewalk_concrete`

## Collections
- Commercial > Meshes, Colliders, Lights
- colliders: 35 (COL_com_<id>, hidden from render) ; lights: 102 (LT_com_<nn>, heroes only, <=6 per hero)

## Issues / remaining problems
- none

(previews written by modules/commercial_previews.py; see commercial_report.json 'previews' for the verification numbers)

## Previews (EEVEE 1920x1080)
- aerial: `/home/abdulhadi/Work/city/out/commercial_preview.png` std 0.0806 (need >0.02), magenta pixels 0
- street: `/home/abdulhadi/Work/city/out/commercial_street_preview.png` std 0.1390 (need >0.02), magenta pixels 0
- verification: PASS (no magenta, both frames vary)
