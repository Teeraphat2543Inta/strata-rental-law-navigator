"""Self-score against the four auto-scored components of the brief (75 of 100 points).

The organizers' score.py and held-out key are not in the starter pack, so this mirrors what the brief says
is measured and reports it per component. Where a component needs the hidden key (extraction matching,
held-out addresses) we report the measurable proxy and say so — the numbers are never dressed up as official.
"""
import json
from collections import Counter

from . import config
from .corpus import load_docs
from .quotes import locate


def _jacc(a, b):
    a, b = set(a), set(b)
    return 1.0 if not a and not b else len(a & b) / len(a | b)


def run():
    out = config.OUT
    rules = json.loads((out / "rules.json").read_text())["rules"]
    lk = json.loads((out / "lookups.json").read_text())["lookups"]
    ch = json.loads((out / "changes.json").read_text())
    props = json.loads((out / "properties.json").read_text())
    docs = {d.doc_id: d.text for d in load_docs()}
    rid = {r["team_rule_id"]: r for r in rules}

    # 1. Extraction (25): field completeness of the scored fields, plus quote grounding
    fields = {"citation": lambda r: bool(r.get("citation")),
              "status": lambda r: r.get("status") in ("in_force", "not_yet_effective", "pending", "failed"),
              "effective_date or explicit null": lambda r: "effective_date" in r,
              "key_value (when a figure exists)": lambda r: r.get("key_value") is not None or r["category"] in (
                  "just_cause_eviction", "screening_restrictions", "algorithmic_rent_setting"),
              "quoted span found in corpus": lambda r: bool(locate(r["quoted_span"], docs.get(r["source_doc_id"], ""))[0])}
    ext = {k: sum(f(r) for r in rules) / len(rules) for k, f in fields.items()}

    # 2. Address coverage (20): every address answered, every jurisdiction resolved, unknown used honestly
    res = Counter(e["result"] for v in lk.values() for e in v)
    resolved = sum(1 for p in props if p["jurisdiction"]) / len(props)
    answered = len(lk) / len(props)

    # 3. Citations (15): exactly as the brief defines it
    applies = [e for v in lk.values() for e in v if e["result"] == "applies"]
    cited = sum(1 for e in applies if locate(rid[e["team_rule_id"]]["quoted_span"],
                                             docs.get(rid[e["team_rule_id"]]["source_doc_id"], ""))[0])
    cit = cited / max(1, len(applies))

    # 4. Change tracking (15): overlap with the affected sets each test definition implies
    state = {s: [p["address_id"] for p in props if p["state"] == s] for s in ("CA", "NJ", "MA")}
    city = lambda c: [p["address_id"] for p in props if p["city"] == c]  # noqa: E731
    expect = {"T1": state["CA"], "T2": city("Hoboken") + city("Jersey City"), "T3": state["NJ"],
              "T4": state["MA"], "T5": []}
    tr = {t: _jacc(ch.get(t, {}).get("affected_address_ids", []), e) for t, e in expect.items()}
    t3flags = _jacc(ch.get("T3", {}).get("conflict_flag_address_ids", []), city("Hoboken") + city("Jersey City"))

    W = 66
    line = "─" * W
    rows = [f"┌{line}┐", f"│{'STRATA · SELF-SCORE (auto-scored components of the brief)':^{W}}│", f"├{line}┤"]

    def row(label, val):
        rows.append(f"│ {label:<46}{val:>18} │")
    row("Extraction · 25 pts", f"{len(rules)} rules")
    for k, v in ext.items():
        row(f"   {k}", f"{v:6.1%}")
    row("   (field accuracy vs held-out key)", "judges' key")
    rows.append(f"├{line}┤")
    row("Address coverage · 20 pts", "")
    row("   addresses answered", f"{answered:6.1%}")
    row("   legal jurisdiction resolved", f"{resolved:6.1%}")
    row("   results", f"{sum(res.values())} answers")
    for k in ("applies", "superseded", "unknown", "not_yet_effective", "pending"):
        row(f"      {k}", str(res.get(k, 0)))
    rows.append(f"├{line}┤")
    row("Citations · 15 pts", f"{cit:6.1%}")
    row("   'applies' backed by a quote in the corpus", f"{cited}/{len(applies)}")
    rows.append(f"├{line}┤")
    row("Change tracking · 15 pts", "vs expected")
    for t, v in tr.items():
        n = len(ch.get(t, {}).get("affected_address_ids", []))
        row(f"   {t}  affected={n}", f"{v:6.1%}")
    row("   T3 conflict flags (JC + Hoboken)", f"{t3flags:6.1%}")
    extra = sorted(k for k in ch if k not in expect)
    for t in extra:
        row(f"   {t}  affected={len(ch[t]['affected_address_ids'])} (new document)", "reported")
    rows.append(f"└{line}┘")
    rows.append("Official score.py and the held-out key are held by the judges; this is a transparent proxy.")
    report = "\n".join(rows)
    print(report)
    (out / "score_self.txt").write_text(report + "\n")
    return report
