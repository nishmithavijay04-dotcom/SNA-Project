import os, sys, copy, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
warnings.filterwarnings("ignore")
import pandas as pd, pytest
import config as C
from services.recipes import load_catalog, load_inventory
from services.menu_optimizer import plan_menu, urgency
from services.scaler import cooking_guide, scale_ingredients
from services.repurposer import suggest
from evaluation.optimizer_eval import evaluate

CAT = load_catalog()
BASE = pd.read_csv(os.path.join(os.path.dirname(__file__), "..", "data", "inventory_sample.csv"))

def inv(**changes):
    df = BASE.copy()
    for item, (q, d) in changes.items():
        item = item.replace("_", " ")
        if item in set(df["item"]): df.loc[df["item"] == item, ["quantity_kg", "days_to_expiry"]] = [q, d]
        else: df = pd.concat([df, pd.DataFrame([{"item": item, "quantity_kg": q, "days_to_expiry": d}])])
    return load_inventory(df, CAT)[0]

def group_sum(plan, cats):
    return sum(m["servings"] for m in plan["menu"] if m["category"] in cats)

# ---------- catalog / inventory ----------
def test_catalog_consistency():
    assert len(CAT.recipes) >= 25 and set(CAT.recipes["category"]) == {"staple", "main", "side"}
    for rid, ing in CAT.per_serving.items():
        assert ing and all(i in CAT.prices for i in ing)
    for meal in C.MEALS:
        cats = set(CAT.eligible(meal)["category"]); assert "staple" in cats and ({"main", "side"} & cats)

def test_inventory_loading_rules():
    df = pd.DataFrame([{"item": "Rice ", "quantity_kg": 10, "days_to_expiry": 5}, {"item": "rice", "quantity_kg": 5, "days_to_expiry": 2},
                       {"item": "unicorn meat", "quantity_kg": 1, "days_to_expiry": 3}])
    out, notes = load_inventory(df, CAT)
    assert list(out["item"]) == ["rice"] and out["quantity_kg"].iloc[0] == 15 and out["days_to_expiry"].iloc[0] == 2
    assert any("unicorn" in n for n in notes) and any("Merged" in n for n in notes)
    with pytest.raises(ValueError): load_inventory(df.assign(quantity_kg=-1), CAT)
    with pytest.raises(ValueError, match="missing columns"): load_inventory(df.drop(columns=["days_to_expiry"]), CAT)

# ---------- optimizer constraints ----------
@pytest.mark.parametrize("meal,servings", [("Lunch", 450), ("Dinner", 300), ("Breakfast", 380)])
def test_plan_satisfies_all_hard_constraints(meal, servings):
    inventory = inv(); p = plan_menu(CAT, inventory, meal, servings)
    assert p["status"] == "optimal"
    if meal == "Breakfast":
        assert group_sum(p, ["staple"]) == servings and group_sum(p, ["main", "side"]) == servings
    else:
        for cats in (["staple"], ["main"], ["side"]):
            assert group_sum(p, cats) == servings                                    # coverage exactly the planned servings
    counts = {c: sum(1 for m in p["menu"] if m["category"] == c) for c in ("staple", "main", "side")}
    assert counts["staple"] in (1, 2) and (meal == "Breakfast" or (1 <= counts["main"] <= 2 and 1 <= counts["side"] <= 2))
    stock = dict(zip(inventory["item"], inventory["quantity_kg"]))
    for r in p["ingredients"].itertuples():
        assert r.from_stock_kg <= stock.get(r.item, 0) + 1e-6                        # never uses more stock than exists
        assert abs(r.need_kg - r.from_stock_kg - r.buy_kg) < 0.011                   # need = stock used + bought
    for m in p["menu"]:
        assert m["batches"] * CAT.recipes.loc[m["recipe_id"], "batch_max"] >= m["servings"]
        assert m["servings"] >= 0.2 * servings                                        # no tiny token dishes
    assert any(CAT.recipes.loc[m["recipe_id"], "protein_flag"] == 1 for m in p["menu"])   # at least one protein option
    t = p["totals"]; tg = C.MEAL_TARGETS[meal]
    assert t["kcal_per_plate"] >= tg["kcal"] - 1 and t["protein_per_plate"] >= tg["protein"] - 0.05
    assert t["pot_min"] <= t["pot_budget"] and t["labour_min"] <= t["labour_budget"]

def test_expired_stock_is_never_used():
    p = plan_menu(CAT, inv(tomato=(500, -1)), "Lunch", 450)
    assert any("expired" in w.lower() for w in p["warnings"])
    row = p["ingredients"][p["ingredients"]["item"] == "tomato"]
    assert row.empty or row["from_stock_kg"].iloc[0] == 0

def test_near_expiry_stock_is_prioritised():
    chicken_today = inv(chicken=(25, 0))
    p = plan_menu(CAT, chicken_today, "Lunch", 450)
    assert any(m["name"] == "Chicken curry" for m in p["menu"])
    used = p["ingredients"].set_index("item").loc["chicken", "from_stock_kg"]
    assert used >= 15 and any("chicken" in e for e in p["explanations"])
    p2 = plan_menu(CAT, inv(), "Lunch", 450)                                          # no chicken in stock: buying is costly
    assert not any(m["name"] == "Chicken curry" for m in p2["menu"])
    assert urgency(0) > urgency(1) > urgency(3) > 0 == urgency(4)

def test_optimizer_uses_more_urgent_stock_than_ignoring_urgency(monkeypatch):
    base = plan_menu(CAT, inv(paneer=(12, 0), curd=(20, 0)), "Lunch", 450)["near_expiry"]["pct_used"]
    monkeypatch.setattr(C, "URGENCY_WEIGHT", 0.0)
    ignored = plan_menu(CAT, inv(paneer=(12, 0), curd=(20, 0)), "Lunch", 450)["near_expiry"]["pct_used"]
    assert base > ignored

def test_nonveg_toggle_and_veg_target():
    p = plan_menu(CAT, inv(chicken=(30, 0), eggs=(10, 1)), "Lunch", 450, allow_nonveg=False)
    assert all(m["veg"] for m in p["menu"])
    p = plan_menu(CAT, inv(), "Lunch", 450, kitchen={"veg_target": 1.0})
    assert p["totals"]["veg_share"] == 1.0

def test_capacity_limits_become_warnings_not_crashes():
    p = plan_menu(CAT, inv(), "Lunch", 450, kitchen={"pots": 1, "staff": 1, "window_min": 60})
    assert p["status"] == "optimal" and any("pot-minutes" in w for w in p["warnings"]) and any("staff time" in w for w in p["warnings"])
    assert p["totals"]["pot_min"] > p["totals"]["pot_budget"]

def test_more_pots_means_no_pot_warning():
    p = plan_menu(CAT, inv(), "Lunch", 450, kitchen={"pots": 10, "staff": 10})
    assert not any("pot-minutes" in w or "staff time" in w for w in p["warnings"])

def test_unused_near_expiry_stock_is_flagged():
    p = plan_menu(CAT, inv(potato=(200, 1)), "Lunch", 450)
    assert any("potato" in w and "NOT used" in w for w in p["warnings"])

def test_shopping_list_cost_matches_prices():
    p = plan_menu(CAT, inv(rice=(0, 100)), "Lunch", 450)                              # no rice in stock -> must buy
    ing = p["ingredients"]
    assert (ing["buy_cost"] - (ing["buy_kg"] * ing["price_per_kg"]).round(0)).abs().max() <= 1
    assert abs(p["totals"]["buy_cost"] - ing["buy_cost"].sum()) < 1e-6

def test_infeasible_when_a_course_is_unavailable():
    cat2 = copy.deepcopy(CAT); cat2.recipes = cat2.recipes[cat2.recipes["category"] != "side"]
    p = plan_menu(cat2, inv(), "Lunch", 450)
    assert p["status"] == "infeasible" and "side" in p["reason"]
    with pytest.raises(ValueError): plan_menu(CAT, inv(), "Lunch", 0)

def test_optimizer_beats_random_menus():
    summary, df = evaluate(CAT, BASE, trials=6, seed=3)
    assert summary["optimizer_near_used_pct"] > summary["random_near_used_pct"] + 20
    assert summary["optimizer_buy_cost"] < summary["random_buy_cost"]
    assert summary["optimizer_meets_nutrition_pct"] >= summary["random_meets_nutrition_pct"]

# ---------- scaler ----------
def test_scaling_4_servings_to_450_is_exact():
    r = scale_ingredients({"rice": 80, "toor dal": 30}, 450)
    assert r["rice"] == pytest.approx(36.0) and r["toor dal"] == pytest.approx(13.5)
    assert scale_ingredients({"rice": 80}, 4)["rice"] * 112.5 == pytest.approx(r["rice"])

def test_cooking_guide_batches_and_totals():
    p = plan_menu(CAT, inv(), "Lunch", 450)
    g = cooking_guide(p, CAT)
    assert len(g) == len(p["menu"])
    for dish, gd in zip(p["menu"], g):
        r = CAT.recipes.loc[dish["recipe_id"]]
        assert gd["batches"] * gd["per_batch"] >= dish["servings"] and gd["per_batch"] <= r["batch_max"]
        for i in gd["ingredients"]:
            assert i["kg"] == pytest.approx(CAT.per_serving[dish["recipe_id"]][i["item"]] * dish["servings"] / 1000, abs=0.006)
        assert len(gd["steps"]) >= 3 and ("batch" in gd["note"])

# ---------- repurposer ----------
def test_repurposer_rules():
    exp = suggest("Cooked rice / pulao / biryani", -10)
    assert not exp["safe_for_people"] and exp["ideas"] == [] and "do NOT" in exp["message"]
    ok = suggest("Cooked rice / pulao / biryani", 180, refrigerated=True)
    assert ok["safe_for_people"] and len(ok["ideas"]) >= 2
    short = suggest("Dairy-based / sweets", 60, refrigerated=False)                   # short window, not chilled: skip chill-dependent ideas
    assert short["ideas"] == []
    salad = suggest("Salad / cut raw items", 90, refrigerated=True)
    assert salad["safe_for_people"] and salad["ideas"]                                 # chilled salad: same-day reuse is fine