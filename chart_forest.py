"""Forest plot: total$ per million visible output tokens per model and effort, with a
90% Bayesian bootstrap interval over session trees.

Observational data: groups differ in task mix, so intervals show sampling noise only,
not the causal effect of a model or effort.
"""
from collections import defaultdict

from bayesian_bootstrap import ratio_interval
from calls import Call

MIN_TREES = 10  # below this, the interval is shown faded: too few independent sessions
HIDE_BELOW = 3  # fewer trees give no usable interval (one tree: every draw is the same ratio)

HELP = ("Each row is a model at one thinking effort; further left is cheaper per token of visible "
        "answer (output without thinking). The dot is the typical value, the line the range it "
        "plausibly lies in given how many sessions there are. Overlapping lines: no clear "
        "difference. A short line means much data, not that the model is better. The groups did "
        "different tasks, so a gap can come from the work, not the model. Log scale: one grid "
        "step further right is several times more expensive.")


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
        if q is None or len(trees) < HIDE_BELOW:
            continue
        rows.append({"group": f"{model} @ {effort}", "model": model, "effort": effort,
                     "lo": q[0] * 1e6, "mid": q[1] * 1e6, "hi": q[2] * 1e6,
                     "trees": len(trees), "few": len(trees) < MIN_TREES})
    return sorted(rows, key=lambda r: r["mid"])


def forest_spec(rows: list[dict]) -> dict:
    enc_y = {"field": "group", "type": "nominal", "sort": None, "title": None,
             "axis": {"labelLimit": 0}}
    opacity = {"condition": {"test": "datum.few", "value": 0.35}, "value": 1}
    x = {"type": "quantitative", "scale": {"type": "log"}, "title": "total$ per M visible output tokens"}
    return {
        "title": {"text": "Cost per visible output (median, 90% interval over session trees)",
                  "subtitle": f"Assistant calls reporting reasoning. Faded: fewer than {MIN_TREES} session trees; "
                              f"hidden: fewer than {HIDE_BELOW}. Observational: groups differ in task mix."},
        "data": {"values": rows},
        "height": {"step": 22},
        "width": 640,
        "encoding": {"y": enc_y, "opacity": opacity},
        "layer": [
            {"mark": "rule", "encoding": {"x": {"field": "lo", **x}, "x2": {"field": "hi"}}},
            {"mark": {"type": "point", "filled": True, "size": 60},
             "encoding": {"x": {"field": "mid", **x},
                          "tooltip": [{"field": "group"}, {"field": "mid", "format": ".1f", "title": "median"},
                                      {"field": "lo", "format": ".1f", "title": "5%"},
                                      {"field": "hi", "format": ".1f", "title": "95%"},
                                      {"field": "trees", "title": "session trees"}]}},
        ],
    }
