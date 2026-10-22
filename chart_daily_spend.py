"""Daily spend stacked by model, with waste (cache misses + cache-warm pings) as a line."""
from collections import defaultdict
from datetime import datetime

from calls import Call

TOP_MODELS = 7  # more stacked colors become indistinguishable; the rest is "other"


def daily_spend_data(calls: list[Call], cutoff: float | None) -> list[dict]:
    """Per local day: spend per model, and waste$ under model "waste". Days before
    `cutoff` are dropped: sessions are selected by modification time, so earlier days
    only contain the old part of sessions that are still active (selection bias)."""
    calls = [c for c in calls if cutoff is None or c.end >= cutoff]
    by_model = defaultdict(float)
    for c in calls:
        by_model[c.model] += c.cost["total"]
    top = set(sorted(by_model, key=by_model.get, reverse=True)[:TOP_MODELS])
    spend = defaultdict(float)
    for c in calls:
        day = datetime.fromtimestamp(c.end).date().isoformat()
        spend[(day, c.model if c.model in top else "other")] += c.cost["total"]
        waste = c.miss_cost + (c.cost["total"] if c.kind == "cache_warm" else 0)
        spend[(day, "waste")] += waste
    return [{"day": d, "model": m, "usd": v} for (d, m), v in sorted(spend.items())]


def daily_spend_spec(rows: list[dict]) -> dict:
    x = {"field": "day", "type": "temporal", "timeUnit": "yearmonthdate", "title": None}
    y = {"field": "usd", "type": "quantitative", "title": "dollars"}
    return {
        "title": {"text": "Daily spend by model",
                  "subtitle": "Line: waste = cache misses + cache-warm pings (part of the bars, not extra). Local time."},
        "data": {"values": rows},
        "width": 640, "height": 260,
        "layer": [
            {"transform": [{"filter": "datum.model != 'waste'"}],
             "mark": "bar",
             "encoding": {"x": x, "y": {**y, "stack": True}, "color": {"field": "model", "type": "nominal", "legend": {"labelLimit": 0}},
                          "tooltip": [{"field": "day", "type": "temporal"}, {"field": "model"},
                                      {"field": "usd", "format": "$.2f"}]}},
            {"transform": [{"filter": "datum.model == 'waste'"}],
             "mark": {"type": "line", "point": True, "color": "black", "strokeDash": [4, 3]},
             "encoding": {"x": x, "y": y,
                          "tooltip": [{"field": "day", "type": "temporal"},
                                      {"field": "usd", "format": "$.2f", "title": "waste"}]}},
        ],
    }
