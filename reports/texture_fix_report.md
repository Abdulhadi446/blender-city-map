# Texture fix report — `/city` image datablocks

Date: 2026-10-28 · Blender 5.2.3 · engine `BLENDER_EEVEE`
Tool: `modules/material_fix.py` (headless, `blender -b out/<name>.blend -P modules/material_fix.py -- --save`)

## What was wrong

Image datablocks pointed at `//../../../../../tmp/opencode/ph/<set>/<Diffuse|AO|Rough|nor_gl|...>.jpg`.
`/tmp/opencode/ph` was wiped, so every material using those images rendered magenta.

Two things had to be fixed in the script:

1. **Map tokens / metadata keys were not normalised.** `nor_gl` / `nor_dx` / `Displacement` were
   looked up with the raw stem, so normals never matched (`norgl` vs `nor_gl`). Token and
   PolyHaven-key tables are now keyed by the normalised stem, and filename matching uses the
   `<set>_<map>_<res>.<ext>` boundary (`_nor_gl_`, `_diff_`, ...) so `nor` no longer matches
   `nor_gl` and `ao` never matches `albedo`.
2. **The packed bytes were the fastest, network-free source.** Most broken images still carried
   their original bytes inside the .blend. The script now resolves in this order:
   project `textures/<set>/` → extract the packed bytes to `/tmp/opencode/ph/<set>/packed_<map>.jpg`
   → download 2k jpg from `textures/_meta/<set>.json` → download via `api.polyhaven.com/files/<set>`.
   Every resolved image is re-pathed and packed, so the .blend stays self-contained.

## Per-blend results

| blend | images | missing before | fixed local | fixed packed | fixed download | still missing |
|---|---|---|---|---|---|---|
| traffic | 0 | 0 | 0 | 0 | 0 | 0 |
| transport | 24 | 17 | 0 | 12 | 5 | 0 |
| props | 20 | 14 | 0 | 14 | 0 | 0 |
| sports | 24 | 20 | 0 | 20 | 0 | 0 |
| interiors | 26 | 20 | 0 | 20 | 0 | 0 |
| lighting | 4 | 4 | 0 | 4 | 0 | 0 |
| flyover | 24 | 22 | 0 | 22 | 0 | 0 |
| roads | 36 | 34 | 0 | 34 | 0 | 0 |
| market | 85 | 56 | 10 | 46 | 0 | 0 |
| nature | 32 | 32 | 8 | 24 | 0 | 0 |
| residential | 91 | 56 | 10 | 46 | 0 | 0 |
| downtown | 40 | 40 | 0 | 40 | 0 | 0 |
| entertainment | 63 | 44 | 8 | 36 | 0 | 0 |
| track | 44 | 44 | 5 | 39 | 0 | 0 |
| civic | 89 | 36 | 6 | 30 | 0 | 0 |
| **total** | **602** | **439** | **47** | **387** | **5** | **0** |

`commercial.blend` was skipped (being rebuilt by another agent). `traffic.blend` contains no image
datablocks at all (procedural materials only), so it was saved unchanged.

Verification pass on every saved file (reload, then check each image's path and pixel buffer):

```
traffic 0 images · transport 24 · props 20 · sports 24 · interiors 26 · lighting 4 · flyover 24
roads 36 · market 81 · nature 32 · residential 87 · downtown 40 · entertainment 59 · track 36 · civic 89
broken_path = 0, no_pixels = 0, bad = []   (every blend)
```

`market`, `residential`, `entertainment` and `track` report slightly fewer images after the save
(85→81, 91→87, 63→59, 44→36): Blender drops zero-user duplicates on save. Nothing is lost — every
remaining image resolves and loads.

## Unresolved set/map

**None.** No image was left pointing at a dead path.

Two sets used by `transport.blend` are absent from both `textures/` and `textures/_meta/`:
`concrete_floor_01` and `bicolour_gravel` (4 images each: Diffuse, AO, Rough, nor_gl).
They were recovered from the packed bytes inside the .blend, so no download was needed.
Downloaded while fixing `transport` (5 images): `asphalt_01` AO, `corrugated_iron` AO + Rough,
`wood_planks` AO (`asphalt_01`/`wood_planks` Rough were already present locally).

## Transport previews

Re-rendered from the fixed `out/transport.blend` with `scripts/transport_preview.py`
(temp 500×500 m asphalt ground at z = -0.01, temp sun energy 3 at 25° elevation, grey-blue world,
EEVEE 1920×1080, 32 samples; temp objects never saved):

| file | mean | stddev | magenta pixels |
|---|---|---|---|
| `out/transport_preview.png` | 0.661 | **0.253** | 0.0 % |
| `out/transport_airport_preview.png` | 0.660 | **0.251** | 0.0 % |

* Aerial oblique: runway, apron, 700 m terminal, control tower, hangars, jet props all present and
  textured (asphalt/gravel grain visible on the apron, wall material on the terminal).
  stddev 0.253 ≫ 0.02.
* Eye level, 1.7 m, 40 m in front of the terminal: the terminal wall, plinth band and apron fill
  the frame with real material texture, no magenta. stddev 0.251 ≫ 0.02.

### Separate magenta source (not textures, flagged only)

`transport.blend` keeps its `Colliders` collection render-visible, and those 31 proxies use
`col_placeholder`, whose node tree is a flat RGB (1.0, 0.0, 1.0) — i.e. pure magenta by design.
They were the magenta boxes in the first preview render. The preview script hides objects using
`col_placeholder` at render time only (31 hidden in transport) and does **not** save that change.
`interiors.blend` has the same issue with 6 visible proxies; all other blends have none visible.
Hiding the `Colliders` collection in those two files is a one-line visibility fix if the owner
wants renders clean without the preview script.

## Files changed

* `modules/material_fix.py` — normalised map/metadata keys, stricter filename matching,
  packed-byte extraction, API fallback, `fixed_packed` counter, per-image exception guard.
* `scripts/transport_preview.py` — new: renders both transport previews.
* `out/{transport,props,sports,interiors,lighting,flyover,roads,market,nature,residential,downtown,entertainment,track,civic}.blend` — repathed, packed, saved.
* `out/transport_preview.png`, `out/transport_airport_preview.png` — re-rendered.
* Logs: `/tmp/opencode/texfix_<blend>.log`.
