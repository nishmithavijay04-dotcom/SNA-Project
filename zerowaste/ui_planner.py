"""Menu planner tab: inventory + expiry + forecast -> optimized menu, reasons, shopping list, cooking guide."""
from datetime import timedelta
import pandas as pd
import streamlit as st
import config as C
import state
from services.menu_optimizer import plan_menu
from services.recipes import load_inventory
from services.scaler import cooking_guide

SAMPLE = pd.read_csv("data/inventory_sample.csv")

def _guide_text(plan, guide):
    out = [f"{plan['meal']} for {plan['servings']} servings", ""]
    for g in guide:
        out += [f"== {g['name']} ({g['category']}) - {g['servings']} servings ==", g["note"],
                "Ingredients (total / per batch):"]
        out += [f"  {i['item']}: {i['kg']} kg / {i['per_batch_kg']} kg" for i in g["ingredients"]]
        out += ["Steps:"] + [f"  {n}. {s}" for n, s in enumerate(g["steps"], 1)] + [""]
    return "\n".join(out)

def render():
    st.markdown('<p class="zw-section">Ingredients & kitchen setup</p>', unsafe_allow_html=True)
    cat = state.catalog()
    f   = state.model()
    c1, c2, c3 = st.columns(3)
    meal     = c1.selectbox("Meal", C.MEALS, index=1, key="pl_meal")
    nxt      = f.history["date"].max() + pd.Timedelta(days=1)
    rec      = f.predict(nxt, meal)["recommended"]
    servings = c2.number_input("Servings to cook", 20, 20000, int(rec), step=10,
                               key=f"pl_servings_{meal}",
                               help=f"The forecaster suggests {rec} for the next {meal.lower()}")
    nonveg   = c3.checkbox("Include non-veg dishes", value=True, key="pl_nonveg")

    with st.expander("⚙️  Kitchen limits"):
        k1, k2, k3, k4 = st.columns(4)
        pots   = k1.number_input("Pots / vessels", 1, 50, C.KITCHEN_DEFAULTS["pots"],       key="pl_pots")
        staff  = k2.number_input("Cooks available", 1, 50, C.KITCHEN_DEFAULTS["staff"],     key="pl_staff")
        window = k3.number_input("Cooking window (min)", 30, 600, C.KITCHEN_DEFAULTS["window_min"],
                                 step=15, key="pl_window")
        veg    = k4.slider("Min veg share %", 0, 100,
                           int(C.KITCHEN_DEFAULTS["veg_target"] * 100), key="pl_veg")

    st.markdown('<p class="zw-section">Stock in hand</p>', unsafe_allow_html=True)
    st.caption("Edit quantities and expiry days. Days to expiry: 0 = expires today, negative = already expired (ignored).")
    inv_in = st.data_editor(
        st.session_state.setdefault("inventory_df", SAMPLE.copy()),
        num_rows="dynamic", key="pl_inventory", hide_index=True,
        use_container_width=True,
        column_config={
            "item":           st.column_config.SelectboxColumn("Item", options=sorted(cat.prices), required=True),
            "quantity_kg":    st.column_config.NumberColumn("Quantity (kg)", min_value=0.0),
            "days_to_expiry": st.column_config.NumberColumn("Days to expiry", step=1)})

    col_a, col_b = st.columns([1, 3])
    if col_a.button("↺ Reset to sample stock", key="pl_reset"):
        st.session_state["inventory_df"] = SAMPLE.copy(); st.rerun()

    if col_b.button("🍽️  Plan menu", type="primary", key="pl_go"):
        try:
            inv, notes = load_inventory(inv_in, cat)
            plan = plan_menu(cat, inv, meal, int(servings),
                             kitchen={"pots": int(pots), "staff": int(staff),
                                      "window_min": int(window), "veg_target": veg / 100},
                             allow_nonveg=nonveg)
            plan["notes"] = notes
            st.session_state["plan"] = plan
        except ValueError as e:
            st.session_state.pop("plan", None)
            st.error(f"Check your stock table: {e}")

    plan = st.session_state.get("plan")
    if not plan:
        return
    if plan["status"] == "infeasible":
        st.error(f"No valid menu found: {plan['reason']}"); return

    # ── Results ───────────────────────────────────────────────
    t = plan["totals"]
    st.markdown('<p class="zw-section">Optimized menu</p>', unsafe_allow_html=True)
    st.success(f"✅ Menu for **{plan['servings']} servings** of {plan['meal'].lower()} — {t['dishes']} dishes, {t['batches']} batches")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("To buy",                f"₹{t['buy_cost']:,.0f}")
    m2.metric("Near-expiry stock used", f"{plan['near_expiry']['pct_used']:.0f}%")
    m3.metric("Calories / plate",       f"{t['kcal_per_plate']:.0f} kcal")
    m4.metric("Protein / plate",        f"{t['protein_per_plate']:.1f} g")

    for w in plan["warnings"]:
        st.warning(w)

    st.markdown('<p class="zw-section">Why this menu</p>', unsafe_allow_html=True)
    for e in plan["explanations"]:
        st.markdown(f"- {e}")

    st.markdown('<p class="zw-section">Dishes</p>', unsafe_allow_html=True)
    st.dataframe(
        pd.DataFrame(plan["menu"])[["category","name","servings","batches","veg"]]
          .rename(columns={"category":"Course","name":"Dish","servings":"Servings","batches":"Batches","veg":"Veg"}),
        hide_index=True, use_container_width=True)

    ing  = plan["ingredients"]
    shop = ing[ing["buy_kg"] > 0][["item","buy_kg","price_per_kg","buy_cost"]]
    st.markdown('<p class="zw-section">Shopping list</p>', unsafe_allow_html=True)
    if len(shop):
        st.dataframe(shop.rename(columns={"item":"Item","buy_kg":"Buy (kg)",
                                          "price_per_kg":"₹/kg","buy_cost":"Cost (₹)"}),
                     hide_index=True, use_container_width=True)
        st.download_button("⬇️ Download shopping list (CSV)", shop.to_csv(index=False),
                           "shopping_list.csv", "text/csv", key="pl_dl_shop")
    else:
        st.caption("Nothing to buy — stock covers this menu.")

    with st.expander("📦  All ingredients: need vs stock"):
        st.dataframe(ing, hide_index=True, use_container_width=True)

    st.markdown('<p class="zw-section">Cooking guide</p>', unsafe_allow_html=True)
    guide = cooking_guide(plan, cat)
    for g in guide:
        with st.expander(f"🍳 {g['name']}  –  {g['servings']} servings, {g['batches']} batch(es)"):
            st.write(g["note"])
            st.dataframe(
                pd.DataFrame(g["ingredients"]).rename(columns={"item":"Ingredient","kg":"Total (kg)","per_batch_kg":"Per batch (kg)"}),
                hide_index=True, use_container_width=True)
            for n, s in enumerate(g["steps"], 1):
                st.markdown(f"{n}. {s}")
    st.download_button("⬇️ Download full cooking guide (text)", _guide_text(plan, guide),
                       "cooking_guide.txt", "text/plain", key="pl_dl_guide")
