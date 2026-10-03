"""Value of information: which missing building fact, if collected, would settle the most answers?

Every `unknown` answer names the fact it depends on (the engine writes it into the explanation). Group
unknown answers by (fact, city) and rank by the number of answers — and buildings — that become
determinate once that fact is known, whatever its value. This turns uncertainty into a data-collection
plan for an agency or a housing provider.
"""
from collections import defaultdict

FACTS = [
    ("certificate-of-occupancy date", ("the cutoff year", "exactly at the")),
    ("year built", ("year built is not in the public record", "year built unknown")),
    ("unit count", ("unit count not in the record", "unit count unknown")),
    ("owner identity / owner-occupancy", ("owner facts not in the data", "owner's identity")),
    ("local coverage of the city ordinance", ("that coverage is itself unknown",)),
]


def missing_fact(explanation):
    for fact, needles in FACTS:
        if any(n in explanation for n in needles):
            return fact
    return "other"


def rank(props, lookups):
    agg = defaultdict(lambda: {"answers": 0, "buildings": set()})
    for p in props:
        for e in lookups[p["address_id"]]:
            if e["result"] != "unknown":
                continue
            k = (missing_fact(e["explanation"]), p["jurisdiction"])
            agg[k]["answers"] += 1
            agg[k]["buildings"].add(p["address_id"])
    out = [{"fact": f, "city": c, "answers": v["answers"], "buildings": len(v["buildings"])}
           for (f, c), v in agg.items()]
    return sorted(out, key=lambda x: (-x["answers"], -x["buildings"], x["city"] or ""))
