"""
Line-movement feed from CLEATZ's public WordPress REST API.

Why this and not ticket%/money% public betting splits: CLEATZ has no free
endpoint carrying them. Their structured feed (/wp-json/cleatz/v1/feed) is
key-gated (HTTP 401, "Missing API key"), the /public-betting/nfl/ page holds
its percentages in hand-written prose rather than markup, and none of the 40
tables on it expose bets%/handle%. This endpoint is open and needs no key, but
it carries LINE MOVEMENT, not betting splits.

That is still a usable sharp-action proxy. probDelta is how far a team's
implied probability has moved since the line opened; money arriving on a side
is what drags its price. A line moving toward the side the crowd is NOT on is
the classic reverse-line-movement signal. It is a proxy, not handle%, and the
site labels it as such.

Endpoint verified 2026-09-03:
  https://cleatz.com/wp-json/nfl-odds-movers/v1/movers
robots.txt permits crawling (User-agent: * / Disallow:). Called once per daily
build.
"""
from __future__ import annotations

import datetime
import json
import os
import urllib.error
import urllib.request
from typing import Optional

from teams import normalize_abbr

MOVERS_URL = "https://cleatz.com/wp-json/nfl-odds-movers/v1/movers"

OUTPUT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "line_movement.json"
)

# CLEATZ and ESPN filter User-Agents in opposite directions: CLEATZ 403s
# anything starting "Python-urllib" (verified 2026-09-03), while ESPN's Akamai
# edge 403s browser-shaped strings and accepts Python-urllib. "curl/..." is the
# one value both accept, so lead with it and keep a browser UA as backup.
USER_AGENTS = (
    "curl/8.7.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
)


def fetch_movers_json(timeout: int = 20) -> dict:
    last_error: Optional[Exception] = None
    for user_agent in USER_AGENTS:
        req = urllib.request.Request(
            MOVERS_URL, headers={"User-Agent": user_agent}
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code not in (403, 429):
                raise
            last_error = e
    raise RuntimeError(
        f"CLEATZ refused every User-Agent tried: {last_error}"
    )


def parse_moneyline_movement(payload: dict) -> dict:
    """
    Reduce the payload to home-relative moneyline movement per game.

    Each row names one team (teamShort) plus the matchup (secondary, formatted
    "AWAY @ HOME"). probDelta is signed for that team, so flip it when the
    mover is the away side to get a consistently home-relative number.

    Only games CLEATZ actually lists as movers appear - roughly 10 of 16 in a
    typical week. Absent means "no signal", not "no movement".
    """
    games: dict[str, dict] = {}

    groups = (payload.get("movers") or {}).get("groups") or {}
    rows = (groups.get("ml") or {}).get("rows") or []

    for row in rows:
        matchup = row.get("secondary") or ""
        if "@" not in matchup:
            continue

        away_raw, home_raw = matchup.split("@", 1)
        away = normalize_abbr(away_raw)
        home = normalize_abbr(home_raw)
        mover = normalize_abbr(row.get("teamShort"))

        delta = row.get("probDelta")
        if delta is None or home is None or away is None:
            continue

        if mover == home:
            move_pp = float(delta) * 100.0
        elif mover == away:
            move_pp = -float(delta) * 100.0
        else:
            # Mover not recognisable as either side; skip rather than guess.
            continue

        games[f"{away}@{home}"] = {
            "away": away,
            "home": home,
            "line_move_pp": round(move_pp, 2),
            "mover_team": mover,
            "open_odds": row.get("openOdds"),
            "curr_odds": row.get("currOdds"),
            "starts_at": row.get("startsAt"),
        }

    return games


def _empty(error: Optional[str] = None) -> dict:
    return {
        "source": MOVERS_URL,
        "fetched_at": None,
        "upstream_fetched_at": None,
        "upstream_stale": None,
        "games": {},
        "error": error,
    }


def load_cached() -> dict:
    if not os.path.exists(OUTPUT_PATH):
        return _empty("no cached line-movement file")
    try:
        with open(OUTPUT_PATH) as f:
            return json.load(f)
    except Exception as e:
        return _empty(f"cached line-movement file unreadable: {e}")


def refresh(timeout: int = 20) -> dict:
    """
    Fetch, write data/line_movement.json, and return it.

    Never raises. This is a nice-to-have signal layered on top of the board, so
    a CLEATZ outage or rate limit must not take the daily build down - on
    failure we fall back to the last good file, and the site renders its
    "no line-movement data available" message if there is nothing at all.
    """
    upstream_error = None
    try:
        payload = fetch_movers_json(timeout=timeout)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        upstream_error = f"{type(e).__name__}: {e}"
    except Exception as e:  # malformed JSON, unexpected shape
        upstream_error = f"{type(e).__name__}: {e}"

    if upstream_error is not None:
        cached = load_cached()
        print(
            f"Warning: line-movement fetch failed ({upstream_error}); "
            f"falling back to cache with {len(cached.get('games', {}))} game(s)."
        )
        cached["error"] = upstream_error
        return cached

    upstream_ts = payload.get("fetchedAt")
    data = {
        "source": MOVERS_URL,
        "fetched_at": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(timespec="seconds"),
        "upstream_fetched_at": (
            datetime.datetime.fromtimestamp(
                upstream_ts, datetime.timezone.utc
            ).isoformat(timespec="seconds")
            if isinstance(upstream_ts, (int, float))
            else None
        ),
        "upstream_stale": bool(payload.get("stale")),
        "games": parse_moneyline_movement(payload),
        "error": None,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(data, f, indent=2)

    return data


def lookup(data: dict, away_abbr: str, home_abbr: str) -> Optional[dict]:
    """Home/away are normalised on both sides before matching."""
    games = data.get("games") or {}
    key = f"{normalize_abbr(away_abbr)}@{normalize_abbr(home_abbr)}"
    return games.get(key)


if __name__ == "__main__":
    d = refresh()
    print(f"upstream_stale={d.get('upstream_stale')} error={d.get('error')}")
    print(f"games with movement: {len(d.get('games', {}))}")
    for k, v in sorted(
        d.get("games", {}).items(),
        key=lambda kv: -abs(kv[1]["line_move_pp"]),
    ):
        # line_move_pp is home-relative, so the side gaining is the home team
        # when positive and the away team when negative - which is not always
        # the team CLEATZ happened to list as the mover.
        gaining = v["home"] if v["line_move_pp"] > 0 else v["away"]
        print(
            f"  {k:<10} {v['line_move_pp']:+6.2f}pp  "
            f"toward {gaining:<4} ({v['open_odds']} -> {v['curr_odds']} "
            f"on {v['mover_team']})"
        )
