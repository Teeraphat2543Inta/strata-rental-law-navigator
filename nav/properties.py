"""Module B (part 1) — turn assessor rows into building facts and a legal jurisdiction.

Building facts are taken from the row when present and otherwise *inferred only from what the public
record itself says*, with the inference recorded. Nothing is guessed:
  * unit counts embedded in NJ MOD-IV building descriptions ("4S-B-A-16U-H" → 16 units)
  * unit ranges implied by the assessor's own use class ("Apartment 5 to 14 Units", NJ class 4C = 5+,
    Cambridge 111 = 4–8 units, Boston "APT 7-30 UNITS")
Year built stays unknown when missing.
"""
import csv
import re

from . import config

# Mailing (postal) names that are neighborhoods inside a city — used only when the Census geocoder
# cannot confirm the place, and always reported with method="postal_alias".
POSTAL_ALIASES = {
    ("MA", "dorchester"): "Boston", ("MA", "roxbury"): "Boston", ("MA", "east boston"): "Boston",
    ("MA", "brighton"): "Boston", ("MA", "allston"): "Boston", ("MA", "south boston"): "Boston",
    ("MA", "jamaica plain"): "Boston", ("MA", "hyde park"): "Boston", ("MA", "mattapan"): "Boston",
    ("MA", "roslindale"): "Boston", ("MA", "west roxbury"): "Boston", ("MA", "charlestown"): "Boston",
    ("CA", "san ysidro"): "San Diego", ("CA", "la jolla"): "San Diego",
    ("CA", "van nuys"): "Los Angeles", ("CA", "north hollywood"): "Los Angeles",
    ("CA", "sylmar"): "Los Angeles", ("CA", "pacoima"): "Los Angeles", ("CA", "tujunga"): "Los Angeles",
    ("CA", "sun valley"): "Los Angeles", ("CA", "sherman oaks"): "Los Angeles",
    ("CA", "studio city"): "Los Angeles", ("CA", "panorama city"): "Los Angeles",
}
CITIES = {"Los Angeles", "San Francisco", "San Diego", "Berkeley", "Santa Ana", "Jersey City",
          "Hoboken", "Newark", "Boston", "Cambridge"}

# Assessor datasets that are municipal rolls: every row is inside that city by construction.
MUNICIPAL_ROLLS = {"DataSF": "San Francisco", "Boston Property Assessment": "Boston",
                   "Cambridge Property Database": "Cambridge"}


def _int(x):
    try:
        return int(float(str(x).strip()))
    except (TypeError, ValueError):
        return None


def units_from_record(row):
    """Return (units_min, units_max, method)."""
    u = _int(row.get("units"))
    if u:
        return u, u, "assessor units field"
    desc = (row.get("use_description") or "").upper()
    ds = row.get("source_dataset", "")
    if ds.startswith("NJOGIS"):
        nums = [int(n) for n in re.findall(r"(\d+)\s*U\b", desc.replace("1OU", "10U"))]
        nums += [int(n) for n in re.findall(r"-(\d+)U", desc) if int(n) not in nums]
        if "/" in desc and len(nums) > 1:
            parts = desc.split("/")
            total = sum(nums) if len(set(parts)) == len(parts) and not desc.endswith(parts[0] + "-G") else max(nums)
            return total, total, f"NJ MOD-IV building description '{row['use_description']}'"
        if nums:
            return max(nums), max(nums), f"NJ MOD-IV building description '{row['use_description']}'"
        if row.get("use_code", "").upper() == "4C":
            return 5, None, "NJ property class 4C (apartment building, 5+ units)"
    m = re.search(r"(\d+)\s*TO\s*(\d+)\s*UNITS", desc) or re.search(r"(\d+)-(\d+)[ -]UNIT", desc)
    if m:
        return int(m.group(1)), int(m.group(2)), f"assessor use class '{row['use_description']}'"
    m = re.search(r">\s*(\d+)[ -]UNIT", desc)
    if m:
        return int(m.group(1)) + 1, None, f"assessor use class '{row['use_description']}'"
    m = re.search(r"(\d+)\s*UNITS OR MORE", desc) or re.search(r"\((\d+)\+ UNITS\)", desc)
    if m:
        return int(m.group(1)), None, f"assessor use class '{row['use_description']}'"
    if "FIVE OR MORE" in desc:
        return 5, None, f"assessor use class '{row['use_description']}'"
    m = re.search(r"(\d+) UNITS OR LESS", desc)
    if m:
        return 1, int(m.group(1)), f"assessor use class '{row['use_description']}'"
    if ds.startswith("Boston") and (row.get("use_code") or "").startswith("A/"):
        return 7, None, "Boston land-use class A (apartment buildings of 7+ units)"
    return None, None, "not in public record"


def load_addresses():
    with open(config.ADDRESSES, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def resolve_city(row, census=None):
    """Return (city, method, confidence, note)."""
    st = row["state"].strip()
    postal = row["postal_city"].strip()
    g = (census or {}).get(row["address_id"])
    roll = next((c for prefix, c in MUNICIPAL_ROLLS.items() if row.get("source_dataset", "").startswith(prefix)), None)
    if roll and g and g.get("place") and not g["place"].lower().startswith(roll.lower()):
        # e.g. "322 Western Ave" exists in both Cambridge and Allston (Boston): a city's own roll only lists
        # parcels inside that city, so it outranks a geocoder match on a same-named street elsewhere.
        return roll, "municipal_assessor_roll", 0.95, (f"Row comes from the {roll} assessor roll; Census matched "
                                                       f"a same-named street in {g['place']}, so the roll wins")
    if g and g.get("place"):
        place = re.sub(r"\s+(city|town|township)$", "", g["place"], flags=re.I).strip()
        if place in CITIES:
            return place, "census_geocoder", 0.98, f"Census incorporated place: {g['place']}"
        return None, "census_geocoder", 0.95, (f"Census places this address in {g['place']}, "
                                               f"outside the 9 covered cities")
    if g and g.get("matched") and not g.get("place"):
        return None, "census_geocoder", 0.9, "Census match falls in no incorporated place (unincorporated)"
    for prefix, city in MUNICIPAL_ROLLS.items():
        if row.get("source_dataset", "").startswith(prefix):
            return city, "municipal_assessor_roll", 0.95, f"Row comes from the {city} assessor roll"
    if postal in CITIES:
        conf = 0.9 if st == "NJ" else 0.8   # NJ MOD-IV municipality field is the taxing municipality
        return postal, "postal_city", conf, "Postal city used; not confirmed by geocoder"
    alias = POSTAL_ALIASES.get((st, postal.lower()))
    if alias:
        return alias, "postal_alias", 0.85, f"'{postal}' is a neighborhood of {alias}"
    return None, "unresolved", 0.0, "Jurisdiction could not be resolved"


def build_property(row, census=None):
    umin, umax, umethod = units_from_record(row)
    city, method, conf, note = resolve_city(row, census)
    st = row["state"].strip()
    zip_ = (row.get("zip") or "").strip()
    flags = []
    if st == "NJ" and zip_ and not zip_.startswith(("07", "08")):
        flags.append(f"ZIP {zip_} is outside New Jersey (MOD-IV ZIP is the owner's mailing ZIP); "
                     "jurisdiction taken from the taxing municipality instead")
    return {
        "address_id": row["address_id"],
        "street_address": row["street_address"],
        "postal_city": row["postal_city"],
        "state": st,
        "zip": zip_,
        "city": city,
        "jurisdiction": f"{city}, {st}" if city else None,
        "jurisdiction_method": method,
        "jurisdiction_confidence": conf,
        "jurisdiction_note": note,
        "year_built": _int(row.get("year_built")),
        "units_min": umin,
        "units_max": umax,
        "units_method": umethod,
        "use_description": row.get("use_description"),
        "source_dataset": row.get("source_dataset"),
        "data_flags": flags,
        "lat": round(g["lat"], 6) if (g := (census or {}).get(row["address_id"])) and g.get("lat") else None,
        "lon": round(g["lon"], 6) if g and g.get("lon") else None,
    }
