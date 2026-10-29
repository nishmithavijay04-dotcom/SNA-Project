"""Impact numbers: donation log + forecaster savings. All factors are assumptions in config.py."""
import os
import pandas as pd
import config as C

COLS = ["date", "item", "food_type", "qty_kg", "partner"]

def log_donation(record, path=None):
    path = path or C.DONATION_LOG
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    row = pd.DataFrame([{c: record.get(c, "") for c in COLS}])
    row.to_csv(path, mode="a", header=not os.path.exists(path), index=False)

def read_donations(path=None):
    path = path or C.DONATION_LOG
    if not os.path.exists(path):
        return pd.DataFrame(columns=COLS)
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df

def donation_summary(df):
    kg = float(df["qty_kg"].sum()) if len(df) else 0.0
    return {"batches": len(df), "kg": kg, "meals": kg / C.MEAL_KG, "co2e_kg": kg * C.CO2E_PER_KG}

def forecaster_savings(metrics):
    """Waste avoided by forecast-based planning at the SAME service level (test period), converted to kg / CO2e."""
    if "matched_waste" not in metrics:
        return None
    servings = metrics["sim_status_quo"]["waste"] - metrics["matched_waste"]
    kg = servings * C.MEAL_KG
    return {"servings": servings, "kg": kg, "co2e_kg": kg * C.CO2E_PER_KG, "pct": metrics["matched_waste_reduction_pct"]}
