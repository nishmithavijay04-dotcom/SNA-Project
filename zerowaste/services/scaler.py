"""Scale recipes to the planned servings: ingredient quantities, number of batches, per-batch size and steps."""
import math

def cooking_guide(plan, catalog):
    guide = []
    for dish in plan["menu"]:
        rid, s = dish["recipe_id"], dish["servings"]
        r = catalog.recipes.loc[rid]
        batches = max(dish["batches"], math.ceil(s / r["batch_max"]))
        per_batch = math.ceil(s / batches)
        ing = [{"item": i, "kg": round(g * s / 1000.0, 2), "per_batch_kg": round(g * per_batch / 1000.0, 2)}
               for i, g in sorted(catalog.per_serving[rid].items(), key=lambda t: -t[1])]
        guide.append({"name": dish["name"], "category": dish["category"], "servings": s, "batches": batches,
                      "per_batch": per_batch, "minutes_per_batch": int(r["cook_min"]), "ingredients": ing,
                      "steps": str(r["steps"]).split("|"),
                      "note": (f"Cook in {batches} batches of about {per_batch} servings "
                               f"(~{int(r['cook_min'])} min each)." if batches > 1 else
                               f"Cook in one batch of {s} servings (~{int(r['cook_min'])} min).")})
    return guide

def scale_ingredients(per_serving_g, servings):
    """Plain scaling helper: grams per serving -> kg for `servings` (used by tests and the UI)."""
    return {i: g * servings / 1000.0 for i, g in per_serving_g.items()}
