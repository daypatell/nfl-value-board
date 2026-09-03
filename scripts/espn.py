"""
ESPN's public (unofficial, undocumented but widely used, free, no API key)
scoreboard endpoint. Used for two things:
  1. Pulling completed games so Elo can update itself.
  2. Pulling the upcoming week's schedule (who plays whom, home/away).

Endpoint confirmed working 2026-08-28:
  https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard

Params: ?year=YYYY&seasontype=N&week=W
  seasontype: 1=preseason, 2=regular season, 3=postseason
"""
from __future__ import annotations
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import List, Optional

from teams import normalize_abbr

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"

# ESPN sits behind Akamai, which 403s unrecognised User-Agent strings (a custom
# "nfl-value-board/1.0" UA is rejected outright). Plain client UAs are accepted,
# so send those and fall through the list if one starts getting blocked.
USER_AGENTS = (
    "Python-urllib/3.12",
    "curl/8.7.1",
)


def fetch_json(url: str, timeout: int = 15):
    """GET + JSON-decode, retrying across USER_AGENTS if the edge blocks one."""
    last_error = None
    for user_agent in USER_AGENTS:
        req = urllib.request.Request(url, headers={"User-Agent": user_agent})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code not in (403, 429):
                raise
            last_error = e
    raise RuntimeError(f"ESPN refused every User-Agent we tried for {url}: {last_error}")


@dataclass
class EspnGame:
    game_id: str
    week: int
    season_type: int
    home_team: str   # abbreviation, e.g. "KC"
    away_team: str
    is_completed: bool
    is_neutral_site: bool
    home_score: Optional[int]
    away_score: Optional[int]
    kickoff_iso: str


def fetch_scoreboard_json(year: int, season_type: int, week: int, timeout: int = 15) -> dict:
    url = f"{BASE_URL}?year={year}&seasontype={season_type}&week={week}"
    return fetch_json(url, timeout=timeout)


def fetch_current_pointer(timeout: int = 15) -> tuple[int, int, int]:
    """Ask ESPN what week it currently considers 'now' (no query params = current)."""
    data = fetch_json(BASE_URL, timeout=timeout)
    return data["season"]["year"], data["season"]["type"], data["week"]["number"]


def parse_games(payload: dict) -> List[EspnGame]:
    games = []
    for event in payload.get("events", []):
        comp = event["competitions"][0]
        competitors = comp["competitors"]
        home = next(c for c in competitors if c["homeAway"] == "home")
        away = next(c for c in competitors if c["homeAway"] == "away")
        status = comp.get("status", event.get("status", {}))
        completed = bool(status.get("type", {}).get("completed", False))
        games.append(EspnGame(
            game_id=event["id"],
            week=event.get("week", {}).get("number", 0),
            season_type=event.get("season", {}).get("type", 0),
            # ESPN spells Washington "WSH" while data/elo_seed.json uses "WAS".
            # update_elo_from_results skips any abbreviation it can't find in
            # state["elo"], so without this every Washington result was dropped
            # and their rating never moved all season.
            home_team=normalize_abbr(home["team"]["abbreviation"]),
            away_team=normalize_abbr(away["team"]["abbreviation"]),
            is_completed=completed,
            is_neutral_site=bool(comp.get("neutralSite", False)),
            home_score=int(home["score"]) if completed and "score" in home else None,
            away_score=int(away["score"]) if completed and "score" in away else None,
            kickoff_iso=comp.get("date", event.get("date", "")),
        ))
    return games


def get_week_games(year: int, season_type: int, week: int) -> List[EspnGame]:
    payload = fetch_scoreboard_json(year, season_type, week)
    return parse_games(payload)
