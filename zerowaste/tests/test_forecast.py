import os, sys, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, pytest
import config as C
from adapters.synthetic import generate_demand
from services.forecaster import Forecaster, load_demand, add_actual, FEATURES, build_features

END = "2026-10-08"

@pytest.fixture(scope="module")
def df():
    return generate_demand(end=END)

@pytest.fixture(scope="module")
def model(df):
    return Forecaster.fit(df)

# ---------- synthetic generator ----------
def test_generator_shape_columns_and_determinism(df):
    assert len(df) == C.SYNTH_DAYS * 3 and set(df["meal"]) == set(C.MEALS)
    assert {"date", "meal", "prepared", "consumed", "ran_out", "demand", *["is_holiday", "is_exam", "is_event", "is_special"]} <= set(df.columns)
    assert df.equals(generate_demand(end=END))
    assert (df["consumed"] <= df["prepared"]).all() and (df["consumed"] <= df["demand"]).all()
    assert ((df["demand"] > df["prepared"]) == (df["ran_out"] == 1)).all()

def test_generator_patterns(df):
    d = df.assign(dow=pd.to_datetime(df["date"]).dt.dayofweek)
    lunch = d[(d["meal"] == "Lunch") & (d["is_holiday"] == 0) & (d["is_exam"] == 0) & (d["is_event"] == 0) & (d["is_special"] == 0)]
    assert lunch[lunch.dow == 5]["demand"].mean() < lunch[lunch.dow < 5]["demand"].mean()        # Saturdays lower
    assert d[d.is_holiday == 1]["demand"].mean() < d[d.is_holiday == 0]["demand"].mean()          # holidays lower
    assert d[d.is_event == 1]["demand"].mean() > d[d.is_event == 0]["demand"].mean()              # events higher
    m = pd.to_datetime(d["date"]).dt.month
    assert d[m.isin([6, 7, 8, 9])]["demand"].mean() < d[~m.isin([6, 7, 8, 9])]["demand"].mean()   # monsoon dip
    waste_share = (df["prepared"] - df["consumed"]).sum() / df["prepared"].sum()
    assert 0.10 < waste_share < 0.25                                                               # 15-25 % over-production range

def test_strength_scales_demand():
    a, b = generate_demand(strength=300, days=60, end=END), generate_demand(strength=600, days=60, end=END)
    assert 1.7 < b["demand"].mean() / a["demand"].mean() < 2.3

# ---------- no leakage ----------
def test_features_contain_no_same_day_or_future_columns():
    for bad in ("consumed", "prepared", "demand", "ran_out"):
        assert bad not in FEATURES

def test_lag_features_use_only_the_past(df):
    f = build_features(load_demand(df))
    g = f[f["meal"] == "Lunch"].set_index("date")
    d = g.index[40]
    assert g.loc[d, "lag7"] == g.loc[d - pd.Timedelta(days=7), "consumed"]
    assert g.loc[d, "lag1"] == g.loc[d - pd.Timedelta(days=1), "consumed"]
    prev = g.loc[d - pd.Timedelta(days=7):d - pd.Timedelta(days=1), "consumed"]
    assert abs(g.loc[d, "roll7"] - prev.mean()) < 1e-9                        # window excludes the day itself

def test_prediction_ignores_the_target_days_own_actual(model):
    d = model.history["date"].max() - pd.Timedelta(days=3)
    base = model.predict(d, "Lunch")["forecast"]
    h2 = model.with_actual(d, "Lunch", consumed=9999, prepared=9999)
    other = Forecaster(model=model.model, history=h2, buffer=model.buffer, val_rel=model.val_rel)
    assert other.predict(d, "Lunch")["forecast"] == base

# ---------- evaluation ----------
def test_time_split_and_model_beats_baselines(model):
    m = model.metrics
    assert m["train_end"] < m["test_start"] and m["n_test_rows"] > 100
    assert m["mae_model"] < 0.85 * m["mae_lag7"] and m["mae_model"] < m["mae_roll7"]
    assert m["mape_model"] < m["mape_lag7"]
    kinds = {r["day type"] for r in m["by_day_type"]}
    assert "normal" in kinds and "holiday" in kinds

def test_same_service_waste_reduction_is_real(model):
    m = model.metrics
    assert m["matched_waste_reduction_pct"] > 15
    assert m["matched_waste"] < m["sim_status_quo"]["waste"]
    t = m["tradeoff"]; assert t["waste"].iloc[-1] > t["waste"].iloc[0] and t["service"].iloc[-1] > t["service"].iloc[0]

# ---------- predictions ----------
def test_prediction_fields_and_service_level(model):
    d = model.history["date"].max() + pd.Timedelta(days=1)
    lo, hi = model.predict(d, "Lunch", service=0.80), model.predict(d, "Lunch", service=0.99)
    assert lo["forecast"] == hi["forecast"] and hi["recommended"] > lo["recommended"] >= lo["forecast"]
    assert 300 < lo["forecast"] < 700 and lo["status_quo"] >= lo["last_week"]

def test_flags_move_the_forecast_the_right_way(model):
    d = model.history["date"].max() + pd.Timedelta(days=1)
    normal = model.predict(d, "Lunch")["forecast"]
    assert model.predict(d, "Lunch", {"is_holiday": 1})["forecast"] < normal
    assert model.predict(d, "Lunch", {"is_event": 1})["forecast"] > normal

def test_multi_day_horizon_and_short_history(model):
    far = model.history["date"].max() + pd.Timedelta(days=5)
    assert model.predict(far, "Dinner")["forecast"] > 0
    with pytest.raises(ValueError): model.predict("2020-01-01", "Lunch")

# ---------- data loading / closed loop ----------
def test_load_demand_validation(df):
    with pytest.raises(ValueError, match="missing required"): load_demand(df.drop(columns=["consumed"]))
    with pytest.raises(ValueError, match="Unknown meal"): load_demand(df.assign(meal="Brunch"))
    with pytest.raises(ValueError, match="28 days"): load_demand(df[pd.to_datetime(df["date"]) < "2024-11-01"])
    with pytest.raises(ValueError, match="non-negative"): load_demand(df.assign(consumed=-1))
    with pytest.raises(ValueError, match="dates"): load_demand(df.assign(date="not a date"))
    minimal = df[["date", "meal", "consumed"]]
    ok = load_demand(minimal); assert (ok["is_holiday"] == 0).all()          # works without prepared/flags
    assert Forecaster.fit(minimal).metrics["mae_model"] > 0

def test_add_actual_appends_and_replaces(model):
    h = model.history
    d = h["date"].max() + pd.Timedelta(days=1)
    h2 = add_actual(h, d, "Lunch", 480, 520, {"is_event": 1})
    assert len(h2) == len(h) + 1 and h2[(h2.date == d) & (h2.meal == "Lunch")]["consumed"].iloc[0] == 480
    h3 = add_actual(h2, d, "Lunch", 500, 520)
    assert len(h3) == len(h2) and h3[(h3.date == d) & (h3.meal == "Lunch")]["consumed"].iloc[0] == 500

def test_retraining_on_new_data_changes_the_model(model):
    h = model.history
    d = h["date"].max()
    h2 = h.copy(); h2.loc[(h2.date == d) & (h2.meal == "Lunch"), "consumed"] = 100       # a strange day
    new = Forecaster.fit(h2)
    assert new.predict(d + pd.Timedelta(days=1), "Lunch")["forecast"] != model.predict(d + pd.Timedelta(days=1), "Lunch")["forecast"]
