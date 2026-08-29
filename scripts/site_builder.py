from __future__ import annotations
import os
import datetime
from typing import List
from model import GamePick

DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "docs")

TIER_CLASS = {
    "\U0001F525 ELITE VALUE": "tier-elite",
    "\U0001F7E2 STRONG VALUE": "tier-strong",
    "\U0001F7E1 MODERATE VALUE": "tier-moderate",
    "\u26aa LOW VALUE": "tier-low",
}


def render_site(state: dict, picks: List[GamePick], week: int, season_type: int, year: int) -> None:
    names = state["team_names"]
    season_label = {1: "Preseason", 2: "Regular Season", 3: "Postseason"}.get(season_type, "")
    ranked = sorted(picks, key=lambda p: p.score_0_100, reverse=True)
    value_picks = [p for p in ranked if p.action == "VALUE"]

    resolved_bets = [b for b in state.get("bet_log", []) if b.get("resolved")]
    wins = sum(1 for b in resolved_bets if b.get("won"))
    record_line = f"{wins}-{len(resolved_bets) - wins}" if resolved_bets else "0-0 (season just started)"

    rows = []
    for i, p in enumerate(ranked, 1):
        home_name, away_name = names.get(p.home_team, p.home_team), names.get(p.away_team, p.away_team)
        side_name = home_name if p.side == "home" else away_name if p.side == "away" else "\u2014"
        edge_str = f"{p.edge_pct:+.1f}pp" if p.edge_pct is not None else "\u2014"
        market_str = f"{p.market_home_win_prob:.0%}" if p.market_home_win_prob is not None else "\u2014"
        ev_str = f"{p.ev_per_unit:+.2f}" if p.ev_per_unit is not None else "\u2014"
        edge_cls = "pos" if (p.edge_pct or 0) >= 0 else "neg"
        tier_cls = TIER_CLASS.get(p.tier, "tier-low")
        rows.append(f"""
        <tr class="{tier_cls}">
          <td class="rank">{i}</td>
          <td class="matchup">{p.away_team}<span class="at">@</span>{p.home_team}</td>
          <td>{side_name}</td>
          <td class="mono">{market_str}</td>
          <td class="mono">{p.model_home_win_prob:.0%}</td>
          <td class="mono {edge_cls}">{edge_str}</td>
          <td class="mono {edge_cls}">{ev_str}</td>
          <td class="mono">{p.score_0_100}</td>
          <td class="action">{p.action}</td>
        </tr>""")

    pick_cards = []
    for p in value_picks:
        home_name, away_name = names.get(p.home_team, p.home_team), names.get(p.away_team, p.away_team)
        side_name = home_name if p.side == "home" else away_name
        tier_cls = TIER_CLASS.get(p.tier, "tier-low")
        market_pct = f"{p.market_home_win_prob:.0%}" if p.market_home_win_prob is not None else "\u2014"
        pick_cards.append(f"""
        <article class="pick-card {tier_cls}">
          <div class="pick-head"><span class="pick-tier">{p.tier}</span><span class="pick-score">{p.score_0_100}<span class="unit">/100</span></span></div>
          <h3 class="pick-team">{side_name} <span class="side-tag">{p.side.upper()}</span></h3>
          <p class="pick-sub">{p.away_team} @ {p.home_team}</p>
          <div class="pick-stats">
            <div><span class="num">{market_pct}</span><span class="lbl">Market</span></div>
            <div class="arrow">&rarr;</div>
            <div><span class="num accent">{p.model_home_win_prob:.0%}</span><span class="lbl">Model</span></div>
            <div class="edge-pill">{p.edge_pct:+.1f}pp</div>
          </div>
        </article>""")

    ladder_rows = []
    ladder_sorted = sorted(state["elo"].items(), key=lambda kv: kv[1], reverse=True)
    max_elo, min_elo = ladder_sorted[0][1], ladder_sorted[-1][1]
    span = max(max_elo - min_elo, 1)
    for i, (tid, elo) in enumerate(ladder_sorted, 1):
        pct = (elo - min_elo) / span * 100
        ladder_rows.append(f"""
        <div class="ladder-row">
          <span class="ladder-rank">{i:02d}</span>
          <span class="ladder-name">{names.get(tid, tid)}</span>
          <div class="ladder-bar-track"><div class="ladder-bar" style="width:{pct:.1f}%"></div></div>
          <span class="ladder-score mono">{elo:.0f}</span>
        </div>""")

    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    n_games, n_value = len(picks), len(value_picks)
    avg_edge = (sum(abs(p.edge_pct) for p in picks if p.edge_pct is not None) /
                max(sum(1 for p in picks if p.edge_pct is not None), 1))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NFL Value Board &mdash; live</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root {{ --bg-deep:#0B1210; --bg-panel:#121C19; --bg-panel-2:#17221E; --hairline:#24332E;
  --text-primary:#EDF2EF; --text-muted:#7E948B; --amber:#F2B705; --green:#5FCB8C; --rose:#D9678C; }}
*{{box-sizing:border-box;}} body{{margin:0;background:var(--bg-deep);color:var(--text-primary);font-family:'Inter',sans-serif;line-height:1.5;}}
.mono{{font-family:'JetBrains Mono',monospace;}} .wrap{{max-width:1080px;margin:0 auto;padding:0 24px 80px;}}
.hero{{background:radial-gradient(ellipse at top left, rgba(242,183,5,0.08), transparent 60%), linear-gradient(180deg,#0E1613 0%,var(--bg-deep) 100%); border-bottom:1px solid var(--hairline); padding:56px 24px 40px;}}
.hero-inner{{max-width:1080px;margin:0 auto;}}
.eyebrow{{font-family:'JetBrains Mono',monospace;font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:var(--amber);margin:0 0 14px;}}
h1{{font-family:'Oswald',sans-serif;font-weight:700;font-size:clamp(36px,6vw,64px);margin:0 0 8px;text-transform:uppercase;line-height:.98;}}
.sub{{color:var(--text-muted);font-size:15px;max-width:600px;margin:0 0 32px;}}
.stat-strip{{display:grid;grid-template-columns:repeat(5,1fr);border:1px solid var(--hairline);border-radius:4px;overflow:hidden;}}
.stat-strip div{{padding:14px 16px;border-right:1px solid var(--hairline);}} .stat-strip div:last-child{{border-right:none;}}
.stat-strip .num{{display:block;font-family:'Oswald',sans-serif;font-size:24px;font-weight:600;}}
.stat-strip .lbl{{display:block;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--text-muted);margin-top:4px;}}
.section{{padding:48px 0 0;}} .section-head{{display:flex;align-items:baseline;gap:12px;margin-bottom:20px;border-bottom:1px solid var(--hairline);padding-bottom:10px;}}
.section-head h2{{font-family:'Oswald',sans-serif;text-transform:uppercase;font-size:20px;letter-spacing:.03em;margin:0;color:var(--amber);}}
.section-head .count{{font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--text-muted);}}
.picks-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;}}
.pick-card{{background:var(--bg-panel);border:1px solid var(--hairline);border-left:3px solid var(--text-muted);border-radius:4px;padding:18px 20px;}}
.pick-card.tier-elite{{border-left-color:var(--amber);}} .pick-card.tier-strong{{border-left-color:var(--green);}}
.pick-card.tier-moderate{{border-left-color:var(--amber);}} .pick-card.tier-low{{border-left-color:var(--text-muted);}}
.pick-head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;}}
.pick-tier{{font-size:11px;letter-spacing:.05em;color:var(--text-muted);text-transform:uppercase;}}
.pick-score{{font-family:'JetBrains Mono',monospace;font-size:16px;}} .pick-score .unit{{color:var(--text-muted);font-size:11px;}}
.pick-team{{font-family:'Oswald',sans-serif;font-size:22px;margin:0 0 2px;text-transform:uppercase;}}
.side-tag{{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--bg-deep);background:var(--amber);padding:2px 6px;border-radius:2px;vertical-align:middle;}}
.pick-sub{{color:var(--text-muted);font-size:13px;margin:0 0 14px;}}
.pick-stats{{display:flex;align-items:center;gap:10px;}} .pick-stats>div:not(.arrow):not(.edge-pill){{text-align:center;}}
.pick-stats .num{{display:block;font-family:'JetBrains Mono',monospace;font-size:20px;}} .pick-stats .num.accent{{color:var(--amber);}}
.pick-stats .lbl{{font-size:10px;color:var(--text-muted);text-transform:uppercase;}} .pick-stats .arrow{{color:var(--text-muted);}}
.edge-pill{{margin-left:auto;font-family:'JetBrains Mono',monospace;font-size:13px;background:rgba(95,203,140,0.12);color:var(--green);padding:4px 10px;border-radius:999px;}}
table{{width:100%;border-collapse:collapse;font-size:13px;}}
thead th{{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--text-muted);border-bottom:1px solid var(--hairline);padding:8px 10px;}}
tbody td{{padding:9px 10px;border-bottom:1px solid var(--hairline);}} tbody tr:hover{{background:var(--bg-panel);}}
.rank{{color:var(--text-muted);}} .matchup .at{{opacity:.5;margin:0 2px;}} td.pos{{color:var(--green);}} td.neg{{color:var(--rose);}}
.action{{color:var(--text-muted);font-size:12px;}}
.ladder-row{{display:grid;grid-template-columns:32px 1fr 200px 56px;align-items:center;gap:12px;padding:6px 0;border-bottom:1px solid var(--hairline);}}
.ladder-rank{{font-family:'JetBrains Mono',monospace;color:var(--text-muted);font-size:12px;}} .ladder-name{{font-size:13px;}}
.ladder-bar-track{{height:5px;background:var(--bg-panel-2);border-radius:3px;overflow:hidden;}}
.ladder-bar{{height:100%;background:linear-gradient(90deg,var(--amber),var(--green));}}
.ladder-score{{font-size:12px;text-align:right;}}
footer{{margin-top:64px;padding-top:24px;border-top:1px solid var(--hairline);color:var(--text-muted);font-size:12px;}}
footer p{{margin:0 0 10px;}} footer strong{{color:var(--text-primary);}}
@media (max-width:640px){{ .stat-strip{{grid-template-columns:repeat(2,1fr);}} table{{font-size:11px;}} .ladder-row{{grid-template-columns:24px 1fr 90px 44px;}} }}
</style>
</head>
<body>
<div class="hero"><div class="hero-inner">
  <p class="eyebrow">2026 NFL Season &middot; {season_label} Week {week} &middot; Model vs Market</p>
  <h1>The Value Board</h1>
  <p class="sub">Elo-based model vs. current DraftKings prices. Updates automatically every day. Season record: {record_line}.</p>
  <div class="stat-strip">
    <div><span class="num">{n_games}</span><span class="lbl">Games this week</span></div>
    <div><span class="num">{n_value}</span><span class="lbl">Value calls</span></div>
    <div><span class="num">{avg_edge:.1f}pp</span><span class="lbl">Avg |edge|</span></div>
    <div><span class="num">{record_line}</span><span class="lbl">Season record</span></div>
    <div><span class="num" style="font-size:14px;">{now}</span><span class="lbl">Last updated</span></div>
  </div>
</div></div>
<div class="wrap">
  <div class="section"><div class="section-head"><h2>Top Picks</h2><span class="count">{n_value} value calls this week</span></div>
    <div class="picks-grid">{''.join(pick_cards) if pick_cards else '<p style="color:var(--text-muted);">No value calls clear the bar this week &mdash; every game is either efficiently priced or below the confidence threshold.</p>'}</div>
  </div>
  <div class="section"><div class="section-head"><h2>Full Slate</h2><span class="count">all {n_games} games this week</span></div>
    <table><thead><tr><th>#</th><th>Matchup</th><th>Side</th><th>Market %</th><th>Model %</th><th>Edge</th><th>EV</th><th>Score</th><th>Action</th></tr></thead>
    <tbody>{''.join(rows)}</tbody></table>
  </div>
  <div class="section"><div class="section-head"><h2>Elo Power Ladder</h2><span class="count">updates after every completed game</span></div>
    <div class="ladder">{''.join(ladder_rows)}</div>
  </div>
  <footer>
    <p><strong>Model:</strong> 538-style Elo rating per team (home field +48 Elo, standard margin-of-victory
    multiplier, K=20) &rarr; expected margin &rarr; 10,000-trial Monte Carlo (SD 13.5 pts) &rarr; win probability,
    compared against DraftKings' current moneyline via The Odds API.</p>
    <p><strong>How it updates:</strong> a scheduled job pulls newly-completed games from ESPN's public scoreboard
    every day, updates every team's Elo rating based on the result, pulls fresh odds, and rebuilds this page.
    Nothing here is edited by hand after the initial Week 1 seed.</p>
    <p>Not financial advice. Not backtested beyond what "Season record" above shows. Treat every number as a
    starting hypothesis, not a guarantee.</p>
  </footer>
</div>
</body></html>"""

    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(os.path.join(DOCS_DIR, "index.html"), "w") as f:
        f.write(html)
