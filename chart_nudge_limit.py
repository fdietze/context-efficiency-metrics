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
- Models differ in price by orders of magnitude, so each unit's dollars are divided by its
  model's average cost per prompt over all units (1 = average for that model). The question
  the chart answers is whether some limit is cheaper; a bar per BIN_TOKENS of limit answers
  it without assuming a curve shape (KISS).
- Bar: sum of normalized dollars / sum of prompts of the bin's units; interval from a Bayesian
  bootstrap over session trees (bayesian_bootstrap.py explains the resampling unit). The
  model averages are not redrawn per draw, which makes the interval slightly narrow.
"""
from collections import defaultdict

from bayesian_bootstrap import ratio_interval
from calls import SIDE_MODEL, Call

MIN_PROMPTS = 3        # fewer prompts after the crossing: too noisy to count the session
MIN_TREES = 3          # fewer session trees in a bin: the bootstrap interval collapses, no bar
BIN_TOKENS = 50_000    # width of a bar in reminder-limit tokens

HELP = ("Is some reminder limit cheaper? In the reminder-limit experiment each session is "
        "reminded to fold at a random context size. Each bar is the sessions whose limit fell in "
        "its range: their cost per prompt, with each model's price level taken out (1 = that "
        "model's average). The whisker is a 90% interval over session trees. Bars with "
        "overlapping whiskers are not clearly different. Only cost after the context first "
        "reached the lower end of the range counts (before that, all sessions behave the same). "
        "A prompt is new work from the agent's owner: a user message, or for a subagent its "
        "spawner's message. Corrective prompts after a bad fold make a limit look cheaper than "
        "it is. Cost only: whether the agent works better or worse with a smaller context is "
        "not measured.")


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
    return [u for u in units.values() if u["prompts"] >= MIN_PROMPTS and u["cost"] > 0]


def nudge_limit_data(calls: list[Call], windows: dict[str, int]) -> list[dict]:
    units = _units(calls, windows)
    level = defaultdict(lambda: [0.0, 0])
    for u in units:
        level[u["model"]][0] += u["cost"]
        level[u["model"]][1] += u["prompts"]
    bins = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))  # bin -> tree -> [dollars/level, prompts]
    for u in units:
        cost, prompts = level[u["model"]]
        t = bins[int(u["dose"] // BIN_TOKENS)][u["tree"]]
        t[0] += u["cost"] / (cost / prompts)
        t[1] += u["prompts"]
    rows = [{"kind": "summary", "sessions": len(units), "trees": len({u["tree"] for u in units})}]
    for b, trees in sorted(bins.items()):
        ci = ratio_interval([tuple(v) for v in trees.values()]) if len(trees) >= MIN_TREES else None
        if ci:
            rows.append({"kind": "bin", "range": f"{b * BIN_TOKENS // 1000}-{(b + 1) * BIN_TOKENS // 1000}k",
                         "lo": ci[0], "mid": ci[1], "hi": ci[2], "trees": len(trees)})
    return rows


def nudge_limit_spec(rows: list[dict]) -> dict:
    (s,) = [r for r in rows if r["kind"] == "summary"]
    bins = [r for r in rows if r["kind"] == "bin"]
    x = {"field": "range", "type": "ordinal", "sort": None, "title": "reminder limit (tokens)",
         "axis": {"labelAngle": 0}}
    y = {"type": "quantitative", "title": "cost per prompt (1 = average)"}
    return {
        "title": {"text": "Cost per prompt by reminder limit",
                  "subtitle": f"{s['sessions']} sessions from {s['trees']} session trees, each with a random limit"
                              + ("" if bins else f". No bar yet: each needs {MIN_TREES} session trees.")},
        "data": {"values": bins},
        "width": 400, "height": 250,
        "layer": [
            {"mark": {"type": "bar", "color": "#4c78a8", "opacity": 0.6},
             "encoding": {"x": x, "y": {**y, "field": "mid"},
                          "tooltip": [{"field": "mid", "format": ".2f", "title": "median"},
                                      {"field": "lo", "format": ".2f", "title": "5%"},
                                      {"field": "hi", "format": ".2f", "title": "95%"},
                                      {"field": "trees", "title": "session trees"}]}},
            {"mark": {"type": "rule", "strokeWidth": 2},
             "encoding": {"x": x, "y": {**y, "field": "lo"}, "y2": {"field": "hi"}}},
            {"data": {"values": [{"one": 1}]}, "mark": {"type": "rule", "strokeDash": [4, 4]},
             "encoding": {"y": {**y, "field": "one"}}},
        ],
    }
