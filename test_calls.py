import json, tempfile, unittest
from pathlib import Path

from calls import NudgeArm, read_calls


def assistant(eid, parent, end_iso, start_ms, read, write, inp=0, cost_in=0.0, cost_w=0.0, effort="high",
              tools=()):
    usage = {"input": inp, "output": 10, "cacheRead": read, "cacheWrite": write, "reasoning": 4,
             "cost": {"input": cost_in, "output": 0.1, "cacheRead": 0.0, "cacheWrite": cost_w,
                      "total": cost_in + cost_w + 0.1}}
    return {"type": "message", "id": eid, "parentId": parent, "timestamp": end_iso,
            "message": {"role": "assistant", "provider": "anthropic", "model": "m",
                        "thinkingLevel": effort, "timestamp": start_ms, "usage": usage,
                        "content": [{"type": "toolCall", "name": t, "arguments": {}} for t in tools]}}


class ReadCallsTest(unittest.TestCase):
    def read(self, lines):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "s.jsonl"
            f.write_text("".join(json.dumps(e) + "\n" for e in lines))
            return read_calls([(f, f)])[0]

    def test_miss_gap_and_kind(self):
        t0 = 1_700_000_000
        iso = lambda s: f"2023-11-14T22:{s // 60:02d}:{s % 60:02d}Z"  # t0 is 22:13:20 UTC
        calls = self.read([
            {"type": "session", "id": "s"},
            assistant("a", "s", iso(800), (t0 + 0) * 1000, read=0, write=1000, cost_w=1.0),
            # Cache-warm ping 60 s later re-reads the whole prefix: on chain, no miss.
            {"type": "usage", "id": "w", "parentId": "a", "timestamp": iso(860), "kind": "cache_warm",
             "provider": "anthropic", "model": "m",
             "usage": {"input": 0, "output": 1, "cacheRead": 1000, "cacheWrite": 0, "cost": {"total": 0.01}}},
            # 400 s after the ping, only 200 of 1000 cached tokens are read: 800 missed.
            assistant("b", "w", iso(1270), (t0 + 460) * 1000, read=200, write=1000, cost_w=2.0),
        ])
        self.assertEqual([c.kind for c in calls], ["assistant", "cache_warm", "assistant"])
        a, w, b = calls
        self.assertIsNone(a.gap)
        self.assertEqual(w.miss_cost, 0)
        self.assertAlmostEqual(b.gap, 400)
        self.assertAlmostEqual(b.miss_cost, 800 / 1000 * 2.0)  # missed share of uncached cost
        self.assertEqual(b.effort, "high")
        self.assertEqual(b.reasoning, 4)

    def test_fold_cost_is_maintenance_turns_plus_the_miss_after_a_fold(self):
        iso = lambda s: f"2023-11-14T22:20:{s:02d}Z"
        ms = lambda s: (1_700_000_400 + s) * 1000
        calls = self.read([
            assistant("a", None, iso(1), ms(0), read=0, write=1000, cost_w=1.0, tools=("context_map",)),
            assistant("f", "a", iso(3), ms(2), read=1000, write=0, tools=("context_fold",)),
            # The fold rewrote the prefix: only 100 of 1000 cached tokens are read again.
            assistant("b", "f", iso(5), ms(4), read=100, write=400, cost_w=0.4, tools=("bash",)),
            # A miss after a task turn is not caused by folding, so a folding turn pays only its
            # cost without that miss.
            assistant("c", "b", iso(7), ms(6), read=0, write=500, cost_w=0.5, tools=("context_map",)),
            # A folding turn right after a fold: its miss is caused by folding too.
            assistant("g", "c", iso(9), ms(8), read=500, write=0, tools=("context_fold",)),
            assistant("h", "g", iso(11), ms(10), read=0, write=500, cost_w=0.5, tools=("context_map",)),
        ])
        a, f, b, c, g, h = calls
        self.assertEqual(f.tools, ("context_fold",))
        self.assertAlmostEqual(a.fold_cost, a.cost["total"])
        self.assertAlmostEqual(f.fold_cost, f.cost["total"])
        self.assertAlmostEqual(b.fold_cost, b.miss_cost)
        self.assertAlmostEqual(b.miss_cost, 0.4)  # 400 missed of 400 uncached
        self.assertGreater(c.miss_cost, 0)
        self.assertAlmostEqual(c.fold_cost, c.cost["total"] - c.miss_cost)
        self.assertGreater(h.miss_cost, 0)
        self.assertAlmostEqual(h.fold_cost, h.cost["total"])

    def test_nudge_arm_follows_the_branch_settings_record(self):
        record = lambda eid, parent, data: {"type": "custom", "customType": "infinite-context:settings",
                                            "id": eid, "parentId": parent, "data": data}
        drawn = {"nudgeAtTokens": 180_000, "nudgeAtPercent": 75, "nudgeAtTokensRange": [100_000, 300_000]}
        calls = self.read([
            record("r", None, drawn),
            assistant("a", "r", "2023-11-14T22:20:01Z", 1_700_000_400_000, read=0, write=10),
            record("f", "a", {"nudgeAtTokens": 150_000, "nudgeAtPercent": 75}),  # fixed: not randomized
            assistant("b", "f", "2023-11-14T22:20:03Z", 1_700_000_402_000, read=10, write=10),
        ])
        self.assertEqual(calls[0].nudge_arm, NudgeArm(tokens=180_000, percent=75.0, low=100_000))
        self.assertIsNone(calls[1].nudge_arm)

    def test_after_prompt_marks_the_first_call_after_external_input(self):
        msg = lambda eid, parent, role: {"type": "message", "id": eid, "parentId": parent,
                                         "message": {"role": role, "content": []}}
        custom = lambda eid, parent, kind: {"type": "custom_message", "customType": kind, "id": eid,
                                            "parentId": parent, "content": ""}
        ms = lambda s: (1_700_000_400 + s) * 1000
        iso = lambda s: f"2023-11-14T22:20:{s:02d}Z"
        calls = self.read([
            msg("u", None, "user"),
            assistant("a", "u", iso(1), ms(0), read=0, write=10),
            msg("t", "a", "toolResult"),
            assistant("b", "t", iso(3), ms(2), read=10, write=10),
            custom("n", "b", "infinite-context/nudge"),  # a reminder is not external input
            assistant("c", "n", iso(5), ms(4), read=20, write=10),
            custom("m", "c", "agent-message"),
            msg("t2", "m", "toolResult"),
            assistant("d", "t2", iso(7), ms(6), read=30, write=10),
        ])
        self.assertEqual([c.after_prompt for c in calls], [True, False, False, True])

    def test_fork_copies_counted_once(self):
        e = assistant("a", None, "2023-11-14T22:13:20Z", 1_700_000_000_000, read=0, write=10)
        self.assertEqual(len(self.read([e, e])), 1)


if __name__ == "__main__":
    unittest.main()
