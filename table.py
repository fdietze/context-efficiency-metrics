"""The terminal table: Call records grouped by dimensions, one row of metrics per group."""
import bisect, math, statistics
from collections import defaultdict

from calls import PARTS, Call
from ctx_ranges import ctx_label

DIMS = ("kind", "model", "effort", "ctx")
KINDS = ("assistant", "cache_warm", "side")
# What it costs, how much is waste, how efficient, why (context, thinking), how much evidence.
DEFAULT_COLUMNS = ("total$", "miss%", "total$/Mvis", "ctx_p50", "think/out", "sessions", "calls")
EFFORTS = ("off", "minimal", "low", "medium", "high", "xhigh", "max", "unknown")


def percentile(xs: list[int], q: float) -> int:
    """Nearest-rank percentile of a sorted list."""
    return xs[max(math.ceil(q * len(xs)) - 1, 0)]


class Group:
    def __init__(self):
        self.sums = defaultdict(float)
        self.ctx = []
        self.calls = 0
        self.sessions = set()
        # Calls whose usage reports reasoning: their reasoning, output and total cost.
        self.think = self.think_out = self.think_cost = 0

    def add(self, c: Call):
        self.sums["miss$"] += c.miss_cost
        self.calls += 1
        self.sessions.add(c.session)
        if c.reasoning is not None:
            self.think += c.reasoning
            self.think_out += c.tokens["output"]
            self.think_cost += c.cost["total"]
        for k in PARTS:
            self.sums[k + "$"] += c.cost[k]
            self.sums[k + "_tok"] += c.tokens[k]
        self.sums["total$"] += c.cost["total"]
        if c.ctx > 0:
            self.ctx.append(c.ctx)

    def metrics(self) -> dict[str, str]:
        """Insertion order is the --wide column order; DEFAULT_COLUMNS is its prefix."""
        r, c = self.sums, sorted(self.ctx)
        # Some providers report reasoning > output; the clamp keeps visible tokens >= 0.
        visible = max(0, self.think_out - self.think)
        n = len(self.sessions)
        return {
            "total$": f"{r['total$']:.4f}",
            "miss%": f"{r['miss$'] / r['total$'] * 100:.1f}" if r["total$"] else "-",
            "total$/Mvis": f"{self.think_cost / visible * 1e6:.2f}" if visible else "-",
            "ctx_p50": f"{int(statistics.median(c))}" if c else "-",
            "think/out": f"{self.think / self.think_out:.3f}" if self.think_out else "-",
            "sessions": str(n),
            "calls": str(self.calls),
            "calls/sess": f"{self.calls / n:.1f}",
            "ctx_p90": f"{percentile(c, 0.9)}" if len(c) >= 10 else "-",
            "ctx_max": f"{c[-1]}" if c else "-",
            "$/call": f"{r['total$'] / self.calls:.4f}",
            **{k: f"{r[k]:.4f}" for k in ("input$", "output$", "cacheRead$", "cacheWrite$", "miss$")},
            "total/out$": f"{r['total$'] / r['output$']:.1f}" if r["output$"] else "-",
            "total$/Mout": f"{r['total$'] / r['output_tok'] * 1e6:.2f}" if r["output_tok"] else "-",
            **{k + "_tok": f"{int(r[k + '_tok'])}" for k in PARTS},
        }


def render_table(calls: list[Call], dims: list[str], edges: list[int], wide: bool) -> str:
    groups, total = defaultdict(Group), Group()
    for c in calls:
        key = {"kind": c.kind, "model": c.model, "effort": c.effort, "ctx": bisect.bisect_right(edges, c.ctx)}
        groups[tuple(key[d] for d in dims)].add(c)
        total.add(c)

    def rank(seq, v):  # known values in their natural order, unknown ones last
        return seq.index(v) if v in seq else len(seq)

    def order(k):  # sort by kind, model name, effort low to high, context range
        v = dict(zip(dims, k))
        return (rank(KINDS, v.get("kind")), str(v.get("kind", "")), str(v.get("model", "")),
                rank(EFFORTS, v.get("effort")),
                v.get("ctx", 0))

    cols = list(total.metrics()) if wide else list(DEFAULT_COLUMNS)
    out = [dims + cols]
    for k in sorted(groups, key=order):
        label = [ctx_label(edges, v) if d == "ctx" else str(v) for d, v in zip(dims, k)]
        m = groups[k].metrics()
        out.append(label + [m[c] for c in cols])
    m = total.metrics()
    out.append(["TOTAL"] + [""] * (len(dims) - 1) + [m[c] for c in cols])
    w = [max(len(r[i]) for r in out) for i in range(len(out[0]))]
    return "\n".join("  ".join(c.ljust(w[i]) for i, c in enumerate(r)).rstrip() for r in out)
