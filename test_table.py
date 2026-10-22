import unittest

from table import render_table
from test_support import call


class RenderTableTest(unittest.TestCase):
    def test_kind_groups_sorted_assistant_first(self):
        calls = [call(kind="cache_warm"), call(), call(effort="medium")]
        lines = render_table(calls, ["kind", "model", "effort"], [], wide=False).splitlines()
        self.assertEqual([l.split()[:3] for l in lines[1:4]],
                         [["assistant", "p/m", "medium"], ["assistant", "p/m", "high"],
                          ["cache_warm", "p/m", "high"]])
        self.assertTrue(lines[-1].startswith("TOTAL"))


if __name__ == "__main__":
    unittest.main()
