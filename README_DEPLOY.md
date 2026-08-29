# NFL Value Board — daily live site

This turns into a real website that updates itself every day, for free.
No server to run or pay for — GitHub does the daily work, GitHub Pages
hosts the result.

## What you get

- A daily cron job (GitHub Actions, free) that:
  1. Pulls completed games from ESPN's public scoreboard and updates every
     team's Elo rating based on the result.
  2. Pulls current NFL odds from The Odds API.
  3. Runs the model and rewrites `docs/index.html`.
  4. Commits the change back to the repo.
- GitHub Pages serves `docs/index.html` as a live website, free, at
  `https://<your-username>.github.io/<repo-name>/`.

## One-time setup (about 10 minutes)

1. **Get a free Odds API key.**
   Go to https://the-odds-api.com, sign up (free tier: 500 requests/month
   — this project uses ~30/month at one pull a day), copy your API key.

2. **Create a GitHub repository** and push this whole folder to it
   (`git init && git add . && git commit -m "init" && git push`), or use
   GitHub's "upload files" UI if you don't want to use git locally.

3. **Add the API key as a repo secret.**
   Repo → Settings → Secrets and variables → Actions → New repository
   secret → name it `ODDS_API_KEY`, paste the key.

4. **Enable GitHub Pages.**
   Repo → Settings → Pages → Source: "Deploy from a branch" → Branch:
   `main`, folder: `/docs` → Save. Your site goes live at
   `https://<your-username>.github.io/<repo-name>/` within a minute or two.

5. **Run it once manually** to confirm it works: repo → Actions tab →
   "Update NFL Value Board" → Run workflow. Check the Actions log for
   errors, then check the site.

That's it. From here it updates itself every day at 13:00 UTC. You can
also trigger it manually anytime from the Actions tab.

## How the model works, in one paragraph

Every team has an Elo rating, starting from a Week 1 seed (derived from
Kalshi's neutral-field power ratings). After every completed game, Elo
updates automatically based on who won, by how much, and how surprising
it was (538's public NFL Elo methodology — home field +48 Elo, K=20,
margin-of-victory multiplier). The Elo gap between two teams converts to
an expected point margin, which feeds a 10,000-trial Monte Carlo (using
the NFL's real season-to-season scoring-margin scatter, SD≈13.5) to get a
win probability. That's compared against DraftKings' current price
(via The Odds API) to find edge, expected value, and a 0–100 confidence
score — the same "VALUE / PASS" logic validated earlier in this project,
just running on a self-updating rating instead of a one-time snapshot.

## Files

- `scripts/elo.py` — the rating math
- `scripts/espn.py` — free, no-key results/schedule source
- `scripts/odds_api.py` — sportsbook prices (needs your free key)
- `scripts/model.py` — Elo diff → Monte Carlo → edge/EV/tier
- `scripts/state.py` — the whole "database" (two JSON files in `data/`)
- `scripts/site_builder.py` — writes `docs/index.html`
- `scripts/update_and_build.py` — the one script the daily job runs
- `data/elo_seed.json` — the only hand-entered file; everything after
  Week 1 comes from real results
- `fixtures/` — sample API responses used to test the parsers offline;
  not used in production

## Honest limitations

- **Odds API free tier**: 500 requests/month is enough for one pull a
  day (~30/month) with room to spare, but don't add more frequent
  schedules without checking your usage.
- **Elo is a simplification.** It only knows final scores — no injuries,
  no weather, no depth-chart detail. It's a legitimate, well-tested
  public methodology (this is close to what 538 published for years),
  but it's not the full 27-factor system from the original spec. Treat
  it as the baseline the rest of that spec would sit on top of, not the
  finished version of it.
- **Nothing here is backtested yet.** The "Season record" line will
  only mean something after real results accumulate — the `bet_log` in
  `data/elo_state.json` is what you'd feed to a proper backtest once
  there's a season's worth of data. Resolving `bet_log` entries (marking
  `resolved`/`won` once games finish) isn't wired up yet — that's the
  next thing to add if you want the record to update automatically too.
