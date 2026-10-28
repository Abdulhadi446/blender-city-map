# geometry_fix_report — GEOMETRY-QA surgical fixes (6 owned blends)

Headless `blender -b -P`, engine `BLENDER_EEVEE`, 1920x1080, temp ground+sun+world (removed after each preview, temps not saved). Contract materials appended via `modules/citykit.append_material` from `materials.blend`. Each blend saved before moving to the next. Pixel stddev measured from the saved preview PNG (0..1 scale); requirement >0.02 met everywhere.

## downtown.blend
- 1(a) stray giant teal inverted-cone: **none found** (no mesh with zmax>200 m AND footprint>80 m; landmark crown `SM_OFF_DEC_098_c` is zmax=216.6 but only 38x38 m footprint — part of tower, not stray).
- 1(b) vertical texture smear on tower facades: triplanar box-mapping applied to `concrete`, `plaster_white`, `plaster_cream`, `stone_grey`, `marble_white`.
- 1(c) blank white side walls: window-band strips added to all 4 sides of every tower — 108 `*_gqa_winbands` objects (all `SM_*_sha_f*` bases covered, incl. curved `*_CUR_*` towers).
- tris (unique): 299894 (hero budget per building respected).
- previews: `downtown_preview.png` stddev=0.0853; `downtown_street_preview.png` stddev=0.0916.

## nature.blend
- 2(a) park ground: all large ground meshes already `grass` (82-100% dominant) with `dirt` shore band only; paths `paving_slab`; **0 meshes reassigned** (already compliant). Venue rects untouched.
- 2(b) pink/magenta props: **none found** (no missing/invalid materials; all images packed).
- tris: 42804. preview: `nature_preview.png` stddev=0.0587.

## residential.blend
- 3(a) oversized road/pavement planes (fp>200 m axis, z 0-0.2, asphalt/paving): **0 found/deleted** (none duplicate Roads; paths/driveways <40 m kept).
- 3(b) boundary walls flat sage-green `facade_plaster_sage` → `facade_plaster_bone` (concrete `stone_grey` coping kept): **163 slot refs across objects** fixed (CourtWall/LotFence + `SM_Bldg_*_SM_*`).
- 3(c) floating dark balcony boxes `SM_Balcony*`: instanced support bracket (`SM_GQA_Bracket_01`, 24 unique tris) placed under **866 balconies**.
- tris: 476420. previews: `residential_preview.png` stddev=0.0760; `residential_street_preview.png` stddev=0.0405.

## track.blend
- 4(a) stray small floating grey box near grandstand (z 2-40, fp<5x5): **none found** matching (pit plant boxes are 6x5, mast is legit).
- 4(b) pit-building roof: `SM_PitBldg_Roof_01` `roof_bitumen` → `roof_metal` + 43 instanced steel ribs/parapet along ridge.
- 4(c) paddock blown-white `concrete` → `concrete_poured` (1 object).
- tris: 153256. preview: `track_ground_preview.png` stddev=0.1004.

## entertainment.blend
- 5(a) shopfront glass blown white: `glass_shop`/`glass_office`/`glass_clear` → `glass_tinted_office` (256 slots now tinted; 0 white shopfront slots remain).
- 5(b) courtyard bare dirt: **0 dirt ground meshes found** (none to reassign).
- 5(c) flat bright-green/teal wall panels `facade_plaster_teal` → `facade_plaster_bone` plaster: **45 objects**.
- tris: 528780. previews: `entertainment_preview.png` stddev=0.0509; `entertainment_street_preview.png` stddev=0.0711.

## market.blend
- 6: all 247 `LT_market_*` lights moved into `Market/Lights` collection (collection created; 0 → 247 members). `<=250: PASS`.
- preview: `market_street_preview.png` stddev=0.0644. tris: 682410.

## Deleted objects
None — no object matched the deletion criteria (sky cone, oversized road plane, floating grey box were all absent in the current builds).

## Remaining issues
- downtown: smear fix applied generically to facade materials (not only towers) — acceptable; no new geometry budget risk.
- entertainment: no distinct "bright-green" wall material found beyond `facade_plaster_teal` (same texture as bone); normalized to contract plaster.
- track: pit ribs are 43 instances along the roof ridge (shared 24-tris mesh).
- All six blends saved; reports/geometry_fix_report.md written.
