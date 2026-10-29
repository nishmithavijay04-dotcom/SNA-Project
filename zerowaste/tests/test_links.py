import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from urllib.parse import urlparse, parse_qs
from services.links import google_directions_url, google_place_url, osm_url

def test_google_directions_url_format():
    u = urlparse(google_directions_url(12.9352, 77.6245, 12.9166, 77.6101))
    q = parse_qs(u.query)
    assert u.scheme == "https" and u.netloc == "www.google.com" and u.path == "/maps/dir/"
    assert q["api"] == ["1"] and q["travelmode"] == ["driving"]
    assert q["origin"] == ["12.935200,77.624500"] and q["destination"] == ["12.916600,77.610100"]

def test_place_and_osm_urls():
    u = urlparse(google_place_url(12.9166, 77.6101))
    assert u.path == "/maps/search/" and parse_qs(u.query)["query"] == ["12.916600,77.610100"]
    assert osm_url(12.9166, 77.6101).startswith("https://www.openstreetmap.org/?mlat=12.916600&mlon=77.610100")

def test_no_spaces_in_urls():
    for u in (google_directions_url(1, 2, 3, 4), google_place_url(1, 2), osm_url(1, 2)):
        assert " " not in u
