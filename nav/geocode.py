"""Resolve each sample address to its legal incorporated place with the U.S. Census Geocoder.

Run on a machine with internet access:  python run.py geocode
Results are cached in cache/geocode/census_places.json (commit it so the demo works offline).
NJ MOD-IV ZIP codes are owners' mailing ZIPs, so NJ addresses are sent without a ZIP.
"""
import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import config
from .properties import load_addresses

URL = "https://geocoding.geo.census.gov/geocoder/geographies/address"


def _query(row):
    st = row["state"].strip()
    street = re.sub(r"^(\d+)[A-Z]?\s*-\s*\d+[A-Z]?\s+", r"\1 ", row["street_address"].strip())  # "1031-1035 X ST" → "1031 X ST"
    params = {"street": street,
              "city": row["postal_city"], "state": st,
              "benchmark": "Public_AR_Current", "vintage": "Current_Current",
              "layers": "Incorporated Places,Counties,County Subdivisions", "format": "json"}
    z = (row.get("zip") or "").strip()
    if z and st != "NJ":
        params["zip"] = z
    url = URL + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                data = json.loads(r.read())
            matches = data["result"]["addressMatches"]
            if not matches:
                return row["address_id"], {"matched": False}
            m = matches[0]
            geos = m.get("geographies", {})
            place = (geos.get("Incorporated Places") or [{}])[0].get("NAME")
            county = (geos.get("Counties") or [{}])[0].get("NAME")
            cousub = (geos.get("County Subdivisions") or [{}])[0].get("NAME")
            # In MA/NJ, cities are county subdivisions; use them when no incorporated place is returned
            if not place and st in ("MA", "NJ") and cousub:
                place = cousub
            return row["address_id"], {"matched": True, "place": place, "county": county,
                                        "matched_address": m.get("matchedAddress"),
                                        "lon": m["coordinates"]["x"], "lat": m["coordinates"]["y"]}
        except Exception as e:  # noqa: BLE001
            if attempt == 3:
                return row["address_id"], {"matched": False, "error": str(e)[:200]}
            time.sleep(2 * (attempt + 1))


def run(workers=8):
    cache = json.loads(config.GEO_CACHE.read_text()) if config.GEO_CACHE.exists() else {}
    todo = [r for r in load_addresses() if r["address_id"] not in cache or cache[r["address_id"]].get("error")]
    print(f"[geocode] {len(todo)} addresses to geocode ({len(cache)} cached)")
    with ThreadPoolExecutor(workers) as ex:
        for i, (aid, res) in enumerate(ex.map(_query, todo), 1):
            cache[aid] = res
            if i % 50 == 0:
                print(f"  {i}/{len(todo)}", flush=True)
                config.GEO_CACHE.write_text(json.dumps(cache, indent=1))
    config.GEO_CACHE.parent.mkdir(parents=True, exist_ok=True)
    config.GEO_CACHE.write_text(json.dumps(cache, indent=1))
    ok = sum(1 for v in cache.values() if v.get("matched"))
    print(f"[geocode] matched {ok}/{len(cache)}")


def load_cache():
    return json.loads(config.GEO_CACHE.read_text()) if config.GEO_CACHE.exists() else {}
