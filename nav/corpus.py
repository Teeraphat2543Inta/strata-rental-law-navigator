"""Load the law corpus (starter pack + any live-added documents)."""
import csv
import re
from dataclasses import dataclass
from pathlib import Path

from . import config


@dataclass
class Doc:
    doc_id: str
    jurisdictions: str      # e.g. "CA" or "San Francisco, CA"
    url: str
    source_type: str
    retrieved_at: str
    text: str               # full text including SOURCE/RETRIEVED header
    path: str

    @property
    def body(self) -> str:
        return self.text

    @property
    def retrieved_date(self) -> str:
        m = re.search(r"RETRIEVED:\s*(\d{4}-\d{2}-\d{2})", self.text)
        if m:
            return m.group(1)
        return (self.retrieved_at or "")[:10]


def _read_manifest(path: Path, base_dir: Path):
    docs = []
    if not path.exists():
        return docs
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            tf = (row.get("text_file") or "").strip()
            if not tf:
                continue                      # link-only source: nothing to quote from
            p = base_dir / tf
            if not p.exists():
                continue
            docs.append(Doc(
                doc_id=row["doc_id"].strip(),
                jurisdictions=row.get("jurisdictions", "").strip(),
                url=row.get("url", "").strip(),
                source_type=row.get("source_type", "").strip(),
                retrieved_at=row.get("retrieved_at", "").strip(),
                text=p.read_text(encoding="utf-8", errors="replace"),
                path=str(p),
            ))
    return docs


def load_docs():
    docs = _read_manifest(config.CORPUS_MANIFEST, config.CORPUS_DIR)
    docs += _read_manifest(config.EXTRA_MANIFEST, config.EXTRA_DOCS)
    seen, out = set(), []
    for d in docs:
        if d.doc_id not in seen:
            seen.add(d.doc_id)
            out.append(d)
    return out


def load_link_only():
    """Sources the pack lists without text. Used only to tell the user what we could NOT read."""
    rows = []
    with open(config.CORPUS_MANIFEST, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if not (row.get("text_file") or "").strip():
                rows.append({k: row[k] for k in ("doc_id", "jurisdictions", "url", "source_type")})
    return rows
