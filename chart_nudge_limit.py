"""Reminder-limit experiment: cost per prompt against the randomly assigned limit at which
the infinite-context extension reminds the agent to fold.

Design (randomized, intent-to-treat): with `nudgeAtTokens: [low, high]` the extension draws
one limit per branch and records it (calls.py NudgeArm). The analysis compares by that
assignment, not by when the agent actually folded, because agents also fold unprompted.
- Dose: the limit in force, min(drawn, percent% of the model's window). A 272k window caps
  the reminder at 204k whatever was drawn, so the window decides the dose.
- Window: below `low` every arm behaves the same, so only calls from the session's first
  call with context >= low onward count. Sessions that never get there carry no information.
- Unit: one session file and model. Sessions with more than one assignment (range edited
  mid-session, or the experiment switched on mid-session) are left out.
- Outcome: all dollars of the unit (including folding and misses, both depend on the limit)
  per prompt (calls.py Call.after_prompt: new work from the agent's owner). Per task step would
  be biased: folding early adds steps and so lowers the cost per step. Per session, not per
  call: calls of one session are correlated.
- Cost per prompt is expected to be U-shaped in the limit: a low limit folds often, a high
  one re-reads a larger context on every call. Models differ in price by orders of
  magnitude, so the fit is log(cost per prompt) = alpha[model] + b*x + c*x^2: one shared
  curve, one level per model (fixed effects, solved by demeaning within each model,
  Frisch-Waugh-Lovell). A model seen in one unit only sets its own level and does not move
  the curve. The interval of the cheapest limit comes from a Bayesian bootstrap over session
  trees (bayesian_bootstrap.py explains the resampling unit).
"""
import math
import random
from collections import defaultdict

from bayesian_bootstrap import QUANTILES
from calls import SIDE_MODEL, Call

MIN_PROMPTS = 3  # fewer prompts after the crossing: too noisy to place a point
MIN_TREES = 5    # fewer independent session trees: no fit
FIT_POINTS = 50  # points of the drawn curve
SCALE = 1e5      # tokens per fit unit, keeps the sums well conditioned

HELP = ("Each dot is one session (and model) from the reminder-limit experiment: x is the "
        "context size at which the agent was reminded to fold, assigned at random per session; "
        "y is what the session cost per prompt (typical session: the fit uses the logarithm) after its context first reached the lower end "
        "of the range (before that, all sessions behave the same), relative to the cheapest "
        "limit and with the price level of its model taken out. Dot size: number of prompts. "
        "The curve is one fit over all models, weighted by prompts; the shaded band is the range "
        "in which its lowest point plausibly lies (90% over session trees), the vertical line its "
        "median. A band that touches the edge of the range means the cheapest limit may lie "
        "outside it. A prompt is new work from the agent's owner: a user message, or for a "
        "subagent its spawner's message. Corrective "
        "prompts after a bad fold make a limit look cheaper than it is. Cost only: whether the "
        "agent works better or worse with a smaller context is not measured.")


def _units(calls: list[Call], windows: dict[str, int]) -> list[dict]:
    by_session = defaultdict(list)
    for c in calls:
        by_session[c.session].append(c)
    units = {}
    for session, cs in by_session.items():
        arms = {c.nudge_arm for c in cs}
        if len(arms) != 1 or None in arms:
            continue
        (arm,) = arms
        start = next((i for i, c in enumerate(cs) if c.kind == "assistant" and c.ctx >= arm.low), None)
        if start is None:
            continue
        for c in cs[start:]:
            window = windows.get(c.model)
            if c.model == SIDE_MODEL or window is None:
                continue
            u = units.setdefault((session, c.model), {
                "tree": c.tree, "model": c.model, "cost": 0.0, "prompts": 0,
                "dose": min(arm.tokens, arm.percent / 100 * window)})
            u["cost"] += c.cost["total"]
            u["prompts"] += c.kind == "assistant" and c.after_prompt
    return [{**u, "x": u["dose"] / SCALE, "y": math.log(u["cost"] / u["prompts"])}
            for u in units.values() if u["prompts"] >= MIN_PROMPTS and u["cost"] > 0]


def _fit(units: list[dict], weights: list[float]):
    """Weighted least squares y = alpha[model] + b*x + c*x^2 -> (b, c, alpha), None if b and c
    are not identified. Demeaning x, x^2 and y within each model removes alpha, leaving a
    2x2 system for b and c (Frisch-Waugh-Lovell)."""
    groups = defaultdict(list)
    for u, w in zip(units, weights):
        groups[u["model"]].append((u, w))
    means, s11, s12, s22, t1, t2 = {}, 0.0, 0.0, 0.0, 0.0, 0.0
    for model, g in groups.items():
        sw = sum(w for _, w in g)
        mx, mq, my = (sum(w * f(u) for u, w in g) / sw
                      for f in (lambda u: u["x"], lambda u: u["x"] ** 2, lambda u: u["y"]))
        means[model] = (mx, mq, my)
        for u, w in g:
            dx, dq, dy = u["x"] - mx, u["x"] ** 2 - mq, u["y"] - my
            s11, s12, s22, t1, t2 = s11 + w * dx * dx, s12 + w * dx * dq, s22 + w * dq * dq, t1 + w * dx * dy, t2 + w * dq * dy
    det = s11 * s22 - s12 * s12
    if det <= 1e-9 * s11 * s22 or det <= 0:
        return None
    b, c = (t1 * s22 - t2 * s12) / det, (s11 * t2 - s12 * t1) / det
    return b, c, {m: my - b * mx - c * mq for m, (mx, mq, my) in means.items()}


def _argmin(b: float, c: float, lo: float, hi: float) -> float:
    """x in [lo, hi] where b*x + c*x^2 is lowest."""
    xs = [lo, hi] + ([-b / (2 * c)] if c > 0 and lo < -b / (2 * c) < hi else [])
    return min(xs, key=lambda x: b * x + c * x * x)


def nudge_limit_data(calls: list[Call], windows: dict[str, int],
                     draws: int = 1000, seed: int = 0) -> list[dict]:
    units = _units(calls, windows)
    trees = sorted({u["tree"] for u in units})
    fit = _fit(units, [u["prompts"] for u in units]) if len(trees) >= MIN_TREES else None
    summary = {"kind": "summary", "sessions": len(units), "trees": len(trees)}
    if fit is None:
        return [summary] + [{"model": u["model"], "kind": "unit", "dose": u["dose"], "rel": None,
                 "prompts": u["prompts"]} for u in units]
    b, c, alpha = fit
    lo, hi = min(u["x"] for u in units), max(u["x"] for u in units)
    x0 = _argmin(b, c, lo, hi)
    base = b * x0 + c * x0 * x0  # the curve is drawn relative to its lowest point
    rows = [summary] + [{"model": u["model"], "kind": "unit", "dose": u["dose"], "prompts": u["prompts"],
             "rel": math.exp(u["y"] - alpha[u["model"]] - base)} for u in units]
    for i in range(FIT_POINTS):
        x = lo + (hi - lo) * i / (FIT_POINTS - 1)
        rows.append({"kind": "fit", "dose": x * SCALE, "rel": math.exp(b * x + c * x * x - base)})
    rng, mins = random.Random(seed), []
    for _ in range(draws):
        w = {t: rng.expovariate(1.0) for t in trees}
        f = _fit(units, [w[u["tree"]] * u["prompts"] for u in units])
        if f is not None:
            mins.append(_argmin(f[0], f[1], lo, hi) * SCALE)
    if mins:
        mins.sort()
        q = [mins[min(int(p * len(mins)), len(mins) - 1)] for p in QUANTILES]
        rows.append({"kind": "argmin", "lo": q[0], "mid": q[1], "hi": q[2], "trees": len(trees)})
    return rows


def nudge_limit_spec(rows: list[dict]) -> dict:
    (summary,) = [r for r in rows if r["kind"] == "summary"]
    shown = ("" if summary["trees"] >= MIN_TREES else
             f" Nothing is drawn below {MIN_TREES} session trees: too few independent sessions to fit.")
    x = {"field": "dose", "type": "quantitative", "scale": {"zero": False},
         "title": "reminder limit in force (tokens)"}
    y = {"field": "rel", "type": "quantitative", "scale": {"zero": False},
         "title": "cost per prompt, relative to the cheapest limit"}
    only = lambda kind: [{"filter": f"datum.kind === '{kind}'"}]
    return {
        "title": {"text": "Reminder-limit experiment: cost per prompt",
                  "subtitle": f"{summary['sessions']} sessions from {summary['trees']} session trees "
                              f"with a randomly assigned limit that reached its range.{shown}"},
        "data": {"values": rows},
        "width": 600, "height": 300,
        "layer": [
            {"transform": only("argmin"), "mark": {"type": "rect", "opacity": 0.15, "color": "#4c78a8"},
             "encoding": {"x": {**x, "field": "lo"}, "x2": {"field": "hi"}}},
            {"transform": only("argmin"), "mark": {"type": "rule", "color": "#4c78a8"},
             "encoding": {"x": {**x, "field": "mid"},
                          "tooltip": [{"field": "mid", "format": ",.0f", "title": "cheapest limit, median"},
                                      {"field": "lo", "format": ",.0f", "title": "5%"},
                                      {"field": "hi", "format": ",.0f", "title": "95%"},
                                      {"field": "trees", "title": "session trees"}]}},
            {"transform": only("unit"), "mark": {"type": "point", "filled": True, "opacity": 0.6},
             "encoding": {"x": x, "y": y, "color": {"field": "model", "type": "nominal", "title": None},
                          "size": {"field": "prompts", "type": "quantitative", "title": "prompts"},
                          "tooltip": [{"field": "model"}, {"field": "dose", "format": ",.0f"},
                                      {"field": "rel", "format": ".2f"}, {"field": "prompts"}]}},
            {"transform": only("fit"), "mark": {"type": "line", "color": "black"},
             "encoding": {"x": x, "y": y}},
        ],
    }
