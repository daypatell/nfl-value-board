"""
The Odds API (https://the-odds-api.com) client. Free tier covers this use
case (one pull a day, one sport) comfortably. Requires signing up for a
free API key and setting it as the ODDS_API_KEY environment variable /
GitHub Actions secret — see README_DEPLOY.md.
"""
from __future__ import annotations
import json
import os
import urllib.error
import urllib.request
import urllib.parse
from dataclasses import dataclass
from typing import List, Optional

BASE_URL = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"


class OddsConfigError(RuntimeError):
    """Key is missing, empty, invalid, or out of quota.

    Kept distinct from transient network errors on purpose: the daily job
    treats this as fatal. A silently key-less run still exits 0 and publishes
    a board with no market prices, which is worse than a visibly failed run.
    """


@dataclass
class OddsQuote:
    home_team: str   # full name, e.g. "Kansas City Chiefs" — Odds API uses full names, not abbreviations
    away_team: str
    commence_time_iso: str
    bookmaker: str
    home_moneyline: Optional[int]
    away_moneyline: Optional[int]
    home_spread: Optional[float]
    total_points: Optional[float]


def fetch_odds_json(api_key: str, regions: str = "us", markets: str = "h2h,spreads,totals",
                     odds_format: str = "american", timeout: int = 15) -> list:
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": markets,
        "oddsFormat": odds_format,
    }
    url = f"{BASE_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "nfl-value-board/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 401 = bad/missing key, 422 = malformed request, 429 = monthly quota gone.
        if e.code in (401, 422, 429):
            detail = e.read().decode("utf-8", "replace")[:200]
            raise OddsConfigError(f"The Odds API rejected the request (HTTP {e.code}): {detail}") from e
        raise


def parse_odds(payload: list, preferred_bookmaker: str = "draftkings") -> List[OddsQuote]:
    """Picks one bookmaker per game (preferred_bookmaker if present, else the first available)."""
    quotes = []
    for game in payload:
        books = game.get("bookmakers", [])
        if not books:
            continue
        book = next((b for b in books if b["key"] == preferred_bookmaker), books[0])

        home_ml = away_ml = home_spread = total_points = None
        for market in book.get("markets", []):
            if market["key"] == "h2h":
                for outcome in market["outcomes"]:
                    if outcome["name"] == game["home_team"]:
                        home_ml = int(outcome["price"])
                    elif outcome["name"] == game["away_team"]:
                        away_ml = int(outcome["price"])
            elif market["key"] == "spreads":
                for outcome in market["outcomes"]:
                    if outcome["name"] == game["home_team"]:
                        home_spread = float(outcome["point"])
            elif market["key"] == "totals":
                for outcome in market["outcomes"]:
                    if outcome["name"].lower().startswith("over"):
                        total_points = float(outcome["point"])

        quotes.append(OddsQuote(
            home_team=game["home_team"], away_team=game["away_team"],
            commence_time_iso=game["commence_time"], bookmaker=book["key"],
            home_moneyline=home_ml, away_moneyline=away_ml,
            home_spread=home_spread, total_points=total_points,
        ))
    return quotes


def get_current_odds(preferred_bookmaker: str = "draftkings") -> List[OddsQuote]:
    api_key = (os.environ.get("ODDS_API_KEY") or "").strip()
    if not api_key:
        raise OddsConfigError(
            "ODDS_API_KEY is not set (or is empty). In GitHub Actions this usually means the "
            "repo secret was never set, or was set to an empty string. See README_DEPLOY.md."
        )
    payload = fetch_odds_json(api_key)
    return parse_odds(payload, preferred_bookmaker)
