"""Forecast tab: how much to cook, plus the closed loop (log actuals -> automatic retrain)."""
from datetime import timedelta
import pandas as pd
import streamlit as st
import config as C
import state
from services.forecaster import load_demand, FLAGS

FLAG_LABEL = {
    "is_holiday": "🏖️  Holiday / low attendance",
    "is_exam":    "📚  Exam week",
    "is_event":   "🎉  Event / extra crowd",
    "is_special": "⭐  Special dish day",
}

def render():
    st.markdown('<p class="zw-section">Demand forecast</p>', unsafe_allow_html=True)
    f = state.model()
    h = f.history
    nxt = (h["date"].max() + pd.Timedelta(days=1)).date()

    c1, c2, c3 = st.columns([1, 1, 1])
    d      = c1.date_input("Date", nxt, key="fc_date")
    meal   = c2.selectbox("Meal", C.MEALS, index=1, key="fc_meal")
    service = c3.slider("Service level %", 80, 99, int(C.FORECAST_SERVICE * 100), key="fc_service",
                        help="Share of days the plan should cover demand. Higher = safer but more leftover food.")

    cols  = st.columns(4)
    flags = {fl: cols[i].checkbox(FLAG_LABEL[fl], key=f"fc_{fl}") for i, fl in enumerate(FLAGS)}

    try:
        p = f.predict(d, meal, flags, service / 100)
    except ValueError as e:
        st.error(f"Cannot forecast this date: {e}"); return

    # ── Key metrics ──────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Expected demand",          f"{p['forecast']} servings")
    m2.metric("Recommended to cook",      f"{p['recommended']} servings",
              help=f"Expected demand + {p['buffer_pct']}% safety buffer")
    m3.metric("Usual plan (last wk +20%)", f"{p['status_quo']} servings")
    diff = p["recommended"] - p["status_quo"]
    m4.metric("Difference vs usual",
              f"{diff:+d} servings",
              f"{diff * C.MEAL_KG:+.0f} kg",
              delta_color="inverse")

    st.caption(
        f"Based on past errors, cooking the recommended amount covers demand on about **{service}%** of days. "
        f"Model trained on {len(h)} rows up to {h['date'].max():%d %b %Y} "
        f"({st.session_state['demand_source']}); retrains automatically when the log changes.")

    # ── 28-day chart ─────────────────────────────────────────
    st.markdown('<p class="zw-section">Last 28 days – {}</p>'.format(meal.lower()), unsafe_allow_html=True)
    hist = h[h["meal"] == meal].tail(28).set_index("date")
    cols_plot = [c for c in ("consumed", "prepared") if c in hist.columns]
    st.line_chart(hist[cols_plot], height=200)
    st.caption(f"Servings eaten vs servings cooked for {meal.lower()}.")

    # ── Accuracy expander ─────────────────────────────────────
    mt = f.metrics
    with st.expander("📊  How good is the forecaster? (held-out test period)"):
        acc = pd.DataFrame({
            "Method":          ["Random Forest model", "Same as last week", "Average of last 7 days"],
            "MAE (servings)":  [mt["mae_model"], mt["mae_lag7"], mt["mae_roll7"]],
            "MAPE %":          [mt["mape_model"], mt["mape_lag7"], mt["mape_roll7"]]}).round(1)
        st.dataframe(acc, hide_index=True, use_container_width=True)
        st.caption(
            f"Trained on data before {mt['train_end']}, tested from {mt['test_start']} (never seen in training). "
            "Only information known the day before is used (calendar flags and past consumption).")

    # ── Log actuals ───────────────────────────────────────────
    with st.expander("📝  Log what actually happened (keeps the model learning)"):
        if st.session_state.get("la_msg"):
            st.success(st.session_state.pop("la_msg"))
        l1, l2 = st.columns(2)
        ld = l1.date_input("Date", nxt, key="la_date")
        lm = l2.selectbox("Meal", C.MEALS, index=1, key="la_meal")
        l3, l4 = st.columns(2)
        lp = l3.number_input("Servings cooked", min_value=0, value=int(p["recommended"]), step=10, key="la_prepared")
        lc = l4.number_input("Servings eaten",  min_value=0, value=int(p["forecast"]),     step=10, key="la_consumed")
        lflags = {fl: st.checkbox(FLAG_LABEL[fl], key=f"la_{fl}") for fl in FLAGS}
        if st.button("💾  Save actual", key="la_save"):
            before = f.predict(pd.Timestamp(ld) + timedelta(days=1), lm)["forecast"]
            state.log_actual(ld, lm, int(lc), int(lp), lflags)
            after  = state.model().predict(pd.Timestamp(ld) + timedelta(days=1), lm)["forecast"]
            st.session_state["la_msg"] = (
                f"Saved. Model retrained: forecast for {lm.lower()} on "
                f"{(pd.Timestamp(ld) + timedelta(days=1)):%d %b} changed from {before} → {after}.")
            st.rerun()

    # ── Upload / regen ────────────────────────────────────────
    with st.expander("📂  Use your own data / change kitchen size"):
        up = st.file_uploader(
            "Upload your demand log (CSV: date, meal, consumed; optional prepared and flag columns)",
            type="csv", key="demand_upload")
        if up is not None and st.session_state.get("upload_id") != (up.name, up.size):
            try:
                state.set_demand(load_demand(up), f"uploaded file ({up.name})")
                st.session_state["upload_id"] = (up.name, up.size); st.rerun()
            except ValueError as e:
                st.error(f"Could not use this file: {e}")
        g1, g2 = st.columns([2, 1])
        strength = g1.number_input("Kitchen strength (people served) for demo data",
                                   50, 20000, C.DEFAULT_STRENGTH, step=50, key="regen_strength")
        if g2.button("🔄  Regenerate demo data", key="regen"):
            state.regenerate(int(strength)); st.rerun()
        st.caption(
            "The demo history is synthetic (weekday/weekend, monsoon dip, holidays, exams, events, noise). "
            "Upload real logs to replace it; nothing else in the app changes.")
