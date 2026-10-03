"""Fake model outputs used ONLY to test the plumbing (quote repair, merge, engine, changes, app).
They are not used for the submission: real outputs come from `python run.py extract`."""
import json, pathlib
F = pathlib.Path(__file__).parent / "llm"
F.mkdir(exist_ok=True)
def cov(**k):
    base = dict(covered_if_built_on_or_before=None, covered_if_built_after=None, exempt_if_newer_than_years=None,
                min_units=None, max_units=None, exemption_max_units=None, owner_type_dependent=False,
                yields_to_local=False, may_preempt_local=False)
    base.update(k); return base
def R(j, cat, title, req, cite, quote, status="in_force", eff=None, conf=0.9, **c):
    return dict(jurisdiction=j, level="state" if len(j) == 2 else "city", category=cat, status=status, title=title,
                requirement=req, requirement_es="(es) " + req, key_value=None, coverage_conditions=None,
                coverage=cov(**c), exemptions=None, penalty=None, effective_date=eff, effective_date_quote=None,
                citation=cite, quoted_span=quote, confidence=conf, conflict_note=None)
fx = {
 "D024": [R("CA","rent_increase_limits","Tenant Protection Act rent cap","Rent can rise at most 5% plus inflation, max 10%, per year.","Cal. Civ. Code § 1947.12",
   "an owner of residential real property shall not, over the course of any 12-month period, increase the gross rental rate for a dwelling or a unit more than 5 percent plus the percentage change in the cost of living, or 10 percent, whichever is lower",
   exempt_if_newer_than_years=15, yields_to_local=True)],
 "D022": [R("CA","algorithmic_rent_setting","Cartwright Act: common pricing algorithms","Using a common pricing algorithm to restrain trade is unlawful.","Cal. Bus. & Prof. Code § 16729",
   "It shall be unlawful for a person to use or distribute a common pricing algorithm as part of a contract,  combination in the form of a trust",  # whitespace drift on purpose
   eff="2026-01-01")],
 "D069": [R("NJ","algorithmic_rent_setting","FAIR Act","Bans algorithmic rent-setting using competitors' data.","P.L.2026, c.43",
   "A municipality shall be prohibited from enacting an ordinance that conflicts with this act.", eff="2027-07-01", status="not_yet_effective", may_preempt_local=True)],
 "D046": [R("MA","algorithmic_rent_setting","S.2983 algorithmic rent setting ban (bill)","Would ban algorithmic rent setting if passed.","Mass. S.2983","An Act prohibiting algorithmic rent setting", status="pending")],
 "D045": [R("MA","algorithmic_rent_setting","H.5222 algorithmic rent fixing (bill)","Would ban algorithmic rent fixing if passed.","Mass. H.5222","An Act relative to preventing algorithmic rent fixing in the rental housing market", status="pending")],
 "D041": [R("Los Angeles, CA","rent_increase_limits","Rent Stabilization Ordinance","Covered units get capped annual increases.","L.A.M.C. § 151.00",
   "Generally, the RSO applies to rental properties that were first built on or before October 1, 1978", covered_if_built_on_or_before="1978-10-01")],
 "D025": [R("CA","security_deposits","Security deposit cap","A deposit may not exceed one month's rent.","Cal. Civ. Code § 1950.5",
   "a landlord shall not demand or receive security, however denominated, in an amount or value in excess of an amount equal to one month’s rent", eff="2024-07-01", exemption_max_units=4)],
 "FX_HOB": [R("Hoboken, NJ","algorithmic_rent_setting","FIXTURE Hoboken ban","fixture","Hoboken Code ch. 158","It shall be unlawful for any landlord in the City of Hoboken to use an algorithmic device to set rent.")],
 "FX_JC": [R("Jersey City, NJ","algorithmic_rent_setting","FIXTURE JC ban","fixture","Jersey City Code § 218-12","No landlord in Jersey City shall use algorithmic rent-setting software to determine rents.")],
}
findings = {"D048": [dict(jurisdiction="Boston, MA", category="rent_increase_limits", finding="State law bars local rent control.",
                          quoted_span="No city or town may enact, maintain or enforce rent control of any kind")]}
for d, rules in fx.items():
    (F / f"{d}.json").write_text(json.dumps({"rules": rules, "no_rule_findings": findings.get(d, [])}, indent=1))
for d, ff in findings.items():
    if d not in fx:
        (F / f"{d}.json").write_text(json.dumps({"rules": [], "no_rule_findings": ff}, indent=1))
print("fixtures written:", sorted(p.name for p in F.glob("*.json")))
