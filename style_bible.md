# AAA CITY — STYLE BIBLE v1.0

**Owner:** Agent 0 (Style Bible + Materials). **Status:** authoritative for every agent.
Anything not specified here is your call; anything specified here is binding.
Read this file before you open Blender. Companion files:

| file | what it is |
|---|---|
| `/city/style_bible.md` | this document — style rules, palette, district rules, signage, time of day |
| `/city/materials.blend` | the PBR library. Append materials **by name**, never create or edit |
| `/city/materials_index.json` | machine-readable index of every material + the 2 node groups |
| `/city/layout.json`, `/city/parcels_<D>.json` | geometry truth (do not regenerate) |
| `/city/modules/materials.py` | regenerates the blend + index (only Agent 0 runs it) |

> **TWO NAME SETS — read this first.** §1–§9 below document the 93-name set indexed by
> `materials_index.json`. The **64 contract names** required by the Global Contract
> (`asphalt`, `brick_red`, `glass_shop`, `neon_*`, …) are documented in **PART B** at the
> end of this file, indexed by `materials.json`. `materials.blend` ships **both** sets
> (155 materials) and **both** node-group pairs, so you can append either list by name —
> `citykit.append_material()` raises a readable error listing every available name.

> **PATHS:** `/city` = `/home/abdulhadi/Work/city` (canonical) **and**
> `/home/abdulhadi/Work/AAA GAME 3D City/city` (symlink → same folder). Both work.
> If a path in your prompt does not exist, check this line before assuming the project is gone.

---

## 0. Non-negotiables (from the Global Contract)

* **Units:** metres, 1 BU = 1 m, Z up, `+X` east, `+Y` north. **Apply all transforms before saving.**
* **Origins:** every kit piece origin at **bottom-centre**.
* **Scale rules:** opening/door height **2.4 m**, lane **3.5 m**, sidewalk **2.5 m**, floor **3.2 m**, curb **0.15 m**.
* **No door meshes.** Enterable buildings use the parcel's `opening` (archway, open frontage, atrium, porch, bay). Interiors go behind it, anchored at `INT_ANCHOR_<parcel_id>`.
* **Materials:** append from `/city/materials.blend` only. **Missing material → ask Agent 0 in your report. Do not invent one.**
* **Collections:** everything under a collection named after your module, with `Meshes` / `Colliders` / `Lights` sub-collections.
* **Naming:** `SM_<Type>_<Variant>_<nn>`, `COL_<name>`, `INT_<building>_<room>`, `LOD1_`/`LOD2_` prefixes.
* **Instancing only** for anything repeated (linked duplicates, collection instances, GN).
* **Budget:** hero building ≤ 150k tris, regular building ≤ 40k, prop ≤ 5k, tree ≤ 8k (LOD0).

### Appending materials (copy-paste)

```python
import bpy
SRC = "/home/abdulhadi/Work/city/materials.blend"          # = /city/materials.blend

def get_materials(names):
    with bpy.data.libraries.load(SRC) as (src, dst):
        missing = [n for n in names if n not in src.materials]
        dst.materials = [n for n in names if n in src.materials]
    got = {m.name: m for m in dst.materials if m}
    if missing:
        raise RuntimeError("REQUEST THESE FROM AGENT 0: %s" % missing)
    return got

mats = get_materials(["road_asphalt_worn", "sidewalk_paving", "facade_plaster_bone"])
obj.data.materials.append(mats["road_asphalt_worn"])       # assign by exact name
```

Appending a material also pulls in any node group it uses. The two shared node groups
are standalone (your materials are clean by default), so append them explicitly:

```python
with bpy.data.libraries.load(SRC) as (src, dst):
    dst.node_groups = ["NG_EdgeWear_Dirt", "NG_ColorVariation"]
```

**Never** re-save, re-link, re-name or re-tint a library material inside your own blend —
if you need a different colour, you need a different material name; request it.

---

## 1. Colour palette — 12 colours, that is all

One palette for the whole city: **facades, signage, awnings, vehicles** (and park furniture,
doors, shutters, gates). Nature (foliage, water, soil) and neutral PBR surfaces
(asphalt, concrete, steel, glass) are *materials*, not palette colours — see §2.

| # | name | hex | primary usage |
|---|---|---|---|
| 1 | `bone` | `#E9E3D7` | Default light facade, trim, window frames, sign faces, whitewash, lane paint |
| 2 | `sand` | `#D4BD99` | Warm residential plaster, awnings, market walls, interior walls |
| 3 | `terracotta` | `#B0603C` | Market-quarter walls, clay roofs, brick-adjacent warm masses, awnings |
| 4 | `oxblood` | `#8E2F2B` | Doors, shutters, awnings, signage, deep accent walls, red vehicles |
| 5 | `mustard` | `#D9A41F` | Market/sport awnings, signage, lane-yellow, hazard stripes, taxi yellow |
| 6 | `sage` | `#7F9070` | Green-belt structures, park furniture, shutters, quiet residential accents |
| 7 | `teal` | `#2E7C74` | Signage, awnings, downtown accent bands, shopfront joinery |
| 8 | `navy` | `#263B5C` | Downtown glass tint base, corporate signage, vehicles, upholstery |
| 9 | `charcoal` | `#34373D` | Metalwork, mullions, roof plant, traffic hardware, dark signage grounds |
| 10 | `stone` | `#9B968D` | Concrete-adjacent neutral, plinths, stone bands, unpainted steel |
| 11 | `magenta` | `#D9447F` | Entertainment district: club/cinema signage and awnings (E only) |
| 12 | `violet` | `#7A4FB6` | Entertainment district: club/cinema/neon accents (E only) |

**Palette rules**

1. Any facade colour must be one of the 12 (as `facade_plaster_<name>`), brick, concrete, stucco, metal panel or timber.
2. A building gets **at most 2 palette colours + 1 neutral** (brick/concrete/timber). Ground-floor trim may be a 3rd.
3. `magenta` and `violet` are **Entertainment (E) only** — downtown stays navy/charcoal/stone, residential stays sand/bone/sage/terracotta.
4. Stripes/awnings alternate a palette colour with `bone` or `charcoal` — never two saturated colours together.
5. Vehicles: only `vehicle_paint_bone | charcoal | navy | oxblood` (+ `mustard` for one taxi variant per 20 cars). No other car colours.
6. Nature greens (`nature_leaf_dark/mid/light`) are fixed and outside the palette — do not "improve" them.

---

## 2. Material list

**93 materials + 2 node groups.** Every row below is a name that exists in
`/city/materials.blend` and in `materials_index.json`.

* **`tile_scale_m`** = metres one texture repeat covers (object-space mapping — see §3).
* **rough / metal** = nominal Principled values (roughness may be driven by a map; value is the map average).
* **source** = `polyhaven:<asset>@<res>` (real photo scan) or `procedural`.
* `base colour` is the material's representative colour — use it for placeholders and for QA colour checks.
* §2 tables are **generated** from `materials_index.json` by `modules/gen_bible_tables.py`
  — never hand-edit them; edit `modules/materials.py` and re-run instead.

### 2a. Roads & ground
<!--MATERIAL_TABLE:roads-->

| material | base colour | rough | metal | tile | emit | source |
|---|---|---|---|---|---|---|
| `road_asphalt_new` | #8E8F8F | 0.66 | 0.00 | 4.00 m |  | PH clean_asphalt@2k |
| `road_asphalt_worn` | #A0988F | 0.77 | 0.00 | 4.00 m |  | PH asphalt_01@2k |
| `road_track_asphalt` | #7E7F80 | 0.66 | 0.00 | 4.00 m |  | PH clean_asphalt@2k |
| `road_lane_paint_white` | #E9E3D7 | 0.52 | 0.00 | 2.00 m |  | proc. |
| `road_lane_paint_yellow` | #D9A41F | 0.52 | 0.00 | 2.00 m |  | proc. |
| `road_curb_concrete` | #C4BFB1 | 0.74 | 0.00 | 2.00 m |  | PH concrete_wall_008@2k |
| `sidewalk_paving` | #C0B9B0 | 0.78 | 0.00 | 1.80 m |  | PH concrete_pavement_02@1k |
| `road_cobble` | #C2BAA6 | 0.63 | 0.00 | 1.50 m |  | PH cobblestone_floor_04@1k |
| `road_manhole_metal` | #3A3C40 | 0.50 | 1.00 | 0.60 m |  | proc. |

### 2b. Facades
<!--MATERIAL_TABLE:facades-->

| material | base colour | rough | metal | tile | emit | source |
|---|---|---|---|---|---|---|
| `facade_concrete` | #C4BFB1 | 0.74 | 0.00 | 2.71 m |  | PH concrete_wall_008@2k |
| `facade_concrete_weathered` | #E8DDCE | 0.62 | 0.00 | 3.00 m |  | PH concrete_wall_003@1k |
| `facade_concrete_slab` | #D5D1CC | 0.87 | 0.00 | 2.30 m |  | PH concrete_slab_wall@1k |
| `facade_stucco` | #EDEBE9 | 0.88 | 0.00 | 2.00 m |  | PH white_stucco@1k |
| `facade_plaster_weathered` | #BAB19D | 0.87 | 0.00 | 1.80 m |  | PH worn_cracked_plaster@1k |
| `facade_brick_red` | #A89385 | 0.91 | 0.00 | 3.00 m |  | PH brick_wall_001@2k |
| `facade_timber_cladding` | #A59482 | 0.65 | 0.00 | 1.80 m |  | PH weathered_brown_planks@1k |
| `facade_plaster_bone` | #E9E3D7 | 0.91 | 0.00 | 2.23 m |  | PH plastered_wall_02@1k |
| `facade_plaster_sand` | #D4BD99 | 0.91 | 0.00 | 2.23 m |  | PH plastered_wall_02@1k |
| `facade_plaster_terracotta` | #B0603C | 0.91 | 0.00 | 2.23 m |  | PH plastered_wall_02@1k |
| `facade_plaster_oxblood` | #8E2F2B | 0.91 | 0.00 | 2.23 m |  | PH plastered_wall_02@1k |
| `facade_plaster_mustard` | #D9A41F | 0.91 | 0.00 | 2.23 m |  | PH plastered_wall_02@1k |
| `facade_plaster_sage` | #7F9070 | 0.91 | 0.00 | 2.23 m |  | PH plastered_wall_02@1k |
| `facade_plaster_teal` | #2E7C74 | 0.91 | 0.00 | 2.23 m |  | PH plastered_wall_02@1k |
| `facade_plaster_navy` | #263B5C | 0.91 | 0.00 | 2.23 m |  | PH plastered_wall_02@1k |
| `facade_plaster_charcoal` | #34373D | 0.91 | 0.00 | 2.23 m |  | PH plastered_wall_02@1k |
| `facade_plaster_stone` | #9B968D | 0.91 | 0.00 | 2.23 m |  | PH plastered_wall_02@1k |
| `facade_plaster_magenta` | #D9447F | 0.91 | 0.00 | 2.23 m |  | PH plastered_wall_02@1k |
| `facade_plaster_violet` | #7A4FB6 | 0.91 | 0.00 | 2.23 m |  | PH plastered_wall_02@1k |
| `facade_brick_painted` | #E9E3D7 | 0.91 | 0.00 | 3.00 m |  | PH brick_wall_001@2k |
| `facade_metal_panel` | #BCBEC0 | 0.38 | 0.75 | 2.00 m |  | PH painted_metal_shutter@1k |
| `facade_metal_panel_weathered` | #AEA9A9 | 0.62 | 0.60 | 2.00 m |  | PH painted_metal_shutter@1k |

### 2c. Glass
<!--MATERIAL_TABLE:glass-->

| material | base colour | rough | metal | tile | emit | source |
|---|---|---|---|---|---|---|
| `glass_clear` | #CFDCD6 | 0.04 | 0.00 | 2.00 m |  | proc. |
| `glass_tinted_office` | #20364F | 0.08 | 0.00 | 2.50 m |  | proc. |
| `glass_shop` | #DDE9E7 | 0.03 | 0.00 | 2.00 m |  | proc. |
| `glass_frosted` | #D5DBDB | 0.45 | 0.00 | 1.50 m |  | proc. |

### 2d. Metal, wood, fabric
<!--MATERIAL_TABLE:metal_wood_fabric-->

| material | base colour | rough | metal | tile | emit | source |
|---|---|---|---|---|---|---|
| `metal_steel` | #9B968D | 0.34 | 1.00 | 1.00 m |  | proc. |
| `metal_checker_plate` | #877A5D | 0.45 | 0.90 | 0.50 m |  | PH metal_plate@1k |
| `metal_rust` | #AE8473 | 0.85 | 0.30 | 2.20 m |  | PH rusty_painted_metal@1k |
| `metal_painted_charcoal` | #34373D | 0.42 | 0.00 | 1.00 m |  | proc. |
| `metal_painted_bone` | #E9E3D7 | 0.42 | 0.00 | 1.00 m |  | proc. |
| `metal_painted_teal` | #2E7C74 | 0.42 | 0.00 | 1.00 m |  | proc. |
| `metal_painted_oxblood` | #8E2F2B | 0.42 | 0.00 | 1.00 m |  | proc. |
| `metal_painted_mustard` | #D9A41F | 0.42 | 0.00 | 1.00 m |  | proc. |
| `metal_painted_sage` | #7F9070 | 0.42 | 0.00 | 1.00 m |  | proc. |
| `metal_painted_navy` | #263B5C | 0.42 | 0.00 | 1.00 m |  | proc. |
| `metal_painted_sand` | #D4BD99 | 0.42 | 0.00 | 1.00 m |  | proc. |
| `wood_planks` | #B79F82 | 0.86 | 0.00 | 1.50 m |  | PH wood_planks@1k |
| `wood_planks_weathered` | #988C84 | 0.74 | 0.00 | 2.00 m |  | PH weathered_planks@1k |
| `fabric_awning_bone` | #E9E3D7 | 0.78 | 0.00 | 1.00 m |  | proc. |
| `fabric_awning_sand` | #D4BD99 | 0.78 | 0.00 | 1.00 m |  | proc. |
| `fabric_awning_terracotta` | #B0603C | 0.78 | 0.00 | 1.00 m |  | proc. |
| `fabric_awning_oxblood` | #8E2F2B | 0.78 | 0.00 | 1.00 m |  | proc. |
| `fabric_awning_mustard` | #D9A41F | 0.78 | 0.00 | 1.00 m |  | proc. |
| `fabric_awning_sage` | #7F9070 | 0.78 | 0.00 | 1.00 m |  | proc. |
| `fabric_awning_teal` | #2E7C74 | 0.78 | 0.00 | 1.00 m |  | proc. |
| `fabric_awning_navy` | #263B5C | 0.78 | 0.00 | 1.00 m |  | proc. |
| `fabric_awning_magenta` | #D9447F | 0.78 | 0.00 | 1.00 m |  | proc. |

### 2e. Roofs
<!--MATERIAL_TABLE:roofs-->

| material | base colour | rough | metal | tile | emit | source |
|---|---|---|---|---|---|---|
| `roof_clay_tile` | #A07C5D | 0.93 | 0.00 | 4.00 m |  | PH clay_roof_tiles@1k |
| `roof_corrugated_metal` | #D5DAD8 | 0.50 | 0.65 | 1.12 m |  | PH corrugated_iron@1k |
| `roof_bitumen_flat` | #847F7D | 0.94 | 0.00 | 4.00 m |  | PH bitumen@1k |

### 2f. Nature
<!--MATERIAL_TABLE:nature-->

| material | base colour | rough | metal | tile | emit | source |
|---|---|---|---|---|---|---|
| `nature_grass` | #AFA587 | 0.94 | 0.00 | 2.51 m |  | PH grass_ground@1k |
| `nature_wild_grass` | #978751 | 0.94 | 0.00 | 2.00 m |  | PH sparse_grass@1k |
| `nature_leaf_dark` | #2F4A28 | 0.55 | 0.00 | 1.00 m |  | proc. |
| `nature_leaf_mid` | #4A7A38 | 0.55 | 0.00 | 1.00 m |  | proc. |
| `nature_leaf_light` | #7FA24A | 0.55 | 0.00 | 1.00 m |  | proc. |
| `nature_bark` | #B3A37E | 0.90 | 0.00 | 1.00 m |  | PH bark_brown_01@1k |
| `nature_dirt` | #9E886E | 0.98 | 0.00 | 2.00 m |  | PH farm_soil@1k |
| `nature_gravel` | #D1C0A9 | 0.51 | 0.00 | 2.25 m |  | PH gravel_floor@1k |
| `nature_water_lake` | #10262B | 0.04 | 0.00 | 3.00 m |  | proc. |

### 2g. Emissive
<!--MATERIAL_TABLE:emissive-->

| material | base colour | rough | metal | tile | emit | source |
|---|---|---|---|---|---|---|
| `neon_teal` | #3FF0E2 | 0.40 | 0.00 | 1.00 m | yes | proc.-emissive |
| `neon_magenta` | #FF4D94 | 0.40 | 0.00 | 1.00 m | yes | proc.-emissive |
| `neon_violet` | #A66BFF | 0.40 | 0.00 | 1.00 m | yes | proc.-emissive |
| `neon_oxblood` | #FF3B30 | 0.40 | 0.00 | 1.00 m | yes | proc.-emissive |
| `neon_mustard` | #FFC043 | 0.40 | 0.00 | 1.00 m | yes | proc.-emissive |
| `light_warm` | #FFD9A8 | 0.40 | 0.00 | 1.00 m | yes | proc.-emissive |
| `light_cool` | #DCEFFF | 0.40 | 0.00 | 1.00 m | yes | proc.-emissive |
| `sign_white` | #FFFFFF | 0.40 | 0.00 | 1.00 m | yes | proc.-emissive |

### 2h. Interiors
<!--MATERIAL_TABLE:interiors-->

| material | base colour | rough | metal | tile | emit | source |
|---|---|---|---|---|---|---|
| `int_wall_paint_bone` | #E9E3D7 | 0.82 | 0.00 | 2.00 m |  | proc. |
| `int_wall_paint_sand` | #D4BD99 | 0.82 | 0.00 | 2.00 m |  | proc. |
| `int_wall_paint_teal` | #2E7C74 | 0.82 | 0.00 | 2.00 m |  | proc. |
| `int_wood_floor` | #BCA58B | 0.47 | 0.00 | 1.70 m |  | PH wood_floor@1k |
| `int_tile_floor` | #D5CBBF | 0.70 | 0.00 | 1.90 m |  | PH interior_tiles@1k |
| `int_carpet` | #3A3630 | 0.95 | 0.00 | 0.50 m |  | proc. |
| `int_marble` | #EDEAE4 | 0.15 | 0.00 | 2.50 m |  | proc. |
| `int_upholstery` | #263B5C | 0.82 | 0.00 | 1.00 m |  | proc. |
| `int_laminate_counter` | #CDBCA8 | 0.35 | 0.00 | 1.70 m |  | PH laminate_floor_02@1k |
| `int_mirror` | #EDEDED | 0.03 | 1.00 | 1.00 m |  | proc. |

### 2i. Vehicles
<!--MATERIAL_TABLE:vehicles-->

| material | base colour | rough | metal | tile | emit | source |
|---|---|---|---|---|---|---|
| `vehicle_paint_bone` | #E9E3D7 | 0.28 | 0.25 | 1.00 m |  | proc. |
| `vehicle_paint_charcoal` | #34373D | 0.28 | 0.25 | 1.00 m |  | proc. |
| `vehicle_paint_navy` | #263B5C | 0.28 | 0.25 | 1.00 m |  | proc. |
| `vehicle_paint_oxblood` | #8E2F2B | 0.28 | 0.25 | 1.00 m |  | proc. |

### 2j. Decals
<!--MATERIAL_TABLE:decals-->

| material | base colour | rough | metal | tile | emit | source |
|---|---|---|---|---|---|---|
| `decal_puddle_wet` | #1A1D20 | 0.06 | 0.00 | 3.00 m |  | proc. |
| `decal_grime` | #2A241C | 0.90 | 0.00 | 2.50 m |  | proc. |

**If you need a material that is not here** (leaf-card alpha cutouts, grille/mesh alpha,
tyre rubber, mirror-glass, crate labels, traffic-cone orange, a sign colour outside the
palette): write it in your report as *"MISSING MATERIAL: <name> — <what for> — <where it
appears>"*. Agent 0 adds it and re-runs `modules/materials.py`. Do not build a
one-off material in your own file.

---

## 3. Texturing, texel density, UVs

**You do not need UV maps.** Every library material samples `TexCoord → Object → Mapping`
and projects images as **BOX (blend 0.12)**:

* Object space is metres (transform applied ⇒ scale baked in), so texture size is correct
  on every object at any size, and density is **identical across the whole city**.
* Walls, floors, rotated pieces and curved shapes all get non-stretched texturing.
* Height detail comes from a **Bump** node fed by the source displacement map — Bump is
  screen-space, so it works without UVs (a Normal Map node would not).

**Texel density**

| class | density | how it is achieved |
|---|---|---|
| Hero surfaces (roads, sidewalks, ground-floor facades, hero interiors) | **512 px / 2 m** (256 px/m) | 2K maps on asphalt/concrete/brick, 1K maps at ≤ 4 m tile |
| Everything else | ≥ 128 px / 2 m (128 px/m) | 1K maps at their authored real-world tile size |

`tile_scale_m` is already baked into each material's Mapping node; it comes from the
source texture's real-world `dimensions`, clamped so density never drops below 256 px/m
(2K maps give 488–757 px/m on hero surfaces). **Never** scale a Mapping node or an object
to "fix" texture size — the answer is always the material's own `tile_scale_m`.

**When you must UV unwrap** (only for your own geometry, never for library materials):
leaf cards, alpha-cutout panels, and any mesh you export to a game engine that needs UV1.
Then unwrap with **1 UV unit = 1 m** (apply scale first, then `Smart UV Project` with
island margin 0.02, or Cube Project at scale 1).

**Roughness/metallic cheat-sheet for your own hero props:** dielectrics 0.4–0.9,
metals 0.25–0.6, glass 0.03–0.1, water 0.04, polished stone 0.15. No material in the
library is pure black (0.0) or pure white (1.0) — do not do that either.

## 4. Shared node groups

Two node groups live in `materials.blend` (category `NodeGroup`). Append them the same
way as materials; never fork them — if you need different behaviour, request it (§9).

### `NG_ColorVariation`

Breaks up flat, repeated painted surfaces (plaster districts especially) without
leaving the palette. Pure value/saturation/hue shift driven by `Object Info > Random`,
so **every object gets a different shade automatically** — no per-object work.

| socket | type | range | default | meaning |
|---|---|---|---|---|
| `Base Color` | color | — | 0.5 grey | your palette colour (post-albedo) |
| `Variation` | float | 0–0.5 | 0.12 | strength; 0 = none, 0.12 subtle, 0.35 strong |
| `Seed` | float | 0–10 | 0.0 | per-object offset (use to split two adjacent masses) |
| → `Color` | color | — | — | varied colour, hue clamped ±3.6° so palette stays valid |

Use on: every `facade_plaster_*`, `metal_painted_*`, `fabric_awning_*`,
`vehicle_paint_*`, `int_wall_paint_*`. Wire albedo → `Base Color`, output → Principled
`Base Color`. Never above 0.35 — beyond that the district palette dissolves.

### `NG_EdgeWear_Dirt`

Grime and sun-bleach layer with **zero UVs**. Mask = large noise patches × up-facing
bias (dust settles on tops) for dirt; pointiness (Cycles) OR fine noise (EEVEE) for
edge wear. Both engines produce a sensible result; EEVEE's is noise-driven only.

| socket | type | range | default | meaning |
|---|---|---|---|---|
| `Base Color` | color | — | 0.5 grey | albedo in (image output or flat colour) |
| `Roughness` | float | 0–1 | 0.7 | nominal roughness; dirt raises it (+0.2), wear lowers it (−0.1) |
| `Wear` | float | 0–1 | 0.35 | edge wear / sun-bleach amount |
| `Dirt` | float | 0–1 | 0.4 | grime amount |
| `Dirt Color` | color | — | warm near-black | grime tint |
| `Scale` | float | 0.25–32 | 2.0 | metres per dirt feature (object space) |
| → `Color` | color | — | — | final albedo |
| → `Roughness` | float | — | — | final roughness |

Wire `Color` → Principled `Base Color` and `Roughness` → Principled `Roughness`.

**Per-district `Wear` / `Dirt` (use these, do not invent your own):**

| district | Wear | Dirt | note |
|---|---|---|---|
| R Residential | 0.30 | 0.25 | kept-up areas, low grime |
| D Downtown | 0.25 | 0.30 | glass/stone towers stay clean; only podiums get dirt |
| E Entertainment | 0.35 | 0.40 | neon-lit grime, spill from signage |
| M Market | 0.45 | 0.55 | the dirtiest district — awnings, cobble, plaster |
| G Green belt | 0.35 | 0.20 | dust and pollen, no urban grime |
| I Industrial | 0.50 | 0.60 | rust streaks, soot; pair with `decal_grime` |
| T Race circuit | 0.40 | 0.30 | tyre rubber (near-black `Dirt Color`), marbles off-line |

`Scale`: 4–8 m for large buildings, 1–2 m for street furniture and vehicles.
Roads use the material's own roughness map instead — do not stack the node group on
`road_asphalt_*`.

## 5. District facade rules

Every parcel in `layout.json` carries `facade_style` from the generator's list; these
are binding. Ground floor ≠ upper floors: **ground floor is always retail/civic
language** (shopfront glass, signage band, canopy), upper floors follow the style.

### R — Residential (`suburban_brick`, `stucco_modern`, `timber_cottage`, `modern_minimal`)

| style | ground floor | upper floor | roof | accent |
|---|---|---|---|---|
| `suburban_brick` | `facade_brick_red` + `glass_clear` | `facade_brick_red` | `roof_clay_tile` | `metal_painted_charcoal` rails |
| `stucco_modern` | `facade_plaster_bone` or `_sand` | same (vary with `NG_ColorVariation`) | `roof_bitumen_flat` | `wood_planks` door, `metal_steel` guard |
| `timber_cottage` | `facade_timber_cladding` | `facade_timber_cladding` | `roof_clay_tile` | `fabric_awning_sage` porch |
| `modern_minimal` | `facade_plaster_stone` + tall `glass_clear` | `facade_plaster_bone` | `roof_bitumen_flat` | `metal_painted_charcoal` fins |

Palette per street: pick **one** of bone/sand/sage/terracotta for a row; never mix
two loud colours on one frontage. `facade_plaster_*` + `NG_ColorVariation` at 0.12 is
the default wall treatment.

### D — Downtown core (`glass_curtain`, `steel_stone`, `art_deco`, `brutalist_modern`)

| style | ground floor | shaft / upper | roof | notes |
|---|---|---|---|---|
| `glass_curtain` | `glass_shop` in `metal_painted_charcoal` mullions | `glass_tinted_office` | `roof_bitumen_flat` + plant | mullion module 1.5 m, floor-to-floor 3.9 m |
| `steel_stone` | `facade_concrete` + `glass_shop` | `facade_concrete` bands + `glass_tinted_office` spandrels | `roof_bitumen_flat` | stone band every 3 floors |
| `art_deco` | `facade_plaster_sand` + `glass_shop` | `facade_plaster_bone`, vertical `metal_painted_mustard` flutes | stepped `roof_bitumen_flat` | setbacks at floor 8, 14; flutes to parapet |
| `brutalist_modern` | `facade_concrete_slab` | `facade_concrete_slab` | exposed `metal_rust` plant | deep reveals, no colour accents |

Towers ≥ 20 floors: `glass_tinted_office` for the shaft, `facade_concrete` podium
3–5 floors. Never `facade_plaster_*` above floor 8.

### E — Entertainment strip (`neon_modern`, `brick_loft`, `glass_retail`)

| style | ground floor | upper | roof |
|---|---|---|---|
| `neon_modern` | `facade_metal_panel` + full-height `glass_shop` + neon bands | `facade_metal_panel` (charcoal/teal) | `roof_bitumen_flat`, roof neon |
| `brick_loft` | `facade_brick_red` + `glass_shop` | `facade_brick_red`, `metal_rust` balconies | `roof_bitumen_flat` |
| `glass_retail` | `glass_shop` (double height) | `facade_plaster_bone` or `facade_metal_panel` | `roof_bitumen_flat`, lightbox signage |

Every E frontage carries ≥ 1 emissive sign (`neon_teal`/`neon_magenta`/`neon_violet`)
plus `fabric_awning_*` on cafés. `magenta` and `violet` are legal **only** here.

### M — Market quarter (`old_bazaar_brick`, `painted_plaster`, `timber_balcony`)

| style | ground floor | upper | roof |
|---|---|---|---|
| `old_bazaar_brick` | arched `facade_brick_red` openings + `glass_shop` | `facade_brick_red` | `roof_clay_tile`, deep eaves |
| `painted_plaster` | `facade_plaster_*` (terracotta, oxblood, mustard, teal) | same colour, `NG_ColorVariation` 0.20 | `roof_clay_tile` |
| `timber_balcony` | `facade_plaster_weathered` + shop | `facade_plaster_*` + `wood_planks_weathered` balcony | `roof_clay_tile` |

Ground surfaces: `road_cobble` in all M alleys. Awnings mandatory on shops
(`fabric_awning_*`, striped by splitting geometry). 1 m parapet eaves everywhere.

### I — Industrial (`corrugated_metal`, `concrete_block`)

| style | walls | roof | notes |
|---|---|---|---|
| `corrugated_metal` | `facade_metal_panel_weathered` | `roof_corrugated_metal` | `metal_rust` flashings, `metal_checker_plate` doors |
| `concrete_block` | `facade_concrete_weathered` | `roof_bitumen_flat` | `facade_concrete_slab` office end, small `glass_frosted` strip |

Yards: `nature_gravel` or worn `nature_dirt`. No plaster, no clay tile. Use
`decal_grime` along wall bases and `NG_EdgeWear_Dirt` at Dirt 0.6.

### G — Green belt

No district facade styles — only pavilions and bandstands: `facade_timber_cladding`
or `facade_stucco`, `roof_clay_tile`, `wood_planks` decks. `nature_grass` ground,
`nature_wild_grass` verges, `nature_gravel` paths, `nature_bark` trunks,
`nature_leaf_dark/mid/light` canopies.

### T — Race circuit (`motorsport_modern`)

`facade_metal_panel` + `glass_tinted_office` grandstand glazing, `facade_concrete`
walls, `metal_rust` barriers, `road_track_asphalt` surface, `road_lane_paint_white`
lines only (no yellow on track), `nature_gravel` run-off, `metal_painted_oxblood`
/ `_mustard` kerb furniture. Pit garages: `facade_concrete_slab` + `metal_steel`
roller shutters.

## 6. Signage & graphics

* **Bands, not boxes.** Signs are thin plates (0.08–0.15 m deep) mounted on a
  structural band between ground and first floor; project 0.4–0.6 m max.
* **Faces:** `sign_white` (lightbox) or a flat palette colour; letters/graphics are
  **geometry** (extruded 0.02 m) or emissive strips — never image decals with text.
* **Emissive tube language:** `neon_*` cylinders Ø 0.03 m for outlines and arrows;
  horizontal runs under canopies; vertical runs only on E strip club frontages.
* **Colours:** letters in palette colours on neutral faces. Sign glow colours
  limited to `neon_teal`, `neon_magenta`, `neon_violet` (E only), `neon_oxblood`,
  `neon_mustard`, `sign_white`, `light_warm`, `light_cool`.
* **Density:** R ≤ 1 sign per shopfront; M one hanging sign + awning per shop;
  D shopfront lettering only above floor 8 (tenant logo on the parapet);
  E as many as look good, but keep 0.6 m clear around doors.
* **Billboards:** flat `sign_white`/charcoal faces on blank walls and roofs, 6×3 m
  typical; emissive at night via the §7 multipliers.
* Never place signage materials on roofs, roads, or vehicles.

## 7. Time of day

Scene is authored in **daylight**; night is achieved by light and emissive
multipliers only — no material is rebuilt.

| pass | sun | sky | view transform | emissive multiplier |
|---|---|---|---|---|
| **Day (hero)** | 5500 K, elevation 38°, azimuth from SW, strength 3.5 | Nishita, air 1.0, dust 0.6, ozone 1.0 | **Standard** (no Filmic/AgX — palette must read true) | ×1.0 (neon 6, lights 8, sign 5) |
| **Golden** | 3200 K, elevation 6° | Nishita, dust 2.0 | Standard | ×1.2 |
| **Dusk** | below horizon, 0.3 | Nishita, elevation −6°, strength 0.15 | Standard | ×3 |
| **Night** | none (moon 0.05 cool fill only) | dark blue ambient 0.02 | Standard | ×8 neon, ×6 interior `light_*`, ×5 `sign_white` |

Rules:

* Emissive strengths stored in the blend are the **day** values; the lighting agent
  scales them (or the whole `emissive` category) for other passes — never edit the
  materials.
* Window interiors: `light_warm` in R/M homes and restaurants, `light_cool` in D
  offices and retail; ~35 % of windows lit at night, randomised, never 100 %.
* Neon signs: E strip only at ≥ 1 sign per frontage; elsewhere single shop signs.
* Bloom/glare: mild, threshold just above the day values; the night pass gets the glow.
* Wet-street night look: scatter `decal_puddle_wet` on flat road areas, and drop
  `road_asphalt_*` roughness globally by ×0.75 **in the lighting scene only**, never
  in the library.

## 8. QA checklist (run before any hand-off)

1. All object scales applied (`Ctrl+A`), transforms clean — object space = metres.
2. No custom image textures: every material appended **by name** from
   `/city/materials.blend`. Missing name ⇒ request it (§9); do not improvise.
3. No UV maps on plain geometry (leaf cards / alpha panels excepted, §3).
4. Palette check: every colour you authored is one of the 12 (§1); `magenta`/
   `violet` only inside E.
5. `NG_ColorVariation` present on painted surfaces, `Variation ≤ 0.35`.
6. Dirt/Wear match the district table (§4); roads free of the node group.
7. Emissive strength is the day value from §2g; night handled in lighting.
8. No pure black/white surfaces; roughness within the §3 cheat-sheet.
9. Render 1920×1080, Standard view transform, check for stretching at building
   corners (box projection should hide seams — if you see streaks, scale was not
   applied).

## 9. Missing material / change request

Need a material that is not in §2? Do **not** create one. Post a request with:

1. **Name** (snake_case, `category_role_variant`, e.g. `facade_metal_brushed`).
2. **Category** (roads / facades / glass / metal_wood_fabric / roofs / nature /
   emissive / interiors / vehicles / decals).
3. **Where it is used** (district + building type + which geometry).
4. **Look:** palette colour (hex from §1) or a PolyHaven texture set + resolution.
5. **Numeric intent:** roughness, metalness, `tile_scale_m`, emissive colour+strength
   if any, and whether `NG_EdgeWear_Dirt`/`NG_ColorVariation` should be applied.

The materials owner adds it to `SPECS` in `city/modules/materials.py`, re-runs the
script headless, and republishes `materials.blend`, `materials_index.json` and this
file's §2 tables. Until then, pick the closest existing material and note it in your
hand-off.

---

# PART B — CONTRACT MATERIAL SET (`materials.json`, 64 names)

Two authoring passes share this folder, so this file documents both:

| index | names | who | where |
|---|---|---|---|
| `materials_index.json` | 93 (`road_*`, `facade_*`, `nature_*`, …) | §1–§9 above | `modules/materials.py` |
| `materials.json` | **64 contract names** (`asphalt`, `brick_red`, `glass_shop`, …) | this Part B | `modules/materials_lib.py` |

`materials.blend` contains **both** sets (155 materials) plus **both** node-group pairs
(`NG_EdgeWear_Dirt`/`NG_ColorVariation` and `City_EdgeWear`/`City_Variation`), so either
name list can be appended from the same file. Only `glass_shop` and `metal_steel` exist in
both — the contract definition is the one that ships. Preview of the 64:
`out/materials_preview.png`. Helpers: `modules/citykit.py` (`ck.append_material(name)`).

## B.1 Contract palette → §1 palette

The city has **one** 12-colour palette (§1). The contract set's material colours map onto it:

| contract colour | hex | §1 entry | where the contract set uses it |
|---|---|---|---|
| Asphalt Graphite | `#2E3236` | `charcoal` | `asphalt*`, `roof_bitumen`, `metal_painted_dark` |
| Concrete Grey | `#B9BDC0` | `stone` | `curb_concrete`, `sidewalk_concrete`, `paving_slab`, `concrete*` |
| Warm Off-White | `#E8E2D6` | `bone` | `plaster_white`, `wall_paint`, `ceiling_paint`, `marking_white`, `wood_painted` |
| Terracotta Brick | `#B5471F` | `terracotta` | `brick_red`, `roof_tile_red`, `plaster_ochre` |
| Timber Brown | `#8C5A2B` | `sand` | `wood_old`, `bark`, `floor_wood` |
| Pine Green | `#2F4A3C` | `sage` | `awning_fabric_green`, `leaves_dark` |
| Aged Brass | `#C8A24A` | `mustard` | art-deco trim, `kerb_yellow`, `marking_yellow` |
| Deep Steel Blue | `#1B2A4A` | `navy` | `glass_office` tint, `water` |
| Signal Red | `#E94F37` | `oxblood` | `neon_red`, `awning_fabric_red`, `kerb_red` |
| Electric Cyan | `#29B6F6` | `teal` | `neon_blue` |
| Warm Lamplight | `#F5D36B` | `light_warm` | `emissive_warm` windows and lamps |
| Night Ink | `#14161A` | `charcoal` | `metal_painted_dark`, `glass_dark`, night sky |

No 13th colour, ever. `magenta`/`violet` stay Entertainment-only (§1 rule 3).

## B.2 Complete material list — 64 names

### Ground / road (16)
| name | look |
|---|---|
| `asphalt` | mid-grey city road, fine aggregate (CC0 `asphalt_01`) |
| `asphalt_worn` | older patchy bleached road (CC0 `worn_asphalt`) |
| `asphalt_highway` | darker smoother highway with tar seams (CC0 `asphalt_02`) |
| `track_asphalt` | fine dark race surface (CC0 `asphalt_track`) |
| `marking_white` | crisp white lane/stop/zebra paint |
| `marking_yellow` | solid / turn-lane yellow paint |
| `curb_concrete` | pale precast kerb, chamfer line (CC0 `concrete_floor_01`) |
| `kerb_red` | red no-parking kerb, worn paint |
| `kerb_white` | white kerb, slightly dirty |
| `kerb_yellow` | yellow loading-zone kerb |
| `sidewalk_concrete` | footway slabs with joints (CC0 `concrete_floor_01`) |
| `paving_slab` | large grey paving plates (CC0 `concrete_tiles`) |
| `cobble_stone` | rounded setts, grouted (CC0 `cobblestone_floor_05`) |
| `gravel` | loose grey-brown gravel (CC0 `bicolour_gravel`) |
| `dirt` | packed tyre-worn earth (CC0 `dirt_floor`) |
| `sand` | dry pale sand, track run-off |

### Vegetation ground (2)
| `grass` | mown park lawn (CC0 `grass_ground`) |
| `grass_dry` | sun-scorched straw verge |

### Facade / wall (13)
| `brick_red` | red clay brick, grey mortar (CC0 `brick_wall_001`) |
| `brick_brown` | brown/salmon older bond (CC0 `brown_brick_02`) |
| `brick_whitewash` | whitewashed brick (CC0 `castle_brick_02_white`) |
| `plaster_white` | clean smooth render, Warm Off-White |
| `plaster_cream` | warm cream residential render |
| `plaster_ochre` | ochre/sand market render |
| `stucco_grey` | cool grey modern stucco (CC0 `grey_plaster_02`) |
| `stone_grey` | ashlar grey blocks, recessed joints (CC0 `stone_wall`) |
| `marble_white` | polished veined marble, roughness 0.18 (CC0 `marble_01`) |
| `concrete` | board-formed structural concrete (CC0 `concrete_floor_01`) |
| `concrete_poured` | raw poured concrete, pour lines + form-tie holes |
| `wall_paint` | generic painted wall (Warm Off-White) |
| `ceiling_paint` | near-white flat ceiling, roughness 0.9 |

### Glass / metal (8)
| `glass_office` | Deep Steel Blue curtain wall, alpha 0.45 (blended) |
| `glass_shop` | clear shopfront glass, alpha 0.30 |
| `glass_dark` | smoked spandrel/automotive, alpha 0.72 |
| `metal_steel` | brushed galvanised steel, metallic 1, roughness 0.34 |
| `metal_chrome` | polished chrome trim, roughness 0.09 |
| `metal_painted_dark` | Night Ink powder coat (frames, railings) |
| `metal_rusty` | corroded steel with orange scale (CC0 `rusty_metal`) |
| `rust` | pure rust patch for accents |

### Roof (4)
| `roof_tile_red` | terracotta pantile (CC0 `clay_roof_tiles`) |
| `roof_metal` | standing-seam/corrugated metal (CC0 `corrugated_iron`) |
| `roof_bitumen` | flat-roof felting with gravel speckle |
| `roof_shingle` | asphalt shingle courses, brick-node rows |

### Timber (3)
| `wood_old` | weathered grey-brown planks (CC0 `wood_planks`) |
| `wood_painted` | painted joinery, slight sheen |
| `bark` | vertical fissured tree bark |

### Interior (3 + shared) — `floor_wood` (CC0 `wooden_floor_01`), `floor_tile` (CC0 `floor_tiles_02`),
`floor_carpet` (CC0 `dirty_carpet`); walls/ceiling use `wall_paint` / `ceiling_paint` / `marble_white`.

### Signage / fabric / emissive (12)
| `sign_metal` | brushed satin sign panel |
| `awning_fabric_red` | red canvas awning with weave bump |
| `awning_fabric_green` | green canvas awning |
| `awning_fabric_stripe` | red/white wave-texture stripes |
| `canvas_tarp` | dirty tarpaulin with creases |
| `neon_red` | **emissive** tube, strength 2.0 (day value) |
| `neon_blue` | **emissive** tube, strength 2.0 |
| `neon_green` | **emissive** tube, strength 2.0 |
| `neon_pink` | **emissive** tube, strength 2.0 |
| `emissive_warm` | **emissive** 2700 K window/lamp glow, strength 1.5 |
| `emissive_cool` | **emissive** 5000 K office glow, strength 1.5 |
| `water` | dark teal pond/canal, roughness 0.03 |

### Vegetation (2) — `leaves_green`, `leaves_dark` (noise-ramp canopy greens, hue-varied per object).

### Utility (1) — `col_placeholder` magenta diagnostic colour.

**Total 64.** Emissive flag list lives in `materials.json["emissive"]` (6 names) and in
`materials.json["detail"][name]["emissive"]`.

## B.3 Node groups — `City_EdgeWear` / `City_Variation`

Both are in `materials.blend`; every one of the 64 materials already runs
`City_Variation → City_EdgeWear → Principled`, so you normally never wire them yourself.
Append them with `dst.node_groups = ["City_EdgeWear", "City_Variation"]` if you build a
procedural material of your own.

### `City_Variation`
| socket | type | default | meaning |
|---|---|---|---|
| `Base` (in) | color | 0.5 grey | your albedo |
| `Amount` (in) | float 0–0.5 | 0.15 | strength; hue ±3 %, value ±8 %, saturation ±5 % |
| `Result` (out) | color | — | per-object varied colour (Object Info > Random) |

### `City_EdgeWear`
| socket | type | default | meaning |
|---|---|---|---|
| `Base` (in) | color | 0.5 grey | albedo in |
| `Wear` (in) | float 0–1 | 0.35 | grime/edge wear amount (noise mask × Wear + AO cavities) |
| `Dirt` (in) | color | `#0E0D0C` | grime tint |
| `Result` (out) | color | — | weathered albedo |

Wear levels: clean interior 0.10 · maintained facade 0.30 · ground/road 0.60 ·
derelict/industrial 0.85 (already baked per material; see `materials.json["detail"][n]["wear"]`).

## B.4 Facade rhythm (window/module rules per `facade_style`)

| district | style | window module | notes |
|---|---|---|---|
| R | `suburban_brick` | 1.2 m openings @ 2.4 m centres, 2 rows/floor, sill 0.9 m | `brick_red` + `wood_painted` lintels, 0.15 m plinth |
| R | `stucco_modern` | 2.6 × 1.5 m ribbon slots per 3.2 m floor | `stucco_grey`/`plaster_cream`, 0.1 m reveal bands |
| R | `timber_cottage` | paired 0.9 m sash @ 1.8 m, shutters optional | `plaster_white` wainscot to 1.0 m, 0.4 m eaves |
| R | `modern_minimal` | 2.8 m full-height glazing per 3.0 m bay | `concrete_poured`, 0.05 m shadow gaps |
| D | `glass_curtain` | 1.5 m mullion spacing, 0.9 m spandrel / 3.2 m floor | `glass_office` + `metal_steel` |
| D | `steel_stone` | punched 1.6 × 2.2 m @ 3.0 m, 0.25 m reveals | `stone_grey` podium, `marble_white` lobby |
| D | `art_deco` | 1.0 m vertical strip windows, pilaster piers | brass/`metal_chrome` fluting, setback above L4 |
| D | `brutalist_modern` | 2.0 m recessed bands @ 3.2 m, 0.6 m deep | board-formed `concrete`, `glass_dark` |
| E | `neon_modern` | 3.0 m shopfronts, 2.2 m upper ribbon | `metal_painted_dark` + neon floor-line runs |
| E | `brick_loft` | 2.4 × 2.6 m industrial sash @ 3.6 m | `brick_red`, black `metal_steel` frames |
| E | `glass_retail` | double-height 3.6 m ground floor | `sign_metal` fascia at 3.4 m |
| M | `old_bazaar_brick` | 2.4 m arches, 2.0 m wide, 1-storey arcade | `brick_brown`/`stone_grey` piers |
| M | `painted_plaster` | 1.1 m windows, 4 per 8 m frontage | one palette colour per parcel, shutters |
| M | `timber_balcony` | French doors 1.6 m @ 2.4 m, 1.1 m balcony | `wood_old` balcony from 1st floor |
| I | `corrugated_metal` | 1.2 m clerestory at 4.5 m; 4.0 m roller doors | `roof_metal` cladding, `rust` at base |
| I | `concrete_block` | 0.9 m punched @ 4.0 m, 3.6 m floor | `concrete` CMU, `metal_steel` lintels |
| T | `motorsport_modern` | 4.5 m clear openings, 1.6 m paddock ribbon | `concrete_painted_dark`, `kerb_red` banding |

Floor height 3.2 m, door/opening head 2.4 m everywhere.

## B.5 Signage numbers (supplements §6)

* Fascia sign: panel 0.6–0.9 m tall, centred **3.4 m** above sidewalk, ≤ 90 % of frontage.
* Blade/projecting sign: 1.2 × 0.6 m, brackets project 1.0 m, **bottom edge 2.8 m** (never below the 2.4 m door head).
* Window vinyl ≤ 0.6 m tall, ≤ 35 % of the glazing. Billboard 6 × 3 m, 1.0 m post clearance.
* Letter cap-height 0.25 m fascia / 0.15 m blade; never scale text non-uniformly.
* Glow colours: `neon_red|blue|green|pink`, `emissive_warm` (hospitality), `emissive_cool` (offices/transit).
  Library stores the **day** value (neon 2.0, lamps 1.5); the lighting pass multiplies
  ×4–8 for night (§7).

## B.6 Time of day (supplements §7)

* **Day / golden hour (default look):** sun elevation 12°, azimuth 295°, colour `#FFD9A8`,
  strength ~4.0; sky `#8FB4E0` → `#FFD8A8` at horizon, strength 0.6; long shadows to the ESE.
* **Night:** sun 0, sky `#0A0E1A` @ 0.05, practicals only — street lamps `emissive_warm`,
  ~30 % of residential windows warm / ~25 % of office floors `emissive_cool`, signage at
  the §7 multipliers. Never mix day and night in one scene.

## B.7 Texel density & shared weathering (supplements §3/§4)

* **512 px per 2 m = 256 px/m**; a 1024 px texture covers **4 m** (roads/highways 8 m).
  Each material's Mapping scale is already baked in — do not rescale Mapping nodes.
* Bricks must read ~0.22 × 0.07 m; no stretched UVs; road markings are geometry, not texture.
* Mandatory chain for exterior surfaces: **albedo → `City_Variation` → `City_EdgeWear` →
  Principled Base Color**, roughness ±0.1 per object from Object Info Random.
  Wear: interior 0.1 / facade 0.3 / ground 0.6 / derelict 0.85.
