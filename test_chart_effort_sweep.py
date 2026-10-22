import unittest

from chart_effort_sweep import COST, THINK, effort_sweep_data
from test_support import call


class EffortSweepTest(unittest.TestCase):
    def test_metrics_per_effort_and_hiding(self):
        calls = [call(tree=f"t{i}", effort="high", cost=2.0, output=100, reasoning=50) for i in range(3)]
        calls += [call(tree="t0", effort="max"), call(kind="cache_warm", tree="t9"),
                  call(tree="t8", reasoning=None)]
        rows = {(r["effort"], r["metric"]): r for r in effort_sweep_data(calls)}
        self.assertEqual(set(rows), {("high", COST), ("high", THINK)})  # max: 1 tree, hidden
        self.assertAlmostEqual(rows["high", COST]["mid"], 2.0 / 50 * 1e6)
        self.assertAlmostEqual(rows["high", THINK]["mid"], 50)
        self.assertTrue(rows["high", COST]["few"])


if __name__ == "__main__":
    unittest.main()
