import os, sys, io, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from datetime import datetime, timedelta
import pandas as pd, pytest
import config as C
from services import routing
from services.ngo_matcher import load_partners, rank_partners
from services.mapview import build_deck

K = {"lat": 12.9352, "lon": 77.6245}
NOW = datetime(2026, 10, 5, 13, 0)

class FakeResp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False

def fake_urlopen(payload):
    return lambda req, timeout=None: FakeResp(json.dumps(payload).encode())

def test_road_times_parses_table_response(monkeypatch):
    payload = {"code": "Ok", "durations": [[0, 600, 1200, None]], "distances": [[0, 4000, 9000, None]]}
    monkeypatch.setattr(routing.urllib.request, "urlopen", fake_urlopen(payload))
    out = routing.road_times(K, [("A", 12.94, 77.62), ("B", 12.98, 77.64), ("C", 13.0, 77.5)])
    assert out == {"A": (4.0, 10.0), "B": (9.0, 20.0)}          # unroutable C omitted

def test_route_path_parses_geometry(monkeypatch):
    payload = {"code": "Ok", "routes": [{"geometry": {"coordinates": [[77.62, 12.93], [77.63, 12.94]]}}]}
    monkeypatch.setattr(routing.urllib.request, "urlopen", fake_urlopen(payload))
    assert routing.route_path(K, 12.94, 77.63) == [[77.62, 12.93], [77.63, 12.94]]

def test_network_failure_raises_routing_error(monkeypatch):
    def boom(*a, **k): raise OSError("no internet")
    monkeypatch.setattr(routing.urllib.request, "urlopen", boom)
    with pytest.raises(routing.RoutingError): routing.road_times(K, [("A", 12.94, 77.62)])

def test_server_error_code_raises(monkeypatch):
    monkeypatch.setattr(routing.urllib.request, "urlopen", fake_urlopen({"code": "InvalidQuery"}))
    with pytest.raises(routing.RoutingError): routing.route_path(K, 12.94, 77.63)

def test_rank_uses_road_time_and_traffic_factor():
    df = load_partners(pd.DataFrame([{"name": "A", "latitude": 12.94, "longitude": 77.62, "phone": "1"}]))
    s = {"quantity_kg": 5, "veg": True, "safe_until": NOW + timedelta(hours=4)}
    res, _ = rank_partners(df, K, s, now=NOW, road={"A": (6.0, 20.0)})
    r = res[0]
    assert r["distance_km"] == 6.0 and r["route_source"] == "road (OSRM)"
    assert r["eta_min"] == round(20 * C.TRAFFIC_FACTOR + C.HANDLING_MIN)
    res2, _ = rank_partners(df, K, s, now=NOW)                    # no road data -> estimate
    assert res2[0]["route_source"] == "estimate"

def test_long_road_trip_makes_partner_infeasible():
    df = load_partners(pd.DataFrame([{"name": "A", "latitude": 12.94, "longitude": 77.62, "phone": "1"}]))
    s = {"quantity_kg": 5, "veg": True, "safe_until": NOW + timedelta(hours=1)}
    res, rej = rank_partners(df, K, s, now=NOW, road={"A": (30.0, 90.0)})
    assert res == [] and "in time" in rej[0][1]

def test_map_draws_road_path_when_available():
    r = [{"name": "A", "lat": 12.94, "lon": 77.62, "distance_km": 1, "eta_min": 25, "phone": "1",
          "path": [[77.6245, 12.9352], [77.62, 12.94]]}]
    js = build_deck(K, r).to_json()
    assert '"PathLayer"' in js and '"LineLayer"' not in js
