import unittest

from bayesian_bootstrap import ratio_interval


class RatioIntervalTest(unittest.TestCase):
    def test_identical_units_give_a_point(self):
        lo, mid, hi = ratio_interval([(2.0, 1.0)] * 5)
        self.assertAlmostEqual(lo, 2.0)
        self.assertAlmostEqual(hi, 2.0)

    def test_interval_brackets_pooled_ratio_and_is_seeded(self):
        units = [(1.0, 1.0), (3.0, 1.0), (2.0, 2.0), (9.0, 3.0)]
        lo, mid, hi = ratio_interval(units)
        self.assertLess(lo, 15 / 7)
        self.assertGreater(hi, 15 / 7)
        self.assertEqual(ratio_interval(units), (lo, mid, hi))

    def test_no_denominator(self):
        self.assertIsNone(ratio_interval([(1.0, 0.0)]))
        self.assertIsNone(ratio_interval([]))


if __name__ == "__main__":
    unittest.main()
