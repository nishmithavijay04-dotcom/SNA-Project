"""Evidence for the report: optimizer vs random valid menus on random inventories.
Metrics: % of near-expiry stock used, purchase cost, and share of plates meeting the nutrition target."""
import numpy as np
import pandas as pd
import config as C
from services.menu_optimizer import plan_menu, _groups
from services.recipes import load_inventory

def random_inventory(catalog, rng, demand, base):
    """Scale the sample inventory to `demand` and randomise quantities and expiry days."""
    rows = []
    for _, r in base.iterrows():
        perishable = catalog.shelf[r["item"]] <= 14
        days = int(rng.integers(0, 8)) if perishable else 60
        rows.append({"item": r["item"], "quantity_kg": float(r["quantity_kg"]) * demand / 450 * rng.uniform(0.4, 1.6),
                     "days_to_expiry": days})
    return pd.DataFrame(rows)

def random_menu(catalog, meal, demand, rng, allow_nonveg=True):
    rec = catalog.eligible(meal, allow_nonveg)
    pick = []
    for name, cats, lo, hi in _groups(meal):
        pool = rec[rec["category"].isin(cats)].index.tolist()
        pick.append(rng.choice(pool))
    return pick

def score_menu(catalog, rec_ids, inv, demand, meal):
    stock = dict(zip(inv["item"], inv["quantity_kg"])); days = dict(zip(inv["item"], inv["days_to_expiry"]))
    need = {}
    for rid in rec_ids:
        for i, g in catalog.per_serving[rid].items():
            need[i] = need.get(i, 0) + g * demand / 1000.0
    used = {i: min(q, stock.get(i, 0)) for i, q in need.items()}
    cost = sum((q - used[i]) * catalog.prices[i] for i, q in need.items())
    near = {i: s for i, s in stock.items() if days[i] <= C.NEAR_EXPIRY_DAYS and s > 0}
    pct = 100 * sum(used.get(i, 0) for i in near) / sum(near.values()) if near else 100.0
    tg = C.MEAL_TARGETS[meal]
    kcal = sum(catalog.recipes.loc[r, "kcal"] for r in rec_ids); prot = sum(catalog.recipes.loc[r, "protein_g"] for r in rec_ids)
    return {"near_used_pct": pct, "buy_cost": cost, "meets_nutrition": bool(kcal >= tg["kcal"] and prot >= tg["protein"])}

def evaluate(catalog, base_inventory, meal="Lunch", demand=450, trials=20, seed=1):
    rng = np.random.default_rng(seed)
    rows = []
    for t in range(trials):
        inv, _ = load_inventory(random_inventory(catalog, rng, demand, base_inventory), catalog)
        p = plan_menu(catalog, inv, meal, demand)
        if p["status"] == "infeasible":
            continue
        opt_ids = [m["recipe_id"] for m in p["menu"]]
        # note: random menu is scored per plate on its own dishes, so compare cost/near-expiry use, not dish count
        ro = score_menu(catalog, random_menu(catalog, meal, demand, rng), inv, demand, meal)
        rows.append({"trial": t, "optimizer_near_used_pct": p["near_expiry"]["pct_used"], "random_near_used_pct": ro["near_used_pct"],
                     "optimizer_buy_cost": p["totals"]["buy_cost"], "random_buy_cost": ro["buy_cost"],
                     "optimizer_meets_nutrition": not any("below" in w for w in p["warnings"]),
                     "random_meets_nutrition": ro["meets_nutrition"]})
    df = pd.DataFrame(rows)
    summary = {"trials": len(df),
               "optimizer_near_used_pct": float(df["optimizer_near_used_pct"].mean()), "random_near_used_pct": float(df["random_near_used_pct"].mean()),
               "optimizer_buy_cost": float(df["optimizer_buy_cost"].mean()), "random_buy_cost": float(df["random_buy_cost"].mean()),
               "optimizer_meets_nutrition_pct": float(100 * df["optimizer_meets_nutrition"].mean()),
               "random_meets_nutrition_pct": float(100 * df["random_meets_nutrition"].mean())}
    return summary, df
