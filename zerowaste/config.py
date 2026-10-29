"""All tunable assumptions live here, so they can be shown/justified in the report."""

# Default kitchen location (Koramangala area centre, Bengaluru). Editable in the app sidebar.
KITCHEN_DEFAULT = {"name": "My Kitchen", "lat": 12.9352, "lon": 77.6245}

# Travel-time model (assumptions, not measurements)
ROAD_FACTOR = 1.35      # road distance ~ 1.35 x straight-line distance
SPEED_KMPH = 18         # average city speed in Bengaluru traffic
HANDLING_MIN = 20       # packing + loading + handover time
BUFFER_MIN = 30         # food must reach partner this long before it expires

MAX_RADIUS_KM = 25      # ignore partners further than this (Bengaluru is large)
TOP_N = 3               # how many recommendations to show

# Ranking weights (sum to 1). Higher score = better.
W_DISTANCE = 0.40       # closer is better (linear: 1 at 0 km, 0 at MAX_RADIUS_KM)
W_SLACK = 0.25          # more spare time before expiry is better
W_SURPLUS = 0.35        # public source says the org takes surplus food (yes=1, likely=0.5, else 0)

# Road routing (OSRM public demo server; needs internet, falls back to the estimate if unreachable)
OSRM_BASE = "https://router.project-osrm.org"
OSRM_TIMEOUT_S = 6
TRAFFIC_FACTOR = 1.5    # OSRM gives free-flow driving time; Bengaluru traffic assumed ~1.5x slower (assumption)

# Approximate area centres for the kitchen-location dropdown (not exact; pick "Custom coordinates" for precision)
KITCHEN_AREAS = {
    "Koramangala": (12.9352, 77.6245), "Indiranagar": (12.9784, 77.6408), "Jayanagar": (12.9308, 77.5838),
    "JP Nagar": (12.9063, 77.5857), "BTM Layout": (12.9166, 77.6101), "HSR Layout": (12.9116, 77.6474),
    "Bellandur": (12.9260, 77.6760), "Marathahalli": (12.9569, 77.7011), "Whitefield": (12.9698, 77.7500),
    "KR Puram": (13.0073, 77.6960), "Electronic City": (12.8452, 77.6602), "Bannerghatta Road": (12.8900, 77.5970),
    "Banashankari": (12.9255, 77.5468), "Basavanagudi": (12.9400, 77.5750), "Kengeri": (12.9170, 77.4830),
    "Rajajinagar": (12.9910, 77.5550), "Malleshwaram": (13.0035, 77.5647), "Yeshwantpur": (13.0280, 77.5400),
    "Hebbal": (13.0358, 77.5970), "Yelahanka": (13.1007, 77.5963), "City centre (Majestic)": (12.9770, 77.5720),
}

# ================= Forecaster / synthetic demand (assumptions, stated in the report) =================
DEMAND_LOG = "data/demand_log.csv"
DONATION_LOG = "data/donation_log.csv"
MEALS = ["Breakfast", "Lunch", "Dinner"]
DEFAULT_STRENGTH = 600          # people the kitchen is registered to serve (generic institutional kitchen)
STATUS_QUO_BUFFER = 0.20        # cook plans "same as last week + 20%" (within the 15-25% over-production range often reported)
SYNTH_DAYS = 730                # two years of synthetic history
SYNTH_SEED = 7

# ================= Menu planner =================
NEAR_EXPIRY_DAYS = 3            # stock expiring within this many days is "urgent"
URGENCY_WEIGHT = 2.0            # value of using urgent stock = price x W/(days_left+1)
OVERCOOK_TOL = 0.0              # cook exactly the planned servings (the forecaster already adds the safety buffer)
MIN_DISH_SHARE = 0.20           # a chosen dish must cover at least 20 % of demand
DISH_PENALTY_RS = 250           # prefers simpler menus
PEN_KCAL, PEN_PROTEIN, PEN_VEG, PEN_TIME = 0.1, 2.0, 2.0, 5.0     # soft-constraint penalties (Rs per unit short)
MEAL_TARGETS = {                # per plate: minimum kcal and protein (approximate institutional targets)
    "Breakfast": {"kcal": 300, "protein": 8},
    "Lunch": {"kcal": 500, "protein": 14},
    "Dinner": {"kcal": 450, "protein": 12},
}
KITCHEN_DEFAULTS = {"pots": 4, "staff": 3, "window_min": 180, "veg_target": 0.60}

# ================= Impact (estimates; replace with cited factors in the final report) =================
MEAL_KG = 0.40                  # 1 meal ~ 0.4 kg of cooked food (assumption)
CO2E_PER_KG = 2.5               # kg CO2e per kg food waste avoided (commonly quoted order of magnitude; cite source)
FORECAST_SERVICE = 0.90         # default share of days the plan should cover demand (user can change in the app)
