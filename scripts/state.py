"""
Tiny JSON-file state store. This is the whole "database" for the project —
deliberately simple so it's just a file the GitHub Action commits back to
the repo every day. No server, no external DB needed.
"""
from __future__ import annotations
import json
import os

STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "elo_state.json")
SEED_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "elo_seed.json")


def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    with open(SEED_PATH) as f:
        seed = json.load(f)
    return {
        "current_season": 2026,
        "current_season_type": 1,   # 1=preseason at seed time; flips to 2 once the regular season starts
        "elo": dict(seed["elo"]),
        "team_names": seed["team_names"],
        "processed_game_ids": [],
        "bet_log": [],   # every VALUE call ever made, for season-long backtesting
    }


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)
