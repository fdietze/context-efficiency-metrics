"""Bayesian bootstrap interval for a ratio of sums (e.g. dollars per visible token).

Calls inside one session tree are correlated (same task, same context), so the resampling
unit is the tree, not the call. Each draw weights the units with Dirichlet(1, ..., 1)
weights and recomputes sum(w*num) / sum(w*den). This is Rubin's Bayesian bootstrap: smooth
like a posterior, and it never drops a unit entirely, which matters with few trees.
"""
import random

QUANTILES = (0.05, 0.5, 0.95)  # a 90% interval and its median


def ratio_interval(units: list[tuple[float, float]], draws: int = 2000,
                   seed: int = 0) -> tuple[float, float, float] | None:
    """(5%, 50%, 95%) quantiles of sum(num)/sum(den) over per-unit (num, den) pairs.
    None if the denominator is never positive. Seeded, so reports are reproducible."""
    units = [(n, d) for n, d in units if d > 0 or n > 0]
    if not any(d > 0 for _, d in units):
        return None
    rng = random.Random(seed)
    ratios = []
    for _ in range(draws):
        # Normalizing Exp(1) draws gives Dirichlet(1) weights; the ratio is scale-free,
        # so the normalization can be skipped.
        num = den = 0.0
        for n, d in units:
            w = rng.expovariate(1.0)
            num += w * n
            den += w * d
        if den > 0:
            ratios.append(num / den)
    ratios.sort()
    return tuple(ratios[min(int(q * len(ratios)), len(ratios) - 1)] for q in QUANTILES)
