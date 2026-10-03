# Requirements traceability

Every requirement in the RealPage challenge brief and the v5 participant guide, and where Strata meets it.
Numbers come from `python run.py check` / `score` on this commit.

## Required modules

| Requirement (brief / guide) | Strata | Evidence |
|---|---|---|
| **A** · Read each corpus document; one structured record per rule; **automated, not hand-coded** | Claude reads all 69 documents via one schema-typed tool call each; no rule is written by hand | `nav/extract.py`, `cache/llm/` (raw outputs), `run.py extract` |
| A · Capture category, jurisdiction, requirement, coverage conditions, exemptions, effective date, status (enacted/pending), penalty, citation, quoted span | All fields in every record; coverage is machine-readable | `out/rules.json` (95/95 schema-valid) |
| **B** · Resolve each address to its legal jurisdiction stack | Census Geocoder place + municipal-roll arbitration; state → city stack in the app | `nav/properties.py`, 500/500 resolved |
| B · Report every applicable rule | 9,234 rule × address answers for all 500 addresses | `out/lookups.json` |
| B · Where a local rule overrides a state rule, say so | `superseded` with the overriding rule named | e.g. A0016: CA-RENT-01 superseded by SF-RENT-01 |
| B · If coverage depends on a missing fact, say **unknown**, not guess | 806 `unknown` answers, each naming the missing fact | engine explanations; value-of-information ranking |
| **C** · Run the change cases; list affected addresses | T1–T5 all match their expected sets | `out/changes.json`, self-check |
| C · Before/after rule set per address | Per test and address | `out/changes_detail.json` |
| C · Support an as-of-date query | Any date in the app's date picker and in Ask Strata questions (in-browser engine, parity-tested); exact change dates per building | date picker, `nav/temporal.py`, `tests/e2e_engine_parity.py` |
| T3 · Flag possible conflict with local bans | 90 flags, exactly Jersey City + Hoboken | self-check T3 |

## Stretch goals

| Stretch goal | Strata |
|---|---|
| Renter-facing plain-language view in English and Spanish | Rights card per address; full EN/ES UI; Spanish requirement on every rule |
| Confidence score and conflict flag for each answer | Evidence-weighted confidence (noisy-OR) per rule; typed conflict flags; human-review queue |
| Extend to one new jurisdiction | `run.py add-doc` + two config lines; nothing city-specific is hard-coded |
| Audit view: source, retrieval date, as-of date, reasoning boundary | Every rule row and the Sources & audit page |

## Submission package

| Item | Where |
|---|---|
| `rules.json`, `lookups.json`, `changes.json` (template formats) | `out/` |
| GitHub repository with README explaining how to run it | this repository, `README.md`, `Makefile` |
| Live demo link | https://teeraphat2543inta.github.io/strata-rental-law-navigator/ |
| One-page method note | `METHOD_NOTE.md` |
| Three videos with scores on screen | team intro · product demo · technical walkthrough (self-check and self-score shown; the organizers confirmed score.py and the dev key are not shared) |

## Responsible design (the solution should / must not)

| Brief | Strata |
|---|---|
| Cite source text and retrieval date for every rule | quote + URL + retrieved date on every rule and answer |
| Show an as-of date; separate enacted from pending | as-of on every answer; in force / not yet effective / pending / failed kept apart |
| Say unknown when facts are missing | 806 unknowns, each with the missing fact |
| Flag conflicts **and low-confidence answers** for human review | `needs_review` on 19 rules (4 typed conflicts, 15 secondary-source-only capped at 0.6, plus any below 60%); review queue in the app |
| Prefer official text over restatements | official / code-publisher capture is always primary; secondary pages are supporting only (80/95 official-primary) |
| Explain rules in plain language a renter can act on | plain-language requirement per rule; rights card |
| Keep an auditable log of sources, model outputs and changes | `out/audit_log.jsonl`, `cache/llm/`, git history |
| Must not present output as legal advice | "Not legal advice" on every screen |
| Must not suggest ways around a rule | the app and assistant only explain; no avoidance content |
| Must not invent rules or citations | rules without a verbatim quote are rejected (1 rejected) |
| Must not use non-public data | public corpus, public assessor data, Census Geocoder only |
| Must not scrape against terms | linked pages fetched one at a time with the organizers' permission (2026-10-04) |

## Organizer clarifications applied (Discord, 2026-10-04)

* v5 clean pack is current (identical content, verified with `diff -r`); T1–T5 only, no hour-16 ordinance.
* score.py and dev key are not shared → `run.py check` and `run.py score` are the score evidence.
* Individual pages in `links_only.csv` may be fetched → `fetch-links --include-publishers`, retrieval dates recorded.
