# City — 3×3 km AAA city map (Blender 5.2)

Single-file master city: **`out/city_master.blend`** (443 MB, self-contained, all textures packed).

| Metric | Value |
|---|---|
| Area | 3,000 × 3,000 m (origin at centre, Z-up, metres) |
| Objects | 84,584 |
| Mesh datablocks | 7,608 |
| Materials | 385 (all from `materials.blend`) |
| Packed images | 610 (0 missing) |
| Collections | 102 |
| Build time | ~43 min (append-all assembler) |

## Open it

```bash
blender out/city_master.blend
```

Scene is preconfigured: **EEVEE**, 1920×1080, 32 samples, metric units, world sky
`(0.55, 0.65, 0.8)`, sun at 5°/35°, energy 3, 0.5° angular size.

## What is inside

| Master collection | Source module | Content |
|---|---|---|
| Roads | `roads.blend` | 454 road edges (arterial 40.2 km, street 22.2 km, alley 10.8 km, highway 11.2 km), 409 zebra crossings, 1,938 manholes, 108 access spurs, kerbs, medians, 1,137 collision proxies |
| Flyovers | `flyover.blend` | NE highway-ring deck + ramp landing on the y=1200 arterial, jersey barriers, pillars |
| Buildings/Market | `market.blend` | 1,236 parcels: 946 tier-3, 188 tier-2 furnished, 7 tier-1, 95 courtyards + covered bazaar landmark |
| Buildings/Downtown | `downtown.blend` | 108 towers (landmark tower 193 m), plaza, window bands |
| Buildings/Residential | `residential.blend` | 844 houses across 16 cells |
| Buildings/Entertainment | `entertainment.blend` | 288 parcels, neon strip, courtyards |
| Buildings/Sports | `sports.blend` | Cricket, football (open roof), athletics, indoor arena, swimming complex |
| Buildings/Civic | `civic.blend` | 40 facilities: city hall, hospital, schools, fire/police, library, mosque, church, courthouse, museum, concert hall, university, planetarium, gallery, theatre, embassy, casino |
| Buildings/Commercial | `commercial.blend` | 35 facilities: mall, supermarkets, department store, offices, hotel, icon tower, industrial, media |
| Buildings/Transport | `transport.blend` | Airport (runway, terminal, tower, hangars), rail station, metro, bus/coach, car parks |
| Vegetation | `nature.blend` | ~14k trees, parks, lake, playgrounds |
| Track | `track.blend` | 3,388 m race circuit, grandstand, paddock, pits |
| Traffic | `traffic.blend` | 4,825 vehicles (13 types), parked + moving + 24 on the elevated deck |
| Props | `props.blend` | 3,614 street props: hydrants, bins, benches, planters, bus shelters, rooftop AC, cables |
| Lighting | `lighting.blend` | 3,516 lamp/signal instances, 102 real lights, 386 signal heads |
| Interiors | `interiors.blend` | Six kit families + reference rooms |
| Ground | master | 3,000 × 3,000 m grass terrain + track infield |

Collision proxies (`COL_*`) are present per module and hidden from render.

## Reports

- `reports/inventory.md` — measured census of all 16 module blends
- `reports/assemble_report.md` — master build log and verification
- `reports/*_report.md` — per-module detail (tris, budgets, issues)
- `reports/risk_fixes.md` — strip rules, ramp positions, Assembler contract
- `reports/city_program.md` — full 179-facility city programme

## Regenerate / extend

```bash
# one module
blender -b -P modules/<module>.py

# rebuild master from the 16 module blends (append-all, ~45 min)
blender -b --factory-startup -P /tmp/opencode/append_all.py

# QA renders (workbench)
blender -b out/city_master.blend -P /tmp/opencode/render_wb.py -- aerial

# export 9 districts as GLB + FBX + manifests
blender -b out/city_master.blend -P modules/export_districts.py -- --out exports
```

## Known issues

- `props.blend` kit mesh `SM_Cable_` is authored ~50 km from origin (source-kit offset); instances were compensated at placement time but the datablock origin is still far.
- Master uses appended copies (not library links): editing a module blend does not update the master — re-run the assembler.
- Collection names carry `.001` suffixes from the append (cosmetic).
- Interiors beyond the built tiers are facade-only with fake depth (per plan).
