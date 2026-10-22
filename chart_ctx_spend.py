"""Cost-weighted context curve: which share of a model's spend went to calls with context <= x.

Weighting by cost, not by call count, shows where the money goes: a few huge-context
calls can dominate spend while barely moving the call-count median.
"""
from collections import defaultdict

from calls import Call

MIN_SHARE = 0.01  # models below this share of total spend are left out to keep the chart readable
POINTS = 200      # curve points per model; the embedded data stays small

HELP = ("Read it as: y% of this model's spend went to calls with at most x tokens of context. "
        "A curve that rises late (to the right) means most money goes to long contexts; "
        "compacting or starting fresh sessions earlier cuts cost there. Where the curve reaches "
        "50% is the context size at which half the money was spent.")


def ctx_spend_data(calls: list[Call]) -> list[dict]:
    per = defaultdict(list)
    for c in calls:
        if c.kind == "assistant" and c.ctx > 0:
            per[c.model].append((c.ctx, c.cost["total"]))
    grand = sum(cost for xs in per.values() for _, cost in xs)
    rows = []
    for model, xs in per.items():
        total = sum(cost for _, cost in xs)
        if not grand or total < MIN_SHARE * grand:
            continue
        xs.sort()
        step = max(1, len(xs) // POINTS)
        acc = 0.0
        for i, (ctx, cost) in enumerate(xs):
            acc += cost
            if i % step == 0 or i == len(xs) - 1:
                rows.append({"model": model, "ctx": ctx, "share": acc / total})
    return rows


def ctx_spend_spec(rows: list[dict]) -> dict:
    return {
        "title": {"text": "Share of spend by context size",
                  "subtitle": "Assistant calls. y: share of the model's spend on calls with context <= x. "
                              f"Models under {MIN_SHARE:.0%} of spend omitted."},
        "data": {"values": rows},
        "width": 640, "height": 260,
        "mark": {"type": "line", "interpolate": "step-after"},
        "encoding": {
            "x": {"field": "ctx", "type": "quantitative", "title": "context tokens"},
            "y": {"field": "share", "type": "quantitative", "title": "share of spend",
                  "axis": {"format": "%"}},
            "color": {"field": "model", "type": "nominal", "legend": {"labelLimit": 0}},
            "tooltip": [{"field": "model"}, {"field": "ctx", "format": ","},
                        {"field": "share", "format": ".1%"}],
        },
    }
