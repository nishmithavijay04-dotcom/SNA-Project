"""Recommend nearby redistribution partners for a surplus batch. Read-only: nothing is contacted.

Partner file columns - required: name, latitude, longitude, phone
optional: type, area, address, email, website, accepts_surplus (yes/likely/unconfirmed),
accepts_cooked (yes/no/unconfirmed), pickup (yes/no/unconfirmed), accepts_nonveg (yes/no/unknown),
capacity_kg, pickup_start, pickup_end, verified, last_checked, source_confidence, cooked_note, source_url.
Blank latitude/longitude is allowed: that partner is listed as 'no location on file' and not ranked."""
from datetime import datetime, timedelta, time
from math import radians, sin, cos, asin, sqrt
import pandas as pd
import config as C
from services.links import google_directions_url

REQUIRED = ["name", "latitude", "longitude", "phone"]
DEFAULTS = {"type": "Not specified", "area": "", "address": "", "email": "", "website": "",
            "accepts_surplus": "unconfirmed", "accepts_cooked": "unconfirmed", "pickup": "unconfirmed",
            "accepts_nonveg": "unknown", "capacity_kg": None, "pickup_start": None, "pickup_end": None,
            "verified": "no", "last_checked": "", "source_confidence": "", "cooked_note": "",
            "source_url": "", "coord_quality": ""}
SURPLUS_LABEL = {"yes": "Surplus intake confirmed by public source",
                 "likely": "Reported food-redistribution partner (intake rules unclear)",
                 "unconfirmed": "Surplus intake NOT confirmed - ask before going"}
SORTERS = {"best": lambda r: -r["score"], "nearest": lambda r: r["distance_km"], "fastest": lambda r: r["eta_min"]}
SURPLUS_SCORE = {"yes": 1.0, "likely": 0.5, "unconfirmed": 0.0}

def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * asin(sqrt(a))

def _blank(v):
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ("", "nan")

def _yes(v):
    return str(v).strip().lower() in ("yes", "y", "true", "1")

def _txt(v):
    return "" if _blank(v) else str(v).strip()

def load_partners(path_or_df) -> pd.DataFrame:
    df = (path_or_df.copy() if isinstance(path_or_df, pd.DataFrame)
          else pd.read_csv(path_or_df, encoding="utf-8-sig"))
    df.columns = [c.strip().lower() for c in df.columns]
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Partner file is missing required columns: {missing}")
    for col, default in DEFAULTS.items():
        if col not in df.columns:
            df[col] = default
    lat = pd.to_numeric(df["latitude"], errors="coerce")
    lon = pd.to_numeric(df["longitude"], errors="coerce")
    bad = df[(df["latitude"].notna() & lat.isna()) | (df["longitude"].notna() & lon.isna())
             | (lat.abs() > 90) | (lon.abs() > 180)]
    if len(bad):
        raise ValueError(f"Invalid coordinates for: {bad['name'].tolist()}")
    df["latitude"], df["longitude"] = lat, lon
    for col in ("accepts_surplus", "accepts_cooked", "pickup"):
        df[col] = df[col].fillna("unconfirmed").astype(str).str.strip().str.lower()
    return df

def _parse_t(v):
    if _blank(v):
        return None
    h, m = str(v).strip().split(":")[:2]
    return time(int(h), int(m))

def eta_minutes(dist_km):
    return dist_km * C.ROAD_FACTOR / C.SPEED_KMPH * 60 + C.HANDLING_MIN

def rank_partners(partners, kitchen, surplus, now=None, top_n=None, only_confirmed=False, road=None, sort_by="best"):
    """kitchen: {lat, lon}; surplus: {quantity_kg, veg(bool), safe_until(datetime), cooked(bool, default True)}.
    road: optional {name: (road_km, free_flow_minutes)} from services.routing; if a partner is in it, real road
    distance/time replace the straight-line estimate. Returns (results, rejected); rejected = [(name, reason)]."""
    if sort_by not in SORTERS:
        raise ValueError(f"sort_by must be one of {list(SORTERS)}")
    now = now or datetime.now()
    road = road or {}
    top_n = top_n or C.TOP_N
    cooked = surplus.get("cooked", True)
    results, rejected = [], []
    window_min = (surplus["safe_until"] - now).total_seconds() / 60
    for _, p in partners.iterrows():
        name = p["name"]
        if pd.isna(p["latitude"]) or pd.isna(p["longitude"]):
            rejected.append((name, "no location on file - call to ask where to deliver")); continue
        if only_confirmed and p["accepts_surplus"] != "yes":
            rejected.append((name, "surplus intake not confirmed (filter on)")); continue
        d = haversine_km(kitchen["lat"], kitchen["lon"], p["latitude"], p["longitude"])
        if d > C.MAX_RADIUS_KM:
            rejected.append((name, f"{d:.1f} km is beyond the {C.MAX_RADIUS_KM} km radius")); continue
        if cooked and p["accepts_cooked"] == "no":
            rejected.append((name, "does not accept cooked food")); continue
        if not surplus["veg"] and not _yes(p["accepts_nonveg"]):
            rejected.append((name, "non-veg not accepted / not confirmed")); continue
        if name in road:
            d_show, eta, src = road[name][0], road[name][1] * C.TRAFFIC_FACTOR + C.HANDLING_MIN, "road (OSRM)"
        else:
            d_show, eta, src = d, eta_minutes(d), "estimate"
        arrive = now + timedelta(minutes=eta)
        spare = window_min - eta - C.BUFFER_MIN
        if spare < 0:
            rejected.append((name, f"cannot be reached in time (needs ~{eta:.0f} min, food has {max(window_min,0):.0f} min left)")); continue
        s, e = _parse_t(p["pickup_start"]), _parse_t(p["pickup_end"])
        if s and e and not (s <= arrive.time() <= e):
            rejected.append((name, f"closed at expected arrival ({arrive:%H:%M}); open {s:%H:%M}-{e:%H:%M}")); continue
        timing = f"open {s:%H:%M}-{e:%H:%M}" if s and e else "timing unknown, confirm by phone"
        notes = []
        if cooked and p["accepts_cooked"] == "unconfirmed":
            notes.append("cooked-food acceptance not confirmed - ask on the call")
        if p["pickup"] == "no":
            notes.append("drop-off model: your kitchen delivers, they do not collect")
        elif p["pickup"] == "yes":
            notes.append("collects after confirmation and safety check")
        if not _blank(p["capacity_kg"]) and surplus["quantity_kg"] > float(p["capacity_kg"]):
            notes.append(f"may not take the full {surplus['quantity_kg']:g} kg (capacity ~{float(p['capacity_kg']):g} kg)")
        slack_frac = min(spare / max(window_min, 1), 1.0)
        dist_score = max(0.0, 1 - d / C.MAX_RADIUS_KM)
        score = (C.W_DISTANCE * dist_score + C.W_SLACK * slack_frac
                 + C.W_SURPLUS * SURPLUS_SCORE.get(p["accepts_surplus"], 0))
        results.append({
            "name": name, "type": p["type"], "area": _txt(p["area"]), "address": _txt(p["address"]),
            "phone": _txt(p["phone"]), "email": _txt(p["email"]), "website": _txt(p["website"]),
            "lat": float(p["latitude"]), "lon": float(p["longitude"]),
            "maps_url": google_directions_url(kitchen["lat"], kitchen["lon"], p["latitude"], p["longitude"]),
            "distance_km": round(d_show, 1), "route_source": src, "eta_min": round(eta), "spare_min": round(spare),
            "surplus_status": SURPLUS_LABEL.get(p["accepts_surplus"], SURPLUS_LABEL["unconfirmed"]),
            "surplus_level": p["accepts_surplus"],
            "source_confidence": _txt(p["source_confidence"]), "coord_quality": _txt(p["coord_quality"]),
            "timing": timing, "notes": notes, "score": round(score, 3),
            "reason": f"{d_show:.1f} km {'by road' if src != 'estimate' else 'away (estimated)'}, ~{eta:.0f} min trip, ~{spare:.0f} min spare before the safety buffer; {timing}",
        })
    results.sort(key=SORTERS[sort_by])
    return results[:top_n], rejected
