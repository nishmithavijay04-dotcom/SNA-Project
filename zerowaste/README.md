# ZeroWaste Kitchen - forecast -> menu planner -> surplus partners -> impact (generic institutional kitchen, Bengaluru partners)

Read-only recommender: it never contacts anyone, it shows partner details and a PyDeck map so a person can call or navigate.

    pip install -r requirements.txt
    streamlit run app.py
    pytest -q

## Partner data
- `data/source_partners.xlsx` - your researched list (29 unique orgs after removing a duplicate).
- `python scripts/convert_partners.py` -> `data/partners.csv` (the app's schema). Re-run only if you change the Excel.
- **Coordinates are approximate area centres typed by hand, not geocoded** (1-3 km error possible).
  Fix any row in `partners.csv` (Google Maps: right-click pin -> click the numbers), and set
  `coord_quality` to `exact`.
- Robin Hood Army and Swabhimaan have no address in the source: listed as "no location on file", never ranked.
- `accepts_surplus`: yes / likely / unconfirmed (from your file). Ranking favours confirmed ones but still
  shows others, labelled "ask before going".
- `data/ngos_demo.csv` is placeholder data used only by some unit tests.

## Assumptions to state in the report (config.py, services/safety_rules.py)
Road routing: OSRM public demo server (needs internet; falls back to estimate). Free-flow drive time x 1.5 traffic factor (assumption).
Road factor 1.35, 18 km/h, 20 min handling, 30 min buffer, 25 km radius; safe-hour windows per food type
(conservative guesses - review against FSSAI/local guidance).
Ranking = 0.40 distance + 0.25 spare time + 0.35 surplus-intake confirmed (from the research file).

## App features (all covered by tests/test_app.py)
Sidebar: kitchen name, area dropdown or custom coordinates, road-routing toggle, partner CSV upload.
Find partners: food inputs -> safe-until -> ranked partners; live controls (how many, sort by, only confirmed);
cards with contacts + Directions / Google Maps / OpenStreetMap buttons; PyDeck map (red kitchen, blue numbered
recommendations, grey others, road lines); CSV download; list of excluded partners with reasons.
Partner directory: search, confirmed filter, sorted table, colour-coded map, full details panel.

## The five tabs
1. **Forecast** - how much to cook (Random Forest on calendar flags + past consumption; no leakage), service-level slider,
   log actuals (auto-retrain), upload your own demand CSV, regenerate demo data for any kitchen size.
2. **Menu planner** - stock + expiry + forecast -> optimized menu (mixed-integer program, scipy/HiGHS): uses near-expiry stock first,
   minimises purchases, meets nutrition / veg-share / pot-time / labour limits (soft limits show warnings),
   with "why this menu", shopping list (CSV) and scaled cooking guide with batches.
3. **Find partners** - surplus -> safe-until -> ranked partners, map, links, reuse ideas, donation log.
4. **Partner directory** - search/filter all partners.
5. **Dashboard** - donations logged, simulated waste avoided by forecasting (at equal service level), forecast accuracy, optimizer vs random menus.

## Data
`python -m adapters.recipe_seed` rewrites recipes / ingredients / sample inventory / leftover ideas (approximate seed values).
`python -m adapters.synthetic` regenerates `data/demand_log.csv` (synthetic). Real logs: upload in the Forecast tab
(columns: date, meal, consumed; optional prepared, is_holiday, is_exam, is_event, is_special).

## Honest limits (state in the report)
Demand data is synthetic; the 'usual plan' (last week + 20%) is simulated; prices, nutrition and recipe quantities are approximate;
meal weight (0.4 kg) and CO2e factor (2.5 kg/kg) are assumptions to be cited; logged consumption hides unmet demand when food runs out.
