import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pandas as pd, pytest
import config as C
from services import impact

def test_donation_log_roundtrip_and_math(tmp_path):
    p = str(tmp_path / "d.csv")
    assert impact.read_donations(p).empty and impact.donation_summary(impact.read_donations(p))["kg"] == 0
    impact.log_donation({"date": "2026-10-01", "item": "pulao", "food_type": "Cooked rice / pulao / biryani", "qty_kg": 15, "partner": "A"}, p)
    impact.log_donation({"date": "2026-10-02", "item": "sambar", "food_type": "Curry / dal / sabzi / sambar", "qty_kg": 5, "partner": "B"}, p)
    df = impact.read_donations(p)
    assert len(df) == 2 and list(df.columns) == impact.COLS                         # header written once
    s = impact.donation_summary(df)
    assert s == {"batches": 2, "kg": 20.0, "meals": 20 / C.MEAL_KG, "co2e_kg": 20 * C.CO2E_PER_KG}

def test_forecaster_savings_conversion():
    m = {"sim_status_quo": {"waste": 1000.0}, "matched_waste": 600.0, "matched_waste_reduction_pct": 40.0}
    s = impact.forecaster_savings(m)
    assert s["servings"] == 400 and s["kg"] == pytest.approx(400 * C.MEAL_KG) and s["co2e_kg"] == pytest.approx(s["kg"] * C.CO2E_PER_KG)
    assert impact.forecaster_savings({}) is None
