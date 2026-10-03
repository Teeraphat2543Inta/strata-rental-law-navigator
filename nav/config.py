"""Central configuration. Override anything with environment variables."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Path to the unzipped RealPage starter pack (folder containing corpus/, data/, schema/, dev/)
PACK = Path(os.environ.get("STARTER_PACK", ROOT / "starter_pack"))

CORPUS_MANIFEST = PACK / "corpus" / "corpus_manifest.csv"
CORPUS_DIR = PACK / "corpus"            # manifest text_file paths are relative to corpus/
ADDRESSES = PACK / "data" / "sample_addresses.csv"
SCHEMA = PACK / "schema" / "rule_record.schema.json"
CHANGE_TESTS = PACK / "dev" / "change_tests.json"
EXTRA_DOCS = ROOT / "extra_docs"        # hour-16 ordinance and any live-added documents
EXTRA_MANIFEST = EXTRA_DOCS / "extra_manifest.csv"

CACHE = ROOT / "cache"
LLM_CACHE = CACHE / "llm"
GEO_CACHE = CACHE / "geocode" / "census_places.json"
OUT = ROOT / "out"
AUDIT_LOG = OUT / "audit_log.jsonl"

QUERY_DATE = os.environ.get("QUERY_DATE", "2026-10-01")
# Dates the demo UI precomputes so the "as of" selector works offline
UI_DATES = ["2025-12-31", "2026-01-02", "2026-10-01", "2027-07-02"]

ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
MAX_DOC_CHARS = 110_000     # documents longer than this are chunked
CHUNK_CHARS = 60_000
CHUNK_OVERLAP = 3_000
