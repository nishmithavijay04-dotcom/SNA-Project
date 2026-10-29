import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from datetime import datetime, timedelta
import pandas as pd, pytest
import config as C
from services.safety_rules import safe_until, food_types
from services.ngo_matcher import haversine_km, load_partners, rank_partners, eta_minutes

K = {"lat": 12.9352, "lon": 77.6245}
NOW = datetime(2026, 10, 5, 13, 0)
DEMO = os.path.join(os.path.dirname(__file__), "..", "data", "ngos_demo.csv")

def surplus(hours_left, veg=True, qty=20):
    return {"quantity_kg": qty, "veg": veg, "safe_until": NOW + timedelta(hours=hours_left)}

def test_haversine_known():
    assert haversine_km(12.9352, 77.6245, 12.9352, 77.6245) == 0
    assert 5.0 < haversine_km(12.9352, 77.6245, 12.9784, 77.6408) < 6.0   # Koramangala-Indiranagar ~5.3 km

def test_safe_until():
    t = datetime(2026, 10, 5, 12, 0)
    assert safe_until("Cooked rice / pulao / biryani", t) == t + timedelta(hours=4)
    assert safe_until("Cooked rice / pulao / biryani", t, refrigerated=True) == t + timedelta(hours=24)
    with pytest.raises(ValueError): safe_until("moon cheese", t)
    assert len(food_types()) >= 5

def test_closest_feasible_ranked_first():
    res, _ = rank_partners(load_partners(DEMO), K, surplus(4), now=NOW)
    assert res and res[0]["name"].endswith("Koramangala")
    assert len(res) <= C.TOP_N

def test_expiring_food_rejects_everyone_with_reason():
    res, rej = rank_partners(load_partners(DEMO), K, surplus(0.6), now=NOW)
    assert res == [] and len(rej) == 8
    assert all("in time" in r or "radius" in r for _, r in rej)

def test_nonveg_filter():
    res, rej = rank_partners(load_partners(DEMO), K, surplus(6, veg=False), now=NOW, top_n=10)
    assert all(r["name"] not in ("Demo Food Bank - Koramangala",) for r in res)
    assert any("non-veg" in r for _, r in rej)

def test_pickup_hours_enforced():
    late = datetime(2026, 10, 5, 23, 30)
    s = {"quantity_kg": 5, "veg": True, "safe_until": late + timedelta(hours=5)}
    res, rej = rank_partners(load_partners(DEMO), K, s, now=late, top_n=10)
    assert any("closed at expected arrival" in r for _, r in rej)
    assert {r["name"] for r in res} <= {"Demo Shelter - HSR Layout", "Demo Shelter - Electronic City"}

def test_minimal_columns_and_defaults():
    df = pd.DataFrame([{"name": "X", "latitude": 12.94, "longitude": 77.62, "phone": "123"}])
    res, _ = rank_partners(load_partners(df), K, surplus(4), now=NOW)
    assert res[0]["type"] == "Not specified" and "lat" in res[0] and "maps_url" in res[0]
    assert "confirm by phone" in res[0]["timing"]

def test_missing_required_column_and_bad_coords():
    with pytest.raises(ValueError): load_partners(pd.DataFrame([{"name": "X", "latitude": 1, "longitude": 2}]))
    with pytest.raises(ValueError): load_partners(pd.DataFrame([{"name": "X", "latitude": "abc", "longitude": 2, "phone": "1"}]))

def test_capacity_note_is_soft():
    df = pd.DataFrame([{"name": "A", "latitude": 12.94, "longitude": 77.62, "phone": "1", "capacity_kg": 5}])
    res, _ = rank_partners(load_partners(df), K, surplus(4, qty=20), now=NOW)
    assert res and res[0]["notes"]

def test_eta_increases_with_distance():
    assert eta_minutes(10) > eta_minutes(1) > C.HANDLING_MIN


# ---------- real researched partner list ----------
REAL = os.path.join(os.path.dirname(__file__), "..", "data", "partners.csv")

def test_real_file_shape_and_cleaning():
    df = load_partners(REAL)
    assert len(df) == 29                                  # duplicate Ashiana row removed
    assert df["latitude"].isna().sum() == 2               # Robin Hood Army, Swabhimaan: no address in source
    assert not df["email"].astype(str).str.contains("hdfcbank").any()   # bank handle is not an email
    ok = df.dropna(subset=["latitude"])
    assert ok["latitude"].between(12.7, 13.3).all() and ok["longitude"].between(77.3, 77.9).all()

def test_cooked_batch_skips_partner_that_refuses_cooked_food():
    df = load_partners(REAL)
    res, rej = rank_partners(df, K, surplus(4), now=NOW, top_n=40)
    assert "Bangalore Food Bank" not in " ".join(r["name"] for r in res)
    assert any("cooked" in why for n, why in rej if n.startswith("Bangalore Food Bank"))
    raw = {"quantity_kg": 10, "veg": True, "cooked": False, "safe_until": NOW + timedelta(hours=4)}
    res2, _ = rank_partners(df, K, raw, now=NOW, top_n=40)
    assert any(r["name"].startswith("Bangalore Food Bank") for r in res2)   # fine for raw/packaged items

def test_no_location_partners_reported_not_ranked():
    df = load_partners(REAL)
    res, rej = rank_partners(df, K, surplus(4), now=NOW, top_n=40)
    reasons = dict(rej)
    assert "no location" in reasons["Robin Hood Army \u2013 Bengaluru"]
    assert all(r["name"] not in reasons for r in res)

def test_only_confirmed_filter():
    df = load_partners(REAL)
    res, _ = rank_partners(df, K, surplus(4), now=NOW, top_n=40, only_confirmed=True)
    assert res and all(r["surplus_level"] == "yes" for r in res)

def test_confirmed_acceptor_gets_honest_labels_and_note():
    df = load_partners(REAL)
    res, _ = rank_partners(df, K, surplus(4), now=NOW, top_n=40)
    by = {r["name"]: r for r in res}
    fridge = by["The Public Fridge / The Public Foundation"]
    assert "confirmed" in fridge["surplus_status"].lower() and any("drop-off" in n for n in fridge["notes"])
    unconf = next(r for r in res if r["surplus_level"] == "unconfirmed")
    assert "NOT confirmed" in unconf["surplus_status"] and any("cooked-food acceptance" in n for n in unconf["notes"])

def test_nonveg_unknown_means_not_offered():
    df = load_partners(REAL)
    res, rej = rank_partners(df, K, surplus(4, veg=False), now=NOW, top_n=40)
    assert res == [] and any("non-veg" in why for _, why in rej)


def test_sort_options_and_validation():
    df = load_partners(REAL)
    near, _ = rank_partners(df, K, surplus(4), now=NOW, top_n=10, sort_by="nearest")
    fast, _ = rank_partners(df, K, surplus(4), now=NOW, top_n=10, sort_by="fastest")
    best, _ = rank_partners(df, K, surplus(4), now=NOW, top_n=10, sort_by="best")
    assert [r["distance_km"] for r in near] == sorted(r["distance_km"] for r in near)
    assert [r["eta_min"] for r in fast] == sorted(r["eta_min"] for r in fast)
    assert [r["score"] for r in best] == sorted((r["score"] for r in best), reverse=True)
    assert len(best) == 10
    with pytest.raises(ValueError): rank_partners(df, K, surplus(4), now=NOW, sort_by="random")

def test_results_carry_map_fields():
    df = load_partners(REAL)
    res, _ = rank_partners(df, K, surplus(4), now=NOW)
    r = res[0]
    assert r["maps_url"].startswith("https://www.google.com/maps/dir/?api=1&origin=12.935200,77.624500")
    assert isinstance(r["lat"], float) and isinstance(r["lon"], float)
