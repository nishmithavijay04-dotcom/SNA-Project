"""Map links (plain URLs - nothing is sent anywhere). Google format: developers.google.com/maps/documentation/urls"""
from urllib.parse import urlencode

def _q(**kw):
    return urlencode(kw, safe=",")

def google_directions_url(o_lat, o_lon, d_lat, d_lon):
    return "https://www.google.com/maps/dir/?" + _q(api=1, origin=f"{o_lat:.6f},{o_lon:.6f}",
                                                    destination=f"{d_lat:.6f},{d_lon:.6f}", travelmode="driving")

def google_place_url(lat, lon):
    return "https://www.google.com/maps/search/?" + _q(api=1, query=f"{lat:.6f},{lon:.6f}")

def osm_url(lat, lon):
    return f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=16/{lat:.6f}/{lon:.6f}"
