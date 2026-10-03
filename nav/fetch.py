"""Optional: read a few link-only sources listed in corpus/links_only.csv.

The starter pack gives some laws only as links (e.g. the Hoboken and Jersey City algorithmic-pricing
ordinances and the Massachusetts ballot-question ruling). Without them the system cannot cite those rules,
so this step fetches ONE page per listed source, politely, and stores it as a dated text file.

Policy (participant guide §3 + organizer ruling on Discord, 2026-10-04: individual pages listed in
links_only.csv may be fetched, one request per page, with the retrieval date recorded; no bulk scraping):
  * code-publisher pages (ecode360, amlegal, gocodebook) are fetched only with --include-publishers;
  * pages that refuse (403) or return no law text are left out and listed as unread in the app;
  * every fetched page keeps its URL + retrieval timestamp and is marked source_type "fetched: <type>",
    so the UI and rules.json show it is NOT part of the official starter corpus.
"""
import csv
import html
import re
import time
import urllib.request

from . import config

UA = "Mozilla/5.0 (hackathon research prototype; one request per page)"


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript|svg|header|footer|nav)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", raw)
    txt = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    txt = re.sub(r"[ \t\r\f\v]+", " ", txt)
    return re.sub(r"\n\s*\n+", "\n\n", txt).strip()


def run(include_publishers=False):
    config.EXTRA_DOCS.mkdir(exist_ok=True)
    existing = []
    if config.EXTRA_MANIFEST.exists():
        with open(config.EXTRA_MANIFEST) as f:
            existing = list(csv.DictReader(f))
    have = {r["doc_id"] for r in existing}
    with open(config.PACK / "corpus" / "links_only.csv", newline="", encoding="utf-8-sig") as f:
        links = list(csv.DictReader(f))
    for row in links:
        did, st = row["doc_id"], row["source_type"]
        if did in have:
            continue
        if st == "code publisher" and not include_publishers:
            print(f"  skip {did} (code publisher; use --include-publishers after checking terms)")
            continue
        try:
            req = urllib.request.Request(row["url"], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                ctype = r.headers.get("content-type", "")
                body = r.read()
            if "pdf" in ctype:
                print(f"  skip {did} (PDF; add manually with `run.py add-doc`)")
                continue
            text = html_to_text(body.decode("utf-8", errors="replace"))
            if len(text) < 500:
                print(f"  skip {did} (page returned too little text)")
                continue
            ts = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
            (config.EXTRA_DOCS / f"{did}.txt").write_text(f"SOURCE: {row['url']}\nRETRIEVED: {ts}\n\n{text}")
            existing.append({"doc_id": did, "jurisdictions": row["jurisdictions"], "url": row["url"],
                             "source_type": f"fetched: {st}", "retrieved_at": ts, "text_file": f"{did}.txt"})
            print(f"  fetched {did} ({len(text):,} chars) {row['url'][:70]}")
        except Exception as e:  # noqa: BLE001
            print(f"  failed {did}: {str(e)[:100]}")
        time.sleep(1.5)
    with open(config.EXTRA_MANIFEST, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["doc_id", "jurisdictions", "url", "source_type", "retrieved_at", "text_file"])
        w.writeheader()
        w.writerows(existing)
