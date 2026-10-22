import unittest
from datetime import datetime

from chart_daily_spend import OVERHEAD, daily_spend_data
from test_support import call


class DailySpendTest(unittest.TestCase):
    def test_overhead_counted_once_and_partial_day_dropped(self):
        noon = datetime(2026, 10, 2, 12).timestamp()
        calls = [call(cost=5.0, miss=2.0, end=noon),
                 call(kind="cache_warm", cost=0.5, miss=0.5, end=noon),  # failed ping
                 call(cost=9.0, end=noon - 86400)]  # Oct 1, the day the cutoff falls into
        rows = {(r["day"], r.get("model") or r["series"]): r["usd"] for r in daily_spend_data(calls, cutoff=noon - 86400 - 3600)}
        self.assertEqual(rows, {("2026-10-02", "p/m"): 5.5, ("2026-10-02", OVERHEAD[0]): 2.0,
                                ("2026-10-02", OVERHEAD[1]): 0.5})


if __name__ == "__main__":
    unittest.main()
