# Strata · Rental Housing Law Navigator

**Housing law for one front door, layer by layer.**
Hack-Nation 7th Global AI Hackathon · Challenge 02 (RealPage) · team Thai_win

For each of 500 apartment buildings, Strata answers *which housing rules apply here today, and what is about to
change?* Every answer quotes the exact sentence of law it rests on, with the source URL, the retrieval date and the
as-of date. **Not legal advice.**

**Live demo:** https://teeraphat2543inta.github.io/strata-rental-law-navigator/ (one static file, no server, works offline)

| | |
|---|---|
| Rules extracted (automated, from 69 documents) | **95** (84 in force · 1 not yet effective · 7 pending · 3 failed) |
| Quotes found verbatim in the cited source | **95 / 95** |
| "Applies" answers backed by a verified quote | **7,535 / 7,535** |
| Addresses answered · legal jurisdiction resolved | **500 / 500 · 500 / 500** |
| Change tests T1–T5 (affected sets + T3 conflict flags) | **all pass** |
| Conflict flags raised | **4** — each a real conflict (preemption, disputed effective date) |

`python run.py check` and `python run.py score` reproduce every number above (`out/selfcheck.txt`, `out/score_self.txt`).

---

## What makes this hard, and what Strata does about it

| The trap in the data or the law | What Strata does |
|---|---|
| **The postal city is not the legal city.** 39 of 500 rows carry a neighborhood or another city's name ("Dorchester", "Allston"). | The U.S. Census Geocoder decides the incorporated place. Method and confidence travel with every answer. |
| **Same street name, two cities.** "322 Western Ave" exists in Cambridge *and* Allston (Boston); the geocoder picks Boston. | A municipal assessor roll only lists parcels inside its city, so the roll outranks the geocoder when they disagree, and the app says why. |
| **New Jersey ZIPs are the owner's mailing ZIP** (Brooklyn, Austin…). | NJ is never geocoded by ZIP; the taxing municipality is used and the row is flagged (27 rows). |
| **Unit counts are missing** for Jersey City, Newark, Hoboken, Berkeley, Boston. | Read from what the public record does say: MOD-IV building codes (`4S-B-A-16U-H` = 16 units), NJ class 4C (5+), Boston class A (7+), assessor use classes. The method is shown next to the number. |
| **Year built ≠ certificate of occupancy.** SF covers CO on or before 1979-06-13, LA on or before 1978-10-01. | A building built in the cutoff year is `unknown`, never a guess, and the state cap that would yield to it becomes `unknown` too. |
| **One ordinance, many pages.** A city page announces "this year's increase is 3%" without repeating which buildings the ordinance covers. | Rules from the same city, category and code chapter inherit the ordinance's building cutoff, with a caveat naming the donor rule. Without this, the 3% cap would silently reach a 2012 building. |
| **A ban on rent control is not a rent cap.** M.G.L. c. 40P bars local rent control in Massachusetts. | Recorded as a cited *no-rule finding* ("no rent cap: state law bars local rent control"), so Boston and Cambridge show a confirmed absence instead of a rule. T5 passes by construction. |
| **Proposals look like laws.** Draft ordinances, first readings, council motions, policy orders, bills sent to study. | All are `pending` or `failed`, never `in_force`. 7 pending, 3 failed in this build. |
| **Statutes don't always print their effective date.** AB 325 was chaptered on 6 Oct 2025. | The California constitutional default (art. IV § 8(c): regular-session statutes take effect 1 January of the next year) is applied only when the document shows the chaptered date, and that line is quoted. |
| **The model can invent.** | Every quoted span is located in the source text (exact → whitespace-normalized → fuzzy ≥ 0.85) and replaced by the source's own characters. A rule whose quote is not in its source is **not published**; it goes to the audit log as `rejected`. |
| **"Conflict" can mean anything.** | The model must classify: `effective_date`, `preemption`, `litigation`, or none. Secondary sources, approximate cites and yearly-adjusted figures are *caveats*, shown in the UI, never flags. Flags dropped from 60 to 4 when this was introduced. |

## Architecture

```
 corpus/*.txt ─► [A] extract ─► verify quote ─► merge + conflict detector ─► inherit ordinance coverage ─► rules.json
                 Claude, one    exact/normalized/  same provision from many     building cutoffs shared
                 schema-typed   fuzzy; else        sources; dates that          within one code chapter
                 tool call per  rejected           disagree raise a flag
                 document,
                 cached
 sample_addresses ─► [B] building facts ─► jurisdiction ─► coverage engine ─────────────────────────────────► lookups.json
                     units from MOD-IV    Census place;     CO cutoffs, rolling new-construction exemptions,
                     codes / use classes  roll beats a      unit thresholds, small-building exemptions,
                     (with provenance)    same-name street  owner-dependence → unknown, state yields to local
 change_tests ─────► [C] as-of diff engine ─► changes.json (T1–T5; T6+ for every document added with add-doc)
                                          └─► out/index.html = docs/index.html (the app: EN/ES, 4 as-of dates)
```

| Module | File | What it does |
|---|---|---|
| A | `nav/extract.py` | Prompt, tool schema, per-document extraction (chunked above 110k chars), quote verification, LLM-assisted clustering of duplicate provisions, conflict detection, ordinance coverage inheritance, stable rule IDs (`SF-RENT-01`). |
| A | `nav/quotes.py` | Quote locator: exact, whitespace/typography-normalized with an index map back to the source, then bounded fuzzy matching. |
| B | `nav/geocode.py`, `nav/properties.py` | Census Geocoder (cached), legal-city resolution with method + confidence, building facts with provenance. |
| B | `nav/engine.py` | Coverage tests per rule × address × date, precedence (state yields to local, possible preemption flags). |
| C | `nav/changes.py` | T1–T5 from `dev/change_tests.json`; any added document becomes T6, T7… with before/after rule sets. |
| — | `nav/build.py`, `app/index.template.html` | Submission files and the self-contained app. |
| — | `nav/selfcheck.py`, `nav/score.py` | Pass/fail checks and a per-component self-score. |

## Run it

Python 3.9+, standard library only (`pip install jsonschema` adds strict schema validation).

```bash
ln -s "/path/to/participant-final-no-hour16 3" starter_pack     # the RealPage starter pack (not redistributed)
export ANTHROPIC_API_KEY=...                                    # extraction only; everything else is offline
export ANTHROPIC_MODEL=claude-sonnet-5-5                        # default

python run.py geocode        # Census Geocoder → cache/geocode
python run.py fetch-links    # optional: read link-only sources (one request per page; add --include-publishers for code-publisher pages)
python run.py extract        # Module A over the whole corpus (~US$3, ~15 min; cached → reruns are free)
python run.py build          # Modules B + C → out/*.json + out/index.html + docs/index.html
python run.py check          # PASS/FAIL report + coverage grid
python run.py score          # self-score per auto-scored component

# a new ordinance or a new city's law arrives: extracted unaided, rebuilt, reported as the next change test
python run.py add-doc new_ordinance.txt --id D088 --jurisdiction "Cambridge, MA" --url "<source url>"
```

Tests: `python -m unittest discover -s tests -p "test_units.py"` (19 unit tests, no key, no network) and
`python tests/test_pipeline.py` (end-to-end with recorded model outputs; needs the starter pack).

## Outputs (`out/`)

| File | Contents |
|---|---|
| `rules.json` | Submission format: one record per rule with citation, quoted span, source URL, retrieval date, effective date, status, coverage, confidence, conflict flag. Extra fields: Spanish requirement, caveat, supporting documents, `quote_verified`. |
| `lookups.json` | All 500 addresses × every rule that reaches them on 2026-10-01: `applies`, `superseded`, `unknown`, `not_yet_effective`, `pending`, each with a plain-language explanation naming the building fact it rests on. |
| `changes.json` | Affected addresses and conflict flags per change test. `changes_detail.json` adds the before/after rule set per address. |
| `no_rule_findings.json` | Cited statements that no rule exists at a level (e.g. no rent cap in Boston). |
| `properties.json` | Every building fact with its provenance and data-quality flags. |
| `audit_log.jsonl` | Every extraction, quote check, merge and rejection. `cache/llm/` holds the raw model output for every document: the audit trail of what the model said. |

## Data

* **Corpus:** the 54 starter-pack documents with text, plus 15 link-only sources fetched individually (69 documents). The
  organizers confirmed on 2026-10-04 that individual pages listed in `links_only.csv` may be fetched (one request per
  page, retrieval date recorded, no bulk scraping); `run.py fetch-links --include-publishers` does exactly that,
  1.5 s apart. Pages that refused (403) or returned no law text are listed in the app as unread and never cited.
* **Addresses:** the 500 sample properties (public assessor data, no owner names), resolved with the free U.S.
  Census Geocoder.
* No customer, resident, pricing or other non-public data is used.

## Responsible design

Source sentence, URL, retrieval date and as-of date on every answer · enacted, not-yet-effective, pending and failed
kept apart · `unknown` whenever a needed fact is missing, with the missing fact named · conflict flags only for real
conflicts, caveats shown separately · confidence per rule · a written reasoning boundary on every answer (what was
checked, what was not) · public data only, one polite request per linked page, nothing scraped in bulk · the app explains rules and never
suggests ways around them · "Not legal advice" on every screen.

## Adding a jurisdiction

1. Put the ordinance or statute text in `extra_docs/` (or `run.py add-doc`).
2. Add the city to `JURISDICTIONS` (`nav/extract.py`) and `CITIES` (`nav/properties.py`); if its assessor roll is a
   municipal roll, add it to `MUNICIPAL_ROLLS`.
3. `python run.py extract && python run.py build`. The prompt, quote verifier, coverage engine, change tracker and
   app are jurisdiction-agnostic; nothing about a city is hard-coded.

## Limitations

The model can misread a coverage condition; the quote on every rule and the self-check make such errors visible,
not impossible. Exact certificate-of-occupancy dates and owner identity are not in the data, so the answers that
depend on them stay `unknown`. Link-only sources that could not be fetched are listed in the app and not used.

## License

Code: MIT. Law text belongs to its public sources (URLs and retrieval dates in `out/rules.json`). The organizers'
starter pack is not redistributed.
