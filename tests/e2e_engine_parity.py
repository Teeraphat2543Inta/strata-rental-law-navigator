"""The in-browser rule engine (app) must give exactly the Python engine's answers.

Runs the built app in headless Chromium and compares ENG.evaluate(...) with out/lookups for every
address at every precomputed date, including explanations and conflict flags.
Needs `pip install playwright && python -m playwright install chromium`; skipped otherwise.
    python tests/e2e_engine_parity.py
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("SKIP: playwright not installed")
    sys.exit(0)

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto((ROOT / "docs" / "index.html").as_uri() + "#/overview?notour")
    page.wait_for_timeout(800)
    r = page.evaluate("""() => { let n = 0, bad = 0;
        for (const d of DATA.dates) for (const p of DATA.properties) { n++;
          if (JSON.stringify(DATA.lookups[d][p.address_id]) !== JSON.stringify(ENG.evaluate(p, DATA.rules, d))) bad++; }
        return {n, bad}; }""")
    b.close()
assert not errors, errors
print(f"engine parity: {r['n'] - r['bad']}/{r['n']} address × date answers identical (explanations included)")
sys.exit(1 if r["bad"] else 0)
