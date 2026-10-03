# Strata · method note (one page)

**Question.** For any of 500 apartment buildings: which housing rules apply on a given date, and which supplied
law changes affect it? **Answer shape.** A jurisdiction stack (state → city) of rules, each `applies`,
`superseded`, `unknown`, `not_yet_effective` or `pending`, with a quoted source sentence, URL, retrieval date and
a one-sentence reason naming the building fact used. Not legal advice.

**A · Extraction (automated).** Each of the 69 documents with text (54 in the starter corpus, 15 linked pages fetched one at a time) is read once by Claude (Sonnet 5.5)
through a single schema-typed tool call (documents over 110k characters are chunked with overlap). The prompt
fixes six categories, thirteen jurisdictions, a status vocabulary (drafts, first readings, motions and policy
orders are `pending`; struck or study-ordered measures are `failed`), citation style, and *machine-readable
coverage*: certificate-of-occupancy cutoffs, rolling new-construction exemptions, unit thresholds, small-building
exemptions, owner dependence, and whether a state rule yields to or may preempt local law. A state ban on local rent
control is recorded as a cited *no-rule finding*, not a rule. Raw outputs are cached per document and form the audit
trail.

**Deterministic post-processing.** (1) Every quote is located in the source (exact → normalized with an index map →
fuzzy ≥ 0.85) and replaced by the source's own characters; rules without a locatable quote are rejected and logged.
(2) Records describing the same provision across sources are clustered (citation key, refined by an LLM grouping
call) and merged; the most official source leads; disagreeing effective dates raise a conflict flag. (3) Conflicts
are typed (`effective_date`, `preemption`, `litigation`); other limitations become caveats. (4) A building cutoff
stated on one page of an ordinance is inherited by rules from the same city, category and code chapter.
(5) Status is computed for any query date from the effective date.

**B · Address resolution and coverage.** The Census Geocoder gives the incorporated place; a municipal assessor roll
outranks a geocoder match on a same-named street in another city; NJ rows never use the (owner's) ZIP. Unit counts
come from the record or from what the record encodes (MOD-IV `16U`, class 4C = 5+, Boston class A = 7+), each with
its provenance. The engine tests every rule's coverage per address and date. A cutoff year, a missing year built, a
missing unit count or an owner-dependent exemption yields `unknown`. Where a covering local rule applies, a state
rule that yields becomes `superseded`; where the local coverage is itself unknown, the state rule is `unknown`.

**C · Change tracking.** For T1–T5 the engine is evaluated before and after each test's dates (or at its as-of date)
and affected addresses are those whose result changes or that the measure reaches; possible preemption flags are
raised only where both the state rule and a local rule of the same category reach the address (T3 → Jersey City and
Hoboken only). Any document added with `run.py add-doc` is extracted unaided and reported as T6, T7…, comparing
results with and without it, now and once effective.

**Validation.** `run.py check`: schema 95/95, quotes 95/95 verbatim, 7,535/7,535 `applies` answers backed by a
verified quote, 500/500 addresses resolved, T1–T5 all pass. 19 unit tests cover the quote verifier, coverage edge
cases (cutoff year, rolling exemption, precedence, city boundaries), time logic and record parsing. Spot checks:
SF 1926 → SF ordinance applies, CA §1947.12 superseded; LA 1978 → unknown; Boston/Cambridge → no rent cap (cited);
FAIR Act not yet effective on 2026-10-01, applies 2027-07-02, flagged only in Jersey City and Hoboken; nothing local
in Newark.

**Responsible design.** Citations and dates on every answer; enacted vs pending vs failed; unknown over guessing;
four conflict flags, each a real conflict; confidence and caveats per rule; a stated reasoning boundary; public data
only, no scraping of code publishers; no advice on avoiding rules.

**Scaling.** A new city is a text file and two config lines; prompt, verifier, engine, change tracker and app are
jurisdiction-agnostic. Extraction of the full corpus costs about US$3 and is cached, so reruns and audits are free.
