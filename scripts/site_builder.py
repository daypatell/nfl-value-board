from __future__ import annotations

import os
import json
import html
import datetime
from typing import List, Optional

from model import (
    DISAGREE_FLIP,
    DISAGREE_MARGIN,
    DISAGREE_SHARP_ALIGNED,
    MISMATCH_THRESHOLD_PP,
    GamePick,
)

DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "docs")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

TIER_CLASS = {
    "🔥 ELITE VALUE": "tier-elite",
    "🟢 STRONG VALUE": "tier-strong",
    "🟡 MODERATE VALUE": "tier-moderate",
    "⚪ LOW VALUE": "tier-low",
}


def esc(value) -> str:
    return html.escape(str(value))


def render_site(
    state: dict,
    picks: List[GamePick],
    week: int,
    season_type: int,
    year: int,
    line_movement_meta: Optional[dict] = None,
) -> None:

    names = state["team_names"]

    line_movement_meta = line_movement_meta or {}

    season_label = {
        1: "Preseason",
        2: "Regular Season",
        3: "Postseason",
    }.get(season_type, "")

    # During preseason the actual NFL current pointer can be preseason Week 4,
    # but we want to display the opening regular-season slate.
    display_week = 1 if season_type == 1 else week

    ranked = sorted(
        picks,
        key=lambda p: p.score_0_100,
        reverse=True,
    )

    value_picks = [
        p for p in ranked
        if p.action == "VALUE"
    ]

    lined_games = [
        p for p in ranked
        if p.market_home_win_prob is not None
    ]

    resolved_bets = [
        b for b in state.get("bet_log", [])
        if b.get("resolved")
    ]

    wins = sum(
        1 for b in resolved_bets
        if b.get("won")
    )

    record_line = (
        f"{wins}-{len(resolved_bets) - wins}"
        if resolved_bets
        else "0-0"
    )

    # ---------------------------------------------------------
    # LOAD FULL SEASON SCHEDULE
    # ---------------------------------------------------------

    markets_path = os.path.join(
        DATA_DIR,
        "season_markets.json",
    )

    season_games = []

    if os.path.exists(markets_path):
        try:
            with open(markets_path, "r") as f:
                season_data = json.load(f)

            season_games = season_data.get("games", [])
        except Exception as e:
            print(f"Warning: could not load season schedule: {e}")

    # ---------------------------------------------------------
    # WEEKLY BOARD
    # ---------------------------------------------------------

    week_rows = []

    for i, p in enumerate(ranked, 1):

        home_name = names.get(
            p.home_team,
            p.home_team,
        )

        away_name = names.get(
            p.away_team,
            p.away_team,
        )

        if p.side == "home":
            side_name = home_name
        elif p.side == "away":
            side_name = away_name
        else:
            side_name = "—"

        market_str = (
            f"{p.market_home_win_prob:.0%}"
            if p.market_home_win_prob is not None
            else "—"
        )

        edge_str = (
            f"{p.edge_pct:+.1f}pp"
            if p.edge_pct is not None
            else "-"
        )

        ev_str = (
            f"{("—" if p.ev_per_unit is None else f"{p.ev_per_unit:+.2f}")}"
            if p.ev_per_unit is not None
            else "—"
        )

        edge_cls = (
            "positive"
            if (p.edge_pct or 0) >= 0
            else "negative"
        )

        action_cls = (
            "action-value"
            if p.action == "VALUE"
            else "action-pass"
        )

        tier_cls = TIER_CLASS.get(
            p.tier,
            "tier-low",
        )

        week_rows.append(f"""
        <div class="game-row {tier_cls}">
            <div class="game-rank">{i:02d}</div>

            <div class="game-matchup">
                <div class="away">{esc(away_name)}</div>
                <div class="at">@</div>
                <div class="home">{esc(home_name)}</div>
            </div>

            <div class="game-pick">
                <span class="pick-label">MODEL PICK</span>
                <strong>{esc(side_name)}</strong>
            </div>

            <div class="prob">
                <span>{market_str}</span>
                <small>MARKET</small>
            </div>

            <div class="prob model">
                <span>{p.model_home_win_prob:.0%}</span>
                <small>MODEL</small>
            </div>

            <div class="edge {edge_cls}">
                {edge_str}
            </div>

            <div class="ev {edge_cls}">
                {ev_str}
            </div>

            <div class="score">
                {p.score_0_100}
            </div>

            <div class="{action_cls}">
                {esc(p.action)}
            </div>
        </div>
        """)

    # ---------------------------------------------------------
    # VALUE PICK CARDS
    # ---------------------------------------------------------

    pick_cards = []

    for p in value_picks:

        edge_display = (
            f"{p.edge_pct:+.1f}pp"
            if p.edge_pct is not None
            else "—"
        )

        home_name = names.get(
            p.home_team,
            p.home_team,
        )

        away_name = names.get(
            p.away_team,
            p.away_team,
        )

        side_name = (
            home_name
            if p.side == "home"
            else away_name
        )

        # Show the probabilities belonging to the bet this card is actually
        # displaying. edge_pct/ev come from p.best_bet, which is often the
        # SPREAD, so pairing them with moneyline win probabilities made the
        # card contradict itself: LAC read "MARKET 84% -> MODEL 89%" beside a
        # "+45.2pp" edge, where 89 - 84 is 4.3. Reading both numbers off
        # best_bet makes edge = model - market true by construction, and also
        # removes the home/away orientation guesswork, since a MarketPick is
        # already stated from the picked side's point of view.
        bet = p.best_bet

        if bet is not None:
            model_prob = bet.model_probability
            market_prob = bet.market_probability
            bet_label = bet.market
            bet_detail = bet.pick
        else:
            model_prob = (
                p.model_home_win_prob
                if p.side == "home"
                else 1.0 - p.model_home_win_prob
            )
            market_prob = (
                None
                if p.market_home_win_prob is None
                else (
                    p.market_home_win_prob
                    if p.side == "home"
                    else 1.0 - p.market_home_win_prob
                )
            )
            bet_label = "Moneyline"
            bet_detail = ""

        model_pct = (
            f"{model_prob:.0%}" if model_prob is not None else "—"
        )

        market_pct = (
            f"{market_prob:.0%}"
            if market_prob is not None
            else "—"
        )

        tier_cls = TIER_CLASS.get(
            p.tier,
            "tier-low",
        )

        pick_cards.append(f"""
        <article class="value-card {tier_cls}">

            <div class="value-top">
                <span class="tier">
                    {esc(p.tier)}
                </span>

                <span class="value-score">
                    {p.score_0_100}
                    <small>/100</small>
                </span>
            </div>

            <div class="value-team">
                {esc(side_name)}
            </div>

            <div class="value-matchup">
                {esc(away_name)} @ {esc(home_name)}
            </div>

            <div class="value-market">
                {esc(bet_label)}{f" &middot; {esc(bet_detail)}" if bet_detail else ""}
            </div>

            <div class="value-line">
                <div>
                    <strong>{market_pct}</strong>
                    <small>MARKET</small>
                </div>

                <span class="arrow">→</span>

                <div>
                    <strong class="model-number">
                        {model_pct}
                    </strong>
                    <small>MODEL</small>
                </div>

                <div class="edge-badge">
                    {edge_display}
                </div>
            </div>

            <div class="value-bottom">
                <span>EV</span>
                <strong>
                    {("—" if p.ev_per_unit is None else f"{p.ev_per_unit:+.2f}")}
                </strong>
            </div>

        </article>
        """)

    if not pick_cards:
        pick_cards.append("""
        <div class="empty-state">
            <div class="empty-icon">—</div>
            <h3>No qualifying value picks</h3>
            <p>
                No game currently clears the model's
                value threshold.
            </p>
        </div>
        """)

    # LINES TABLE
    # ---------------------------------------------------------

    line_rows = []

    for p in lined_games:

        home_name = names.get(
            p.home_team,
            p.home_team,
        )

        away_name = names.get(
            p.away_team,
            p.away_team,
        )

        edge_cls = (
            "positive"
            if (p.edge_pct or 0) >= 0
            else "negative"
        )

        edge_display = (
            f"{p.edge_pct:+.1f}pp"
            if p.edge_pct is not None
            else "-"
        )

        line_rows.append(f"""
        <div class="line-row">

            <div class="line-game">
                <strong>{esc(away_name)}</strong>
                <span>@</span>
                <strong>{esc(home_name)}</strong>
            </div>

            <div>
                {p.market_home_win_prob:.0%}
            </div>

            <div class="model-cell">
                {p.model_home_win_prob:.0%}
            </div>

            <div class="{edge_cls}">
                {edge_display}
            </div>

            <div class="{edge_cls}">
                {("—" if p.ev_per_unit is None else f"{p.ev_per_unit:+.2f}")}
            </div>

            <div>
                <span class="mini-action">
                    {esc(p.action)}
                </span>
            </div>

        </div>
        """)

    if not line_rows:
        line_rows.append("""
        <div class="empty-state small">
            No sportsbook lines available.
        </div>
        """)

    # ---------------------------------------------------------
    # TEAM SCHEDULES
    # ---------------------------------------------------------

    team_games = {}

    for game in season_games:

        try:
            game_week = int(game.get("week"))
        except Exception:
            continue

        home = game.get("home_team")
        away = game.get("away_team")

        if not home or not away:
            continue

        team_games.setdefault(home, []).append(game)
        team_games.setdefault(away, []).append(game)

    team_buttons = []
    team_panels = []

    sorted_teams = sorted(
        team_games.keys(),
        key=lambda x: names.get(x, x),
    )

    for index, team in enumerate(sorted_teams):

        team_name = names.get(
            team,
            team,
        )

        team_buttons.append(f"""
        <button
            class="team-button {'selected' if index == 0 else ''}"
            onclick="showTeam('{esc(team)}', this)"
        >
            {esc(team_name)}
        </button>
        """)

        games_for_team = sorted(
            team_games[team],
            key=lambda x: int(x.get("week", 99)),
        )

        schedule_rows = []

        for game in games_for_team:

            game_week = int(
                game.get("week", 0)
            )

            home = game.get(
                "home_team",
                "",
            )

            away = game.get(
                "away_team",
                "",
            )

            opponent = (
                away
                if home == team
                else home
            )

            location = (
                "HOME"
                if home == team
                else "AWAY"
            )

            schedule_rows.append(f"""
            <div class="schedule-row">

                <div class="schedule-week">
                    W{game_week}
                </div>

                <div class="schedule-opponent">
                    <strong>
                        {esc(names.get(opponent, opponent))}
                    </strong>

                    <span>
                        {location}
                    </span>
                </div>

                <div class="schedule-matchup">
                    {esc(names.get(away, away))}
                    @
                    {esc(names.get(home, home))}
                </div>

            </div>
            """)

        team_panels.append(f"""
        <div
            class="team-panel"
            id="team-{esc(team)}"
            style="display:{'block' if index == 0 else 'none'}"
        >

            <div class="team-panel-header">
                <div>
                    <span>2026 SEASON</span>
                    <h3>{esc(team_name)}</h3>
                </div>

                <div class="team-abbr">
                    {esc(team)}
                </div>
            </div>

            <div class="schedule-list">
                {''.join(schedule_rows)}
            </div>

        </div>
        """)

    # ---------------------------------------------------------
    # ELO LADDER
    # ---------------------------------------------------------

    ladder_rows = []

    ladder_sorted = sorted(
        state["elo"].items(),
        key=lambda kv: kv[1],
        reverse=True,
    )

    if ladder_sorted:

        max_elo = ladder_sorted[0][1]
        min_elo = ladder_sorted[-1][1]

        span = max(
            max_elo - min_elo,
            1,
        )

        for i, (tid, elo) in enumerate(
            ladder_sorted,
            1,
        ):

            pct = (
                (elo - min_elo)
                / span
                * 100
            )

            ladder_rows.append(f"""
            <div class="ladder-row">

                <span class="ladder-rank">
                    {i:02d}
                </span>

                <span class="ladder-name">
                    {esc(names.get(tid, tid))}
                </span>

                <div class="ladder-track">
                    <div
                        class="ladder-fill"
                        style="width:{pct:.1f}%"
                    ></div>
                </div>

                <span class="ladder-score">
                    {elo:.0f}
                </span>

            </div>
            """)

    # ---------------------------------------------------------
    # FAVORITE MISMATCHES  +  SHARP ACTION
    # ---------------------------------------------------------

    # Severity order, most severe first. MODEL + SHARP ALIGNMENT outranks a
    # plain flip because it is a flip that line movement agrees with.
    mismatch_order = {
        DISAGREE_SHARP_ALIGNED: 0,
        DISAGREE_FLIP: 1,
        DISAGREE_MARGIN: 2,
    }

    MISMATCH_LABEL_CLASS = {
        DISAGREE_SHARP_ALIGNED: "mm-aligned",
        DISAGREE_FLIP: "mm-flip",
        DISAGREE_MARGIN: "mm-margin",
    }

    mismatches = sorted(
        (p for p in picks if p.disagreement in mismatch_order),
        key=lambda p: (
            mismatch_order[p.disagreement],
            -(p.mismatch_pp or 0.0),
        ),
    )

    n_flip = sum(1 for p in picks if p.disagreement == DISAGREE_FLIP)
    n_aligned = sum(
        1 for p in picks if p.disagreement == DISAGREE_SHARP_ALIGNED
    )
    n_margin = sum(1 for p in picks if p.disagreement == DISAGREE_MARGIN)

    mismatch_cards = []

    for p in mismatches:
        home_name = names.get(p.home_team, p.home_team)
        away_name = names.get(p.away_team, p.away_team)

        # Which team each side actually favours, spelled out - "the model
        # disagrees" is only useful if you can see who it disagrees about.
        model_fav = (
            home_name
            if p.model_home_win_prob > 0.5
            else away_name
        )

        market_fav = (
            home_name
            if (p.market_home_win_prob_devig or 0.0) > 0.5
            else away_name
        )

        model_fav_prob = max(
            p.model_home_win_prob,
            1.0 - p.model_home_win_prob,
        )

        market_fav_prob = max(
            p.market_home_win_prob_devig or 0.0,
            1.0 - (p.market_home_win_prob_devig or 0.0),
        )

        if p.sharp_side == "home":
            sharp_note = f"Line moving toward {esc(home_name)}"
        elif p.sharp_side == "away":
            sharp_note = f"Line moving toward {esc(away_name)}"
        else:
            sharp_note = "No meaningful line movement"

        if p.line_move_pp is not None:
            sharp_note += f" ({p.line_move_pp:+.2f}pp)"

        mismatch_cards.append(f"""
        <article class="mm-card {MISMATCH_LABEL_CLASS[p.disagreement]}">

            <div class="mm-top">
                <span class="mm-badge">{esc(p.disagreement)}</span>
                <span class="mm-gap">{p.mismatch_pp:.1f}pp apart</span>
            </div>

            <div class="mm-matchup">
                {esc(away_name)} @ {esc(home_name)}
            </div>

            <div class="mm-split">
                <div class="mm-col">
                    <span class="mm-lbl">Market favours</span>
                    <strong>{esc(market_fav)}</strong>
                    <span class="mm-pct">{market_fav_prob:.0%}</span>
                </div>
                <span class="mm-vs">vs</span>
                <div class="mm-col mm-col-model">
                    <span class="mm-lbl">Model favours</span>
                    <strong>{esc(model_fav)}</strong>
                    <span class="mm-pct">{model_fav_prob:.0%}</span>
                </div>
            </div>

            <div class="mm-sharp">{sharp_note}</div>

        </article>""")

    if not mismatch_cards:
        mismatch_body = (
            '<p class="mm-empty">No mismatches this week &mdash; the model '
            'and the market agree on every priced game, within the '
            f'{MISMATCH_THRESHOLD_PP:.0f}pp threshold.</p>'
        )
    else:
        mismatch_body = (
            '<div class="mm-grid">' + "".join(mismatch_cards) + "</div>"
        )

    # ---- Sharp action / line movement table ----

    sharp_rows = []

    for p in sorted(
        (x for x in picks if x.line_move_pp is not None),
        key=lambda x: -abs(x.line_move_pp),
    ):
        home_name = names.get(p.home_team, p.home_team)
        away_name = names.get(p.away_team, p.away_team)

        gaining = home_name if p.line_move_pp > 0 else away_name
        move_cls = "positive" if p.line_move_pp > 0 else "negative"

        sharp_rows.append(f"""
        <div class="sharp-row">
            <div class="sharp-matchup">{esc(away_name)} @ {esc(home_name)}</div>
            <div class="sharp-move {move_cls}">{p.line_move_pp:+.2f}pp</div>
            <div class="sharp-toward">{esc(gaining)}</div>
            <div class="sharp-label">{esc(p.disagreement)}</div>
        </div>""")

    if sharp_rows:
        sharp_body = "".join(sharp_rows)
    else:
        sharp_body = (
            '<p class="mm-empty">No public data available &mdash; the '
            'line-movement feed returned nothing for this slate.</p>'
        )

    sharp_meta_parts = []
    if line_movement_meta.get("upstream_fetched_at"):
        sharp_meta_parts.append(
            f"feed timestamped {esc(line_movement_meta['upstream_fetched_at'])}"
        )
    if line_movement_meta.get("upstream_stale"):
        sharp_meta_parts.append("upstream reports this data as stale")
    if line_movement_meta.get("error"):
        sharp_meta_parts.append(
            f"last fetch failed: {esc(line_movement_meta['error'])}"
        )
    sharp_meta = " &middot; ".join(sharp_meta_parts)

    # ---------------------------------------------------------
    # STATS
    # ---------------------------------------------------------

    n_games = len(picks)
    n_value = len(value_picks)
    n_lined = len(lined_games)
    n_with_move = sum(1 for p in picks if p.line_move_pp is not None)

    edges = [
        abs(p.edge_pct)
        for p in picks
        if p.edge_pct is not None
    ]

    avg_edge = (
        sum(edges) / len(edges)
        if edges
        else 0
    )

    now = datetime.datetime.now(
        datetime.timezone.utc
    ).strftime(
        "%Y-%m-%d %H:%M UTC"
    )

    # ---------------------------------------------------------
    # HTML
    # ---------------------------------------------------------

    html_page = f"""<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>NFL Value Board — 2026</title>

<link rel="preconnect" href="https://fonts.googleapis.com">

<link
href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap"
rel="stylesheet"
>

<style>

:root {{
    --bg:#080d0b;
    --panel:#101916;
    --panel2:#151f1b;
    --border:#23332d;
    --text:#edf2ef;
    --muted:#81948b;
    --gold:#f2b705;
    --green:#5fcb8c;
    --red:#df718f;
}}

/* ---- Favorite mismatches ---- */
.mm-band{{border-bottom:1px solid var(--border);background:
  radial-gradient(ellipse at top left,rgba(242,183,5,.07),transparent 60%),var(--panel);}}
.mm-inner{{max-width:1180px;margin:0 auto;padding:28px 28px 32px;}}
.mm-head{{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:16px;}}
.mm-head h2{{font-family:'Oswald',sans-serif;text-transform:uppercase;font-size:19px;
  letter-spacing:.04em;margin:0;color:var(--gold);}}
.mm-head span{{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--muted);}}
.mm-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:14px;}}
.mm-card{{background:var(--panel2);border:1px solid var(--border);
  border-left:3px solid var(--muted);border-radius:5px;padding:15px 17px;}}
.mm-card.mm-aligned{{border-left-color:var(--gold);}}
.mm-card.mm-flip{{border-left-color:var(--red);}}
.mm-card.mm-margin{{border-left-color:var(--green);}}
.mm-top{{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:9px;}}
.mm-badge{{font-family:'JetBrains Mono',monospace;font-size:9.5px;letter-spacing:.09em;
  text-transform:uppercase;color:var(--text);}}
.mm-gap{{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--muted);white-space:nowrap;}}
.mm-matchup{{font-family:'Oswald',sans-serif;font-size:17px;text-transform:uppercase;
  margin-bottom:12px;}}
.mm-split{{display:flex;align-items:center;gap:10px;}}
.mm-col{{display:flex;flex-direction:column;gap:1px;min-width:0;flex:1;}}
.mm-col strong{{font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
.mm-col-model strong{{color:var(--gold);}}
.mm-lbl{{font-size:9px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);}}
.mm-pct{{font-family:'JetBrains Mono',monospace;font-size:14px;}}
.mm-vs{{font-size:10px;color:var(--muted);text-transform:uppercase;}}
.mm-sharp{{margin-top:11px;padding-top:9px;border-top:1px solid var(--border);
  font-size:11px;color:var(--muted);}}
.mm-empty{{color:var(--muted);font-size:13px;margin:0;}}
.value-market{{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.06em;
  text-transform:uppercase;color:var(--gold);margin:-6px 0 10px;}}

/* ---- Sharp action ---- */
.sharp-row{{display:grid;grid-template-columns:1fr 92px 1fr 190px;gap:12px;align-items:center;
  padding:9px 0;border-bottom:1px solid var(--border);font-size:13px;}}
.sharp-move{{font-family:'JetBrains Mono',monospace;text-align:right;}}
.sharp-move.positive{{color:var(--green);}} .sharp-move.negative{{color:var(--red);}}
.sharp-toward{{color:var(--text);}}
.sharp-label{{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.06em;
  text-transform:uppercase;color:var(--muted);text-align:right;}}
.sharp-note{{color:var(--muted);font-size:11px;margin:10px 0 0;}}
@media (max-width:720px){{
  .sharp-row{{grid-template-columns:1fr 80px;row-gap:2px;}}
  .sharp-toward,.sharp-label{{text-align:left;grid-column:1 / -1;font-size:11px;}}
}}

* {{
    box-sizing:border-box;
}}

html {{
    scroll-behavior:smooth;
}}

body {{
    margin:0;
    background:var(--bg);
    color:var(--text);
    font-family:Inter,sans-serif;
}}

button {{
    font-family:inherit;
}}

.hero {{
    padding:55px 24px 38px;
    border-bottom:1px solid var(--border);
    background:
        radial-gradient(
            ellipse at top left,
            rgba(242,183,5,.10),
            transparent 55%
        );
}}

.hero-inner,
.wrap {{
    max-width:1180px;
    margin:auto;
}}

.eyebrow {{
    color:var(--gold);
    font-family:JetBrains Mono,monospace;
    font-size:12px;
    letter-spacing:.16em;
    text-transform:uppercase;
}}

h1 {{
    font-family:Oswald,sans-serif;
    font-size:clamp(42px,7vw,76px);
    line-height:.95;
    text-transform:uppercase;
    margin:8px 0 12px;
}}

.sub {{
    max-width:680px;
    color:var(--muted);
    font-size:15px;
}}

.stats {{
    display:grid;
    grid-template-columns:repeat(5,1fr);
    margin-top:32px;
    border:1px solid var(--border);
}}

.stat {{
    padding:17px;
    border-right:1px solid var(--border);
}}

.stat:last-child {{
    border-right:0;
}}

.stat strong {{
    display:block;
    font-family:Oswald,sans-serif;
    font-size:27px;
}}

.stat span {{
    color:var(--muted);
    font-size:10px;
    letter-spacing:.08em;
    text-transform:uppercase;
}}

.nav {{
    position:sticky;
    top:0;
    z-index:20;
    background:rgba(8,13,11,.96);
    border-bottom:1px solid var(--border);
}}

.nav-inner {{
    max-width:1180px;
    margin:auto;
    display:flex;
    overflow-x:auto;
}}

.nav button {{
    background:none;
    color:var(--muted);
    border:0;
    padding:17px 22px;
    cursor:pointer;
    font-size:12px;
    font-weight:700;
    letter-spacing:.08em;
    white-space:nowrap;
}}

.nav button:hover,
.nav button.active {{
    color:var(--gold);
}}

.section {{
    padding:45px 0;
}}

.section-title {{
    display:flex;
    align-items:baseline;
    gap:12px;
    border-bottom:1px solid var(--border);
    padding-bottom:12px;
    margin-bottom:22px;
}}

.section-title h2 {{
    font-family:Oswald,sans-serif;
    color:var(--gold);
    text-transform:uppercase;
    font-size:25px;
    margin:0;
}}

.section-title span {{
    color:var(--muted);
    font-size:12px;
}}

.game-row {{
    display:grid;
    grid-template-columns:42px minmax(220px,1.6fr) 1.2fr 75px 75px 80px 75px 60px 180px;
    align-items:center;
    gap:10px;
    padding:14px 12px;
    border-bottom:1px solid var(--border);
    background:rgba(255,255,255,.01);
}}

.game-row:hover {{
    background:var(--panel);
}}

.game-rank {{
    color:var(--muted);
    font-family:JetBrains Mono,monospace;
}}

.game-matchup {{
    display:flex;
    align-items:center;
    gap:7px;
    font-weight:700;
}}

.game-matchup .at {{
    color:var(--muted);
}}

.game-pick {{
    font-size:13px;
}}

.pick-label {{
    display:block;
    color:var(--muted);
    font-size:9px;
    margin-bottom:3px;
}}

.prob span,
.score {{
    font-family:JetBrains Mono,monospace;
}}

.prob small {{
    display:block;
    color:var(--muted);
    font-size:8px;
}}

.model {{
    color:var(--gold);
}}

.edge,
.ev {{
    font-family:JetBrains Mono,monospace;
    font-size:12px;
}}

.positive {{
    color:var(--green);
}}

.negative {{
    color:var(--red);
}}

.score {{
    font-weight:700;
}}

.action-value {{
    color:var(--green);
    font-size:11px;
    font-weight:700;
}}

.action-pass {{
    color:var(--muted);
    font-size:11px;
}}

.value-grid {{
    display:grid;
    grid-template-columns:repeat(auto-fit,minmax(285px,1fr));
    gap:17px;
}}

.value-card {{
    background:var(--panel);
    border:1px solid var(--border);
    border-left:3px solid var(--muted);
    padding:20px;
}}

.tier-elite {{
    border-left-color:var(--gold);
}}

.tier-strong {{
    border-left-color:var(--green);
}}

.tier-moderate {{
    border-left-color:var(--gold);
}}

.value-top {{
    display:flex;
    justify-content:space-between;
}}

.tier {{
    color:var(--muted);
    font-size:10px;
    text-transform:uppercase;
}}

.value-score {{
    font-family:JetBrains Mono,monospace;
}}

.value-score small {{
    color:var(--muted);
}}

.value-team {{
    font-family:Oswald,sans-serif;
    text-transform:uppercase;
    font-size:27px;
    margin-top:14px;
}}

.value-matchup {{
    color:var(--muted);
    font-size:12px;
    margin-top:3px;
}}

.value-line {{
    display:flex;
    align-items:center;
    gap:14px;
    margin-top:25px;
}}

.value-line strong {{
    display:block;
    font-family:JetBrains Mono,monospace;
    font-size:21px;
}}

.value-line small {{
    color:var(--muted);
    font-size:8px;
}}

.model-number {{
    color:var(--gold);
}}

.arrow {{
    color:var(--muted);
}}

.edge-badge {{
    margin-left:auto;
    background:rgba(95,203,140,.12);
    color:var(--green);
    padding:6px 10px;
    border-radius:20px;
    font-family:JetBrains Mono,monospace;
    font-size:12px;
}}

.value-bottom {{
    display:flex;
    justify-content:space-between;
    border-top:1px solid var(--border);
    margin-top:18px;
    padding-top:12px;
    color:var(--muted);
    font-size:11px;
}}

.value-bottom strong {{
    color:var(--green);
    font-family:JetBrains Mono,monospace;
}}

.line-row {{
    display:grid;
    grid-template-columns:2fr 100px 100px 100px 100px 150px;
    align-items:center;
    padding:14px;
    border-bottom:1px solid var(--border);
    font-family:JetBrains Mono,monospace;
    font-size:12px;
}}

.line-game {{
    font-family:Inter,sans-serif;
}}

.line-game span {{
    color:var(--muted);
    margin:0 5px;
}}

.model-cell {{
    color:var(--gold);
}}

.mini-action {{
    color:var(--muted);
    font-family:Inter,sans-serif;
    font-size:10px;
}}

.team-selector {{
    display:flex;
    gap:8px;
    flex-wrap:wrap;
    margin-bottom:20px;
}}

.team-button {{
    background:var(--panel);
    color:var(--muted);
    border:1px solid var(--border);
    padding:9px 12px;
    cursor:pointer;
    border-radius:3px;
    font-size:11px;
}}

.team-button:hover,
.team-button.selected {{
    color:var(--bg);
    background:var(--gold);
    border-color:var(--gold);
}}

.team-panel {{
    background:var(--panel);
    border:1px solid var(--border);
}}

.team-panel-header {{
    display:flex;
    justify-content:space-between;
    align-items:center;
    padding:25px;
    border-bottom:1px solid var(--border);
}}

.team-panel-header span {{
    color:var(--muted);
    font-size:9px;
    letter-spacing:.1em;
}}

.team-panel-header h3 {{
    font-family:Oswald,sans-serif;
    text-transform:uppercase;
    font-size:32px;
    margin:5px 0 0;
}}

.team-abbr {{
    color:var(--gold);
    font-family:JetBrains Mono,monospace;
    font-weight:700;
}}

.schedule-row {{
    display:grid;
    grid-template-columns:70px 1fr 2fr;
    padding:14px 20px;
    border-bottom:1px solid var(--border);
    align-items:center;
}}

.schedule-week {{
    color:var(--gold);
    font-family:JetBrains Mono,monospace;
    font-size:12px;
}}

.schedule-opponent strong {{
    display:block;
}}

.schedule-opponent span {{
    color:var(--muted);
    font-size:9px;
}}

.schedule-matchup {{
    color:var(--muted);
    font-size:12px;
}}

.ladder-row {{
    display:grid;
    grid-template-columns:35px 1fr 250px 60px;
    gap:12px;
    align-items:center;
    padding:8px 0;
    border-bottom:1px solid var(--border);
}}

.ladder-rank,
.ladder-score {{
    font-family:JetBrains Mono,monospace;
    color:var(--muted);
}}

.ladder-track {{
    height:5px;
    background:var(--panel2);
}}

.ladder-fill {{
    height:100%;
    background:linear-gradient(
        90deg,
        var(--gold),
        var(--green)
    );
}}

.empty-state {{
    border:1px dashed var(--border);
    padding:45px;
    text-align:center;
    color:var(--muted);
    grid-column:1/-1;
}}

.empty-state h3 {{
    color:var(--text);
    font-family:Oswald,sans-serif;
    text-transform:uppercase;
}}

.empty-icon {{
    font-size:30px;
    color:var(--gold);
}}

footer {{
    border-top:1px solid var(--border);
    margin-top:40px;
    padding:30px 0 60px;
    color:var(--muted);
    font-size:11px;
    line-height:1.7;
}}

@media(max-width:850px) {{

    .stats {{
        grid-template-columns:repeat(2,1fr);
    }}

    .stat {{
        border-bottom:1px solid var(--border);
    }}

    .game-row {{
        grid-template-columns:30px 1fr 70px 70px;
    }}

    .game-pick,
    .edge,
    .ev,
    .action-pass,
    .action-value {{
        display:none;
    }}

    .line-row {{
        grid-template-columns:1fr 70px 70px 80px;
    }}

    .line-row > div:nth-child(5),
    .line-row > div:nth-child(6) {{
        display:none;
    }}

    .ladder-row {{
        grid-template-columns:30px 1fr 90px 50px;
    }}

}}

</style>

</head>

<body>

<header class="hero">

<div class="hero-inner">

<p class="eyebrow">
2026 NFL Season · {esc(season_label)} · Week {display_week} · Model vs Market
</p>

<h1>The Value Board</h1>

<p class="sub">
An automated NFL prediction market comparing the model's
win probabilities against current sportsbook pricing.
</p>

<div class="stats">

<div class="stat">
<strong>{n_games}</strong>
<span>Games This Week</span>
</div>

<div class="stat">
<strong>{n_lined}</strong>
<span>Games With Lines</span>
</div>

<div class="stat">
<strong>{n_value}</strong>
<span>Value Picks</span>
</div>

<div class="stat">
<strong>{avg_edge:.1f}pp</strong>
<span>Avg Edge</span>
</div>

<div class="stat">
<strong>{record_line}</strong>
<span>Season Record</span>
</div>

</div>

</div>

</header>


<div class="mm-band">
<div class="mm-inner">

<div class="mm-head">
<h2>Favorite Mismatches</h2>
<span>
{n_aligned} sharp-aligned &middot; {n_flip} favourite flip &middot; {n_margin} margin
</span>
</div>

{mismatch_body}

</div>
</div>


<nav class="nav">

<div class="nav-inner">

<button
class="active"
onclick="showSection('weekly', this)"
>
WEEKLY BOARD
</button>

<button
onclick="showSection('value', this)"
>
VALUE PICKS
</button>

<button
onclick="showSection('lines', this)"
>
GAMES WITH LINES
</button>

<button
onclick="showSection('teams', this)"
>
TEAM SCHEDULES
</button>

<button
onclick="showSection('sharp', this)"
>
SHARP ACTION
</button>

<button
onclick="showSection('elo', this)"
>
ELO LADDER
</button>

</div>

</nav>


<main class="wrap">


<section
id="weekly"
class="section site-section"
>

<div class="section-title">

<h2>Week {display_week} Games</h2>

<span>
{n_games} games evaluated
</span>

</div>

<div class="game-row" style="font-size:9px;color:var(--muted);text-transform:uppercase;">

<div>#</div>
<div>Matchup</div>
<div>Model Pick</div>
<div>Market</div>
<div>Model</div>
<div>Edge</div>
<div>EV</div>
<div>Score</div>
<div>Action</div>

</div>

{''.join(week_rows)}

</section>


<section
id="value"
class="section site-section"
style="display:none"
>

<div class="section-title">

<h2>Value Picks</h2>

<span>
Live model opportunities for Week {display_week}
</span>

</div>

<div class="value-grid">

{''.join(pick_cards)}

</div>

</section>


<section
id="lines"
class="section site-section"
style="display:none"
>

<div class="section-title">

<h2>Games With Lines</h2>

<span>
{n_lined} games currently matched to sportsbook prices
</span>

</div>

<div class="line-row"
style="color:var(--muted);font-size:9px;text-transform:uppercase;"
>

<div>Game</div>
<div>Market</div>
<div>Model</div>
<div>Edge</div>
<div>EV</div>
<div>Action</div>

</div>

{''.join(line_rows)}

</section>


<section
id="teams"
class="section site-section"
style="display:none"
>

<div class="section-title">

<h2>Team Schedules</h2>

<span>
2026 full regular-season schedule
</span>

</div>

<div class="team-selector">

{''.join(team_buttons)}

</div>

{''.join(team_panels)}

</section>


<section
id="sharp"
class="section site-section"
style="display:none"
>

<div class="section-title">

<h2>Sharp vs Public Split</h2>

<span>
Line movement as a sharp-action proxy &mdash; {n_with_move} of {n_games} games
</span>

</div>

{sharp_body}

<p class="sharp-note">
Positive means the home team's implied probability has risen since the line
opened; money arriving on a side is what moves its price, so the direction of
travel stands in for where the sharp money is going. This is line movement from
CLEATZ's public odds-movers feed, <strong>not</strong> ticket%/handle% betting
splits &mdash; no free source for those was available. {sharp_meta}
</p>

</section>


<section
id="elo"
class="section site-section"
style="display:none"
>

<div class="section-title">

<h2>Elo Power Ladder</h2>

<span>
Updates after completed games
</span>

</div>

<div>

{''.join(ladder_rows)}

</div>

</section>


<footer>

<p>
<strong>Model:</strong>
538-style Elo rating per team with home-field adjustment,
expected margin, and Monte Carlo win probability.
</p>

<p>
<strong>Market:</strong>
Current sportsbook market probabilities supplied by
the odds feed.
</p>

<p>
<strong>Updates:</strong>
The automated update script pulls schedule/results data,
updates Elo ratings, refreshes sportsbook prices, reruns
the prediction model, and rebuilds this website.
</p>

<p>
Last updated: {esc(now)}
</p>

<p>
Not financial advice. Model outputs are probabilities and
hypotheses, not guarantees.
</p>

</footer>


</main>


<script>

function showSection(id, button) {{

    document
        .querySelectorAll('.site-section')
        .forEach(section => {{
            section.style.display = 'none';
        }});

    document.getElementById(id).style.display = 'block';

    document
        .querySelectorAll('.nav button')
        .forEach(btn => {{
            btn.classList.remove('active');
        }});

    button.classList.add('active');

    window.scrollTo({{
        top: 0,
        behavior: 'smooth'
    }});
}}


function showTeam(team, button) {{

    document
        .querySelectorAll('.team-panel')
        .forEach(panel => {{
            panel.style.display = 'none';
        }});

    const selected =
        document.getElementById('team-' + team);

    if (selected) {{
        selected.style.display = 'block';
    }}

    document
        .querySelectorAll('.team-button')
        .forEach(btn => {{
            btn.classList.remove('selected');
        }});

    button.classList.add('selected');
}}

</script>


</body>

</html>
"""

    os.makedirs(
        DOCS_DIR,
        exist_ok=True,
    )

    output_path = os.path.join(
        DOCS_DIR,
        "index.html",
    )

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as f:
        f.write(html_page)


    print(f"Website rebuilt: {output_path}")
