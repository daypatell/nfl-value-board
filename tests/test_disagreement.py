"""
Offline unit tests for the model-vs-market disagreement classifier.

No network and no API key: every case is hand-built numbers, so this runs
anywhere and can't go red because a feed changed. Run with:

    python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "scripts"),
)

from model import (  # noqa: E402
    DISAGREE_FLIP,
    DISAGREE_MARGIN,
    DISAGREE_NO_LINE,
    DISAGREE_NONE,
    DISAGREE_SHARP_ALIGNED,
    american_to_probability,
    classify_disagreement,
    devig_home_probability,
    evaluate_game,
    favorite_from_prob,
    sharp_side_from_move,
)
from teams import normalize_abbr  # noqa: E402


class TestDevig(unittest.TestCase):

    def test_devigged_pair_sums_to_one(self):
        home = devig_home_probability(-150, +130)
        self.assertIsNotNone(home)
        away = 1.0 - home
        self.assertAlmostEqual(home + away, 1.0, places=9)

    def test_favorite_survives_devig(self):
        # -150 home / +130 away: home is clearly favoured.
        self.assertGreater(devig_home_probability(-150, +130), 0.5)

    def test_pickem_devigs_to_exactly_half(self):
        # THE case that motivates de-vigging: raw implied probabilities both
        # read above 50%, which would name two favourites in one game.
        self.assertGreater(american_to_probability(-110), 0.5)
        self.assertAlmostEqual(
            devig_home_probability(-110, -110), 0.5, places=9
        )

    def test_missing_price_returns_none(self):
        self.assertIsNone(devig_home_probability(None, +130))
        self.assertIsNone(devig_home_probability(-150, None))


class TestFavoriteFromProb(unittest.TestCase):

    def test_sides(self):
        self.assertEqual(favorite_from_prob(0.61), "home")
        self.assertEqual(favorite_from_prob(0.39), "away")

    def test_exact_coin_flip_has_no_favorite(self):
        self.assertIsNone(favorite_from_prob(0.5))
        self.assertIsNone(favorite_from_prob(None))


class TestSharpSide(unittest.TestCase):

    def test_direction(self):
        self.assertEqual(sharp_side_from_move(+4.0), "home")
        self.assertEqual(sharp_side_from_move(-4.0), "away")

    def test_small_moves_are_noise(self):
        self.assertIsNone(sharp_side_from_move(0.4))
        self.assertIsNone(sharp_side_from_move(-0.4))
        self.assertIsNone(sharp_side_from_move(None))


class TestClassification(unittest.TestCase):

    def test_favorite_flip(self):
        # Market: home favoured (~0.60 de-vigged). Model: away wins.
        label, gap = classify_disagreement(0.35, 0.60)
        self.assertEqual(label, DISAGREE_FLIP)
        self.assertAlmostEqual(gap, 25.0, places=6)

    def test_margin_mismatch(self):
        # Both favour home, but 13pp apart.
        label, gap = classify_disagreement(0.75, 0.62)
        self.assertEqual(label, DISAGREE_MARGIN)
        self.assertAlmostEqual(gap, 13.0, places=6)

    def test_agreement(self):
        label, gap = classify_disagreement(0.63, 0.62)
        self.assertEqual(label, DISAGREE_NONE)
        self.assertAlmostEqual(gap, 1.0, places=6)

    def test_threshold_is_strict_greater_than(self):
        # Exactly at the threshold is agreement, just past it is a mismatch.
        self.assertEqual(
            classify_disagreement(0.65, 0.62, threshold_pp=3.0)[0],
            DISAGREE_NONE,
        )
        self.assertEqual(
            classify_disagreement(0.6501, 0.62, threshold_pp=3.0)[0],
            DISAGREE_MARGIN,
        )

    def test_threshold_is_configurable(self):
        self.assertEqual(
            classify_disagreement(0.68, 0.62, threshold_pp=10.0)[0],
            DISAGREE_NONE,
        )

    def test_no_line(self):
        label, gap = classify_disagreement(0.55, None)
        self.assertEqual(label, DISAGREE_NO_LINE)
        self.assertIsNone(gap)

    def test_pickem_market_cannot_flip(self):
        # De-vigged market is an exact 50/50, so there is no market favourite
        # to disagree with - this is a margin call, not a flip.
        label, gap = classify_disagreement(0.55, 0.5)
        self.assertEqual(label, DISAGREE_MARGIN)
        self.assertAlmostEqual(gap, 5.0, places=6)

    def test_big_gap_on_same_favorite_is_never_a_flip(self):
        # Both say home, 30pp apart. Severity must stay MARGIN MISMATCH.
        self.assertEqual(
            classify_disagreement(0.95, 0.65)[0], DISAGREE_MARGIN
        )


class TestSharpAlignment(unittest.TestCase):

    def test_sharp_money_agreeing_with_model_upgrades_a_flip(self):
        # Market favours home, model favours away, line moving toward away.
        label, _ = classify_disagreement(0.35, 0.60, sharp_side="away")
        self.assertEqual(label, DISAGREE_SHARP_ALIGNED)

    def test_sharp_money_against_model_stays_a_flip(self):
        label, _ = classify_disagreement(0.35, 0.60, sharp_side="home")
        self.assertEqual(label, DISAGREE_FLIP)

    def test_sharp_money_does_not_upgrade_a_margin_mismatch(self):
        # No flip, so alignment is not the headline signal.
        label, _ = classify_disagreement(0.75, 0.62, sharp_side="home")
        self.assertEqual(label, DISAGREE_MARGIN)

    def test_no_line_movement_leaves_flip_alone(self):
        label, _ = classify_disagreement(0.35, 0.60, sharp_side=None)
        self.assertEqual(label, DISAGREE_FLIP)


class TestEndToEnd(unittest.TestCase):
    """evaluate_game should populate the new fields coherently."""

    def test_flip_surfaces_on_a_real_evaluate_game_call(self):
        pick = evaluate_game(
            "HOU", "BAL",
            home_elo=1400.0, away_elo=1600.0,   # model likes the away team
            home_ml=-150, away_ml=+130,          # market likes the home team
            seed=7,
        )
        self.assertLess(pick.model_home_win_prob, 0.5)
        self.assertGreater(pick.market_home_win_prob_devig, 0.5)
        self.assertEqual(pick.disagreement, DISAGREE_FLIP)
        self.assertGreater(pick.mismatch_pp, 0.0)

    def test_sharp_alignment_surfaces_end_to_end(self):
        pick = evaluate_game(
            "HOU", "BAL",
            home_elo=1400.0, away_elo=1600.0,
            home_ml=-150, away_ml=+130,
            seed=7,
            line_move_pp=-6.0,   # implied prob moving toward the away team
        )
        self.assertEqual(pick.sharp_side, "away")
        self.assertEqual(pick.disagreement, DISAGREE_SHARP_ALIGNED)

    def test_no_market_price_yields_no_line(self):
        pick = evaluate_game(
            "HOU", "BAL",
            home_elo=1500.0, away_elo=1500.0,
            home_ml=None, away_ml=None,
            seed=7,
        )
        self.assertEqual(pick.disagreement, DISAGREE_NO_LINE)
        self.assertIsNone(pick.mismatch_pp)
        self.assertIsNone(pick.market_home_win_prob_devig)

    def test_edge_pct_still_uses_the_raw_vigged_price(self):
        # The de-vigged number is for classification only; it must not leak
        # into edge/EV, which have to reflect the price actually on offer.
        pick = evaluate_game(
            "HOU", "BAL",
            home_elo=1600.0, away_elo=1400.0,
            home_ml=-150, away_ml=+130,
            seed=7,
        )
        self.assertAlmostEqual(
            pick.market_home_win_prob,
            american_to_probability(-150),
            places=9,
        )
        self.assertNotAlmostEqual(
            pick.market_home_win_prob,
            pick.market_home_win_prob_devig,
            places=4,
        )


class TestAbbreviationNormalisation(unittest.TestCase):
    """The silent-drop bug this feature's matching code depends on."""

    def test_known_aliases(self):
        self.assertEqual(normalize_abbr("WSH"), "WAS")   # ESPN
        self.assertEqual(normalize_abbr("JAC"), "JAX")   # CLEATZ
        self.assertEqual(normalize_abbr("LA"), "LAR")    # CLEATZ (Rams)

    def test_canonical_and_unknown_pass_through(self):
        self.assertEqual(normalize_abbr("KC"), "KC")
        self.assertEqual(normalize_abbr("ZZZ"), "ZZZ")
        self.assertIsNone(normalize_abbr(None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
