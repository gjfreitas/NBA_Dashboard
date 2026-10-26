# NBA Live

- `backend/` — Python relay (curl_cffi client, normalizers, cache, FastAPI + SSE, fixture replay). See `backend/README.md`.
- `frontend/` — Next.js 16 app: scoreboard and game pages (Summary, Play-by-play, Box score, Preview).
- `fixtures/` — saved NBA JSON used by replay mode and tests. `spike/` — endpoint probe script.
- `RESEARCH.md` — research, decisions, spike results.

## Run (simulated live game)
```bash
cd backend && NBA_SOURCE=replay NBA_REPLAY_STEP=12 python -m uvicorn nbadash.app:app --port 8000
cd frontend && npm run dev        # http://localhost:3000, API at NEXT_PUBLIC_API_URL (.env.local)
```
Use `NBA_SOURCE=live` for the real feed. The frontend reads Next 16 docs in `frontend/node_modules/next/dist/docs/` (see `frontend/AGENTS.md`).

## Player data
Stored in SQLite (`backend/data/nba.db`, override with `NBA_DB`). Ingestion calls stats.nba.com, so run it from a non-cloud IP.
```bash
cd backend && python -m pip install -e ".[ingest]"
python -m nbadash.ingest roster                  # all ~5k players, instant
python -m nbadash.ingest player 203999 2544      # bio, career splits, last 2 seasons of game logs + shots
python -m nbadash.ingest active --limit 50       # active players that are missing or stalest; safe to re-run
python -m nbadash.ingest status
```
Pages: `/players` (search), `/players/{id}` (overview), `/players/{id}/game-log`, `/players/{id}/shot-chart`.

## Game previews
`python -m nbadash.ingest teams` loads league-wide team stats, every team game and per-game player averages (current and previous season, ~8 API calls). The Preview tab uses them for the team comparison (with league ranks), last-10 form, team leaders and recent head-to-head. Early in a season (<10 games) it shows last season's averages and says so.

## Compare players
`/compare?a=<id>&b=<id>[&season=2025-26][&mode=per36]` — side-by-side per-game or per-36 stats (with efficiency), and shot charts + zone FG% for the latest season both players have shot data. Reachable from the nav and each player's page.

## Standings and teams
`python -m nbadash.ingest teams` also loads standings (both seasons) and the league schedule. Pages: `/standings` (conference / division / league, play-in line, clinch codes), `/teams/{id}` (overview: record, ranks, form, leaders), `/teams/{id}/roster`, `/teams/{id}/schedule` (results link to the game page). Re-run it daily (or after each game night) to refresh; each piece is skipped while fresh.

## Player Stats tab (`/players/{id}/stats`)
Prop-style analysis: a market bar (points, assists, rebounds, threes, combos, double/triple double, 1Q and 1H stats, steals, blocks, turnovers, fouls, FTA; show/hide/reorder via the gear), hit rate against a line you set (no sportsbook odds are used), averages with deltas, per-game over/under bars, and filters (season, last N games, home/away, regular/playoffs, win/loss, back-to-back, minutes, opponent defence tier, head-to-head, with/without a teammate). Below it: shooting zones (player vs the opponent's defence), shot-type analysis and play-type analysis, and a **Similar players** table, against the next opponent or any team you pick. Similar players are ranked by how closely their shot zones and shot types match (or, alternatively, by position); the table shows how they did against the opponent this season, compared with each player's own season average since no sportsbook lines are used.

Data comes from one league-wide ingestion (~45 calls per season plus one for every player's position, resumable, run from a non-cloud IP):
```bash
cd backend && python -m nbadash.ingest props            # current + two previous seasons
python -m nbadash.ingest props --seasons 2025-26        # just one
```
Logic tests for markets and filters: `cd frontend && npm run test:logic`.

## Automatic refresh
`python -m nbadash.ingest refresh` brings the database up to date only when something happened: a game finished that the database doesn't have yet (checked against the NBA scoreboard), or the last refresh is over a day old. Never twice within 30 minutes. It refreshes the current season's standings, team stats, team games, schedule, and every player's game log (usage, quarters); zones, shot types, play types and player positions are refreshed once a day. A typical pass takes ~20 s; a pass with nothing new takes ~3 s.

A Windows scheduled task runs it every 15 minutes while you are logged on (no console window; output in `backend/data/refresh.log`):
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\refresh-task.ps1 install     # also: status | run | uninstall   (-Minutes 15 to change the interval)
```
Other options: `refresh --force` (now), `refresh --watch --interval 20` (a long-running loop instead of a scheduled task). Like all stats.nba.com ingestion it must run from a non-cloud IP; on a server, use `--watch` or cron.

## League leaders (`/leaders`)
Player and team leaderboards from the data already in the database, no extra ingestion.
- **Players:** 17 categories (points, rebounds, assists, steals, blocks, threes, turnovers, minutes, Pts+Reb+Ast, FG%, 3P%, FT%, eFG%, TS%, usage, double- and triple-doubles), per game or totals, regular season or playoffs, any ingested season. Clicking a column header re-ranks by it. "Qualified players only" applies the NBA's rules scaled to games played: 70% of the player's team's games, and 300 / 82 / 125 made FG / 3P / FT (per 82 games) for the percentage boards.
- **Teams:** net, offensive and defensive rating, pace, points, rebounds, assists, steals, blocks, turnovers and shooting percentages. Lowest-is-best stats (defensive rating, turnovers) rank ascending.
- API: `GET /api/leaders/players?stat=pts&season=2025-26&season_type=regular&mode=pg&qualified=true&limit=25` and `GET /api/leaders/teams?stat=net_rtg&season=2025-26`.

## Injuries and starting lineups
- **Injury report** (`/injuries`, plus a status badge on player pages, an injury card on team pages and both teams' injuries on a game's Preview tab): the NBA files a PDF every 15 minutes on game days (`official.nba.com/nba-injury-report-<season>-season/`). `backend/nbadash/injuries.py` parses it by word position (fixed-column table; wrapped reasons are centred on the player's row; date/time/matchup/team are forward-filled), matches players, teams and games, and keeps every report so changes can be tracked. Teams that haven't filed yet are listed separately, because "no players listed" does not mean healthy. Reports older than 36 hours are treated as history, not current.
- **Starting lineups** (Preview tab): the NBA's daily lineups file, `Expected` until a team confirms. `backend/nbadash/lineups.py` records every change with the moment we saw it.
- Both run on **every pass of the scheduled refresh** (now every 15 minutes), which costs 2-3 small requests. Manual runs: `python -m nbadash.injuries once|show`, `python -m nbadash.lineups once`.
- **How early is "Confirmed"?** `python -m nbadash.lineups watch --interval 60 --hours 16` logs lineup changes; afterwards `python -m nbadash.lineups analyze` prints, per game and team, how many minutes before tip-off the lineup first appeared, when it was confirmed, and whether the five changed.
- **Changes feed** ("Changes since the last report" on the Injuries page, and on a game's Preview when something changed for it): compares consecutive official reports and lists players who were added, removed, or moved between statuses (`backend/nbadash/injury_changes.py`, `GET /api/injuries/changes?hours=24&team_id=&game_id=`). A team's first filing and a new game day appearing are not counted as changes. The scheduled refresh stores every report, including ones missed while the machine slept (`python -m nbadash.injuries backfill --hours 24` loads history by hand). Overnight the NBA republishes the same report every 15 minutes, so the feed is empty until teams update during the day.
- **ESPN as a secondary source** (unofficial, always labeled "ESPN" in the UI with a dashed outline so it can't be mistaken for the NBA report). `backend/nbadash/espn_injuries.py` fetches ESPN's injury list at most once an hour (inside the same scheduled refresh) and matches players and teams by name, never guessing when a name is ambiguous. It does two things: (1) **"Also injured per ESPN"** lists players who are *not* on the official report (by player id or normalized name), on the Injuries page, team pages, a game's Preview tab and the player header; (2) official entries get an **"ESPN est. return <date>"** appended. ESPN's own wording is kept ("Day-to-day" covers anything from Probable to Doubtful) and return dates are ESPN's estimates. ESPN's editorial comments are not stored or shown. A snapshot older than 36 hours is ignored, and an empty response never wipes the stored list. Manual runs: `python -m nbadash.espn_injuries once|show`.
- API: `GET /api/injuries[?team_id=&status=]` (adds `espn` and `espn_meta`), `GET /api/games/{id}/availability` (adds `espn_only` per team), `GET /api/games/{id}/info` (a game from the schedule, so Preview opens before the game reaches the live scoreboard), and `injury` / `espn_injury` fields on `GET /api/players/{id}`.
- Source notes and licensing: `RESEARCH.md` section 9. (The AGPL `nba-injury-report` package is deliberately not used.)

## Game-day extras
- **Preview schedule context:** rest days (back-to-back flagged), games in the last 7 days, streak, last 5, and home/road record with average margin, computed from games already played before this game's date (`GET /api/preview?home=&away=&game_id=`).
- **Scoreboard cards** (games not yet started): lineup status (Expected / Confirmed) and which of each team's five top scorers are Out, Doubtful or Questionable on the official report, plus a count of other players out. One batched call: `GET /api/availability/summary?game_ids=a,b,c`. ESPN-only injuries are not shown here (only the official report is).
- **Search** (header button or Ctrl/Cmd+K): players (accent-insensitive: "jokic" finds "Jokić") and teams. **Watchlist** (`/watchlist`): follow players and teams with the ☆ button; stored in this browser only; shows their injury status and any report changes.
- **Player splits** (Stats tab): home/away, wins/losses, rest, opponent defence tier, season type and the chosen opponent, for the selected market and line, with games, average and hit rate; fewer than 5 games is flagged as noise.
- **Data status** (`/status`, `GET /api/health`): when each source was last reached, the last error, and how many player profiles are loaded. The scheduled refresh records a heartbeat every pass, so a sleeping computer or a failing source shows up instead of silently serving old data.
- **Game shot chart** (game page, "Shot chart" tab): every field goal of the game from the play-by-play, filterable by team, period, player and made/missed, with FG%, 3P and eFG%. Totals match the box score.
- **Game flow** (Summary tab): lead changes, ties, biggest lead and longest run per team. The lead tracker doubles as the win-probability chart: move the pointer over it (or use the arrow keys) to read the score and estimated win probability at any moment. The probability uses only the score and the time left (a random-walk model with a 12-point full-game spread), so it ignores team strength, possession and fouls: a rough guide, labelled as an estimate.

## Sportsbook prop lines (optional, needs an API key)
Off by default. Set a key in the environment of the scheduled task and the relay (never in a file in the repo) and the refresh pass will snapshot prop lines into SQLite; the Stats tab then shows one chip per book for the selected market (press one to set the line).
- `THE_ODDS_API_KEY` (the-odds-api.com, free plan 500 credits a month) and/or `SPORTSGAMEODDS_API_KEY` (sportsgameodds.com, free plan 2,500 objects a month). `ODDS_PROVIDER=theoddsapi|sportsgameodds` picks one when both are set.
- `ODDS_MARKETS` (default: all of `pts,reb,ast,fg3m,pa,pr,ra,pra,dd,td,q1pts,q1reb,q1ast,h1pts,stl,blk,sb,tov`; `dd`/`td` are yes/no markets, `h1pts` comes only from SportsGameOdds), `ODDS_MONTHLY_BUDGET` (per key; default 450 credits / 2,300 objects), `ODDS_MIN_HOURS` (default 12 between fetches), `ODDS_BOOKMAKERS`, `ODDS_REGIONS`. `THE_ODDS_API_KEY` may hold several keys separated by commas: when one is refused or out of credits the next is used, and the monthly budget is the per-key budget times the number of keys. On The Odds API each event costs markets x regions credits (16 markets for 9 games is about 144 credits a day), so the full list needs several keys or a longer `ODDS_MIN_HOURS`; use `ODDS_MARKETS` to pick fewer.
- Only games starting within 30 hours are fetched. Lines are stored append-only (a row when a line or price changes), so the first row is the opening line and the chip shows how far it moved.
- `python -m nbadash.odds once --force`, `show`, and `capture DIR` (saves the raw responses, without the key, so they can become test fixtures).
- A failure (refused key, used-up quota, changed response) is logged and shown on `/status`; it never stops the rest of the refresh.
- **Checked against live responses (2026-10-23):** both providers' real responses are saved in `fixtures/odds/` and parse correctly: 12 events matched to our schedule, about 2,300 lines each, books DraftKings, FanDuel, BetMGM, Bovada and more. Books often list alternate lines under the main market, so `main_lines` keeps, per book, the line nearest the consensus. When both providers are used and disagree on a line, the newest one wins. Terms: lines may be shown in the app but not resold or republished as a data feed (RESEARCH.md section 10).

## Props board, Today, alerts and deeper previews
- **Props** (`/props`, `GET /api/slate`): tonight's games as expandable cards, each listing players that have lines. A row shows the line most books agree on and the **best over and best under price** among the books at that line; press it for every book's line and prices (moves since we first stored a line are shown), plus a quick analysis loaded on demand: last 5 and 10 games, season, home/road and vs-opponent averages, and over/under for the last 10. The 18+ / responsible-gambling notice sits at the top of the board, on Today and on the live props tab.
- **Today** (`/today`, `GET /api/today`): the day's games with record, rest and back-to-back flags, lineup status and key players out; followed players and teams playing today; the biggest line moves (`GET /api/lines/moves`). "Moved" means since we first stored the line, not since the book opened it.
- **Alerts:** for followed players and teams, while the site is open in a tab, a check every 2 minutes looks for injury-report changes and line moves of a point or more, shows a badge on the Watchlist link, lists them on the Watchlist page, and sends a browser notification if you allow it. Nothing runs after the tab is closed. On the first run, existing news is marked as seen so you don't get a burst.
- **Live props** (game page, "Props" tab, `GET /api/games/{id}/props`): each player's prop against his live box-score total with a progress bar and a pace projection (his rate so far times the minutes he usually plays that are still left, capped by game time left). It ignores matchup, fouls and blowouts. Not yet watched through a real live game.
- **Who steps up** (Preview tab, `GET /api/players/{id}/without`): when a top-five scorer is Out or Doubtful, an expandable panel compares his teammates' averages in the games he played and the games his team played without him (his current team, last two seasons; fewer than 5 missed games is flagged).
- **Preview depth** (`GET /api/preview/matchup`): expected tempo, defence by opposing position (points allowed per player-game with the league rank), and a shot-zone matchup for each team (where it shoots vs how the other defence guards that zone).
- **Matchup boosts** (Today page, `GET /api/today/boosts`): for each rotation scorer playing today (8+ points a game, 15+ games, not ruled out), the expected change in scoring against that defence versus a league-average one, from three effects averaged: his **play types** weighted by his share of points against the opponent's points per possession allowed on each, his **shot types** (catch & shoot, pull-up, under 10 ft) against effective FG% allowed, and his **position** against points allowed to that position (halved: a noisier signal). Best and toughest cards name the strongest driver ("Pull-ups 59% of his shots, UTA allow the 2nd most"), and a table lists everyone with the three components. It is a pointer to soft and tough matchups, not a projection; **how much of a defence is this season's** depends on how many games that team has played: none of it at 10 games or fewer (all last season's), a straight ramp in between, all of it at 30. Numbers that stay noisy after 30 games (rare play types such as post ups, handoffs and cuts, and the shooting percentages that include threes) never go above 70% this season. A player's own profile uses this season once he has 15 games, otherwise last season's. Each card says how much of the opponent's numbers are this season's.

## Look and feel
An arena-broadcast look on a hardwood floor, defined in `frontend/app/globals.css` (tokens, textures, court lines) so components stay on semantic colours. Dark is "arena night" (warm near-black, cream type, one ball-orange accent, hardwood gold); light is "maple gym". Type: Big Shoulders (condensed arena signage) for headings and scores, Instrument Sans for reading, JetBrains Mono for small labels. Scores are drawn as score bugs with quarter pips, a score ticker runs across the top, and on a phone the navigation is a bottom bar with a More sheet. Both themes meet 4.5:1 text contrast. Team colours (`frontend/lib/teamColors.ts`) tint game cards, the game hero, standings rows and team pages. Motion: scores roll to their new value and glow when they change, a slow score crawl runs across the top (it pauses on hover or focus), a single marker slides between tabs, pages ease in, cards light up under the pointer, charts draw themselves on and shots pop onto the court, the game hero shrinks as you scroll, and loading placeholders shimmer. All of it stops under the system's reduced-motion setting. The long explanations that used to sit under panels are now small "i" notes.
