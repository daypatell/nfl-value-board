from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_URL = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds/"
OUTPUT = Path("data/season_markets.json")

MARKETS = ["h2h", "spreads", "totals"]
REGIONS = "us"


def fetch_odds():
    key = os.environ.get("ODDS_API_KEY", "").strip()

    if not key:
        raise RuntimeError("ODDS_API_KEY is not set.")

    params = urllib.parse.urlencode({
        "apiKey": key,
        "regions": REGIONS,
        "markets": ",".join(MARKETS),
        "oddsFormat": "american",
    })

    request = urllib.request.Request(
        f"{API_URL}?{params}",
        headers={"User-Agent": "Mozilla/5.0"},
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            status = response.status
    except Exception as exc:
        raise RuntimeError(f"Odds API request failed: {exc}") from exc

    if status != 200:
        raise RuntimeError(
            f"Odds API returned HTTP {status}: "
            f"{raw.decode(errors='replace')}"
        )

    return json.loads(raw)


def calculate_week(commence_time):
    dt = datetime.fromisoformat(
        commence_time.replace("Z", "+00:00")
    )

    # Approximate grouping. ESPN will remain the authoritative
    # source for official NFL week numbers later.
    season_start = datetime(2026, 9, 9, tzinfo=timezone.utc)

    days = (dt - season_start).days

    if days < 0:
        return None

    week = (days // 7) + 1

    return week if 1 <= week <= 18 else None


def build_summary(bookmakers):
    summary = {
        "moneyline": [],
        "spread": [],
        "total": [],
    }

    for book in bookmakers:
        book_name = book.get("title")
        book_key = book.get("key")

        for market in book.get("markets", []):
            market_key = market.get("key")

            if market_key == "h2h":
                for outcome in market.get("outcomes", []):
                    summary["moneyline"].append({
                        "sportsbook": book_name,
                        "sportsbook_key": book_key,
                        "team": outcome.get("name"),
                        "price": outcome.get("price"),
                    })

            elif market_key == "spreads":
                for outcome in market.get("outcomes", []):
                    summary["spread"].append({
                        "sportsbook": book_name,
                        "sportsbook_key": book_key,
                        "team": outcome.get("name"),
                        "price": outcome.get("price"),
                        "point": outcome.get("point"),
                    })

            elif market_key == "totals":
                for outcome in market.get("outcomes", []):
                    summary["total"].append({
                        "sportsbook": book_name,
                        "sportsbook_key": book_key,
                        "side": outcome.get("name"),
                        "price": outcome.get("price"),
                        "point": outcome.get("point"),
                    })

    return summary


def main():
    raw_games = fetch_odds()

    games = []

    for raw in raw_games:
        commence = raw.get("commence_time")

        if not commence:
            continue

        game = {
            "id": raw.get("id"),
            "commence_time": commence,
            "home_team": raw.get("home_team"),
            "away_team": raw.get("away_team"),
            "week": calculate_week(commence),
            "bookmakers": raw.get("bookmakers", []),
        }

        game["market_summary"] = build_summary(
            game["bookmakers"]
        )

        game["sportsbook_count"] = len(
            game["bookmakers"]
        )

        game["markets_available"] = {
            "moneyline": bool(
                game["market_summary"]["moneyline"]
            ),
            "spread": bool(
                game["market_summary"]["spread"]
            ),
            "total": bool(
                game["market_summary"]["total"]
            ),
        }

        games.append(game)

    games.sort(
        key=lambda game: game["commence_time"]
    )

    week_counts = {}

    for week in range(1, 19):
        week_counts[str(week)] = sum(
            1 for game in games
            if game["week"] == week
        )

    output = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "season": 2026,
        "game_count": len(games),
        "weeks": week_counts,
        "games": games,
    }

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with OUTPUT.open("w") as file:
        json.dump(
            output,
            file,
            indent=2
        )

    print(f"Found {len(games)} games.")
    print()

    for week in range(1, 19):
        print(
            f"Week {week}: "
            f"{week_counts[str(week)]}"
        )

    ml = sum(
        1 for game in games
        if game["markets_available"]["moneyline"]
    )

    spread = sum(
        1 for game in games
        if game["markets_available"]["spread"]
    )

    total = sum(
        1 for game in games
        if game["markets_available"]["total"]
    )

    print()
    print(
        f"Games with moneyline: {ml}/{len(games)}"
    )
    print(
        f"Games with spread:    {spread}/{len(games)}"
    )
    print(
        f"Games with O/U:       {total}/{len(games)}"
    )

    print()
    print(
        f"Saved to {OUTPUT}"
    )


if __name__ == "__main__":
    main()
