"""Real road distance/time via OSRM (OpenStreetMap routing). Raises RoutingError on any failure,
so callers can fall back to the straight-line estimate."""
import json
import urllib.request
import config as C

class RoutingError(Exception):
    pass

def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ZeroWasteKitchen-student-prototype"})
    try:
        with urllib.request.urlopen(req, timeout=C.OSRM_TIMEOUT_S) as r:
            data = json.load(r)
    except Exception as e:
        raise RoutingError(f"routing server unreachable: {e}") from e
    if data.get("code") != "Ok":
        raise RoutingError(f"routing server said: {data.get('code')}")
    return data

def road_times(kitchen, points):
    """points: list of (name, lat, lon). One 'table' request for all partners.
    Returns {name: (road_km, drive_minutes_free_flow)}; unroutable partners are omitted."""
    if not points:
        return {}
    coords = [f"{kitchen['lon']:.6f},{kitchen['lat']:.6f}"] + [f"{lo:.6f},{la:.6f}" for _, la, lo in points]
    url = (f"{C.OSRM_BASE}/table/v1/driving/{';'.join(coords)}"
           "?sources=0&annotations=duration,distance")
    data = _get(url)
    try:
        durs, dists = data["durations"][0][1:], data["distances"][0][1:]
    except (KeyError, IndexError, TypeError) as e:
        raise RoutingError("unexpected routing response") from e
    return {name: (dm / 1000.0, ds / 60.0)
            for (name, _, _), ds, dm in zip(points, durs, dists) if ds is not None and dm is not None}

def route_path(kitchen, lat, lon):
    """Road geometry for drawing on the map: list of [lon, lat]."""
    url = (f"{C.OSRM_BASE}/route/v1/driving/{kitchen['lon']:.6f},{kitchen['lat']:.6f};{lon:.6f},{lat:.6f}"
           "?overview=full&geometries=geojson")
    data = _get(url)
    try:
        return data["routes"][0]["geometry"]["coordinates"]
    except (KeyError, IndexError, TypeError) as e:
        raise RoutingError("unexpected routing response") from e
