# Preview Review (Orchestrator, 2026-10-27)

Method: read each out/*.png, note issues immediately. Status: IN PROGRESS.

## Verified observations (images confirmed on disk + reviewed)

### transport_preview.png / transport_airport_preview.png — CRITICAL
- Runway/apron surfaces render **magenta/pink** = MISSING MATERIALS (failed material append/assign).
- Airport preview camera is INSIDE geometry (flat pink wall fills frame, no readable subject).
- transport_preview: mostly empty dark frame, only runway visible — camera framing wrong and/or most facilities not in frame; matches agent's self-reported "skeleton quality" (terminal 2148 tris).
- FIX REQUIRED: TRANSPORT-FIX agent (materials from citykit.append_material, re-frame cameras, upgrade terminal/rail/station geometry toward hero budgets).

### roads_preview.png — OK (full city!)
- Shows ALL 454 edges: dense inner grid + highway ring with orange dirt verge, medians on arterials.
- Dark world background (module preview only — Assembler adds world/ground).
- NOTE: roads-city appears to have re-rendered this → check if ROADS-CITY finished.

### market_street_preview.png — GOOD with minor issues
- Dense alley of 2-4 storey shops, open storefronts (no doors), awnings, blade signs, crates.
- Issues: (a) some open storefront interiors read as flat light-grey void (fake depth needs darker interior/back wall); (b) left sidewalk very bright vs right darker — inconsistent surfacing/lighting; (c) foreground-right shop interior wood texture stretched.

### market_preview.png — GOOD
- Dense colorful bazaar quarter, 1236 parcels all built, LM_BAZAAR dome hero reads well, courtyard arcades, external stairs, rooftop AC/tanks. No empty land.
- Minor: bazaar roof is a very large flat grey slab (could use more roof articulation); no plaza shade trees visible yet (nature adds); some gigantic flat roofs read plain.

### flyover_preview.png — WEAK (module-only, not broken)
- Pilot NE corner deck only (expected scope); lane markings + dashes correct; no pillars/barrier visible in top-down dark frame. `flyover_ground_preview.png` is the better check.

### flyover_ground_preview.png — OK (dark)
- Under-deck view: piers with dark bases, service road, yellow edge lines, emissive edge markers. Soffit pitch black (no bounce light) — preview lighting choice, not geometry.

### nature_preview.png — ISSUES
- Green belt ground is ORANGE-BROWN DIRT/gravel over huge areas with only patchy dark-green — reads as wasteland, not park. Needs continuous grass lawn (grass / grass_dry materials available).
- Several PINK/MAGENTA objects on paths (near centre-bottom, left-middle, right-middle) = missing materials on a few nature props (benches/kiosks/signs).
- Tree density good (14k), lake+paths present; trees read olive/dark (leaves_dry variants) — acceptable but ground must be green.

### nature_playground_preview.png — BROKEN
- Frame is completely blank (dark grey-green gradient, no geometry). Camera inside ground or aimed at nothing. Must re-render.

### track_preview.png — GOOD with issues
- Grandstand + pit lane + circuit read correctly; kerbs, dashed lines, green verges present.
- Issues: (a) one small grey box floating above ground left mid-frame (stray object); (b) pit-building roof is a giant flat brown slab (needs texture/ribs or darker roof material); (c) some white dashed markings appear on the paddock/apron, outside the track surface — verify track marking placement.

### track_ground_preview.png — WEAK (blockout look)
- Eye-level pit lane: grandstand canopy fine, but pit garages read as blank white/grey boxes with brown striped panels; concrete is blown-out white; asphalt flat grey with only yellow lines; overall washed-out/untextured look. Needs QA polish pass (materials + exposure + garage fronts).

### materials_preview.png — OK
- All 64 contract materials render on spheres; col_placeholder magenta by design; palette consistent. No action.

### sports_preview.png + sports_football_preview.png — BROKEN
- Both frames are 95% flat dark grey; sports_preview shows only a small grass patch top-right. Cameras are inside/behind a stand wall. Geometry claims (1373 obj, all budget checks PASS) can't be visually confirmed — RE-RENDER REQUIRED with correct cameras.

### props_preview.png + props_street_preview.png — BROKEN
- Both frames completely blank (flat dark grey). Blend has 3,614 instances, so it is a camera/render failure, not missing geometry. RE-RENDER REQUIRED.

### lighting_preview.png + lighting_street_preview.png — OK for isolated module, one odd object
- Night renders show only lamp/signal geometry (lighting.blend has no city context): aerial reads as a field of emissive dots; street shows posts + lamp heads. Expected, but weak as proof.
- Odd: one large white square floating low near bottom-centre of the street preview (misplaced lamp-head/flood mesh?) — check SM_FloodTower_01 placement.
- Recommendation: re-render lighting previews against a temporary ground plane + context later if desired.

### traffic_preview.png + traffic_street_preview.png — UNREADABLE (no context)
- Both render vehicles against empty world (no ground/roads). Aerial: white roof-shapes floating on dark; street: black silhouettes. Lane alignment / wheels-on-ground cannot be verified. Paint variants not evident (roofs read white).
- Geometry claims (4,825 instances, 24 elevated) plausible but unproven visually → re-render with ground + sun, and verify material assignment on bodies.

### commercial_preview.png + commercial_street_preview.png — CRITICAL (module broken)
- Nearly every surface is MAGENTA = missing materials across the whole module. Buildings read as floating pink slabs (facade generation apparently failed / materials never assigned); landmark tower is alternating pink+dark bands. Street preview: camera buried in a giant pink wall.
- Overall this module's blend appears to be an unfinished/WIP build (matches the suspected OpenRouter model). REBUILD REQUIRED, not just re-render.

### downtown_preview.png — ISSUES
- Masses read well (LM tower + antialias spike, podiums, rooftop AC). 
- MAJOR: many towers show completely BLANK WHITE side facades (windows only on 1-2 faces) — big white-box look; landmark tower itself washed out/white.
- BUG: a giant inverted teal cone/trumpet object floats in the sky right of centre (~x1490,y350 px) — stray landmark crown object.
- Ground between towers is bare brown dirt (plaza paving missing in module); white railing/floor-slab strips at podium bases look odd.

### entertainment_preview.png — GOOD with issues
- Best-looking district so far: textured roofs, brick + banded facades, billboards, string lights, rooftop AC.
- Issues: courtyards between buildings are bare BROWN DIRT (should be paved or grass); several side walls blank; some courtyard zones very dark (deep shadow/black); bright green wall panels read odd.

### downtown_street_preview.png — WRONG SUBJECT + texture bug
- Camera points UP at a tower, not a street; no street/people/cars in frame.
- Facades show heavily STRETCHED vertical texture smears (window strips melted into streaks) — UV/texture-scale bug on towers.

### entertainment_street_preview.png — context-poor (expected pre-assembly)
- Empty wide asphalt with no markings, kerbs, sidewalks, lamps or cars; buildings sit straight on road. Fine once Roads/Props/Traffic merge, but shopfront glass panes render blown-out WHITE (should be dark/reflective glass) — check glass material on shopfronts.

### residential_preview.png — ISSUES
- Green lawns + brick/stucco houses + boundary walls + driveways read well.
- MAJOR: enormous plain grey ROAD SLABS (whole cell widths) with no markings/kerbs — looks like residential laid its own road planes → will double/z-fight with Roads build; verify and strip its road planes at assembly.
- No street trees/lamps/cars yet (other modules).

### residential_street_preview.png — ISSUES
- Boundary walls: flat sage-green panels with white coping read like cardboard/plastic (only gate posts are brick) — needs a plaster/brick material or texture scale fix.
- Balconies = dark grey boxes floating with no supports.
- No sidewalk/kerb/markings; walls meet asphalt directly.
- Windows fine (blue glass + timber frames); brick facades good.

### interiors_preview.png + interiors_kit_preview.png — BAD FRAMING
- Hero interior: camera is inside the room too close — only wood floor + grey wall band + one tiny floating white panel visible; no furniture/room readable.
- Kit preview: parts scattered tiny across empty space, most too small to read, one cut off at frame edge. Not usable as proof. RE-RENDER with proper framing.

## ROOT CAUSES FOUND (probe 16 blends)
- Missing textures in EVERY blend: image paths `//../../../../../tmp/opencode/ph/<set>/<File>.jpg` — case/path mismatch; only modules using alternate `facade_*`/`road_*` materials show magenta (commercial 48, transport 24, market 56 but unused, residential 56, downtown 48, entertainment 44, track 44...). FIX = repath case-insensitively + PACK images in all blends.
- traffic.blend: 4,853 of 4,855 mesh objects have NO material slots (1 material in file) → white/black cars. REAL BUG.
- civic.blend: only 4 of 45 SportsCivic facilities built (CITY_HALL, CIVIC_TOWN_OFFICES, CUL_CINEMA, CUL_CLUB); 5 stadiums owned by sports; 36 missing. No previews.
- props: 15 objects no material. roads: 1,137 no material (likely COL_ colliders). track: 11 no material.

## FIX AGENTS LAUNCHED (4 max, >=100B models)
A. MATERIAL-FIX (deepseek): repath+pack all blends, traffic materials, re-render traffic/commercial/transport.
B. CIVIC-FINISH (nemotron-super): build 36 missing facilities + previews.
C. GEOMETRY-QA (deepseek): downtown cone/UV/blank walls, nature grass+pink props, residential road planes/walls/balconies, track stray box/roof, entertainment glass/courtyards, market lights collection, re-render.
D. PREVIEW-REPAIR (glm): robust auto-framed renders for sports/props/nature_playground/interiors/lighting/flyover.

CRITICAL geometry/material bugs:
1. COMMERCIAL — whole module magenta (missing materials), buildings are floating slabs → REBUILD.
2. TRANSPORT — magenta runway/apron, cameras inside geometry, skeleton-level terminals → FIX.
3. DOWNTOWN — giant floating teal cone in sky; stretched vertical facade UVs on towers; mass blank white side walls.
4. NATURE — green belt ground is dirt-brown (should be grass); several magenta props (missing material).
5. RESIDENTIAL — own oversized grey road planes (duplicate of Roads, z-fight risk); sage-green boundary wall panels read like cardboard; balconies float as dark boxes.
6. MARKET — 247 LT_market lights exist but 0 in Market/Lights collection (assembly tree issue).
7. TRACK — stray floating grey box; flat brown pit-building roof; blown-out white concrete.
8. ENTERTAINMENT — courtyard ground dirt; shopfront glass blown white.

Preview-only failures (geometry likely fine): SPORTS x2, PROPS x2, NATURE_PLAYGROUND, INTERIORS x2, TRAFFIC x2 (context), LIGHTING x2 (isolated).
Weak-but-valid: FLYOVER (dark), ROADS (ok), MATERIALS (ok), MARKET (good), ENTERTAINMENT (good).

- market_preview, flyover_preview, flyover_ground_preview
- nature_preview, nature_playground_preview
- track_preview, track_ground_preview
- materials_preview
- sports_preview, sports_football_preview
- props_preview, props_street_preview
- lighting_preview, lighting_street_preview
- traffic_preview, traffic_street_preview
- commercial_preview, commercial_street_preview
- downtown_preview, downtown_street_preview, entertainment_preview, entertainment_street_preview
- residential_preview, residential_street_preview

## ISSUE LEDGER (accumulating)
1. TRANSPORT broken (magenta materials + bad cameras + skeleton geometry).
2. Market: LT_market lights may not be in Market/Lights collection (REPAIRS scan found 0 members).
3. Residential preview camera may have failed in REPAIRS re-render — verify image is non-blank.
4. Market storefront fake-depth interiors too bright/flat (minor, QA pass).
