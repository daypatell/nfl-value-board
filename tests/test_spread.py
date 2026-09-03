"""
Offline regression tests for the spread cover-probability math.

The original implementation used +home_spread as the threshold instead of
-home_spread and divided by NFL_MARGIN_SD * sqrt(2), which reported LAC -10.5
off a +16.08 expected margin as a 97.6% cover instead of 66.0%. That fabricated
a ~+45pp edge on nearly every spread, so the spread always beat the moneyline
for best_bet and the whole board filled with fake ELITE VALUE.

The anchor property: when the expected margin exactly equals the spread, the
cover probability must be exactly 50%.
"""
from __future__ import annotations

import math
import os
import sys
import unittest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "scripts")
)

from model import NFL_MARGIN_SD, evaluate_game  # noqa: E402


def cover_prob(pick) -> float:
    """
    Home-side cover probability.

    evaluate_game stores whichever of the two spread sides scored higher in
    pick.spread, so it is not reliably the home side - normalise before
    asserting anything about the home team.
    """
    sp = pick.spread
    if sp.pick.startswith("HOME"):
        return sp.model_probability
    return 1.0 - sp.model_probability


def build(home_elo, away_elo, home_spread):
    """Spread-only evaluation at -110 a side."""
    return evaluate_game(
        "HOME", "AWAY",
        home_elo=home_elo, away_elo=away_elo,
        home_ml=None, away_ml=None,
        home_spread=home_spread, away_spread=-home_spread,
        home_spread_odds=-110, away_spread_odds=-110,
        is_neutral_site=True,          # keeps the margin purely Elo-driven
        seed=3,
    )


class TestSpreadCoverProbability(unittest.TestCase):

    def test_margin_equal_to_spread_is_a_coin_flip(self):
        # Neutral site, 250 Elo gap -> 10.0 point expected margin.
        pick = build(1625.0, 1375.0, -10.0)
        self.assertAlmostEqual(pick.mean_margin, 10.0, places=6)
        self.assertAlmostEqual(cover_prob(pick), 0.5, places=6)

    def test_pickem_at_zero_margin_is_a_coin_flip(self):
        pick = build(1500.0, 1500.0, 0.0)
        self.assertAlmostEqual(cover_prob(pick), 0.5, places=6)

    def test_the_regression_case(self):
        # LAC -10.5 with a +16.08 expected margin: 66.0%, not 97.6%.
        pick = build(1622.0 + 48.0, 1268.0, -10.5)
        self.assertAlmostEqual(pick.mean_margin, 16.08, places=2)
        self.assertAlmostEqual(cover_prob(pick), 0.660, places=3)
        self.assertLess(cover_prob(pick), 0.80)

    def test_favourite_short_of_the_spread_is_under_fifty(self):
        # 2.0 expected margin but laying 7.5 - should be a clear underdog bet.
        pick = build(1525.0, 1475.0, -7.5)
        self.assertAlmostEqual(pick.mean_margin, 2.0, places=6)
        self.assertLess(cover_prob(pick), 0.5)

    def test_matches_the_closed_form(self):
        for home_elo, away_elo, spread in [
            (1600.0, 1400.0, -6.5),
            (1450.0, 1550.0, +3.5),
            (1500.0, 1500.0, -1.5),
        ]:
            pick = build(home_elo, away_elo, spread)
            expected = 0.5 * (
                1.0
                + math.erf(
                    (pick.mean_margin + spread)
                    / (NFL_MARGIN_SD * math.sqrt(2.0))
                )
            )
            self.assertAlmostEqual(
                cover_prob(pick), expected, places=9
            )

    def test_home_and_away_cover_probabilities_are_complementary(self):
        pick = build(1600.0, 1400.0, -6.5)
        home_p = cover_prob(pick)
        # Rebuild from the away side; the two must sum to 1.
        mirror = build(1400.0, 1600.0, +6.5)
        self.assertAlmostEqual(home_p + cover_prob(mirror), 1.0, places=9)


class TestBestBetCoherence(unittest.TestCase):
    """edge_pct must be reproducible from the numbers shown beside it."""

    def test_best_bet_edge_equals_model_minus_market(self):
        pick = evaluate_game(
            "LAC", "ARI",
            home_elo=1622.0, away_elo=1268.0,
            home_ml=-535, away_ml=+400,
            home_spread=-10.5, away_spread=+10.5,
            home_spread_odds=-110, away_spread_odds=-110,
            seed=1006,
        )
        bet = pick.best_bet
        if bet is None:
            self.skipTest("no qualifying bet for this fixture")
        self.assertAlmostEqual(
            bet.edge_pct,
            (bet.model_probability - bet.market_probability) * 100.0,
            places=6,
        )

    def test_spread_no_longer_dominates_with_a_fake_edge(self):
        pick = evaluate_game(
            "LAC", "ARI",
            home_elo=1622.0, away_elo=1268.0,
            home_ml=-535, away_ml=+400,
            home_spread=-10.5, away_spread=+10.5,
            home_spread_odds=-110, away_spread_odds=-110,
            seed=1006,
        )
        # 66% cover at -110 (52.4% implied) is a ~13.6pp edge, not ~45pp.
        self.assertLess(pick.spread.edge_pct, 20.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestMarketHomeProbOrientation(unittest.TestCase):
    """
    market_home_win_prob must always describe the HOME team.

    The deployed build set it from `moneyline.market_probability`, where
    `moneyline` is the MarketPick for whichever side the MODEL preferred. When
    the model leaned away, the away team's price landed in a field named
    market_home_win_prob, and the site rendered it as the home team's number:
    the Chargers showed "MARKET 20%" (Arizona's +400) beside "MODEL 80%".
    It was wrong on 11 of 16 week-1 games.
    """

    def _probability(self, odds):
        from model import american_to_probability
        return american_to_probability(odds)

    def test_home_price_is_stored_even_when_model_prefers_away(self):
        # LAC -535 / ARI +400 with an 80% model on LAC: home_edge is -3.75 and
        # away_edge is -0.50, so the model's preferred moneyline side is AWAY.
        pick = evaluate_game(
            "LAC", "ARI",
            home_elo=1583.0, away_elo=1347.0,
            home_ml=-535, away_ml=+400,
            seed=1006,
        )
        self.assertAlmostEqual(
            pick.market_home_win_prob,
            self._probability(-535),   # 84.25%, NOT 20%
            places=9,
        )
        self.assertGreater(pick.market_home_win_prob, 0.80)

    def test_home_price_is_stored_when_model_prefers_home(self):
        pick = evaluate_game(
            "KC", "DEN",
            home_elo=1600.0, away_elo=1450.0,
            home_ml=-150, away_ml=+130,
            seed=11,
        )
        self.assertAlmostEqual(
            pick.market_home_win_prob,
            self._probability(-150),
            places=9,
        )

    def test_orientation_holds_across_both_favourite_directions(self):
        for home_ml, away_ml in [
            (-535, +400), (+400, -535), (-110, -110), (-200, +170),
        ]:
            pick = evaluate_game(
                "HOME", "AWAY",
                home_elo=1550.0, away_elo=1500.0,
                home_ml=home_ml, away_ml=away_ml,
                seed=5,
            )
            self.assertAlmostEqual(
                pick.market_home_win_prob,
                self._probability(home_ml),
                places=9,
                msg=f"home_ml={home_ml}",
            )
