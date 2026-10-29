"""Seed data for recipes, ingredients, sample inventory and leftover ideas.
Quantities, kcal and prices are APPROXIMATE typical values for institutional South-Indian cooking
(grams per serving). Replace with a Kaggle recipe import later (same CSV columns).
Run:  python -m adapters.recipe_seed"""
import os
import pandas as pd

D = os.path.join(os.path.dirname(__file__), "..", "data")

# name: (price Rs/kg, shelf life days when stored normally)
INGREDIENTS = {
    "rice": (55, 365), "toor dal": (130, 365), "urad dal": (120, 365), "moong dal": (115, 365), "chana": (90, 365),
    "wheat flour": (40, 120), "ragi flour": (45, 120), "rava": (50, 180), "poha": (55, 180), "groundnuts": (120, 180),
    "potato": (30, 30), "onion": (35, 30), "tomato": (40, 6), "carrot": (50, 14), "beans": (70, 6),
    "cabbage": (30, 10), "cauliflower": (45, 6), "brinjal": (50, 7),
    "paneer": (330, 5), "curd": (70, 5), "chicken": (220, 2), "eggs": (110, 14),
}

# id, name, category, meals, veg, protein, cook_min/batch, labour_min/batch, batch_max_servings, kcal, protein_g, ingredients(g/serving), steps
R = [
 ("R01", "Steamed rice", "staple", "L,D", 1, 0, 35, 15, 120, 280, 5.5, {"rice": 80},
  "Wash rice 2-3 times|Boil water in the pot, add rice|Cook until soft, drain and rest 5 min|Fluff and keep covered"),
 ("R02", "Lemon rice", "staple", "L,D", 1, 0, 40, 20, 100, 330, 7, {"rice": 80, "groundnuts": 8, "onion": 10},
  "Cook rice and cool slightly|Temper groundnuts and onion in oil|Mix with lemon juice and salt|Toss gently with rice"),
 ("R03", "Tomato rice", "staple", "L,D", 1, 0, 45, 20, 100, 320, 6.5, {"rice": 80, "tomato": 60, "onion": 25},
  "Saute onion, add chopped tomato and spices|Add washed rice and water|Cook until done|Rest and fluff"),
 ("R04", "Bisibele bath", "staple", "L,D", 1, 1, 60, 25, 100, 360, 12,
  {"rice": 55, "toor dal": 30, "carrot": 20, "beans": 20, "potato": 20, "onion": 15, "tomato": 15},
  "Pressure-cook dal and rice together|Cook chopped vegetables with spice powder|Combine and simmer|Finish with ghee/tempering"),
 ("R05", "Curd rice", "staple", "L,D", 1, 0, 35, 15, 120, 310, 9, {"rice": 70, "curd": 120},
  "Cook rice soft and let it cool|Mix with curd and salt|Temper mustard and curry leaves|Serve chilled or at room temperature"),
 ("R06", "Chapati", "staple", "L,D", 1, 0, 60, 40, 150, 240, 8, {"wheat flour": 70},
  "Knead dough and rest 20 min|Roll into rounds|Cook on a hot griddle both sides|Stack in a cloth-lined box"),
 ("R07", "Ragi mudde", "staple", "L,D", 1, 0, 40, 30, 80, 280, 6, {"ragi flour": 80},
  "Boil water with salt|Add ragi flour and stir continuously|Cook on low heat until smooth|Shape into balls"),
 ("R08", "Idli", "staple", "B", 1, 0, 45, 20, 250, 200, 6, {"rice": 40, "urad dal": 15},
  "Use fermented batter (soak and ferment the day before)|Pour into greased idli plates|Steam 12-15 min|Serve hot"),
 ("R09", "Dosa", "staple", "B", 1, 0, 60, 45, 200, 220, 6, {"rice": 50, "urad dal": 15},
  "Use fermented batter (prepared the day before)|Spread on a hot griddle|Cook until crisp|Serve hot"),
 ("R10", "Upma", "staple", "B", 1, 0, 30, 20, 150, 260, 7, {"rava": 60, "onion": 25, "carrot": 15, "beans": 10},
  "Roast rava lightly|Saute onion and vegetables|Add water and salt, bring to boil|Stir in rava and cover to cook"),
 ("R11", "Poha", "staple", "B", 1, 0, 25, 20, 150, 280, 6, {"poha": 60, "onion": 25, "potato": 20, "groundnuts": 8},
  "Rinse poha and drain|Temper groundnuts, onion and diced potato|Add poha and turmeric|Warm through and finish with lemon"),
 ("R12", "Pongal", "staple", "B", 1, 1, 35, 15, 150, 300, 10, {"rice": 50, "moong dal": 25},
  "Dry-roast moong dal|Cook with rice until very soft|Temper pepper and cumin|Mix well"),
 ("R13", "Sambar", "main", "B,L,D", 1, 1, 50, 20, 200, 130, 7,
  {"toor dal": 30, "carrot": 15, "beans": 15, "potato": 15, "onion": 15, "tomato": 20},
  "Pressure-cook dal|Cook vegetables with tamarind and sambar powder|Combine and simmer 10 min|Temper and serve hot"),
 ("R14", "Dal tadka", "main", "L,D", 1, 1, 45, 15, 200, 150, 9, {"toor dal": 40, "onion": 15, "tomato": 20},
  "Pressure-cook dal until soft|Prepare tempering with onion and tomato|Mix into dal|Simmer 5 min"),
 ("R15", "Chana masala", "main", "L,D", 1, 1, 70, 25, 150, 200, 10, {"chana": 40, "onion": 25, "tomato": 30},
  "Soak chana overnight|Pressure-cook until soft|Cook onion-tomato masala|Combine and simmer"),
 ("R16", "Paneer butter masala", "main", "L,D", 1, 1, 40, 30, 120, 280, 11, {"paneer": 50, "tomato": 60, "onion": 30},
  "Cube paneer|Cook onion-tomato gravy and blend|Add spices and cream/butter|Add paneer and simmer 5 min"),
 ("R17", "Chicken curry", "main", "L,D", 0, 1, 60, 35, 100, 260, 20, {"chicken": 90, "onion": 40, "tomato": 40},
  "Marinate chicken|Cook onion-tomato masala|Add chicken and cook until done (core temp 75 C)|Simmer in gravy"),
 ("R18", "Egg curry", "main", "L,D", 0, 1, 35, 25, 120, 220, 13, {"eggs": 110, "onion": 30, "tomato": 40},
  "Hard-boil eggs and peel|Cook onion-tomato masala|Add eggs and simmer 8 min|Garnish"),
 ("R19", "Rasam", "side", "L,D", 1, 0, 25, 10, 250, 50, 2.5, {"toor dal": 10, "tomato": 30},
  "Boil tomato with tamarind and rasam powder|Add cooked dal water|Temper|Serve hot"),
 ("R20", "Aloo fry", "side", "L,D", 1, 0, 35, 25, 150, 140, 3, {"potato": 100, "onion": 20},
  "Boil and cube potatoes|Temper mustard, onion|Add potato and spices|Roast until golden"),
 ("R21", "Cabbage poriyal", "side", "L,D", 1, 0, 25, 20, 150, 70, 2.5, {"cabbage": 100, "onion": 10},
  "Shred cabbage|Temper mustard and onion|Add cabbage and cook covered|Finish dry"),
 ("R22", "Beans carrot palya", "side", "L,D", 1, 0, 25, 20, 150, 80, 2.5, {"beans": 60, "carrot": 40},
  "Chop vegetables finely|Temper and add vegetables|Cook covered until tender|Add grated coconut if available"),
 ("R23", "Cauliflower masala", "side", "L,D", 1, 0, 30, 25, 150, 100, 3.5, {"cauliflower": 100, "onion": 20, "tomato": 20},
  "Cut florets|Cook onion-tomato masala|Add cauliflower and cook until tender|Dry-roast to finish"),
 ("R24", "Brinjal curry", "side", "L,D", 1, 0, 30, 25, 150, 110, 2, {"brinjal": 100, "onion": 20, "tomato": 20},
  "Cut brinjal and keep in water|Cook onion-tomato masala|Add brinjal and cook covered|Simmer until soft"),
 ("R25", "Mixed vegetable curry", "side", "L,D", 1, 0, 35, 30, 150, 110, 3,
  {"carrot": 30, "beans": 30, "potato": 30, "cauliflower": 30, "onion": 15},
  "Chop all vegetables|Cook masala base|Add vegetables and water|Simmer until tender"),
 ("R26", "Tomato chutney", "side", "B,L,D", 1, 0, 20, 15, 300, 50, 1.5, {"tomato": 60, "onion": 20},
  "Saute onion and tomato|Cool|Grind with salt and chilli|Temper and serve"),
 ("R27", "Onion raita", "side", "L,D", 1, 0, 10, 10, 300, 70, 3.5, {"curd": 80, "onion": 20},
  "Whisk curd|Add chopped onion and salt|Chill|Serve"),
]

# sample inventory: item, quantity_kg, days_to_expiry (from cooking day)
INVENTORY = [
 ("rice", 120, 300), ("toor dal", 30, 200), ("urad dal", 12, 200), ("moong dal", 8, 200), ("chana", 10, 200),
 ("wheat flour", 40, 90), ("ragi flour", 15, 90), ("rava", 15, 120), ("poha", 12, 120), ("groundnuts", 4, 120),
 ("potato", 60, 2), ("onion", 40, 12), ("tomato", 25, 1), ("carrot", 15, 4), ("beans", 12, 2),
 ("cabbage", 20, 5), ("cauliflower", 14, 1), ("brinjal", 10, 3),
 ("paneer", 12, 1), ("curd", 20, 2), ("chicken", 0, 2), ("eggs", 0, 7),
]

# food type (must match services.safety_rules) -> (idea, safe to freeze, note)
IDEAS = [
 ("Cooked rice / pulao / biryani", "Fried rice or lemon rice for the next meal", "no", "Cool within 1 hour, refrigerate, reheat once until piping hot"),
 ("Cooked rice / pulao / biryani", "Curd rice or rice kanji for the next day", "no", "Use only if refrigerated promptly"),
 ("Cooked rice / pulao / biryani", "Rice flour base for idli/dosa batter (small share)", "no", "Only from fresh, properly cooled rice"),
 ("Curry / dal / sabzi / sambar", "Blend into soup or use as a base for next day's sambar", "yes", "Refrigerate in shallow containers; reheat once to boiling"),
 ("Curry / dal / sabzi / sambar", "Stuff into parathas or sandwiches", "yes", "Vegetarian curries only; thick gravies work best"),
 ("Roti / chapati / dosa / idli", "Chapati noodles / roti upma / idli upma next breakfast", "yes", "Refrigerate promptly; use within a day"),
 ("Roti / chapati / dosa / idli", "Dry and crush for crumb coating", "yes", "Only if not damp"),
 ("Fried snacks / upma / poha", "Use as a filling for sandwiches or cutlets", "no", "Use the same day"),
 ("Dairy-based / sweets", "Convert curd to buttermilk or kadhi for the next meal", "no", "Keep refrigerated; discard if sour smell"),
 ("Salad / cut raw items", "Add to soups, sambar or palya on the same day", "no", "Short window: use within hours"),
 ("Packaged dry goods (sealed)", "Store for later use or offer to a partner", "yes", "Check best-before date"),
]

def build():
    os.makedirs(D, exist_ok=True)
    pd.DataFrame([{"item": k, "price_per_kg": v[0], "shelf_days": v[1]} for k, v in INGREDIENTS.items()]).to_csv(
        os.path.join(D, "ingredients.csv"), index=False)
    pd.DataFrame([{"recipe_id": r[0], "name": r[1], "category": r[2], "meals": r[3], "veg": r[4], "protein_flag": r[5],
                   "cook_min": r[6], "labour_min": r[7], "batch_max": r[8], "kcal": r[9], "protein_g": r[10], "steps": r[12]}
                  for r in R]).to_csv(os.path.join(D, "recipes.csv"), index=False)
    pd.DataFrame([{"recipe_id": r[0], "item": i, "grams_per_serving": g} for r in R for i, g in r[11].items()]).to_csv(
        os.path.join(D, "recipe_ingredients.csv"), index=False)
    pd.DataFrame(INVENTORY, columns=["item", "quantity_kg", "days_to_expiry"]).to_csv(
        os.path.join(D, "inventory_sample.csv"), index=False)
    pd.DataFrame(IDEAS, columns=["food_type", "idea", "safe_to_freeze", "note"]).to_csv(
        os.path.join(D, "leftover_ideas.csv"), index=False)

if __name__ == "__main__":
    build(); print("seed data written to", os.path.abspath(D))
