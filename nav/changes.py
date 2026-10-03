"""Module C — change tracking.

Each test names rules by the organizers' ids (e.g. CA-ALG-01). We map them to our extracted rules by
jurisdiction + category (+ pending/failed for 'P' ids), then compare engine results across dates.
The same machinery handles any new document (e.g. the hour-16 ordinance): `changes_for_doc`.
"""
import re

from .engine import lookups

ABBR2JUR = {"CA": "CA", "NJ": "NJ", "MA": "MA", "LA": "Los Angeles, CA", "SF": "San Francisco, CA",
            "SD": "San Diego, CA", "BRK": "Berkeley, CA", "SNA": "Santa Ana, CA", "JC": "Jersey City, NJ",
            "HOB": "Hoboken, NJ", "NWK": "Newark, NJ", "BOS": "Boston, MA", "CAM": "Cambridge, MA"}
CAT = {"RENT": "rent_increase_limits", "EVICT": "just_cause_eviction", "DEP": "security_deposits",
       "FEE": "application_screening_fees", "SCREEN": "screening_restrictions", "ALG": "algorithmic_rent_setting"}


def match_rules(test_rule_id, rules):
    m = re.match(r"([A-Z]+)-([A-Z]+)-(P?)\d+", test_rule_id)
    if not m:
        return []
    jur, cat, p = ABBR2JUR.get(m.group(1)), CAT.get(m.group(2)), m.group(3)
    cands = [r for r in rules if r["jurisdiction"] == jur and r["category"] == cat]
    if p:
        return [r for r in cands if r.get("status_raw") in ("pending", "failed")]
    return [r for r in cands if r.get("status_raw") not in ("pending", "failed")]


def _results(lk, ids):
    return {aid: {e["team_rule_id"]: e for e in entries if e["team_rule_id"] in ids} for aid, entries in lk.items()}


def run_test(test, props, rules):
    matched = []
    for tid in test.get("rule_ids", []):
        matched += [r["team_rule_id"] for r in match_rules(tid, rules)]
    matched = sorted(set(matched))
    conflict_rules = set()
    for tid in test.get("conflict_with", []):
        conflict_rules |= {r["team_rule_id"] for r in match_rules(tid, rules)}
    affected, flagged, detail = [], [], {}
    t = test["type"]
    if t == "as_of":
        b = _results(lookups(props, rules, test["as_of_before"]), matched)
        a = _results(lookups(props, rules, test["as_of_after"]), matched)
        for p in props:
            aid = p["address_id"]
            rb = {k: v["result"] for k, v in b[aid].items()}
            ra = {k: v["result"] for k, v in a[aid].items()}
            if rb != ra:
                affected.append(aid)
                detail[aid] = {"before": rb, "after": ra}
            if any(v["conflict_flag"] for v in list(a[aid].values()) + list(b[aid].values())):
                flagged.append(aid)
        notes = (f"Rules {matched}: results change between {test['as_of_before']} and "
                 f"{test['as_of_after']} for {len(affected)} addresses.")
    else:
        lk = _results(lookups(props, rules, test.get("as_of", "2026-10-01")), matched)
        keep = {"boundary": ("applies", "unknown", "superseded", "not_yet_effective"),
                "pending": ("pending",),
                "negative": ("applies", "unknown", "superseded", "not_yet_effective", "pending")}[t]
        for p in props:
            aid = p["address_id"]
            hits = {k: v["result"] for k, v in lk[aid].items() if v["result"] in keep}
            if hits:
                affected.append(aid)
                detail[aid] = hits
            if any(v["conflict_flag"] for v in lk[aid].values()):
                flagged.append(aid)
        if t == "boundary":
            per = {}
            for aid, h in detail.items():
                for k in h:
                    per.setdefault(k, set()).add(next(p["city"] for p in props if p["address_id"] == aid))
            notes = "; ".join(f"{k} reaches only {sorted(v)}" for k, v in sorted(per.items()))
        elif t == "pending":
            notes = (f"{matched} are pending bills, never reported as in force; {len(affected)} addresses "
                     "would be affected if enacted.")
        else:
            failed = [r["team_rule_id"] for r in rules if r["team_rule_id"] in matched]
            notes = (f"Measure recorded as {[r['status_raw'] for r in rules if r['team_rule_id'] in failed] or 'not found'}; "
                     f"no rent cap reported for any address. Affected set size: {len(affected)}.")
    if conflict_rules and t == "as_of":
        flagged = [aid for aid in flagged]
    return {"affected_address_ids": affected, "conflict_flag_address_ids": sorted(set(flagged)),
            "notes": notes}, {"matched_rule_ids": matched, "per_address": detail}


def changes_for_doc(doc_id, props, rules, as_of, horizon="2030-01-01"):
    """Which addresses does a newly added document change, now and once effective?"""
    ids = {r["team_rule_id"] for r in rules if r.get("source_doc_id") == doc_id or doc_id in r.get("supporting_docs", [])}
    without = [r for r in rules if r["team_rule_id"] not in ids]
    now_with, now_without = lookups(props, rules, as_of), lookups(props, without, as_of)
    later = lookups(props, rules, horizon)
    affected, flagged, detail = [], [], {}
    for p in props:
        aid = p["address_id"]
        new_now = {e["team_rule_id"]: e["result"] for e in now_with[aid] if e["team_rule_id"] in ids}
        new_later = {e["team_rule_id"]: e["result"] for e in later[aid] if e["team_rule_id"] in ids}
        changed_other = ({e["team_rule_id"]: e["result"] for e in now_with[aid] if e["team_rule_id"] not in ids} !=
                         {e["team_rule_id"]: e["result"] for e in now_without[aid]})
        if new_now or new_later or changed_other:
            affected.append(aid)
            detail[aid] = {"as_of": new_now, "once_effective": new_later}
        if any(e["conflict_flag"] for e in now_with[aid] if e["team_rule_id"] in ids):
            flagged.append(aid)
    eff = sorted({r.get("effective_date") or "unknown" for r in rules if r["team_rule_id"] in ids})
    notes = (f"New document {doc_id} → rules {sorted(ids)}; effective {eff}; status as of {as_of}: "
             f"{sorted({r['status'] for r in rules if r['team_rule_id'] in ids})}; {len(affected)} addresses affected.")
    return {"affected_address_ids": affected, "conflict_flag_address_ids": flagged, "notes": notes}, \
        {"matched_rule_ids": sorted(ids), "per_address": detail}
