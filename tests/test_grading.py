"""Regression checks for the general scoring policy; no Sleeper requests."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fantasy.grading import score_pick, evaluate, match_player, load_rankings, RANKINGS_PATH, SCORING_VERSION


class GradingChecks(unittest.TestCase):
    def test_scoring_examples_and_version(self):
        self.assertEqual(SCORING_VERSION, '2026-softer-misses-v15')
        # A severe early miss now has a 2x ceiling; modest misses keep their old weight.
        self.assertEqual(score_pick(13, 37)['surplus'], -40.5)
        self.assertEqual(score_pick(8, 12)['surplus'], -4.1)
        self.assertEqual(score_pick(13, 26)['surplus'], -21.9)
        self.assertEqual(score_pick(98, 33)['surplus'], 66.6)

    def test_slot_limits_and_rank_monotonicity(self):
        for pick in range(1, 161):
            previous = float('inf')
            for rank in range(1, 181):
                scored = score_pick(pick, rank)
                value = scored['surplus']
                self.assertLessEqual(-scored['maxLoss'], value)
                self.assertLessEqual(value, scored['maxGain'])
                self.assertLessEqual(value, previous, 'A worse ranking must not improve the score')
                self.assertGreaterEqual(value * (min(pick, 160) - min(rank, 160)), 0)
                if rank > pick:
                    self.assertGreaterEqual(scored['valueMultiplier'], 1)
                    self.assertLessEqual(scored['valueMultiplier'], 2)
                previous = value

    def test_missing_rank_and_evaluation_total(self):
        self.assertEqual(score_pick(13, None)['surplus'], 0)
        result = evaluate([{'overallPick': 13, 'round': 2, 'playerName': 'Chase Brown', 'position': 'RB'}])
        self.assertEqual(result['totalSurplus'], sum(
            p['surplus'] for p in result['picks'] if not p['ignored']))

    def test_duplicate_rankings_names_are_not_silently_matched(self):
        _, rankings, _ = load_rankings(RANKINGS_PATH)
        for player in ['Kyle Williams', 'Kyle William']:
            self.assertEqual(match_player(player, 'WR', rankings), (None, 'ambiguous'))
        result = evaluate([{'overallPick': 100, 'round': 10,
                            'playerName': 'Kyle Williams', 'position': 'WR'}])
        self.assertTrue(result['picks'][0]['ignored'])
        self.assertIsNone(result['picks'][0]['current_rank'])
        self.assertEqual(result['letterGrade'], 'N/A')
        self.assertEqual(result['warnings'][0]['code'], 'ambiguous')


if __name__ == '__main__':
    unittest.main()
