"""Module B (part 2) — decide, for one address and one date, which rules apply.

result ∈ applies | unknown | superseded | not_yet_effective | pending   (rules that don't apply are omitted)
Every decision carries a plain-language explanation that names the building fact it rests on.
"""
from datetime import date

from .extract import _date_key, status_on


def _y(d):
    return int(str(d)[:4]) if d else None


def _check_coverage(rule, prop, as_of):
    """Return ('covered'|'not_covered'|'unknown', [reasons])."""
    c = rule.get("coverage_conditions") or {}
    yb, umin, umax = prop["year_built"], prop["units_min"], prop["units_max"]
    reasons, unknown = [], False

    cutoff = c.get("covered_if_built_on_or_before")
    if cutoff:
        cy = _y(cutoff)
        if yb is None:
            unknown = True
            reasons.append(f"covers buildings with a certificate of occupancy on or before {cutoff}; "
                           "year built is not in the public record")
        elif yb < cy:
            reasons.append(f"built {yb}, before the {cutoff} cutoff")
        elif yb == cy:
            unknown = True
            reasons.append(f"built {yb}, the cutoff year — depends on the exact certificate-of-occupancy date "
                           f"(cutoff {cutoff}), which the data does not have")
        else:
            return "not_covered", [f"built {yb}, after the {cutoff} cutoff"]

    after = c.get("covered_if_built_after")
    if after:
        ay = _y(after)
        if yb is None:
            unknown = True
            reasons.append(f"covers buildings built after {after}; year built unknown")
        elif yb > ay:
            reasons.append(f"built {yb}, after {after}")
        elif yb == ay:
            unknown = True
            reasons.append(f"built {yb}, the cutoff year")
        else:
            return "not_covered", [f"built {yb}, not after {after}"]

    n = c.get("exempt_if_newer_than_years")
    if n:
        cy = int(as_of[:4]) - int(n)
        if yb is None:
            unknown = True
            reasons.append(f"exempts buildings with a certificate of occupancy in the last {n} years; "
                           "year built unknown")
        elif yb < cy:
            reasons.append(f"built {yb}, more than {n} years ago")
        elif yb == cy:
            unknown = True
            reasons.append(f"built {yb}: exactly at the {n}-year line, depends on the certificate date")
        else:
            return "not_covered", [f"built {yb}, within the {n}-year new-construction exemption"]

    mn, mx = c.get("min_units"), c.get("max_units")
    if mn:
        if umin is not None and umin >= mn:
            reasons.append(f"{_units(prop)} (rule covers {mn}+ units)")
        elif umax is not None and umax < mn:
            return "not_covered", [f"{_units(prop)}, fewer than {mn}"]
        else:
            unknown = True
            reasons.append(f"rule covers {mn}+ units; unit count not in the record")
    if mx:
        if umax is not None and umax <= mx:
            reasons.append(f"{_units(prop)} (rule covers up to {mx})")
        elif umin is not None and umin > mx:
            return "not_covered", [f"{_units(prop)}, more than {mx}"]
        else:
            unknown = True
            reasons.append(f"rule covers buildings up to {mx} units; unit count not in the record")

    ex = c.get("exemption_max_units")
    if ex:
        if umin is not None and umin > ex:
            reasons.append(f"{_units(prop)}, so the small-building exemption (≤{ex} units) cannot apply")
        elif umax is not None and umax <= ex:
            unknown = True
            reasons.append(f"{_units(prop)}: an exemption for buildings of ≤{ex} units may apply "
                           "(depends on owner facts not in the data)")
        else:
            unknown = True
            reasons.append(f"an exemption for buildings of ≤{ex} units may apply; unit count unknown")
    elif c.get("owner_type_dependent"):
        unknown = True
        reasons.append("coverage depends on the owner's identity; owner names are not in the data")

    return ("unknown" if unknown else "covered"), reasons


def _units(prop):
    a, b = prop["units_min"], prop["units_max"]
    if a is None:
        return "unit count unknown"
    if a == b:
        return f"{a} units"
    return f"{a}+ units" if b is None else f"{a}–{b} units"


def _applies_to_place(rule, prop):
    # statewide rules reach every address in the state, even one whose city is outside the covered set
    if rule["level"] == "state":
        return rule["jurisdiction"] == prop["state"]
    return bool(prop.get("jurisdiction")) and rule["jurisdiction"] == prop["jurisdiction"]


def evaluate(prop, rules, as_of):
    """Return list of lookup entries for one address."""
    rows = {}
    for r in rules:
        if not _applies_to_place(r, prop):
            continue
        st = status_on(r, as_of)
        if st == "failed":
            continue
        where = (f"{prop['city']}, {prop['state']}" if r["level"] == "city" else f"statewide {prop['state']}")
        if st == "pending":
            rows[r["team_rule_id"]] = ("pending", f"Pending bill/proposal, not law as of {as_of}; "
                                                  f"would cover this address ({where}) if enacted.")
            continue
        cov, reasons = _check_coverage(r, prop, as_of)
        if cov == "not_covered":
            continue
        if st == "not_yet_effective":
            eff = _date_key(r.get("effective_date"))
            rows[r["team_rule_id"]] = ("not_yet_effective",
                                       f"Enacted; takes effect {eff}. " + ("; ".join(reasons) or f"Covers {where}") + ".")
            continue
        res = "applies" if cov == "covered" else "unknown"
        why = "; ".join(reasons) if reasons else f"in force and covers {where}"
        rows[r["team_rule_id"]] = (res, why[0].upper() + why[1:] + ".")

    # precedence: state rules that yield to a stricter local rule of the same category
    by_id = {r["team_rule_id"]: r for r in rules}
    for rid, (res, why) in list(rows.items()):
        r = by_id[rid]
        if r["level"] != "state" or not (r.get("coverage_conditions") or {}).get("yields_to_local"):
            continue
        if res not in ("applies", "unknown"):
            continue
        local = [(by_id[x], rows[x][0]) for x in rows if by_id[x]["level"] == "city"
                 and by_id[x]["category"] == r["category"] and rows[x][0] in ("applies", "unknown")]
        if any(lr == "applies" for _, lr in local):
            names = ", ".join(l["team_rule_id"] for l, lr in local if lr == "applies")
            rows[rid] = ("superseded", f"Local rule {names} covers this unit; this state rule yields to it.")
        elif local:
            names = ", ".join(l["team_rule_id"] for l, _ in local)
            rows[rid] = ("unknown", f"Applies only if the local rule ({names}) does not cover the unit, "
                                    "and that coverage is itself unknown.")

    # conflict flags: a state rule that may preempt local rules, where both reach this address
    out = []
    for rid, (res, why) in rows.items():
        r = by_id[rid]
        flag = False
        cov = r.get("coverage_conditions") or {}
        if r["level"] == "state" and cov.get("may_preempt_local"):
            flag = any(by_id[x]["level"] == "city" and by_id[x]["category"] == r["category"] for x in rows)
        if r["level"] == "city":
            flag = flag or any(by_id[x]["level"] == "state" and by_id[x]["category"] == r["category"]
                               and (by_id[x].get("coverage_conditions") or {}).get("may_preempt_local")
                               for x in rows)
        if r.get("conflict_flag") and r.get("conflict_note") and not cov.get("may_preempt_local"):
            flag = True
        if prop.get("jurisdiction_confidence", 1) < 0.85:
            why += f" Jurisdiction resolved by {prop['jurisdiction_method']} — verify."
        out.append({"team_rule_id": rid, "result": res, "explanation": why, "conflict_flag": flag})
    order = {"applies": 0, "superseded": 1, "unknown": 2, "not_yet_effective": 3, "pending": 4}
    out.sort(key=lambda e: (order[e["result"]], e["team_rule_id"]))
    return out


def lookups(props, rules, as_of):
    return {p["address_id"]: evaluate(p, rules, as_of) for p in props}


def excluded(prop, rules, as_of):
    """Rules of this address's state and city that were checked and do NOT reach it, with the reason.
    Shown in the app as "checked, does not apply here" so a missing rule is never a silent omission."""
    out = []
    for r in rules:
        if not _applies_to_place(r, prop):
            continue
        if status_on(r, as_of) == "failed":
            out.append([r["team_rule_id"], "Measure failed (struck, vetoed or sent to study); it is not law."])
            continue
        cov, reasons = _check_coverage(r, prop, as_of)
        if cov == "not_covered":
            why = "; ".join(reasons)
            out.append([r["team_rule_id"], why[0].upper() + why[1:] + "."])
    return out
