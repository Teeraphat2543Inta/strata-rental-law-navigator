PY ?= python3
STARTER_PACK ?= ../pack_raw/participant-final-no-hour16 3

.PHONY: setup geocode fetch extract build check score test all serve clean-out

setup:            ## link the organizers' starter pack (not redistributed)
	@[ -e starter_pack ] || ln -s "$(STARTER_PACK)" starter_pack
	@test -f starter_pack/corpus/corpus_manifest.csv && echo "starter pack OK"

geocode:          ## Census Geocoder → cache/geocode
	$(PY) run.py geocode

fetch:            ## read link-only sources, one request per page
	$(PY) run.py fetch-links --include-publishers

extract:          ## Module A (needs ANTHROPIC_API_KEY; cached)
	$(PY) run.py extract

build:            ## Modules B + C → out/ and docs/index.html
	$(PY) run.py build

check:            ## PASS/FAIL report
	$(PY) run.py check

score:            ## self-score per auto-scored component
	$(PY) run.py score

test:             ## unit tests (no key, no network)
	$(PY) -m unittest discover -s tests -p "test_units.py" -v

all: geocode extract build check score

serve:            ## open the app on http://localhost:8000
	cd docs && $(PY) -m http.server 8000
