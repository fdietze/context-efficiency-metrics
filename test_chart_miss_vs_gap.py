import unittest

from chart_miss_vs_gap import MIN_CALLS, miss_vs_gap_data
from test_support import call


class MissVsGapTest(unittest.TestCase):
    def test_bins_per_provider(self):
        calls = [call(model="anthropic/m", gap=10) for _ in range(MIN_CALLS)]
        calls += [call(model="anthropic/m", gap=400, miss=1.0) for _ in range(MIN_CALLS)]
        calls += [call(model="openai/m", gap=10)]  # thin bin, dropped
        calls += [call(model="anthropic/m", gap=None)]  # first call of a chain, no gap
        rows = miss_vs_gap_data(calls)
        self.assertEqual([(r["provider"], r["bin"], r["p"]) for r in rows],
                         [("anthropic", "0-30s", 0.0), ("anthropic", "6m-10m", 1.0)])


if __name__ == "__main__":
    unittest.main()
