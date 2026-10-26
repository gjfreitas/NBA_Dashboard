# NBA Live Dashboard — Research & Build Plan

Goal: a website with **live play-by-play, game preview, box score, player info** (the web version of [nba-go](https://github.com/homerchen19/nba-go)).

Evidence labels: **[verified]** = seen in a source this session; **[unverified]** = my own knowledge or a single secondhand source. Re-check every endpoint with a live request before relying on it.

---

## 1. What the reference repos teach

| Repo | Takeaway |
|---|---|
| [homerchen19/nba-go](https://github.com/homerchen19/nba-go) (MIT, ~3.7k stars, appears unmaintained since ~Jan 2023) | **Feature model to copy**: UI switches by game status — *pregame* (team comparison: avg points, FG%, assists), *live* (scoreboard + scrolling play-by-play + box score), *final* (scoreboard + box score). Player view: info, regular season, playoffs, multi-player compare. **Avoid**: stats.nba.com-only data, no documented polling/retry, stale tooling. |
| [swar/nba_api](https://github.com/swar/nba_api) (MIT) | Best-documented client. Two families: `nba_api.live.nba.endpoints` (ScoreBoard, BoxScore, PlayByPlay, Odds) and `nba_api.stats.endpoints` (hundreds). Use it as an **endpoint/field reference** even if we write our own fetcher. Release notes: PlayByPlayV2 returns empty JSON → use **V3**; ScoreboardV2 deprecated → V3. |
| [bttmly/nba](https://github.com/bttmly/nba) (Node, MIT) | Documents the hard problems: NBA **blacklists cloud IP ranges** (requests hang), requires specific headers, and **blocks browser CORS** → you need a server relay. |
| [agv117/nba "Court Vision"](https://github.com/agv117/nba) | Pattern: bake stats data offline with nba_api (because of cloud blocking), ship a static front-end. Canvas half-court drawing. |
| [d3-shotchart](https://www.npmjs.com/package/d3-shotchart) | Old (v0.0.2); better to write our own SVG court + hexbin. |

Gap found: **no open-source Next.js project does live NBA games well** — so this is a genuine opportunity, but also means no template to lean on.

## 2. Data sources

### Free / unofficial (NBA.com's own JSON)
- **Live CDN (`cdn.nba.com/static/json/liveData/...`)** — unprotected, reportedly works from anywhere incl. cloud [secondhand: dev report].
  - Boxscore: `.../liveData/boxscore/boxscore_{gameId}.json` — gameId is 10 digits [verified, nba_api docs].
  - Play-by-play: `.../liveData/playbyplay/playbyplay_{gameId}.json` → `game.actions[]` [path verified in nba_api source; full base URL unverified].
  - Today's scoreboard: `.../liveData/scoreboard/todaysScoreboard_00.json` [relative path seen in a Ruby wrapper; unverified].
  - Schedule: `https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json` (~8 MB, `leagueSchedule.gameDates[].games[]`) [GitHub issue, secondhand].
  - Fields: `gameStatus` (1 pre / 2 live / 3 final), `period`, `gameClock` (ISO duration `PT11M58.00S`), PBP actions: `actionNumber`, `clock`, `period`, `teamTricode`, `personId`, `actionType`, `subType`, `description`, `x`, `y`, `scoreHome`, `scoreAway` (strings), `isFieldGoal` [verified]. Parse ISO durations; scores arrive as strings.
- **stats.nba.com** — for player profiles, career stats, shot charts, standings, team comparison. **Problems**: Akamai bot protection (header/TLS-fingerprint sensitive), cloud IPs dropped/hang, throttling (nba_api suggests ≥1 s between calls, long timeouts, proxy support) [verified from README + dev reports]. Treat as **batch-ingested, not called per page view**.

### Paid / licensed
| Vendor | Notes |
|---|---|
| [SportsDataIO](https://sportsdata.io/developers/api-documentation/nba) | Free tier is 1-day delayed, not licensed for commercial redistribution; real-time requires commercial agreement (pricing by quote). |
| [BALLDONTLIE](https://highlightly.net/blogs/best-nba-apis-in-2026) | Self-serve; play-by-play + box scores need the ~$39.99/mo tier (per a competitor's blog — verify); PBP history only from the 2025 season; commercial terms unconfirmed. |
| Sportradar | Lowest latency (push feeds), enterprise pricing, sales-only. |

### Legal reality
The unofficial endpoints are fine for **learning / personal projects**, but I found no NBA statement permitting commercial use, and [NBA.com Terms of Use](https://www.nba.com/terms) protect its content/marks. If this becomes public or monetized, plan to **swap to a licensed feed** — so the architecture must make the data source replaceable. Not legal advice.

## 3. Recommended architecture

```
 Browser (Next.js app, React)
    │  SSE / short polling of OUR API only (never nba.com — CORS + blocking)
 ┌──▼─────────────────────────────┐
 │ API / BFF  (Node or Python)     │  normalizes → our own schema (Game, Play, BoxScore, Player)
 │  - in-memory/Redis cache        │  adapter interface: NbaCdnAdapter | LicensedFeedAdapter
 │  - one poller per live game     │  → N viewers = 1 upstream request
 └──┬───────────────┬─────────────┘
    │ live (2–5 s)  │ batch (nightly / on demand, ≥1 s throttle)
 cdn.nba.com     stats.nba.com via nba_api  →  SQLite/Postgres (players, teams, season stats)
```

Key design decisions:
1. **Server-side polling with fan-out.** One poller per live game, cache JSON, push to clients via SSE. Poll only games with `gameStatus == 2`; back off when idle. Diff PBP by `actionNumber` and send only new actions.
2. **Own normalized schema** — the NBA field quirks (string scores, ISO clocks, deprecated endpoints) stay inside the adapter.
3. **Static/ISR for slow data** (player bios, career stats, schedule); **live for the three live panels.**
4. **Resilience**: stale-while-error caching, fail-fast timeouts (the cloud-block symptom is *hanging*), a "data delayed" banner when the feed stalls, and fixture-replay mode for development when no game is on.
5. **Hosting caveat**: if stats.nba.com is needed from production, it must run from a non-cloud IP or proxy, or be pre-ingested locally. Live CDN is the safer path.

Suggested stack: **Next.js (App Router) + TypeScript + Tailwind**, TanStack Query for client state, SSE route handlers, SQLite→Postgres, `nba_api` ingestion scripts in Python, Recharts/visx or hand-rolled SVG for charts.

## 4. Feature → data mapping

| Feature | Source | Contents |
|---|---|---|
| **Scoreboard / schedule** | live scoreboard + schedule JSON | Day strip, game cards with status/clock/score |
| **Game preview** (pre-game) | schedule + stats ingestion | Team comparison (PPG, FG%, AST, form), season series, injuries/leaders if sourced, odds (if licensed) |
| **Live play-by-play** | live PBP | Auto-scrolling feed, filters (scoring only / player / team), quarter jump, score + clock per row |
| **Box score** | live boxscore | Team + player tables, sortable, starters/bench, advanced (TS%, +/−), four-factors |
| **Player info** | stats ingestion | Bio, season/career/playoffs, game log, shot chart, compare (nba-go's `-c`) |

## 5. UI/UX research

**Caveat**: the UI/UX Pro Max skill's search script was not present in the installed skill package (only `SKILL.md`), so its design-system generator didn't run. The below combines its published priority rules (accessibility → touch → performance → style → layout → type/colour → motion → charts) with web research (thin: only consumer reviews of FotMob/Sofascore/theScore/Apple Sports, no formal teardowns) and my own knowledge of NBA.com / ESPN / Sofascore / FotMob patterns **[unverified against live sites]**. Worth doing a hands-on screenshot teardown before locking the design.

**Patterns observed across the best sports products**
- **Scores "river" as the home**: dense list of game cards grouped by status, live games first, with a date strip. Primary result must stay dominant (a Macworld review faults a scoring app for burying the line score).
- **Game page = tabs on a sticky score header**: *Summary / Play-by-play / Box score / Preview-Stats*. The header (logos, score, period, clock) stays visible while scrolling — users use apps *during* broadcasts for background detail like foul counts ([Six Colors](https://sixcolors.com/link/2024/04/the-poor-design-of-apple-sports/)), and basketball box scores are a known weak spot of mobile apps.
- **Momentum / flow visual**: FotMob's momentum graph is a signature feature. Basketball analog: **score-differential (lead tracker) line chart across 4 quarters**, with scoring runs highlighted.
- **Live Activities / lock-screen** are now standard on iOS apps; a web equivalent is a tab-title ticker + optional notifications.

**Design principles for this product**
1. **Data-dense, not decorative** — dark-first theme (also light), team colours used *sparingly* as accents; tabular numerals (`font-variant-numeric: tabular-nums`) so live numbers don't jitter.
2. **Live feels live without distraction** — new PBP row slides in once (150–250 ms), score changes flash briefly, `prefers-reduced-motion` respected; "pause auto-scroll / jump to latest" control when the user scrolls up.
3. **Never colour alone** — pair green/red with ▲/▼ or text; ≥4.5:1 contrast; visible focus rings; keyboard navigation for tabs and tables; `aria-live="polite"` on score changes (throttled).
4. **Mobile-first**: 44 px touch targets, bottom nav (≤5 items), sticky score header, **box score with sticky first column + horizontal scroll inside the table only**, no page-level horizontal scroll.
5. **Performance**: reserve space to avoid layout shift (CLS < 0.1), virtualize long PBP lists, SSR the first paint, lazy-load charts and logos (SVG/WebP).
6. **Honest states**: skeletons, "Last updated 3 s ago", delayed-feed banner, empty states for off-days ("Next games Thursday").
7. **Deep links**: `/games/{id}/play-by-play`, `/players/{id}` — shareable, back button works.
8. **Charts**: lead tracker, shot chart (half-court SVG, made/missed + hex zones), player-vs-player bars; always with legend + tooltip + text alternative.

**Typography/colour starting point** (to refine): Inter or a similar neutral sans for UI + a condensed display face for scores; neutral slate surfaces, one accent, semantic tokens (no raw hex in components).

## 6. Proposed phases

1. **Spike (½ day)** — hit the live CDN from your machine and from the planned host; save fixtures; confirm URLs, headers, CORS and latency.
2. **MVP** — scoreboard + game page with live PBP and box score (SSE, single poller, cache).
3. **Preview + players** — nightly ingestion via nba_api → DB; preview comparison; player pages with game log.
4. **Polish** — shot charts, lead tracker, filters, a11y audit, responsive pass, replay mode, tests.
5. **Decision gate** — if going public/commercial: licensed-feed adapter + legal review.

## 7. Decisions (answered)
1. **Public now, possibly monetized later** → build behind a data-source adapter from day one; show NBA attribution/disclaimer; plan a licensed-feed swap (Sportradar/SportsDataIO) *before* any monetization (ads, paywall, subscriptions). Unofficial endpoints are a risk for any public site, so cache aggressively to minimize upstream load.
2. **Hosting: Vercel / Cloudflare** → these are cloud IPs, so **stats.nba.com will be blocked or hang from production**. Consequences:
   - Anything from stats.nba.com is **pre-ingested** by a Python job running from a non-cloud IP (your own machine/home server, or a residential/proxy egress — GitHub Actions runners are Azure and likely blocked too; verify), then written to a hosted DB.
   - Live data comes from cdn.nba.com, which reportedly works from cloud. Fetch it at the edge with short cache TTL (2–5 s, stale-while-revalidate) so thousands of viewers collapse to ~1 upstream request per game. **No long-lived poller needed on serverless.** Verify from an actual Vercel/Cloudflare region in the spike.
3. **Python-centred data layer** (more sources: `nba_api`, plus pandas-friendly tooling, e.g. basketball-reference scrapers, ESPN endpoints, later licensed feeds).
   - **Python = ingestion + data API** (FastAPI), not the browser UI.
   - Serverless caveat: Vercel Python functions are stateless and short-lived; Cloudflare Workers' Python support is limited. So the always-on/batch Python lives on a small non-cloud host or scheduled local job, while Vercel/Cloudflare serves the web UI and cached live-JSON proxy.
   - Frontend remains a JS framework (Next.js/TypeScript) — Python can't sensibly render the interactive live UI on Vercel/Cloudflare.
4. **Player scope: everything** → bio, season/career/playoffs splits, game logs, shot chart (zones + hexbin), advanced stats, comparison tool, awards/draft info. This makes player ingestion the largest data job (≈ 5k+ players historically; ingest active players first, then backfill).

### Resulting architecture
```
 Vercel/Cloudflare:  Next.js UI  +  edge route /api/live/* → cdn.nba.com (cached 2–5 s)
                          │ reads
                      Hosted DB (Neon/Supabase Postgres or Turso/D1)  ◄── Python ingestion (nba_api + other sources)
                                                                          runs from NON-cloud IP, scheduled nightly + pre/post game
```

### Revised phases
1. **Spike**: test cdn.nba.com from a Vercel/Cloudflare function; test nba_api from your machine; save fixtures.
2. **Live MVP**: scoreboard + game page (PBP, box score) via edge-cached proxy.
3. **Python ingestion**: teams, players, schedule, season stats → DB.
4. **Preview + player pages**, then shot charts, advanced stats, comparison.
5. **Pre-launch**: attribution/disclaimer, rate-limit protection, a11y audit; licensing decision before monetizing.

### Still open
- Which hosted DB (Neon Postgres vs Turso/D1)? Default: Neon Postgres if Vercel, D1 if Cloudflare.
- Vercel or Cloudflare as the primary host?
- Where will the non-cloud Python ingestion run (your PC, a home server/Raspberry Pi, a residential VPS)?

## Sources
[nba-go](https://github.com/homerchen19/nba-go) · [swar/nba_api](https://github.com/swar/nba_api) · [nba_api live boxscore docs](https://github.com/swar/nba_api/blob/master/docs/nba_api/live/endpoints/boxscore.md) · [nba_api playbyplay.py](https://github.com/swar/nba_api/blob/master/src/nba_api/live/nba/endpoints/playbyplay.py) · [nba_api releases](https://github.com/swar/nba_api/releases) · [bttmly/nba](https://github.com/bttmly/nba) · [agv117/nba](https://github.com/agv117/nba) · [d3-shotchart](https://www.npmjs.com/package/d3-shotchart) · [Best NBA APIs 2026](https://highlightly.net/blogs/best-nba-apis-in-2026) · [SportsDataIO NBA](https://sportsdata.io/developers/api-documentation/nba) · [Sportradar review](https://sportsapis.dev/apis/sportradar) · [NBA.com Terms](https://www.nba.com/terms) · [Six Colors on Apple Sports](https://sixcolors.com/link/2024/04/the-poor-design-of-apple-sports/) · [FotMob vs Sofascore](https://ontourfootball.com/news/fotmob-vs-sofascore-which-is-better-in-2026)

---

## 8. Spike results (2026-10-22, run from this machine; egress IP = Deutsche Telekom, DE)

Script: `spike/spike.py`. Fixtures in `fixtures/`.

| Probe | Result |
|---|---|
| cdn.nba.com via `curl` / Python `requests` (even with browser UA, Referer, Origin) | **403 Access Denied (Akamai)** |
| cdn.nba.com via `curl_cffi` with `impersonate="chrome"` | **200** (scoreboard 6.5 KB, schedule 7.4 MB, boxscore ~33 KB, play-by-play ~420 KB) |
| `nba_api` 1.11.4 `live.ScoreBoard()` | **Fails** (JSONDecodeError — the 403 HTML page) |
| `nba_api` stats: static teams (30) / players (5,103), `CommonPlayerInfo`, `PlayerCareerStats` | **OK** (0.3–1.6 s) |
| box score / PBP for a not-yet-started game | 403 (file doesn't exist yet) — treat as "not available", not an error |
| box score / PBP for completed games `0022600001`, `0022600002` | 200 |

### Findings
1. **The live CDN is TLS-fingerprint-protected, contrary to the earlier "unprotected" report.** Plain HTTP clients get 403 regardless of headers; a browser-impersonating TLS client (curl_cffi) passes. This is a *client-fingerprint* block, not an IP block, from this network. (Not tested: whether it differs from a Vercel/Cloudflare IP.)
2. **`nba_api`'s live module is broken here for the same reason.** Use our own fetcher with `curl_cffi` for live data; `nba_api` stats endpoints still work from this IP.
3. **Consequence for hosting:** Vercel/Cloudflare `fetch()` has a non-browser TLS fingerprint and will very likely get 403 from cdn.nba.com. So the "edge proxy to the CDN" plan **doesn't hold as written.** Revised plan: a small always-on **Python relay** (FastAPI + `curl_cffi`) on a non-cloud host polls live games every 2–5 s and publishes to a cache/KV store (or serves SSE) that Vercel/Cloudflare reads. This is a stronger reason for the Python backend you chose. Must be tested from the intended host's IP before committing.
4. **Payload size**: full PBP is ~420 KB per fetch (600+ actions). The relay must diff by `actionNumber` and send only new actions to browsers.
5. **Data verified (fixtures):**
   - Scoreboard game: `gameId, gameStatus (1/2/3), gameStatusText, period, gameClock, gameTimeUTC, homeTeam, awayTeam, gameLeaders, pbOdds, seriesText…`
   - Box score: arena, attendance, officials; per player `starter, position, jerseyNum, oncourt, statistics{points, reboundsTotal, assists, steals, blocks, fieldGoals*, threePointers*, freeThrows*, plus/minus, pointsInThePaint, pointsFastBreak, pointsSecondChance, …}`.
   - PBP action: `actionNumber, clock (ISO), timeActual (UTC timestamp), period, periodType, teamId, actionType, subType, description, qualifiers, x, y (and xLegacy/yLegacy), possession, scoreHome/scoreAway (strings), orderNumber, isFieldGoal, edited`. `edited` means past actions can be revised — diff on `actionNumber` **and** re-sync periodically.
   - `x/y` on shots enable shot charts directly from live PBP.
6. Season is live: today is 2026-10-22, two games scheduled (CLE@PHI, DEN@OKC); the spike shows only pregame state — **live in-game behaviour (polling cadence, `edited` actions) remains untested** until a game is in progress.

### Next steps
- Build `data/` Python package: `curl_cffi` client, normalizers, fixture-replay mode.
- Re-run the CDN probe from a Cloudflare Worker and a Vercel function to confirm 403, and from the intended relay host.
- Watch tonight's games (7 pm ET) to record a live PBP sequence as a replay fixture.


---

## 9. Injury report and lineup sources (researched 2026-10-23, endpoints tested from this machine)

| Source | What it gives | Tested result | Caveats |
|---|---|---|---|
| **NBA official injury report** (PDF, `ak-static.cms.nba.com/referee/injury/Injury-Report_YYYY-MM-DD_HH_MMAM.pdf`; index page `official.nba.com/nba-injury-report-2026-27-season/`) | The league-mandated report: every team's players with Out / Doubtful / Questionable / Probable / Available, reason, per game | 33 reports listed for the day, one every 15 min (12:00 AM … 8:00 AM ET at test time); newest has 85 rows (51 Out, 20 Questionable, 7 Probable, 4 Available, 3 Doubtful); 16 team blocks still "NOT YET SUBMITTED". Works with a plain HTTP client (no browser TLS fingerprint). | PDF only, names only ("Last,First", no NBA ids). Rows wrap over several lines; game date, time, matchup and team are filled in only on the first row of a block. Text extraction drops spaces ("Injury/Illness-LeftHamstringStrain"). Teams file late on game days. |
| **NBA daily lineups** (`stats.nba.com/js/data/leaders/00_daily_lineups_YYYYMMDD.json`, same data as nba.com/players/todays-lineups) | Starting five per team with `personId`, position, `lineupStatus` (Expected / Confirmed), `rosterStatus`, `timestamp`, plus game id and status | Works for today (12 games, 120 players, all "Expected" before tip) and yesterday (Final, all "Confirmed", 17 players per team). 28 KB. Works with a plain HTTP client. | Undocumented path, can change. When "Confirmed" appears relative to tip-off is not measured yet. Only starters pre-game; no bench or injury flags. |
| **ESPN injuries** (`site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries`) | Per-team injury list with status (Out / Day-To-Day), injury type, location, side, **return date**, short and long comment | 200, JSON, 875 KB, 25 teams, 78 entries, timestamped. Plain client OK. | Unofficial and undocumented; ESPN's terms for commercial reuse not checked. No NBA player id (match by name + team). Mostly long-term injuries; "Day-To-Day" is coarser than the NBA's five statuses. |
| `nba-injury-report` (PyPI, github.com/mkeenan195/nba-injury-report) | Wrapper that fetches the same official PDF and parses it with pymupdf | Not run. Fetches only the one `..._HHAM.pdf` slot (the hour minus 30 min), no fallback. | **AGPL-3.0**, version 0.1.0, one maintainer, last commit Jan 2026, 0 stars. AGPL would oblige us to publish our source if the site is public and we modify it. Better to write our own parser. |
| RotoWire injury table (`rotowire.com/basketball/tables/injury-report.php`) | Injuries with expected return | Responded, but only 5 rows | Commercial site with a bot policy; no license; not recommended. |
| Paid feeds: SportsDataIO, Sportradar, BALLDONTLIE | Injuries and (some) lineups with support | Not tested. A third-party comparison put BALLDONTLIE injuries at its ~$9.99/month tier; the others are sales-quoted. | The route if the site is ever monetized (see section 2, licensing). |

**Recommendation**
- **Lineups:** the NBA daily lineups JSON. It has `personId`, so it joins to our players directly.
- **Injuries:** the official NBA PDF as the source of truth for game-day status, parsed by our own code (not the AGPL package). Optionally add ESPN for return dates and comments on long-term injuries.
- **Matching:** the PDF and ESPN have names only. Normalize (accents, Jr./II/III suffixes) and match on team + last name + first initial; log every unmatched name.
- **Refresh:** poll the report index every 15 minutes on game days and the lineups file from a few hours before tip-off; reuse the existing scheduled refresh.
- **ESPN, as built (2026-10-23):** used as a labeled secondary source, hourly. On the day it was added, all 78 ESPN rows matched a player and team by name (0 unmatched); 14 players were not on the official report (long-term injuries, plus teams that hadn't filed yet) and 64 official entries gained an ESPN return date. ESPN's `comment` text is deliberately not stored (editorial copy, the least defensible thing to republish). **Still unverified:** ESPN's terms for reuse. Fine for a personal project; check before making the site public or monetized, and swap in a licensed feed (section 2) if needed.
- **Untested:** none of these hosts has been tried from a Vercel / Cloudflare IP. stats.nba.com's API blocks cloud IPs, and this static path may or may not.


---

## 10. Player prop lines and odds: free and reliable sources (researched 2026-10-23)

**Bottom line.** No free source gives *reliable, complete, redistributable* NBA player-prop lines. The free tiers that exist are small or delayed, and the DFS apps (PrizePicks, Underdog) have no public API. The realistic route is a licensed aggregator on a free or cheap tier, behind our swappable-source interface, with lines still user-editable as today.

| Source | Free tier | NBA props on free? | Cheapest with props | Display / redistribution terms | Verdict |
|---|---|---|---|---|---|
| **The Odds API** (the-odds-api.com) | 500 credits/month, no stated per-minute limit | **Not stated** on the pages; "All betting markets" is on the free card. Test with one call. | Free card claims all markets; paid $30 (20k credits), $59, $119, $249 | **Most permissive found**: website/UI display and commercial use allowed; only reselling the raw feed is barred; attribution not required. | **Best first try.** Props use the per-event endpoint: cost = markets returned x regions (about 1 credit per event per prop market). 500 credits is roughly one slate of 8 games x 5 markets once a day, so it is for testing, not live polling. |
| **SportsGameOdds** | 2,500 objects/month, 10 req/min, 10-minute updates, 9 books (DraftKings, FanDuel, BetMGM, Caesars, ESPN BET, Bovada, Unibet, PointsBet, William Hill) | **Yes, stated** ("every plan, including the free tier"): points, rebounds, assists, PRA, threes, steals, blocks, turnovers, double/triple-double, quarter variants | Free; Rookie $99 (3-min updates), Pro $299 (PrizePicks) | No resale or data feed; may show data to end users inside an app with independent value; free-vs-paid display not separated. Card "may be required". | **Best documented free NBA props.** 2,500 objects is small (an event with props can be many objects), so cache hard. |
| **OddsPapi** | 250 requests/month (resets on the 1st) | Not stated | Paid prices not published | No standalone resale; display not addressed. Lists DraftKings, FanDuel, PrizePicks | Too small and opaque to rely on. |
| **TheRundown** | 20k data points/day, 5-minute delay, DraftKings/FanDuel/BetMGM | **No** ("No player props or alt markets") | Starter $49 (internal or personal use only); Pro $149 adds commercial display with attribution | Clear and explicit | Reliable but props cost money. |
| **SharpAPI** | 12 req/min, 2 books, 60-second delay, no card | Not stated | Hobby $79 | Display allowed in your own app with an active paid subscription | Unclear for props. |
| **BALLDONTLIE** | $0: 5 req/min, 1 sport, "Basic" endpoints | Probably not (third-party sources put odds on the GOAT tier, $39.99/month; prices conflict) | Unconfirmed, $9.99 to $39.99 per sport | Most permissive text, but it does not clear sportsbook rights | Check the NBA tier on its subscription page. |
| OpticOdds | None stated | n/a | Sales only | Terms bar "any revenue-generating endeavor" | Not for us. |
| SportsDataIO | Free-trial sign-up, limits unstated | Props listed in coverage | Sales/quote | No copying or republishing without consent | Trial only. |
| Sportradar | None found | n/a | Enterprise | Not read | Not for us. |

**Sportsbook and DFS sources directly**
- **DraftKings / FanDuel:** terms prohibit automated scraping; DraftKings has sent cease-and-desist letters to data sites. Their site endpoints change without notice and can block by IP. Not recommended.
- **PrizePicks / Underdog:** no public API. Underdog's terms explicitly bar scraping; paid third-party scrapers exist (Apify and others) but sit on top of the same terms problem. PrizePicks lines are on SportsGameOdds Pro ($299) and OddsPapi. Underdog lines were not found in any licensed feed we read.
- **Sportsbook lines are not the same as DFS lines:** DFS apps set their own numbers, often one stat line with no over/under price, so they differ from books.

**Reliability caveats that apply to every source**
- Props are posted late (often the morning of the game) and move; the free tiers refresh every 1 to 10 minutes at best, or are delayed.
- Different books offer different players and lines; there is no single "the line". Consensus or best-line logic is needed.
- None of these vendors publishes an uptime guarantee for free plans; most can revoke keys.
- Gambling-content rules vary by jurisdiction; The Odds API only *encourages* responsible-gambling messaging, but a public site should show it.

**Recommendation**
1. Create a free key at SportsGameOdds and one at The Odds API. One test call each answers the open questions (does the free plan return NBA `player_points`; how many credits or objects one slate costs).
2. Build an `OddsSource` interface (like the existing Source protocol) with a daily snapshot job for the prop markets we already chart (points, rebounds, assists, threes, PRA), storing opening and latest line per book in SQLite, so the website never calls the vendor per page view.
3. Show lines as optional defaults for the Stats tab's line selector, labelled with book and time, with the current user-set line staying the fallback.
4. Revisit paid plans ($30 The Odds API, or TheRundown Pro at $149 for display rights) only if the site goes public or monetized; confirm display rights in writing first.
5. Unverified: nothing here was tested with a live key, so free-tier prop access, credit cost and latency are claims from the vendors' own pages.
