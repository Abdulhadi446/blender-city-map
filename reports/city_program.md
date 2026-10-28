# City program - AAA City (land use & building inventory)

Research deliverable of the CITY-PROGRAM RESEARCH agent. Machine-readable twin: `reports/program.json` (schema `city-program/1`).

**Inputs (read-only):** `city_map_plan.md`, `generate_layout.py`, `layout.json`, `style_bible.md`, `guide.md`, `reports/*.md`, `out/*.blend` (ground truth), `modules/*.py`.

**Result:** 179 facilities, 8,865,500 tris of budget, 18 build waves (max 2 agents each), validator **PASS** (0 errors / 0 warnings across 13 checks).

## 1. Rules the program obeys

| Rule | Implementation |
|---|---|
| rect axis-aligned | every `placement.rect` = `[x0,y0,x1,y1]`, `x1>x0`, `y1>y0` |
| inside `[-1500,1500]` | checked for all 179 rects |
| no road corridor | tested against all 454 corridors: highway hw 17, arterial 12, street 6, alley 2.5, ramp 9, **plus** the four ring corner arcs (r=120, hw=17) |
| modes | only `superlot` / `district_cell` / `existing_parcels` |
| owning_module | only `Nature`, `Props`, `Lighting`, `Traffic`, `Residential`, `SportsCivic`, `Commercial`, `Transport`, `Track`, `Interiors` |
| phase | only `D`, `E`, `F` |
| waves | 18 waves, every facility in exactly one, max 2 agents per wave |
| tri budgets | hero <=150k, regular <=40k, props <=5k, trees <=8k - checked per item |
| cell coords | `cell_rect = [-1200+cx*300, -1200+cy*300, -1200+(cx+1)*300, -1200+(cy+1)*300]`, district = `grid[7-cy][cx]`, band/frame land = `OUTER` |

## 2. Gap analysis - how each facility is placed

`placement.mode` has exactly three values; the `gap` object in `program.json` carries the detail.

### 2.1 `existing_parcels` - 42 facilities already given a parcel type in `layout.json`

Gap = *the type exists, no new land is consumed*. Counts are taken from the generated layout.

| Facility | parcel type(s) | n | R | D | E | G | I | M | T | tri | module |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `RET_SHOPS` | shop x508 | 508 | 0 | 0 | 55 | 0 | 0 | 453 | 0 | 6000 | Commercial |
| `RES_HOUSE_TERRACED` | house x484 | 484 | 484 | 0 | 0 | 0 | 0 | 0 | 0 | 3000 | Residential |
| `RES_SHOPHOUSE` | house_above_shop x352 | 352 | 0 | 0 | 0 | 0 | 0 | 352 | 0 | 6000 | Commercial |
| `RET_RESTAURANT` | restaurant x197 | 197 | 0 | 0 | 61 | 0 | 0 | 136 | 0 | 8000 | Commercial |
| `RES_APARTMENT_LOW` | apartment_low x170 | 170 | 147 | 0 | 23 | 0 | 0 | 0 | 0 | 40000 | Residential |
| `RES_HOUSE_VILLA` | house_large x128 | 128 | 128 | 0 | 0 | 0 | 0 | 0 | 0 | 3500 | Residential |
| `INT_SHELL_INTERIORS` | restaurant x19, hotel x16, cafe x12, club x9, +14 more | 120 | 15 | 15 | 79 | 0 | 11 | 0 | 0 | 40000 | Interiors |
| `RET_WORKSHOP_STALL` | workshop x110 | 110 | 0 | 0 | 0 | 0 | 0 | 110 | 0 | 4000 | Commercial |
| `MKT_COURTYARD` | courtyard x95 | 95 | 0 | 0 | 0 | 0 | 0 | 95 | 0 | 8000 | Nature |
| `RET_TEAHOUSE` | teahouse x89 | 89 | 0 | 0 | 0 | 0 | 0 | 89 | 0 | 5000 | Commercial |
| `RES_COURTYARD_HOMES` | courtyard x64 | 64 | 64 | 0 | 0 | 0 | 0 | 0 | 0 | 8000 | Nature |
| `OFF_TOWER` | office_tower x55 | 55 | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 150000 | Commercial |
| `INT_HERO_INTERIORS` | restaurant x8, shop x6, office_tower x6, house x5, +7 more | 39 | 6 | 11 | 15 | 0 | 0 | 7 | 0 | 40000 | Interiors |
| `HOT_HOTEL` | hotel x37 | 37 | 0 | 17 | 20 | 0 | 0 | 0 | 0 | 150000 | Commercial |
| `RET_CAFE` | cafe x35 | 35 | 0 | 0 | 35 | 0 | 0 | 0 | 0 | 5000 | Commercial |
| `RES_COURTYARD_EM` | courtyard x32 | 32 | 0 | 0 | 32 | 0 | 0 | 0 | 0 | 8000 | Nature |
| `REC_GYM` | gym x26 | 26 | 0 | 0 | 26 | 0 | 0 | 0 | 0 | 20000 | SportsCivic |
| `IND_WAREHOUSE` | warehouse x23 | 23 | 0 | 0 | 0 | 0 | 23 | 0 | 0 | 30000 | Commercial |
| `OFF_MIDRISE` | office_tower x17 | 17 | 0 | 17 | 0 | 0 | 0 | 0 | 0 | 40000 | Commercial |
| `IND_FACTORY` | factory x15 | 15 | 0 | 0 | 0 | 0 | 15 | 0 | 0 | 40000 | Commercial |
| `CUL_CLUB` | club x15 | 15 | 0 | 0 | 15 | 0 | 0 | 0 | 0 | 20000 | SportsCivic |
| `PARK_MAIN` | park x13 | 13 | 0 | 0 | 0 | 13 | 0 | 0 | 0 | 8000 | Nature |
| `RES_APARTMENT_TOWER` | apartment_tower x12 | 12 | 0 | 12 | 0 | 0 | 0 | 0 | 0 | 40000 | Residential |
| `PARK_POCKET` | pocket_park x12 | 12 | 12 | 0 | 0 | 0 | 0 | 0 | 0 | 8000 | Nature |
| `FIN_BANK` | bank x11 | 11 | 0 | 11 | 0 | 0 | 0 | 0 | 0 | 15000 | Commercial |
| `CUL_CINEMA` | cinema x11 | 11 | 0 | 0 | 11 | 0 | 0 | 0 | 0 | 40000 | SportsCivic |
| `RET_SUPERMARKET` | supermarket x10 | 10 | 0 | 0 | 10 | 0 | 0 | 0 | 0 | 40000 | Commercial |
| `RET_CORNER_SHOP` | corner_shop x9 | 9 | 9 | 0 | 0 | 0 | 0 | 0 | 0 | 4000 | Commercial |
| `RET_MALL` | mall x8 | 8 | 0 | 8 | 0 | 0 | 0 | 0 | 0 | 150000 | Commercial |
| `INT_MALL_FITOUT` | mall x8 | 8 | 0 | 8 | 0 | 0 | 0 | 0 | 0 | 40000 | Interiors |
| `IND_YARD` | yard x7 | 7 | 0 | 0 | 0 | 0 | 7 | 0 | 0 | 5000 | Props |
| `CIVIC_TOWN_OFFICES` | civic x4 | 4 | 0 | 4 | 0 | 0 | 0 | 0 | 0 | 40000 | SportsCivic |
| `IND_DEPOT` | depot x3 | 3 | 0 | 0 | 0 | 0 | 3 | 0 | 0 | 20000 | Transport |
| `TRACK_GRANDSTAND` | grandstand x2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 150000 | Track |
| `TRACK_PARKING` | parking_lot x2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 5000 | Track |
| `RET_BAZAAR` | covered_bazaar_hall x1 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 150000 | Commercial |
| `CITY_HALL` | civic x1 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 150000 | SportsCivic |
| `PLAZA_CENTRAL` | central_plaza x1 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 8000 | Nature |
| `TRACK_PIT` | pit_building x1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 40000 | Track |
| `TRACK_PADDOCK` | paddock x1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 20000 | Track |
| `TRACK_TOWER` | control_tower x1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 20000 | Track |
| `TRACK_CIRCUIT` |  | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 40000 | Track |

### 2.2 `superlot` - 21 contiguous-parcel merges (hard conflict: those buildings are NOT built)

- **`COURTHOUSE`** - Law courts + public square | D | cell [3, 5] [-300, 300, 0, 600] | **4 parcels**: `B_3_5_0_0_0_0`, `B_3_5_0_0_1_0`, `B_3_5_0_0_0_1`, `B_3_5_0_0_1_1` | 150000 tris | `SportsCivic` | phase D
- **`MUSEUM_CITY`** - City museum | D | cell [4, 4] [0, 0, 300, 300] | **4 parcels**: `B_4_4_1_0_0_0`, `B_4_4_1_0_1_0`, `B_4_4_1_0_0_1`, `B_4_4_1_0_1_1` | 150000 tris | `SportsCivic` | phase D
- **`PLANETARIUM`** - Planetarium + science centre | D | cell [4, 4] [0, 0, 300, 300] | **4 parcels**: `B_4_4_1_1_0_0`, `B_4_4_1_1_1_0`, `B_4_4_1_1_0_1`, `B_4_4_1_1_1_1` | 120000 tris | `SportsCivic` | phase D
- **`DEPARTMENT_STORE`** - Department store | D | cell [3, 4] [-300, 0, 0, 300] | **4 parcels**: `B_3_4_1_1_0_0`, `B_3_4_1_1_1_0`, `B_3_4_1_1_0_1`, `B_3_4_1_1_1_1` | 120000 tris | `Commercial` | phase D
- **`CARPARK_MULTISTOREY`** - Multi-storey car park | D | cell [5, 4] [300, 0, 600, 300] | **4 parcels**: `B_5_4_1_1_0_0`, `B_5_4_1_1_1_0`, `B_5_4_1_1_0_1`, `B_5_4_1_1_1_1` | 40000 tris | `Transport` | phase D
- **`CONFERENCE_CENTRE`** - Conference / exhibition centre | D | cell [5, 5] [300, 300, 600, 600] | **4 parcels**: `B_5_5_0_1_0_0`, `B_5_5_0_1_1_0`, `B_5_5_0_1_0_1`, `B_5_5_0_1_1_1` | 120000 tris | `Commercial` | phase D
- **`OFFICE_COWORKING`** - Co-working / serviced office | D | cell [4, 5] [0, 300, 300, 600] | **4 parcels**: `B_4_5_1_1_0_0`, `B_4_5_1_1_1_0`, `B_4_5_1_1_0_1`, `B_4_5_1_1_1_1` | 40000 tris | `Commercial` | phase D
- **`THEATRE`** - Theatre / playhouse | E | cell [3, 3] [-300, -300, 0, 0] | **9 parcels**: `B_3_3_0_0_0_0`, `B_3_3_0_0_1_0`, `B_3_3_0_0_2_0`, `B_3_3_0_0_0_1`, `B_3_3_0_0_2_1`, `B_3_3_0_0_0_2`, `B_3_3_0_0_1_2`, `B_3_3_0_0_2_2`, `CY_3_3_0_0` | 120000 tris | `SportsCivic` | phase D
- **`CONCERT_HALL`** - Concert hall (symphonic) | E | cell [5, 3] [300, -300, 600, 0] | **9 parcels**: `B_5_3_0_0_0_0`, `B_5_3_0_0_1_0`, `B_5_3_0_0_2_0`, `B_5_3_0_0_0_1`, `B_5_3_0_0_2_1`, `B_5_3_0_0_0_2`, `B_5_3_0_0_1_2`, `B_5_3_0_0_2_2`, `CY_5_3_0_0` | 150000 tris | `SportsCivic` | phase D
- **`GALLERY_ART`** - Art gallery | E | cell [2, 4] [-600, 0, -300, 300] | **9 parcels**: `B_2_4_0_0_0_0`, `B_2_4_0_0_1_0`, `B_2_4_0_0_2_0`, `B_2_4_0_0_0_1`, `B_2_4_0_0_2_1`, `B_2_4_0_0_0_2`, `B_2_4_0_0_1_2`, `B_2_4_0_0_2_2`, `CY_2_4_0_0` | 120000 tris | `SportsCivic` | phase D
- **`ARCADE_GAMES`** - Amusement arcade | E | cell [6, 4] [600, 0, 900, 300] | **9 parcels**: `B_6_4_0_0_0_0`, `B_6_4_0_0_1_0`, `B_6_4_0_0_2_0`, `B_6_4_0_0_0_1`, `B_6_4_0_0_2_1`, `B_6_4_0_0_0_2`, `B_6_4_0_0_1_2`, `B_6_4_0_0_2_2`, `CY_6_4_0_0` | 40000 tris | `SportsCivic` | phase D
- **`CASINO`** - Casino + entertainment | E | cell [4, 6] [0, 600, 300, 900] | **9 parcels**: `B_4_6_0_0_0_0`, `B_4_6_0_0_1_0`, `B_4_6_0_0_2_0`, `B_4_6_0_0_0_1`, `B_4_6_0_0_2_1`, `B_4_6_0_0_0_2`, `B_4_6_0_0_1_2`, `B_4_6_0_0_2_2`, `CY_4_6_0_0` | 120000 tris | `SportsCivic` | phase D
- **`BANQUET_HALL`** - Banquet / wedding hall | E | cell [6, 5] [600, 300, 900, 600] | **9 parcels**: `B_6_5_0_0_0_0`, `B_6_5_0_0_1_0`, `B_6_5_0_0_2_0`, `B_6_5_0_0_0_1`, `B_6_5_0_0_2_1`, `B_6_5_0_0_0_2`, `B_6_5_0_0_1_2`, `B_6_5_0_0_2_2`, `CY_6_5_0_0` | 80000 tris | `Commercial` | phase D
- **`HOSTEL`** - Hostel / budget lodging | R | cell [1, 5] [-900, 300, -600, 600] | **13 parcels**: `B_1_5_0_0_0_0`, `B_1_5_0_0_1_0`, `B_1_5_0_0_2_0`, `B_1_5_0_0_3_0`, `B_1_5_0_0_0_1`, `B_1_5_0_0_3_1`, `B_1_5_0_0_0_2`, `B_1_5_0_0_3_2`, `B_1_5_0_0_0_3`, `B_1_5_0_0_1_3`, `B_1_5_0_0_2_3`, `B_1_5_0_0_3_3`, `CY_1_5_0_0` | 40000 tris | `Commercial` | phase D
- **`EMBASSY`** - Embassy / consulate compound | R | cell [1, 7] [-900, 900, -600, 1200] | **13 parcels**: `B_1_7_0_0_0_0`, `B_1_7_0_0_1_0`, `B_1_7_0_0_2_0`, `B_1_7_0_0_3_0`, `B_1_7_0_0_0_1`, `B_1_7_0_0_3_1`, `B_1_7_0_0_0_2`, `B_1_7_0_0_3_2`, `B_1_7_0_0_0_3`, `B_1_7_0_0_1_3`, `B_1_7_0_0_2_3`, `B_1_7_0_0_3_3`, `CY_1_7_0_0` | 80000 tris | `SportsCivic` | phase D
- **`UNIVERSITY_MAIN`** - University: main building + quad | R | cell [3, 7] [-300, 900, 0, 1200] | **13 parcels**: `B_3_7_0_0_0_0`, `B_3_7_0_0_1_0`, `B_3_7_0_0_2_0`, `B_3_7_0_0_3_0`, `B_3_7_0_0_0_1`, `B_3_7_0_0_3_1`, `B_3_7_0_0_0_2`, `B_3_7_0_0_3_2`, `B_3_7_0_0_0_3`, `B_3_7_0_0_1_3`, `B_3_7_0_0_2_3`, `B_3_7_0_0_3_3`, `CY_3_7_0_0` | 150000 tris | `SportsCivic` | phase D
- **`UNIVERSITY_FACULTY`** - University: faculty blocks | R | cell [3, 7] [-300, 900, 0, 1200] | **13 parcels**: `B_3_7_1_0_0_0`, `B_3_7_1_0_1_0`, `B_3_7_1_0_2_0`, `B_3_7_1_0_3_0`, `B_3_7_1_0_0_1`, `B_3_7_1_0_3_1`, `B_3_7_1_0_0_2`, `B_3_7_1_0_3_2`, `B_3_7_1_0_0_3`, `B_3_7_1_0_1_3`, `B_3_7_1_0_2_3`, `B_3_7_1_0_3_3`, `CY_3_7_1_0` | 80000 tris | `SportsCivic` | phase D
- **`DORMITORIES`** - Student dormitories | R | cell [3, 7] [-300, 900, 0, 1200] | **13 parcels**: `B_3_7_0_1_0_0`, `B_3_7_0_1_1_0`, `B_3_7_0_1_2_0`, `B_3_7_0_1_3_0`, `B_3_7_0_1_0_1`, `B_3_7_0_1_3_1`, `B_3_7_0_1_0_2`, `B_3_7_0_1_3_2`, `B_3_7_0_1_0_3`, `B_3_7_0_1_1_3`, `B_3_7_0_1_2_3`, `B_3_7_0_1_3_3`, `CY_3_7_0_1` | 80000 tris | `Residential` | phase D
- **`BREWERY`** - Brewery + tap hall | I | cell [5, 1] [300, -900, 600, -600] | **4 parcels**: `B_5_1_0_1_0_0`, `B_5_1_0_1_1_0`, `B_5_1_0_1_0_1`, `B_5_1_0_1_1_1` | 80000 tris | `Commercial` | phase D
- **`COLD_STORAGE`** - Cold storage plant | I | cell [5, 0] [300, -1200, 600, -900] | **4 parcels**: `B_5_0_1_0_0_0`, `B_5_0_1_0_1_0`, `B_5_0_1_0_0_1`, `B_5_0_1_0_1_1` | 40000 tris | `Commercial` | phase D
- **`WORKSHOP_FABRICATION`** - Metal fabrication works | I | cell [5, 2] [300, -600, 600, -300] | **4 parcels**: `B_5_2_0_1_0_0`, `B_5_2_0_1_1_0`, `B_5_2_0_1_0_1`, `B_5_2_0_1_1_1` | 40000 tris | `Commercial` | phase D

### 2.3 `district_cell` - 116 new placements on open / green / band land

| Facility | district | cell | cell rect | rect (x0,y0,x1,y1) | m | tri | module | phase |
|---|---|---|---|---|---|---:|---|---|
| `STADIUM_CRICKET` | G | [1, 0] | [-900, -1200, -600, -900] | [-864, -1164, -636, -936] | 228x228 | 150000 | SportsCivic | D |
| `STADIUM_FOOTBALL` | G | [4, 0] | [0, -1200, 300, -900] | [36, -1164, 264, -936] | 228x228 | 150000 | SportsCivic | D |
| `STADIUM_ATHLETICS` | G | [0, 1] | [-1200, -900, -900, -600] | [-1164, -864, -936, -636] | 228x228 | 150000 | SportsCivic | D |
| `COMPLEX_SWIMMING` | G | [4, 1] | [0, -900, 300, -600] | [36, -864, 264, -636] | 228x228 | 120000 | SportsCivic | D |
| `ARENA_INDOOR` | G | [0, 2] | [-1200, -600, -900, -300] | [-1164, -564, -936, -336] | 228x228 | 150000 | SportsCivic | D |
| `STATION_FIRE` | R | [0, 3] | [-1200, -300, -900, 0] | [-1184, -140, -1108, -96] | 76x44 | 40000 | SportsCivic | D |
| `HOSPITAL_MAIN` | R | [0, 4] | [-1200, 0, -900, 300] | [-1040, 16, -936, 96] | 104x80 | 120000 | SportsCivic | D |
| `STATION_POLICE` | R | [0, 7] | [-1200, 900, -900, 1200] | [-1040, 916, -968, 960] | 72x44 | 40000 | SportsCivic | D |
| `SCHOOL_SECONDARY` | R | [2, 2] | [-600, -600, -300, -300] | [-584, -584, -488, -516] | 96x68 | 40000 | SportsCivic | D |
| `SCHOOL_KINDER` | R | [2, 2] | [-600, -600, -300, -300] | [-368, -440, -316, -404] | 52x36 | 40000 | SportsCivic | D |
| `CLINIC_URGENT` | R | [2, 3] | [-600, -300, -300, 0] | [-440, -284, -364, -236] | 76x48 | 40000 | SportsCivic | D |
| `SCHOOL_PRIMARY` | R | [2, 6] | [-600, 600, -300, 900] | [-584, 760, -488, 828] | 96x68 | 40000 | SportsCivic | D |
| `LIBRARY_PUBLIC` | R | [2, 7] | [-600, 900, -300, 1200] | [-540, 916, -460, 976] | 80x60 | 40000 | SportsCivic | D |
| `MOSQUE` | R | [2, 7] | [-600, 900, -300, 1200] | [-440, 980, -364, 1040] | 76x60 | 40000 | SportsCivic | D |
| `CHURCH` | R | [3, 6] | [-300, 600, 0, 900] | [-284, 684, -212, 740] | 72x56 | 40000 | SportsCivic | D |
| `COLLEGE_VOCATIONAL` | R | [3, 6] | [-300, 600, 0, 900] | [-140, 820, -48, 884] | 92x64 | 40000 | SportsCivic | D |
| `HOUSING_SENIOR` | R | [7, 5] | [900, 300, 1200, 600] | [944, 368, 1040, 440] | 96x72 | 40000 | Residential | D |
| `TEMPLE` | G | [1, 1] | [-900, -900, -600, -600] | [-672, -884, -616, -840] | 56x44 | 20000 | SportsCivic | F |
| `GURUDWARA` | G | [3, 1] | [-300, -900, 0, -600] | [-68, -660, -16, -616] | 52x44 | 20000 | SportsCivic | F |
| `PARK_DOG` | G | [3, 0] | [-300, -1200, 0, -900] | [-92, -1184, -16, -1132] | 76x52 | 5000 | Nature | F |
| `GARDEN_ZEN` | G | [1, 2] | [-900, -600, -600, -300] | [-884, -372, -812, -316] | 72x56 | 5000 | Nature | F |
| `BANDSTAND` | G | [2, 1] | [-600, -900, -300, -600] | [-360, -884, -316, -840] | 44x44 | 5000 | Nature | F |
| `RESTROOM_PARK` | G | [0, 0] | [-1200, -1200, -900, -900] | [-940, -930, -916, -916] | 24x14 | 5000 | Props | F |
| `BOATHOUSE_PIER` | G | [2, 0] | [-600, -1200, -300, -900] | [-376, -942, -316, -916] | 60x26 | 5000 | Nature | F |
| `TRN_BUS_DEPOT` | OUTER | [0, 8] | [-1200, 1200, -900, 1500] | [-1214, 1214, -1046.3, 1360] | 167.7x146 | 40000 | Transport | D |
| `TRN_MAIL_SORTING` | OUTER | [0, 8] | [-1200, 1200, -900, 1500] | [-1028.3, 1214, -854.6, 1360] | 173.7x146 | 40000 | Transport | D |
| `WRK_TECH_PARK` | OUTER | [2, 8] | [-600, 1200, -300, 1500] | [-555, 1214, -430.8, 1360] | 124.2x146 | 80000 | Commercial | D |
| `TRN_PARK_AND_RIDE` | OUTER | [2, 8] | [-600, 1200, -300, 1500] | [-414.6, 1214, -290.4, 1360] | 124.2x146 | 5000 | Transport | F |
| `TRN_COACH_TERMINAL` | OUTER | [4, 8] | [0, 1200, 300, 1500] | [213.3, 1214, 381.6, 1360] | 168.3x146 | 80000 | Transport | D |
| `RET_MOTOR_TRADE` | OUTER | [5, 8] | [300, 1200, 600, 1500] | [396.9, 1214, 555, 1360] | 158.1x146 | 40000 | Commercial | D |
| `MED_FILM_STUDIO` | OUTER | [6, 8] | [600, 1200, 900, 1500] | [690, 1214, 826.2, 1360] | 136.2x146 | 80000 | Commercial | E |
| `MED_BROADCAST` | OUTER | [7, 8] | [900, 1200, 1200, 1500] | [842, 1214, 962.5, 1360] | 120.5x146 | 80000 | Commercial | E |
| `UTL_CEMETERY` | OUTER | [0, -1] | [-1200, -1500, -900, -1200] | [-1214, -1360, -974.4, -1214] | 239.6x146 | 8000 | Nature | F |
| `UTL_CREMATORIUM` | OUTER | [1, -1] | [-900, -1500, -600, -1200] | [-956.4, -1360, -806.7, -1214] | 149.7x146 | 40000 | SportsCivic | E |
| `UTL_WATER_TREATMENT` | OUTER | [2, -1] | [-600, -1500, -300, -1200] | [-555, -1360, -382.2, -1214] | 172.8x146 | 40000 | Props | E |
| `UTL_SEWAGE` | OUTER | [2, -1] | [-600, -1500, -300, -1200] | [-366, -1360, -241.8, -1279.7] | 124.2x80.3 | 20000 | Props | E |
| `UTL_WATER_TOWER` | OUTER | [2, -1] | [-600, -1500, -300, -1200] | [-366, -1272.4, -258, -1214] | 108x58.4 | 5000 | Props | E |
| `UTL_WASTE` | OUTER | [4, -1] | [0, -1500, 300, -1200] | [45, -1360, 218.4, -1214] | 173.4x146 | 40000 | Props | E |
| `RET_WHOLESALER` | OUTER | [5, -1] | [300, -1500, 600, -1200] | [233.7, -1360, 412.2, -1214] | 178.5x146 | 80000 | Commercial | E |
| `TRN_PETROL_EV` | OUTER | [6, -1] | [600, -1500, 900, -1200] | [645, -1360, 758.8, -1214] | 113.8x146 | 40000 | Transport | F |
| `HOT_MOTEL` | OUTER | [6, -1] | [600, -1500, 900, -1200] | [775.9, -1360, 940.9, -1214] | 165x146 | 80000 | Commercial | E |
| `TRN_TRUCK_STOP` | OUTER | [7, -1] | [900, -1500, 1200, -1200] | [958, -1360, 1111.6, -1214] | 153.6x146 | 40000 | Transport | E |
| `REC_ZOO` | OUTER | [-1, 0] | [-1500, -1200, -1200, -900] | [-1360, -1214, -1214, -854.6] | 146x359.4 | 150000 | Nature | E |
| `REC_BOTANICAL` | OUTER | [-1, 2] | [-1500, -600, -1200, -300] | [-1360, -555, -1214, -220.2] | 146x334.8 | 120000 | Nature | E |
| `REC_AMUSEMENT` | OUTER | [-1, 4] | [-1500, 0, -1200, 300] | [-1360, 45, -1214, 340.8] | 146x295.8 | 150000 | Nature | E |
| `REC_GOLF_RANGE` | OUTER | [-1, 6] | [-1500, 600, -1200, 900] | [-1360, 645, -1214, 997.8] | 146x352.8 | 80000 | Nature | E |
| `UTL_SUBSTATION` | OUTER | [8, 0] | [1200, -1200, 1500, -900] | [1214, -1214, 1360, -1070.2] | 146x143.8 | 5000 | Props | E |
| `UTL_GAS_DEPOT` | OUTER | [8, 0] | [1200, -1200, 1500, -900] | [1214, -1052.3, 1360, -914.5] | 146x137.8 | 20000 | Props | E |
| `WRK_DATA_CENTRE` | OUTER | [8, 2] | [1200, -600, 1500, -300] | [1214, -555, 1360, -328.2] | 146x226.8 | 80000 | Commercial | E |
| `REC_WATER_PARK` | OUTER | [8, 4] | [1200, 0, 1500, 300] | [1214, 45, 1360, 289.8] | 146x244.8 | 120000 | Nature | E |
| `SPT_VELODROME` | OUTER | [8, 6] | [1200, 600, 1500, 900] | [1214, 645, 1360, 832.8] | 146x187.8 | 120000 | SportsCivic | E |
| `SPT_TENNIS_CENTRE` | OUTER | [8, 7] | [1200, 900, 1500, 1200] | [1214, 849.8, 1360, 1020.5] | 146x170.7 | 40000 | SportsCivic | E |
| `UTL_TELECOM` | OUTER | [8, 8] | [1200, 1200, 1500, 1500] | [1268, 1214, 1360, 1276] | 92x62 | 5000 | Props | F |
| `UTL_TRANSFORMER` | OUTER | [-1, 8] | [-1500, 1200, -1200, 1500] | [-1360, 1214, -1268, 1276] | 92x62 | 5000 | Props | F |
| `TRN_RUNWAY` | OUTER | [1, -1] | [-900, -1500, -600, -1200] | [-1480, -1494, -284, -1456] | 1196x38 | 5000 | Transport | D |
| `TRN_TAXIWAY` | OUTER | [3, -1] | [-300, -1500, 0, -1200] | [-284, -1494, -256, -1456] | 28x38 | 5000 | Transport | F |
| `TRN_APRON` | OUTER | [5, -1] | [300, -1500, 600, -1200] | [-256, -1494, 900, -1456] | 1156x38 | 5000 | Transport | F |
| `TRN_AIR_TERMINAL` | OUTER | [4, -1] | [0, -1500, 300, -1200] | [-256, -1456, 440, -1426] | 696x30 | 150000 | Transport | D |
| `TRN_AIR_TOWER` | OUTER | [5, -1] | [300, -1500, 600, -1200] | [460, -1456, 484, -1432] | 24x24 | 40000 | Transport | D |
| `TRN_AIR_HANGARS` | OUTER | [6, -1] | [600, -1500, 900, -1200] | [500, -1456, 860, -1426] | 360x30 | 80000 | Transport | E |
| `TRN_AIR_FIRE` | OUTER | [7, -1] | [900, -1500, 1200, -1200] | [880, -1456, 1020, -1426] | 140x30 | 40000 | Transport | E |
| `TRN_AIR_CARGO` | OUTER | [7, -1] | [900, -1500, 1200, -1200] | [1040, -1456, 1300, -1426] | 260x30 | 40000 | Transport | E |
| `TRN_AIR_PARKING` | OUTER | [8, -1] | [1200, -1500, 1500, -1200] | [1424, -1400, 1496, -1080] | 72x320 | 5000 | Transport | F |
| `TRN_RAIL_LINE` | OUTER | [4, 8] | [0, 1200, 300, 1500] | [-1420, 1440, 1420, 1460] | 2840x20 | 40000 | Transport | D |
| `TRN_RAIL_PLATFORMS` | OUTER | [3, 8] | [-300, 1200, 0, 1500] | [-420, 1460, 280, 1474] | 700x14 | 20000 | Transport | D |
| `TRN_RAIL_STATION` | OUTER | [3, 8] | [-300, 1200, 0, 1500] | [-420, 1474, 280, 1496] | 700x22 | 150000 | Transport | D |
| `TRK_MOTORSPORT_MUSEUM` | T | [6, 3] | [600, -300, 900, 0] | [772, -398, 930, -174] | 158x224 | 150000 | SportsCivic | D |
| `TRK_SKID_PAD` | T | [7, 3] | [900, -300, 1200, 0] | [1010, -360, 1120, -200] | 110x160 | 20000 | Track | E |
| `TRK_KARTING` | T | [7, 1] | [900, -900, 1200, -600] | [932, -934, 1124, -670] | 192x264 | 40000 | Track | E |
| `TRK_PADDOCK_ANNEX` | T | [6, 0] | [600, -1200, 900, -900] | [716, -1142, 828, -894] | 112x248 | 20000 | Track | E |
| `TRK_MEDICAL` | T | [6, 1] | [600, -900, 900, -600] | [676, -894, 732, -700] | 56x194 | 40000 | SportsCivic | D |
| `TRK_WORKSHOP` | T | [6, 2] | [600, -600, 900, -300] | [676, -640, 732, -190] | 56x450 | 40000 | Track | E |
| `TRK_FAN_ZONE` | T | [6, 1] | [600, -900, 900, -600] | [780, -846, 924, -718] | 144x128 | 40000 | Commercial | E |
| `TRK_GRANDSTAND_E2` | T | [6, 2] | [600, -600, 900, -300] | [612, -400, 662, -250] | 50x150 | 40000 | Track | D |
| `TRK_GRANDSTAND_N` | T | [6, 3] | [600, -300, 900, 0] | [750, -42, 1000, -16] | 250x26 | 40000 | Track | D |
| `TRK_START_GANTRY` | T | [6, 2] | [600, -600, 900, -300] | [772, -566, 940, -526] | 168x40 | 20000 | Track | D |
| `TRK_SCORING_TOWER` | T | [7, 3] | [900, -300, 1200, 0] | [960, -300, 1000, -260] | 40x40 | 20000 | Lighting | D |
| `TRK_FLOODLIGHT_A` | T | [6, 1] | [600, -900, 900, -600] | [680, -690, 720, -650] | 40x40 | 5000 | Lighting | D |
| `TRK_FLOODLIGHT_B` | T | [7, 3] | [900, -300, 1200, 0] | [1010, -40, 1050, -18] | 40x22 | 5000 | Lighting | D |
| `TRK_SPECTATOR_VILLAGE` | OUTER | [8, 1] | [1200, -900, 1500, -600] | [1214, -896.5, 1360, -758.8] | 146x137.7 | 80000 | Commercial | E |
| `TRK_FOOD_COURT` | OUTER | [8, 3] | [1200, -300, 1500, 0] | [1214, -312, 1360, -166.2] | 146x145.8 | 40000 | Commercial | E |
| `TRK_MERCH_HALL` | OUTER | [8, 3] | [1200, -300, 1500, 0] | [1214, -150, 1360, -15] | 146x135 | 40000 | Commercial | E |
| `TRK_PARKING_E1` | OUTER | [8, 5] | [1200, 300, 1500, 600] | [1214, 305.1, 1360, 422.4] | 146x117.3 | 5000 | Transport | F |
| `TRK_PARKING_E2` | OUTER | [8, 5] | [1200, 300, 1500, 600] | [1214, 437.7, 1360, 504] | 146x66.3 | 5000 | Transport | F |
| `TRK_CAMPSITE` | OUTER | [8, 1] | [1200, -900, 1500, -600] | [1214, -740.8, 1360, -615] | 146x125.8 | 20000 | Nature | F |
| `TRK_GATE_E` | OUTER | [8, 5] | [1200, 300, 1500, 600] | [1214, 519.3, 1360, 555] | 146x35.7 | 20000 | Transport | E |
| `TRK_TRANSPORT_HUB` | OUTER | [8, 7] | [1200, 900, 1500, 1200] | [1214, 1037.6, 1360, 1134.3] | 146x96.7 | 40000 | Transport | D |
| `TRK_PARKING_E3` | OUTER | [8, 7] | [1200, 900, 1500, 1200] | [1214, 1151.4, 1360, 1214] | 146x62.6 | 5000 | Transport | F |
| `TRN_BICYCLE_SHARE` | OUTER | [8, -1] | [1200, -1500, 1500, -1200] | [1268, -1276, 1360, -1214] | 92x62 | 5000 | Props | F |
| `ICON_TOWER` | OUTER | [4, 8] | [0, 1200, 300, 1500] | [45, 1214, 198, 1360] | 153x146 | 150000 | Commercial | D |
| `WRK_LOGISTICS_HUB` | OUTER | [7, 8] | [900, 1200, 1200, 1500] | [978.2, 1214, 1093.5, 1360] | 115.3x146 | 80000 | Commercial | E |
| `CIVIC_EMERGENCY_OPS` | OUTER | [7, 8] | [900, 1200, 1200, 1500] | [1109.2, 1214, 1214, 1360] | 104.8x146 | 80000 | SportsCivic | E |
| `TRN_BUS_SHELTERS` | OUTER | [1, 8] | [-900, 1200, -600, 1500] | [-836.6, 1214, -615, 1360] | 221.6x146 | 5000 | Props | F |
| `UTL_SOLAR_FARM` | OUTER | [3, 8] | [-300, 1200, 0, 1500] | [-274.2, 1214, -155.4, 1360] | 118.8x146 | 20000 | Props | E |
| `TRF_TRAFFIC_SIGNALS` | OUTER | [3, 8] | [-300, 1200, 0, 1500] | [-139.2, 1214, -15, 1360] | 124.2x146 | 5000 | Traffic | F |
| `TRF_ROAD_MARKINGS` | OUTER | [-1, -1] | [-1500, -1500, -1200, -1200] | [-1360, -1276, -1268, -1214] | 92x62 | 5000 | Props | F |
| `WRK_CONSTRUCTION_YARD` | OUTER | [1, -1] | [-900, -1500, -600, -1200] | [-788.7, -1360, -615, -1214] | 173.7x146 | 20000 | Commercial | F |
| `SPT_MOTOCROSS_PARK` | OUTER | [3, -1] | [-300, -1500, 0, -1200] | [-225.6, -1360, -15, -1214] | 210.6x146 | 40000 | SportsCivic | E |
| `HOT_AIRPORT_HOTEL` | OUTER | [5, -1] | [300, -1500, 600, -1200] | [427.5, -1360, 555, -1214] | 127.5x146 | 150000 | Commercial | D |
| `LGT_STREET_LIGHTING` | OUTER | [7, -1] | [900, -1500, 1200, -1200] | [1128.7, -1360, 1214, -1214] | 85.3x146 | 5000 | Lighting | F |
| `REC_URBAN_FARM` | OUTER | [-1, 3] | [-1500, -300, -1200, 0] | [-1360, -204, -1214, -15] | 146x189 | 20000 | Nature | F |
| `TRN_STREET_DEPOT` | OUTER | [-1, 7] | [-1500, 900, -1200, 1200] | [-1360, 1014.9, -1214, 1214] | 146x199.1 | 40000 | Transport | E |
| `REC_FARMERS_MARKET` | OUTER | [-1, 5] | [-1500, 300, -1200, 600] | [-1360, 356.1, -1214, 555] | 146x198.9 | 40000 | Commercial | E |
| `SPT_ARCHERY_RANGE` | OUTER | [-1, 1] | [-1500, -900, -1200, -600] | [-1360, -836.6, -1214, -615] | 146x221.6 | 40000 | SportsCivic | E |
| `METRO_ENT_1` | R | [0, 3] | [-1200, -300, -900, 0] | [-1078, -34, -1062, -18] | 16x16 | 20000 | Transport | D |
| `METRO_ENT_2` | R | [0, 4] | [-1200, 0, -900, 300] | [-934, 122, -918, 138] | 16x16 | 20000 | Transport | D |
| `METRO_ENT_3` | R | [0, 7] | [-1200, 900, -900, 1200] | [-934, 1022, -918, 1038] | 16x16 | 20000 | Transport | D |
| `METRO_ENT_4` | R | [2, 2] | [-600, -600, -300, -300] | [-478, -478, -462, -462] | 16x16 | 20000 | Transport | D |
| `METRO_ENT_5` | R | [7, 5] | [900, 300, 1200, 600] | [918, 318, 934, 334] | 16x16 | 20000 | Transport | D |
| `PLAYGROUND_1` | G | [1, 1] | [-900, -900, -600, -600] | [-880, -670, -810, -620] | 70x50 | 5000 | Props | F |
| `PLAYGROUND_2` | G | [3, 1] | [-300, -900, 0, -600] | [-280, -880, -210, -830] | 70x50 | 5000 | Props | F |
| `PLAYGROUND_3` | G | [4, 7] | [0, 900, 300, 1200] | [20, 1130, 90, 1180] | 70x50 | 5000 | Props | F |
| `SKATEPARK` | G | [1, 2] | [-900, -600, -600, -300] | [-690, -580, -620, -530] | 70x50 | 5000 | Props | F |
| `SPORTS_FIELD_1` | G | [0, 0] | [-1200, -1200, -900, -900] | [-1180, -990, -1070, -920] | 110x70 | 20000 | SportsCivic | F |
| `SPORTS_FIELD_2` | G | [3, 0] | [-300, -1200, 0, -900] | [-280, -990, -170, -920] | 110x70 | 20000 | SportsCivic | F |
| `AMPHITHEATRE` | G | [2, 1] | [-600, -900, -300, -600] | [-580, -670, -510, -620] | 70x50 | 20000 | SportsCivic | F |

#### Where the new land comes from

| Zone family | extent | facilities |
|---|---|---|
| G-cell venues (5 of the 13 park cells) | 276x276 m cells, 24 m green ring kept | `STADIUM_CRICKET`, `STADIUM_FOOTBALL`, `STADIUM_ATHLETICS`, `COMPLEX_SWIMMING`, `ARENA_INDOOR` |
| Pocket-park infill (all 12 pocket parks) | corner of a 132x132 m park | 12 civic/health/school buildings |
| Park-corner infill (7 of the 13 big parks) | corner of a 276x276 m park | temple, gurdwara, dog park, zen garden, bandstand, restrooms, boathouse |
| Inner band (between grid edge and ring) | 162 m deep, split by the 12 ring ramps | 55 belt facilities (zoo, botanical, amusement, golf, utilities, offices, hotels ...) |
| Outer frame (outside the ring) | 72 m strips at +-1424..1496 | airport, railway, car park |
| Track zone + circuit infield | `layout.json` `track.zone_rect` [612, -1188, 1188, -12] | pit, stands, tower, museum, karting, skid pad, fan zone |
| Metro entrances | 16x16 m in the free corner of a pocket park | 5 |

## 3. Build order - 18 waves, max 2 concurrent builds

8 cores / ~2 GB RAM => never more than two headless Blender sessions at once. Each agent names its module, the facilities it owns and the data files it reads/writes. Facility lists inside an agent are topologically sorted on `depends_on`.

| Wave | Phase | Agent | Module | # | Facilities | Data |
|---:|---|---|---|---:|---|---|
| 1 | E | `A1_01_0` | Nature | 5 | `REC_ZOO`, `REC_BOTANICAL`, `REC_AMUSEMENT`, `REC_GOLF_RANGE`, `REC_WATER_PARK` | `out/nature_w1.blend` |
| 2 | D+E | `A2_01_0` | Nature | 13 | `RES_COURTYARD_HOMES`, `MKT_COURTYARD`, `RES_COURTYARD_EM`, `PARK_MAIN`, `PARK_POCKET`, `PLAZA_CENTRAL`, `PARK_DOG`, `GARDEN_ZEN`, `BANDSTAND`, `BOATHOUSE_PIER`, `UTL_CEMETERY`, `TRK_CAMPSITE`, `REC_URBAN_FARM` | `out/nature_w2.blend` |
| 2 | D+E | `A2_02_1` | Props | 7 | `UTL_WATER_TREATMENT`, `UTL_SEWAGE`, `UTL_WATER_TOWER`, `UTL_WASTE`, `UTL_SUBSTATION`, `UTL_GAS_DEPOT`, `UTL_SOLAR_FARM` | `out/props_w2.blend` |
| 3 | D+E | `A3_01_1` | Props | 11 | `IND_YARD`, `RESTROOM_PARK`, `UTL_TELECOM`, `UTL_TRANSFORMER`, `TRN_BICYCLE_SHARE`, `TRN_BUS_SHELTERS`, `TRF_ROAD_MARKINGS`, `PLAYGROUND_1`, `PLAYGROUND_2`, `PLAYGROUND_3`, `SKATEPARK` | `out/props_w3.blend` |
| 3 | D+E | `A3_02_2` | Lighting | 3 | `TRK_SCORING_TOWER`, `TRK_FLOODLIGHT_A`, `TRK_FLOODLIGHT_B` | `out/lighting_w3.blend` |
| 4 | F | `A4_01_2` | Lighting | 1 | `LGT_STREET_LIGHTING` | `out/lighting_w4.blend` |
| 4 | F | `A4_02_3` | Traffic | 1 | `TRF_TRAFFIC_SIGNALS` | `out/traffic_w4.blend` |
| 5 | D | `A5_01_4` | Residential | 6 | `RES_HOUSE_TERRACED`, `RES_HOUSE_VILLA`, `RES_APARTMENT_LOW`, `RES_APARTMENT_TOWER`, `HOUSING_SENIOR`, `DORMITORIES` | `out/residential_w5.blend` |
| 5 | D | `A5_02_5` | SportsCivic | 14 | `CIVIC_TOWN_OFFICES`, `CITY_HALL`, `CUL_CINEMA`, `CUL_CLUB`, `REC_GYM`, `STADIUM_CRICKET`, `STADIUM_FOOTBALL`, `STADIUM_ATHLETICS`, `COMPLEX_SWIMMING`, `ARENA_INDOOR`, `STATION_FIRE`, `HOSPITAL_MAIN`, `STATION_POLICE`, `SCHOOL_SECONDARY` | `out/sportscivic_w5.blend` |
| 6 | D | `A6_01_5` | SportsCivic | 14 | `SCHOOL_KINDER`, `CLINIC_URGENT`, `SCHOOL_PRIMARY`, `LIBRARY_PUBLIC`, `MOSQUE`, `CHURCH`, `COLLEGE_VOCATIONAL`, `COURTHOUSE`, `MUSEUM_CITY`, `PLANETARIUM`, `THEATRE`, `CONCERT_HALL`, `GALLERY_ART`, `ARCADE_GAMES` | `out/sportscivic_w6.blend` |
| 7 | D | `A7_01_5` | SportsCivic | 6 | `CASINO`, `EMBASSY`, `UNIVERSITY_MAIN`, `UNIVERSITY_FACULTY`, `TRK_MOTORSPORT_MUSEUM`, `TRK_MEDICAL` | `out/sportscivic_w7.blend` |
| 8 | E | `A8_01_5` | SportsCivic | 6 | `UTL_CREMATORIUM`, `SPT_VELODROME`, `SPT_TENNIS_CENTRE`, `CIVIC_EMERGENCY_OPS`, `SPT_MOTOCROSS_PARK`, `SPT_ARCHERY_RANGE` | `out/sportscivic_w8.blend` |
| 9 | D+E | `A9_01_5` | SportsCivic | 5 | `TEMPLE`, `GURUDWARA`, `SPORTS_FIELD_1`, `SPORTS_FIELD_2`, `AMPHITHEATRE` | `out/sportscivic_w9.blend` |
| 9 | D+E | `A9_02_6` | Commercial | 14 | `RES_SHOPHOUSE`, `RET_SHOPS`, `RET_CORNER_SHOP`, `RET_SUPERMARKET`, `RET_MALL`, `RET_BAZAAR`, `RET_RESTAURANT`, `RET_CAFE`, `RET_TEAHOUSE`, `FIN_BANK`, `RET_WORKSHOP_STALL`, `OFF_TOWER`, `OFF_MIDRISE`, `IND_WAREHOUSE` | `out/commercial_w9.blend` |
| 10 | D | `A10_01_6` | Commercial | 14 | `IND_FACTORY`, `HOT_HOTEL`, `DEPARTMENT_STORE`, `CONFERENCE_CENTRE`, `OFFICE_COWORKING`, `BANQUET_HALL`, `HOSTEL`, `BREWERY`, `COLD_STORAGE`, `WORKSHOP_FABRICATION`, `WRK_TECH_PARK`, `RET_MOTOR_TRADE`, `ICON_TOWER`, `HOT_AIRPORT_HOTEL` | `out/commercial_w10.blend` |
| 11 | E | `A11_01_6` | Commercial | 11 | `MED_FILM_STUDIO`, `MED_BROADCAST`, `RET_WHOLESALER`, `HOT_MOTEL`, `WRK_DATA_CENTRE`, `TRK_FAN_ZONE`, `TRK_SPECTATOR_VILLAGE`, `TRK_FOOD_COURT`, `TRK_MERCH_HALL`, `WRK_LOGISTICS_HUB`, `REC_FARMERS_MARKET` | `out/commercial_w11.blend` |
| 12 | D+E | `A12_01_6` | Commercial | 1 | `WRK_CONSTRUCTION_YARD` | `out/commercial_w12.blend` |
| 12 | D+E | `A12_02_7` | Transport | 14 | `IND_DEPOT`, `CARPARK_MULTISTOREY`, `TRN_BUS_DEPOT`, `TRN_MAIL_SORTING`, `TRN_COACH_TERMINAL`, `TRN_RUNWAY`, `TRN_AIR_TERMINAL`, `TRN_AIR_TOWER`, `TRN_RAIL_LINE`, `TRN_RAIL_PLATFORMS`, `TRN_RAIL_STATION`, `TRK_TRANSPORT_HUB`, `METRO_ENT_1`, `METRO_ENT_2` | `out/transport_w12.blend` |
| 13 | D | `A13_01_7` | Transport | 3 | `METRO_ENT_3`, `METRO_ENT_4`, `METRO_ENT_5` | `out/transport_w13.blend` |
| 14 | E | `A14_01_7` | Transport | 6 | `TRN_TRUCK_STOP`, `TRN_AIR_HANGARS`, `TRN_AIR_FIRE`, `TRN_AIR_CARGO`, `TRK_GATE_E`, `TRN_STREET_DEPOT` | `out/transport_w14.blend` |
| 15 | D+E | `A15_01_7` | Transport | 8 | `TRN_PARK_AND_RIDE`, `TRN_PETROL_EV`, `TRN_TAXIWAY`, `TRN_APRON`, `TRN_AIR_PARKING`, `TRK_PARKING_E1`, `TRK_PARKING_E2`, `TRK_PARKING_E3` | `out/transport_w15.blend` |
| 15 | D+E | `A15_02_8` | Track | 8 | `TRACK_CIRCUIT`, `TRACK_PIT`, `TRACK_GRANDSTAND`, `TRACK_PADDOCK`, `TRACK_TOWER`, `TRK_GRANDSTAND_E2`, `TRK_GRANDSTAND_N`, `TRK_START_GANTRY` | `out/track_w15.blend` |
| 16 | E | `A16_01_8` | Track | 4 | `TRK_SKID_PAD`, `TRK_KARTING`, `TRK_PADDOCK_ANNEX`, `TRK_WORKSHOP` | `out/track_w16.blend` |
| 17 | D+E | `A17_01_8` | Track | 1 | `TRACK_PARKING` | `out/track_w17.blend` |
| 17 | D+E | `A17_02_9` | Interiors | 2 | `INT_HERO_INTERIORS`, `INT_MALL_FITOUT` | `out/interiors_w17.blend` |
| 18 | F | `A18_01_9` | Interiors | 1 | `INT_SHELL_INTERIORS` | `out/interiors_w18.blend` |

Ordering rationale: green ground (`Nature`) first because five park cells are converted by venues; `Residential`/`SportsCivic`/`Commercial` shells next; `Transport` and `Track` after their access land exists; `Interiors` last because it is a fit-out pass over buildings that already stand; `Props`/`Lighting`/`Traffic` early because they are street-level and repeat-instanced.

## 4. Tri budget

| Class | cap | facilities | tris | share |
|---|---:|---:|---:|---:|
| hero | 150,000 | 49 | 5,830,000 | 66% |
| regular | 40,000 | 87 | 2,805,000 | 32% |
| prop | 5,000 | 32 | 154,500 | 2% |
| tree | 8,000 | 11 | 76,000 | 1% |
| **project total** | - | **179** | **8,865,500** | 100% |

| Module | facilities | tris | | Phase | facilities | tris |
|---|---:|---:|---|---|---:|---:|
| SportsCivic | 45 | 3,440,000 | | D | 96 | 6,134,500 |
| Commercial | 40 | 2,523,000 | | E | 41 | 2,310,000 |
| Transport | 31 | 1,100,000 | | F | 42 | 421,000 |
| Nature | 18 | 736,000 | |  | 0 | 0 |
| Track | 13 | 495,000 | |  | 0 | 0 |
| Residential | 6 | 206,500 | |  | 0 | 0 |
| Props | 18 | 205,000 | |  | 0 | 0 |
| Interiors | 3 | 120,000 | |  | 0 | 0 |
| Lighting | 4 | 35,000 | |  | 0 | 0 |
| Traffic | 1 | 5,000 | |  | 0 | 0 |

Top 20 items:

| # | Facility | class | tris | module | wave |
|---:|---|---|---:|---|---:|
| 1 | `RET_MALL` - Shopping malls | hero | 150,000 | Commercial | 9 |
| 2 | `RET_BAZAAR` - Covered bazaar hall | hero | 150,000 | Commercial | 9 |
| 3 | `OFF_TOWER` - Office towers + skyscrapers | hero | 150,000 | Commercial | 9 |
| 4 | `CITY_HALL` - City hall (tier-1 hero) | hero | 150,000 | SportsCivic | 5 |
| 5 | `HOT_HOTEL` - Hotels | hero | 150,000 | Commercial | 10 |
| 6 | `TRACK_GRANDSTAND` - Grandstands (main + hairpin) | hero | 150,000 | Track | 15 |
| 7 | `STADIUM_CRICKET` - Cricket stadium (open bowl, 228x228) | hero | 150,000 | SportsCivic | 5 |
| 8 | `STADIUM_FOOTBALL` - Football stadium with OPEN ROOF (228x228) | hero | 150,000 | SportsCivic | 5 |
| 9 | `STADIUM_ATHLETICS` - Athletics / Olympic stadium (228x228) | hero | 150,000 | SportsCivic | 5 |
| 10 | `ARENA_INDOOR` - Indoor arena (basketball / concerts) | hero | 150,000 | SportsCivic | 5 |
| 11 | `COURTHOUSE` - Law courts + public square | hero | 150,000 | SportsCivic | 6 |
| 12 | `MUSEUM_CITY` - City museum | hero | 150,000 | SportsCivic | 6 |
| 13 | `CONCERT_HALL` - Concert hall (symphonic) | hero | 150,000 | SportsCivic | 6 |
| 14 | `UNIVERSITY_MAIN` - University: main building + quad | hero | 150,000 | SportsCivic | 7 |
| 15 | `REC_ZOO` - City zoo (compact) | hero | 150,000 | Nature | 1 |
| 16 | `REC_AMUSEMENT` - Amusement park | hero | 150,000 | Nature | 1 |
| 17 | `TRN_AIR_TERMINAL` - Airport terminal (open frontage) | hero | 150,000 | Transport | 12 |
| 18 | `TRN_RAIL_STATION` - Railway station concourse | hero | 150,000 | Transport | 12 |
| 19 | `TRK_MOTORSPORT_MUSEUM` - Motorsport museum + hall of fame | hero | 150,000 | SportsCivic | 7 |
| 20 | `ICON_TOWER` - Icon supertall tower (mixed office + hotel + observatory) | hero | 150,000 | Commercial | 10 |

## 5. Priority coverage checklist

| Ask | Where it lands |
|---|---|
| Parks / open space | `PARK_MAIN` (13 park cells), `PARK_POCKET` (12), `PLAZA_CENTRAL`, `RES_COURTYARD_HOMES` (64 courtyards), `REC_URBAN_FARM`, `REC_FARMERS_MARKET`, `UTL_CEMETERY` - all 26 open spaces keep >70% of their green |
| Playgrounds | `PLAYGROUND_1/2/3`, `SKATEPARK`, `AMPHITHEATRE`, `SPORTS_FIELD_1/2` sited in free corners of big parks; every pocket park also carries playground equipment in its features list |
| Offices | `OFF_TOWER` (55 office_tower parcels, 12-60 fl), `OFF_MIDRISE` (<=20 fl), `OFFICE_COWORKING` superlot, `WRK_TECH_PARK`, `WRK_LOGISTICS_HUB`, `ICON_TOWER` (45 fl), `MED_BROADCAST`, `CIVIC_EMERGENCY_OPS` |
| Big / skyscraper buildings | `OFF_TOWER` incl. `LM_LANDMARK_TOWER` (60 fl, B_4_3_0_1_0_0), `RES_APARTMENT_TOWER` (12 lots, 15-29 fl), `HOT_HOTEL` (to 25 fl) and the new `ICON_TOWER` (150x163 m podium, 180 m shaft) on the north band |
| Racing track - grandstands | `TRACK_GRANDSTAND` (main + hairpin, existing) + `TRK_GRANDSTAND_E2` + `TRK_GRANDSTAND_N` = 4 stands |
| Racing track - pit & paddock | `TRACK_PIT` (existing, 14 garages) + `TRACK_PADDOCK` + `TRK_PADDOCK_ANNEX` + `TRK_WORKSHOP` + `TRK_MEDICAL` |
| Racing track - floodlights & furniture | `TRK_FLOODLIGHT_A`, `TRK_FLOODLIGHT_B` (4x28 m masts each), `TRK_START_GANTRY`, `TRK_SCORING_TOWER`, `TRK_FAN_ZONE` |
| Shopping market / store / mart / supermarket | `RET_BAZAAR` (already built, 1236 M parcels in `out/market.blend`), `RET_SUPERMARKET` (10), `RET_MALL` (8), `RET_SHOPS` (508), `RET_CORNER_SHOP` (9), `RET_TEAHOUSE` (89), `RET_RESTAURANT` (197), `DEPARTMENT_STORE` superlot, `RET_WHOLESALER` cash & carry |
| Cricket stadium | `STADIUM_CRICKET` - 228x228 m open bowl on park `PK_1_0`, cell [1,0] [-888,-1188,-612,-912], outfield 150 m, 4 stands, sightscreen, floodlight pylons, 24 m green ring kept |
| Football stadium with OPEN ROOF | `STADIUM_FOOTBALL` - 228x228 m on park `PK_4_0`, cell [4,0] [12,-1188,288,-912], 105x68 pitch open to the sky (no roof membrane), 4 stands, open oculus |
| Airport | `TRN_RUNWAY` 1200x38 m STOL strip, `TRN_TAXIWAY`, `TRN_APRON` (6 stands), `TRN_AIR_TERMINAL` 700x30 m, `TRN_AIR_TOWER` (26 m), `TRN_AIR_HANGARS`, `TRN_AIR_FIRE`, `TRN_AIR_CARGO`, `TRN_AIR_PARKING` - all in the south outer frame |

## 6. Conflicts

| Level | kind | n |
|---|---|---:|
| hard | `superlot_merges_parcels` | 21 |
| hard | `no_adjacent_road` | 12 |
| hard | `converts_park` | 5 |
| info | `dependency` | 137 |
| info | `outer_or_band_land` | 67 |
| info | `already_built` | 8 |
| soft | `no_adjacent_road` | 112 |
| soft | `inside_pocket_park` | 16 |
| soft | `inside_park` | 3 |

**38 hard, 131 soft, 212 info** conflicts recorded on 38 facilities (full list per facility in `program.json` -> `conflicts[]`).

### 6.1 Districts

- 21 superlot merges live in **R / D / E / I** cells only - never in **M**, because `out/market.blend` already models all 1236 M parcels (validator rule `market_already_built`).
- District tally of the program: D 16, E 15, G 20, I 8, M 5, OUTER 67, R 29, T 19.
- **8 facilities already reference M-district parcels** (shophouses, restaurants, teahouses, courtyard markets): they are *already built*, so the build pass must skip or instance them, not remodel.

### 6.2 Roads

- Zero rect intersects a road corridor (checked against 454 corridors + the 4 ring arcs).
- **124 facilities have no road touching them** - the inner band, the outer frame, the T circuit cells and the circuit infield contain no road at all in `layout.json`.
  Every one carries `depends_on: ["Roads"]`: the Roads module must add service roads / access spurs before the build wave runs. This is the single largest structural gap in the layout.
- Band land is reachable only through the 12 interchange ramps (x/y = -1400, -600, 0, 600, 1400); the ramps themselves are the corridors the band rects were kept clear of (50 m clearance at every ramp).

### 6.3 The 26 open spaces (13 parks + 12 pocket parks + 1 plaza)

| Open space | cell | rect | disposition |
|---|---|---|---|
| `PK_0_0` (park) | [0, 0] | [-1188, -1188, -912, -912] | corner infill: `RESTROOM_PARK` (>70% stays green - soft conflict) |
| `PK_1_0` (park) | [1, 0] | [-888, -1188, -612, -912] | **converted to `STADIUM_CRICKET`** (24 m green ring, jogging path and trees kept) |
| `PK_2_0` (park) | [2, 0] | [-588, -1188, -312, -912] | corner infill: `BOATHOUSE_PIER` (>70% stays green - soft conflict) |
| `PK_3_0` (park) | [3, 0] | [-288, -1188, -12, -912] | corner infill: `PARK_DOG` (>70% stays green - soft conflict) |
| `PK_4_0` (park) | [4, 0] | [12, -1188, 288, -912] | **converted to `STADIUM_FOOTBALL`** (24 m green ring, jogging path and trees kept) |
| `PK_0_1` (park) | [0, 1] | [-1188, -888, -912, -612] | **converted to `STADIUM_ATHLETICS`** (24 m green ring, jogging path and trees kept) |
| `PK_1_1` (park) | [1, 1] | [-888, -888, -612, -612] | corner infill: `TEMPLE` (>70% stays green - soft conflict) |
| `PK_2_1` (park) | [2, 1] | [-588, -888, -312, -612] | corner infill: `BANDSTAND` (>70% stays green - soft conflict) |
| `PK_3_1` (park) | [3, 1] | [-288, -888, -12, -612] | corner infill: `GURUDWARA` (>70% stays green - soft conflict) |
| `PK_4_1` (park) | [4, 1] | [12, -888, 288, -612] | **converted to `COMPLEX_SWIMMING`** (24 m green ring, jogging path and trees kept) |
| `PK_0_2` (park) | [0, 2] | [-1188, -588, -912, -312] | **converted to `ARENA_INDOOR`** (24 m green ring, jogging path and trees kept) |
| `PK_1_2` (park) | [1, 2] | [-888, -588, -612, -312] | corner infill: `GARDEN_ZEN` (>70% stays green - soft conflict) |
| `PK_2_2_0_0` (pocket_park) | [2, 2] | [-588, -588, -456, -456] | corner infill: `SCHOOL_SECONDARY` (>70% stays green - soft conflict) |
| `PK_2_2_1_1` (pocket_park) | [2, 2] | [-444, -444, -312, -312] | corner infill: `SCHOOL_KINDER` (>70% stays green - soft conflict) |
| `PK_0_3_0_1` (pocket_park) | [0, 3] | [-1188, -144, -1056, -12] | corner infill: `STATION_FIRE` (>70% stays green - soft conflict) |
| `PK_2_3_1_0` (pocket_park) | [2, 3] | [-444, -288, -312, -156] | corner infill: `CLINIC_URGENT` (>70% stays green - soft conflict) |
| `PK_0_4_1_0` (pocket_park) | [0, 4] | [-1044, 12, -912, 144] | corner infill: `HOSPITAL_MAIN` (>70% stays green - soft conflict) |
| `PZ_4_4_0_0` (central_plaza) | [4, 4] | [12, 12, 144, 144] | stays open (ground, paths, planting only) |
| `PK_7_5_0_0` (pocket_park) | [7, 5] | [912, 312, 1044, 444] | corner infill: `HOUSING_SENIOR` (>70% stays green - soft conflict) |
| `PK_2_6_0_1` (pocket_park) | [2, 6] | [-588, 756, -456, 888] | corner infill: `SCHOOL_PRIMARY` (>70% stays green - soft conflict) |
| `PK_3_6_0_0` (pocket_park) | [3, 6] | [-288, 612, -156, 744] | corner infill: `CHURCH` (>70% stays green - soft conflict) |
| `PK_3_6_1_1` (pocket_park) | [3, 6] | [-144, 756, -12, 888] | corner infill: `COLLEGE_VOCATIONAL` (>70% stays green - soft conflict) |
| `PK_0_7_1_0` (pocket_park) | [0, 7] | [-1044, 912, -912, 1044] | corner infill: `STATION_POLICE` (>70% stays green - soft conflict) |
| `PK_2_7_0_0` (pocket_park) | [2, 7] | [-588, 912, -456, 1044] | corner infill: `LIBRARY_PUBLIC` (>70% stays green - soft conflict) |
| `PK_2_7_1_0` (pocket_park) | [2, 7] | [-444, 912, -312, 1044] | corner infill: `MOSQUE` (>70% stays green - soft conflict) |
| `PK_4_7` (park) | [4, 7] | [12, 912, 288, 1188] | stays open (ground, paths, planting only) |

- 5 park cells are converted to venues (`converts_park`, hard), 19 spaces take a corner building (soft), and the central plaza keeps its fountain/stage.

### 6.4 LAKE_1

- Lake polygon bbox [-552.58, -1142.57, -335.1, -969.78]. **0 facilities intersect it** - validator fails the file if any does.
- The lake sits inside park `PK_2_0`; the only structure nearby is `BOATHOUSE_PIER` on the north shore and `SPORTS_FIELD_2` was moved to `PK_3_0` to stay off the water.

### 6.5 Race circuit

- Circuit zone [612, -1188, 1188, -12], spline length 3388.88 m (`TRACK_CIRCUIT`).
- 19 new `TRK_*` rects sit in the zone; all are clear of the 7 existing track parcels (`TRK_PIT_BUILDING`, `TRK_GRANDSTAND_MAIN`, `TRK_HAIRPIN_STAND`, `TRK_PADDOCK`, `TRK_CONTROL_TOWER`, `TRK_PARKING_A/B`) - validator rule `track_parcel_clearance`.
- Infield facilities share one access: the pit lane entry. Service road required from the south/west grid edge.
- Non-track facilities are forbidden inside the zone (`inside_circuit_zone` = error).

### 6.6 Highway ring (r = 120 corner arcs, deck hw 17 at z=8)

- 0 rects touch the ring or its arcs; band rects keep >=50 m clearance from every ramp.
- The ring is elevated, so band land is not severed by it - but nothing drives onto the band today.

### 6.7 Already-built assets

| Built | ground truth | affected facilities |
|---|---|---|
| market | `out/market.blend` - all 1236 M parcels | `RES_SHOPHOUSE`, `RET_SHOPS`, `RET_BAZAAR`, `RET_RESTAURANT`, `RET_TEAHOUSE`, `RET_WORKSHOP_STALL`, `MKT_COURTYARD`, `INT_HERO_INTERIORS` |
| roads (pilot) | `out/roads.blend` - NE arterials + 144 market alleys, bbox x[300,1200] y[600,1200] | 0 new facilities already sit on finished road (free access): none |
| flyover | `out/flyover.blend` - ring H_07 + H_08 arc + ramp X_N_600 (40 m east bulge), ground band +-20 m | none |

## 7. Compromises taken (sanctioned by the brief)

1. **STOL strip runway** - 1200x38 m instead of 3000 m: a 3x3 km city cannot hold a full runway inside the ring, and a taxiway crossing the elevated ring would violate the no-road-intersection rule. Runway + 28 m taxiway link + 1156x38 m apron + 700x30 m terminal all sit in the south outer frame.
2. **Airport outside the ring** - the whole airport is a linear string layout in the south frame, so it never crosses a corridor; access is service-only (documented risk R2).
3. **Venues in park cells** - 5 of the 13 G-cell parks become stadiums/complexes, each keeping a 24 m green ring, which is how the brief's cricket + open-roof football + athletics + swimming + indoor arena fit without eating the R/D/E grid.
4. **Circuit infield used for the motorsport cluster** - museum, karting, skid pad, paddock annexe, medical and workshop are packed inside the oval; the extra grandstands take the north/west verges.
5. **Band land shared, not doubled** - every 162 m band zone is split into non-overlapping slots (`ZONE_PLAN`), so the zoo shares W1 with the archery range, the data centre shares E2 with the track food court, etc.

## 8. Reserved (unallocated) land

- Inner band: 1774980 m2 total, 1227551 m2 assigned to band facilities, **547429 m2 left as reserve** (mainly the four corner squares between the ring arcs and the trimmed zones, plus the ramp gaps).
- Outer frame: 72 m strips at x/y +-1424..1496 - the airport string uses the south strip, the railway the north strip; the west strip and most of the east strip are free for later phases.
- Ramp gaps (50 m either side of each of the 12 ramps) are deliberately empty.

## 9. Risk register (top 6)

| # | Risk | Impact | Mitigation |
|---:|---|---|---|
| R1 | 124 facilities have no adjacent road; band/frame/infield land has zero roads in `layout.json` | builds float or are unreachable | Roads module adds service roads + 12 ramp landings before waves 2+ |
| R2 | Airport, railway and the whole outer frame sit outside the ring with no legal vehicle access | airport reads as an orphan | accept service-only access, or add a at-grade crossing at one ramp |
| R3 | 21 superlot merges delete **159 existing buildings** in R/D/E/I | visible density drop in those blocks | each merge note names the parcels; check `layout.json` regeneration removes them |
| R4 | 5 park cells converted to venues + 12 pocket parks infilled = 17 of 26 open spaces carry a building | green loss | 24 m rings / >70%% green rules, plus the 6 parks that stay completely open |
| R5 | The NE flyover bulge (40 m east of X_N_600) is only measured for the built corner; unbuilt ramps may bulge the same way | band rect could clash with a future ramp | all band rects already keep 50 m from every ramp corridor; re-run this validator after any road change |
| R6 | Project tri total 8,865,500 (hero 5,830,000) across 18 waves | session memory / time | heroes are isolated one per agent where possible; props are instanced |

## 10. Full inventory (179 facilities)

| # | id | facility | category | mode | district / cell | rect | bldg | module | ph | wave | class | tris |
|---:|---|---|---|---|---|---|---|---|---|---:|---|---:|
| 1 | `BANDSTAND` | Bandstand | recreation | `district_cell` | G [2, 1] | [-360, -884, -316, -840] | 1 fl / 4.5 m / sealed T0 | Nature | F | 2 | tree | 5,000 |
| 2 | `BOATHOUSE_PIER` | Boathouse Pier | transport | `district_cell` | G [2, 0] | [-376, -942, -316, -916] | 2 fl / 4.5 m / ent T0 | Nature | F | 2 | tree | 5,000 |
| 3 | `GARDEN_ZEN` | Garden Zen | recreation | `district_cell` | G [1, 2] | [-884, -372, -812, -316] | 1 fl / 4.5 m / sealed T0 | Nature | F | 2 | tree | 5,000 |
| 4 | `MKT_COURTYARD` | Market covered courtyards | retail | `existing_parcels` | M [5, 6] | [328.4, 628.4, 360.9, 660.9] | - | Nature | F | 2 | tree | 8,000 |
| 5 | `PARK_DOG` | Park Dog | recreation | `district_cell` | G [3, 0] | [-92, -1184, -16, -1132] | 1 fl / 4.5 m / sealed T0 | Nature | F | 2 | tree | 5,000 |
| 6 | `PARK_MAIN` | Large parks (13 cells) | recreation | `existing_parcels` | G [0, 0] | [-1188, -1188, -912, -912] | - | Nature | F | 2 | tree | 8,000 |
| 7 | `PARK_POCKET` | Pocket parks (12) | recreation | `existing_parcels` | R [2, 2] | [-588, -588, -456, -456] | - | Nature | F | 2 | tree | 8,000 |
| 8 | `PLAZA_CENTRAL` | Central plaza | recreation | `existing_parcels` | D [4, 4] | [12, 12, 144, 144] | - | Nature | F | 2 | tree | 8,000 |
| 9 | `REC_AMUSEMENT` | Amusement park | recreation | `district_cell` | OUTER [-1, 4] | [-1360, 45, -1214, 340.8] | 1 fl / 8 m / ent T2 | Nature | E | 1 | hero | 150,000 |
| 10 | `REC_BOTANICAL` | Botanical garden + conservatory | recreation | `district_cell` | OUTER [-1, 2] | [-1360, -555, -1214, -220.2] | 1 fl / 9 m / ent T2 | Nature | E | 1 | hero | 120,000 |
| 11 | `REC_GOLF_RANGE` | Golf driving range + putting green | recreation | `district_cell` | OUTER [-1, 6] | [-1360, 645, -1214, 997.8] | 1 fl / 6 m / ent T2 | Nature | E | 1 | hero | 80,000 |
| 12 | `REC_URBAN_FARM` | Community farms + allotments | recreation | `district_cell` | OUTER [-1, 3] | [-1360, -204, -1214, -15] | - | Nature | F | 2 | regular | 20,000 |
| 13 | `REC_WATER_PARK` | Water park | recreation | `district_cell` | OUTER [8, 4] | [1214, 45, 1360, 289.8] | 1 fl / 8 m / ent T2 | Nature | E | 1 | hero | 120,000 |
| 14 | `REC_ZOO` | City zoo (compact) | recreation | `district_cell` | OUTER [-1, 0] | [-1360, -1214, -1214, -854.6] | 1 fl / 8 m / ent T2 | Nature | E | 1 | hero | 150,000 |
| 15 | `RES_COURTYARD_EM` | Entertainment plazas / dining courts | recreation | `existing_parcels` | E [3, 2] | [-244, -544, -200, -500] | - | Nature | F | 2 | tree | 8,000 |
| 16 | `RES_COURTYARD_HOMES` | Backyard courtyards / residential gardens | residential | `existing_parcels` | R [2, 2] | [-411, -555, -345, -489] | - | Nature | F | 2 | tree | 8,000 |
| 17 | `TRK_CAMPSITE` | Race weekend campsite | recreation | `district_cell` | OUTER [8, 1] | [1214, -740.8, 1360, -615] | - | Nature | F | 2 | regular | 20,000 |
| 18 | `UTL_CEMETERY` | Cemetery | utilities | `district_cell` | OUTER [0, -1] | [-1214, -1360, -974.4, -1214] | - | Nature | F | 2 | tree | 8,000 |
| 19 | `IND_YARD` | Open industrial yards | work | `existing_parcels` | I [5, 0] | [378, -1188, 444, -1122] | - | Props | F | 3 | prop | 5,000 |
| 20 | `PLAYGROUND_1` | Neighbourhood playground | recreation | `district_cell` | G [1, 1] | [-880, -670, -810, -620] | 1 fl / 5 m / sealed T0 | Props | F | 3 | prop | 5,000 |
| 21 | `PLAYGROUND_2` | Neighbourhood playground | recreation | `district_cell` | G [3, 1] | [-280, -880, -210, -830] | 1 fl / 5 m / sealed T0 | Props | F | 3 | prop | 5,000 |
| 22 | `PLAYGROUND_3` | Neighbourhood playground | recreation | `district_cell` | G [4, 7] | [20, 1130, 90, 1180] | 1 fl / 5 m / sealed T0 | Props | F | 3 | prop | 5,000 |
| 23 | `RESTROOM_PARK` | Restroom Park | utilities | `district_cell` | G [0, 0] | [-940, -930, -916, -916] | 1 fl / 4.5 m / sealed T0 | Props | F | 3 | prop | 5,000 |
| 24 | `SKATEPARK` | Concrete skate park | recreation | `district_cell` | G [1, 2] | [-690, -580, -620, -530] | 1 fl / 5 m / sealed T0 | Props | F | 3 | prop | 5,000 |
| 25 | `TRF_ROAD_MARKINGS` | Road marking & signage yard | traffic | `district_cell` | OUTER [-1, -1] | [-1360, -1276, -1268, -1214] | - | Props | F | 3 | prop | 5,000 |
| 26 | `TRN_BICYCLE_SHARE` | Bicycle share dock + repair depot | transport | `district_cell` | OUTER [8, -1] | [1268, -1276, 1360, -1214] | 1 fl / 4 m / ent T1 | Props | F | 3 | prop | 5,000 |
| 27 | `TRN_BUS_SHELTERS` | Bus shelter & street furniture depot | transport | `district_cell` | OUTER [1, 8] | [-836.6, 1214, -615, 1360] | - | Props | F | 3 | prop | 5,000 |
| 28 | `UTL_GAS_DEPOT` | Gas regulator + storage depot | utilities | `district_cell` | OUTER [8, 0] | [1214, -1052.3, 1360, -914.5] | 1 fl / 7 m / sealed T3 | Props | E | 2 | regular | 20,000 |
| 29 | `UTL_SEWAGE` | Sewage pumping station | utilities | `district_cell` | OUTER [2, -1] | [-366, -1360, -241.8, -1279.7] | 1 fl / 8 m / sealed T3 | Props | E | 2 | regular | 20,000 |
| 30 | `UTL_SOLAR_FARM` | Solar array + battery yard | utilities | `district_cell` | OUTER [3, 8] | [-274.2, 1214, -155.4, 1360] | - | Props | E | 2 | regular | 20,000 |
| 31 | `UTL_SUBSTATION` | Power substation | utilities | `district_cell` | OUTER [8, 0] | [1214, -1214, 1360, -1070.2] | - | Props | E | 2 | prop | 5,000 |
| 32 | `UTL_TELECOM` | Telecom / radio mast | utilities | `district_cell` | OUTER [8, 8] | [1268, 1214, 1360, 1276] | 1 fl / 36 m / sealed T3 | Props | F | 3 | prop | 5,000 |
| 33 | `UTL_TRANSFORMER` | Neighbourhood transformer + fire water tank | utilities | `district_cell` | OUTER [-1, 8] | [-1360, 1214, -1268, 1276] | - | Props | F | 3 | prop | 5,000 |
| 34 | `UTL_WASTE` | Waste transfer + recycling centre | utilities | `district_cell` | OUTER [4, -1] | [45, -1360, 218.4, -1214] | 1 fl / 10 m / sealed T3 | Props | E | 2 | regular | 40,000 |
| 35 | `UTL_WATER_TOWER` | Water tower (30 m) | utilities | `district_cell` | OUTER [2, -1] | [-366, -1272.4, -258, -1214] | 1 fl / 30 m / sealed T3 | Props | E | 2 | prop | 5,000 |
| 36 | `UTL_WATER_TREATMENT` | Water treatment works | utilities | `district_cell` | OUTER [2, -1] | [-555, -1360, -382.2, -1214] | 1 fl / 6 m / sealed T3 | Props | E | 2 | regular | 40,000 |
| 37 | `LGT_STREET_LIGHTING` | Street lighting store & maintenance | lighting | `district_cell` | OUTER [7, -1] | [1128.7, -1360, 1214, -1214] | - | Lighting | F | 4 | prop | 5,000 |
| 38 | `TRK_FLOODLIGHT_A` | Floodlight mast cluster A | sports | `district_cell` | T [6, 1] | [680, -690, 720, -650] | - | Lighting | D | 3 | prop | 5,000 |
| 39 | `TRK_FLOODLIGHT_B` | Floodlight mast cluster B | sports | `district_cell` | T [7, 3] | [1010, -40, 1050, -18] | - | Lighting | D | 3 | prop | 5,000 |
| 40 | `TRK_SCORING_TOWER` | Scoring tower + big screen | sports | `district_cell` | T [7, 3] | [960, -300, 1000, -260] | - | Lighting | D | 3 | regular | 20,000 |
| 41 | `TRF_TRAFFIC_SIGNALS` | Traffic signal controller store | traffic | `district_cell` | OUTER [3, 8] | [-139.2, 1214, -15, 1360] | - | Traffic | F | 4 | prop | 5,000 |
| 42 | `DORMITORIES` | Student dormitories | education | `superlot` | R [3, 7] | [-288, 1056, -156, 1188] | 5 fl / 16 m / ent T5 | Residential | D | 5 | hero | 80,000 |
| 43 | `HOUSING_SENIOR` | Housing Senior (pocket-park infill) | residential | `district_cell` | R [7, 5] | [944, 368, 1040, 440] | 2 fl / 8 m / ent T2 | Residential | D | 5 | regular | 40,000 |
| 44 | `RES_APARTMENT_LOW` | Low apartment blocks | residential | `existing_parcels` | R [2, 2] | [-200, -588, -156, -544] | 5 fl / 16 m / sealed T3 | Residential | D | 5 | regular | 40,000 |
| 45 | `RES_APARTMENT_TOWER` | Apartment towers (Downtown) | residential | `existing_parcels` | D [4, 3] | [156, -288, 222, -222] | 29 fl / 92.8 m / ent T3 | Residential | D | 5 | regular | 40,000 |
| 46 | `RES_HOUSE_TERRACED` | Terraced / row houses (house) | residential | `existing_parcels` | R [2, 2] | [-444, -588, -411, -555] | 2 fl / 6 m / ent T3 | Residential | D | 5 | prop | 3,000 |
| 47 | `RES_HOUSE_VILLA` | Villas / large detached (house_large) | residential | `existing_parcels` | R [2, 2] | [-444, -555, -411, -522] | 3 fl / 9 m / sealed T3 | Residential | D | 5 | prop | 3,500 |
| 48 | `AMPHITHEATRE` | Park bandshell / amphitheatre | culture | `district_cell` | G [2, 1] | [-580, -670, -510, -620] | 1 fl / 5 m / ent T2 | SportsCivic | F | 9 | regular | 20,000 |
| 49 | `ARCADE_GAMES` | Amusement arcade | culture | `superlot` | E [6, 4] | [612, 12, 744, 144] | 2 fl / 8 m / ent T1 | SportsCivic | D | 6 | regular | 40,000 |
| 50 | `ARENA_INDOOR` | Indoor arena (basketball / concerts) | sports | `district_cell` | G [0, 2] | [-1164, -564, -936, -336] | 2 fl / 18 m / ent T1 | SportsCivic | D | 5 | hero | 150,000 |
| 51 | `CASINO` | Casino + entertainment | culture | `superlot` | E [4, 6] | [12, 612, 144, 744] | 4 fl / 16 m / ent T1 | SportsCivic | D | 7 | hero | 120,000 |
| 52 | `CHURCH` | Church (pocket-park infill) | culture | `district_cell` | R [3, 6] | [-284, 684, -212, 740] | 2 fl / 8 m / ent T2 | SportsCivic | D | 6 | regular | 40,000 |
| 53 | `CITY_HALL` | City hall (tier-1 hero) | civic | `existing_parcels` | D [4, 4] | [12, 222, 78, 288] | 4 fl / 12.8 m / ent T1 | SportsCivic | D | 5 | hero | 150,000 |
| 54 | `CIVIC_EMERGENCY_OPS` | Emergency operations centre + civil shelter | civic | `district_cell` | OUTER [7, 8] | [1109.2, 1214, 1214, 1360] | 2 fl / 14 m / ent T3 | SportsCivic | E | 8 | hero | 80,000 |
| 55 | `CIVIC_TOWN_OFFICES` | Civic / government offices | civic | `existing_parcels` | D [3, 5] | [-144, 312, -78, 378] | 6 fl / 19.2 m / ent T2 | SportsCivic | D | 5 | regular | 40,000 |
| 56 | `CLINIC_URGENT` | Clinic Urgent (pocket-park infill) | health | `district_cell` | R [2, 3] | [-440, -284, -364, -236] | 2 fl / 8 m / ent T2 | SportsCivic | D | 6 | regular | 40,000 |
| 57 | `COLLEGE_VOCATIONAL` | College Vocational (pocket-park infill) | education | `district_cell` | R [3, 6] | [-140, 820, -48, 884] | 4 fl / 16 m / ent T1 | SportsCivic | D | 6 | regular | 40,000 |
| 58 | `COMPLEX_SWIMMING` | Swimming + diving complex | sports | `district_cell` | G [4, 1] | [36, -864, 264, -636] | 2 fl / 12 m / ent T1 | SportsCivic | D | 5 | hero | 120,000 |
| 59 | `CONCERT_HALL` | Concert hall (symphonic) | culture | `superlot` | E [5, 3] | [312, -288, 444, -156] | 4 fl / 16 m / ent T1 | SportsCivic | D | 6 | hero | 150,000 |
| 60 | `COURTHOUSE` | Law courts + public square | civic | `superlot` | D [3, 5] | [-288, 312, -156, 444] | 4 fl / 12 m / ent T1 | SportsCivic | D | 6 | hero | 150,000 |
| 61 | `CUL_CINEMA` | Cinemas | culture | `existing_parcels` | E [3, 2] | [-288, -400, -244, -356] | 4 fl / 12.8 m / ent T1 | SportsCivic | D | 5 | regular | 40,000 |
| 62 | `CUL_CLUB` | Clubs / nightlife | culture | `existing_parcels` | E [3, 2] | [-288, -356, -244, -312] | 3 fl / 9.6 m / ent T3 | SportsCivic | D | 5 | regular | 20,000 |
| 63 | `EMBASSY` | Embassy / consulate compound | civic | `superlot` | R [1, 7] | [-888, 912, -756, 1044] | 3 fl / 12 m / ent T2 | SportsCivic | D | 7 | hero | 80,000 |
| 64 | `GALLERY_ART` | Art gallery | culture | `superlot` | E [2, 4] | [-588, 12, -456, 144] | 3 fl / 12 m / ent T1 | SportsCivic | D | 6 | hero | 120,000 |
| 65 | `GURUDWARA` | Gurudwara | culture | `district_cell` | G [3, 1] | [-68, -660, -16, -616] | 2 fl / 8 m / ent T2 | SportsCivic | F | 9 | regular | 20,000 |
| 66 | `HOSPITAL_MAIN` | Hospital Main (pocket-park infill) | health | `district_cell` | R [0, 4] | [-1040, 16, -936, 96] | 4 fl / 16 m / ent T1 | SportsCivic | D | 5 | hero | 120,000 |
| 67 | `LIBRARY_PUBLIC` | Library Public (pocket-park infill) | education | `district_cell` | R [2, 7] | [-540, 916, -460, 976] | 4 fl / 16 m / ent T1 | SportsCivic | D | 6 | regular | 40,000 |
| 68 | `MOSQUE` | Mosque (pocket-park infill) | culture | `district_cell` | R [2, 7] | [-440, 980, -364, 1040] | 2 fl / 8 m / ent T2 | SportsCivic | D | 6 | regular | 40,000 |
| 69 | `MUSEUM_CITY` | City museum | culture | `superlot` | D [4, 4] | [156, 12, 288, 144] | 4 fl / 16 m / ent T1 | SportsCivic | D | 6 | hero | 150,000 |
| 70 | `PLANETARIUM` | Planetarium + science centre | culture | `superlot` | D [4, 4] | [156, 156, 288, 288] | 3 fl / 14 m / ent T1 | SportsCivic | D | 6 | hero | 120,000 |
| 71 | `REC_GYM` | Gyms + fitness | sports | `existing_parcels` | E [3, 2] | [-200, -544, -156, -500] | 3 fl / 9.6 m / ent T1 | SportsCivic | D | 5 | regular | 20,000 |
| 72 | `SCHOOL_KINDER` | School Kinder (pocket-park infill) | education | `district_cell` | R [2, 2] | [-368, -440, -316, -404] | 2 fl / 8 m / ent T2 | SportsCivic | D | 6 | regular | 40,000 |
| 73 | `SCHOOL_PRIMARY` | School Primary (pocket-park infill) | education | `district_cell` | R [2, 6] | [-584, 760, -488, 828] | 2 fl / 8 m / ent T2 | SportsCivic | D | 6 | regular | 40,000 |
| 74 | `SCHOOL_SECONDARY` | School Secondary (pocket-park infill) | education | `district_cell` | R [2, 2] | [-584, -584, -488, -516] | 4 fl / 16 m / ent T1 | SportsCivic | D | 5 | regular | 40,000 |
| 75 | `SPORTS_FIELD_1` | Multi-use games area | sports | `district_cell` | G [0, 0] | [-1180, -990, -1070, -920] | 1 fl / 5 m / ent T2 | SportsCivic | F | 9 | regular | 20,000 |
| 76 | `SPORTS_FIELD_2` | Multi-use games area | sports | `district_cell` | G [3, 0] | [-280, -990, -170, -920] | 1 fl / 5 m / ent T2 | SportsCivic | F | 9 | regular | 20,000 |
| 77 | `SPT_ARCHERY_RANGE` | Archery + shooting range | sports | `district_cell` | OUTER [-1, 1] | [-1360, -836.6, -1214, -615] | - | SportsCivic | E | 8 | regular | 40,000 |
| 78 | `SPT_MOTOCROSS_PARK` | Motocross / dirt track | sports | `district_cell` | OUTER [3, -1] | [-225.6, -1360, -15, -1214] | - | SportsCivic | E | 8 | regular | 40,000 |
| 79 | `SPT_TENNIS_CENTRE` | Tennis centre (8 courts) | sports | `district_cell` | OUTER [8, 7] | [1214, 849.8, 1360, 1020.5] | 1 fl / 7 m / ent T2 | SportsCivic | E | 8 | regular | 40,000 |
| 80 | `SPT_VELODROME` | Velodrome (indoor 200 m track) | sports | `district_cell` | OUTER [8, 6] | [1214, 645, 1360, 832.8] | 1 fl / 12 m / ent T1 | SportsCivic | E | 8 | hero | 120,000 |
| 81 | `STADIUM_ATHLETICS` | Athletics / Olympic stadium (228x228) | sports | `district_cell` | G [0, 1] | [-1164, -864, -936, -636] | 3 fl / 15 m / ent T1 | SportsCivic | D | 5 | hero | 150,000 |
| 82 | `STADIUM_CRICKET` | Cricket stadium (open bowl, 228x228) | sports | `district_cell` | G [1, 0] | [-864, -1164, -636, -936] | 3 fl / 14 m / ent T1 | SportsCivic | D | 5 | hero | 150,000 |
| 83 | `STADIUM_FOOTBALL` | Football stadium with OPEN ROOF (228x228) | sports | `district_cell` | G [4, 0] | [36, -1164, 264, -936] | 3 fl / 16 m / ent T1 | SportsCivic | D | 5 | hero | 150,000 |
| 84 | `STATION_FIRE` | Station Fire (pocket-park infill) | civic | `district_cell` | R [0, 3] | [-1184, -140, -1108, -96] | 2 fl / 8 m / ent T2 | SportsCivic | D | 5 | regular | 40,000 |
| 85 | `STATION_POLICE` | Station Police (pocket-park infill) | civic | `district_cell` | R [0, 7] | [-1040, 916, -968, 960] | 2 fl / 8 m / ent T2 | SportsCivic | D | 5 | regular | 40,000 |
| 86 | `TEMPLE` | Temple | culture | `district_cell` | G [1, 1] | [-672, -884, -616, -840] | 2 fl / 8 m / ent T2 | SportsCivic | F | 9 | regular | 20,000 |
| 87 | `THEATRE` | Theatre / playhouse | culture | `superlot` | E [3, 3] | [-288, -288, -156, -156] | 3 fl / 12 m / ent T1 | SportsCivic | D | 6 | hero | 120,000 |
| 88 | `TRK_MEDICAL` | Track medical centre + ambulance bay | health | `district_cell` | T [6, 1] | [676, -894, 732, -700] | 2 fl / 8 m / ent T2 | SportsCivic | D | 7 | regular | 40,000 |
| 89 | `TRK_MOTORSPORT_MUSEUM` | Motorsport museum + hall of fame | culture | `district_cell` | T [6, 3] | [772, -398, 930, -174] | 1 fl / 16 m / ent T3 | SportsCivic | D | 7 | hero | 150,000 |
| 90 | `UNIVERSITY_FACULTY` | University: faculty blocks | education | `superlot` | R [3, 7] | [-144, 912, -12, 1044] | 4 fl / 16 m / ent T4 | SportsCivic | D | 7 | hero | 80,000 |
| 91 | `UNIVERSITY_MAIN` | University: main building + quad | education | `superlot` | R [3, 7] | [-288, 912, -156, 1044] | 4 fl / 16 m / ent T4 | SportsCivic | D | 7 | hero | 150,000 |
| 92 | `UTL_CREMATORIUM` | Crematorium + chapel | utilities | `district_cell` | OUTER [1, -1] | [-956.4, -1360, -806.7, -1214] | 1 fl / 8 m / ent T2 | SportsCivic | E | 8 | regular | 40,000 |
| 93 | `BANQUET_HALL` | Banquet / wedding hall | hospitality | `superlot` | E [6, 5] | [612, 312, 744, 444] | 2 fl / 10 m / ent T1 | Commercial | D | 10 | hero | 80,000 |
| 94 | `BREWERY` | Brewery + tap hall | work | `superlot` | I [5, 1] | [312, -744, 444, -612] | 4 fl / 16 m / ent T2 | Commercial | D | 10 | hero | 80,000 |
| 95 | `COLD_STORAGE` | Cold storage plant | work | `superlot` | I [5, 0] | [456, -1188, 588, -1056] | 4 fl / 12 m / ent T2 | Commercial | D | 10 | regular | 40,000 |
| 96 | `CONFERENCE_CENTRE` | Conference / exhibition centre | hospitality | `superlot` | D [5, 5] | [312, 456, 444, 588] | 3 fl / 12 m / ent T1 | Commercial | D | 10 | hero | 120,000 |
| 97 | `DEPARTMENT_STORE` | Department store | retail | `superlot` | D [3, 4] | [-144, 156, -12, 288] | 5 fl / 16 m / ent T1 | Commercial | D | 10 | hero | 120,000 |
| 98 | `FIN_BANK` | Banks (branches) | retail | `existing_parcels` | D [4, 3] | [222, -288, 288, -222] | 8 fl / 25.6 m / ent T1 | Commercial | D | 9 | regular | 15,000 |
| 99 | `HOSTEL` | Hostel / budget lodging | hospitality | `superlot` | R [1, 5] | [-888, 312, -756, 444] | 3 fl / 10 m / ent T2 | Commercial | D | 10 | regular | 40,000 |
| 100 | `HOT_AIRPORT_HOTEL` | Airport hotel | hospitality | `district_cell` | OUTER [5, -1] | [427.5, -1360, 555, -1214] | 1 fl / 24 m / ent T6 | Commercial | D | 10 | hero | 150,000 |
| 101 | `HOT_HOTEL` | Hotels | hospitality | `existing_parcels` | E [3, 2] | [78, -222, 144, -156] | 25 fl / 80 m / ent T1 | Commercial | D | 10 | hero | 150,000 |
| 102 | `HOT_MOTEL` | Motel (surface parking at door) | hospitality | `district_cell` | OUTER [6, -1] | [775.9, -1360, 940.9, -1214] | 2 fl / 8 m / ent T2 | Commercial | E | 11 | hero | 80,000 |
| 103 | `ICON_TOWER` | Icon supertall tower (mixed office + hotel + observatory) | work | `district_cell` | OUTER [4, 8] | [45, 1214, 198, 1360] | 1 fl / 180 m / ent T45 | Commercial | D | 10 | hero | 150,000 |
| 104 | `IND_FACTORY` | Factories | work | `existing_parcels` | I [5, 0] | [312, -1122, 378, -1056] | 3 fl / 9.6 m / sealed T3 | Commercial | D | 10 | regular | 40,000 |
| 105 | `IND_WAREHOUSE` | Warehouses | work | `existing_parcels` | I [5, 0] | [312, -1188, 378, -1122] | 2 fl / 6.4 m / sealed T3 | Commercial | D | 9 | regular | 30,000 |
| 106 | `MED_BROADCAST` | TV broadcast centre | media | `district_cell` | OUTER [7, 8] | [842, 1214, 962.5, 1360] | 3 fl / 14 m / ent T2 | Commercial | E | 11 | hero | 80,000 |
| 107 | `MED_FILM_STUDIO` | Film studio sound stages | media | `district_cell` | OUTER [6, 8] | [690, 1214, 826.2, 1360] | 1 fl / 14 m / sealed T3 | Commercial | E | 11 | hero | 80,000 |
| 108 | `OFFICE_COWORKING` | Co-working / serviced office | work | `superlot` | D [4, 5] | [156, 456, 288, 588] | 8 fl / 25.6 m / ent T1 | Commercial | D | 10 | regular | 40,000 |
| 109 | `OFF_MIDRISE` | Mid-rise offices (<=20 fl) | work | `existing_parcels` | D [4, 3] | [12, -288, 78, -222] | 20 fl / 64 m / ent T2 | Commercial | D | 9 | regular | 40,000 |
| 110 | `OFF_TOWER` | Office towers + skyscrapers | work | `existing_parcels` | D [4, 3] | [12, -288, 78, -222] | 60 fl / 192 m / ent T1 | Commercial | D | 9 | hero | 150,000 |
| 111 | `REC_FARMERS_MARKET` | Weekend farmers market yard | retail | `district_cell` | OUTER [-1, 5] | [-1360, 356.1, -1214, 555] | 2 fl / 7 m / ent T1 | Commercial | E | 11 | regular | 40,000 |
| 112 | `RES_SHOPHOUSE` | Shop-houses (house_above_shop) | mixed_use | `existing_parcels` | M [5, 6] | [312, 644.7, 328.3, 660.9] | 4 fl / 12.8 m / sealed T3 | Commercial | D | 9 | regular | 6,000 |
| 113 | `RET_BAZAAR` | Covered bazaar hall | retail | `existing_parcels` | M [6, 6] | [682.3, 682.3, 747.5, 747.5] | 2 fl / 12 m / ent T1 | Commercial | D | 9 | hero | 150,000 |
| 114 | `RET_CAFE` | Cafes | retail | `existing_parcels` | E [3, 2] | [-244, -588, -200, -544] | 2 fl / 6.4 m / sealed T3 | Commercial | D | 9 | prop | 5,000 |
| 115 | `RET_CORNER_SHOP` | Corner shops | retail | `existing_parcels` | R [0, 3] | [-945, -189, -912, -156] | 2 fl / 6.4 m / ent T3 | Commercial | D | 9 | prop | 4,000 |
| 116 | `RET_MALL` | Shopping malls | retail | `existing_parcels` | D [4, 3] | [78, -288, 144, -222] | 5 fl / 16 m / ent T1 | Commercial | D | 9 | hero | 150,000 |
| 117 | `RET_MOTOR_TRADE` | Car showroom + service | retail | `district_cell` | OUTER [5, 8] | [396.9, 1214, 555, 1360] | 2 fl / 9 m / ent T2 | Commercial | D | 10 | regular | 40,000 |
| 118 | `RET_RESTAURANT` | Restaurants | retail | `existing_parcels` | E [3, 2] | [-56, -544, -12, -500] | 2 fl / 6.4 m / ent T2 | Commercial | D | 9 | regular | 8,000 |
| 119 | `RET_SHOPS` | High-street shops | retail | `existing_parcels` | E [3, 2] | [-288, -500, -244, -456] | 3 fl / 9.6 m / ent T2 | Commercial | D | 9 | regular | 6,000 |
| 120 | `RET_SUPERMARKET` | Supermarket / grocery mart | retail | `existing_parcels` | E [4, 2] | [56, -500, 100, -456] | 2 fl / 6.4 m / ent T1 | Commercial | D | 9 | regular | 40,000 |
| 121 | `RET_TEAHOUSE` | Teahouses (market) | retail | `existing_parcels` | M [5, 6] | [361, 644.7, 377.2, 660.9] | 3 fl / 9.6 m / sealed T3 | Commercial | D | 9 | prop | 5,000 |
| 122 | `RET_WHOLESALER` | Wholesale cash-and-carry mart | retail | `district_cell` | OUTER [5, -1] | [233.7, -1360, 412.2, -1214] | 1 fl / 12 m / ent T2 | Commercial | E | 11 | hero | 80,000 |
| 123 | `RET_WORKSHOP_STALL` | Small market workshops | work | `existing_parcels` | M [5, 6] | [344.7, 661, 360.9, 677.2] | 2 fl / 6.4 m / ent T3 | Commercial | D | 9 | prop | 4,000 |
| 124 | `TRK_FAN_ZONE` | Fan zone + spectator amenities | recreation | `district_cell` | T [6, 1] | [780, -846, 924, -718] | 2 fl / 6 m / ent T1 | Commercial | E | 11 | regular | 40,000 |
| 125 | `TRK_FOOD_COURT` | Track food court + beergarden | hospitality | `district_cell` | OUTER [8, 3] | [1214, -312, 1360, -166.2] | 2 fl / 6 m / ent T1 | Commercial | E | 11 | regular | 40,000 |
| 126 | `TRK_MERCH_HALL` | Merchandise hall + paddock club | retail | `district_cell` | OUTER [8, 3] | [1214, -150, 1360, -15] | 2 fl / 7 m / ent T1 | Commercial | E | 11 | regular | 40,000 |
| 127 | `TRK_SPECTATOR_VILLAGE` | Circuit spectator village | hospitality | `district_cell` | OUTER [8, 1] | [1214, -896.5, 1360, -758.8] | 2 fl / 10 m / ent T2 | Commercial | E | 11 | hero | 80,000 |
| 128 | `WORKSHOP_FABRICATION` | Metal fabrication works | work | `superlot` | I [5, 2] | [312, -444, 444, -312] | 4 fl / 16 m / ent T1 | Commercial | D | 10 | regular | 40,000 |
| 129 | `WRK_CONSTRUCTION_YARD` | Contractor laydown yard | work | `district_cell` | OUTER [1, -1] | [-788.7, -1360, -615, -1214] | - | Commercial | F | 12 | regular | 20,000 |
| 130 | `WRK_DATA_CENTRE` | Data centre | work | `district_cell` | OUTER [8, 2] | [1214, -555, 1360, -328.2] | 1 fl / 10 m / sealed T3 | Commercial | E | 11 | hero | 80,000 |
| 131 | `WRK_LOGISTICS_HUB` | Logistics / fulfilment hub | work | `district_cell` | OUTER [7, 8] | [978.2, 1214, 1093.5, 1360] | 3 fl / 14 m / ent T2 | Commercial | E | 11 | hero | 80,000 |
| 132 | `WRK_TECH_PARK` | Tech park / office campus | work | `district_cell` | OUTER [2, 8] | [-555, 1214, -430.8, 1360] | 4 fl / 16 m / ent T2 | Commercial | D | 10 | hero | 80,000 |
| 133 | `CARPARK_MULTISTOREY` | Multi-storey car park | transport | `superlot` | D [5, 4] | [456, 156, 588, 288] | 6 fl / 21 m / sealed T0 | Transport | D | 12 | regular | 40,000 |
| 134 | `IND_DEPOT` | Depots | work | `existing_parcels` | I [5, 0] | [378, -978, 444, -912] | 2 fl / 6.4 m / sealed T3 | Transport | D | 12 | regular | 20,000 |
| 135 | `METRO_ENT_1` | Metro entrance 1 (stairs + lift + vent) | metro | `district_cell` | R [0, 3] | [-1078, -34, -1062, -18] | 1 fl / 5 m / ent T2 | Transport | D | 12 | regular | 20,000 |
| 136 | `METRO_ENT_2` | Metro entrance 2 (stairs + lift + vent) | metro | `district_cell` | R [0, 4] | [-934, 122, -918, 138] | 1 fl / 5 m / ent T2 | Transport | D | 12 | regular | 20,000 |
| 137 | `METRO_ENT_3` | Metro entrance 3 (stairs + lift + vent) | metro | `district_cell` | R [0, 7] | [-934, 1022, -918, 1038] | 1 fl / 5 m / ent T2 | Transport | D | 13 | regular | 20,000 |
| 138 | `METRO_ENT_4` | Metro entrance 4 (stairs + lift + vent) | metro | `district_cell` | R [2, 2] | [-478, -478, -462, -462] | 1 fl / 5 m / ent T2 | Transport | D | 13 | regular | 20,000 |
| 139 | `METRO_ENT_5` | Metro entrance 5 (stairs + lift + vent) | metro | `district_cell` | R [7, 5] | [918, 318, 934, 334] | 1 fl / 5 m / ent T2 | Transport | D | 13 | regular | 20,000 |
| 140 | `TRK_GATE_E` | East gate: ticketing + search lanes | transport | `district_cell` | OUTER [8, 5] | [1214, 519.3, 1360, 555] | 2 fl / 6 m / ent T1 | Transport | E | 14 | regular | 20,000 |
| 141 | `TRK_PARKING_E1` | Circuit parking (east 1) | transport | `district_cell` | OUTER [8, 5] | [1214, 305.1, 1360, 422.4] | - | Transport | F | 15 | prop | 5,000 |
| 142 | `TRK_PARKING_E2` | Circuit parking (east 2) | transport | `district_cell` | OUTER [8, 5] | [1214, 437.7, 1360, 504] | - | Transport | F | 15 | prop | 5,000 |
| 143 | `TRK_PARKING_E3` | Circuit parking (east 3) | transport | `district_cell` | OUTER [8, 7] | [1214, 1151.4, 1360, 1214] | - | Transport | F | 15 | prop | 5,000 |
| 144 | `TRK_TRANSPORT_HUB` | Circuit transport hub (bus + tram stop) | transport | `district_cell` | OUTER [8, 7] | [1214, 1037.6, 1360, 1134.3] | 2 fl / 7 m / ent T1 | Transport | D | 12 | regular | 40,000 |
| 145 | `TRN_AIR_CARGO` | Air cargo terminal | transport | `district_cell` | OUTER [7, -1] | [1040, -1456, 1300, -1426] | 1 fl / 9 m / sealed T3 | Transport | E | 14 | regular | 40,000 |
| 146 | `TRN_AIR_FIRE` | Airport fire station | transport | `district_cell` | OUTER [7, -1] | [880, -1456, 1020, -1426] | 1 fl / 8 m / sealed T3 | Transport | E | 14 | regular | 40,000 |
| 147 | `TRN_AIR_HANGARS` | Aircraft hangars | transport | `district_cell` | OUTER [6, -1] | [500, -1456, 860, -1426] | 1 fl / 12 m / sealed T3 | Transport | E | 14 | hero | 80,000 |
| 148 | `TRN_AIR_PARKING` | Airport car park | transport | `district_cell` | OUTER [8, -1] | [1424, -1400, 1496, -1080] | - | Transport | F | 15 | prop | 5,000 |
| 149 | `TRN_AIR_TERMINAL` | Airport terminal (open frontage) | transport | `district_cell` | OUTER [4, -1] | [-256, -1456, 440, -1426] | 2 fl / 8 m / ent T1 | Transport | D | 12 | hero | 150,000 |
| 150 | `TRN_AIR_TOWER` | Airport control tower | transport | `district_cell` | OUTER [5, -1] | [460, -1456, 484, -1432] | 1 fl / 26 m / ent T2 | Transport | D | 12 | regular | 40,000 |
| 151 | `TRN_APRON` | Airport apron + aircraft stands | transport | `district_cell` | OUTER [5, -1] | [-256, -1494, 900, -1456] | - | Transport | F | 15 | prop | 5,000 |
| 152 | `TRN_BUS_DEPOT` | Bus depot + washing bay | transport | `district_cell` | OUTER [0, 8] | [-1214, 1214, -1046.3, 1360] | 1 fl / 9 m / ent T2 | Transport | D | 12 | regular | 40,000 |
| 153 | `TRN_COACH_TERMINAL` | Coach / intercity terminal | transport | `district_cell` | OUTER [4, 8] | [213.3, 1214, 381.6, 1360] | 2 fl / 10 m / ent T1 | Transport | D | 12 | hero | 80,000 |
| 154 | `TRN_MAIL_SORTING` | Mail sorting centre (post office back-of-house) | civic | `district_cell` | OUTER [0, 8] | [-1028.3, 1214, -854.6, 1360] | 2 fl / 9 m / sealed T3 | Transport | D | 12 | regular | 40,000 |
| 155 | `TRN_PARK_AND_RIDE` | Park-and-ride car park | transport | `district_cell` | OUTER [2, 8] | [-414.6, 1214, -290.4, 1360] | - | Transport | F | 15 | prop | 5,000 |
| 156 | `TRN_PETROL_EV` | Petrol station + EV charging hub | transport | `district_cell` | OUTER [6, -1] | [645, -1360, 758.8, -1214] | 1 fl / 6 m / ent T2 | Transport | F | 15 | regular | 40,000 |
| 157 | `TRN_RAIL_LINE` | Belt railway (4 tracks, surface) | transport | `district_cell` | OUTER [4, 8] | [-1420, 1440, 1420, 1460] | - | Transport | D | 12 | regular | 40,000 |
| 158 | `TRN_RAIL_PLATFORMS` | Rail platforms (2 island, 400 m) | transport | `district_cell` | OUTER [3, 8] | [-420, 1460, 280, 1474] | - | Transport | D | 12 | regular | 20,000 |
| 159 | `TRN_RAIL_STATION` | Railway station concourse | transport | `district_cell` | OUTER [3, 8] | [-420, 1474, 280, 1496] | 2 fl / 12 m / ent T1 | Transport | D | 12 | hero | 150,000 |
| 160 | `TRN_RUNWAY` | Airport runway 1200x38 m (STOL-capable strip) | transport | `district_cell` | OUTER [1, -1] | [-1480, -1494, -284, -1456] | - | Transport | D | 12 | prop | 5,000 |
| 161 | `TRN_STREET_DEPOT` | Street maintenance depot | transport | `district_cell` | OUTER [-1, 7] | [-1360, 1014.9, -1214, 1214] | - | Transport | E | 14 | regular | 40,000 |
| 162 | `TRN_TAXIWAY` | Airport taxiway link | transport | `district_cell` | OUTER [3, -1] | [-284, -1494, -256, -1456] | - | Transport | F | 15 | prop | 5,000 |
| 163 | `TRN_TRUCK_STOP` | Truck stop + freight consolidation | transport | `district_cell` | OUTER [7, -1] | [958, -1360, 1111.6, -1214] | 1 fl / 9 m / sealed T3 | Transport | E | 14 | regular | 40,000 |
| 164 | `TRACK_CIRCUIT` | Race circuit (3388.88 m) | sports | `existing_parcels` | T [7, 2] | [612, -1188, 1188, -12] | - | Track | D | 15 | regular | 40,000 |
| 165 | `TRACK_GRANDSTAND` | Grandstands (main + hairpin) | sports | `existing_parcels` | T [7, 2] | [636.4, -858.7, 1187.6, -247.2] | 4 fl / 12.8 m / sealed T3 | Track | D | 15 | hero | 150,000 |
| 166 | `TRACK_PADDOCK` | Paddock | sports | `existing_parcels` | T [6, 1] | [772.4, -717.6, 818.4, -647.6] | 1 fl / 3.2 m / ent T3 | Track | D | 15 | regular | 20,000 |
| 167 | `TRACK_PARKING` | Circuit car parks | sports | `existing_parcels` | T [7, 1] | [1068, -1180, 1180, -24] | - | Track | F | 17 | prop | 5,000 |
| 168 | `TRACK_PIT` | Pit building + 14 open garages | sports | `existing_parcels` | T [6, 2] | [738.4, -894, 768.4, -306] | 2 fl / 6.4 m / ent T2 | Track | D | 15 | regular | 40,000 |
| 169 | `TRACK_TOWER` | Circuit control tower | sports | `existing_parcels` | T [6, 1] | [772.4, -635.2, 788.4, -619.3] | 5 fl / 16 m / ent T2 | Track | D | 15 | regular | 20,000 |
| 170 | `TRK_GRANDSTAND_E2` | Extra grandstand (west straight, outside loop) | sports | `district_cell` | T [6, 2] | [612, -400, 662, -250] | 2 fl / 12 m / ent T3 | Track | D | 15 | regular | 40,000 |
| 171 | `TRK_GRANDSTAND_N` | Extra grandstand (north edge) | sports | `district_cell` | T [6, 3] | [750, -42, 1000, -16] | 2 fl / 10 m / ent T3 | Track | D | 15 | regular | 40,000 |
| 172 | `TRK_KARTING` | Karting circuit | sports | `district_cell` | T [7, 1] | [932, -934, 1124, -670] | - | Track | E | 16 | regular | 40,000 |
| 173 | `TRK_PADDOCK_ANNEX` | Paddock annexe (trucks, generators) | work | `district_cell` | T [6, 0] | [716, -1142, 828, -894] | - | Track | E | 16 | regular | 20,000 |
| 174 | `TRK_SKID_PAD` | Skid pad + wet handling area | sports | `district_cell` | T [7, 3] | [1010, -360, 1120, -200] | - | Track | E | 16 | regular | 20,000 |
| 175 | `TRK_START_GANTRY` | Start/finish gantry + pit wall | sports | `district_cell` | T [6, 2] | [772, -566, 940, -526] | - | Track | D | 15 | regular | 20,000 |
| 176 | `TRK_WORKSHOP` | Track workshop + tyre & fuel store | work | `district_cell` | T [6, 2] | [676, -640, 732, -190] | 3 fl / 7 m / ent T1 | Track | E | 16 | regular | 40,000 |
| 177 | `INT_HERO_INTERIORS` | Hero interiors: 39 tier-1 buildings (lobby, stair, 1 furnished floor each) | interiors | `existing_parcels` | R [2, 2] | [12, -144, 78, -78] | 1 fl / 3.2 m / ent T1 | Interiors | E | 17 | regular | 40,000 |
| 178 | `INT_MALL_FITOUT` | Shopping mall fit-out (atrium, escalators, shop fronts) | interiors | `existing_parcels` | D [4, 3] | [78, -288, 144, -222] | 1 fl / 3.2 m / ent T1 | Interiors | E | 17 | regular | 40,000 |
| 179 | `INT_SHELL_INTERIORS` | Shell interiors: tier-2 enterable buildings (one furnished room + shell) | interiors | `existing_parcels` | I [5, 0] | [456, -1188, 522, -1122] | 1 fl / 3.2 m / ent T1 | Interiors | F | 18 | regular | 40,000 |

### 10.1 Facility notes (placement intent)

- `AMPHITHEATRE`: shell stage 14 m, terraced grass seating, back-of-house block (park PK_2_1 keeps its south-east corner for the bandstand) | sited in the free corner of park PK_2_1, keeping >70% of the green open
- `ARCADE_GAMES`: MERGE of 9 contiguous parcels in sub-block (0, 0) of cell [6,4] - those 9 buildings are NOT built
- `ARENA_INDOOR`: converts park PK_0_2; clear-span roof, 8000 seats, open archway concourse (no doors)
- `BANDSTAND`: corner infill inside park PK_2_1, >85% of the park stays open
- `BANQUET_HALL`: MERGE of 9 contiguous parcels in sub-block (0, 0) of cell [6,5] - those 9 buildings are NOT built
- `BOATHOUSE_PIER`: corner infill inside park PK_2_0, >85% of the park stays open
- `BREWERY`: MERGE of 4 contiguous parcels in sub-block (0, 1) of cell [5,1] - those 4 buildings are NOT built
- `CARPARK_MULTISTOREY`: MERGE of 4 contiguous parcels in sub-block (1, 1) of cell [5,4] - those 4 buildings are NOT built
- `CASINO`: MERGE of 9 contiguous parcels in sub-block (0, 0) of cell [4,6] - those 9 buildings are NOT built
- `CHURCH`: infill on pocket park PK_3_6_0_0: footprint 72x56 m, the rest of the 132x132 park stays green (soft conflict)
- `CITY_HALL`: the only tier-1 civic parcel, 4 floors, faces the central plaza
- `CIVIC_EMERGENCY_OPS`: 280x163 m: hardened control floor, generator yard, radio mast, muster court | zone slot CIVIC_EMERGENCY_OPS frac (0.8, 0, 1, 1) of the N4 band zone
- `CIVIC_TOWN_OFFICES`: 4 x 66x66 m, 3-6 floors, enterable [rect = single_parcel, 4 parcels, set is scattered]
- `CLINIC_URGENT`: infill on pocket park PK_2_3_1_0: footprint 76x48 m, the rest of the 132x132 park stays green (soft conflict)
- `COLD_STORAGE`: MERGE of 4 contiguous parcels in sub-block (1, 0) of cell [5,0] - those 4 buildings are NOT built
- `COLLEGE_VOCATIONAL`: infill on pocket park PK_3_6_1_1: footprint 92x64 m, the rest of the 132x132 park stays green (soft conflict)
- `COMPLEX_SWIMMING`: converts park PK_4_1; 50 m pool hall + dive pool + outdoor learner pool, glazed north facade
- `CONCERT_HALL`: MERGE of 9 contiguous parcels in sub-block (0, 0) of cell [5,3] - those 9 buildings are NOT built
- `CONFERENCE_CENTRE`: MERGE of 4 contiguous parcels in sub-block (0, 1) of cell [5,5] - those 4 buildings are NOT built
- `COURTHOUSE`: MERGE of 4 contiguous parcels in sub-block (0, 0) of cell [3,5] - those 4 buildings are NOT built
- `CUL_CINEMA`: 11 x 44x44 m, 2-4 floors, all enterable [rect = single_parcel, 11 parcels, set is scattered]
- `CUL_CLUB`: 15 x 44x44 m, 2-3 floors, all enterable [rect = single_parcel, 15 parcels, set is scattered]
- `DEPARTMENT_STORE`: MERGE of 4 contiguous parcels in sub-block (1, 1) of cell [3,4] - those 4 buildings are NOT built
- `DORMITORIES`: MERGE of 13 contiguous parcels in sub-block (0, 1) of cell [3,7] - those 13 buildings are NOT built
- `EMBASSY`: MERGE of 13 contiguous parcels in sub-block (0, 0) of cell [1,7] - those 13 buildings are NOT built
- `FIN_BANK`: 11 x 66x66 m in D, all enterable; ATM kiosks = Props [rect = single_parcel, 11 parcels, set is scattered]
- `GALLERY_ART`: MERGE of 9 contiguous parcels in sub-block (0, 0) of cell [2,4] - those 9 buildings are NOT built
- `GARDEN_ZEN`: corner infill inside park PK_1_2, >85% of the park stays open
- `GURUDWARA`: corner infill inside park PK_3_1, >85% of the park stays open
- `HOSPITAL_MAIN`: infill on pocket park PK_0_4_1_0: footprint 104x80 m, the rest of the 132x132 park stays green (soft conflict)
- `HOSTEL`: MERGE of 13 contiguous parcels in sub-block (0, 0) of cell [1,5] - those 13 buildings are NOT built
- `HOT_AIRPORT_HOTEL`: 560x163 m: 240-room L block with sky link to the terminal side, pool deck, conference floor | zone slot HOT_AIRPORT_HOTEL frac (0.75, 0, 1, 1) of the S3 band zone
- `HOT_HOTEL`: 37 (17 D + 20 E), 6-25 floors, all enterable, 5 tier-1 [rect = single_parcel, 37 parcels, set is scattered]
- `HOT_MOTEL`: L-shaped 40-room motel, direct parking, open walkway (no doors) - highway-facing | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot HOT_MOTEL frac (0.23, 0, 0.52, 1) of the S4 band zone
- `HOUSING_SENIOR`: infill on pocket park PK_7_5_0_0: footprint 96x72 m, the rest of the 132x132 park stays green (soft conflict)
- `ICON_TOWER`: HERO: 150x163 m podium + 45-floor shaft (180 m), sky lobby at 150 m, crown beacon; stands on the north band so it reads on the skyline behind the grid | zone slot ICON_TOWER frac (0, 0, 0.3, 1) of the N3 band zone
- `IND_DEPOT`: 3 x 66x66 m [rect = single_parcel, 3 parcels, set is scattered]
- `IND_FACTORY`: 15 x 66x66 m in I, 7 enterable [rect = single_parcel, 15 parcels, set is scattered]
- `IND_WAREHOUSE`: 23 x 66x66 m in I, 4 enterable [rect = single_parcel, 23 parcels, set is scattered]
- `IND_YARD`: 7 x 66x66 m open ground - good base for scrap / fuel / storage [rect = single_parcel, 7 parcels, set is scattered]
- `INT_HERO_INTERIORS`: city hall, landmark tower, bazaar, malls, hotels, banks, gyms - full tier-1 fit-out | separate build pass over ALREADY-PLACED buildings (no new footprint); rect = single_parcel of the 39-parcel set (the pass runs on every parcel in gap.parcel_ids)
- `INT_MALL_FITOUT`: 8 malls, 66x66 m, 3-5 floors; food court + escalator banks + shopfront run | separate build pass over ALREADY-PLACED buildings (no new footprint); rect = single_parcel of the 8-parcel set (the pass runs on every parcel in gap.parcel_ids)
- `INT_SHELL_INTERIORS`: first 120 of 518 tier-2 parcels; the rest reuse the same shell asset | separate build pass over ALREADY-PLACED buildings (no new footprint); rect = single_parcel of the 120-parcel set (the pass runs on every parcel in gap.parcel_ids)
- `LGT_STREET_LIGHTING`: 280x163 m depot for columns/luminaire spares; the lighting system itself is instanced city-wide | zone slot LGT_STREET_LIGHTING frac (0.85, 0, 1, 1) of the S4 band zone
- `LIBRARY_PUBLIC`: infill on pocket park PK_2_7_0_0: footprint 80x60 m, the rest of the 132x132 park stays green (soft conflict)
- `MED_BROADCAST`: studio + gallery + offices + roof antenna mast 40 m | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot MED_BROADCAST frac (0.29, 0, 0.52, 1) of the N4 band zone
- `MED_FILM_STUDIO`: 2 windowless stages 120x80 m + backlot; no doors, roller-shutter openings | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot MED_FILM_STUDIO frac (0, 0, 0.26, 1) of the N4 band zone
- `METRO_ENT_1`: 20x20 m entrance pavilion in the free corner of pocket park PK_0_3_0_1 (opposite the civic infill); the rest of the park stays green (soft conflict)
- `METRO_ENT_2`: 20x20 m entrance pavilion in the free corner of pocket park PK_0_4_1_0 (opposite the civic infill); the rest of the park stays green (soft conflict)
- `METRO_ENT_3`: 20x20 m entrance pavilion in the free corner of pocket park PK_0_7_1_0 (opposite the civic infill); the rest of the park stays green (soft conflict)
- `METRO_ENT_4`: 20x20 m entrance pavilion in the free corner of pocket park PK_2_2_0_0 (opposite the civic infill); the rest of the park stays green (soft conflict)
- `METRO_ENT_5`: 20x20 m entrance pavilion in the free corner of pocket park PK_7_5_0_0 (opposite the civic infill); the rest of the park stays green (soft conflict)
- `MKT_COURTYARD`: 95 open-air covered courtyards, already built [rect = single_parcel, 95 parcels, set is scattered]
- `MOSQUE`: infill on pocket park PK_2_7_1_0: footprint 76x60 m, the rest of the 132x132 park stays green (soft conflict)
- `MUSEUM_CITY`: MERGE of 4 contiguous parcels in sub-block (1, 0) of cell [4,4] - those 4 buildings are NOT built
- `OFFICE_COWORKING`: MERGE of 4 contiguous parcels in sub-block (1, 1) of cell [4,5] - those 4 buildings are NOT built
- `OFF_MIDRISE`: subset of OFF_TOWER: 12-20 floors [rect = single_parcel, 17 parcels, set is scattered]
- `OFF_TOWER`: 55 x 66x66 m, 12-60 floors (LM_LANDMARK_TOWER = 60 fl, B_4_3_0_1_0_0) [rect = single_parcel, 55 parcels, set is scattered]
- `PARK_DOG`: corner infill inside park PK_3_0, >85% of the park stays open
- `PARK_MAIN`: 13 x 276x276 m G cells; 5 of them are converted to stadiums - see conflicts [rect = single_parcel, 13 parcels, set is scattered]
- `PARK_POCKET`: 12 x 132x132 m in R cells; all 12 receive a small civic infill building [rect = single_parcel, 12 parcels, set is scattered]
- `PLANETARIUM`: MERGE of 4 contiguous parcels in sub-block (1, 1) of cell [4,4] - those 4 buildings are NOT built
- `PLAYGROUND_1`: swings, slide tower, spring riders, rubber surfacing, shade sail, fence | sited in the free corner of park PK_1_1, keeping >70% of the green open
- `PLAYGROUND_2`: climbing frame, zip line, basket swing, inclusive roundabout | sited in the free corner of park PK_3_1, keeping >70% of the green open
- `PLAYGROUND_3`: play trail + sand pit + toddler zone, shade sail | sited in the free corner of park PK_4_7, keeping >70% of the green open
- `PLAZA_CENTRAL`: 132x132, fountain + event stage + kiosks; LM_CENTRAL_PLAZA
- `REC_AMUSEMENT`: 162x510 m: ferris wheel 55 m, coaster, carousel, bumper cars, drop tower, ticket gate, food stalls | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot REC_AMUSEMENT frac (0, 0, 1, 0.58) of the W3 band zone
- `REC_BOTANICAL`: 162x540 m: glasshouse 60x30 m, formal beds, palm walk, nursery, cafe with open front | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot REC_BOTANICAL frac (0, 0, 1, 0.62) of the W2 band zone
- `REC_FARMERS_MARKET`: 163x540 m: 40 stall pads, canopy frame, vendor parking, produce hall (open front) | zone slot REC_FARMERS_MARKET frac (0, 0.61, 1, 1) of the W3 band zone
- `REC_GOLF_RANGE`: 162x620 m: 24 covered bays, 220 m fairway, net mast 18 m, putting green | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot REC_GOLF_RANGE frac (0, 0, 1, 0.62) of the W4 band zone
- `REC_GYM`: 26 x 44x44 m, all enterable, 4 tier-1 [rect = single_parcel, 26 parcels, set is scattered]
- `REC_URBAN_FARM`: 163x550 m: 120 allotment plots, tool sheds, polytunnels, compost bays | zone slot REC_URBAN_FARM frac (0, 0.65, 1, 1) of the W2 band zone
- `REC_WATER_PARK`: wave pool 40x60, 4 slide tower, lazy river, splash pad, changing block with open arches | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot REC_WATER_PARK frac (0, 0, 1, 0.48) of the E3 band zone
- `REC_ZOO`: 162x650 m: 8 enclosures, aviary, reptile house, keeper buildings, entry gate - replaces no parcel (belt is unplanned) | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot REC_ZOO frac (0, 0, 1, 0.6) of the W1 band zone
- `RESTROOM_PARK`: corner infill inside park PK_0_0, >85% of the park stays open
- `RES_APARTMENT_LOW`: 170 lots, 3-5 floors; also serves social housing + senior living shells [rect = single_parcel, 170 parcels, set is scattered]
- `RES_APARTMENT_TOWER`: 12 lots, 15-29 floors [rect = single_parcel, 12 parcels, set is scattered]
- `RES_COURTYARD_EM`:  [rect = single_parcel, 32 parcels, set is scattered]
- `RES_COURTYARD_HOMES`: 64 open-air courtyards, no facade [rect = single_parcel, 64 parcels, set is scattered]
- `RES_HOUSE_TERRACED`: 484 lots, 1-2 floors, 33x33 m lots [rect = single_parcel, 484 parcels, set is scattered]
- `RES_HOUSE_VILLA`: 128 lots, 2-3 floors; doubles as 'mansion' variant [rect = single_parcel, 128 parcels, set is scattered]
- `RES_SHOPHOUSE`: 352 lots in M, 2-4 floors, ground floor retail + dwelling [rect = single_parcel, 352 parcels, set is scattered]
- `RET_BAZAAR`: built in out/market.blend; LM_BAZAAR landmark
- `RET_CAFE`:  [rect = single_parcel, 35 parcels, set is scattered]
- `RET_CORNER_SHOP`:  [rect = single_parcel, 9 parcels, set is scattered]
- `RET_MALL`: 8 x 66x66 m, 3-5 floors; B_4_4_1_1_1_1 is the tier-1 hero [rect = single_parcel, 8 parcels, set is scattered]
- `RET_MOTOR_TRADE`: glass showroom + 2-bay workshop + forecourt | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot RET_MOTOR_TRADE frac (0.69, 0, 1, 1) of the N3 band zone
- `RET_RESTAURANT`: 197 lots (136 M + 61 E), 127 enterable [rect = single_parcel, 197 parcels, set is scattered]
- `RET_SHOPS`: 508 lots (453 M + 55 E), 16-44 m; assign pharmacy/bookstore/electronics/clothes signage variants here [rect = single_parcel, 508 parcels, set is scattered]
- `RET_SUPERMARKET`: 10 x 44x44 m, 1-2 floors, all enterable [rect = single_parcel, 10 parcels, set is scattered]
- `RET_TEAHOUSE`: 89 lots, 16 m, 40 enterable [rect = single_parcel, 89 parcels, set is scattered]
- `RET_WHOLESALER`: 160x162 m shed, dock levellers, pallet racking visible through the open front | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot RET_WHOLESALER frac (0.37, 0, 0.72, 1) of the S3 band zone
- `RET_WORKSHOP_STALL`: 110 lots, 16 m, 11 enterable [rect = single_parcel, 110 parcels, set is scattered]
- `SCHOOL_KINDER`: infill on pocket park PK_2_2_1_1: footprint 52x36 m, the rest of the 132x132 park stays green (soft conflict)
- `SCHOOL_PRIMARY`: infill on pocket park PK_2_6_0_1: footprint 96x68 m, the rest of the 132x132 park stays green (soft conflict)
- `SCHOOL_SECONDARY`: infill on pocket park PK_2_2_0_0: footprint 96x68 m, the rest of the 132x132 park stays green (soft conflict)
- `SKATEPARK`: bowls, quarter pipes, grind rails, stair set, ledges | sited in the free corner of park PK_1_2, keeping >70% of the green open
- `SPORTS_FIELD_1`: floodlit 100x60 m pitch with goals + basketball half-court, 6 m fence | sited in the free corner of park PK_0_0, keeping >70% of the green open
- `SPORTS_FIELD_2`: cricket nets + turf strip, volleyball sand court | sited in the free corner of park PK_3_0, keeping >70% of the green open
- `SPT_ARCHERY_RANGE`: 163x530 m: 18 covered lanes at 70 m, butt lines, safety berm, clubhouse | zone slot SPT_ARCHERY_RANGE frac (0, 0.63, 1, 1) of the W1 band zone
- `SPT_MOTOCROSS_PARK`: 560x163 m: 1.2 km dirt loop, jumps, spectator bank, timing hut | zone slot SPT_MOTOCROSS_PARK frac (0.61, 0, 1, 1) of the S2 band zone
- `SPT_TENNIS_CENTRE`: 8 courts 36x18 + clubhouse + 2 covered courts + floodlight poles | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot SPT_TENNIS_CENTRE frac (0, 0.36, 1, 0.66) of the E4 band zone
- `SPT_VELODROME`: 162x250 m footprint, timber banking, clear-span roof | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot SPT_VELODROME frac (0, 0, 1, 0.33) of the E4 band zone
- `STADIUM_ATHLETICS`: converts park PK_0_1; 400 m track, jump pits, open roof, 24 m green ring
- `STADIUM_CRICKET`: converts park PK_1_0 (sports_field) - keeps a 24 m green ring with jogging path + trees; outfield 150 m, 4 stands, sightscreen, floodlight pylons
- `STADIUM_FOOTBALL`: converts park PK_4_0; 105x68 pitch open to the sky, 4 uncovered/covered stands, no roof membrane - open oculus; 24 m green ring kept
- `STATION_FIRE`: infill on pocket park PK_0_3_0_1: footprint 76x44 m, the rest of the 132x132 park stays green (soft conflict)
- `STATION_POLICE`: infill on pocket park PK_0_7_1_0: footprint 72x44 m, the rest of the 132x132 park stays green (soft conflict)
- `TEMPLE`: corner infill inside park PK_1_1, >85% of the park stays open
- `THEATRE`: MERGE of 9 contiguous parcels in sub-block (0, 0) of cell [3,3] - those 9 buildings are NOT built
- `TRACK_CIRCUIT`: layout spline exists; build = asphalt surface + racing wear + kerbs + 15 m run-offs + tyre walls + catch fence
- `TRACK_GRANDSTAND`: 2 stands exist; 2 more needed (see TRACK_GRANDSTAND_EXTRA)
- `TRF_ROAD_MARKINGS`: 120x163 m: paint store, sign fabrication, thermoplastic rolls | zone slot TRF_ROAD_MARKINGS frac (0, 0, 1, 1) of the C_SW band zone
- `TRF_TRAFFIC_SIGNALS`: 130x163 m: controller cabinets, signal-head spares, pole stock (drives all junction signals) | zone slot TRF_TRAFFIC_SIGNALS frac (0.77, 0, 1, 1) of the N2 band zone
- `TRK_CAMPSITE`: 163x210 m lawn: pitches, service hookups, ablution block, small shop | zone slot TRK_CAMPSITE frac (0, 0.79, 1, 1) of the E1 band zone
- `TRK_FAN_ZONE`: 144x128 m: food stalls (open fronts), merch tents, seating deck, toilets
- `TRK_FLOODLIGHT_A`: 4x 28 m masts in the infield gap between the medical centre and the workshop (props budget)
- `TRK_FLOODLIGHT_B`: 4x 28 m masts on the north verge beside the new north stand (props budget)
- `TRK_FOOD_COURT`: 163x150 m open court: 12 stalls under a canopy, picnic tables, stage | zone slot TRK_FOOD_COURT frac (0, 0.45, 1, 0.72) of the E2 band zone
- `TRK_GATE_E`: 163x110 m: 10 search lanes, ticket offices, bus drop-off | zone slot TRK_GATE_E frac (0, 0.93, 1, 1) of the E3 band zone
- `TRK_GRANDSTAND_E2`: third stand, 50x150 m, cantilever roof, 32 rows
- `TRK_GRANDSTAND_N`: fourth stand on the north verge of the circuit zone, 250x26 m
- `TRK_KARTING`: 192x264 m infield kart track: 8 m asphalt ribbon, kerbs, barriers, timing gantry
- `TRK_MEDICAL`: infield trauma room, 4 ambulance bays, helipad marking H on the apron
- `TRK_MERCH_HALL`: 163x120 m hall, roller fronts open, VIP paddock club above | zone slot TRK_MERCH_HALL frac (0, 0.75, 1, 1) of the E2 band zone
- `TRK_MOTORSPORT_MUSEUM`: hero: 228x224 m glazed hall inside the circuit infield; race simulators, trophy hall, cafe
- `TRK_PADDOCK_ANNEX`: hardstanding south of the pit lane: 6 team truck boxes, generator set, welfare block
- `TRK_PARKING_E1`: surface lot 163x140 m, ~260 bays, solar shade over 40 | zone slot TRK_PARKING_E1 frac (0, 0.51, 1, 0.74) of the E3 band zone
- `TRK_PARKING_E2`: surface lot 163x100 m, coach bays on the north edge | zone slot TRK_PARKING_E2 frac (0, 0.77, 1, 0.9) of the E3 band zone
- `TRK_PARKING_E3`: surface lot 163x130 m | zone slot TRK_PARKING_E3 frac (0, 0.89, 1, 1) of the E4 band zone
- `TRK_SCORING_TOWER`: 14 m mast, LED screen 12x7 m, timing boxes
- `TRK_SKID_PAD`: open asphalt pad inside the infield, water-spray nozzles, cone set, tyre barriers
- `TRK_SPECTATOR_VILLAGE`: 163x170 m: souvenir street, food hall (open front), fan deck, information pavilion | zone slot TRK_SPECTATOR_VILLAGE frac (0, 0.53, 1, 0.76) of the E1 band zone
- `TRK_START_GANTRY`: steel truss over the start line with light beam + team boards (structure, not a building)
- `TRK_TRANSPORT_HUB`: 163x170 m: 8 bus bays, tram platform, taxi rank, cycle racks, canopy | zone slot TRK_TRANSPORT_HUB frac (0, 0.69, 1, 0.86) of the E4 band zone
- `TRK_WORKSHOP`: long shed along the pit straight: tyre racks, fuel bowsers, workshop, parts store
- `TRN_AIR_CARGO`: 260x30 m cross-dock, 12 dock doors | outer frame lies OUTSIDE the elevated highway ring; no parcels exist there
- `TRN_AIR_FIRE`: 2 appliance bays open frontage, drill tower 18 m | outer frame lies OUTSIDE the elevated highway ring; no parcels exist there
- `TRN_AIR_HANGARS`: 3 hangars with open roller fronts (no doors), 110x30 m each | outer frame lies OUTSIDE the elevated highway ring; no parcels exist there
- `TRN_AIR_PARKING`: 72x320 m multi-row surface lot on the E frame, solar canopy over 60 bays | outer frame lies OUTSIDE the elevated highway ring; no parcels exist there
- `TRN_AIR_TERMINAL`: 700x30 m single-loaded concourse, 2 floors, glazed south wall with missing-glass openings, 6 gates | outer frame lies OUTSIDE the elevated highway ring; no parcels exist there
- `TRN_AIR_TOWER`: 24x24 m base, 24 m shaft, canted cab with 360 deg glazing | outer frame lies OUTSIDE the elevated highway ring; no parcels exist there
- `TRN_APRON`: 1156x38 m apron, 6 marked stands with stand-guidance lines, ground equipment props | outer frame lies OUTSIDE the elevated highway ring; no parcels exist there
- `TRN_BICYCLE_SHARE`: 60x163 m: 60 docks, repair shed, spare-bike racks (street furniture cluster) | zone slot TRN_BICYCLE_SHARE frac (0, 0, 1, 1) of the C_SE band zone
- `TRN_BUS_DEPOT`: 26 open bays (no doors), workshop, fuel island; serves the N arterial ramp at x=-600 | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot TRN_BUS_DEPOT frac (0, 0, 0.28, 1) of the N1 band zone
- `TRN_BUS_SHELTERS`: 260x163 m works yard: shelters/bins/benches stored here, installed across the city (props budget) | zone slot TRN_BUS_SHELTERS frac (0.63, 0, 1, 1) of the N1 band zone
- `TRN_COACH_TERMINAL`: 12 angled coach bays, glazed hall, open archway entrance | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot TRN_COACH_TERMINAL frac (0.33, 0, 0.66, 1) of the N3 band zone
- `TRN_MAIL_SORTING`: postal sorting hall + 24 loading docks; counter post offices are distributed shop units | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot TRN_MAIL_SORTING frac (0.31, 0, 0.6, 1) of the N1 band zone
- `TRN_PARK_AND_RIDE`: surface lot 190x162 m, ~450 marked bays, shade canopies + solar | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot TRN_PARK_AND_RIDE frac (0.26, 0, 0.49, 1) of the N2 band zone
- `TRN_PETROL_EV`: 2 canopies (6 pumps + 8 EV stalls), shop with open frontage, air/vacuum, car wash | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot TRN_PETROL_EV frac (0, 0, 0.2, 1) of the S4 band zone
- `TRN_RAIL_LINE`: surface rail in the north outer frame, entirely outside the ring so it never crosses a road corridor; set 23 m clear of the ring deck and 3 m clear of the flyover ground band; ballast + sleepers + catenary masts
- `TRN_RAIL_PLATFORMS`: platform faces, canopies, stairs to the concourse
- `TRN_RAIL_STATION`: 700x38 m concourse with a full-height glazed north wall and open gate line (no doors); park-and-ride access via the x=0 ring ramp
- `TRN_RUNWAY`: COMPROMISE: a full 3000 m runway cannot fit 3x3 km; 1200 m strip + centreline + thresholds + overrun, no taxiway grid | outer frame lies OUTSIDE the elevated highway ring; no parcels exist there
- `TRN_STREET_DEPOT`: 163x530 m: grit/salt barn, 12 vehicle bays, salt pile, wash bay | zone slot TRN_STREET_DEPOT frac (0, 0.65, 1, 1) of the W4 band zone
- `TRN_TAXIWAY`: 28 m link from runway end to apron | outer frame lies OUTSIDE the elevated highway ring; no parcels exist there
- `TRN_TRUCK_STOP`: 24 truck bays, weighbridge, drivers' diner, washroom block | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot TRN_TRUCK_STOP frac (0.55, 0, 0.82, 1) of the S4 band zone
- `UNIVERSITY_FACULTY`: MERGE of 13 contiguous parcels in sub-block (1, 0) of cell [3,7] - those 13 buildings are NOT built
- `UNIVERSITY_MAIN`: MERGE of 13 contiguous parcels in sub-block (0, 0) of cell [3,7] - those 13 buildings are NOT built
- `UTL_CEMETERY`: walled lawn cemetery, rows of headstones (instanced), chapel, memorial wall | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot UTL_CEMETERY frac (0, 0, 0.4, 1) of the S1 band zone
- `UTL_CREMATORIUM`: chapel with open porch, 2 ovens hall, car park | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot UTL_CREMATORIUM frac (0.43, 0, 0.68, 1) of the S1 band zone
- `UTL_GAS_DEPOT`: 2 bullet tanks, regulator skid, flare stack, bunker | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot UTL_GAS_DEPOT frac (0, 0.27, 1, 0.5) of the E1 band zone
- `UTL_SEWAGE`: pump house + 2 tank cylinders + odour vent stack | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot UTL_SEWAGE frac (0.35, 0, 0.58, 0.55) of the S2 band zone
- `UTL_SOLAR_FARM`: 280x163 m: 18 rows of panels, inverter cabinets, battery containers | zone slot UTL_SOLAR_FARM frac (0.52, 0, 0.74, 1) of the N2 band zone
- `UTL_SUBSTATION`: transformer yard, gantry, 6 m fence, warning signage | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot UTL_SUBSTATION frac (0, 0, 1, 0.24) of the E1 band zone
- `UTL_TELECOM`: 36 m lattice mast + 8 m equipment cabin on the NE corner wedge | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot UTL_TELECOM frac (0, 0, 1, 1) of the C_NE band zone
- `UTL_TRANSFORMER`: pad-mount transformers + 120 m3 water tank (fire cover for the belt) | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot UTL_TRANSFORMER frac (0, 0, 1, 1) of the C_NW band zone
- `UTL_WASTE`: sorting hall, bays for paper/glass/plastic, truck weighbridge | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot UTL_WASTE frac (0, 0, 0.34, 1) of the S3 band zone
- `UTL_WATER_TOWER`: elevated steel tank on legs, landmark visible from the green belt | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot UTL_WATER_TOWER frac (0.35, 0.6, 0.55, 1) of the S2 band zone
- `UTL_WATER_TREATMENT`: 4 circular clarifier tanks, filter house, chemical store | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot UTL_WATER_TREATMENT frac (0, 0, 0.32, 1) of the S2 band zone
- `WORKSHOP_FABRICATION`: MERGE of 4 contiguous parcels in sub-block (0, 1) of cell [5,2] - those 4 buildings are NOT built
- `WRK_CONSTRUCTION_YARD`: 560x163 m: site offices, material stacks, plant parking | zone slot WRK_CONSTRUCTION_YARD frac (0.71, 0, 1, 1) of the S1 band zone
- `WRK_DATA_CENTRE`: 162x540 m: 2 windowless halls + generator yard + cooling towers - big, flat, no glazing | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot WRK_DATA_CENTRE frac (0, 0, 1, 0.42) of the E2 band zone
- `WRK_LOGISTICS_HUB`: 560x163 m: 2 cross-dock halls, 40 dock doors, trailer court | zone slot WRK_LOGISTICS_HUB frac (0.55, 0, 0.77, 1) of the N4 band zone
- `WRK_TECH_PARK`: 3 slab blocks around a landscaped court; out-of-town campus for the R/M districts | belt land has NO parcels in layout.json (open land, no road corridor) | zone slot WRK_TECH_PARK frac (0, 0, 0.23, 1) of the N2 band zone

### 10.2 Hard conflicts, facility by facility

- `TRACK_PIT` [no_adjacent_road]: nearest road corridor is 126 m away (A_H_5_1); layout.json has NO road in this land - a service road / access spur must come from the Roads module first
- `TRACK_PADDOCK` [no_adjacent_road]: nearest road corridor is 160 m away (A_V_6_1); layout.json has NO road in this land - a service road / access spur must come from the Roads module first
- `TRACK_TOWER` [no_adjacent_road]: nearest road corridor is 160 m away (A_V_6_1); layout.json has NO road in this land - a service road / access spur must come from the Roads module first
- `STADIUM_CRICKET` [converts_park]: cell [1, 0] holds park STADIUM_CRICKET - the park ground is rebuilt around the venue (24 m green ring kept)
- `STADIUM_FOOTBALL` [converts_park]: cell [4, 0] holds park STADIUM_FOOTBALL - the park ground is rebuilt around the venue (24 m green ring kept)
- `STADIUM_ATHLETICS` [converts_park]: cell [0, 1] holds park STADIUM_ATHLETICS - the park ground is rebuilt around the venue (24 m green ring kept)
- `COMPLEX_SWIMMING` [converts_park]: cell [4, 1] holds park COMPLEX_SWIMMING - the park ground is rebuilt around the venue (24 m green ring kept)
- `ARENA_INDOOR` [converts_park]: cell [0, 2] holds park ARENA_INDOOR - the park ground is rebuilt around the venue (24 m green ring kept)
- `COURTHOUSE` [superlot_merges_parcels]: 4 contiguous parcels in cell [3, 5] (D) are REMOVED and replaced by one building
- `MUSEUM_CITY` [superlot_merges_parcels]: 4 contiguous parcels in cell [4, 4] (D) are REMOVED and replaced by one building
- `PLANETARIUM` [superlot_merges_parcels]: 4 contiguous parcels in cell [4, 4] (D) are REMOVED and replaced by one building
- `DEPARTMENT_STORE` [superlot_merges_parcels]: 4 contiguous parcels in cell [3, 4] (D) are REMOVED and replaced by one building
- `CARPARK_MULTISTOREY` [superlot_merges_parcels]: 4 contiguous parcels in cell [5, 4] (D) are REMOVED and replaced by one building
- `CONFERENCE_CENTRE` [superlot_merges_parcels]: 4 contiguous parcels in cell [5, 5] (D) are REMOVED and replaced by one building
- `OFFICE_COWORKING` [superlot_merges_parcels]: 4 contiguous parcels in cell [4, 5] (D) are REMOVED and replaced by one building
- `THEATRE` [superlot_merges_parcels]: 9 contiguous parcels in cell [3, 3] (E) are REMOVED and replaced by one building
- `CONCERT_HALL` [superlot_merges_parcels]: 9 contiguous parcels in cell [5, 3] (E) are REMOVED and replaced by one building
- `GALLERY_ART` [superlot_merges_parcels]: 9 contiguous parcels in cell [2, 4] (E) are REMOVED and replaced by one building
- `ARCADE_GAMES` [superlot_merges_parcels]: 9 contiguous parcels in cell [6, 4] (E) are REMOVED and replaced by one building
- `CASINO` [superlot_merges_parcels]: 9 contiguous parcels in cell [4, 6] (E) are REMOVED and replaced by one building
- `BANQUET_HALL` [superlot_merges_parcels]: 9 contiguous parcels in cell [6, 5] (E) are REMOVED and replaced by one building
- `HOSTEL` [superlot_merges_parcels]: 13 contiguous parcels in cell [1, 5] (R) are REMOVED and replaced by one building
- `EMBASSY` [superlot_merges_parcels]: 13 contiguous parcels in cell [1, 7] (R) are REMOVED and replaced by one building
- `UNIVERSITY_MAIN` [superlot_merges_parcels]: 13 contiguous parcels in cell [3, 7] (R) are REMOVED and replaced by one building
- `UNIVERSITY_FACULTY` [superlot_merges_parcels]: 13 contiguous parcels in cell [3, 7] (R) are REMOVED and replaced by one building
- `DORMITORIES` [superlot_merges_parcels]: 13 contiguous parcels in cell [3, 7] (R) are REMOVED and replaced by one building
- `BREWERY` [superlot_merges_parcels]: 4 contiguous parcels in cell [5, 1] (I) are REMOVED and replaced by one building
- `COLD_STORAGE` [superlot_merges_parcels]: 4 contiguous parcels in cell [5, 0] (I) are REMOVED and replaced by one building
- `WORKSHOP_FABRICATION` [superlot_merges_parcels]: 4 contiguous parcels in cell [5, 2] (I) are REMOVED and replaced by one building
- `TRK_MOTORSPORT_MUSEUM` [no_adjacent_road]: nearest road corridor is 160 m away (A_H_5_3); layout.json has NO road in this land - a service road / access spur must come from the Roads module first
- `TRK_SKID_PAD` [no_adjacent_road]: nearest road corridor is 68 m away (A_V_8_2); layout.json has NO road in this land - a service road / access spur must come from the Roads module first
- `TRK_KARTING` [no_adjacent_road]: nearest road corridor is 64 m away (A_V_8_0); layout.json has NO road in this land - a service road / access spur must come from the Roads module first
- `TRK_MEDICAL` [no_adjacent_road]: nearest road corridor is 64 m away (A_H_5_1); layout.json has NO road in this land - a service road / access spur must come from the Roads module first
- `TRK_WORKSHOP` [no_adjacent_road]: nearest road corridor is 64 m away (A_H_5_2); layout.json has NO road in this land - a service road / access spur must come from the Roads module first
- `TRK_FAN_ZONE` [no_adjacent_road]: nearest road corridor is 168 m away (A_V_6_1); layout.json has NO road in this land - a service road / access spur must come from the Roads module first
- `TRK_START_GANTRY` [no_adjacent_road]: nearest road corridor is 160 m away (A_V_6_2); layout.json has NO road in this land - a service road / access spur must come from the Roads module first
- `TRK_SCORING_TOWER` [no_adjacent_road]: nearest road corridor is 188 m away (A_V_8_2); layout.json has NO road in this land - a service road / access spur must come from the Roads module first
- `TRK_FLOODLIGHT_A` [no_adjacent_road]: nearest road corridor is 68 m away (A_V_6_1); layout.json has NO road in this land - a service road / access spur must come from the Roads module first

---

Validator: `PASS` - checks rect_shape, extent_-1500_1500, road_corridor_intersection, ring_corner_arc, mode_enum, module_enum, phase_enum, tri_budget_cap, unique_ids, facility_vs_facility_overlap, track_parcel_clearance, lake_clearance, wave_agent_limit.
Machine twin: `reports/program.json` (schema `city-program/1`).
