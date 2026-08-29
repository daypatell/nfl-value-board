"""
The prediction model itself: Elo difference -> expected margin -> Monte
Carlo -> win probability -> compared against the sportsbook's implied
probability -> edge / EV / tier. Same approach validated earlier in chat
(real_pipeline.py), reimplemented standalone here so this project has no
dependency on files outside this repo.
"""
from __future__ import annotations
from dataclasses import dataclass
import random
import math
from typing import Optional

from elo import HOME_FIELD_ELO, elo_diff_to_expected_margin

NFL_MARGIN_SD = 13.5
N_SIMS = 10_000


def american_to_probability(odds: int) -> float:
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return -odds / (-odds + 100.0)


def american_to_decimal(odds: int) -> float:
    if odds > 0:
        return 1.0 + odds / 100.0
    return 1.0 + 100.0 / (-odds)


@dataclass
class GamePick:
    home_team: str
    away_team: str
    model_home_win_prob: float
    ci_low: float
    ci_high: float
    mean_margin: float
    market_home_win_prob: Optional[float]
    edge_pct: Optional[float]
    ev_per_unit: Optional[float]
    side: str            # "home", "away", or "no_line"
    action: str
    score_0_100: float
    tier: str


def simulate_home_win_prob(mean_margin: float, seed: int, n: int = N_SIMS) -> tuple[float, float, float]:
    rng = random.Random(seed)
    wins = 0
    for _ in range(n):
        m = rng.gauss(mean_margin, NFL_MARGIN_SD)
        if m > 0:
            wins += 1
    p = wins / n
    se = math.sqrt(max(p * (1 - p), 1e-6) / n)
    return p, max(0.0, p - 1.96 * se), min(1.0, p + 1.96 * se)


MIN_EDGE_PCT = 3.0


def evaluate_game(
    home_team: str, away_team: str, home_elo: float, away_elo: float,
    home_ml: Optional[int], away_ml: Optional[int],
    is_neutral_site: bool, seed: int,
) -> GamePick:
    home_field = 0.0 if is_neutral_site else HOME_FIELD_ELO
    elo_diff = (home_elo + home_field) - away_elo
    mean_margin = elo_diff_to_expected_margin(elo_diff)

    model_home_p, ci_low, ci_high = simulate_home_win_prob(mean_margin, seed)

    if home_ml is None or away_ml is None:
        return GamePick(home_team, away_team, model_home_p, ci_low, ci_high, mean_margin,
                         None, None, None, "no_line", "PASS - no market price available", 0.0, "\u26aa LOW VALUE")

    market_home_p = american_to_probability(home_ml)
    market_away_p = american_to_probability(away_ml)

    home_edge = (model_home_p - market_home_p) * 100.0
    away_edge = ((1 - model_home_p) - market_away_p) * 100.0

    if home_edge >= away_edge:
        side, edge_pct = "home", home_edge
        model_p, market_p, odds = model_home_p, market_home_p, home_ml
    else:
        side, edge_pct = "away", away_edge
        model_p, market_p, odds = 1 - model_home_p, market_away_p, away_ml

    decimal_odds = american_to_decimal(odds)
    ev = model_p * (decimal_odds - 1.0) - (1.0 - model_p)

    ci_width = ci_high - ci_low
    if ci_width >= 0.30:
        action = "PASS - insufficient confidence"
    elif abs(edge_pct) < MIN_EDGE_PCT:
        action = "PASS - edge too small"
    elif ev <= 0:
        action = "PASS - edge does not translate to positive EV"
    else:
        action = "VALUE"

    edge_score = min(abs(edge_pct) / 20.0, 1.0)
    confidence_score = 1.0 if ci_width < 0.15 else 0.6 if ci_width < 0.30 else 0.2
    score = (edge_score * 0.5 + confidence_score * 0.3 + 0.2) * 100.0  # simplified single-source version of the ranking system
    tier = "\U0001F525 ELITE VALUE" if score >= 80 else "\U0001F7E2 STRONG VALUE" if score >= 70 else \
           "\U0001F7E1 MODERATE VALUE" if score >= 60 else "\u26aa LOW VALUE"

    return GamePick(home_team, away_team, model_home_p, ci_low, ci_high, mean_margin,
                     market_home_p, edge_pct, ev, side, action, round(score, 1), tier)
