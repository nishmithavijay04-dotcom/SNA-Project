"""Menu optimizer: a small mixed-integer program (scipy/HiGHS).
Chooses dishes and servings so that demand is covered, near-expiry stock is used first, purchases are cheap,
nutrition / veg-share / pot-time / labour limits are respected (soft limits report warnings), and the menu stays simple."""
import math
import numpy as np
import pandas as pd
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import lil_matrix
import config as C

class _Model:
    def __init__(self):
        self.names, self.lb, self.ub, self.integer, self.cost, self.rows = [], [], [], [], [], []
    def var(self, name, lb=0.0, ub=np.inf, integer=False, cost=0.0):
        self.names.append(name); self.lb.append(lb); self.ub.append(ub)
        self.integer.append(1 if integer else 0); self.cost.append(cost)
        return len(self.names) - 1
    def con(self, coeffs, lo=-np.inf, hi=np.inf):
        self.rows.append((coeffs, lo, hi))
    def solve(self, time_limit=20):
        A = lil_matrix((len(self.rows), len(self.names)))
        lo, hi = [], []
        for k, (co, l, h) in enumerate(self.rows):
            for j, v in co.items():
                A[k, j] = A[k, j] + v
            lo.append(l); hi.append(h)
        return milp(c=np.array(self.cost), constraints=LinearConstraint(A.tocsr(), lo, hi),
                    integrality=np.array(self.integer), bounds=Bounds(self.lb, self.ub),
                    options={"time_limit": time_limit})

def _groups(meal):
    """(group name, categories, min dishes, max dishes) for each course group the meal needs."""
    if meal == "Breakfast":
        return [("staple", ["staple"], 1, 1), ("accompaniment", ["main", "side"], 1, 2)]
    return [("staple", ["staple"], 1, 2), ("main", ["main"], 1, 2), ("side", ["side"], 1, 2)]

def urgency(days_left):
    return C.URGENCY_WEIGHT / (days_left + 1) if days_left <= C.NEAR_EXPIRY_DAYS else 0.0

def plan_menu(catalog, inventory, meal, servings, kitchen=None, allow_nonveg=True):
    if servings <= 0:
        raise ValueError("servings must be positive")
    k = {**C.KITCHEN_DEFAULTS, **(kitchen or {})}
    tg = C.MEAL_TARGETS[meal]
    d = float(servings)
    rec = catalog.eligible(meal, allow_nonveg)
    inv = inventory.copy()
    notes = []
    expired = inv[inv["days_to_expiry"] < 0]
    if len(expired):
        notes.append("Ignored expired stock: " + ", ".join(f"{r.item} ({r.quantity_kg:g} kg)" for r in expired.itertuples()))
    inv = inv[inv["days_to_expiry"] >= 0]
    stock = dict(zip(inv["item"], inv["quantity_kg"]))
    days = dict(zip(inv["item"], inv["days_to_expiry"]))
    price = {i: float(inv.loc[inv["item"] == i, "price_per_kg"].iloc[0]) if "price_per_kg" in inv.columns and
             pd.notna(inv.loc[inv["item"] == i, "price_per_kg"].iloc[0]) else catalog.prices[i] for i in catalog.prices
             if i in stock} | {i: p for i, p in catalog.prices.items() if i not in stock}

    m = _Model()
    ub = math.floor(d * (1 + C.OVERCOOK_TOL))
    x, y, n = {}, {}, {}
    for rid, r in rec.iterrows():
        x[rid] = m.var(f"x_{rid}", 0, ub, integer=True)
        y[rid] = m.var(f"y_{rid}", 0, 1, integer=True, cost=C.DISH_PENALTY_RS)
        n[rid] = m.var(f"n_{rid}", 0, math.ceil(ub / r["batch_max"]) + 1, integer=True)
        m.con({x[rid]: 1, y[rid]: -ub}, hi=0)                                       # x <= ub*y
        m.con({x[rid]: 1, y[rid]: -math.ceil(C.MIN_DISH_SHARE * d)}, lo=0)           # chosen dish covers >= 20 %
        m.con({n[rid]: r["batch_max"], x[rid]: -1}, lo=0)                            # batches * batch_max >= servings
    # course groups
    for name, cats, lo_n, hi_n in _groups(meal):
        ids = [rid for rid, r in rec.iterrows() if r["category"] in cats]
        if not ids:
            return {"status": "infeasible", "reason": f"No {name} dish is available for {meal}", "warnings": notes}
        m.con({x[i]: 1 for i in ids}, lo=d, hi=d * (1 + C.OVERCOOK_TOL))
        m.con({y[i]: 1 for i in ids}, lo=lo_n, hi=hi_n)
    # ingredients
    used, buy = {}, {}
    items = sorted({i for rid in rec.index for i in catalog.per_serving[rid]})
    for i in items:
        w = urgency(days[i]) if i in days else 0.0
        used[i] = m.var(f"use_{i}", 0, stock.get(i, 0.0), cost=-price[i] * w)
        buy[i] = m.var(f"buy_{i}", 0, cost=price[i])
        co = {x[rid]: catalog.per_serving[rid][i] / 1000.0 for rid in rec.index if i in catalog.per_serving[rid]}
        co[used[i]] = -1; co[buy[i]] = -1
        m.con(co, lo=0, hi=0)                                                       # need = used stock + bought
    # nutrition, veg share, protein option (soft where noted)
    s_k = m.var("slack_kcal", cost=C.PEN_KCAL); s_p = m.var("slack_protein", cost=C.PEN_PROTEIN)
    s_v = m.var("slack_veg", cost=C.PEN_VEG)
    m.con({**{x[r]: rec.loc[r, "kcal"] for r in rec.index}, s_k: 1}, lo=tg["kcal"] * d)
    m.con({**{x[r]: rec.loc[r, "protein_g"] for r in rec.index}, s_p: 1}, lo=tg["protein"] * d)
    vt = k["veg_target"]
    m.con({**{x[r]: (1 if rec.loc[r, "veg"] == 1 else 0) - vt for r in rec.index}, s_v: 1}, lo=0)
    m.con({y[r]: 1 for r in rec.index if rec.loc[r, "protein_flag"] == 1}, lo=1)
    # kitchen capacity (soft): pot-minutes and labour-minutes
    s_pot = m.var("slack_pot", cost=C.PEN_TIME); s_lab = m.var("slack_labour", cost=C.PEN_TIME)
    pot_budget, lab_budget = k["pots"] * k["window_min"], k["staff"] * k["window_min"]
    m.con({**{n[r]: rec.loc[r, "cook_min"] for r in rec.index}, s_pot: -1}, hi=pot_budget)
    m.con({**{n[r]: rec.loc[r, "labour_min"] for r in rec.index}, s_lab: -1}, hi=lab_budget)

    res = m.solve()
    if res.x is None:
        return {"status": "infeasible", "reason": "No menu satisfies the structure and demand limits", "warnings": notes}
    v = res.x
    names = {nm: j for j, nm in enumerate(m.names)}
    val = lambda nm: float(v[names[nm]])

    menu = []
    for rid in rec.index:
        sv = round(val(f"x_{rid}"))
        if sv > 0:
            r = rec.loc[rid]
            menu.append({"recipe_id": rid, "name": r["name"], "category": r["category"], "servings": sv,
                         "batches": int(round(val(f"n_{rid}"))), "veg": bool(r["veg"]), "cook_min": int(r["cook_min"]),
                         "labour_min": int(r["labour_min"]), "kcal": float(r["kcal"]), "protein_g": float(r["protein_g"])})
    order = {"staple": 0, "main": 1, "side": 2}
    menu.sort(key=lambda r: (order[r["category"]], r["name"]))

    rows = []
    for i in items:
        need = sum(r["servings"] * catalog.per_serving[r["recipe_id"]].get(i, 0) for r in menu) / 1000.0
        if need <= 1e-9:
            continue
        u = min(need, stock.get(i, 0.0))
        rows.append({"item": i, "need_kg": round(need, 2), "from_stock_kg": round(u, 2), "buy_kg": round(max(need - u, 0), 2),
                     "price_per_kg": price[i], "buy_cost": round(max(need - u, 0) * price[i], 0),
                     "days_left": days.get(i), "urgent": bool(i in days and days[i] <= C.NEAR_EXPIRY_DAYS)})
    ing = pd.DataFrame(rows)

    tot_serv = sum(r["servings"] for r in menu)
    totals = {
        "buy_cost": float(ing["buy_cost"].sum()), "dishes": len(menu),
        "kcal_per_plate": float(sum(r["servings"] * r["kcal"] for r in menu) / d),
        "protein_per_plate": float(sum(r["servings"] * r["protein_g"] for r in menu) / d),
        "veg_share": float(sum(r["servings"] for r in menu if r["veg"]) / tot_serv),
        "pot_min": sum(r["batches"] * r["cook_min"] for r in menu), "pot_budget": pot_budget,
        "labour_min": sum(r["batches"] * r["labour_min"] for r in menu), "labour_budget": lab_budget,
        "batches": sum(r["batches"] for r in menu),
    }
    near = ing[ing["urgent"]] if len(ing) else ing
    urgent_stock = {i: s for i, s in stock.items() if days[i] <= C.NEAR_EXPIRY_DAYS and s > 0}
    used_near = {i: float(ing.loc[ing["item"] == i, "from_stock_kg"].sum()) for i in urgent_stock}
    near_summary = {"stock_kg": sum(urgent_stock.values()), "used_kg": sum(used_near.values()),
                    "pct_used": 100 * sum(used_near.values()) / sum(urgent_stock.values()) if urgent_stock else 100.0}

    warnings = list(notes)
    if totals["kcal_per_plate"] < tg["kcal"] - 1:
        warnings.append(f"Energy per plate {totals['kcal_per_plate']:.0f} kcal is below the {tg['kcal']} kcal target")
    if totals["protein_per_plate"] < tg["protein"] - 0.05:
        warnings.append(f"Protein per plate {totals['protein_per_plate']:.1f} g is below the {tg['protein']} g target")
    if totals["veg_share"] < vt - 0.005:
        warnings.append(f"Veg share {totals['veg_share']:.0%} is below the {vt:.0%} target")
    if totals["pot_min"] > pot_budget:
        warnings.append(f"Cooking needs {totals['pot_min'] - pot_budget:.0f} more pot-minutes than your {k['pots']} pots give in {k['window_min']} min")
    if totals["labour_min"] > lab_budget:
        warnings.append(f"Hands-on work exceeds your staff time by {totals['labour_min'] - lab_budget:.0f} min")
    for i, s in urgent_stock.items():
        left = s - used_near[i]
        if left > 0.5:
            warnings.append(f"{left:.1f} kg {i} ({days[i]:.0f} day(s) left) is NOT used - consider donating or using it elsewhere")

    return {"status": "optimal" if res.status == 0 else "time_limit", "meal": meal, "servings": int(d), "menu": menu,
            "ingredients": ing, "totals": totals, "near_expiry": near_summary, "warnings": warnings,
            "explanations": explain(menu, ing, totals, near_summary, catalog, stock, days, price, k), "kitchen": k}

def explain(menu, ing, tot, near, catalog, stock, days, price, k):
    out = []
    for r in ing[ing["urgent"]].itertuples() if len(ing) else []:
        if r.from_stock_kg > 0:
            dishes = [m["name"] for m in menu if r.item in catalog.per_serving[m["recipe_id"]]]
            out.append(f"Uses {r.from_stock_kg:.1f} kg {r.item} that expires in {r.days_left:.0f} day(s), in {', '.join(dishes)}.")
    saved = float((ing["from_stock_kg"] * ing["price_per_kg"]).sum()) if len(ing) else 0.0
    out.append(f"Existing stock covers Rs {saved:,.0f} of the ingredients; you still need to buy Rs {tot['buy_cost']:,.0f} worth.")
    if near["stock_kg"] > 0:
        out.append(f"{near['pct_used']:.0f}% of your near-expiry stock ({near['used_kg']:.1f} of {near['stock_kg']:.1f} kg) is used in this menu.")
    out.append(f"Per plate: {tot['kcal_per_plate']:.0f} kcal, {tot['protein_per_plate']:.1f} g protein, {tot['veg_share']:.0%} vegetarian.")
    out.append(f"Cooking takes {tot['batches']} batches: {tot['pot_min']} of {tot['pot_budget']} pot-minutes and "
               f"{tot['labour_min']} of {tot['labour_budget']} labour-minutes available.")
    return out
