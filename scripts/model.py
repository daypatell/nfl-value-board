from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import random
import math

from elo import HOME_FIELD_ELO, elo_diff_to_expected_margin

NFL_MARGIN_SD = 13.5
N_SIMS = 10_000
MIN_EDGE_PCT = 3.0
MIN_EV = 0.0


def american_to_probability(odds: int) -> float:
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return -odds / (-odds + 100.0)


def american_to_decimal(odds: int) -> float:
    if odds > 0:
        return 1.0 + odds / 100.0
    return 1.0 + 100.0 / (-odds)


@dataclass
class MarketPick:
    market: str
    pick: str
    odds: Optional[int]
    line: Optional[float]
    model_probability: Optional[float]
    market_probability: Optional[float]
    edge_pct: Optional[float]
    ev_per_unit: Optional[float]
    action: str
    score: float


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

    side: str
    action: str
    score_0_100: float
    tier: str

    # New market information
    moneyline: Optional[MarketPick] = None
    spread: Optional[MarketPick] = None
    total: Optional[MarketPick] = None
    best_bet: Optional[MarketPick] = None


def simulate_home_win_prob(
    mean_margin: float,
    seed: int,
    n: int = N_SIMS,
) -> tuple[float, float, float]:

    rng = random.Random(seed)
    wins = 0

    for _ in range(n):
        margin = rng.gauss(mean_margin, NFL_MARGIN_SD)

        if margin > 0:
            wins += 1

    p = wins / n

    se = math.sqrt(
        max(p * (1 - p), 1e-6) / n
    )

    return (
        p,
        max(0.0, p - 1.96 * se),
        min(1.0, p + 1.96 * se),
    )


def calculate_ev(
    model_probability: float,
    odds: int,
) -> float:

    decimal_odds = american_to_decimal(odds)

    return (
        model_probability * (decimal_odds - 1.0)
        - (1.0 - model_probability)
    )


def make_market_pick(
    market: str,
    pick: str,
    odds: Optional[int],
    line: Optional[float],
    model_probability: Optional[float],
) -> Optional[MarketPick]:

    if odds is None or model_probability is None:
        return None

    market_probability = american_to_probability(odds)

    edge_pct = (
        model_probability - market_probability
    ) * 100.0

    ev = calculate_ev(
        model_probability,
        odds,
    )

    if edge_pct >= MIN_EDGE_PCT and ev > MIN_EV:
        action = "VALUE"
    else:
        action = "PASS"

    score = (
        min(max(edge_pct, 0.0) / 20.0, 1.0) * 70.0
        + min(max(ev, 0.0) / 0.20, 1.0) * 30.0
    )

    return MarketPick(
        market=market,
        pick=pick,
        odds=odds,
        line=line,
        model_probability=model_probability,
        market_probability=market_probability,
        edge_pct=edge_pct,
        ev_per_unit=ev,
        action=action,
        score=round(score, 1),
    )


def evaluate_game(
    home_team: str,
    away_team: str,
    home_elo: float,
    away_elo: float,
    home_ml: Optional[int],
    away_ml: Optional[int],
    home_spread: Optional[float] = None,
    away_spread: Optional[float] = None,
    home_spread_odds: Optional[int] = None,
    away_spread_odds: Optional[int] = None,
    total_points: Optional[float] = None,
    over_odds: Optional[int] = None,
    under_odds: Optional[int] = None,
    is_neutral_site: bool = False,
    seed: int = 1000,
) -> GamePick:

    home_field = (
        0.0 if is_neutral_site else HOME_FIELD_ELO
    )

    elo_diff = (
        home_elo
        + home_field
        - away_elo
    )

    mean_margin = elo_diff_to_expected_margin(
        elo_diff
    )

    model_home_p, ci_low, ci_high = simulate_home_win_prob(
        mean_margin,
        seed,
    )

    # -------------------------------------------------
    # MONEYLINE
    # -------------------------------------------------

    moneyline = None

    if home_ml is not None and away_ml is not None:

        home_market_p = american_to_probability(
            home_ml
        )

        away_market_p = american_to_probability(
            away_ml
        )

        home_edge = (
            model_home_p - home_market_p
        ) * 100.0

        away_edge = (
            (1.0 - model_home_p)
            - away_market_p
        ) * 100.0

        if home_edge >= away_edge:

            moneyline = make_market_pick(
                "Moneyline",
                home_team,
                home_ml,
                None,
                model_home_p,
            )

        else:

            moneyline = make_market_pick(
                "Moneyline",
                away_team,
                away_ml,
                None,
                1.0 - model_home_p,
            )

    # -------------------------------------------------
    # SPREAD
    # -------------------------------------------------

    spread = None

    if (
        home_spread is not None
        and home_spread_odds is not None
        and away_spread is not None
        and away_spread_odds is not None
    ):

        # Approximate probability that the selected team
        # covers the posted spread.
        #
        # Example:
        # Seahawks -2.5
        # Model margin +5.0
        #
        # Probability = P(actual margin > 2.5)

        home_cover_probability = 1.0 - (
            0.5 * (
                1.0 + math.erf(
                    (
                        home_spread - mean_margin
                    ) / (
                        NFL_MARGIN_SD * math.sqrt(2)
                    )
                )
            )
        )

        away_cover_probability = 1.0 - home_cover_probability

        home_spread_pick = make_market_pick(
            "Spread",
            f"{home_team} {home_spread:+g}",
            home_spread_odds,
            home_spread,
            home_cover_probability,
        )

        away_spread_pick = make_market_pick(
            "Spread",
            f"{away_team} {away_spread:+g}",
            away_spread_odds,
            away_spread,
            away_cover_probability,
        )

        candidates = [
            p for p in [
                home_spread_pick,
                away_spread_pick,
            ]
            if p is not None
        ]

        if candidates:
            spread = max(
                candidates,
                key=lambda p: p.score
            )

    # -------------------------------------------------
    # TOTAL
    # -------------------------------------------------

    total = None

    if (
        total_points is not None
        and over_odds is not None
        and under_odds is not None
    ):

        # The current Elo model does not have a true
        # offensive/defensive scoring model, so we do
        # NOT pretend it can accurately predict totals.
        #
        # We leave total as PASS until a scoring model
        # is added.

        total = MarketPick(
            market="Total",
            pick=f"Over/Under {total_points:g}",
            odds=None,
            line=total_points,
            model_probability=None,
            market_probability=None,
            edge_pct=None,
            ev_per_unit=None,
            action="PASS - scoring model not yet enabled",
            score=0.0,
        )

    # -------------------------------------------------
    # BEST BET
    # -------------------------------------------------

    candidates = [
        p for p in [
            moneyline,
            spread,
        ]
        if p is not None
        and p.action == "VALUE"
    ]

    best_bet = (
        max(
            candidates,
            key=lambda p: p.score
        )
        if candidates
        else None
    )

    # Preserve compatibility with the existing site.
    if best_bet is not None:

        side = (
            "home"
            if best_bet.pick.startswith(home_team)
            else "away"
        )

        edge_pct = best_bet.edge_pct
        ev = best_bet.ev_per_unit

        model_probability = (
            best_bet.model_probability
            if best_bet.model_probability is not None
            else model_home_p
        )

    else:

        side = "no_line"
        edge_pct = None
        ev = None
        model_probability = model_home_p

    ci_width = ci_high - ci_low

    if best_bet is None:

        action = "PASS"

    elif ci_width >= 0.30:

        action = "PASS - insufficient confidence"

    else:

        action = "VALUE"

    if best_bet is not None:

        score = best_bet.score

    else:

        score = 0.0

    tier = (
        "🔥 ELITE VALUE"
        if score >= 80
        else "🟢 STRONG VALUE"
        if score >= 70
        else "🟡 MODERATE VALUE"
        if score >= 60
        else "⚪ LOW VALUE"
    )

    return GamePick(
        home_team=home_team,
        away_team=away_team,
        model_home_win_prob=model_home_p,
        ci_low=ci_low,
        ci_high=ci_high,
        mean_margin=mean_margin,
        market_home_win_prob=(
            moneyline.market_probability
            if moneyline
            else None
        ),
        edge_pct=edge_pct,
        ev_per_unit=ev,
        side=side,
        action=action,
        score_0_100=round(score, 1),
        tier=tier,
        moneyline=moneyline,
        spread=spread,
        total=total,
        best_bet=best_bet,
    )
