"""Self-check — run before every submission and show the output in the technical video.

Checks: schema conformance, every quoted_span found verbatim in its source, lookups cover all addresses,
the T1–T5 expected behaviours from dev/change_tests.json, and a jurisdiction × category coverage grid.
If the organizers' score.py is available, run it too:  python score.py --dev ...
"""
import json
from collections import Counter

from . import config
from .corpus import load_docs
from .extract import CATEGORIES, JURISDICTIONS
from .quotes import _norm_with_map


def _schema_errors(rule, schema):
    errs = []
    for k in schema["required"]:
        if k not in rule or rule[k] in (None, ""):
            errs.append(f"missing {k}")
    for k, spec in schema["properties"].items():
        if k in rule and "enum" in spec and rule[k] not in spec["enum"]:
            errs.append(f"{k}={rule[k]!r} not in enum")
    if len(rule.get("quoted_span", "")) < 20:
        errs.append("quoted_span < 20 chars")
    try:
        import jsonschema  # optional
        jsonschema.validate(rule, schema)
    except ImportError:
        pass
    except Exception as e:  # noqa: BLE001
        errs.append(str(e).split("\n")[0][:120])
    return errs


def run():
    out = config.OUT
    rules = json.loads((out / "rules.json").read_text())["rules"]
    lk = json.loads((out / "lookups.json").read_text())
    ch = json.loads((out / "changes.json").read_text())
    props = json.loads((out / "properties.json").read_text())
    schema = json.loads(config.SCHEMA.read_text())
    docs = {d.doc_id: d for d in load_docs()}
    lines, ok_all = [], True

    def say(ok, msg):
        nonlocal ok_all
        ok_all &= ok
        lines.append(f"{'PASS' if ok else 'FAIL'}  {msg}")

    bad = {r["team_rule_id"]: _schema_errors(r, schema) for r in rules}
    bad = {k: v for k, v in bad.items() if v}
    say(not bad, f"schema: {len(rules) - len(bad)}/{len(rules)} rule records valid" +
        (f" — e.g. {next(iter(bad.items()))}" if bad else ""))

    exact = norm = 0
    for r in rules:
        src = docs.get(r.get("source_doc_id"))
        if not src:
            continue
        if r["quoted_span"] in src.text:
            exact += 1
        elif _norm_with_map(r["quoted_span"])[0] in _norm_with_map(src.text)[0]:
            norm += 1
    say(exact + norm == len(rules), f"quotes: {exact} exact + {norm} whitespace-normalized matches "
                                    f"of {len(rules)} rules found in the cited source text")

    applies = [e for v in lk["lookups"].values() for e in v if e["result"] == "applies"]
    rid = {r["team_rule_id"]: r for r in rules}
    cited = sum(1 for e in applies if rid[e["team_rule_id"]].get("quote_verified"))
    say(cited == len(applies), f"citations: {cited}/{len(applies)} 'applies' answers backed by a verified quote")

    say(len(lk["lookups"]) == len(props), f"lookups cover {len(lk['lookups'])}/{len(props)} addresses")
    unresolved = [p["address_id"] for p in props if not p["jurisdiction"]]
    say(not unresolved, f"jurisdiction resolved for {len(props) - len(unresolved)}/{len(props)} addresses "
                        f"({Counter(p['jurisdiction_method'] for p in props)})")
    lines.append("      results: " + str(Counter(e["result"] for v in lk["lookups"].values() for e in v)))

    by_state = {s: {p["address_id"] for p in props if p["state"] == s} for s in ("CA", "NJ", "MA")}
    by_city = {}
    for p in props:
        by_city.setdefault(p["city"], set()).add(p["address_id"])
    t = ch.get("T1", {})
    say(set(t.get("affected_address_ids", [])) == by_state["CA"],
        f"T1 CA algorithmic law: {len(t.get('affected_address_ids', []))} affected (expect all {len(by_state['CA'])} CA)")
    t = ch.get("T2", {})
    aff = set(t.get("affected_address_ids", []))
    say(aff == by_city.get("Hoboken", set()) | by_city.get("Jersey City", set()) and not aff & by_city.get("Newark", set()),
        f"T2 boundary: {len(aff)} affected, Newark leakage={len(aff & by_city.get('Newark', set()))} — {t.get('notes', '')[:120]}")
    t = ch.get("T3", {})
    say(set(t.get("affected_address_ids", [])) == by_state["NJ"] and
        set(t.get("conflict_flag_address_ids", [])) == by_city.get("Hoboken", set()) | by_city.get("Jersey City", set()),
        f"T3 FAIR Act: {len(t.get('affected_address_ids', []))} affected (expect {len(by_state['NJ'])}), "
        f"{len(t.get('conflict_flag_address_ids', []))} conflict-flagged (expect JC+Hoboken = "
        f"{len(by_city.get('Hoboken', set()) | by_city.get('Jersey City', set()))})")
    t = ch.get("T4", {})
    say(set(t.get("affected_address_ids", [])) == by_state["MA"],
        f"T4 MA pending bills: {len(t.get('affected_address_ids', []))} affected (expect {len(by_state['MA'])})")
    pend_in_force = [r["team_rule_id"] for r in rules if r["jurisdiction"] == "MA" and
                     r.get("status_raw") == "pending" and r["status"] != "pending"]
    say(not pend_in_force, f"T4 pending bills never reported in force ({pend_in_force or 'ok'})")
    t = ch.get("T5", {})
    ma_caps = [aid for aid in by_state["MA"] for e in lk["lookups"][aid]
               if rid[e["team_rule_id"]]["category"] == "rent_increase_limits" and e["result"] in ("applies", "unknown")]
    say(not t.get("affected_address_ids") and not ma_caps,
        f"T5 MA ballot question: affected={len(t.get('affected_address_ids', []))}, MA rent caps reported={len(ma_caps)} (expect 0, 0)")

    lines.append("\nCoverage grid (rules extracted per jurisdiction × category; '·' = none, 'n' = no-rule finding):")
    findings = json.loads((out / "no_rule_findings.json").read_text())
    nf = {(f["jurisdiction"], f["category"]) for f in findings}
    hdr = "  " + "".join(f"{c[:6]:>8}" for c in CATEGORIES)
    lines.append(f"{'':18}{hdr}")
    for j in JURISDICTIONS:
        row = ""
        for c in CATEGORIES:
            n = sum(1 for r in rules if r["jurisdiction"] == j and r["category"] == c)
            row += f"{(str(n) if n else ('n' if (j, c) in nf else '·')):>8}"
        lines.append(f"{j:18}  {row}")
    lines.append(f"\nStatus mix: {Counter(r['status'] for r in rules)}   "
                 f"conflict-flagged rules: {[r['team_rule_id'] for r in rules if r['conflict_flag']]}")
    report = "\n".join(lines)
    print(report)
    (out / "selfcheck.txt").write_text(report)
    print("\nOVERALL:", "ALL CHECKS PASS" if ok_all else "SOME CHECKS FAIL — see above")
    return ok_all
