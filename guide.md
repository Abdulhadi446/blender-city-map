All public downtown and entertainment buildings are enterable except a share of shops and cafes, which are tier 3 to keep the interior count manageable. If you want every shop enterable, raise the probabilities in ENTER_PROB, but expect hundreds more interiors to build.

Don’t hand the full 1.1 MB layout.json to every subagent. Run python generate_layout.py --split to also write one parcels_<district>.json per district, so each agent loads only its own slice. You can change the seed with --seed, and the district map is the GRID constant at the top of the script.
