import math, unittest

from calls import NudgeArm
from chart_nudge_limit import MIN_PROMPTS, nudge_limit_data, nudge_limit_spec
from test_support import call

WINDOWS = {"p/m": 1_000_000, "p/x": 1_000_000, "p/small": 200_000}


def session(name, limit, cost_per_prompt, model="p/m", prompts=MIN_PROMPTS, low=100_000):
    arm = NudgeArm(tokens=limit, percent=75.0, low=low)
    # One call below the range's lower end (not counted), then per prompt one call that follows
    # the prompt and one task step.
    return ([call(tree=name, model=model, ctx=low - 1, cost=100.0, arm=arm, prompt=True)]
            + [call(tree=name, model=model, ctx=150_000, cost=cost_per_prompt / 2, arm=arm, prompt=p)
               for _ in range(prompts) for p in (True, False)])


class NudgeLimitTest(unittest.TestCase):
    def test_one_curve_over_models_with_different_prices(self):
        # Same U in both models, minimum at 200k; p/x costs 10x as much and covers only the
        # upper half, so a fit without a level per model would move the minimum up.
        calls = []
        for i, limit in enumerate(range(100_000, 300_001, 20_000)):
            calls += session(f"m{i}", limit, math.exp(((limit - 200_000) / 100_000) ** 2))
            if limit >= 200_000:
                calls += session(f"x{i}", limit, 10 * math.exp(((limit - 200_000) / 100_000) ** 2), model="p/x")
        rows = nudge_limit_data(calls, WINDOWS, draws=50)
        units = [r for r in rows if r["kind"] == "unit"]
        self.assertEqual(len(units), 17)
        for r in units:  # model level taken out, call below the range left out
            self.assertAlmostEqual(r["rel"], math.exp(((r["dose"] - 200_000) / 100_000) ** 2))
        (argmin,) = [r for r in rows if r["kind"] == "argmin"]
        self.assertAlmostEqual(argmin["lo"], 200_000, delta=1)
        self.assertAlmostEqual(argmin["hi"], 200_000, delta=1)

    def test_dose_is_capped_by_the_window_and_mixed_or_short_sessions_are_left_out(self):
        mixed = session("m", 150_000, 1.0) + [call(tree="m", ctx=150_000, arm=None)]
        calls = (session("a", 250_000, 1.0, model="p/small") + mixed
                 + session("s", 150_000, 1.0, prompts=MIN_PROMPTS - 1)
                 + session("u", 150_000, 1.0, model="p/unknown")
                 + [call(tree="n", ctx=150_000, prompt=True)] * MIN_PROMPTS)  # not randomized
        rows = nudge_limit_data(calls, WINDOWS)
        self.assertEqual([(r["model"], r["dose"], r["rel"]) for r in rows if r["kind"] == "unit"],
                         [("p/small", 150_000, None)])
        self.assertIn("1 session trees", nudge_limit_spec(rows)["title"]["subtitle"])


if __name__ == "__main__":
    unittest.main()
