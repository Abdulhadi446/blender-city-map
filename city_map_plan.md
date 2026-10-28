# AAA City Map: Blender MCP + Subagents Build Plan

A full playable-looking city built in Blender through the Blender MCP, using parallel subagents.
Target: "5-star studio game" quality, game-engine ready (Unity / Unreal / Godot).

---

## 0. Goal

Build a dense, explorable city map that includes:

- Houses (some with interiors, some without doors but enterable)
- Offices, hotels, gyms, restaurants, shops (all enterable, no door meshes, with interiors)
- Markets with deep, narrow streets and covered alleys
- Roads, streets, alleys, intersections, traffic lights, crosswalks, signs
- Flyovers and a highway ring
- Parks, trees, grass, a lake, jogging paths
- A race track with pits and grandstands
- The entire map filled: no empty gray plane anywhere

**Rule for "no doors":** every enterable building gets a wide open archway, an open storefront, or a missing-glass frontage instead of a door object. No door animation needed. Interiors sit directly behind the opening.

---

## 1. Architecture and the parallelism catch (READ THIS FIRST)

The Blender MCP addon runs a socket server inside Blender (JSON over TCP, default port 9876).
Blender's Python API (`bpy`) is **not thread-safe**. If several subagents all send `execute_blender_code` into the **same live Blender session**, they will collide, fail, or corrupt the scene.

**Therefore:**

1. Subagents do **not** live-drive the master scene.
2. Each subagent **writes a Python module to a file** and runs it in its **own headless Blender**:
   ```
   blender -b -P /city/modules/<name>.py
   ```
   Output: `/city/out/<name>.blend`
   (Alternative: run several Blender instances, each with the addon on a different port.)
3. One **Assembler** agent is the only one allowed to touch the master scene through the MCP. It appends/links all `/city/out/*.blend` files into `city_master.blend`.
4. Everyone follows the **Global Contract** (section 2).
5. **Save before every `execute_blender_code` call.** It runs arbitrary Python and is irreversible.
6. Send code in small chunks, not giant scripts, when using live MCP.

```
Orchestrator
 ├─ Agent 0   Layout + style bible          (runs first, alone)
 ├─ Roads, Flyovers                         (run second; everything snaps to them)
 ├─ Parallel: Traffic, Track, Nature, Residential, Commercial,
 │            Market, Interiors, Props, Lighting
 ├─ Assembler                                (merges)
 └─ QA agent                                 (checks, fixes, screenshots)
```

---

## 2. Global Contract (paste into EVERY subagent prompt)

```
UNITS: metres. 1 Blender unit = 1 m. Z-up. Apply all transforms before saving.
ORIGIN: every kit piece origin at bottom-centre.
SCALE RULES: door/opening height 2.4 m, lane width 3.5 m, sidewalk 2.5 m,
             floor height 3.2 m, curb height 0.15 m.
LAYOUT: read /city/layout.json. Work ONLY inside your assigned zone/ids.
        Do NOT touch other zones.
OUTPUT: script  -> /city/modules/<name>.py
        blend   -> /city/out/<name>.blend
        preview -> /city/out/<name>_preview.png (rendered, 1920x1080)
COLLECTIONS: everything under a collection named after your module.
             Sub-collections: Meshes, Colliders, Lights.
MATERIALS: ONLY from /city/materials.blend (append, never create new ones).
           If a material is missing, request it in your report instead.
NAMING: SM_<Type>_<Variant>_<nn>  static mesh
        COL_<name>                collision proxy
        INT_<building>_<room>     interior piece
        LOD1_/LOD2_ prefix        lower detail variants
INSTANCING: use linked duplicates / collection instances / Geometry Nodes
            instancing for anything repeated. Never unique copies.
BUDGET: report triangle count for your module. Hero buildings <= 150k tris,
        regular buildings <= 40k, props <= 5k, trees <= 8k (LOD0).
RUN: headless (blender -b -P). Never call execute_blender_code on the
     master scene. Only the Assembler does that.
REPORT BACK: file paths, triangle count, object count, known issues,
             list of materials used, anything you need from other agents.
```

---

## 3. Map layout

**Size:** 3 km x 3 km, on a 10 m grid. Origin at map centre.

| District | Contents | Approx. area |
|---|---|---|
| **Downtown core** | Towers, offices, hotels, central plaza, main interchange | centre |
| **Market quarter** | Dense narrow streets, covered bazaar, stalls, restaurants, alleys | NE |
| **Residential** | Houses, low apartments, tree-lined streets, pocket parks | W and SW |
| **Entertainment strip** | Gyms, restaurants, cinema, hotels, neon signage | along main arterial |
| **Green belt** | Big park, lake, jogging paths, playgrounds, sports fields | S and SE |
| **Race / industrial** | Circuit track, pits, grandstands, warehouses | E / outskirts |
| **Highway ring** | Elevated ring road with flyovers into downtown | perimeter |

**Road hierarchy:**

1. Highway ring (elevated, 3 lanes each way)
2. Arterials (2 lanes each way, median, traffic lights)
3. Streets (1 lane each way, parked cars)
4. Alleys / "deep streets" (market and residential, 4 to 6 m wide, pedestrian-first)

No dead empty land. Every block gets a building, park, plaza, parking lot, or industrial yard.

---

## 4. Build phases

### Phase A: Foundation (sequential, one agent)
1. Agent 0 produces `/city/layout.json`: blocks, road graph, parcel list (id, district, footprint, building type, enterable flag, interior tier).
2. Agent 0 produces the **style bible** and `/city/materials.blend`.
3. Master collection tree created: `Roads`, `Flyovers`, `Buildings`, `Interiors`, `Vegetation`, `Props`, `Traffic`, `Track`, `Lighting`, `Colliders`.

### Phase B: Infrastructure (sequential)
Roads, then Flyovers. Everything else snaps to road edges and parcel boundaries.

### Phase C: Parallel content (all at once)
Traffic, Track, Nature, Residential, Commercial, Market, Interiors, Props, Lighting.

### Phase D: Assembly and polish
Assembler merges, QA runs checks, fix loop, lighting pass, export.

---

## 5. Interiors strategy (tiers)

Fully furnishing every building will blow the poly budget and agent time.

| Tier | Count | What you get |
|---|---|---|
| **Tier 1 (hero)** | 30 to 40 | Fully furnished: offices, hotel lobby and rooms, gyms, restaurants, key shops, a few homes |
| **Tier 2** | ~150 | Shell interior with one furnished room and a simple floor plan behind the opening |
| **Tier 3** | the rest | Facade and exterior only, with blinds or glass, plus interior-mapped fake depth if needed |

**Interior kits needed:**
- Office: open floor, desks, cubicles, meeting room, reception
- Hotel: lobby, reception desk, corridor, bedroom, bathroom
- Gym: machines, free weights, mats, mirrors, lockers
- Restaurant: tables, booths, bar, kitchen pass-through
- Shop: shelves, counter, displays, storage nook
- Home: living room, kitchen, bedroom, bathroom

Assets can come from PolyHaven (models, textures, HDRIs) and Sketchfab through the MCP, plus AI generation (Hyper3D Rodin / Hunyuan3D) for hero props. **Check Sketchfab licences before shipping.**

---

## 6. "AAA / big-corp" quality bar

- **Strict palette and materials.** A limited PBR material library; no random colours.
- **Prop density.** Bins, cables, signs, planters, parked cars, bikes, hydrants, awnings, AC units, vents. This sells realism more than anything else.
- **Variation.** Parametric buildings, random rotation and scale on trees, multiple facade textures per building type, colour variation through a shared node group.
- **Road detail.** Lane wear, manhole covers, cracks, puddle decals, crosswalk paint, tyre marks near lights.
- **Weathering.** Shared edge-wear and dirt node group.
- **Lighting.** HDRI sky, soft sun, volumetric haze, emissive signage, warm interior lights visible through openings, a night variant.
- **Composition.** Landmarks (tall tower, stadium, plaza fountain), clear sightlines down main streets, silhouette variety on the skyline.
- **Consistency.** Same style, same scale, same texel density everywhere.

---

## 7. Game-ready checklist

- Naming prefixes (see contract).
- Collision proxies (`COL_`) for roads, buildings, track, barriers.
- LODs for buildings, trees, and props.
- Instances for repeated assets.
- Clean UVs, consistent texel density, baked atlases per district.
- Export per district chunk (glTF or FBX), not one giant file, so the engine can stream it.
- Provide a `manifest.json`: district, file, tri count, bounding box.
- Navmesh-friendly: sidewalks, crossings, and paths on separate collections.

---

## 8. Subagent prompts

Every prompt below assumes the **Global Contract** from section 2 is prepended.

### Agent 0: Layout + Style Bible

```
You are the City Layout agent. Produce:
1. /city/layout.json with: districts (polygon + type), road graph
   (nodes, edges, hierarchy: highway/arterial/street/alley, lane count),
   parcels (id, district, footprint polygon, building type, enterable flag,
   interior tier 1/2/3, floors), park zones, track path, flyover paths,
   traffic-light positions (every arterial intersection).
2. /city/style_bible.md: colour palette (max 12 colours), material list,
   facade styles per district, signage style, time-of-day target.
3. /city/materials.blend: PBR material library (asphalt, concrete, brick,
   glass, metal, wood, grass, leaves, paint variants, fabric, tile) using
   PolyHaven textures where possible.
Map: 3x3 km, 10 m grid. Fill EVERY block with a use. No empty land.
Verify layout.json parses and has no overlapping parcels, then stop.
```

### Roads agent

```
Build the full road network from layout.json.
- Curve-based roads converted to meshes, with lane markings, medians,
  sidewalks, curbs, crosswalks, intersections (proper corner radii).
- Hierarchy: highway ring, arterials, streets, alleys.
- Alleys in the market quarter are 4 to 6 m, with cobble or tile material.
- Add manhole covers, gutters, and road wear decals.
- Export road centre-lines and edges to /city/out/road_edges.json so other
  agents can snap to them.
Output: /city/out/roads.blend
```

### Flyover agent

```
Build the elevated highway ring and 2 to 3 interchange flyovers from layout.json.
- Deck, pillars, barriers, expansion joints, lane markings, ramps with
  proper gradient (max 6%), lighting poles.
- Pillar base must land on ground road edges, not through buildings.
- Add collision proxies for deck and barriers.
Output: /city/out/flyovers.blend
```

### Traffic agent

```
Place traffic infrastructure using road_edges.json.
- Traffic light poles and heads at every arterial intersection, with
  pedestrian signals and stop lines.
- Street lights, road signs (speed, stop, direction), bus stops, crosswalk signs.
- Parked cars along streets (instanced from a car kit with colour variation).
- Emissive materials on lights so the Lighting agent can toggle night mode.
Output: /city/out/traffic.blend
```

### Race track agent

```
Build a circuit in the Race/industrial zone.
- Spline-based track (about 3 km), kerbs, run-off areas, tyre barriers,
  catch fencing, pit lane, pit garages (open front, no doors), start/finish
  gantry, grandstands, scoreboard, sponsor billboards (generic brands only).
- Track surface material with racing line wear and tyre marks.
- Collision proxies for barriers and track edges.
Output: /city/out/track.blend
```

### Nature agent

```
Fill all park and green zones.
- Tree set: 6 species, 3 variants each, with LOD1/LOD2.
- Scatter using Geometry Nodes inside parks and along tree-lined streets.
- Grass (card-based or shader), shrubs, flower beds, rocks.
- Big park: lake with shore, bridge, jogging paths, benches, playground,
  sports field, fountain, picnic area.
- Pocket parks in residential blocks.
- Keep trees off road surfaces and out of building footprints.
Output: /city/out/nature.blend
```

### Residential agent

```
Build 12 to 15 house and low apartment archetypes with parameters
(width, depth, floors, roof type, colour, facade variant), then place them
on every residential parcel from layout.json.
- Fences, gardens, driveways, garages.
- Enterable homes (flag in layout.json) get an open archway or open porch
  frontage, NO door mesh, and hand off to the Interiors agent via an
  anchor empty named INT_ANCHOR_<parcel_id>.
- Non-enterable homes get closed facades with windows and blinds.
Output: /city/out/residential.blend
```

### Commercial agent

```
Build offices, hotels, gyms, restaurants, and shops from modular kits
(ground floor, mid floor, top floor, roof) and place them on commercial parcels.
- Downtown towers up to 40 floors with unique silhouettes.
- Ground floors have wide open frontages or archways, NO door meshes.
- Signage, awnings, canopies, rooftop equipment (AC units, water tanks).
- Create INT_ANCHOR_<parcel_id> empties at every enterable ground floor.
Output: /city/out/commercial.blend
```

### Market agent

```
Build the market quarter in the NE.
- Narrow alleys, covered bazaar sections, stalls with awnings and cloth
  roofs, crates, produce, hanging lanterns, signage in multiple styles,
  tight 2 to 3 floor buildings with balconies.
- Dense prop clutter (baskets, carts, sacks, bikes, wires overhead).
- Restaurants and tea houses with open frontage, no door meshes.
- Mix of enterable shop interiors (hand off to Interiors agent via anchors).
Output: /city/out/market.blend
```

### Interiors agent

```
Build interior kits per the Tier plan in layout.json.
- Tier 1: full furnished interiors for office, hotel, gym, restaurant,
  shop, home. Tier 2: one furnished room plus simple floor plan.
- Place at each INT_ANCHOR_<parcel_id>; interior must fit behind the opening
  with no clipping through exterior walls.
- Interior lighting (area lights, emissive fixtures), baked or light-probe
  friendly. No door meshes; use open archways between rooms where sensible.
- Use PolyHaven/Sketchfab props where available, else simple procedural props.
Output: /city/out/interiors.blend
```

### Props and decals agent

```
Create and place street furniture and clutter.
- Benches, bins, hydrants, bollards, planters, signs, billboards,
  newspaper boxes, power poles with cables, bus shelters, ATMs, vending machines.
- Decals: dirt, cracks, puddles, graffiti (generic), posters.
- Place using road_edges.json and parcel boundaries; target high density
  without blocking walkways or crosswalks.
Output: /city/out/props.blend
```

### Lighting agent

```
Set up lighting and atmosphere for the master scene.
- Day: sun + PolyHaven HDRI, soft shadows, light haze.
- Night: street lights, emissive signs, interior lights, neon strip,
  headlight-friendly setup.
- Two switchable setups (collection toggles or a driver).
- Provide render previews: day, dusk, night.
Output: /city/out/lighting.blend
```

### Assembler agent (the ONLY agent allowed to use live MCP on the master)

```
1. save_blend a backup of city_master.blend before every merge step.
2. Append/link each /city/out/*.blend into city_master.blend in this order:
   roads, flyovers, traffic, track, nature, residential, commercial,
   market, interiors, props, lighting.
3. Verify collection tree matches contract. Fix naming issues.
4. Run checks (see QA). Do NOT fix art problems; send them back as tasks.
5. Use get_scene_info and get_viewport_screenshot after each merge.
6. Do each merge in small execute_blender_code chunks.
```

### QA agent

```
Run automated checks on city_master.blend and report/fix:
- Overlapping parcels or buildings intersecting roads
- Objects below the ground plane or floating
- Missing materials / pink textures
- Non-instanced duplicates (should be instanced)
- Triangle budget per district
- Missing collision proxies
- Interiors clipping through exterior walls
- Unapplied transforms, wrong scale (check against contract rules)
- Empty zones with no content
Take viewport screenshots from 10 fixed camera spots (downtown, market alley,
park, track, flyover, residential street, interior x3, skyline) and list
the 10 worst visual problems.
```

---

## 9. Order of execution

1. **Agent 0** (layout + style bible + materials)
2. **Roads**, then **Flyovers**
3. **Parallel:** Traffic, Track, Nature, Residential, Commercial, Market, Props, Lighting
4. **Interiors** (after Residential/Commercial/Market create anchors)
5. **Assembler** merges
6. **QA** reports, **fix loop** (send tasks back to owning agents)
7. **Export** per district + `manifest.json`

**Pilot first:** build ONE district (Market quarter + 2 roads + 1 flyover) end-to-end to prove the pipeline, then scale to the full map. If the contract works for one district, it works for six.

---

## 10. Common pitfalls

- Several agents sending live MCP commands to the same Blender session: collisions and corrupted scenes.
- Giant single scripts that time out. Use chunks.
- Skipping `save_blend` before code execution.
- Unique copies instead of instances: file size and RAM explode.
- Agents inventing their own materials: style drift.
- Wrong scale (agents assuming cm or random units).
- Trees and props spawning inside buildings or on roads.
- Interiors built before anchors exist.
- No collision proxies, so the engine can't walk the map.
- Going for the full city first instead of piloting one district.

---

## 11. Master kickoff prompt (give this to the orchestrating agent)

```
You are the Orchestrator for a 3x3 km AAA-quality city map built in Blender.
Read /city/city_map_plan.md fully.

RULES:
- Use subagents for every module listed in section 8, in the order from section 9.
- Subagents write Python modules and run them headless. Only the Assembler
  touches the master scene through the Blender MCP.
- Prepend the Global Contract (section 2) to every subagent prompt.
- Start with a PILOT of one district (Market quarter + 2 roads + 1 flyover).
  Do not scale up until the pilot passes QA.
- Run independent agents in parallel (Phase C). Do not wait on one when
  another can start.
- After each phase, summarise: files produced, triangle counts, issues.
- Save before any execute_blender_code. Use small chunks.
- The goal is visual quality comparable to a big-studio game: dense props,
  consistent style, strong lighting, zero empty land.
```
