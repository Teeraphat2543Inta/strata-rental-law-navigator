"""Unit tests for the deterministic layer (no network, no API key):  python -m unittest discover tests"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from nav.engine import _check_coverage, evaluate  # noqa: E402
from nav.extract import _date_key, _ordinance_key, inherit_ordinance_coverage, status_on  # noqa: E402
from nav.properties import units_from_record  # noqa: E402
from nav.quotes import locate  # noqa: E402
from nav.confidence import evidence_confidence, noisy_or, source_weight  # noqa: E402
from nav.dedupe import clusters, pairwise_agreement  # noqa: E402
from nav.temporal import address_timeline, candidate_points  # noqa: E402
from nav.voi import missing_fact, rank  # noqa: E402


def prop(**kw):
    base = {"address_id": "X1", "state": "CA", "city": "San Francisco", "jurisdiction": "San Francisco, CA",
            "year_built": 1950, "units_min": 10, "units_max": 10, "jurisdiction_confidence": 1.0,
            "jurisdiction_method": "census_geocoder", "data_flags": []}
    base.update(kw)
    return base


def rule(rid, jur="San Francisco, CA", level="city", cat="rent_increase_limits", **cov):
    return {"team_rule_id": rid, "jurisdiction": jur, "level": level, "category": cat, "status_raw": "in_force",
            "effective_date": None, "citation": "S.F. Admin. Code ch. 37", "conflict_flag": False,
            "conflict_note": None, "quote_verified": True, "coverage_conditions": cov}


class QuoteVerification(unittest.TestCase):
    SRC = "Section 1.\nRent may be increased once every 12 months\nby the allowable percentage.  Other text."

    def test_exact(self):
        self.assertEqual(locate("Other text.", self.SRC)[1], "exact")

    def test_whitespace_and_line_breaks_are_normalized(self):
        span, how = locate("increased once every 12 months by the allowable percentage", self.SRC)
        self.assertEqual(how, "normalized")
        self.assertIn("\n", span)               # the returned span is the source's own text, line break included

    def test_invented_quote_is_rejected(self):
        self.assertEqual(locate("Rent may never be increased under any circumstances at all", self.SRC),
                         (None, "not_found"))

    def test_too_short(self):
        self.assertEqual(locate("Rent", self.SRC)[1], "too_short")


class CoverageEngine(unittest.TestCase):
    sf_rent = rule("SF-RENT-01", covered_if_built_on_or_before="1979-06-13")

    def test_cutoff_year_is_unknown_not_a_guess(self):
        self.assertEqual(_check_coverage(self.sf_rent, prop(year_built=1979), "2026-10-01")[0], "unknown")

    def test_before_and_after_cutoff(self):
        self.assertEqual(_check_coverage(self.sf_rent, prop(year_built=1962), "2026-10-01")[0], "covered")
        self.assertEqual(_check_coverage(self.sf_rent, prop(year_built=1990), "2026-10-01")[0], "not_covered")

    def test_missing_year_is_unknown(self):
        self.assertEqual(_check_coverage(self.sf_rent, prop(year_built=None), "2026-10-01")[0], "unknown")

    def test_rolling_new_construction_exemption(self):
        r = rule("CA-RENT-01", "CA", "state", exempt_if_newer_than_years=15)
        self.assertEqual(_check_coverage(r, prop(year_built=2020), "2026-10-01")[0], "not_covered")
        self.assertEqual(_check_coverage(r, prop(year_built=2000), "2026-10-01")[0], "covered")

    def test_state_cap_yields_to_local_rent_control(self):
        state = rule("CA-RENT-01", "CA", "state", yields_to_local=True)
        res = {e["team_rule_id"]: e["result"] for e in evaluate(prop(year_built=1962), [state, self.sf_rent],
                                                                   "2026-10-01")}
        self.assertEqual(res, {"SF-RENT-01": "applies", "CA-RENT-01": "superseded"})

    def test_state_cap_unknown_when_local_coverage_unknown(self):
        state = rule("CA-RENT-01", "CA", "state", yields_to_local=True)
        res = {e["team_rule_id"]: e["result"] for e in evaluate(prop(year_built=1979), [state, self.sf_rent],
                                                                   "2026-10-01")}
        self.assertEqual(res, {"SF-RENT-01": "unknown", "CA-RENT-01": "unknown"})

    def test_city_rule_never_leaks_to_another_city(self):
        hob = rule("HOB-ALG-01", "Hoboken, NJ", cat="algorithmic_rent_setting")
        newark = prop(state="NJ", city="Newark", jurisdiction="Newark, NJ")
        self.assertEqual(evaluate(newark, [hob], "2026-10-01"), [])


class Time(unittest.TestCase):
    def test_partial_dates(self):
        self.assertEqual(_date_key("2027-07"), "2027-07-01")
        self.assertEqual(_date_key("2026"), "2026-01-01")

    def test_status_is_computed_for_the_query_date(self):
        r = {"status_raw": "in_force", "effective_date": "2027-07-01"}
        self.assertEqual(status_on(r, "2026-10-01"), "not_yet_effective")
        self.assertEqual(status_on(r, "2027-07-02"), "in_force")

    def test_pending_and_failed_never_become_law(self):
        for raw in ("pending", "failed"):
            self.assertEqual(status_on({"status_raw": raw, "effective_date": "2020-01-01"}, "2030-01-01"), raw)


class BuildingFacts(unittest.TestCase):
    def test_nj_unit_count_hidden_in_building_description(self):
        row = {"units": "", "use_description": "4S-B-A-16U-H", "source_dataset": "NJOGIS Parcels & MOD-IV Composite"}
        self.assertEqual(units_from_record(row)[:2], (16, 16))

    def test_boston_apartment_class(self):
        row = {"units": "", "use_description": "", "use_code": "A/112", "source_dataset": "Boston property assessment"}
        self.assertEqual(units_from_record(row)[:2], (7, None))

    def test_missing_units_stay_missing(self):
        self.assertEqual(units_from_record({"units": "", "use_description": "", "source_dataset": "x"})[:2],
                         (None, None))


class OrdinanceCoverageInheritance(unittest.TestCase):
    def test_keys(self):
        self.assertEqual(_ordinance_key("L.A.M.C. § 151.00"), "151")
        self.assertEqual(_ordinance_key("B.M.C. § 13.76.110"), "13")
        self.assertEqual(_ordinance_key("S.F. Admin. Code ch. 37"), "37")

    def test_cutoff_is_inherited_within_one_ordinance_only(self):
        donor = rule("LA-RENT-01", "Los Angeles, CA", covered_if_built_on_or_before="1978-10-01")
        donor["citation"] = "L.A.M.C. § 151.00"
        same = rule("LA-RENT-02", "Los Angeles, CA")
        same["citation"] = "L.A.M.C. § 151.06"
        other = rule("LA-RENT-03", "Los Angeles, CA")
        other["citation"] = "L.A.M.C. § 165.01"
        inherit_ordinance_coverage([donor, same, other])
        self.assertEqual(same["coverage_conditions"]["covered_if_built_on_or_before"], "1978-10-01")
        self.assertIn("inherited from LA-RENT-01", same["caveat"])
        self.assertIsNone(other["coverage_conditions"].get("covered_if_built_on_or_before"))


class Algorithms(unittest.TestCase):
    def test_sweep_line_finds_effective_dates_and_rolling_boundaries(self):
        fair = rule("NJ-ALG-01", "NJ", "state", cat="algorithmic_rent_setting")
        fair["effective_date"] = "2027-07-01"
        roll = rule("CA-RENT-01", "CA", "state", exempt_if_newer_than_years=15)
        nj = prop(state="NJ", city="Newark", jurisdiction="Newark, NJ", year_built=2012)
        self.assertEqual(candidate_points(nj, [fair, roll], "2024-01-01", "2030-12-31"),
                         ["2027-01-01", "2027-07-01", "2028-01-01"])
        tl = address_timeline(nj, [fair], "2024-01-01", "2030-12-31")
        self.assertEqual([d for d, _ in tl], ["2024-01-01", "2027-07-01"])
        self.assertEqual(tl[1][1], {"NJ-ALG-01": "applies"})

    def test_noisy_or_rewards_independent_corroboration(self):
        one = noisy_or([source_weight("fetched: secondary")])
        two = noisy_or([source_weight("fetched: secondary"), source_weight("official")])
        self.assertGreater(two, one)
        self.assertAlmostEqual(noisy_or([0.9, 0.5]), 0.95)
        self.assertLess(evidence_confidence(0.9, [0.9], conflict=True)[0], evidence_confidence(0.9, [0.9])[0])

    def test_fuzzy_quote_is_discounted(self):
        self.assertLess(source_weight("official", "fuzzy:0.86"), source_weight("official", "exact"))

    def test_tfidf_clusters_and_agreement(self):
        recs = [{"title": "Security deposit cap", "requirement": "deposit may not exceed one month rent",
                 "citation": "Cal. Civ. Code 1950.5", "_cite_key": "a"},
                {"title": "Deposit limit", "requirement": "a deposit may not exceed one month rent",
                 "citation": "Civ. Code 1950.5", "_cite_key": "b"},
                {"title": "Algorithmic pricing ban", "requirement": "no coordinated pricing software",
                 "citation": "S.F. 37.10C", "_cite_key": "c"}]
        got = sorted(sorted(g) for g in clusters(recs))
        self.assertEqual(got, [[0, 1], [2]])
        self.assertEqual(pairwise_agreement([[0, 1], [2]], got), (1.0, 1.0, 1.0))

    def test_value_of_information_ranks_missing_facts(self):
        self.assertEqual(missing_fact("Built 1979, the cutoff year — depends on the exact certificate"),
                         "certificate-of-occupancy date")
        props = [prop(address_id="X1"), prop(address_id="X2")]
        lk = {"X1": [{"result": "unknown", "explanation": "covers ...; year built is not in the public record"}],
              "X2": [{"result": "unknown", "explanation": "rule covers 5+ units; unit count not in the record"},
                     {"result": "unknown", "explanation": "year built is not in the public record"}]}
        top = rank(props, lk)[0]
        self.assertEqual((top["fact"], top["answers"], top["buildings"]), ("year built", 2, 2))


if __name__ == "__main__":
    unittest.main()
