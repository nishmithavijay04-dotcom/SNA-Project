"""PyDeck maps. Colours: kitchen = RED (with a 'K'), recommended partners = BLUE (numbered),
other partners = GREY. Directory map: GREEN = surplus intake confirmed, ORANGE = reported, GREY = not confirmed."""
import pandas as pd
import pydeck as pdk

RED, BLUE, GREY = [220, 40, 40, 245], [30, 100, 220, 225], [150, 150, 150, 200]
GREEN, ORANGE = [40, 160, 80, 225], [240, 150, 30, 225]

def _view(points, kitchen):
    try:
        v = pdk.data_utils.compute_view(points, 0.9)
    except Exception:
        v = pdk.ViewState(latitude=kitchen["lat"], longitude=kitchen["lon"], zoom=11)
    v.pitch = 0
    return v

def _kitchen_layers(kitchen, name):
    k = pd.DataFrame([{"name": name, "lat": kitchen["lat"], "lon": kitchen["lon"], "info": "Your kitchen", "label": "K"}])
    return [pdk.Layer("ScatterplotLayer", k, get_position="[lon, lat]", get_fill_color=RED, get_radius=250,
                      radius_min_pixels=15, radius_max_pixels=26, pickable=True, stroked=True,
                      get_line_color=[255, 255, 255, 255], line_width_min_pixels=2),
            pdk.Layer("TextLayer", k, get_position="[lon, lat]", get_text="label", get_size=15,
                      get_color=[255, 255, 255, 255], get_alignment_baseline="'center'")]

def build_deck(kitchen, results, kitchen_name="Your kitchen", others=None):
    """results: ranked partner dicts (need lat, lon, name, distance_km, eta_min, phone, optional path).
    others: optional list of {name, lat, lon, info} drawn as small grey dots."""
    layers = []
    if others:
        o = pd.DataFrame(others)
        layers.append(pdk.Layer("ScatterplotLayer", o, get_position="[lon, lat]", get_fill_color=GREY,
                                get_radius=150, radius_min_pixels=6, radius_max_pixels=11, pickable=True))
    p = pd.DataFrame([{
        "name": r["name"], "lat": r["lat"], "lon": r["lon"], "rank": str(i),
        "info": f"{r['distance_km']} km, ~{r['eta_min']} min | {r['phone'] or 'phone not listed'}",
        "klat": kitchen["lat"], "klon": kitchen["lon"],
    } for i, r in enumerate(results, 1)])
    if len(p):
        paths = [{"path": r["path"]} for r in results if r.get("path")]
        straight = p[[not r.get("path") for r in results]]
        if len(straight):
            layers.append(pdk.Layer("LineLayer", straight, get_source_position="[klon, klat]",
                                    get_target_position="[lon, lat]", get_color=[120, 120, 120, 140], get_width=2))
        if paths:
            layers.append(pdk.Layer("PathLayer", pd.DataFrame(paths), get_path="path",
                                    get_color=[30, 100, 220, 150], get_width=4, width_min_pixels=3))
        layers.append(pdk.Layer("ScatterplotLayer", p, get_position="[lon, lat]", get_fill_color=BLUE,
                                get_radius=200, radius_min_pixels=13, radius_max_pixels=24, pickable=True))
        layers.append(pdk.Layer("TextLayer", p, get_position="[lon, lat]", get_text="rank", get_size=16,
                                get_color=[255, 255, 255, 255], get_alignment_baseline="'center'"))
    layers += _kitchen_layers(kitchen, kitchen_name)
    pts = [[kitchen["lon"], kitchen["lat"]]] + [[r["lon"], r["lat"]] for r in results]
    return pdk.Deck(layers=layers, initial_view_state=_view(pts, kitchen), map_style="light",
                    tooltip={"html": "<b>{name}</b><br/>{info}"})

def build_directory_deck(kitchen, partners, kitchen_name="Your kitchen"):
    """partners: DataFrame with name, latitude, longitude, accepts_surplus, area, phone (blank coords skipped)."""
    df = partners.dropna(subset=["latitude", "longitude"])
    label = {"yes": "Surplus intake confirmed", "likely": "Reported partner", "unconfirmed": "Not confirmed"}
    color = {"yes": GREEN, "likely": ORANGE}
    d = pd.DataFrame([{
        "name": r["name"], "lat": float(r["latitude"]), "lon": float(r["longitude"]),
        "info": f"{r.get('area', '')} | {label.get(r['accepts_surplus'], 'Not confirmed')}",
        "color": color.get(r["accepts_surplus"], GREY),
    } for _, r in df.iterrows()])
    layers = []
    if len(d):
        layers.append(pdk.Layer("ScatterplotLayer", d, get_position="[lon, lat]", get_fill_color="color",
                                get_radius=200, radius_min_pixels=8, radius_max_pixels=14, pickable=True))
    layers += _kitchen_layers(kitchen, kitchen_name)
    pts = [[kitchen["lon"], kitchen["lat"]]] + ([[x, y] for x, y in zip(d["lon"], d["lat"])] if len(d) else [])
    return pdk.Deck(layers=layers, initial_view_state=_view(pts, kitchen), map_style="light",
                    tooltip={"html": "<b>{name}</b><br/>{info}"})
