"""Assemble the submission files and the demo app from extracted rules."""
import json
import time

from . import config
from .changes import changes_for_doc, run_test
from .corpus import load_docs, load_link_only
from .engine import excluded, lookups
from .temporal import change_dates
from .voi import rank as voi_rank
from .geocode import load_cache
from .properties import build_property, load_addresses


def _w(name, obj):
    config.OUT.mkdir(parents=True, exist_ok=True)
    (config.OUT / name).write_text(json.dumps(obj, indent=1, ensure_ascii=False))
    print(f"  wrote out/{name}")


def build(rules, findings, new_doc_ids=()):
    census = load_cache()
    props = [build_property(r, census) for r in load_addresses()]
    print(f"[build] {len(rules)} rules, {len(props)} addresses, geocoded={len(census)}")

    _w("rules.json", {"rules": rules})
    _w("lookups.json", {"as_of": config.QUERY_DATE, "lookups": lookups(props, rules, config.QUERY_DATE)})

    tests = json.loads(config.CHANGE_TESTS.read_text())
    changes, detail = {}, {}
    for t in tests:
        changes[t["test_id"]], detail[t["test_id"]] = run_test(t, props, rules)
    for i, d in enumerate(new_doc_ids, start=len(tests) + 1):
        tid = f"T{i}"
        changes[tid], detail[tid] = changes_for_doc(d, props, rules, config.QUERY_DATE)
    _w("changes.json", changes)
    _w("changes_detail.json", detail)
    _w("no_rule_findings.json", findings)
    _w("properties.json", props)

    # demo bundle: everything the static app needs, precomputed for the as-of selector
    bundle = {
        "generated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "default_as_of": config.QUERY_DATE,
        "dates": config.UI_DATES,
        "rules": rules,
        "properties": props,
        "lookups": {d: lookups(props, rules, d) for d in config.UI_DATES},
        "excluded": {d: {p["address_id"]: excluded(p, rules, d) for p in props} for d in config.UI_DATES},
        "changes": changes,
        "no_rule_findings": findings,
        "link_only_sources": load_link_only(),
        "sources": [{"doc_id": d.doc_id, "jurisdictions": d.jurisdictions, "url": d.url, "source_type": d.source_type,
                     "retrieved": d.retrieved_date, "chars": len(d.text)} for d in load_docs()],
        "tests": tests,
        "audit": _audit_summary(),
        "timeline": change_dates(props, rules),
        "voi": voi_rank(props, lookups(props, rules, config.QUERY_DATE)),
        "model": config.ANTHROPIC_MODEL,
        "selfcheck": None,
    }
    (config.OUT / "app_bundle.json").write_text(json.dumps(bundle, ensure_ascii=False))
    render_app(bundle)
    return props, changes


def _audit_summary():
    path = config.AUDIT_LOG
    if not path.exists():
        return None
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    stages, checks = {}, {}
    for r in rows:
        stages[r["stage"]] = stages.get(r["stage"], 0) + 1
        if r["stage"] == "extract":
            checks[r["quote_check"].split(":")[0]] = checks.get(r["quote_check"].split(":")[0], 0) + 1
    dd = next((r for r in rows if r["stage"] == "dedupe_check"), None)
    return {"stages": stages, "quote_checks": checks, "dedupe_check": dd,
            "merged_records": sum(len(r.get("merged", [])) for r in rows if r["stage"] == "merge")}


def render_app(bundle):
    tpl = (config.ROOT / "app" / "index.template.html").read_text()
    html = tpl.replace("/*__DATA__*/null", json.dumps(bundle, ensure_ascii=False).replace("</", "<\\/"))
    (config.OUT / "index.html").write_text(html)
    config.DOCS.mkdir(parents=True, exist_ok=True)
    (config.DOCS / "index.html").write_text(html)      # GitHub Pages serves /docs
    print("  wrote out/index.html + docs/index.html (self-contained demo app)")


def attach_selfcheck():
    """Embed the latest self-check result in the app, so the demo shows the numbers it was built with."""
    path, report = config.OUT / "app_bundle.json", config.OUT / "selfcheck.txt"
    if not (path.exists() and report.exists()):
        return
    bundle = json.loads(path.read_text())
    lines = [l for l in report.read_text().splitlines() if l.startswith(("PASS", "FAIL"))]
    tl = [l for l in lines if l.split()[1].startswith("T") and l.split()[1][1:2].isdigit()]
    bundle["selfcheck"] = {"lines": lines, "tests_pass": len({l.split()[1] for l in tl if l.startswith("PASS")}
                                                              - {l.split()[1] for l in tl if l.startswith("FAIL")}),
                           "tests_total": len({l.split()[1] for l in tl})}
    path.write_text(json.dumps(bundle, ensure_ascii=False))
    render_app(bundle)
