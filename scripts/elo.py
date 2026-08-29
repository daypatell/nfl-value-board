"""
NFL Elo rating system, 538-style. This is what makes the site work all
season without me hand-updating anything: after every completed game, the
two teams' ratings move based on the result, and next week's predictions
come from whatever the ratings currently say.

Constants match the widely-used FiveThirtyEight NFL Elo methodology
(documented publicly; not proprietary math).
"""
from __future__ import annotations
import math

MEAN_ELO = 1505.0
K_FACTOR = 20.0
HOME_FIELD_ELO = 48.0
PLAYOFF_K_MULTIPLIER = 1.2
SEASON_REGRESS_FACTOR = 1.0 / 3.0   # how far ratings pull back toward mean between seasons


def win_probability(elo_diff: float) -> float:
    """Standard logistic Elo win-probability curve."""
    return 1.0 / (10.0 ** (-elo_diff / 400.0) + 1.0)


def mov_multiplier(point_margin: float, winner_elo_diff: float) -> float:
    """
    Margin-of-victory multiplier: blowouts move ratings more, but with
    diminishing returns, and a big favorite winning big moves ratings less
    than a big underdog winning big (winner_elo_diff is signed from the
    winning team's perspective before the game).
    """
    margin = max(abs(point_margin), 1)
    return math.log(margin + 1.0) * (2.2 / ((winner_elo_diff * 0.001) + 2.2))


def update_ratings(
    home_elo: float,
    away_elo: float,
    home_score: int,
    away_score: int,
    is_playoff: bool = False,
    neutral_site: bool = False,
) -> tuple[float, float]:
    """Returns (new_home_elo, new_away_elo) after one completed game."""
    home_field = 0.0 if neutral_site else HOME_FIELD_ELO
    elo_diff_pregame = (home_elo + home_field) - away_elo

    home_win_prob = win_probability(elo_diff_pregame)
    if home_score > away_score:
        home_actual, away_actual = 1.0, 0.0
        winner_elo_diff = elo_diff_pregame
    elif away_score > home_score:
        home_actual, away_actual = 0.0, 1.0
        winner_elo_diff = -elo_diff_pregame
    else:
        home_actual, away_actual = 0.5, 0.5
        winner_elo_diff = 0.0

    k = K_FACTOR * (PLAYOFF_K_MULTIPLIER if is_playoff else 1.0)
    mult = mov_multiplier(home_score - away_score, winner_elo_diff)

    home_new = home_elo + k * mult * (home_actual - home_win_prob)
    away_new = away_elo + k * mult * (away_actual - (1.0 - home_win_prob))
    return home_new, away_new


def regress_to_mean(elo: float, factor: float = SEASON_REGRESS_FACTOR, mean: float = MEAN_ELO) -> float:
    """Applied once at the start of a new season for every team."""
    return elo + (mean - elo) * factor


def elo_diff_to_expected_margin(elo_diff: float, points_per_elo: float = 1.0 / 25.0) -> float:
    """
    538's convention: roughly 25 Elo points per 1 point of expected scoring
    margin. Used to feed the same margin-based Monte Carlo used elsewhere
    in this project (see simulate_margin in real_pipeline-style code).
    """
    return elo_diff * points_per_elo
