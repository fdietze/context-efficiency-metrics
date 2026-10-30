import dataclasses, unittest

from chart_fold_payoff import fold_payoff_data
from test_support import call

READ, UNCACHED = 1e-6, 12.5e-6  # $ per token


def turn(ctx, tools=(), fold=0.0, miss=0.0, read=None, session="s"):
    """A call that re-reads `read` cached tokens (default: all of ctx) and writes the rest."""
    read = ctx if read is None else read
    c = call(tree=session, ctx=ctx, tools=tools, fold=fold, miss=miss)
    return dataclasses.replace(
        c, tokens={**c.tokens, "cacheRead": read, "cacheWrite": ctx - read},
        cost={**c.cost, "cacheRead": read * READ, "cacheWrite": (ctx - read) * UNCACHED})


class FoldPayoffTest(unittest.TestCase):
    def test_cost_and_savings_of_one_fold(self):
        calls = [
            turn(100_000),
            turn(100_000, tools=("context_map",), fold=0.1),
            turn(101_000, tools=("context_fold",), fold=0.2),
            # The fold freed 60k; this call's miss is the fold's (cost), not a saving.
            turn(41_000, read=1_000, fold=0.3, miss=0.5),
            turn(42_000),
            # After a pause the cache expired: 42k re-written, 60k fewer than without the fold
            # is capped at what was missed.
            turn(43_000, read=0, miss=42_000 * UNCACHED),
            # A look-only run frees nothing: not a saving, and the horizon goes on.
            turn(43_000, tools=("context_map",), fold=0.1),
            turn(43_000),
            # The next fold ends the horizon.
            turn(43_000, tools=("context_fold",), fold=0.1),
            turn(40_000),  # frees 7%: another bin
        ]
        (summary, fold, _, *bins) = fold_payoff_data(calls)
        self.assertEqual((summary["folds"], summary["grew"], summary["unfollowed"]), (2, 0, 0))
        # Freed from the run's first call: 100k -> 41k. Later task calls: 41k (read 1k), 42k
        # (read 42k), 43k (read 0, so no read price known), 43k (read 43k).
        save = 59_000 * READ * 3 + 42_000 * UNCACHED
        self.assertAlmostEqual(fold["freed"], 59_000)
        self.assertAlmostEqual(fold["share"], 0.59)
        self.assertEqual(fold["later"], 4)
        self.assertAlmostEqual(fold["ratio"], save / 0.6)
        self.assertAlmostEqual([b for b in bins if b["share"] == 0.55][0]["mid"], save / 0.6)

    def test_a_run_that_folds_twice_counts_both_folds(self):
        calls = [turn(300_000, tools=("context_fold",), fold=0.2),
                 turn(150_000, tools=("context_fold",), read=10_000, fold=0.2),
                 turn(50_000, read=10_000, fold=0.1), turn(50_000)]
        (summary, fold, *_) = fold_payoff_data(calls)
        self.assertEqual(summary["folds"], 1)
        self.assertAlmostEqual(fold["share"], 250_000 / 300_000)

    def test_folds_left_out(self):
        calls = [turn(100_000), turn(100_000, tools=("context_fold",), fold=0.2),
                 turn(101_000, fold=0.1),  # freed nothing
                 turn(100_000, tools=("context_fold",), fold=0.2)]  # ends the session
        summary = fold_payoff_data(calls)[0]
        self.assertEqual((summary["folds"], summary["grew"], summary["unfollowed"]), (0, 1, 1))


if __name__ == "__main__":
    unittest.main()
