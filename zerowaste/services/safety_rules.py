"""Food-safety windows. Values are conservative ASSUMPTIONS based on the general
'danger zone' idea (cooked food left at room temperature for more than ~2-4 hours is risky).
They are config values to be reviewed against FSSAI / local guidance before real use."""
from datetime import datetime, timedelta

# category -> (hours safe at room temperature, hours safe if refrigerated promptly)
SAFE_HOURS = {
    "Cooked rice / pulao / biryani":     (4, 24),
    "Curry / dal / sabzi / sambar":      (4, 24),
    "Roti / chapati / dosa / idli":      (6, 24),
    "Fried snacks / upma / poha":        (6, 24),
    "Dairy-based / sweets":              (3, 24),
    "Salad / cut raw items":             (2, 12),
    "Packaged dry goods (sealed)":       (24 * 30, 24 * 30),
}

# raw / sealed items are not "cooked food" (matters for partners that refuse cooked food)
NOT_COOKED = {"Salad / cut raw items", "Packaged dry goods (sealed)"}

def is_cooked(food_type: str) -> bool:
    return food_type not in NOT_COOKED

def food_types():
    return list(SAFE_HOURS)

def safe_until(food_type: str, cooked_time: datetime, refrigerated: bool = False) -> datetime:
    if food_type not in SAFE_HOURS:
        raise ValueError(f"Unknown food type: {food_type!r}")
    room, fridge = SAFE_HOURS[food_type]
    return cooked_time + timedelta(hours=fridge if refrigerated else room)
