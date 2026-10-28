# Preview Repair Report — PREVIEW-REPAIR subagent

Reusable harness: `city/modules/preview_harness.py` (rewritten). Each run opens a blend
read-only (never saves), adds temp camera + temp ground + temp sun/world, renders EEVEE
1920x1080 @ 32 samples, computes pixel stddev + magenta fraction, retries blank shots
(top-down / 45° / 2× distance), removes temp objects, never saves the source blend.
Materials come only from `materials.blend`.

## Results (all targets re-rendered from existing blends)

| Preview | stddev | magenta | attempts / variants | Status |
|---|---:|---:|---|---|
| `out/sports_preview.png` | 0.1155 | 0.0000 | 1 (base elev=50 az=0) | OK |
| `out/sports_football_preview.png` | 0.2022 | 0.0000 | 1 (eye_default nudge=0) | OK |
| `out/props_preview.png` | 0.0580 | 0.0000 | 1 (base elev=26 az=20, after closer re-frame) | OK |
| `out/props_street_preview.png` | 0.0939 | 0.0000 | 1 (eye_default nudge=0) | OK |
| `out/nature_playground_preview.png` | 0.1896 | 0.0000 | 1 (eye_default nudge=0) | OK |
| `out/interiors_preview.png` | 0.2518 | 0.0000 | 1 (eye_default nudge=0, indoor world) | OK |
| `out/interiors_kit_preview.png` | 0.0957 | 0.0000 | 1 (base elev=42 az=40) | OK |
| `out/lighting_preview.png` | 0.0413 | 0.0000 | 1 (base elev=66 az=10, night, 400×400 temp asphalt) | OK |
| `out/lighting_street_preview.png` | 0.0476 | 0.0000 | 1 (eye_default nudge=0, night) | OK |
| `out/flyover_preview.png` | 0.0989 | 0.0000 | 1 (base elev=42 az=38) | OK |
| `out/flyover_ground_preview.png` | 0.0814 | 0.0000 | 1 (re-framed angled up at deck+sky) | OK |
| `out/civic_preview.png` | 0.0992 | 0.0000 | 1 (base elev=44 az=40) | OK* |
| `out/civic_street_preview.png` | 0.1339 | 0.0000 | 1 (eye_default nudge=0) | OK |

All stddev values exceed the 0.02 blank threshold; magenta fraction is 0.0000 on every frame
(subject visible, not magenta). PNGs confirmed on disk in `/city/out/`.

*`civic_preview` frames City_Hall + Courthouse + Library_Public. MUSEUM_CITY could not be
included: its mesh (`SM_MuseumCity`) deterministically crashes the EEVEE renderer (segfault,
even without a ground plane), so it was excluded from the frame.

## Blends that could not be fully framed
- `out/civic.blend`: MUSEUM_CITY unrenderable (EEVEE crash). Several other civic facility meshes
  also crash EEVEE on render (`SM_CivicEmergencyOps`, `SM_Gurudwara`, plus meshes in index range
  594–618), so only verified-safe meshes were enabled for the civic previews.

## Issues found in source blends (not modified — reads only)
- `out/props.blend`: pure kit library; every kit mesh is authored at a different scattered far
  local coordinate (transforms never applied, origins not bottom-centre), so pieces render miles
  apart. Workaround: in-session, each instance was re-placed by compensating its mesh local
  offset onto a temporary street; source blend untouched and not saved.
- `out/civic.blend`: multiple meshes crash EEVEE on render (see above).
- All previews use temporary camera/ground/sun/world that are removed after render; no source
  blend was opened for writing or saved.

## Blends NOT touched (per contract)
commercial, traffic, transport, downtown, residential, entertainment, track, market, roads.
