"""Fold payoff: what a fold returns per dollar it costs, against the share of context it freed.

- Fold: per session file, a maximal run of assistant calls using folding tools
  (calls.py FOLD_TOOLS) that contains at least one context_fold call. File order stands in
  for the chain; branches inside one file are rare.
- Freed: context of the run's last call minus context of the first call after it.
- Cost: Call.fold_cost of the run's calls plus that of the first call after it (the cache
  miss the fold causes). DRY: the same attribution as the fold% column (calls.py read_calls).
- Savings (counterfactual: the same later calls without this fold), summed over the later
  calls up to the next fold or the session's end. The next fold would have folded these
  tokens anyway, so the horizon ends there. Per later call:
  - freed * cache-read price: each call re-reads that many tokens fewer;
  - min(freed, missed) * (uncached - cache-read price) for a call with a cache miss: after an
    expiry the whole prefix is written again, `freed` tokens fewer. Skipped for the first
    call after the fold, whose miss the fold itself caused (counted as cost).
- x is the share of context freed, not tokens: a fold's cost grows with the context
  (about ten full cached reads of it), so the break-even in tokens scales with context size
  and the share carries over between context sizes and models.
- Observational: bigger folds also delay the next fold, so more later calls profit. That
  is part of what they buy, so y is not divided by the number of later calls. Without the
  fold the next one would have come earlier, which makes the horizon slightly generous.

Intervals: 90% Bayesian bootstrap over session trees (see bayesian_bootstrap.py).
"""
from collections import defaultdict

from bayesian_bootstrap import ratio_interval
from calls import FOLD, FOLD_TOOLS, Call

SHARE_EDGES = tuple(i / 10 for i in range(11))  # bins of the share of context freed

HELP = ("Each faint dot is one fold: x is the share of the context it freed, y what it saved "
        "per dollar it cost, on a log scale. Cost: the folding turns plus the cache miss the fold "
        "causes. Savings: every later call up to the next fold re-reads fewer cached tokens, and "
        "a later cache miss after a pause re-writes fewer. Above the dashed line at 1 a fold "
        "paid off. The line with its band is the return of all folds in a bin (90% over "
        "session trees). The share, not the token count, decides, because a fold costs about "
        "ten cached reads of the whole context: the same number of freed tokens pays off in a "
        "small context and not in a large one. Folds that freed more also push the next fold "
        "later, which is included. Cost only: what the agent loses or gains in quality by "
        "folding is not measured.")


def _later_savings(freed: int, later: list[Call]) -> float:
    save = 0.0
    for i, c in enumerate(later):
        t, p = c.tokens, c.cost
        read = p["cacheRead"] / t["cacheRead"] if t["cacheRead"] else 0.0  # unknown: count none
        save += freed * read
        uncached_tokens = t["input"] + t["cacheWrite"]
        if i > 0 and c.miss_cost > 0 and uncached_tokens:
            uncached = (p["input"] + p["cacheWrite"]) / uncached_tokens
            save += min(freed, c.miss_cost / uncached) * (uncached - read)
    return save


def _folds(calls: list[Call]) -> tuple[list[dict], int]:
    """(folds, folds left out because no call followed them)."""
    by_session = defaultdict(list)
    for c in calls:
        if c.kind == "assistant" and c.ctx > 0:
            by_session[c.session].append(c)
    folds, unfollowed = [], 0
    folding = lambda c: bool(FOLD_TOOLS.intersection(c.tools))
    for cs in by_session.values():
        starts = [i for i, c in enumerate(cs) if folding(c) and (i == 0 or not folding(cs[i - 1]))]
        runs = []
        for i in starts:
            j = i
            while j < len(cs) and folding(cs[j]):
                j += 1
            runs.append((i, j))
        for n, (i, j) in enumerate(runs):
            if not any(FOLD in c.tools for c in cs[i:j]):
                continue
            if j == len(cs):
                unfollowed += 1
                continue
            later = cs[j:runs[n + 1][0] if n + 1 < len(runs) else len(cs)]
            ctx, freed = cs[j - 1].ctx, cs[j - 1].ctx - cs[j].ctx
            folds.append({"tree": cs[i].tree, "model": cs[i].model, "ctx": ctx, "freed": freed,
                          "later": len(later), "cost": sum(c.fold_cost for c in cs[i:j + 1]),
                          "save": _later_savings(freed, later) if freed > 0 else 0.0})
    return folds, unfollowed


def fold_payoff_data(calls: list[Call]) -> list[dict]:
    folds, unfollowed = _folds(calls)
    shown = [f for f in folds if f["freed"] > 0]
    rows = [{"kind": "summary", "folds": len(shown), "grew": len(folds) - len(shown),
             "unfollowed": unfollowed, "save": sum(f["save"] for f in folds),
             "cost": sum(f["cost"] for f in folds)}]
    rows += [{"kind": "fold", "model": f["model"], "share": f["freed"] / f["ctx"], "freed": f["freed"],
              "ctx": f["ctx"], "later": f["later"], "ratio": f["save"] / f["cost"]}
             for f in shown if f["cost"] > 0 and f["save"] > 0]
    for lo, hi in zip(SHARE_EDGES, SHARE_EDGES[1:]):
        trees = defaultdict(lambda: [0.0, 0.0])
        n = 0
        for f in shown:
            if lo < f["freed"] / f["ctx"] <= hi:
                trees[f["tree"]][0] += f["save"]
                trees[f["tree"]][1] += f["cost"]
                n += 1
        ci = ratio_interval([tuple(v) for v in trees.values()])
        if ci:
            rows.append({"kind": "bin", "share": (lo + hi) / 2, "lo": ci[0], "mid": ci[1], "hi": ci[2],
                         "folds": n, "trees": len(trees)})
    return rows


def fold_payoff_spec(rows: list[dict]) -> dict:
    (s,) = [r for r in rows if r["kind"] == "summary"]
    total = f"{s['save'] / s['cost']:.1f}x" if s["cost"] else "-"
    x = {"field": "share", "type": "quantitative", "scale": {"domain": [0, 1]}, "axis": {"format": "%"},
         "title": "share of the context the fold freed"}
    y = {"type": "quantitative", "scale": {"type": "log"}, "title": "$ saved per $ the fold cost"}
    only = lambda kind: [{"filter": f"datum.kind === '{kind}'"}]
    return {
        "title": {"text": "Fold payoff: return per dollar against the share of context freed",
                  "subtitle": f"{s['folds']} folds, together {total} return. Left out: {s['grew']} that "
                              f"freed nothing, {s['unfollowed']} that ended their session."},
        "data": {"values": rows},
        "width": 600, "height": 300,
        "layer": [
            {"transform": only("fold"), "mark": {"type": "point", "filled": True, "opacity": 0.25, "size": 15},
             "encoding": {"x": x, "y": {**y, "field": "ratio"},
                          "color": {"field": "model", "type": "nominal", "title": None,
                                    "legend": {"labelLimit": 0}},
                          "tooltip": [{"field": "model"}, {"field": "freed", "format": ",.0f", "title": "tokens freed"},
                                      {"field": "ctx", "format": ",.0f", "title": "context"},
                                      {"field": "later", "title": "later calls"},
                                      {"field": "ratio", "format": ".2f", "title": "return"}]}},
            {"transform": only("bin"), "mark": {"type": "area", "opacity": 0.2, "color": "black"},
             "encoding": {"x": x, "y": {**y, "field": "lo"}, "y2": {"field": "hi"}}},
            {"transform": only("bin"), "mark": {"type": "line", "point": True, "color": "black"},
             "encoding": {"x": x, "y": {**y, "field": "mid"},
                          "tooltip": [{"field": "mid", "format": ".2f", "title": "return, median"},
                                      {"field": "lo", "format": ".2f", "title": "5%"},
                                      {"field": "hi", "format": ".2f", "title": "95%"},
                                      {"field": "folds"}, {"field": "trees", "title": "session trees"}]}},
            {"data": {"values": [{"one": 1}]}, "mark": {"type": "rule", "strokeDash": [4, 4]},
             "encoding": {"y": {**y, "field": "one"}}},
        ],
    }
