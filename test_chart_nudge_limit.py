import unittest

from calls import NudgeArm
from chart_nudge_limit import MIN_STEPS, nudge_limit_data
from test_support import call

WINDOWS = {"p/m": 1_000_000, "p/small": 200_000}


def session(name, limit, cost_per_step, model="p/m", ctx=150_000, steps=MIN_STEPS, low=100_000):
    arm = NudgeArm(tokens=limit, percent=75.0, low=low)
    # One call below the range's lower end (not counted), then the steps.
    return ([call(tree=name, model=model, ctx=low - 1, cost=100.0, arm=arm)]
            + [call(tree=name, model=model, ctx=ctx, cost=cost_per_step, arm=arm) for _ in range(steps)])


class NudgeLimitTest(unittest.TestCase):
    def test_finds_the_minimum_of_a_u(self):
        calls = []
        for i, limit in enumerate(range(100_000, 300_001, 20_000)):
            calls += session(f"t{i}", limit, 1 + ((limit - 200_000) / 100_000) ** 2)
        rows = nudge_limit_data(calls, WINDOWS, draws=50)
        units = [r for r in rows if r["kind"] == "unit"]
        self.assertEqual(len(units), 11)
        self.assertAlmostEqual(min(r["usd"] for r in units), 1.0)  # call below the range left out
        (argmin,) = [r for r in rows if r["kind"] == "argmin"]
        self.assertAlmostEqual(argmin["mid"], 200_000, delta=1)

    def test_dose_is_capped_by_the_window_and_mixed_or_short_sessions_are_left_out(self):
        mixed = session("m", 150_000, 1.0) + [call(tree="m", ctx=150_000, arm=None)]
        calls = (session("a", 250_000, 1.0, model="p/small") + mixed
                 + session("s", 150_000, 1.0, steps=MIN_STEPS - 1)
                 + session("u", 150_000, 1.0, model="p/unknown")
                 + [call(tree="n", ctx=150_000)] * MIN_STEPS)  # not randomized
        rows = nudge_limit_data(calls, WINDOWS)
        self.assertEqual([(r["model"], r["dose"]) for r in rows], [("p/small", 150_000)])


if __name__ == "__main__":
    unittest.main()
