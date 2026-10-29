import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from services.mapview import build_deck
import re

def flat(s):
    return re.sub(r"\s+", "", s)

R = [{"name": "A", "lat": 12.94, "lon": 77.62, "distance_km": 1.2, "eta_min": 25, "phone": "123"},
     {"name": "B", "lat": 12.98, "lon": 77.64, "distance_km": 5.0, "eta_min": 40, "phone": ""}]

def test_deck_layers_and_numbering():
    d = build_deck({"lat": 12.9352, "lon": 77.6245}, R)
    js = d.to_json()
    assert js.count('"ScatterplotLayer"') == 2 and js.count('"TextLayer"') == 2 and '"LineLayer"' in js
    assert "[220,40,40" in flat(js) and "[30,100,220" in flat(js)        # kitchen red, partners blue
    assert '"label":"K"' in flat(js)
    assert '"rank":"1"' in flat(js) and '"rank":"2"' in flat(js) and "phone not listed" in js

def test_deck_with_no_results_still_shows_kitchen():
    d = build_deck({"lat": 12.9352, "lon": 77.6245}, [])
    assert "Your kitchen" in d.to_json() and '"LineLayer"' not in d.to_json()


def test_other_partners_drawn_grey_and_directory_colours():
    d = build_deck({"lat": 12.9352, "lon": 77.6245}, R, others=[{"name": "Z", "lat": 13.0, "lon": 77.5, "info": "x"}])
    js = d.to_json()
    assert js.count('"ScatterplotLayer"') == 3 and "[150,150,150" in flat(js)
    import pandas as pd
    from services.mapview import build_directory_deck
    df = pd.DataFrame([{"name": "A", "latitude": 12.9, "longitude": 77.6, "accepts_surplus": "yes", "area": "x"},
                       {"name": "B", "latitude": 12.95, "longitude": 77.65, "accepts_surplus": "likely", "area": "y"},
                       {"name": "C", "latitude": 12.96, "longitude": 77.66, "accepts_surplus": "unconfirmed", "area": "z"},
                       {"name": "D", "latitude": None, "longitude": None, "accepts_surplus": "yes", "area": "w"}])
    js2 = build_directory_deck({"lat": 12.9352, "lon": 77.6245}, df).to_json()
    f2 = flat(js2)
    assert "[40,160,80" in f2 and "[240,150,30" in f2 and "[150,150,150" in f2 and "[220,40,40" in f2
    assert '"name":"D"' not in f2                              # no-location partner not drawn
