"""Effort sweep: per model, cost per visible output and thinking per request at each effort.

The cost excludes cache misses (miss_cost): how often the cache expired depends on how
interactively an effort was used, not on the effort, and would swamp the effort effect.
Misses have their own charts (chart_miss_vs_gap.py, chart_daily_spend.py).
The low point of the cost line is the cheapest effort per visible token. The thinking row
shows whether a higher effort actually made the model think more. Both rows share the
y scale across models, so the chart also compares models.

Intervals: 90% Bayesian bootstrap over session trees (see bayesian_bootstrap.py).
Observational data: efforts are chosen per task, so a gap can come from the task.
"""
from collections import defaultdict

from bayesian_bootstrap import ratio_interval
from calls import Call
from table import EFFORTS

MIN_TREES = 10  # below this, the point is shown faded: too few independent sessions
HIDE_BELOW = 3  # fewer trees give no usable interval (one tree: every draw is the same ratio)
COST, THINK = "$ per M visible output tokens, without misses", "thinking tokens per request"

HELP = ("One column per model, thinking effort rising to the right. Top: dollars per million "
        "tokens of visible answer (output without thinking), counting cache misses as if the "
        "cache had held, because misses depend on your pauses, not on the effort; the lowest "
        "point is the cheapest effort. Bottom: average thinking tokens per request, to see whether a higher effort "
        "really thinks more. Dot: typical value; line: the range it plausibly lies in given the "
        "number of sessions; overlapping ranges mean no clear difference. Faded: fewer than "
        f"{MIN_TREES} sessions; efforts with fewer than {HIDE_BELOW} are hidden. Caveats: you "
        "pick higher efforts for harder tasks, so a difference may come from the task; and "
        "this cost never credits thinking for fewer retries or better answers.")


def effort_sweep_data(calls: list[Call]) -> list[dict]:
    # Per (model, effort) and tree: [cost, visible tokens, reasoning tokens, calls].
    per = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0.0, 0]))
    for c in calls:
        if c.kind != "assistant" or c.reasoning is None:
            continue
        u = per[(c.model, c.effort)][c.tree]
        u[0] += c.cost["total"] - c.miss_cost
        u[1] += c.tokens["output"] - c.reasoning
        u[2] += c.reasoning
        u[3] += 1
    rows = []
    for (model, effort), trees in per.items():
        if len(trees) < HIDE_BELOW:
            continue
        # Some providers report reasoning > output; clamp like table.py does per group.
        cost = ratio_interval([(u[0], max(0.0, u[1])) for u in trees.values()])
        think = ratio_interval([(u[2], u[3]) for u in trees.values()])
        for metric, q, scale in ((COST, cost, 1e6), (THINK, think, 1)):
            if q is not None:
                rows.append({"model": model, "effort": effort, "metric": metric,
                             "lo": q[0] * scale, "mid": q[1] * scale, "hi": q[2] * scale,
                             "trees": len(trees), "few": len(trees) < MIN_TREES})
    return rows


def _panel(rows: list[dict], metric: str, y_scale: dict, header: bool) -> dict:
    x = {"field": "effort", "type": "ordinal", "sort": list(EFFORTS), "title": None}
    y = {"type": "quantitative", "scale": y_scale, "title": metric}
    tooltip = [{"field": "model"}, {"field": "effort"}, {"field": "mid", "format": ",.1f", "title": "median"},
               {"field": "lo", "format": ",.1f", "title": "5%"}, {"field": "hi", "format": ",.1f", "title": "95%"},
               {"field": "trees", "title": "session trees"}]
    return {
        "data": {"values": [r for r in rows if r["metric"] == metric]},
        "facet": {"column": {"field": "model", "type": "nominal", "title": None,
                             "header": {"labelAngle": -20, "labelAlign": "right", "labelLimit": 0}
                             if header else {"labels": False}}},
        "spec": {
            "width": {"step": 26}, "height": 180,
            "encoding": {"x": x, "opacity": {"condition": {"test": "datum.few", "value": 0.35}, "value": 1}},
            "layer": [
                {"mark": {"type": "line", "color": "#bbb"}, "encoding": {"y": {"field": "mid", **y}}},
                {"mark": {"type": "rule", "color": "#4c78a8"},
                 "encoding": {"y": {"field": "lo", **y}, "y2": {"field": "hi"}}},
                {"mark": {"type": "point", "filled": True, "size": 50, "color": "#4c78a8"},
                 "encoding": {"y": {"field": "mid", **y}, "tooltip": tooltip}},
            ],
        },
    }


def effort_sweep_spec(rows: list[dict]) -> dict:
    return {
        "title": {"text": "Cost and thinking by effort (median, 90% interval over session trees)",
                  "subtitle": "Assistant calls reporting reasoning. Observational: efforts differ in task mix."},
        "vconcat": [_panel(rows, COST, {"type": "log"}, header=True),
                    _panel(rows, THINK, {"zero": True}, header=False)],
    }
