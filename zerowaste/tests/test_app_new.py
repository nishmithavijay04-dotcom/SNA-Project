"""End-to-end tests for the Forecast, Menu planner and Dashboard tabs (+ donation log and reuse ideas)."""
import os, sys, re
sys.path.insert(0, os.path.dirname(__file__)); sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pandas as pd
import config as C
from adapters.synthetic import generate_demand
from test_app import offline, new, find, cards, captions, APP    # noqa: F401  (offline = autouse isolation fixture)

def num(at, label):
    return int(re.sub(r"[^\d-]", "", next(m.value for m in at.metric if m.label == label).split()[0]))

def mval(at, label):
    return next(m.value for m in at.metric if m.label == label)

def successes(at): return " | ".join(s.value for s in at.success)
def warnings(at): return [w.value for w in at.warning]

# ---------------- Forecast ----------------
def test_forecast_defaults_and_ordering():
    at = new()
    exp, rec, usual = num(at, "Expected demand"), num(at, "Recommended to cook"), num(at, "Usual plan (last week + 20%)")
    assert 300 < exp < 800 and rec >= exp and usual > 0
    assert "retrains automatically" in captions(at)

def test_service_level_slider_changes_recommendation():
    at = new(); at.slider(key="fc_service").set_value(80).run(); low = num(at, "Recommended to cook")
    at.slider(key="fc_service").set_value(99).run(); high = num(at, "Recommended to cook")
    assert high > low and num(at, "Expected demand") <= low

def test_flags_and_meal_change_forecast():
    at = new(); base = num(at, "Expected demand")
    at.checkbox(key="fc_is_holiday").check().run(); assert num(at, "Expected demand") < base
    at.checkbox(key="fc_is_holiday").uncheck().run()
    at.checkbox(key="fc_is_event").check().run(); assert num(at, "Expected demand") > base
    at.checkbox(key="fc_is_event").uncheck().run()
    at.selectbox(key="fc_meal").select("Breakfast").run(); assert num(at, "Expected demand") < base

def test_date_before_history_gives_clear_error():
    at = new(); at.date_input(key="fc_date").set_value(pd.Timestamp("2024-10-10").date()).run()
    assert any("Cannot forecast" in e.value for e in at.error)

def test_forecast_accuracy_panel_present():
    at = new()
    assert any("How good is the forecaster" in e.label for e in at.expander)
    acc = next(d.value for d in at.dataframe if "MAE (servings)" in d.value.columns)
    assert len(acc) == 3 and acc["MAE (servings)"].iloc[0] < acc["MAE (servings)"].iloc[1]    # model beats last-week baseline

def test_log_actual_updates_history_file_and_retrains():
    at = new(); n0 = len(pd.read_csv(C.DEMAND_LOG))
    at.number_input(key="la_consumed").set_value(150).run()
    at.number_input(key="la_prepared").set_value(300).run()
    at.button(key="la_save").click().run()
    assert not at.exception and "Saved. The model retrained" in successes(at)
    assert len(pd.read_csv(C.DEMAND_LOG)) == n0 + 1 and len(at.session_state["demand_df"]) == n0 + 1

def test_regenerate_demo_data_scales_forecast():
    at = new(); small = num(at, "Expected demand")
    at.number_input(key="regen_strength").set_value(1800).run()
    at.button(key="regen").click().run()
    assert not at.exception and num(at, "Expected demand") > 2 * small
    assert generate_demand(strength=1800, days=30).demand.mean() > 800

def test_own_data_source_label_shows():
    at = new()
    df = generate_demand(days=90)[["date", "meal", "consumed"]]
    from services.forecaster import load_demand
    at.session_state["demand_df"] = load_demand(df); at.session_state["demand_source"] = "uploaded file (mess.csv)"
    at.run(); assert not at.exception and "uploaded file (mess.csv)" in captions(at)

# ---------------- Menu planner ----------------
def plan_of(at): return at.session_state["plan"]

def test_planner_builds_menu_with_reasons_and_guide():
    at = new(); at.button(key="pl_go").click().run()
    assert not at.exception and "Menu for" in successes(at)
    p = plan_of(at); assert p["status"] == "optimal" and len(p["menu"]) >= 3
    assert mval(at, "To buy").startswith("Rs") and "%" in mval(at, "Near-expiry stock used")
    guide = [e for e in at.expander if "batch(es)" in e.label]
    assert len(guide) == len(p["menu"])
    labels = [b.proto.label for b in at.get("download_button")]
    assert any("cooking guide" in l for l in labels)
    md = " ".join(m.value for m in at.markdown)
    assert "Why this menu" in md and "Uses " in md and "Shopping list" in md

def test_planner_default_servings_follow_forecast():
    at = new(); rec = num(at, "Recommended to cook")
    assert at.number_input(key="pl_servings_Lunch").value == rec
    at.selectbox(key="pl_meal").select("Breakfast").run()
    assert at.number_input(key="pl_servings_Breakfast").value != rec

def test_planner_breakfast_and_veg_only():
    at = new(); at.selectbox(key="pl_meal").select("Breakfast").run()
    at.checkbox(key="pl_nonveg").uncheck().run(); at.button(key="pl_go").click().run()
    p = plan_of(at); assert p["meal"] == "Breakfast" and all(m["veg"] for m in p["menu"])
    assert "breakfast" in successes(at)

def test_planner_kitchen_limits_produce_warnings():
    at = new()
    at.number_input(key="pl_pots").set_value(1).run(); at.number_input(key="pl_staff").set_value(1).run()
    at.number_input(key="pl_window").set_value(60).run(); at.button(key="pl_go").click().run()
    assert any("pot-minutes" in w for w in warnings(at))

def test_planner_rejects_bad_stock_table_and_reset_restores():
    at = new()
    bad = pd.read_csv("data/inventory_sample.csv"); bad.loc[0, "quantity_kg"] = -5
    at.session_state["inventory_df"] = bad; at.run()
    at.button(key="pl_go").click().run()
    assert any("Check your stock table" in e.value for e in at.error)
    at.button(key="pl_reset").click().run(); at.button(key="pl_go").click().run()
    assert not any("Check your stock table" in e.value for e in at.error) and plan_of(at)["status"] == "optimal"

def test_planner_infeasible_message(monkeypatch):
    import services.recipes as R
    real = R.Catalog.eligible
    monkeypatch.setattr(R.Catalog, "eligible", lambda self, meal, allow_nonveg=True: real(self, meal, allow_nonveg).query("category != 'side'"))
    at = new(); at.button(key="pl_go").click().run()
    assert any("No valid menu" in e.value for e in at.error)

# ---------------- Dashboard ----------------
def test_dashboard_shows_simulated_savings_and_empty_donations():
    at = new()
    assert mval(at, "Batches") == "0" and mval(at, "Food (kg)") == "0.0"
    assert int(mval(at, "Less food wasted").strip("%")) > 15
    assert any("Assumptions and limits" in e.label for e in at.expander)

def test_dashboard_optimizer_evaluation_button():
    at = new(); at.button(key="dash_eval").click().run()
    assert not at.exception
    assert int(mval(at, "Near-expiry stock used").split("%")[0]) > 60 and "vs random" in next(m.delta for m in at.metric if m.label == "Near-expiry stock used")

# ---------------- donation log + reuse ideas ----------------
def test_donation_is_logged_and_counts_on_dashboard():
    at = find(new())
    assert any("Record this donation" in e.label for e in at.expander)
    at.button(key="don_save").click().run()
    assert not at.exception and "Saved" in successes(at)
    log = pd.read_csv(C.DONATION_LOG)
    assert len(log) == 1 and log["qty_kg"].iloc[0] == 15 and log["partner"].iloc[0]
    assert mval(at, "Batches") == "1" and mval(at, "Food (kg)") == "15.0" and mval(at, "Meals (est.)") == str(round(15 / C.MEAL_KG))

def test_reuse_ideas_for_fresh_and_expired_food():
    at = find(new())
    assert any("Second-life ideas" in e.label for e in at.expander)
    at = new(); at.number_input(key="mins_ago").set_value(600).run(); at.button(key="find").click().run()
    assert any("do NOT serve" in e.value for e in at.error)
