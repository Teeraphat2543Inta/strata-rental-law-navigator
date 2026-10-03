#!/usr/bin/env python3
"""Rental Housing Law Navigator — one command per stage.

  python run.py geocode                 # Census Geocoder → cache/geocode (needs internet, ~5 min)
  python run.py extract                 # Claude reads every corpus doc → cache/llm (needs ANTHROPIC_API_KEY)
  python run.py build                   # rules.json, lookups.json, changes.json, out/index.html
  python run.py check                   # self-check: schema, quotes, T1–T5 expectations
  python run.py fetch-links             # optional: read link-only sources (Hoboken/JC bans, MA ballot ruling)
  python run.py all                     # geocode + extract + build + check
  python run.py add-doc FILE --id D088 --jurisdiction "Cambridge, MA" --url URL
                                        # hour-16 flow: ingest a new document, extract it, rebuild, report T6
"""
import argparse
import csv
import json
import sys
import time

from nav import config


def _extract_and_postprocess(force=False):
    from nav import extract
    raw_rules, raw_findings, docs = extract.run(force=force)
    audit = []
    rules, findings = extract.postprocess(raw_rules, raw_findings, docs, audit)
    config.OUT.mkdir(exist_ok=True)
    with open(config.AUDIT_LOG, "w") as f:
        for a in audit:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **a}) + "\n")
    (config.OUT / "_rules_cache.json").write_text(json.dumps({"rules": rules, "findings": findings}))
    print(f"[extract] {len(raw_rules)} raw records → {len(rules)} rules after verification + merge; "
          f"{sum(1 for r in rules if r['quote_verified'])} with verified quotes")
    return rules, findings


def _load_rules():
    p = config.OUT / "_rules_cache.json"
    if not p.exists():
        sys.exit("No extracted rules yet: run `python run.py extract` first.")
    d = json.loads(p.read_text())
    return d["rules"], d["findings"]


def _new_docs():
    if not config.EXTRA_MANIFEST.exists():
        return []
    with open(config.EXTRA_MANIFEST) as f:
        # link-only sources read by fetch-links fill gaps in the starter corpus; only documents registered
        # with add-doc are *new law* and get their own change test (T6, T7, …)
        return [r["doc_id"] for r in csv.DictReader(f) if not r["source_type"].startswith("fetched")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["geocode", "fetch-links", "extract", "build", "check", "score", "all", "add-doc"])
    ap.add_argument("file", nargs="?")
    ap.add_argument("--id")
    ap.add_argument("--jurisdiction")
    ap.add_argument("--url", default="")
    ap.add_argument("--force", action="store_true", help="ignore the LLM cache")
    ap.add_argument("--include-publishers", action="store_true")
    a = ap.parse_args()

    if a.cmd in ("geocode", "all"):
        from nav import geocode
        geocode.run()
    if a.cmd == "fetch-links":
        from nav import fetch
        fetch.run(include_publishers=a.include_publishers)
    if a.cmd == "add-doc":
        from pathlib import Path
        src = Path(a.file).read_text(encoding="utf-8", errors="replace")
        did = a.id or "D088"
        config.EXTRA_DOCS.mkdir(exist_ok=True)
        if not src.startswith("SOURCE:"):
            src = f"SOURCE: {a.url}\nRETRIEVED: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}\n\n" + src
        (config.EXTRA_DOCS / f"{did}.txt").write_text(src)
        rows = []
        if config.EXTRA_MANIFEST.exists():
            with open(config.EXTRA_MANIFEST) as f:
                rows = [r for r in csv.DictReader(f) if r["doc_id"] != did]
        rows.append({"doc_id": did, "jurisdictions": a.jurisdiction or "", "url": a.url,
                     "source_type": "official", "retrieved_at": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()),
                     "text_file": f"{did}.txt"})
        with open(config.EXTRA_MANIFEST, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"[add-doc] registered {did}; extracting (cached docs are not re-billed)…")
    if a.cmd in ("extract", "all", "add-doc"):
        rules, findings = _extract_and_postprocess(force=a.force)
    if a.cmd in ("build", "all", "add-doc"):
        from nav import build
        rules, findings = _load_rules()
        build.build(rules, findings, new_doc_ids=_new_docs())
    if a.cmd in ("check", "all", "add-doc"):
        from nav import build, selfcheck
        selfcheck.run()
        build.attach_selfcheck()
    if a.cmd in ("score", "all", "add-doc"):
        from nav import score
        score.run()


if __name__ == "__main__":
    main()
