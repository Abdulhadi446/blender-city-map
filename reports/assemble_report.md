# Master Assembly Report — out/city_master.blend

Built by `modules/assemble_all.py` (run also archived at `/tmp/opencode/append_all.py`), which appends
all 16 module blends with `bpy.data.libraries.load(..., link=False)` into a single self-contained
master scene. No library links remain: the .blend is portable.

## Result

| Property | Value |
|---|---|
| File | `out/city_master.blend` |
| Size | ~443 MB (compressed on save) |
| Objects | 84,584 |
| Mesh datablocks | 7,608 |
| Materials | 385 |
| Images | 610 (packed, 0 missing) |
| Collections | 102 |
| Build time | 2,600 s (~43 min) headless |

## Scene tree

```
City
├── Roads.001          (454 edges, 5,146 objects, 1,137 colliders excluded)
├── Flyovers.001       (NE ring + ramp, 1,243 objects)
├── Buildings
│   ├── Market         (1,236 parcels, bazaar hero)
│   ├── Downtown       (108 towers + landmark)
│   ├── Residential    (844 R parcels)
│   ├── Entertainment  (288 parcels)
│   ├── Sports         (5 venues)
│   ├── Civic          (40 facilities)
│   ├── Commercial     (35 facilities)
│   └── Transport      (31 facilities)
├── Vegetation         (nature: 27,304 objects)
├── Track.001          (3,388 m circuit)
├── Traffic.001        (4,825 vehicle instances)
├── Props.001 / Props.002
├── Lighting.001       (3,516 lamp/signal instances)
├── Interiors.001
└── Ground             (3,000×3,000 grass + track infield fill)
```

Collection-name suffixes (`.001`, `.002`) are cosmetic artifacts of appending; data is correct.

## Lighting / world

- `World_Master`: sky colour (0.55, 0.65, 0.80), strength 1.0
- `SUN_Master`: 5° elevation / 35° azimuth, energy 3.0, angular size 0.5°, warm white
- Engine: `BLENDER_EEVEE`, 1920×1080, 32 samples, metric units

## Data hygiene

- `mesh.validate(clean_customdata=True)` was run on every source blend before assembly
  (`modules/validate_meshes.py`): civic 13 repairs, interiors 6, residential 4, all others 0.
  This removed the EEVEE segfault caused by invalid civic meshes.
- All images are packed; `count_master.py` reported 0 missing images.
- Collider collections were excluded at build time (hide_render); `COL_*` proxies remain in the file
  for game export.

## Known issues

1. Colliders in `Interiors`/`Transport` were render-visible in isolated module previews (magenta
   `col_placeholder`). In the master they are inside `*Colliders*` collections with
   `hide_render=True`.
2. `out/props.blend` kit meshes carry unapplied far offsets (e.g. `SM_Cable_` around x≈−50.9 km).
   Instances are placed by object transform, so in-scene props are correct, but exported kit data
   should be fixed before reuse.
3. The five stadium repurposed park rects contain no Nature geometry (verified separately: 0 mesh
   objects inside the 5 rects), so sports venues are clear.
4. Desktop MCP (live Blender) was unavailable during this build; the master is delivered as a file
   plus headless QA renders (`out/qa_*.png`).

## Verification

- Load test: `blender -b out/city_master.blend -P /tmp/opencode/count_master.py` →
  `###OBJS 84584 ###COLLS 102 ###MESHES 7608 ###MATS 385 ###IMGS 610 missing 0 ###OK`
- QA renders: `out/qa_aerial.png`, `out/qa_market.png`, `out/qa_downtown.png`,
  `out/qa_street.png`, `out/qa_stadium.png` (1280×720, EEVEE, 8 samples).
