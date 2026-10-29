"""End-to-end tests of every app feature (headless Streamlit). Network is mocked: no real routing calls."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from urllib.parse import urlparse, parse_qs
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest
from services import routing

APP = os.path.join(os.path.dirname(__file__), "..", "app.py")

@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    import shutil, config as C
    shutil.copy(os.path.join(os.path.dirname(__file__), "..", "data", "demand_log.csv"), tmp_path / "demand_log.csv")
    monkeypatch.setattr(C, "DEMAND_LOG", str(tmp_path / "demand_log.csv"))
    monkeypatch.setattr(C, "DONATION_LOG", str(tmp_path / "donation_log.csv"))
    st.cache_data.clear()
    def down(*a, **k): raise routing.RoutingError("offline (test)")
    monkeypatch.setattr(routing, "road_times", down)
    monkeypatch.setattr(routing, "route_path", down)

def new():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    return at

def find(at):
    at.button(key="find").click().run()
    assert not at.exception
    return at

def _all_text(at):
    """All renderable text: markdown + captions + info + success + error + warning values."""
    parts = []
    for col in ("markdown", "caption", "info", "success", "error", "warning"):
        try:
            parts.extend(e.value for e in getattr(at, col))
        except Exception:
            pass
    return " | ".join(parts)

def cards(at):
    """Partner card names – look in all markdown for the numbered card header HTML."""
    found = []
    for m in at.markdown:
        # new HTML-rendered card headers contain the numbered circle + partner name
        match = re.search(r'zw-partner-num[^>]*>\d+</span>.*?zw-partner-name[^>]*>(.*?)</span>', m.value, re.DOTALL)
        if match:
            found.append(match.group(0))
    # fallback: old plain-markdown style **N. Name**
    if not found:
        found = [m.value for m in at.markdown if re.match(r"^\*\*\d+\. ", m.value)]
    return found

def distances(at):
    return [float(m.value.split()[0]) for m in at.metric if m.label == "Distance"]

def captions(at):
    return " | ".join(c.value for c in at.caption)

def dir_df(at):
    # column name changed from "Straight-line km" to "Distance (km)"
    return next(d.value for d in at.dataframe
                if "Partner" in d.value.columns and
                   ("Straight-line km" in d.value.columns or "Distance (km)" in d.value.columns))

def decks(at):
    return [d.proto.json for d in at.get("deck_gl_json_chart")]

# ---------- start-up ----------
def test_startup_has_two_tabs_and_no_results_yet():
    at = new()
    # Tab labels may include emoji prefixes – check core words are present
    labels = [t.label for t in at.tabs]
    assert len(labels) == 5
    assert any("Forecast" in l for l in labels)
    assert any("Menu planner" in l for l in labels)
    assert any("Find partners" in l for l in labels)
    assert any("Partner directory" in l for l in labels)
    assert any("Dashboard" in l for l in labels)
    assert cards(at) == [] and "29 partners loaded" in _all_text(at)

# ---------- find partners ----------
def test_default_search_recommends_confirmed_cooked_partner_first():
    at = find(new())
    cs = cards(at)
    assert len(cs) >= 1 and "Public Fridge" in cs[0]
    # safe-until banner is now HTML in a markdown block
    assert any("safe until" in m.value.lower() or "Safe until" in m.value for m in at.markdown) or \
           any("safe until" in i.value.lower() for i in at.info)
    # Phone number appears somewhere in the rendered text
    all_text = _all_text(at)
    assert "+91" in all_text or "Phone" in all_text
    assert "phone before you go" in all_text

def test_expired_batch_blocked_and_fridge_extends_window():
    at = new(); at.number_input(key="mins_ago").set_value(600)
    find(at)
    assert any("past its safe window" in e.value for e in at.error) and cards(at) == []
    at.checkbox(key="fridge").check().run()                      # refrigerated: 24 h window, so still safe
    at.button(key="find").click().run()
    assert not any("past its safe window" in e.value for e in at.error) and cards(at)

def test_nonveg_returns_no_partner_with_exclusion_reason():
    at = new(); at.radio(key="veg").set_value("Non-veg"); find(at)
    assert any("No partner can safely" in e.value for e in at.error) and cards(at) == []

def test_cooked_vs_packaged_changes_who_is_eligible():
    at = find(new()); at.checkbox(key="only_conf").check().run()
    assert len(cards(at)) == 1 and "Public Fridge" in cards(at)[0]          # cooked: Food Bank refuses cooked
    at.selectbox(key="ftype").select("Packaged dry goods (sealed)").run()
    at.button(key="find").click().run()                          # food inputs apply when Find is pressed
    cs = cards(at)
    assert len(cs) == 2 and any("Bangalore Food Bank" in c for c in cs)     # sealed goods: both confirmed partners

def test_results_stay_when_controls_change_and_controls_work():
    at = find(new())
    at.slider(key="n_results").set_value(6).run()
    assert len(cards(at)) == 6                                              # no need to press Find again
    at.selectbox(key="sort_by").select("Nearest first").run()
    d = distances(at); assert d == sorted(d)
    at.selectbox(key="sort_by").select("Shortest trip").run()
    etas = [int(m.value.split()[0]) for m in at.metric if m.label == "Est. trip"]
    assert etas == sorted(etas)
    at.slider(key="n_results").set_value(1).run(); assert len(cards(at)) == 1

def test_changing_kitchen_area_updates_results():
    at = find(new()); before = distances(at)
    at.selectbox(key="area").select("Whitefield").run()
    assert not at.exception and distances(at) != before and cards(at)

def test_custom_coordinates_inputs_work():
    at = find(new())
    at.selectbox(key="area").select("Custom coordinates").run()
    at.number_input(key="klat").set_value(13.0358).run()
    at.number_input(key="klon").set_value(77.5970).run()
    assert not at.exception and cards(at)

def test_exclusion_list_and_accuracy_note_present():
    at = find(new())
    labels = [e.label for e in at.expander]
    assert any("excluded" in l for l in labels) and any("accurate" in l for l in labels)

# ---------- links, maps, export ----------
def test_link_buttons_have_valid_google_osm_urls():
    at = find(new())
    urls = [b.proto.url for b in at.get("link_button")]
    assert len(urls) == 3 * 3 + 3                                           # 3 cards + directory detail
    d = [u for u in urls if "/maps/dir/" in u]
    assert d and all(parse_qs(urlparse(u).query)["origin"] == ["12.935200,77.624500"] for u in d)
    assert all("travelmode=driving" in u for u in d)
    assert any("/maps/search/" in u for u in urls) and any("openstreetmap.org" in u for u in urls)

def test_map_has_kitchen_partners_and_legend():
    at = find(new())
    js = decks(at)
    assert len(js) == 2                                                     # results map + directory map
    f = re.sub(r"\s+", "", js[0])
    assert "Yourkitchen" in f and "[220,40,40" in f and "[30,100,220" in f and "[150,150,150" in f
    md = " ".join(m.value for m in at.markdown)
    assert "🔴" in md and "🔵" in md and "⚪" in md

def test_download_button_present_after_search():
    at = new(); assert not at.get("download_button")
    find(at); assert len(at.get("download_button")) == 1

# ---------- routing ----------
def test_road_routing_success_uses_road_data_and_draws_path(monkeypatch):
    st.cache_data.clear()
    monkeypatch.setattr(routing, "road_times", lambda k, pts: {n: (7.0, 15.0) for n, _, _ in pts})
    monkeypatch.setattr(routing, "route_path", lambda k, la, lo: [[k["lon"], k["lat"]], [lo, la]])
    at = find(new())
    assert set(distances(at)) == {7.0} and "by road" in _all_text(at)
    assert '"PathLayer"' in decks(at)[0]

def test_routing_failure_falls_back_with_message():
    at = find(new())
    all_text = _all_text(at)
    assert "Road routing unavailable" in all_text and "away (estimated)" in all_text and cards(at)

def test_routing_toggle_off_never_calls_server(monkeypatch):
    def forbidden(*a, **k): raise AssertionError("routing must not be called")
    monkeypatch.setattr(routing, "road_times", forbidden)
    at = new(); at.checkbox(key="use_road").uncheck().run(); find(at)
    assert cards(at) and "unavailable" not in _all_text(at)

# ---------- directory ----------
def test_directory_lists_all_sorted_with_unlocated_last():
    at = new()
    df = dir_df(at)
    assert len(df) == 29 and list(df.columns)[:2] == ["Partner", "Area"]
    # Accept either column name (old or new)
    km_col = "Straight-line km" if "Straight-line km" in df.columns else "Distance (km)"
    km = df[km_col].dropna().tolist(); assert km == sorted(km)
    assert df[km_col].isna().sum() == 2 and df[km_col].isna().iloc[-2:].all()

def test_directory_search_and_confirmed_filter():
    at = new(); at.text_input(key="dir_search").set_value("yelahanka").run()
    df = dir_df(at)
    assert 0 < len(df) < 29 and df.apply(lambda r: "yelahanka" in (r["Partner"] + r["Area"]).lower(), axis=1).any()
    at.text_input(key="dir_search").set_value("").run()
    at.checkbox(key="dir_conf").check().run()
    assert len(dir_df(at)) == 3

def test_directory_detail_panel_and_no_location_message():
    at = new()
    sel = at.selectbox(key="dir_partner")
    sel.select("Robin Hood Army \u2013 Bengaluru").run()
    assert any("No location on file" in c.value for c in at.caption)
    at.selectbox(key="dir_partner").select("The Public Fridge / The Public Foundation").run()
    all_text = _all_text(at)
    assert "+91" in all_text or "9884466228" in all_text
    assert not any("No location on file" in c.value for c in at.caption)
