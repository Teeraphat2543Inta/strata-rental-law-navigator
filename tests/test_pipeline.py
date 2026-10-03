"""End-to-end plumbing test with fake model outputs (no API key needed):  python tests/test_pipeline.py"""
import json, pathlib, shutil, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
subprocess.run([sys.executable, str(ROOT / "tests/fixtures/make_fixtures.py")], check=True)
from nav import config, extract, llm, build, selfcheck  # noqa: E402

FIX = ROOT / "tests/fixtures/llm"
config.OUT = ROOT / "tests/_out"
config.EXTRA_DOCS = ROOT / "tests/fixtures/extra"
config.EXTRA_MANIFEST = config.EXTRA_DOCS / "extra_manifest.csv"
config.GEO_CACHE = ROOT / "tests/_out/none.json"
shutil.rmtree(config.OUT, ignore_errors=True); config.OUT.mkdir()

def fake_call_tool(system, user, tool, cache_name, **kw):
    p = FIX / f"{cache_name.split('.')[0]}.json"
    return json.loads(p.read_text()) if p.exists() else {"rules": [], "no_rule_findings": []}
extract.call_tool = fake_call_tool

raw_r, raw_f, docs = extract.run()
audit = []
rules, findings = extract.postprocess(raw_r, raw_f, docs, audit)
print(f"{len(rules)} rules; quote checks:", [a["quote_check"] for a in audit if "quote_check" in a])
build.build(rules, findings)
ok = selfcheck.run()
print("\nT1-T5 plumbing", "OK" if ok else "has failures (expected only if fixtures are incomplete)")
