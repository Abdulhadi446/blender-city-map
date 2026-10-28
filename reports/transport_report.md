# Transport module report

- blend: `/home/abdulhadi/Work/city/out/transport.blend`
- previews: `/home/abdulhadi/Work/city/out/transport_preview.png`, `/home/abdulhadi/Work/city/out/transport_airport_preview.png`
- objects: 184
- triangles (unique/expanded): 20688 / 23232
- facilities: 31 (unchanged) (unchanged)
- lights: 12

## Per facility

| id | objects | triangles |
|---|---|---|
| IND_DEPOT | 1 | 288 |
| CARPARK_MULTISTOREY | 1 | 288 |
| TRN_BUS_DEPOT | 1 | 504 |
| TRN_MAIL_SORTING | 1 | 648 |
| TRN_PARK_AND_RIDE | 1 | 1644 |
| TRN_COACH_TERMINAL | 19 | 660 |
| TRN_PETROL_EV | 1 | 384 |
| TRN_TRUCK_STOP | 1 | 504 |
| TRN_RUNWAY | 1 | 768 |
| TRN_TAXIWAY | 1 | 12 |
| TRN_APRON | 2 | 300 |
| TRN_AIR_TERMINAL | 63 | 2148 |
| TRN_AIR_TOWER | 1 | 60 |
| TRN_AIR_HANGARS | 1 | 396 |
| TRN_AIR_FIRE | 1 | 108 |
| TRN_AIR_CARGO | 1 | 228 |
| TRN_AIR_PARKING | 1 | 768 |
| TRN_RAIL_LINE | 1 | 7548 |
| TRN_RAIL_PLATFORMS | 1 | 1032 |
| TRN_RAIL_STATION | 23 | 1104 |
| TRK_PARKING_E1 | 1 | 684 |
| TRK_PARKING_E2 | 1 | 684 |
| TRK_GATE_E | 1 | 204 |
| TRK_TRANSPORT_HUB | 1 | 396 |
| TRK_PARKING_E3 | 1 | 684 |
| TRN_STREET_DEPOT | 1 | 192 |
| METRO_ENT_1 | 1 | 96 |
| METRO_ENT_2 | 1 | 96 |
| METRO_ENT_3 | 1 | 96 |
| METRO_ENT_4 | 1 | 96 |
| METRO_ENT_5 | 1 | 96 |

## Materials

asphalt, col_placeholder, concrete, emissive_warm, glass_dark, glass_office, glass_shop, gravel, marking_white, marking_yellow, metal_painted_dark, metal_steel, roof_bitumen, roof_metal, sand, sign_metal, wood_old, wood_painted

## Issues / needs

- No road geometry built by this module; entrances kept clear for Roads 8 m spurs.
- TRK_* facilities included per program owning_module=Transport; verify ownership with Track agent.
- Roads: 8 m access spurs to each facility entrance; many band/outer sites have no adjacent road.
- Assembler: ground plane under outer frame and band lands.
