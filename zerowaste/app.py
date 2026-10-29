"""ZeroWaste Kitchen. Run:  streamlit run app.py
Read-only: recommends partners and shows their details. Nothing is contacted."""
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import streamlit as st
import config as C
from services.safety_rules import food_types, safe_until, is_cooked
from services.ngo_matcher import load_partners, rank_partners, haversine_km, SURPLUS_LABEL, _txt as txt
from services.mapview import build_deck, build_directory_deck
from services.links import google_directions_url, google_place_url, osm_url
from services import routing, impact, repurposer
import state, ui_forecast, ui_planner, ui_dashboard

SORTS = {"Best match": "best", "Nearest first": "nearest", "Shortest trip": "fastest"}
SHORT = {"yes": "Confirmed", "likely": "Reported", "unconfirmed": "Not confirmed"}
BADGE = {"yes": "badge-confirmed", "likely": "badge-reported", "unconfirmed": "badge-unconfirmed"}

st.set_page_config(page_title="ZeroWaste Kitchen", page_icon="♻️", layout="centered")

# ── Inject CSS ──────────────────────────────────────────────
_css_path = Path(__file__).parent / "style.css"
if _css_path.exists():
    st.markdown(f"<style>{_css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

# ── Sidebar ─────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class="zw-sidebar-brand">
        <span class="logo">♻️</span>
        <div>
            <div class="name">ZeroWaste Kitchen</div>
            <div class="tagline">Smart food surplus management</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.header("Your kitchen")
    kname = st.text_input("Kitchen name", C.KITCHEN_DEFAULT["name"], key="kname")
    area = st.selectbox("Area", list(C.KITCHEN_AREAS) + ["Custom coordinates"], key="area")
    if area == "Custom coordinates":
        klat = st.number_input("Latitude", value=C.KITCHEN_DEFAULT["lat"], format="%.5f", key="klat")
        klon = st.number_input("Longitude", value=C.KITCHEN_DEFAULT["lon"], format="%.5f", key="klon")
        st.caption("Right-click your kitchen on Google Maps → click the numbers to copy.")
    else:
        klat, klon = C.KITCHEN_AREAS[area]
        st.caption(f"Centre of {area} ({klat:.4f}, {klon:.4f}). Choose 'Custom coordinates' for exact distances.")

    st.header("Routing")
    use_road = st.checkbox("Use real road distance (needs internet)", value=True, key="use_road")
    st.caption("Falls back to an estimate if the server is unreachable.")

    st.header("Partner list")
    up = st.file_uploader("Upload a different partner CSV (optional)", type="csv", key="upload")
    st.caption("Required columns: name, latitude, longitude, phone")

# ── Load partners ───────────────────────────────────────────
try:
    partners = load_partners(up if up is not None else "data/partners.csv")
except Exception as e:
    st.error(f"Could not read partner file: {e}"); st.stop()
kitchen = {"lat": klat, "lon": klon}

@st.cache_data(ttl=3600, show_spinner=False)
def cached_road_times(klat, klon, pts):
    return routing.road_times({"lat": klat, "lon": klon}, list(pts))

@st.cache_data(ttl=3600, show_spinner=False)
def cached_path(klat, klon, lat, lon):
    return routing.route_path({"lat": klat, "lon": klon}, lat, lon)

# ── Page header ──────────────────────────────────────────────
n_loc  = int(partners["latitude"].notna().sum())
n_conf = int((partners["accepts_surplus"] == "yes").sum())
st.markdown(f"""
<div class="zw-page-header">
    <h1>♻️ ZeroWaste Kitchen</h1>
</div>
<p class="zw-subtitle">
    {len(partners)} redistribution partners loaded &nbsp;·&nbsp;
    {n_loc} with a location &nbsp;·&nbsp;
    {n_conf} with confirmed surplus intake &nbsp;·&nbsp;
    <span style="color:#D99A36;font-weight:600;">Partner locations are approximate area centres.</span>
</p>
""", unsafe_allow_html=True)

# ── Tabs ─────────────────────────────────────────────────────
tab_fc, tab_plan, tab_find, tab_dir, tab_dash = st.tabs(
    ["📈  Forecast", "🍽️  Menu planner", "🤝  Find partners", "📋  Partner directory", "📊  Dashboard"])

with tab_fc:
    ui_forecast.render()
with tab_plan:
    ui_planner.render()
with tab_dash:
    ui_dashboard.render()

# ── Helper: 3 map link buttons ────────────────────────────────
def link_buttons(lat, lon, key):
    c1, c2, c3 = st.columns(3)
    c1.link_button("🗺️ Directions",   google_directions_url(klat, klon, lat, lon), key=f"dir_{key}")
    c2.link_button("📍 Google Maps",   google_place_url(lat, lon),                 key=f"gm_{key}")
    c3.link_button("🌐 OpenStreetMap", osm_url(lat, lon),                          key=f"osm_{key}")


# ════════════════════════════════════════════════════════════
#  Tab: Find partners
# ════════════════════════════════════════════════════════════
with tab_find:
    st.markdown('<p class="zw-section">Log surplus food</p>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    ftype = c1.selectbox("Food type", food_types(), key="ftype")
    item  = c2.text_input("Item (e.g. veg pulao)", "Veg pulao", key="item")
    c3, c4 = st.columns(2)
    qty   = c3.number_input("Quantity (kg)", min_value=0.5, value=15.0, step=0.5, key="qty")
    veg   = c4.radio("Type", ["Veg", "Non-veg"], horizontal=True, key="veg") == "Veg"
    c5, c6 = st.columns(2)
    mins_ago = c5.number_input("Cooked how many minutes ago?", min_value=0, value=60, step=15, key="mins_ago")
    fridge   = c6.checkbox("Refrigerated promptly", value=False, key="fridge")

    if st.button("🔍  Find partners", type="primary", key="find"):
        st.session_state["query"] = {
            "item": item, "qty": qty, "veg": veg, "ftype": ftype, "fridge": fridge,
            "cooked_at": datetime.now() - timedelta(minutes=int(mins_ago))}

    q = st.session_state.get("query")
    if q:
        st.divider()
        d1, d2, d3 = st.columns([1, 1, 1])
        n_results  = d1.slider("How many results", 1, 10, C.TOP_N, key="n_results")
        sort_label = d2.selectbox("Sort by", list(SORTS), key="sort_by")
        only_conf  = d3.checkbox("Only confirmed partners", value=False, key="only_conf")

        now = datetime.now()
        sa  = safe_until(q["ftype"], q["cooked_at"], q["fridge"])
        left = (sa - now).total_seconds() / 60

        if left <= 30:
            banner_cls = "danger"
            banner_icon = "🚨"
        elif left <= 90:
            banner_cls = "warning"
            banner_icon = "⚠️"
        else:
            banner_cls = ""
            banner_icon = "✅"

        st.markdown(
            f'<div class="zw-safe-banner {banner_cls}">'
            f'{banner_icon} &nbsp;<strong>{q["item"]}</strong> ({q["qty"]:g} kg)  ·  '
            f'Safe until <strong>{sa:%d %b, %H:%M}</strong>  ·  '
            f'<strong>{max(left,0):.0f} min left</strong>'
            f'</div>', unsafe_allow_html=True)

        if left <= 0:
            st.error("🚨 This batch is past its safe window and should **not** be redistributed for consumption.")
        else:
            road = None
            if use_road:
                loc = partners.dropna(subset=["latitude", "longitude"])
                try:
                    road = cached_road_times(klat, klon,
                        tuple(zip(loc["name"], loc["latitude"], loc["longitude"])))
                except routing.RoutingError:
                    st.markdown('<p class="zw-tip">📡 Road routing unavailable right now – using estimated trip times.</p>',
                                unsafe_allow_html=True)

            surplus = {"quantity_kg": q["qty"], "veg": q["veg"],
                       "cooked": is_cooked(q["ftype"]), "safe_until": sa}
            res, rej = rank_partners(partners, kitchen, surplus, now=now, top_n=n_results,
                                     only_confirmed=only_conf, road=road, sort_by=SORTS[sort_label])
            if road:
                for r in res:
                    try:
                        r["path"] = cached_path(klat, klon, r["lat"], r["lon"])
                    except routing.RoutingError:
                        pass

            if not res:
                st.error("No partner can safely receive this batch in time. Consider the second-life ideas below.")
            else:
                st.markdown('<p class="zw-tip">📞 Please phone before you go – many partners have not publicly confirmed they accept surplus food.</p>',
                            unsafe_allow_html=True)

            # ── Partner cards ──────────────────────────────────
            st.markdown('<p class="zw-section">Recommended partners</p>', unsafe_allow_html=True)
            for i, r in enumerate(res, 1):
                badge_cls = BADGE.get(r.get("surplus_level", "unconfirmed"), "badge-unconfirmed")
                badge_lbl = SHORT.get(r.get("surplus_level", "unconfirmed"), "Not confirmed")
                with st.container(border=True):
                    # Header row
                    st.markdown(
                        f'<div class="zw-partner-header">'
                        f'<span class="zw-partner-num">{i}</span>'
                        f'<div>'
                        f'<span class="zw-partner-name">{r["name"]}</span>'
                        f'&nbsp;&nbsp;<span class="badge {badge_cls}">{badge_lbl}</span>'
                        f'</div>'
                        f'</div>'
                        f'<p class="zw-partner-meta">{r["type"]}{(", "+r["area"]) if r["area"] else ""}</p>',
                        unsafe_allow_html=True)

                    # Metric mini row
                    st.markdown(
                        f'<div class="zw-metric-row">'
                        f'<div class="zw-metric-mini"><span class="label">Distance</span><span class="value">{r["distance_km"]} km</span></div>'
                        f'<div class="zw-metric-mini"><span class="label">Est. trip</span><span class="value">{r["eta_min"]} min</span></div>'
                        f'<div class="zw-metric-mini"><span class="label">Spare time</span><span class="value">{r["spare_min"]} min</span></div>'
                        f'</div>', unsafe_allow_html=True)

                    # Contact
                    parts = []
                    if r["phone"]:   parts.append(f'📞 {r["phone"]}')
                    if r["email"]:   parts.append(f'✉️ <a href="mailto:{r["email"]}" style="color:#2F6B52">{r["email"]}</a>')
                    if r["website"]: parts.append(f'🌐 <a href="{r["website"]}" target="_blank" style="color:#2F6B52">{r["website"]}</a>')
                    if parts:
                        st.markdown(
                            '<div class="zw-contact-row">' +
                            "".join(f"<span>{p}</span>" for p in parts) +
                            "</div>", unsafe_allow_html=True)
                    if r["address"]:
                        st.markdown(f'<p class="zw-note">📍 {r["address"]}</p>', unsafe_allow_html=True)

                    # Why / notes
                    st.markdown(r["surplus_status"])
                    st.caption(f"Why: {r['reason']}")
                    for n in r["notes"]:
                        st.caption(f"Note: {n}")

                    link_buttons(r["lat"], r["lon"], i)

            # ── Map ──────────────────────────────────────────
            if res:
                st.markdown('<p class="zw-section">Map</p>', unsafe_allow_html=True)
                shown  = {r["name"] for r in res}
                others = [{"name": p["name"], "lat": float(p["latitude"]), "lon": float(p["longitude"]),
                           "info": f"{txt(p['area'])} | not in top {len(res)}"}
                          for _, p in partners.dropna(subset=["latitude","longitude"]).iterrows()
                          if p["name"] not in shown]
                st.pydeck_chart(build_deck(kitchen, res, kname, others))
                st.caption("🔴 Your kitchen · 🔵 Recommended partners (numbered) · ⚪ Other partners · Blue lines = road routes")

                export = pd.DataFrame([{k: r[k] for k in
                    ("name","type","area","distance_km","eta_min","spare_min","phone","email","website","address","maps_url")}
                    for r in res])
                st.download_button("⬇️ Download results (CSV)", export.to_csv(index=False),
                                   "recommended_partners.csv", "text/csv", key="dl")

                with st.expander("📝 Record this donation (feeds the dashboard)"):
                    if st.session_state.get("don_msg"):
                        st.success(st.session_state.pop("don_msg"))
                    to = st.selectbox("Sent to", [r["name"] for r in res], key="don_partner")
                    if st.button("Save to donation log", key="don_save"):
                        impact.log_donation({"date": datetime.now().date().isoformat(), "item": q["item"],
                                             "food_type": q["ftype"], "qty_kg": q["qty"], "partner": to}, C.DONATION_LOG)
                        st.session_state["don_msg"] = "✅ Saved. It now counts in the Dashboard."
                        st.rerun()

            if rej:
                with st.expander(f"⛔ Why {len(rej)} partner(s) were excluded"):
                    for name, why in rej:
                        st.write(f"- **{name}:** {why}")

        ideas = repurposer.suggest(q["ftype"], left, q["fridge"])
        with st.expander("♻️ Rather reuse it in your kitchen? Second-life ideas",
                         expanded=(not ideas["safe_for_people"])):
            if ideas["message"]:
                st.error(ideas["message"])
            for i in ideas["ideas"]:
                st.markdown(f"- **{i['idea']}** – {i['note']}")
            if ideas["safe_for_people"] and not ideas["ideas"]:
                st.caption("No reuse idea fits this food in the time left; donating is the better option.")

        with st.expander("ℹ️ How accurate are the distances?"):
            st.write("With road routing on, distance and time come from real roads. Accuracy is limited by the "
                     "partner points (approximate area centres, 1–3 km off is possible) and your kitchen location. "
                     "Trip time = road time × 1.5 (traffic) + 20 min handling. Without internet it uses straight-line "
                     "× 1.35 at ~18 km/h + 20 min. Use the Google Maps button for a live check.")


# ════════════════════════════════════════════════════════════
#  Tab: Partner directory
# ════════════════════════════════════════════════════════════
with tab_dir:
    st.markdown('<p class="zw-section">All partners</p>', unsafe_allow_html=True)

    s1, s2 = st.columns([3, 1])
    search    = s1.text_input("🔍  Search by name, area or type", key="dir_search",
                              placeholder="e.g. food bank, Koramangala…")
    conf_only = s2.checkbox("Only confirmed", key="dir_conf")

    df = partners.copy()
    df["straight_km"] = [haversine_km(klat, klon, a, b) if pd.notna(a) and pd.notna(b) else None
                         for a, b in zip(df["latitude"], df["longitude"])]
    if search.strip():
        s = search.strip().lower()
        df = df[df.apply(lambda r: s in f"{r['name']} {r['area']} {r['type']}".lower(), axis=1)]
    if conf_only:
        df = df[df["accepts_surplus"] == "yes"]
    df = df.sort_values("straight_km", na_position="last")

    table = pd.DataFrame({
        "Partner":        df["name"],
        "Area":           df["area"],
        "Phone":          df["phone"],
        "Surplus intake": df["accepts_surplus"].map(SHORT),
        "Distance (km)":  df["straight_km"].round(1)})
    st.dataframe(table, hide_index=True, use_container_width=True)
    st.caption(f"{len(df)} partner(s) shown · nearest first (straight-line distance from your kitchen).")

    st.markdown('<p class="zw-section">Map view</p>', unsafe_allow_html=True)
    st.pydeck_chart(build_directory_deck(kitchen, df, kname))
    st.caption("🔴 Your kitchen · 🟢 Confirmed · 🟠 Reported · ⚪ Not confirmed")

    if len(df):
        st.markdown('<p class="zw-section">Partner details</p>', unsafe_allow_html=True)
        sel = st.selectbox("Select a partner to view details", list(df["name"]), key="dir_partner")
        p   = df[df["name"] == sel].iloc[0]
        badge_cls = BADGE.get(p["accepts_surplus"], "badge-unconfirmed")
        badge_lbl = SHORT.get(p["accepts_surplus"], "Not confirmed")

        with st.container(border=True):
            st.markdown(
                f'<div class="zw-partner-header">'
                f'<div>'
                f'<span class="zw-partner-name">{p["name"]}</span>'
                f'&nbsp;&nbsp;<span class="badge {badge_cls}">{badge_lbl}</span>'
                f'</div></div>'
                f'<p class="zw-partner-meta">{p["type"]}</p>',
                unsafe_allow_html=True)

            contact_parts = []
            if txt(p["phone"]):   contact_parts.append(f'📞 {txt(p["phone"])}')
            if txt(p["email"]):   contact_parts.append(f'✉️ <a href="mailto:{txt(p["email"])}" style="color:#2F6B52">{txt(p["email"])}</a>')
            if txt(p["website"]): contact_parts.append(f'🌐 <a href="{txt(p["website"])}" target="_blank" style="color:#2F6B52">{txt(p["website"])}</a>')
            if contact_parts:
                st.markdown('<div class="zw-contact-row">' +
                            "".join(f"<span>{cp}</span>" for cp in contact_parts) +
                            "</div>", unsafe_allow_html=True)
            if txt(p["address"]):
                st.markdown(f'<p class="zw-note">📍 {txt(p["address"])}</p>', unsafe_allow_html=True)

            st.markdown(SURPLUS_LABEL.get(p["accepts_surplus"], SURPLUS_LABEL["unconfirmed"]))
            if txt(p["cooked_note"]):
                st.caption(f"Cooked food: {txt(p['cooked_note'])}")
            if pd.notna(p["latitude"]):
                link_buttons(float(p["latitude"]), float(p["longitude"]), "dir")
            else:
                st.caption("No location on file – phone them to ask where to deliver.")
