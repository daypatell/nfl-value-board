"""
Run: python3 scripts/update_and_build.py
This is the ONE script the daily GitHub Action calls. It:
  1. Loads current Elo state (data/elo_state.json, seeded from data/elo_seed.json on first run)
  2. Pulls completed games from ESPN and updates Elo for any not already processed
  3. Applies season regression at the right transition points
  4. Pulls current odds from The Odds API
  5. Runs the model on the upcoming games
  6. Writes docs/index.html (served by GitHub Pages) and appends results to data/elo_state.json's bet_log
"""
from __future__ import annotations
import sys
import os
import datetime

sys.path.insert(0, os.path.dirname(__file__))

from state import load_state, save_state
from elo import update_ratings, regress_to_mean
from espn import fetch_scoreboard_json, fetch_current_pointer, parse_games
from odds_api import OddsConfigError, get_current_odds
from line_movement import refresh as refresh_line_movement, lookup as lookup_line_movement
from model import evaluate_game
from site_builder import render_site

PRESEASON = 1


def maybe_apply_season_regression(state: dict, year: int, season_type: int) -> None:
    key = f"{year}-{season_type}"
    if state.get("last_regression_key") == key:
        state["current_season"], state["current_season_type"] = year, season_type
        return
    prev_year = state.get("current_season")
    prev_type = state.get("current_season_type")
    should_regress = (season_type == 2 and (prev_type != 2 or prev_year != year)) or (prev_year is not None and year > prev_year)
    if should_regress:
        for team in state["elo"]:
            state["elo"][team] = round(regress_to_mean(state["elo"][team]), 1)
        print(f"Applied season regression at transition {prev_year}-{prev_type} -> {key}")
    state["last_regression_key"] = key
    state["current_season"], state["current_season_type"] = year, season_type


def update_elo_from_results(state: dict, year: int, season_type: int, week: int) -> int:
    # Preseason results are noise for rating purposes - starters barely play - and
    # 538's methodology rates regular-season and playoff games only. Ratings stay
    # at the Week 1 seed until the regular season actually starts.
    if season_type == PRESEASON:
        return 0
    payload = fetch_scoreboard_json(year, season_type, week)
    games = parse_games(payload)
    updated = 0
    for g in games:
        if not g.is_completed or g.game_id in state["processed_game_ids"]:
            continue
        if g.home_team not in state["elo"] or g.away_team not in state["elo"]:
            continue  # unmapped team abbreviation (bye-week placeholder etc.) - skip safely
        h_new, a_new = update_ratings(
            state["elo"][g.home_team], state["elo"][g.away_team],
            g.home_score, g.away_score, is_playoff=(season_type == 3),
            neutral_site=g.is_neutral_site,
        )
        state["elo"][g.home_team] = round(h_new, 1)
        state["elo"][g.away_team] = round(a_new, 1)
        state["processed_game_ids"].append(g.game_id)
        updated += 1
    return updated


def get_current_week_pointer() -> tuple[int, int, int]:
    """Ask ESPN what week it currently considers 'now' (no query params = current)."""
    return fetch_current_pointer()


def main() -> None:
    state = load_state()
    year, season_type, week = get_current_week_pointer()
    print(f"Current pointer: year={year} season_type={season_type} week={week}")

    maybe_apply_season_regression(state, year, season_type)

    # Process this week AND the previous week, so nothing completed gets missed
    # near the boundary (ESPN flips its "current week" pointer mid-week).
    total_updated = 0
    for wk in sorted({max(week - 1, 1), week}):
        try:
            total_updated += update_elo_from_results(state, year, season_type, wk)
        except Exception as e:
            print(f"Warning: could not process season_type={season_type} week={wk}: {e}")
    if season_type == PRESEASON:
        print("Preseason: Elo ratings held at their Week 1 seed (no rating updates).")
    print(f"Elo updated for {total_updated} newly-completed game(s)")

    # Upcoming games:
    # Use season_markets.json so the model can evaluate the full
    # 2026 regular-season slate during preseason.

    import json

    markets_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "data",
        "season_markets.json",
    )

    with open(markets_path, "r") as f:
        season_markets = json.load(f)

    if season_markets.get("season") != year:
        raise RuntimeError(
            f"season_markets.json is for {season_markets.get('season')}, "
            f"but current year is {year}"
        )

    upcoming = []

    name_to_abbr = {
        name: abbr
        for abbr, name in state["team_names"].items()
    }

    for game in season_markets.get("games", []):
        home_name = game["home_team"]
        away_name = game["away_team"]

        home_abbr = name_to_abbr.get(home_name)
        away_abbr = name_to_abbr.get(away_name)

        if not home_abbr or not away_abbr:
            print(
                f"Warning: could not map teams: "
                f"{away_name} @ {home_name}"
            )
            continue

        if game.get("week") is None:
            continue

        upcoming.append({
            "game_id": game["id"],
            "home_team": home_abbr,
            "away_team": away_abbr,
            "week": int(game["week"]),
            "commence_time": game["commence_time"],
            "is_neutral_site": False,
        })

    # Only evaluate the games for the current NFL week.
    # During preseason, use Week 1 as the initial regular-season display.
    display_week = 1 if season_type == PRESEASON else week

    upcoming = [
        g for g in upcoming
        if int(g["week"]) == display_week
    ]

    print(
        f"Loaded {len(upcoming)} games for Week {display_week} "
        f"from season_markets.json"
    )

    # Odds
    # A misconfigured key is fatal: publishing a board with no market prices while
    # still exiting 0 hides the breakage behind a green check. Transient network
    # trouble is different - warn, publish the Elo side, try again tomorrow.
    try:
        odds_quotes = get_current_odds()
    except OddsConfigError as e:
        print(f"FATAL: {e}")
        raise SystemExit(1)
    except Exception as e:
        print(f"Warning: transient odds fetch failure ({e}); building site with no market lines.")
        odds_quotes = []
    print(f"Odds API returned prices for {len(odds_quotes)} game(s)")

    # Line movement (sharp-action proxy). Refreshed before the model runs so
    # the board is built from today's numbers. Never fatal: it's a secondary
    # signal, and refresh() falls back to the last good file on failure.
    line_moves = refresh_line_movement()
    print(
        f"Line movement: {len(line_moves.get('games', {}))} game(s) "
        f"(upstream_stale={line_moves.get('upstream_stale')}, "
        f"error={line_moves.get('error')})"
    )

    def find_odds(home_abbr: str, away_abbr: str):
        home_name = state["team_names"].get(home_abbr, home_abbr)
        away_name = state["team_names"].get(away_abbr, away_abbr)
        for q in odds_quotes:
            if q.home_team == home_name and q.away_team == away_name:
                return q
        return None

    picks = []
    for i, g in enumerate(upcoming):
        home_team = g["home_team"]
        away_team = g["away_team"]

        if home_team not in state["elo"] or away_team not in state["elo"]:
            continue

        q = find_odds(home_team, away_team)

        move = lookup_line_movement(line_moves, away_team, home_team)

        pick = evaluate_game(
            home_team,
            away_team,
            state["elo"][home_team],
            state["elo"][away_team],
            q.home_moneyline if q else None,
            q.away_moneyline if q else None,
            q.home_spread if q else None,
            q.away_spread if q else None,
            q.home_spread_odds if q else None,
            q.away_spread_odds if q else None,
            q.total_points if q else None,
            q.over_odds if q else None,
            q.under_odds if q else None,
            g.get("is_neutral_site", False),
            seed=1000 + i,
            line_move_pp=move["line_move_pp"] if move else None,
        )

        picks.append(pick)

        if pick.action == "VALUE":
            state["bet_log"].append({
                "date": datetime.date.today().isoformat(),
                "home": home_team,
                "away": away_team,
                "side": pick.side,
                "edge_pct": pick.edge_pct,
                "model_prob": pick.model_home_win_prob,
                "score": pick.score_0_100,
                "week": g["week"],
                "season_type": season_type,
                "year": year,
                "resolved": False,
            })

    matched = sum(
        1 for p in picks
        if p.market_home_win_prob is not None
    )

    print(
        f"{matched}/{len(picks)} upcoming game(s) "
        "matched to a market price"
    )

    with_move = sum(1 for p in picks if p.line_move_pp is not None)
    flips = sum(1 for p in picks if p.disagreement == "FAVORITE FLIP")
    aligned = sum(
        1 for p in picks if p.disagreement == "MODEL + SHARP ALIGNMENT"
    )
    margins = sum(1 for p in picks if p.disagreement == "MARGIN MISMATCH")
    print(
        f"{with_move}/{len(picks)} game(s) have line movement | "
        f"mismatches: {aligned} sharp-aligned, {flips} favourite flip, "
        f"{margins} margin"
    )

    if picks and matched == 0 and odds_quotes:
        print(
            "Warning: odds were returned but none matched the slate; "
            "check team_names mapping."
        )

    render_site(
        state, picks, week, season_type, year,
        line_movement_meta=line_moves,
    )
    save_state(state)

    print(f"Done. {len(picks)} upcoming games evaluated.")


if __name__ == "__main__":
    main()
