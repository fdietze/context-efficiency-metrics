"""Daily spend stacked by model, with waste (cache misses + cache-warm pings) as a line."""
from collections import defaultdict
from datetime import datetime, timedelta

from calls import Call

TOP_MODELS = 7  # more stacked colors become indistinguishable; the rest is "other"

HELP = ("Bars: what each day cost. The two lines are cache overhead inside the bars: "
        "'cache misses' is context processed again because the cache had expired; "
        "'cache warming' is the cost of keep-alive pings that prevent such misses. "
        "Warming pays off while it stays clearly below the misses it avoids. "
        "Days before --since are left out because only part of their sessions was read.")
OVERHEAD = ("cache misses", "cache warming")  # line series, kept in their own field "series"


def daily_spend_data(calls: list[Call], cutoff: float | None) -> list[dict]:
    """Per local day: spend per model, plus the OVERHEAD series. Sessions are selected by
    modification time, so days before `cutoff` only contain the old part of sessions that
    are still active (selection bias); they are dropped, and so is the partial day the
    cutoff falls into."""
    if cutoff is not None:
        start = datetime.fromtimestamp(cutoff)
        if start.time() != datetime.min.time():
            start = datetime.combine(start.date() + timedelta(days=1), datetime.min.time())
        calls = [c for c in calls if c.end >= start.timestamp()]
    by_model = defaultdict(float)
    for c in calls:
        by_model[c.model] += c.cost["total"]
    top = set(sorted(by_model, key=by_model.get, reverse=True)[:TOP_MODELS])
    spend = defaultdict(float)
    for c in calls:
        day = datetime.fromtimestamp(c.end).date().isoformat()
        spend[(day, c.model if c.model in top else "other")] += c.cost["total"]
        # A failed warm ping's miss is part of its own cost, so each call counts once.
        if c.kind == "cache_warm":
            spend[(day, OVERHEAD[1])] += c.cost["total"]
        else:
            spend[(day, OVERHEAD[0])] += c.miss_cost
    # Bars and lines use separate fields; a shared field would merge their legends.
    return [{"day": d, "series" if m in OVERHEAD else "model": m, "usd": v}
            for (d, m), v in sorted(spend.items())]


def daily_spend_spec(rows: list[dict]) -> dict:
    x = {"field": "day", "type": "temporal", "timeUnit": "yearmonthdate", "title": None}
    y = {"field": "usd", "type": "quantitative", "title": "dollars"}
    return {
        "title": {"text": "Daily spend by model",
                  "subtitle": "Lines: cache overhead, part of the bars, not extra. Local time."},
        "data": {"values": rows},
        "width": 640, "height": 260,
        "layer": [
            {"transform": [{"filter": "isValid(datum.model)"}],
             "mark": "bar",
             "encoding": {"x": x, "y": {**y, "stack": True}, "color": {"field": "model", "type": "nominal", "title": "model", "legend": {"labelLimit": 0}},
                          "tooltip": [{"field": "day", "type": "temporal"}, {"field": "model"},
                                      {"field": "usd", "format": "$.2f"}]}},
            {"transform": [{"filter": "isValid(datum.series)"}],
             "mark": {"type": "line", "point": True, "color": "black"},
             "encoding": {"x": x, "y": y,
                          "strokeDash": {"field": "series", "type": "nominal", "title": "cache overhead",
                                         "scale": {"domain": list(OVERHEAD), "range": [[1, 0], [4, 3]]}},
                          "tooltip": [{"field": "day", "type": "temporal"}, {"field": "series"},
                                      {"field": "usd", "format": "$.2f"}]}},
        ],
    }
