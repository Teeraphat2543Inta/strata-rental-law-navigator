"""Evidence-weighted confidence for a rule.

A rule supported by several independent sources is more trustworthy than one supported by a single
secondary page. Each supporting source i contributes a probability w_i that it alone establishes the
rule (by source type, discounted by how the quote was matched); sources are combined with a noisy-OR,
1 − Π(1 − w_i). Caveats and typed conflicts discount the result. The final value blends that evidence
score with the extractor's own confidence, so neither can dominate.
"""
SOURCE_WEIGHT = {"official": 0.9, "official city-linked policy": 0.8}
FETCHED_WEIGHT = 0.6           # law-firm, news or mirror pages read with fetch-links
QUOTE_FACTOR = {"exact": 1.0, "normalized": 0.95}   # fuzzy:<ratio> uses the ratio itself


def source_weight(source_type, quote_check="exact"):
    w = SOURCE_WEIGHT.get(source_type, FETCHED_WEIGHT if source_type.startswith("fetched") else 0.7)
    if quote_check.startswith("fuzzy:"):
        f = float(quote_check.split(":")[1])
    else:
        f = QUOTE_FACTOR.get(quote_check, 0.0)
    return w * f


def noisy_or(ws):
    p = 1.0
    for w in ws:
        p *= 1.0 - max(0.0, min(1.0, w))
    return 1.0 - p


def evidence_confidence(model_conf, source_weights, caveat=False, conflict=False):
    e = noisy_or(source_weights)
    if caveat:
        e *= 0.9
    if conflict:
        e *= 0.8
    return round(0.5 * float(model_conf or 0.5) + 0.5 * e, 2), round(e, 3)
