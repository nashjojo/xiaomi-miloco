import unittest

from evaluate import answer, memory, observe, scenario, score


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.truth, self.queries = scenario(60)
        self.clean, _ = observe(self.truth, "clean")

    def test_clean_and_long_exact_temporal_retrieval(self):
        for duration in (60, 18000):
            truth, questions = scenario(duration)
            records, _ = observe(truth, "clean")
            self.assertEqual(score(records, questions)["overall"]["accuracy"], 1)
            self.assertEqual(len(truth), duration//6)

    def test_gate_loss_cannot_be_reconstructed_from_future_state(self):
        records, losses = observe(self.truth, "gate")
        result = score(records, self.queries)
        self.assertEqual(losses["injected_gate_skip"], 1)
        self.assertEqual(result["by_kind"]["historical_location"]["correct"], 0)
        self.assertEqual(result["by_kind"]["last_seen_location"]["correct"], 1)

    def test_unknown_after_return_is_not_reidentified(self):
        records, _ = observe(self.truth, "identity")
        self.assertEqual(score(records, self.queries)["by_kind"]["return_identity"]["answered"], 0)

    def test_cross_camera_track_collision_does_not_link_people(self):
        records, _ = observe(self.truth, "cross_camera")
        self.assertEqual(score(records, self.queries)["by_kind"]["cross_camera"]["answered"], 0)

    def test_hidden_action_and_occluded_current_are_different(self):
        records, _ = observe(self.truth, "occlusion")
        result = score(records, self.queries)
        self.assertEqual(result["by_kind"]["mover"]["correct"], 0)
        self.assertEqual(result["by_kind"]["occluded_current"]["correct"], 1)

    def test_summary_and_profile_do_not_keep_event_history(self):
        self.assertLess(score(memory(self.clean, "periodic"), self.queries)["overall"]["accuracy"], 1)
        self.assertEqual(memory(self.clean, "profile"), [])

    def test_budget_loses_old_events_and_no_future_leak(self):
        truth, queries = scenario(18000)
        records, _ = observe(truth, "clean")
        self.assertIsNone(answer(memory(records, "raw", budget=10), queries[0])["value"])
        q = dict(self.queries[0], asked_at=0)
        self.assertIsNone(answer(self.clean, q)["value"])

    def test_unknown_not_false_negative_and_truth_is_separate(self):
        before = [dict(e) for e in self.truth]
        observe(self.truth, "combined")
        self.assertEqual(before, self.truth)
        result = score([], self.queries)
        self.assertEqual(result["overall"]["correct"], 1)  # justified abstention only


if __name__ == "__main__":
    unittest.main()
