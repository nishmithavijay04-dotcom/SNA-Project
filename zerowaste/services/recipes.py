"""Recipe / ingredient / inventory loading. Swappable source: replace the CSVs (or write an importer with the same columns)."""
import os
from dataclasses import dataclass
import pandas as pd

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
MEAL_CODE = {"Breakfast": "B", "Lunch": "L", "Dinner": "D"}

@dataclass
class Catalog:
    recipes: pd.DataFrame        # index recipe_id
    per_serving: dict            # recipe_id -> {item: grams per serving}
    prices: dict                 # item -> Rs/kg
    shelf: dict                  # item -> typical shelf life (days)

    def eligible(self, meal, allow_nonveg=True):
        code = MEAL_CODE[meal]
        r = self.recipes[self.recipes["meals"].str.split(",").apply(lambda m: code in m)]
        return r if allow_nonveg else r[r["veg"] == 1]

def load_catalog(data_dir=DATA):
    r = pd.read_csv(os.path.join(data_dir, "recipes.csv")).set_index("recipe_id")
    ri = pd.read_csv(os.path.join(data_dir, "recipe_ingredients.csv"))
    ing = pd.read_csv(os.path.join(data_dir, "ingredients.csv"))
    per = {rid: dict(zip(g["item"], g["grams_per_serving"])) for rid, g in ri.groupby("recipe_id")}
    unknown = set(ri["item"]) - set(ing["item"])
    if unknown:
        raise ValueError(f"Ingredients used in recipes but missing from ingredients.csv: {sorted(unknown)}")
    return Catalog(r, per, dict(zip(ing["item"], ing["price_per_kg"])), dict(zip(ing["item"], ing["shelf_days"])))

def load_inventory(src, catalog):
    """Columns: item, quantity_kg, days_to_expiry (optional: price_per_kg). Returns (DataFrame, notes)."""
    df = src.copy() if isinstance(src, pd.DataFrame) else pd.read_csv(src)
    df.columns = [c.strip().lower() for c in df.columns]
    miss = [c for c in ("item", "quantity_kg", "days_to_expiry") if c not in df.columns]
    if miss:
        raise ValueError(f"Inventory is missing columns: {miss}")
    df = df.dropna(subset=["item"]).copy()
    df["item"] = df["item"].astype(str).str.strip().str.lower()
    df["quantity_kg"] = pd.to_numeric(df["quantity_kg"], errors="coerce")
    df["days_to_expiry"] = pd.to_numeric(df["days_to_expiry"], errors="coerce")
    if df["quantity_kg"].isna().any() or (df["quantity_kg"] < 0).any():
        raise ValueError("quantity_kg must be non-negative numbers")
    df["days_to_expiry"] = df["days_to_expiry"].fillna(9999)
    notes = []
    unknown = sorted(set(df["item"]) - set(catalog.prices))
    if unknown:
        notes.append(f"Ignored items not used by any recipe: {', '.join(unknown)}")
        df = df[~df["item"].isin(unknown)]
    dup = df["item"].duplicated(keep=False)
    if dup.any():                                   # merge duplicate rows: add quantities, keep the earliest expiry
        df = df.groupby("item", as_index=False).agg({"quantity_kg": "sum", "days_to_expiry": "min",
                                                    **({"price_per_kg": "first"} if "price_per_kg" in df.columns else {})})
        notes.append("Merged duplicate inventory rows (quantities added, earliest expiry kept)")
    return df.reset_index(drop=True), notes
