"""Sweep-line temporal engine: the dates on which an address's answer can change.

Rule results are piecewise constant in time. They can only change at (a) an effective date and (b) the
year boundaries of a rolling new-construction exemption (built Y, exempt for N years → boundaries at
Jan 1 of Y+N and Y+N+1, because the engine compares calendar years). Sweeping those candidate points
and evaluating once per segment gives the exact timeline for any date, at O(k · rules) per address,
instead of evaluating every day.
"""
from .engine import evaluate
from .extract import _date_key


def candidate_points(prop, rules, start, end):
    pts = set()
    for r in rules:
        d = _date_key(r.get("effective_date"))
        if d and start < d <= end:
            pts.add(d)
        n = (r.get("coverage_conditions") or {}).get("exempt_if_newer_than_years")
        if n and prop.get("year_built"):
            for y in (prop["year_built"] + int(n), prop["year_built"] + int(n) + 1):
                d = f"{y}-01-01"
                if start < d <= end:
                    pts.add(d)
    return sorted(pts)


def _signature(entries):
    return tuple(sorted((e["team_rule_id"], e["result"]) for e in entries))


def address_timeline(prop, rules, start="2024-01-01", end="2030-12-31"):
    """[(date, {rule_id: result})] — the answer at `start` and every date it changes, up to `end`."""
    out, last = [], None
    for d in [start] + candidate_points(prop, rules, start, end):
        entries = evaluate(prop, rules, d)
        sig = _signature(entries)
        if sig != last:
            out.append((d, dict(sig)))
            last = sig
    return out


def change_dates(props, rules, start="2024-01-01", end="2030-12-31"):
    """{address_id: [dates where the answer changes]} (the first entry is `start`, omitted)."""
    return {p["address_id"]: [d for d, _ in address_timeline(p, rules, start, end)[1:]] for p in props}
