"""Deterministic duplicate detection, used to cross-check the LLM's clustering of rule records.

TF-IDF vectors over title + requirement + citation; cosine similarity ≥ threshold or an identical
normalized citation key links two records; connected components (union-find) are the clusters.
Agreement with another clustering is reported as pairwise precision / recall / F1.
"""
import math
import re
from collections import Counter
from itertools import combinations

STOP = set("a an the of to and or in on for by is are be with any that this as at from may not shall".split())


def _tokens(s):
    return [t for t in re.findall(r"[a-z0-9§.]+", (s or "").lower()) if t not in STOP and len(t) > 1]


def tfidf(docs):
    tf = [Counter(_tokens(d)) for d in docs]
    df = Counter(t for c in tf for t in c)
    n = len(docs)
    vecs = []
    for c in tf:
        v = {t: (1 + math.log(k)) * math.log((1 + n) / (1 + df[t]) + 1) for t, k in c.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({t: x / norm for t, x in v.items()})
    return vecs


def cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


def clusters(records, key=lambda r: r.get("_cite_key"), threshold=0.55):
    texts = [f"{r.get('title', '')} {r.get('requirement', '')} {r.get('citation', '')}" for r in records]
    vecs = tfidf(texts)
    parent = list(range(len(records)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, j in combinations(range(len(records)), 2):
        same_key = key(records[i]) and key(records[i]) == key(records[j])
        if same_key or cosine(vecs[i], vecs[j]) >= threshold:
            parent[find(i)] = find(j)
    groups = {}
    for i in range(len(records)):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def pairwise_agreement(a, b):
    """a, b: lists of clusters (lists of indices). Returns (precision, recall, f1) of b against a."""
    pa = {frozenset(p) for g in a for p in combinations(sorted(g), 2)}
    pb = {frozenset(p) for g in b for p in combinations(sorted(g), 2)}
    if not pa and not pb:
        return 1.0, 1.0, 1.0
    tp = len(pa & pb)
    prec = tp / len(pb) if pb else 1.0
    rec = tp / len(pa) if pa else 1.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return round(prec, 3), round(rec, 3), round(f1, 3)
