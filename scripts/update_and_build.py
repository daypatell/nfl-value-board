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

    # Upcoming games for the current week
    upcoming_payload = fetch_scoreboard_json(year, season_type, week)
    from espn import parse_games as _parse
    upcoming = [g for g in _parse(upcoming_payload) if not g.is_completed]

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

    def find_odds(home_abbr: str, away_abbr: str):
        home_name = state["team_names"].get(home_abbr, home_abbr)
        away_name = state["team_names"].get(away_abbr, away_abbr)
        for q in odds_quotes:
            if q.home_team == home_name and q.away_team == away_name:
                return q
        return None

    picks = []
    for i, g in enumerate(upcoming):
        if g.home_team not in state["elo"] or g.away_team not in state["elo"]:
            continue
        q = find_odds(g.home_team, g.away_team)
        pick = evaluate_game(
            g.home_team, g.away_team,
            state["elo"][g.home_team], state["elo"][g.away_team],
            q.home_moneyline if q else None, q.away_moneyline if q else None,
            g.is_neutral_site, seed=1000 + i,
        )
        picks.append(pick)
        if pick.action == "VALUE":
            state["bet_log"].append({
                "date": datetime.date.today().isoformat(),
                "home": g.home_team, "away": g.away_team,
                "side": pick.side, "edge_pct": pick.edge_pct,
                "model_prob": pick.model_home_win_prob, "score": pick.score_0_100,
                "week": week, "season_type": season_type, "year": year,
                "resolved": False,  # filled in by a later run once the game completes
            })

    matched = sum(1 for p in picks if p.market_home_win_prob is not None)
    print(f"{matched}/{len(picks)} upcoming game(s) matched to a market price")
    if picks and matched == 0 and odds_quotes:
        # Odds arrived but nothing matched - almost always a team-name mismatch
        # between ESPN abbreviations and The Odds API's full names.
        print("Warning: odds were returned but none matched the slate; check team_names mapping.")

    render_site(state, picks, week, season_type, year)
    save_state(state)
    print(f"Done. {len(picks)} upcoming games evaluated.")


if __name__ == "__main__":
    main()
