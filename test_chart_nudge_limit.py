import unittest

from calls import NudgeArm
from chart_nudge_limit import MIN_PROMPTS, _units, nudge_limit_data, nudge_limit_spec
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
    def test_bars_take_out_the_model_price_level(self):
        # Per model, sessions below 150k cost 1 per prompt and those above 2; p/x costs 10x as
        # much. With the model's average (1.5) taken out, the bars are 2/3 and 4/3 for both.
        calls = []
        for i, limit in enumerate((110_000, 120_000, 130_000, 160_000, 170_000, 180_000)):
            cost = 1.0 if limit < 150_000 else 2.0
            calls += session(f"m{i}", limit, cost) + session(f"x{i}", limit, 10 * cost, model="p/x")
        bins = [r for r in nudge_limit_data(calls, WINDOWS) if r["kind"] == "bin"]
        self.assertEqual([r["range"] for r in bins], ["100-150k", "150-200k"])
        for r, want in zip(bins, (2 / 3, 4 / 3)):
            for q in ("lo", "mid", "hi"):
                self.assertAlmostEqual(r[q], want)

    def test_bins_with_too_few_trees_get_no_bar(self):
        calls = sum((session(t, 120_000, 1.0) for t in "ab"), []) + sum((session(t, 220_000, 1.0) for t in "cde"), [])
        rows = nudge_limit_data(calls, WINDOWS)
        self.assertEqual([r["range"] for r in rows if r["kind"] == "bin"], ["200-250k"])

    def test_dose_is_capped_by_the_window_and_mixed_or_short_sessions_are_left_out(self):
        mixed = session("m", 150_000, 1.0) + [call(tree="m", ctx=150_000, arm=None)]
        calls = (session("a", 250_000, 1.0, model="p/small") + mixed
                 + session("s", 150_000, 1.0, prompts=MIN_PROMPTS - 1)
                 + session("u", 150_000, 1.0, model="p/unknown")
                 + [call(tree="n", ctx=150_000, prompt=True)] * MIN_PROMPTS)  # not randomized
        self.assertEqual([(u["model"], u["dose"]) for u in _units(calls, WINDOWS)], [("p/small", 150_000)])
        rows = nudge_limit_data(calls, WINDOWS)
        self.assertEqual(rows, [{"kind": "summary", "sessions": 1, "trees": 1}])
        self.assertIn("1 session trees", nudge_limit_spec(rows)["title"]["subtitle"])


if __name__ == "__main__":
    unittest.main()
