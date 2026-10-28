# Layout Report — city map generation

Generated: 2026-10-25 by `python3 generate_layout.py --split` (seed **1337**).

## Files produced

| File | Size | Contents |
|---|---|---|
| `/home/abdulhadi/Work/city/layout.json` | 1 121 172 B (1.09 MB) | meta, districts, road_nodes, road_edges, flyovers, stack_interchange, traffic_lights, parcels, parks, water, track, landmarks, vegetation_rules, stats |
| `parcels_D.json` | 50 645 B | 109 parcels (Downtown core) |
| `parcels_E.json` | 119 907 B | 288 parcels (Entertainment strip) |
| `parcels_G.json` | 5 944 B | 13 parcels (Green belt) |
| `parcels_I.json` | 18 767 B | 48 parcels (Industrial) |
| `parcels_M.json` | 478 871 B | 1 236 parcels (Market quarter) |
| `parcels_R.json` | 314 241 B | 844 parcels (Residential) |
| `parcels_T.json` | 2 634 B | 7 parcels (Race circuit) |

## Validation results (all PASS)

1. **JSON parses** — `layout.json` and all 7 `parcels_*.json` load with `json.load` (no exceptions).
2. **Required keys** — every one of the 2545 parcels has `id`, `district`, `rect`, `floors`, `enterable`, `interior_tier`.
   Missing-key count: **0**.
3. **No overlapping parcel rects** — sweep-line sweep on `rect[0]` (reference: `/tmp/opencode/check_layout.py`):
   * overlapping parcel pairs: **0**
   * degenerate rects (x1<=x0 or y1<=y0): **0**
4. **Split-file consistency** — sum of `parcels_<district>.json` = 109+288+13+48+1236+844+7 = **2545** = parcel count in
   `layout.json`; every record inside `parcels_X.json` has `district == "X"`.
5. **stats match file counts**
   * `stats.parcels_total` = 2545 ✓
   * `stats.parcels_by_district` = R 844, M 1236, E 288, D 109, I 48, G 13, T 7 ✓
   * `stats.road_edges_by_hierarchy` = arterial 134 + street 148 + alley 144 + highway 16 + ramp 12 = **454** = `len(road_edges)` ✓
   * `len(road_nodes)` = 322
   * `stats.parks` 26 = `len(parks)` ✓, `stats.traffic_lights` 111 = `len(traffic_lights)` ✓
   * `stats.validation_problems` = **[]** (empty)
6. **Map extent** — x ∈ [-1188, 1188], y ∈ [-1188, 1188] → 2376 m ≈ 3×3 km grid (fits the 3×3 km target).

## Known non-blocking observations

* **217 parcels have no `facade_style`** (76 R, 95 M, 32 E, 13 G, 1 D). These are parks, plazas, water lots,
  parking and other non-building parcels (facade_style only exists on the 2328 building parcels). Downstream
  agents should treat a missing `facade_style` as "no facade — open/ground lot".
* **225 parcels have no `buildable_rect`** — same non-buildable categories (park/plaza/water/yard). Treat as
  "do not place a building footprint".
* `interior_tier`: tier1_hero 39, tier2_shell 518, tier3_facade_only 1771; enterable_total 557.
* Road network: 454 edges / 322 nodes, 86.8 km of roads total (40.2 arterial, 22.2 street, 10.8 alley,
  11.2 highway, 2.4 ramp).

## Changes made to `generate_layout.py`

None — the script passed every check on the first run, so it was left untouched.
