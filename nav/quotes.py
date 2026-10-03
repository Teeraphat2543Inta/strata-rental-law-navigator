"""Verify that every quoted_span really exists in the cited source document.

The model is asked to copy text verbatim. We never trust that: each quote is located in the
source text. If the model changed whitespace, quote marks or a few characters, the quote is
replaced with the exact source substring; if it cannot be found, the rule is marked unverified.
"""
import difflib
import re

_TRANS = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
                        "\u2013": "-", "\u2014": "-", "\u00a0": " ", "\u00a7": "§"})


def _norm_with_map(s: str):
    """Lower-case, unify punctuation, collapse whitespace. Returns (normalized, index_map)."""
    out, idx, prev_space = [], [], False
    for i, ch in enumerate(s.translate(_TRANS)):
        if ch.isspace():
            if prev_space:
                continue
            out.append(" ")
            idx.append(i)
            prev_space = True
        else:
            out.append(ch.lower())
            idx.append(i)
            prev_space = False
    return "".join(out), idx


def locate(quote: str, source: str):
    """Return (exact_source_substring, method) or (None, 'not_found')."""
    if not quote or len(quote.strip()) < 10:
        return None, "too_short"
    if quote in source:
        return quote, "exact"
    nq, _ = _norm_with_map(quote.strip())
    ns, smap = _norm_with_map(source)
    pos = ns.find(nq)
    if pos >= 0:
        start, end = smap[pos], smap[pos + len(nq) - 1] + 1
        return source[start:end], "normalized"
    # fuzzy: compare against runs of 1-4 consecutive source segments (lines / sentences)
    segs = [(m.start(), m.end()) for m in re.finditer(r"[^\n.;]+[.;]?", source) if m.group().strip()]
    sm = difflib.SequenceMatcher(autojunk=False)
    sm.set_seq2(nq)
    best, best_ratio = None, 0.0
    for i in range(len(segs)):
        for j in range(i, min(i + 6, len(segs))):
            a, b = segs[i][0], segs[j][1]
            if b - a > len(quote) * 1.6 + 40:
                break
            cand, _ = _norm_with_map(source[a:b].strip())
            sm.set_seq1(cand)
            if sm.real_quick_ratio() <= best_ratio or sm.quick_ratio() <= best_ratio:
                continue
            r = sm.ratio()
            if r > best_ratio:
                best_ratio, best = r, (a, b)
    if best and best_ratio >= 0.85:
        return source[best[0]:best[1]].strip(), f"fuzzy:{best_ratio:.2f}"
    return None, "not_found"


def clean_span(span: str) -> str:
    """Quotes are emitted as exact source text, trimmed of surrounding whitespace."""
    return span.strip()
