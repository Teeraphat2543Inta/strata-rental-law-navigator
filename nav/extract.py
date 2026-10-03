"""Module A — automated rule extraction.

For every corpus document the model reads the full text and returns structured rule records
through one schema-typed tool call. Every record is then post-processed by deterministic code:
  * quoted_span is located in the source text (exact → normalized → fuzzy) and replaced by the
    exact source substring; records whose quote cannot be found are kept but flagged unverified
  * jurisdiction / citation are normalized, records describing the same provision are merged
  * conflicting effective dates across sources raise a conflict flag for human review
  * status is recomputed from effective_date for the query date
"""
import json
import re
from collections import defaultdict

from . import config
from .corpus import Doc, load_docs
from .confidence import evidence_confidence, source_weight
from .dedupe import clusters as tfidf_clusters, pairwise_agreement
from .llm import call_tool
from .quotes import locate, clean_span

CATEGORIES = ["rent_increase_limits", "just_cause_eviction", "security_deposits",
              "application_screening_fees", "screening_restrictions", "algorithmic_rent_setting"]
JURISDICTIONS = ["CA", "NJ", "MA", "Los Angeles, CA", "San Francisco, CA", "San Diego, CA",
                 "Berkeley, CA", "Santa Ana, CA", "Jersey City, NJ", "Hoboken, NJ", "Newark, NJ",
                 "Boston, MA", "Cambridge, MA"]

SYSTEM = f"""You are a meticulous legal-data extraction engine for a rental housing law navigator.
You read ONE source document and return every housing RULE it establishes or describes, as structured
records, through the submit_rules tool. Accuracy and verifiable quotes matter more than volume.

SCOPE — only these six categories, for residential rental housing:
- rent_increase_limits: caps/formulas on rent increases and rent control / rent stabilization coverage.
  A state law that BARS local rent control is not a rent cap: record it as a no_rule_finding for every city
  of that state ("no rent cap: state law bars local rent control"), not as a rule. A state law that only
  EXEMPTS some buildings from local rent control is a rule.
- just_cause_eviction: allowed eviction causes, notice, relocation assistance tied to no-fault eviction, coverage.
- security_deposits: maximum deposit, exceptions, interest/return rules that are part of the deposit law.
- application_screening_fees: application/screening fee caps, allowed upfront charges, receipts/refunds, broker fees charged to tenants.
- screening_restrictions: limits on criminal-history screening, source-of-income discrimination, timing of screening.
- algorithmic_rent_setting: bans/limits on algorithmic or coordinated rent-pricing software (definitions, prohibited conduct, penalties).
Ignore everything else (habitability, discrimination in general, registration fees, utilities...) unless it
is a direct part of one of the six categories.

JURISDICTION — use exactly one of: {", ".join(JURISDICTIONS)}. A rule belongs to the government that
ENACTED it: a city web page that explains a state statute yields a state rule (jurisdiction "CA"), not a city rule.
level = "state" for CA/NJ/MA, "city" otherwise.

GRANULARITY — one record per distinct legal provision per category. Do not split one provision into many
records, and do not merge two different laws. If a law has a state cap and a separate city ordinance, those
are two records.

STATUS as written in the source: "in_force" (enacted and effective), "not_yet_effective" (enacted, future
effective date), "pending" (a bill/proposal that is not law — e.g. referred to committee), "failed" (vetoed,
struck from ballot, rejected, repealed, or sent to a study order). Pending bills and failed measures MUST be
recorded with that status — never as in_force. A local ordinance that the document shows only as a draft, a
staff report, a first reading / "passed to print", a council motion or a policy order asking staff to draft
language is "pending" unless the same document also shows final adoption. effective_date: ISO date (YYYY-MM-DD, or YYYY-MM / YYYY if the source is only that precise)
on which the rule takes/took effect. Compute it if the text states a rule (e.g. "takes effect on the first day of
the twelfth month after enactment" with an enactment date). Constitutional default: a California statute
from a regular session that the document shows as chaptered/approved in year Y, with no other effective date
and no urgency clause, takes effect on Y+1-01-01 (Cal. Const. art. IV, § 8(c)) — use that and quote the
chaptered/approved line as effective_date_quote. null if none of this is in the document.

CITATION — the official cite in this style: "Cal. Civ. Code § 1947.12", "Cal. Gov. Code § 12955",
"N.J.S.A. 46:8-21.2", "P.L.2026, c.43", "M.G.L. c. 186, § 15B", "S.F. Admin. Code § 37.9",
"L.A.M.C. § 151.00", "B.M.C. ch. 13.63", "S.D.M.C. § 98.1103", "Jersey City Code § 218-12",
"Hoboken Code ch. 158", "Mass. S.2983". Use the bill number for bills.

QUOTES — quoted_span must be copied CHARACTER FOR CHARACTER from the document (20–400 characters, one
contiguous passage, ideally one sentence) and must by itself support the requirement. Never paraphrase inside
quoted_span. If the effective date is stated elsewhere in the document, copy that passage into
effective_date_quote.

COVERAGE (machine-readable, used to decide which buildings a rule covers — building/owner facts only,
never tenant-level facts such as length of tenancy):
- covered_if_built_on_or_before: date — rule covers only buildings first built / issued a certificate of
  occupancy on or before this date (e.g. a rent ordinance limited to pre-1978 buildings).
- covered_if_built_after: date — rule covers only buildings built after this date.
- exempt_if_newer_than_years: integer — rolling exemption for buildings whose certificate of occupancy
  is within the previous N years.
- min_units / max_units: integers — rule covers only buildings with at least / at most this many units.
- exemption_max_units: integer — an exemption exists only for buildings with at most this many units (e.g.
  owner-occupied two-unit buildings, small-landlord exceptions defined by unit count).
- owner_type_dependent: true if coverage depends on who the owner is (natural person, corporation, REIT)
  in a way NOT captured by exemption_max_units.
- yields_to_local: true if a STATE rule does not apply where a stricter local rule of the same category
  covers the unit (e.g. statewide rent cap exempting units under local rent control).
- may_preempt_local: true if a STATE rule may preempt or conflict with local ordinances of the same category.
Express exemptions of newer buildings as coverage: "units first certified for occupancy after June 13, 1979 are
exempt from the rent limits" → covered_if_built_on_or_before = "1979-06-13" on the rent-limit rule (and NOT on a
just-cause rule that still covers those units).
If a document states which buildings a local rent-control / rent-stabilization ordinance's RENT LIMITS cover
(e.g. a just-cause page saying "units that first obtained a Certificate of Occupancy after June 13, 1979 are
exempt from the rent increase limitations"), ALSO record a rent_increase_limits rule for that ordinance that
carries this coverage and quotes that sentence, even when the document is mainly about another category.
Leave a field null/false when the document does not establish it.

CONFLICTS vs CAVEATS — two separate fields:
- conflict_type: a REAL conflict a human must review before relying on the answer: "effective_date" (the
  document gives two different effective dates for this rule), "preemption" (this rule and another level's rule
  may conflict or one may preempt the other), "litigation" (the rule is enjoined or its validity is being
  litigated). Otherwise "none". Secondary sources, approximate citations, month-only dates and rates that are
  adjusted yearly are NOT conflicts.
- conflict_note: one sentence explaining the conflict (null when conflict_type is "none").
- caveat: any other limitation a reader should know (secondary source, approximate citation, figure updated
  annually, only a passing mention). null if none. Lower confidence accordingly.

Also return no_rule_findings: explicit statements that NO rule of a category exists at a level
(e.g. a state law barring local rent control means a city has no rent cap), each with a verbatim quote.
Return an empty list when the document contains no rule in scope."""

RULE_PROPS = {
    "jurisdiction": {"type": "string", "enum": JURISDICTIONS},
    "level": {"type": "string", "enum": ["state", "city"]},
    "category": {"type": "string", "enum": CATEGORIES},
    "status": {"type": "string", "enum": ["in_force", "not_yet_effective", "pending", "failed"]},
    "title": {"type": "string"},
    "requirement": {"type": "string", "description": "One or two plain-language sentences a renter can act on."},
    "requirement_es": {"type": "string", "description": "The same requirement in plain Spanish."},
    "key_value": {"type": ["string", "null"]},
    "coverage_conditions": {"type": ["string", "null"], "description": "Human-readable coverage summary."},
    "coverage": {"type": "object", "properties": {
        "covered_if_built_on_or_before": {"type": ["string", "null"]},
        "covered_if_built_after": {"type": ["string", "null"]},
        "exempt_if_newer_than_years": {"type": ["integer", "null"]},
        "min_units": {"type": ["integer", "null"]},
        "max_units": {"type": ["integer", "null"]},
        "exemption_max_units": {"type": ["integer", "null"]},
        "owner_type_dependent": {"type": "boolean"},
        "yields_to_local": {"type": "boolean"},
        "may_preempt_local": {"type": "boolean"}}},
    "exemptions": {"type": ["string", "null"]},
    "penalty": {"type": ["string", "null"]},
    "effective_date": {"type": ["string", "null"]},
    "effective_date_quote": {"type": ["string", "null"]},
    "citation": {"type": "string"},
    "quoted_span": {"type": "string"},
    "confidence": {"type": "number"},
    "conflict_type": {"type": "string", "enum": ["none", "effective_date", "preemption", "litigation"]},
    "conflict_note": {"type": ["string", "null"]},
    "caveat": {"type": ["string", "null"]},
}
TOOL = {
    "name": "submit_rules",
    "description": "Submit every in-scope rule found in the document.",
    "input_schema": {
        "type": "object",
        "properties": {
            "rules": {"type": "array", "items": {"type": "object", "properties": RULE_PROPS,
                      "required": ["jurisdiction", "level", "category", "status", "title", "requirement",
                                   "citation", "quoted_span", "coverage", "confidence"]}},
            "no_rule_findings": {"type": "array", "items": {"type": "object", "properties": {
                "jurisdiction": {"type": "string", "enum": JURISDICTIONS},
                "category": {"type": "string", "enum": CATEGORIES},
                "finding": {"type": "string"},
                "quoted_span": {"type": "string"}}}},
        },
        "required": ["rules", "no_rule_findings"],
    },
}


def _chunks(text: str):
    if len(text) <= config.MAX_DOC_CHARS:
        return [text]
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + config.CHUNK_CHARS])
        i += config.CHUNK_CHARS - config.CHUNK_OVERLAP
    return out


def extract_doc(doc: Doc, force=False):
    parts = _chunks(doc.text)
    rules, findings = [], []
    for k, part in enumerate(parts):
        user = (f"DOCUMENT {doc.doc_id}  (part {k + 1} of {len(parts)})\n"
                f"Manifest jurisdiction: {doc.jurisdictions}\nSource type: {doc.source_type}\n"
                f"URL: {doc.url}\nRetrieved: {doc.retrieved_date}\n"
                f"Today's query date: {config.QUERY_DATE}\n\n<document>\n{part}\n</document>")
        out = call_tool(SYSTEM, user, TOOL, cache_name=f"{doc.doc_id}.p{k + 1}", force=force)
        for r in out.get("rules", []):
            r["_doc"] = doc.doc_id
            rules.append(r)
        for f in out.get("no_rule_findings", []):
            f["_doc"] = doc.doc_id
            findings.append(f)
    return rules, findings


# ---------------------------------------------------------------- post-processing
def cite_key(cite: str) -> str:
    """Normalized key so 'Cal. Civ. Code §1947.12' == 'California Civil Code Section 1947.12'."""
    c = (cite or "").lower().replace("section", "§").replace("sec.", "§")
    c = re.sub(r"(california|cal\.?)\s*(civil|civ\.?)\s*code", "cacivcode", c)
    c = re.sub(r"(california|cal\.?)\s*(government|gov\.?|govt\.?)\s*code", "cagovcode", c)
    c = re.sub(r"(m\.?g\.?l\.?|g\.\s*l\.|general laws)", "mgl", c)
    c = re.sub(r"chapter", "c", c)
    c = re.sub(r"[^a-z0-9.:\-]", "", c)
    c = re.sub(r"\.(?=[a-z])", "", c)
    return c.strip(".")


def _date_key(d):
    if not d:
        return None
    d = str(d)
    return (d + "-01-01")[:10] if len(d) == 4 else (d + "-01")[:10] if len(d) == 7 else d[:10]


def status_on(rule: dict, as_of: str) -> str:
    raw = rule.get("status_raw") or rule.get("status")
    if raw in ("pending", "failed"):
        return raw
    eff = _date_key(rule.get("effective_date"))
    if eff and eff > as_of:
        return "not_yet_effective"
    return "in_force"


ABBR = {"CA": "CA", "NJ": "NJ", "MA": "MA", "Los Angeles, CA": "LA", "San Francisco, CA": "SF",
        "San Diego, CA": "SD", "Berkeley, CA": "BRK", "Santa Ana, CA": "SNA", "Jersey City, NJ": "JC",
        "Hoboken, NJ": "HOB", "Newark, NJ": "NWK", "Boston, MA": "BOS", "Cambridge, MA": "CAM"}
CAT_ABBR = {"rent_increase_limits": "RENT", "just_cause_eviction": "EVICT", "security_deposits": "DEP",
            "application_screening_fees": "FEE", "screening_restrictions": "SCREEN",
            "algorithmic_rent_setting": "ALG"}
OFFICIAL_RANK = {"official": 0, "official city-linked policy": 1, "code publisher": 2}
SECONDARY_ONLY_NOTE = "Secondary source only — official text not captured; verify against the ordinance."
SECONDARY_ONLY_MAX_CONFIDENCE = 0.6


def source_rank(source_type):
    """official < city-linked policy < code publisher < secondary; pages read by fetch-links keep their kind."""
    return OFFICIAL_RANK.get(source_type.removeprefix("fetched: "), 3)


def is_primary_source(source_type):
    return source_rank(source_type) < 3


CONSOLIDATE_TOOL = {
    "name": "group_records",
    "description": "Group record indices that describe the SAME legal provision.",
    "input_schema": {"type": "object", "properties": {
        "groups": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}}},
        "required": ["groups"]},
}


LOW_CONFIDENCE = 0.6
BUILDING_CUTOFFS = ("covered_if_built_on_or_before", "covered_if_built_after", "exempt_if_newer_than_years")


def _ordinance_key(citation):
    """'L.A.M.C. § 151.00' -> '151', 'B.M.C. § 13.76.110' -> '13', 'S.F. Admin. Code ch. 37' -> '37'."""
    m = re.search(r"(?:§|ch\.|chapter|sec\.)\s*(\d+)", citation or "", re.I)
    return m.group(1) if m else None


def inherit_ordinance_coverage(rules):
    """A local rent ordinance's building cutoff (e.g. CO on or before 1978-10-01) is often stated on one page
    and omitted on another page about the same ordinance (e.g. this year's allowable increase). Rules of the
    same city, category and code chapter inherit the cutoff, and say so — otherwise a rent-limit rule would
    silently reach every building in the city."""
    for r in rules:
        cov = r["coverage_conditions"]
        if r["level"] != "city" or r["category"] != "rent_increase_limits" or any(cov.get(k) for k in BUILDING_CUTOFFS):
            continue
        key = _ordinance_key(r["citation"])
        donors = [d for d in rules if d is not r and d["jurisdiction"] == r["jurisdiction"]
                  and d["category"] == r["category"] and key and _ordinance_key(d["citation"]) == key
                  and any(d["coverage_conditions"].get(k) for k in BUILDING_CUTOFFS)]
        if donors:
            d = donors[0]
            for k in BUILDING_CUTOFFS:
                if d["coverage_conditions"].get(k):
                    cov[k] = d["coverage_conditions"][k]
            r["caveat"] = " | ".join(filter(None, [r.get("caveat"),
                f"Building coverage inherited from {d['team_rule_id']} (same ordinance, {d['citation']})."]))


def consolidate(jur, cat, recs):
    """Cluster records that describe the same provision. Returns a list of lists of records."""
    if len(recs) == 1:
        return [recs]
    by_cite = defaultdict(list)
    for r in recs:
        by_cite[r["_cite_key"] or r.get("title", "").lower()].append(r)
    fallback = list(by_cite.values())
    listing = "\n".join(f"[{i}] {r.get('title')} | {r.get('citation')} | status={r.get('status')} | "
                        f"eff={r.get('effective_date')} | {r.get('requirement')} (doc {r['_doc']})"
                        for i, r in enumerate(recs))
    user = (f"Jurisdiction: {jur}\nCategory: {cat}\nThese records were extracted from different documents. "
            "Group together the indices that describe the SAME legal provision (same law/ordinance section and "
            "same requirement, even if cited differently or summarized by a secondary page). Keep different laws, "
            "and a bill vs. an enacted law, in separate groups. Every index must appear exactly once.\n\n" + listing)
    try:
        out = call_tool("You consolidate legal rule records. Be conservative: merge only true duplicates.",
                        user, CONSOLIDATE_TOOL, cache_name=f"merge.{ABBR[jur]}.{CAT_ABBR[cat]}", max_tokens=8000)
        seen, clusters = set(), []
        for g in out.get("groups", []):
            g = [i for i in g if isinstance(i, int) and 0 <= i < len(recs) and i not in seen]
            seen |= set(g)
            if g:
                clusters.append([recs[i] for i in g])
        clusters += [[recs[i]] for i in range(len(recs)) if i not in seen]
        return clusters
    except (Exception, SystemExit) as e:  # noqa: BLE001 — no key and no cached grouping: group by citation
        print(f"  [merge] fallback to citation grouping for {jur}/{cat}: {e}")
        return fallback


def postprocess(raw_rules, raw_findings, docs_by_id, audit):
    verified = []
    for r in raw_rules:
        doc = docs_by_id[r["_doc"]]
        span, how = locate(r.get("quoted_span", ""), doc.text)
        rec = dict(r)
        rec["quote_check"] = how
        if not span:
            # A rule we cannot tie to a sentence of its source is not published; the audit log keeps it.
            audit.append({"stage": "rejected", "doc_id": doc.doc_id, "reason": f"quote {how}",
                          "title": r.get("title"), "quoted_span": r.get("quoted_span")})
            continue
        rec["quoted_span"] = clean_span(span)
        eq = r.get("effective_date_quote")
        if eq:
            espan, _ = locate(eq, doc.text)
            rec["effective_date_quote"] = clean_span(espan) if espan else None
        rec["level"] = "state" if rec["jurisdiction"] in ("CA", "NJ", "MA") else "city"
        rec["_cite_key"] = cite_key(rec.get("citation", ""))
        audit.append({"stage": "extract", "doc_id": doc.doc_id, "jurisdiction": rec["jurisdiction"],
                      "category": rec["category"], "citation": rec.get("citation"),
                      "quote_check": how})
        verified.append(rec)

    # merge records that describe the same provision. Within each (jurisdiction, category) the model
    # clusters records by legal provision (different docs cite the same ordinance differently); without
    # an API key we fall back to the normalized citation.
    by_jc = defaultdict(list)
    for r in verified:
        by_jc[(r["jurisdiction"], r["category"])].append(r)
    groups = {}
    agree = []
    for (jur, cat), recs in by_jc.items():
        llm = consolidate(jur, cat, recs)
        if len(recs) > 1:   # deterministic TF-IDF clustering as an independent cross-check
            idx = {id(r): i for i, r in enumerate(recs)}
            agree.append(pairwise_agreement([[idx[id(r)] for r in g] for g in llm], tfidf_clusters(recs)))
        for gi, cluster in enumerate(llm):
            groups[(jur, cat, gi)] = cluster
            if len(cluster) > 1:
                audit.append({"stage": "merge", "jurisdiction": jur, "category": cat,
                              "merged": [f"{c['_doc']}:{c.get('citation')}" for c in cluster]})

    merged = []
    for (jur, cat, _), recs in groups.items():
        def rank(r):
            d = docs_by_id[r["_doc"]]
            return (r["quote_check"] in ("too_short", "not_found"),
                    source_rank(d.source_type), -float(r.get("confidence") or 0))
        recs.sort(key=rank)
        best = dict(recs[0])
        # status: a primary-source failed/pending/enacted signal wins over secondary restatements
        statuses = {r.get("status") for r in recs}
        for s in ("failed", "pending"):
            if s in statuses and best.get("status") not in ("failed", "pending"):
                best["status"] = s if any(r.get("status") == s and source_rank(
                    docs_by_id[r["_doc"]].source_type) <= 1 for r in recs) else best["status"]
        dates = sorted({_date_key(r.get("effective_date")) for r in recs if r.get("effective_date")})
        notes = [r["conflict_note"] for r in recs
                 if r.get("conflict_note") and r.get("conflict_type", "none") != "none"]
        caveats = [r["caveat"] for r in recs if r.get("caveat")]
        if len(dates) > 1:
            notes.append("Sources give different effective dates: " + ", ".join(
                f"{_date_key(r.get('effective_date'))} ({r['_doc']})" for r in recs if r.get("effective_date")))
        # combine coverage flags conservatively (any source asserting a flag keeps it)
        cov = dict(best.get("coverage") or {})
        for r in recs[1:]:
            for k2, v in (r.get("coverage") or {}).items():
                if cov.get(k2) in (None, False) and v not in (None, False):
                    cov[k2] = v
        best["coverage"] = cov
        best["conflict_flag"] = bool(notes)
        best["conflict_note"] = " | ".join(dict.fromkeys(notes)) or None
        best["caveat"] = " | ".join(dict.fromkeys(caveats)) or None
        weights = [source_weight(docs_by_id[r["_doc"]].source_type, r["quote_check"]) for r in recs]
        best["model_confidence"] = float(best.get("confidence") or 0.5)
        best["confidence"], best["evidence_score"] = evidence_confidence(
            best["model_confidence"], weights, caveat=bool(best["caveat"]), conflict=bool(notes))
        best["supporting_docs"] = sorted({r["_doc"] for r in recs})
        # recs are sorted primary-first, so an official / code-publisher capture is always source_doc_id;
        # a provision known only from law-firm or news pages is capped and sent to human review
        best["secondary_only"] = not any(is_primary_source(docs_by_id[r["_doc"]].source_type) for r in recs)
        if best["secondary_only"]:
            best["confidence"] = min(best["confidence"], SECONDARY_ONLY_MAX_CONFIDENCE)
            best["conflict_note"] = " | ".join(filter(None, [best.get("conflict_note"), SECONDARY_ONLY_NOTE]))
        merged.append(best)

    if agree:
        audit.append({"stage": "dedupe_check", "groups": len(agree),
                      "pairwise_f1_mean": round(sum(a[2] for a in agree) / len(agree), 3),
                      "precision_mean": round(sum(a[0] for a in agree) / len(agree), 3),
                      "recall_mean": round(sum(a[1] for a in agree) / len(agree), 3)})

    # stable readable ids
    merged.sort(key=lambda r: (JURISDICTIONS.index(r["jurisdiction"]), CATEGORIES.index(r["category"]),
                               r.get("citation", "")))
    counters = defaultdict(int)
    out = []
    for r in merged:
        prefix = f"{ABBR[r['jurisdiction']]}-{CAT_ABBR[r['category']]}"
        counters[prefix] += 1
        doc = docs_by_id[r["_doc"]]
        cov = r.get("coverage") or {}
        status_raw = r.get("status")
        rec = {
            "team_rule_id": f"{prefix}-{counters[prefix]:02d}",
            "jurisdiction": r["jurisdiction"],
            "level": r["level"],
            "category": r["category"],
            "status": None,  # filled below
            "title": r.get("title", "").strip(),
            "requirement": r.get("requirement", "").strip(),
            "key_value": r.get("key_value"),
            "coverage_conditions": {"summary": r.get("coverage_conditions"), **cov},
            "exemptions": r.get("exemptions"),
            "overrides": [],
            "interaction": None,
            "effective_date": r.get("effective_date") if r.get("effective_date") and re.match(
                r"^\d{4}(-\d{2}(-\d{2})?)?$", str(r.get("effective_date"))) else None,
            "citation": r.get("citation", "").strip(),
            "source_doc_id": doc.doc_id,
            "source_url": doc.url,
            "retrieved_at": doc.retrieved_date,
            "quoted_span": r.get("quoted_span", ""),
            "confidence": round(float(r.get("confidence") or 0.5), 2),
            "conflict_flag": r["conflict_flag"],
            "conflict_note": r["conflict_note"],
            # extra fields (allowed by the schema) used by the app
            "status_raw": status_raw,
            "requirement_es": r.get("requirement_es"),
            "caveat": r.get("caveat"),
            "model_confidence": r.get("model_confidence"),
            "evidence_score": r.get("evidence_score"),
            "secondary_only": r["secondary_only"],
            "penalty": r.get("penalty"),
            "effective_date_quote": r.get("effective_date_quote"),
            "quote_verified": r["quote_check"] not in ("not_found", "too_short"),
            "supporting_docs": r["supporting_docs"],
        }
        rec["status"] = status_on(rec, config.QUERY_DATE)
        if cov.get("may_preempt_local"):
            rec["conflict_flag"] = True
            rec["conflict_note"] = " | ".join(filter(None, [rec["conflict_note"],
                "May preempt local ordinances in the same category once effective; human review needed."]))
        out.append(rec)

    inherit_ordinance_coverage(out)
    for r in out:   # human-review queue: real conflicts and low-confidence rules (brief: "flag conflicts and
        r["needs_review"] = bool(r["conflict_flag"] or r["secondary_only"] or r["confidence"] < LOW_CONFIDENCE)   # low-confidence answers")

    # interactions between levels (recorded in overrides/interaction for transparency)
    for r in out:
        cov = r["coverage_conditions"]
        if r["level"] == "state" and (cov.get("yields_to_local") or cov.get("may_preempt_local")):
            st = r["jurisdiction"]
            locals_ = [x["team_rule_id"] for x in out if x["level"] == "city" and x["category"] == r["category"]
                       and x["jurisdiction"].endswith(", " + st)]
            r["overrides"] = locals_
            r["interaction"] = ("yields to stricter local rule where the local rule covers the unit"
                                if cov.get("yields_to_local") else
                                "may preempt local ordinances once effective (flagged for review)")

    findings = []
    for f in raw_findings:
        doc = docs_by_id[f["_doc"]]
        span, how = locate(f.get("quoted_span", ""), doc.text)
        if span:
            findings.append({"jurisdiction": f.get("jurisdiction"), "category": f.get("category"),
                             "finding": f.get("finding"), "quoted_span": clean_span(span),
                             "source_doc_id": doc.doc_id, "source_url": doc.url})
    return out, findings


def run(force=False, only=None, workers=8):
    from concurrent.futures import ThreadPoolExecutor
    docs = load_docs()
    if only:
        docs = [d for d in docs if d.doc_id in only]
    raw_rules, raw_findings = [], []

    def one(d):
        print(f"[extract] {d.doc_id} ({len(d.text):,} chars)", flush=True)
        return extract_doc(d, force=force)
    with ThreadPoolExecutor(workers) as ex:
        for rr, ff in ex.map(one, docs):      # map keeps document order → deterministic output
            raw_rules += rr
            raw_findings += ff
    return raw_rules, raw_findings, {d.doc_id: d for d in load_docs()}
