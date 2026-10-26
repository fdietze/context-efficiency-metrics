"""Reminder-limit experiment: cost per task step against the randomly assigned limit at which
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
  per task step (assistant call that calls no folding tool). Per session, not per call:
  calls of one session are correlated.
- Cost per step is expected to be U-shaped in the limit: a low limit folds often (fold%
  rises), a high one re-reads a larger context on every call. A weighted quadratic fit
  locates the minimum; its interval comes from a Bayesian bootstrap over session trees
  (bayesian_bootstrap.py explains the resampling unit).
"""
import random
from collections import defaultdict

from bayesian_bootstrap import QUANTILES
from calls import FOLD_TOOLS, SIDE_MODEL, Call

MIN_STEPS = 10   # fewer task steps after the crossing: too noisy to place a point
MIN_TREES = 5    # fewer independent session trees: no fit
FIT_POINTS = 50  # points of the drawn curve
SCALE = 1e5      # tokens per fit unit, keeps the normal equations well conditioned

HELP = ("Each dot is one session (and model) from the reminder-limit experiment: x is the "
        "context size at which the agent was reminded to fold, assigned at random per session; "
        "y is what the session cost per task step after its context first reached the lower end "
        "of the range (before that, all sessions behave the same). Dot size: number of steps. "
        "The curve is a quadratic fit weighted by steps; the shaded band is the range in which "
        "its lowest point plausibly lies (90% over session trees), the vertical line its median. "
        "A band that touches the edge of the range means the cheapest limit may lie outside it. "
        "Cost only: whether the agent works better or worse with a smaller context is not measured.")


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
                "tree": c.tree, "model": c.model, "cost": 0.0, "steps": 0,
                "dose": min(arm.tokens, arm.percent / 100 * window)})
            u["cost"] += c.cost["total"]
            if c.kind == "assistant" and not FOLD_TOOLS.intersection(c.tools):
                u["steps"] += 1
    return [u for u in units.values() if u["steps"] >= MIN_STEPS]


def _quadratic(points: list[tuple[float, float, float]]) -> tuple[float, float, float] | None:
    """Weighted least squares y = a + b*x + c*x^2 over (x, y, weight); None if degenerate."""
    s = [sum(w * x ** k for x, _, w in points) for k in range(5)]
    t = [sum(w * y * x ** k for x, y, w in points) for k in range(3)]
    m = [[s[0], s[1], s[2]], [s[1], s[2], s[3]], [s[2], s[3], s[4]]]

    def det(a):
        return (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
                - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
                + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))

    d = det(m)
    if abs(d) < 1e-12 * max(1.0, abs(s[0]) ** 3):
        return None
    # Cramer's rule: replace column j with t.
    return tuple(det([[t[i] if j == col else m[i][j] for j in range(3)] for i in range(3)]) / d
                 for col in range(3))


def _argmin(coef, lo: float, hi: float) -> float:
    """x in [lo, hi] where the fitted parabola is lowest."""
    a, b, c = coef
    xs = [lo, hi] + ([-b / (2 * c)] if c > 0 and lo < -b / (2 * c) < hi else [])
    return min(xs, key=lambda x: a + b * x + c * x * x)


def nudge_limit_data(calls: list[Call], windows: dict[str, int],
                     draws: int = 1000, seed: int = 0) -> list[dict]:
    rows, per_model = [], defaultdict(list)
    for u in _units(calls, windows):
        per_model[u["model"]].append(u)
        rows.append({"model": u["model"], "kind": "unit", "dose": u["dose"],
                     "usd": u["cost"] / u["steps"], "steps": u["steps"]})
    for model, us in per_model.items():
        trees = sorted({u["tree"] for u in us})
        xs = [u["dose"] / SCALE for u in us]
        lo, hi = min(xs), max(xs)
        fit = _quadratic([(x, u["cost"] / u["steps"], u["steps"]) for x, u in zip(xs, us)])
        if len(trees) < MIN_TREES or fit is None or hi - lo <= 0:
            continue
        a, b, c = fit
        for i in range(FIT_POINTS):
            x = lo + (hi - lo) * i / (FIT_POINTS - 1)
            rows.append({"model": model, "kind": "fit", "dose": x * SCALE, "usd": a + b * x + c * x * x})
        rng, mins = random.Random(seed), []
        for _ in range(draws):
            w = {t: rng.expovariate(1.0) for t in trees}
            f = _quadratic([(x, u["cost"] / u["steps"], w[u["tree"]] * u["steps"]) for x, u in zip(xs, us)])
            if f is not None:
                mins.append(_argmin(f, lo, hi) * SCALE)
        if mins:
            mins.sort()
            q = [mins[min(int(p * len(mins)), len(mins) - 1)] for p in QUANTILES]
            rows.append({"model": model, "kind": "argmin", "lo": q[0], "mid": q[1], "hi": q[2],
                         "trees": len(trees)})
    return rows


def nudge_limit_spec(rows: list[dict]) -> dict:
    n = sum(r["kind"] == "unit" for r in rows)
    x = {"field": "dose", "type": "quantitative", "scale": {"zero": False},
         "title": "reminder limit in force (tokens)"}
    y = {"field": "usd", "type": "quantitative", "title": "$ per task step"}
    only = lambda kind: [{"filter": f"datum.kind === '{kind}'"}]
    return {
        "title": {"text": "Reminder-limit experiment: cost per task step",
                  "subtitle": f"{n} sessions with a randomly assigned limit that reached its range. "
                              "Fit and band need sessions from enough trees."},
        "data": {"values": rows},
        "facet": {"column": {"field": "model", "type": "nominal", "title": None,
                             "header": {"labelLimit": 0}}},
        "spec": {
            "width": 300, "height": 220,
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
                 "encoding": {"x": x, "y": y, "size": {"field": "steps", "type": "quantitative", "title": "steps"},
                              "tooltip": [{"field": "dose", "format": ",.0f"}, {"field": "usd", "format": "$.3f"},
                                          {"field": "steps"}]}},
                {"transform": only("fit"), "mark": {"type": "line", "color": "black"},
                 "encoding": {"x": x, "y": y}},
            ],
        },
    }
