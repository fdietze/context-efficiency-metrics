"""Probability of a cache miss versus the pause before the call, one panel per provider.

Providers expire caches differently (Anthropic: hard 5-minute TTL by default, 1 hour with
long retention; OpenAI: gradual eviction), so pooling them would mix two curves into a
misleading third one (Simpson's paradox).
"""
import bisect
from collections import defaultdict

from calls import Call

# Bin edges in seconds, finer around the 5-minute and 1-hour TTLs.
EDGES = (30, 60, 120, 240, 300, 360, 600, 1800, 3600, 7200, 86400)
TTL_RULES = (300, 3600)


def _label(i: int) -> str:
    def h(s):
        return f"{s // 3600}h" if s >= 3600 and s % 3600 == 0 else f"{s // 60}m" if s >= 60 else f"{s}s"
    lo = h(EDGES[i - 1]) if i else "0"
    return f"{lo}-{h(EDGES[i])}" if i < len(EDGES) else f">{lo}"


def miss_vs_gap_data(calls: list[Call]) -> list[dict]:
    """Calls with a known gap to their previous main-chain call (cache_warm pings included:
    they are on the chain too). A miss is any call with miss_cost > 0."""
    n, miss = defaultdict(int), defaultdict(int)
    for c in calls:
        if c.gap is None:
            continue
        key = (c.model.split("/")[0], bisect.bisect_right(EDGES, c.gap))
        n[key] += 1
        miss[key] += c.miss_cost > 0
    rows = []
    for (provider, i), k in sorted(n.items()):
        lo = EDGES[i - 1] if i else 1  # log axis: plot the first bin from 1 s
        hi = EDGES[i] if i < len(EDGES) else EDGES[-1] * 7
        rows.append({"provider": provider, "bin": _label(i), "lo": lo, "hi": hi,
                     "mid": (lo * hi) ** 0.5, "calls": k, "p": miss[(provider, i)] / k})
    return rows


def miss_vs_gap_spec(rows: list[dict]) -> dict:
    x = {"type": "quantitative", "scale": {"type": "log"}, "title": "pause before the call (seconds)"}
    return {
        "title": {"text": "Cache-miss probability vs pause",
                  "subtitle": "One panel per provider. Rules at 5 min and 1 h (Anthropic cache TTLs). "
                              "Point size: calls in the bin."},
        "data": {"values": rows},
        "facet": {"row": {"field": "provider", "type": "nominal", "title": None}},
        "spec": {
            "width": 640, "height": 160,
            "layer": [
                # Constant rules via `datum`: layers inside a facet cannot carry their own data.
                *({"mark": {"type": "rule", "color": "gray", "strokeDash": [4, 3]},
                   "encoding": {"x": {"datum": t, **x}}} for t in TTL_RULES),
                {"mark": {"type": "line", "point": False, "color": "#4c78a8"},
                 "encoding": {"x": {"field": "mid", **x}, "y": {"field": "p", "type": "quantitative"}}},
                {"mark": {"type": "point", "filled": True, "color": "#4c78a8"},
                 "encoding": {"x": {"field": "mid", **x},
                              "y": {"field": "p", "type": "quantitative", "title": "P(miss)",
                                    "axis": {"format": "%"}, "scale": {"domain": [0, 1]}},
                              "size": {"field": "calls", "type": "quantitative", "scale": {"type": "sqrt"},
                                       "legend": None},
                              "tooltip": [{"field": "bin"}, {"field": "p", "format": ".1%", "title": "P(miss)"},
                                          {"field": "calls"}]}},
            ],
        },
        "resolve": {"scale": {"size": "shared"}},
    }
