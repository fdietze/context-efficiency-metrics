"""Forest plot: total$ per million visible output tokens per model and effort, with a
90% Bayesian bootstrap interval over session trees.

Observational data: groups differ in task mix, so intervals show sampling noise only,
not the causal effect of a model or effort.
"""
from collections import defaultdict

from bayesian_bootstrap import ratio_interval
from calls import Call

MIN_TREES = 10  # below this, the interval is shown faded: too few independent sessions


def forest_data(calls: list[Call]) -> list[dict]:
    # Pre-aggregate (num, den) per (group, tree) so each bootstrap draw is O(trees).
    per = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    for c in calls:
        if c.kind != "assistant" or c.reasoning is None:
            continue
        u = per[(c.model, c.effort)][c.tree]
        u[0] += c.cost["total"]
        u[1] += c.tokens["output"] - c.reasoning
    rows = []
    for (model, effort), trees in per.items():
        # Some providers report reasoning > output; clamp like table.py does per group.
        units = [(n, max(0.0, d)) for n, d in trees.values()]
        q = ratio_interval(units)
        if q is None:
            continue
        rows.append({"group": f"{model} @ {effort}", "model": model, "effort": effort,
                     "lo": q[0] * 1e6, "mid": q[1] * 1e6, "hi": q[2] * 1e6,
                     "trees": len(trees), "few": len(trees) < MIN_TREES})
    return sorted(rows, key=lambda r: r["mid"])


def forest_spec(rows: list[dict]) -> dict:
    enc_y = {"field": "group", "type": "nominal", "sort": None, "title": None}
    opacity = {"condition": {"test": "datum.few", "value": 0.35}, "value": 1}
    x = {"type": "quantitative", "scale": {"type": "log"}, "title": "total$ per M visible output tokens"}
    return {
        "title": {"text": "Cost per visible output (median, 90% interval over session trees)",
                  "subtitle": f"Assistant calls reporting reasoning. Faded: fewer than {MIN_TREES} "
                              "session trees. Observational: groups differ in task mix."},
        "data": {"values": rows},
        "height": {"step": 22},
        "width": 640,
        "encoding": {"y": enc_y, "opacity": opacity},
        "layer": [
            {"mark": "rule", "encoding": {"x": {"field": "lo", **x}, "x2": {"field": "hi"}}},
            {"mark": {"type": "point", "filled": True, "size": 60},
             "encoding": {"x": {"field": "mid", **x}, "color": {"field": "model", "legend": None},
                          "tooltip": [{"field": "group"}, {"field": "mid", "format": ".1f", "title": "median"},
                                      {"field": "lo", "format": ".1f", "title": "5%"},
                                      {"field": "hi", "format": ".1f", "title": "95%"},
                                      {"field": "trees", "title": "session trees"}]}},
        ],
    }
