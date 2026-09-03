from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import math
import random


from elo import (
    HOME_FIELD_ELO,
    elo_diff_to_expected_margin,
)


NFL_MARGIN_SD = 13.5
N_SIMS = 20000

# We deliberately require a meaningful edge.
MIN_EDGE_PCT = 3.0
MIN_EV = 0.0

# ---------------------------------------------------------------------------
# MODEL-VS-MARKET DISAGREEMENT
# ---------------------------------------------------------------------------
# Separate from edge_pct on purpose. edge_pct answers "is this bet +EV at the
# posted price", so it must use the raw vigged probability. These labels answer
# "does the model actually disagree with the market about this game", which is a
# question about opinion, so they use the de-vigged probability instead.

DISAGREE_SHARP_ALIGNED = "MODEL + SHARP ALIGNMENT"
DISAGREE_FLIP = "FAVORITE FLIP"
DISAGREE_MARGIN = "MARGIN MISMATCH"
DISAGREE_NONE = "AGREEMENT"
DISAGREE_NO_LINE = "NO LINE"

# Severity order for ranking; lower sorts first.
DISAGREE_RANK = {
    DISAGREE_SHARP_ALIGNED: 0,
    DISAGREE_FLIP: 1,
    DISAGREE_MARGIN: 2,
    DISAGREE_NONE: 3,
    DISAGREE_NO_LINE: 4,
}

# How far apart the model and the de-vigged market have to be, in percentage
# points, before we call it a margin mismatch rather than agreement.
MISMATCH_THRESHOLD_PP = MIN_EDGE_PCT

# Implied-probability move (percentage points) below which line movement is
# treated as noise rather than a directional signal.
SHARP_MOVE_MIN_PP = 1.0

# Absorbs float representation error in threshold comparisons.
_PP_EPSILON = 1e-9


def devig_home_probability(
    home_ml: Optional[int],
    away_ml: Optional[int],
) -> Optional[float]:
    """
    Home win probability with the bookmaker's margin removed.

    Raw implied probabilities sum to more than 1, so a -110/-110 pick'em reads
    as 52.4% on BOTH sides. Comparing either raw number against 50% would name
    two favourites in the same game and misfire the favourite-flip test, so
    normalise the pair to sum to 1 first.
    """
    if home_ml is None or away_ml is None:
        return None

    home_p = american_to_probability(home_ml)
    away_p = american_to_probability(away_ml)
    total = home_p + away_p

    if total <= 0:
        return None

    return home_p / total


def favorite_from_prob(home_prob: Optional[float]) -> Optional[str]:
    """"home" / "away" / None for an exact coin flip (no favourite exists)."""
    if home_prob is None:
        return None
    if home_prob > 0.5:
        return "home"
    if home_prob < 0.5:
        return "away"
    return None


def sharp_side_from_move(
    line_move_pp: Optional[float],
    min_move_pp: float = SHARP_MOVE_MIN_PP,
) -> Optional[str]:
    """
    Which side the money is coming in on, inferred from line movement.

    line_move_pp is home-relative: positive means the home team's implied
    probability rose since open. Moves smaller than min_move_pp are noise.
    """
    if line_move_pp is None or abs(line_move_pp) < min_move_pp:
        return None
    return "home" if line_move_pp > 0 else "away"


def classify_disagreement(
    model_home_prob: float,
    market_home_prob_devig: Optional[float],
    threshold_pp: float = MISMATCH_THRESHOLD_PP,
    sharp_side: Optional[str] = None,
) -> tuple[str, Optional[float]]:
    """
    Label how the model disagrees with the market, and by how much.

    Returns (label, mismatch_pp). mismatch_pp is the absolute gap between the
    model and the de-vigged market, in percentage points, or None with no line.
    """
    if market_home_prob_devig is None:
        return DISAGREE_NO_LINE, None

    mismatch_pp = abs(model_home_prob - market_home_prob_devig) * 100.0

    market_fav = favorite_from_prob(market_home_prob_devig)
    model_fav = favorite_from_prob(model_home_prob)

    # A true coin flip on either side means there is no favourite to flip.
    flipped = (
        market_fav is not None
        and model_fav is not None
        and market_fav != model_fav
    )

    if flipped:
        # Strongest contrarian read: the market (and the crowd behind it) favours
        # one team, the model favours the other, and the line is moving toward
        # the model's side.
        if sharp_side is not None and sharp_side == model_fav:
            return DISAGREE_SHARP_ALIGNED, mismatch_pp
        return DISAGREE_FLIP, mismatch_pp

    # Tolerance, not decoration: abs(0.65 - 0.62) * 100 is 3.0000000000000004
    # in binary floating point, so a gap sitting exactly on a 3.0pp threshold
    # would otherwise be classified by rounding error.
    if mismatch_pp > threshold_pp + _PP_EPSILON:
        return DISAGREE_MARGIN, mismatch_pp

    return DISAGREE_NONE, mismatch_pp


def american_to_probability(odds: int) -> float:

    if odds > 0:
        return 100.0 / (odds + 100.0)

    return -odds / (-odds + 100.0)


def american_to_decimal(odds: int) -> float:

    if odds > 0:
        return 1.0 + odds / 100.0

    return 1.0 + 100.0 / (-odds)


def calculate_ev(
    probability: float,
    odds: int,
) -> float:

    decimal_odds = american_to_decimal(odds)

    return (
        probability * (decimal_odds - 1.0)
        - (1.0 - probability)
    )


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

    moneyline: Optional[MarketPick] = None
    spread: Optional[MarketPick] = None
    total: Optional[MarketPick] = None

    best_bet: Optional[MarketPick] = None

    # Model-vs-market disagreement.
    disagreement: str = DISAGREE_NO_LINE
    market_home_win_prob_devig: Optional[float] = None
    mismatch_pp: Optional[float] = None

    # Line movement (CLEATZ odds-movers), home-relative percentage points.
    line_move_pp: Optional[float] = None
    sharp_side: Optional[str] = None

    # Advanced model diagnostics.
    factor_score: float = 0.0
    injury_adjustment: float = 0.0
    recent_form_adjustment: float = 0.0
    weather_adjustment: float = 0.0
    rest_adjustment: float = 0.0
    roster_adjustment: float = 0.0
    coaching_adjustment: float = 0.0


def sigmoid(x: float) -> float:

    x = max(-20.0, min(20.0, x))

    return 1.0 / (1.0 + math.exp(-x))


def simulate_home_win_prob(
    mean_margin: float,
    seed: int,
    n: int = N_SIMS,
):

    rng = random.Random(seed)

    wins = 0

    for _ in range(n):

        margin = rng.gauss(
            mean_margin,
            NFL_MARGIN_SD,
        )

        if margin > 0:
            wins += 1

    p = wins / n

    se = math.sqrt(
        max(p * (1.0 - p), 1e-6) / n
    )

    return (
        p,
        max(0.0, p - 1.96 * se),
        min(1.0, p + 1.96 * se),
    )


def make_market_pick(
    market: str,
    pick: str,
    odds: Optional[int],
    line: Optional[float],
    model_probability: Optional[float],
):

    if odds is None or model_probability is None:
        return None

    market_probability = (
        american_to_probability(odds)
    )

    edge_pct = (
        model_probability
        - market_probability
    ) * 100.0

    ev = calculate_ev(
        model_probability,
        odds,
    )

    if (
        edge_pct >= MIN_EDGE_PCT
        and ev > MIN_EV
    ):
        action = "VALUE"
    else:
        action = "PASS"

    score = (
        min(
            max(edge_pct, 0.0) / 12.0,
            1.0,
        ) * 70.0
        +
        min(
            max(ev, 0.0) / 0.20,
            1.0,
        ) * 30.0
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

    # NEW ADVANCED FACTORS
    home_injury_penalty: float = 0.0,
    away_injury_penalty: float = 0.0,

    home_recent_form: float = 0.0,
    away_recent_form: float = 0.0,

    home_roster_strength: float = 0.0,
    away_roster_strength: float = 0.0,

    home_coaching: float = 0.0,
    away_coaching: float = 0.0,

    rest_difference: float = 0.0,

    weather_penalty_value: float = 0.0,

    # Home-relative implied-probability move since open, in percentage points.
    line_move_pp: Optional[float] = None,

    mismatch_threshold_pp: float = MISMATCH_THRESHOLD_PP,
) -> GamePick:

    # -------------------------------------------------
    # BASE ELO
    # -------------------------------------------------

    home_field = (
        0.0
        if is_neutral_site
        else HOME_FIELD_ELO
    )

    elo_diff = (
        home_elo
        + home_field
        - away_elo
    )

    base_margin = (
        elo_diff_to_expected_margin(
            elo_diff
        )
    )

    # -------------------------------------------------
    # ADVANCED FACTORS
    # -------------------------------------------------

    injury_adjustment = (
        away_injury_penalty
        - home_injury_penalty
    ) * 1.25

    recent_form_adjustment = (
        home_recent_form
        - away_recent_form
    ) * 0.12

    roster_adjustment = (
        home_roster_strength
        - away_roster_strength
    )

    coaching_adjustment = (
        home_coaching
        - away_coaching
    )

    rest_adjustment = (
        rest_difference * 0.50
    )

    # Weather generally reduces scoring/margin
    # certainty rather than creating a giant team edge.
    weather_adjustment = (
        -weather_penalty_value
        * 0.20
    )

    advanced_margin = (
        base_margin
        + injury_adjustment
        + recent_form_adjustment
        + roster_adjustment
        + coaching_adjustment
        + rest_adjustment
        + weather_adjustment
    )

    # Prevent the model from producing absurd
    # 75%-90% predictions from one noisy factor.
    advanced_margin = max(
        -24.0,
        min(24.0, advanced_margin),
    )

    model_home_p, ci_low, ci_high = (
        simulate_home_win_prob(
            advanced_margin,
            seed,
        )
    )

    # -------------------------------------------------
    # MARKET
    # -------------------------------------------------

    moneyline = None

    if (
        home_ml is not None
        and away_ml is not None
    ):

        home_market_p = (
            american_to_probability(
                home_ml
            )
        )

        away_market_p = (
            american_to_probability(
                away_ml
            )
        )

        home_edge = (
            model_home_p
            - home_market_p
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
        and away_spread is not None
        and home_spread_odds is not None
        and away_spread_odds is not None
    ):

        # Probability the home team covers.
        #
        # home_spread is signed the way a book quotes it: -10.5 means the home
        # team must win by more than 10.5. So the margin has to clear
        # -home_spread, and P(cover) = P(margin > -home_spread).
        #
        # Two bugs previously lived here. The threshold used +home_spread
        # instead of -home_spread, which inverted every favourite's cover
        # probability, and the SD was inflated by sqrt(2). NFL_MARGIN_SD is
        # already the standard deviation OF THE MARGIN - the sqrt(2) would only
        # apply when differencing two independent normals. Together they turned
        # LAC -10.5 off a +16.08 expected margin into 97.6% instead of 66.0%,
        # manufacturing a +45pp edge on essentially every spread.
        z = (
            -home_spread
            - advanced_margin
        ) / NFL_MARGIN_SD

        home_cover_probability = (
            0.5 * (1.0 - math.erf(z / math.sqrt(2.0)))
        )

        away_cover_probability = (
            1.0
            - home_cover_probability
        )

        home_pick = make_market_pick(
            "Spread",
            f"{home_team} {home_spread:+g}",
            home_spread_odds,
            home_spread,
            home_cover_probability,
        )

        away_pick = make_market_pick(
            "Spread",
            f"{away_team} {away_spread:+g}",
            away_spread_odds,
            away_spread,
            away_cover_probability,
        )

        candidates = [
            p
            for p in [
                home_pick,
                away_pick,
            ]
            if p is not None
        ]

        if candidates:
            spread = max(
                candidates,
                key=lambda x: x.score,
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

        # We intentionally don't invent a total model
        # from an Elo-only model.
        total = MarketPick(
            market="Total",
            pick=f"Over/Under {total_points:g}",
            odds=None,
            line=total_points,
            model_probability=None,
            market_probability=None,
            edge_pct=None,
            ev_per_unit=None,
            action="PASS",
            score=0.0,
        )

    # -------------------------------------------------
    # BEST BET
    # -------------------------------------------------

    candidates = [
        p
        for p in [
            moneyline,
            spread,
        ]
        if p is not None
        and p.action == "VALUE"
    ]

    best_bet = (
        max(
            candidates,
            key=lambda x: x.score,
        )
        if candidates
        else None
    )

    if best_bet:

        side = (
            "home"
            if best_bet.pick.startswith(
                home_team
            )
            else "away"
        )

        edge_pct = (
            best_bet.edge_pct
        )

        ev = (
            best_bet.ev_per_unit
        )

    else:

        side = "no_line"
        edge_pct = None
        ev = None

    if best_bet:

        score = best_bet.score

        if score >= 80:
            tier = "ELITE VALUE"
        elif score >= 60:
            tier = "STRONG VALUE"
        elif score >= 40:
            tier = "VALUE"
        else:
            tier = "LEAN"

        action = "VALUE"

    else:

        score = 0.0
        tier = "NO VALUE"
        action = "PASS"

    market_home_prob = None

    if home_ml is not None:

        market_home_prob = (
            american_to_probability(
                home_ml
            )
        )

    factor_score = (
        abs(injury_adjustment)
        + abs(recent_form_adjustment)
        + abs(roster_adjustment)
        + abs(coaching_adjustment)
    )

    market_home_prob_devig = devig_home_probability(
        home_ml,
        away_ml,
    )

    sharp_side = sharp_side_from_move(line_move_pp)

    disagreement, mismatch_pp = classify_disagreement(
        model_home_p,
        market_home_prob_devig,
        mismatch_threshold_pp,
        sharp_side,
    )

    return GamePick(
        home_team=home_team,
        away_team=away_team,

        model_home_win_prob=model_home_p,

        ci_low=ci_low,
        ci_high=ci_high,

        mean_margin=advanced_margin,

        market_home_win_prob=market_home_prob,
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

        disagreement=disagreement,
        market_home_win_prob_devig=market_home_prob_devig,
        mismatch_pp=(
            None if mismatch_pp is None else round(mismatch_pp, 2)
        ),
        line_move_pp=(
            None if line_move_pp is None else round(line_move_pp, 2)
        ),
        sharp_side=sharp_side,

        factor_score=round(
            factor_score,
            3,
        ),

        injury_adjustment=round(
            injury_adjustment,
            3,
        ),

        recent_form_adjustment=round(
            recent_form_adjustment,
            3,
        ),

        weather_adjustment=round(
            weather_adjustment,
            3,
        ),

        rest_adjustment=round(
            rest_adjustment,
            3,
        ),

        roster_adjustment=round(
            roster_adjustment,
            3,
        ),

        coaching_adjustment=round(
            coaching_adjustment,
            3,
        ),
    )
