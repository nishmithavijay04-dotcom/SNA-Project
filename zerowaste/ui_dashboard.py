"""Dashboard tab: impact numbers, forecaster accuracy and optimizer evidence."""
import pandas as pd
import streamlit as st
import config as C
import state
from services import impact
from evaluation.optimizer_eval import evaluate

def render():
    f  = state.model(); mt = f.metrics
    don = impact.read_donations()
    s  = impact.donation_summary(don)

    # ── Impact strip ──────────────────────────────────────────
    st.markdown('<p class="zw-section">Food sent to partners</p>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="zw-impact-strip">
        <div class="stat"><span class="lbl">Batches donated</span><span class="val">{s['batches']}</span></div>
        <div class="stat"><span class="lbl">Food (kg)</span><span class="val">{s['kg']:.1f}</span></div>
        <div class="stat"><span class="lbl">Meals provided (est.)</span><span class="val">{s['meals']:.0f}</span></div>
        <div class="stat"><span class="lbl">CO₂e avoided (kg est.)</span><span class="val">{s['co2e_kg']:.0f}</span></div>
    </div>
    """, unsafe_allow_html=True)

    if len(don):
        st.dataframe(don.sort_values("date", ascending=False).head(10), hide_index=True, use_container_width=True)
    else:
        st.markdown('<p class="zw-tip">No donations logged yet. Use "Record this donation" on the Find partners tab.</p>',
                    unsafe_allow_html=True)

    # ── Forecaster savings ────────────────────────────────────
    st.markdown('<p class="zw-section">Waste avoided by forecast-based planning</p>', unsafe_allow_html=True)
    sv = impact.forecaster_savings(mt)
    if sv:
        e1, e2, e3 = st.columns(3)
        e1.metric("Less food wasted",   f"{sv['pct']:.0f}%",
                  help="At the same service level as the usual 'last week + 20%' plan")
        e2.metric("Servings saved",     f"{sv['servings']:,.0f}")
        e3.metric("kg / CO₂e kg (est.)",f"{sv['kg']:,.0f} / {sv['co2e_kg']:,.0f}")
        sq, fc = mt["sim_status_quo"], mt["sim_forecast"]
        st.caption(
            f"Usual plan: {sq['service']:.0%} of meals fully covered, {sq['waste']:,.0f} servings wasted. "
            f"Forecast plan at {mt['target_service']:.0%} service: {fc['waste']:,.0f} wasted, {fc['service']:.0%} covered. "
            "Comparing at equal service is the fair test: more buffer always means more waste.")

        st.markdown('<p class="zw-section">Weekly waste (test period)</p>', unsafe_allow_html=True)
        st.line_chart(mt["weekly_waste"], height=200)
        st.caption("Weekly servings wasted: usual plan vs forecaster.")

        st.markdown('<p class="zw-section">Waste vs service level trade-off</p>', unsafe_allow_html=True)
        tr = mt["tradeoff"].set_index("service")[["waste"]]
        st.line_chart(tr, height=180)
        st.caption(f"Usual plan sits at {sq['service']:.0%} service and {sq['waste']:,.0f} wasted servings (shown for reference).")

    # ── By day type ───────────────────────────────────────────
    st.markdown('<p class="zw-section">Forecast error by day type (MAE, servings)</p>', unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(mt["by_day_type"]), hide_index=True, use_container_width=True)

    # ── Optimizer evaluation ───────────────────────────────────
    st.markdown('<p class="zw-section">Menu optimizer vs random menus</p>', unsafe_allow_html=True)
    if st.button("▶️  Run evaluation (10 random inventories)", key="dash_eval"):
        with st.spinner("Solving 10 random inventories…"):
            summary, _ = evaluate(state.catalog(), pd.read_csv("data/inventory_sample.csv"), trials=10)
        st.session_state["opt_eval"] = summary

    ev = st.session_state.get("opt_eval")
    if ev:
        x1, x2, x3 = st.columns(3)
        x1.metric("Near-expiry stock used",  f"{ev['optimizer_near_used_pct']:.0f}%",
                  f"{ev['optimizer_near_used_pct'] - ev['random_near_used_pct']:+.0f} pts vs random")
        x2.metric("Ingredients bought (₹)",  f"{ev['optimizer_buy_cost']:,.0f}",
                  f"{ev['optimizer_buy_cost'] - ev['random_buy_cost']:+,.0f} vs random",
                  delta_color="inverse")
        x3.metric("Meets nutrition target",  f"{ev['optimizer_meets_nutrition_pct']:.0f}%",
                  f"{ev['optimizer_meets_nutrition_pct'] - ev['random_meets_nutrition_pct']:+.0f} pts vs random")
        st.caption(f"Averages over {ev['trials']} random lunch inventories (450 servings). "
                   "'Random' = a random valid menu (one staple, main and side) cooked from the same stock.")

    # ── Assumptions ───────────────────────────────────────────
    with st.expander("⚠️  Assumptions and limits (include in your report)"):
        st.markdown(f"""
- Demand history is **synthetic** (generic institutional kitchen); the pipeline accepts real logs unchanged.
- The 'usual plan' is simulated as last week's consumption + {C.STATUS_QUO_BUFFER:.0%}. Real kitchens differ.
- 1 meal = **{C.MEAL_KG} kg** of food and **{C.CO2E_PER_KG} kg CO₂e** per kg of food waste are **assumed factors** — cite a source before presenting.
- Prices, nutrition values and recipe quantities are approximate seed data.
- Logged 'servings eaten' hides unmet demand when food runs out (censoring).
- Nutrition, veg share, pot-time and labour limits are soft constraints: violations show as warnings.
- Partner coordinates are approximate area centres (1–3 km error possible).
""")
