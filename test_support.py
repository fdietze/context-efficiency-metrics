"""Builds Call records for chart and table tests."""
from pathlib import Path

from calls import PARTS, Call


def call(tree="t", kind="assistant", model="p/m", effort="high", cost=1.0, output=100,
         reasoning=50, ctx=1000, gap=None, miss=0.0, end=1_700_000_000.0) -> Call:
    return Call(tree=Path(tree), session=Path(tree), kind=kind, model=model, effort=effort,
                effort_source="message", start=end, end=end, gap=gap, ctx=ctx,
                tokens={k: output if k == "output" else 0 for k in PARTS},
                cost={**{k: 0.0 for k in PARTS}, "total": cost}, reasoning=reasoning, miss_cost=miss)
