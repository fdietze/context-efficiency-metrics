"""Parse Pi session files into one Call record per billed LLM call (functional core input).

Parse, don't validate: everything downstream (table.py, chart_*.py) works on Call
records only and never touches raw log entries.
"""
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from jsonl_entries import entries

PARTS = ("input", "output", "cacheRead", "cacheWrite")
# Side calls (tool summaries, compaction) do not log their model; kind="side" identifies them.
SIDE_MODEL = "-"
# Tools of the infinite-context extension. Calling one is context maintenance, not task work.
FOLD = "context_fold"
FOLD_TOOLS = frozenset({FOLD, "context_map", "context_search", "context_peek"})


@dataclass(frozen=True, slots=True)
class NudgeArm:
    """Reminder limit a branch was randomly assigned by the infinite-context extension
    (its settings.json `nudgeAtTokens: [low, high]`). The reminder fires at
    min(tokens, percent% of the model's context window)."""
    tokens: int           # drawn limit
    percent: float        # nudgeAtPercent
    low: int              # lower end of the range the limit was drawn from


@dataclass(frozen=True, slots=True)
class Call:
    tree: Path            # main session file; its subagents share it (the sampling unit)
    session: Path         # the file the call was logged in
    kind: str             # "assistant", "cache_warm" or "side"
    model: str            # provider/model
    effort: str           # thinking level, "unknown" if not recorded
    effort_source: str    # "message", "history" or "unknown"
    start: float          # request start, epoch seconds
    end: float            # response logged, epoch seconds
    gap: float | None     # start minus end of the previous main-chain call on this branch
    ctx: int              # input + cacheRead + cacheWrite tokens
    tokens: dict          # PARTS -> tokens
    cost: dict            # PARTS and "total" -> dollars
    reasoning: int | None  # reasoning tokens, None if the provider did not report them
    miss_cost: float      # dollars spent re-processing tokens that were cached before
    tools: tuple          # names of the tools this call invoked, in order
    fold_cost: float      # dollars spent on context folding (see read_calls)
    nudge_arm: NudgeArm | None  # randomized reminder limit in force, None if not randomized


@dataclass
class ReadStats:
    torn: list            # (path, line number) of torn lines
    effort_sources: Counter


def _epoch(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def _usage_of(e: dict):
    """(kind, model, own effort or None, start epoch or None, usage) for entries Pi counts
    toward session totals, else None."""
    t, m = e.get("type"), e.get("message") or {}
    if t == "message" and m.get("role") == "assistant":
        own = m.get("thinkingLevel") or m.get("providerThinkingLevel")
        start = m["timestamp"] / 1000 if isinstance(m.get("timestamp"), (int, float)) else None
        return ("assistant", f"{m.get('provider')}/{m.get('responseModel') or m.get('model')}",
                own, start, m.get("usage"))
    if t == "usage":
        return e.get("kind") or "usage", f"{e.get('provider')}/{e.get('model')}", None, None, e.get("usage")
    if t == "message" and m.get("role") == "toolResult" and m.get("usage"):
        return "side", SIDE_MODEL, None, None, m["usage"]
    if t in ("branch_summary", "compaction") and e.get("usage"):
        return "side", SIDE_MODEL, None, None, e["usage"]
    return None


def _nudge_arm(data) -> NudgeArm | None:
    """Parses an infinite-context:settings record; None unless the limit was drawn from a range."""
    if not isinstance(data, dict):
        return None
    t, pct, rng = data.get("nudgeAtTokens"), data.get("nudgeAtPercent"), data.get("nudgeAtTokensRange")
    if not (isinstance(rng, list) and len(rng) == 2 and all(isinstance(x, int) for x in rng)
            and isinstance(t, int) and isinstance(pct, (int, float)) and rng[0] <= t <= rng[1]):
        return None
    return NudgeArm(tokens=t, percent=float(pct), low=rng[0])


def _tools_of(e: dict) -> tuple:
    content = (e.get("message") or {}).get("content")
    if not isinstance(content, list):
        return ()
    return tuple(b.get("name") for b in content if isinstance(b, dict) and b.get("type") == "toolCall")


def read_calls(files: list[tuple[Path, Path]]) -> tuple[list[Call], ReadStats]:
    """Calls of (session file, tree) pairs in file order. Entries copied verbatim by /fork
    and /clone are counted once."""
    stats = ReadStats([], Counter())
    seen, calls = set(), []
    for f, tree in files:
        # Both maps follow the parent chain, so a call sees the state of the branch it was made on.
        level_at = {}  # entry id -> thinking level in force at that entry
        arm_at = {}    # entry id -> NudgeArm (or None) of the latest settings record
        # entry id -> (cached prefix tokens, end epoch, called context_fold) of the last main-chain call
        chain_at = {}
        for e in entries(f, stats.torn):
            eid, parent = e.get("id"), e.get("parentId")
            if e.get("type") == "thinking_level_change":
                level_at[eid] = e.get("thinkingLevel")
            elif parent in level_at:
                level_at[eid] = level_at[parent]
            if e.get("type") == "custom" and e.get("customType") == "infinite-context:settings":
                arm_at[eid] = _nudge_arm(e.get("data"))
            elif parent in arm_at:
                arm_at[eid] = arm_at[parent]
            hit = _usage_of(e)
            u = hit[4] if hit else None
            ctx = sum((u or {}).get(k, 0) for k in ("input", "cacheRead", "cacheWrite"))
            # Side calls use other prompts; failed calls (no tokens) leave the cache untouched.
            on_chain = bool(hit) and hit[0] != "side" and ctx > 0
            before = chain_at.get(parent)
            end = _epoch(e["timestamp"]) if u and e.get("timestamp") else None
            tools = _tools_of(e) if hit else ()
            if on_chain:
                chain_at[eid] = (u.get("cacheRead", 0) + u.get("cacheWrite", 0), end, FOLD in tools)
            elif parent in chain_at:
                chain_at[eid] = chain_at[parent]
            if not u:
                continue
            dedup = (eid, e.get("timestamp"))
            if dedup in seen:
                continue
            seen.add(dedup)
            kind, model, own, start, u = hit
            if own:
                effort, src = own, "message"
            elif level_at.get(parent):
                effort, src = level_at[parent], "history"
            else:
                effort, src = "unknown", "unknown"
            stats.effort_sources[src] += 1
            start = start if start is not None else end
            miss, gap = 0.0, None
            if on_chain and before is not None:
                # Tokens cached at the previous call but not read now were processed again.
                # Measured on real logs this shortfall is either 0 or > 500 tokens, so no
                # tolerance is needed. Priced at this call's average uncached-token price.
                uncached = u.get("input", 0) + u.get("cacheWrite", 0)
                missed = min(uncached, max(0, before[0] - u.get("cacheRead", 0)))
                if missed:
                    c = u.get("cost", {})
                    miss = missed * (c.get("input", 0) + c.get("cacheWrite", 0)) / uncached
                if start is not None and before[1] is not None:
                    gap = max(0.0, start - before[1])
            c = u.get("cost", {})
            # Folding costs the turn that calls a folding tool (the turn exists only for
            # maintenance; the rare turn that mixes in task tools is counted whole too) minus its
            # own miss, which a task turn in its place would have paid too (mostly cache expiry
            # after a pause). Folding does cause the miss of the next main-chain call, because a
            # fold rewrites the cached prompt prefix.
            fold = c.get("total", 0) - miss if FOLD_TOOLS.intersection(tools) else 0.0
            if before is not None and before[2]:
                fold += miss
            calls.append(Call(
                tree=tree, session=f, kind=kind, model=model, effort=effort, effort_source=src,
                start=start, end=end, gap=gap, ctx=ctx,
                tokens={k: u.get(k, 0) for k in PARTS},
                cost={k: c.get(k, 0) for k in PARTS + ("total",)},
                reasoning=u["reasoning"] if "reasoning" in u else None,
                miss_cost=miss, tools=tools, fold_cost=fold, nudge_arm=arm_at.get(parent)))
    return calls, stats
