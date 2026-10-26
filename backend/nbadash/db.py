"""SQLite storage for player data (stdlib only). Swap for Postgres later by replacing this module."""
from __future__ import annotations

import os
import sqlite3
import unicodedata
from pathlib import Path
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
  id INTEGER PRIMARY KEY,
  full_name TEXT NOT NULL, first_name TEXT, last_name TEXT, slug TEXT,
  is_active INTEGER NOT NULL DEFAULT 0,
  birthdate TEXT, country TEXT, school TEXT, height TEXT, weight TEXT,
  jersey TEXT, position TEXT, roster_status TEXT,
  team_id INTEGER, team_abbr TEXT, team_name TEXT, team_city TEXT,
  from_year INTEGER, to_year INTEGER,
  draft_year TEXT, draft_round TEXT, draft_number TEXT, greatest_75 INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS players_name ON players(full_name COLLATE NOCASE);

-- One row per player/season/type/team; season='Career' holds NBA's career totals row.
CREATE TABLE IF NOT EXISTS player_seasons (
  player_id INTEGER NOT NULL, season TEXT NOT NULL, season_type TEXT NOT NULL,
  team_id INTEGER, team_abbr TEXT NOT NULL DEFAULT '', age REAL,
  gp INTEGER, gs INTEGER, min REAL, fgm INTEGER, fga INTEGER, fg3m INTEGER, fg3a INTEGER,
  ftm INTEGER, fta INTEGER, oreb INTEGER, dreb INTEGER, reb INTEGER, ast INTEGER,
  stl INTEGER, blk INTEGER, tov INTEGER, pf INTEGER, pts INTEGER,
  PRIMARY KEY (player_id, season, season_type, team_abbr)
);

CREATE TABLE IF NOT EXISTS player_game_logs (
  player_id INTEGER NOT NULL, game_id TEXT NOT NULL, season TEXT NOT NULL, season_type TEXT NOT NULL,
  game_date TEXT, matchup TEXT, wl TEXT, min REAL,
  fgm INTEGER, fga INTEGER, fg3m INTEGER, fg3a INTEGER, ftm INTEGER, fta INTEGER,
  oreb INTEGER, dreb INTEGER, reb INTEGER, ast INTEGER, stl INTEGER, blk INTEGER,
  tov INTEGER, pf INTEGER, pts INTEGER, plus_minus INTEGER,
  team_id INTEGER, usg_pct REAL, q1_pts INTEGER, q1_reb INTEGER, q1_ast INTEGER, q2_pts INTEGER,
  PRIMARY KEY (player_id, game_id)
);
CREATE INDEX IF NOT EXISTS logs_lookup ON player_game_logs(player_id, season, season_type, game_date);

-- x/y are NBA shot-chart units: tenths of a foot, origin at the rim, +y toward half court.
CREATE TABLE IF NOT EXISTS player_shots (
  player_id INTEGER NOT NULL, game_id TEXT NOT NULL, event_id INTEGER NOT NULL,
  season TEXT NOT NULL, season_type TEXT NOT NULL, game_date TEXT,
  period INTEGER, min_rem INTEGER, sec_rem INTEGER,
  action_type TEXT, shot_type TEXT, zone_basic TEXT, zone_area TEXT, zone_range TEXT,
  distance INTEGER, x INTEGER, y INTEGER, made INTEGER NOT NULL,
  PRIMARY KEY (player_id, game_id, event_id)
);
CREATE INDEX IF NOT EXISTS shots_lookup ON player_shots(player_id, season, season_type);

-- Team preview data: per-game team stats + league ranks, every team game, and per-game player averages.
CREATE TABLE IF NOT EXISTS team_season (
  team_id INTEGER NOT NULL, season TEXT NOT NULL, name TEXT, gp INTEGER, w INTEGER, l INTEGER,
  pts REAL, reb REAL, ast REAL, stl REAL, blk REAL, tov REAL, fg_pct REAL, fg3_pct REAL, ft_pct REAL,
  plus_minus REAL, off_rtg REAL, def_rtg REAL, net_rtg REAL, pace REAL, ts_pct REAL,
  pts_rank INTEGER, reb_rank INTEGER, ast_rank INTEGER, fg_pct_rank INTEGER, fg3_pct_rank INTEGER,
  off_rtg_rank INTEGER, def_rtg_rank INTEGER, net_rtg_rank INTEGER, pace_rank INTEGER,
  PRIMARY KEY (team_id, season)
);
CREATE TABLE IF NOT EXISTS team_games (
  team_id INTEGER NOT NULL, game_id TEXT NOT NULL, season TEXT NOT NULL, abbr TEXT NOT NULL, opp_abbr TEXT NOT NULL,
  game_date TEXT NOT NULL, home INTEGER NOT NULL, wl TEXT, pts INTEGER, plus_minus INTEGER,
  PRIMARY KEY (team_id, game_id)
);
CREATE INDEX IF NOT EXISTS team_games_lookup ON team_games(team_id, game_date);
CREATE TABLE IF NOT EXISTS league_players (
  player_id INTEGER NOT NULL, season TEXT NOT NULL, team_id INTEGER, name TEXT, gp INTEGER,
  min REAL, pts REAL, reb REAL, ast REAL, PRIMARY KEY (player_id, season)
);
CREATE INDEX IF NOT EXISTS league_players_team ON league_players(team_id, season);

-- Standings, team directory and schedule.
CREATE TABLE IF NOT EXISTS teams (
  id INTEGER PRIMARY KEY, abbr TEXT, city TEXT NOT NULL, name TEXT NOT NULL, slug TEXT,
  conference TEXT, division TEXT
);
CREATE TABLE IF NOT EXISTS standings (
  team_id INTEGER NOT NULL, season TEXT NOT NULL, conf_rank INTEGER, div_rank INTEGER, league_rank INTEGER,
  w INTEGER, l INTEGER, pct REAL, gb REAL, home TEXT, road TEXT, l10 TEXT, streak TEXT,
  conf_record TEXT, div_record TEXT, ppg REAL, opp_ppg REAL, diff REAL, clinch TEXT,
  PRIMARY KEY (team_id, season)
);
CREATE TABLE IF NOT EXISTS schedule (
  game_id TEXT PRIMARY KEY, season TEXT NOT NULL, game_date TEXT NOT NULL, start_utc TEXT,
  status INTEGER NOT NULL, status_text TEXT,
  home_id INTEGER NOT NULL, away_id INTEGER NOT NULL, home_abbr TEXT, away_abbr TEXT,
  home_score INTEGER, away_score INTEGER, label TEXT, sub_label TEXT, arena TEXT
);
CREATE INDEX IF NOT EXISTS schedule_home ON schedule(home_id, game_date);
CREATE INDEX IF NOT EXISTS schedule_away ON schedule(away_id, game_date);

-- Matchup analysis (league-wide, one row per player/team per season).
CREATE TABLE IF NOT EXISTS player_zones (
  player_id INTEGER NOT NULL, season TEXT NOT NULL, zone TEXT NOT NULL, fgm INTEGER, fga INTEGER,
  PRIMARY KEY (player_id, season, zone)
);
CREATE TABLE IF NOT EXISTS team_zones_def (
  team_id INTEGER NOT NULL, season TEXT NOT NULL, zone TEXT NOT NULL, fgm INTEGER, fga INTEGER,
  PRIMARY KEY (team_id, season, zone)
);
CREATE TABLE IF NOT EXISTS player_shot_types (
  player_id INTEGER NOT NULL, season TEXT NOT NULL, shot_type TEXT NOT NULL,
  fgm INTEGER, fga INTEGER, fg3m INTEGER, fg3a INTEGER, gp INTEGER,
  PRIMARY KEY (player_id, season, shot_type)
);
CREATE TABLE IF NOT EXISTS team_shot_types_def (
  team_id INTEGER NOT NULL, season TEXT NOT NULL, shot_type TEXT NOT NULL,
  fgm INTEGER, fga INTEGER, fg3m INTEGER, fg3a INTEGER,
  PRIMARY KEY (team_id, season, shot_type)
);
CREATE TABLE IF NOT EXISTS player_play_types (
  player_id INTEGER NOT NULL, season TEXT NOT NULL, play_type TEXT NOT NULL,
  gp INTEGER, poss REAL, pts REAL, fgm INTEGER, fga INTEGER,
  PRIMARY KEY (player_id, season, play_type)
);
CREATE TABLE IF NOT EXISTS team_play_types_def (
  team_id INTEGER NOT NULL, season TEXT NOT NULL, play_type TEXT NOT NULL, poss REAL, pts REAL,
  PRIMARY KEY (team_id, season, play_type)
);

-- Availability: starting lineups (NBA daily lineups file) and the official injury report (PDF, every 15 minutes).
CREATE TABLE IF NOT EXISTS lineups (
  game_id TEXT NOT NULL, team_id INTEGER NOT NULL, player_id INTEGER NOT NULL, name TEXT, position TEXT,
  starter INTEGER NOT NULL DEFAULT 0, status TEXT, roster_status TEXT, file_timestamp TEXT, updated_at TEXT NOT NULL,
  PRIMARY KEY (game_id, team_id, player_id)
);
-- one row each time a team's status or starting five changes, stamped with when WE saw it (to measure how early lineups arrive)
CREATE TABLE IF NOT EXISTS lineup_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, game_id TEXT NOT NULL, team_id INTEGER NOT NULL, status TEXT, starters TEXT,
  file_timestamp TEXT, observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS lineup_events_game ON lineup_events(game_id, team_id, id);

CREATE TABLE IF NOT EXISTS injury_reports (
  report_id TEXT PRIMARY KEY,        -- "2026-10-23_08_00AM", from the PDF's file name
  published_at TEXT NOT NULL,        -- Eastern wall-clock time of the report, ISO without zone
  published_utc TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  entries INTEGER NOT NULL,
  pending INTEGER NOT NULL DEFAULT 0 -- teams that had not submitted yet
);
CREATE TABLE IF NOT EXISTS injuries (
  report_id TEXT NOT NULL, seq INTEGER NOT NULL, game_date TEXT, game_time TEXT, matchup TEXT, game_id TEXT,
  team_name TEXT, team_id INTEGER, team_abbr TEXT, player_name TEXT NOT NULL, player_id INTEGER,
  status TEXT NOT NULL, reason TEXT,
  PRIMARY KEY (report_id, seq)
);
CREATE INDEX IF NOT EXISTS injuries_player ON injuries(player_id, report_id);
CREATE INDEX IF NOT EXISTS injuries_team ON injuries(team_id, report_id);
CREATE TABLE IF NOT EXISTS injury_pending (
  report_id TEXT NOT NULL, game_date TEXT, matchup TEXT, team_name TEXT, team_id INTEGER,
  PRIMARY KEY (report_id, matchup, team_name)
);

-- ESPN's injury list: a secondary, unofficial source (return-date estimates, players the NBA report doesn't list). Replaced wholesale on each fetch.
CREATE TABLE IF NOT EXISTS espn_injuries (
  espn_id TEXT PRIMARY KEY, player_name TEXT NOT NULL, player_id INTEGER, team_name TEXT, team_id INTEGER, team_abbr TEXT,
  status TEXT NOT NULL,        -- ESPN's own vocabulary: Out | Day-To-Day
  injury TEXT,                 -- "Left Foot Fracture"
  return_date TEXT,            -- ISO date; ESPN's estimate
  updated_at TEXT,             -- when ESPN last changed this entry
  snapshot_at TEXT NOT NULL    -- ESPN's timestamp for the list
);
CREATE INDEX IF NOT EXISTS espn_injuries_player ON espn_injuries(player_id);
CREATE INDEX IF NOT EXISTS espn_injuries_team ON espn_injuries(team_id);

-- Player prop lines from an odds API (odds.py). Append-only: a row is added when a book's line or price changes, so the first row is the opening line.
CREATE TABLE IF NOT EXISTS prop_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, event_id TEXT NOT NULL, game_id TEXT, player_id INTEGER, player_name TEXT NOT NULL,
  market TEXT NOT NULL, book TEXT NOT NULL, line REAL NOT NULL, over_price INTEGER, under_price INTEGER, book_updated_at TEXT, seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS prop_lines_player ON prop_lines(player_id, game_id, market, id);
CREATE INDEX IF NOT EXISTS prop_lines_game ON prop_lines(game_id);
CREATE TABLE IF NOT EXISTS odds_usage (
  source TEXT NOT NULL, period TEXT NOT NULL, spent INTEGER NOT NULL DEFAULT 0, remaining INTEGER, PRIMARY KEY (source, period)
);

-- When each data source was last reached, and its last failure (see health.py).
CREATE TABLE IF NOT EXISTS source_checks (
  source TEXT PRIMARY KEY, last_ok TEXT, last_error TEXT, last_error_at TEXT
);

CREATE TABLE IF NOT EXISTS sync (
  player_id INTEGER NOT NULL, kind TEXT NOT NULL, synced_at TEXT NOT NULL,
  PRIMARY KEY (player_id, kind)
);
"""


def default_path() -> Path:
    return Path(os.getenv("NBA_DB", Path(__file__).resolve().parents[1] / "data" / "nba.db"))


# Columns added after the first release; CREATE TABLE IF NOT EXISTS won't touch an existing table.
_ADDED_COLUMNS = {
    "player_game_logs": {"team_id": "INTEGER", "usg_pct": "REAL", "q1_pts": "INTEGER", "q1_reb": "INTEGER",
                         "q1_ast": "INTEGER", "q2_pts": "INTEGER"},
}


def _migrate(conn: sqlite3.Connection) -> None:
    for table, cols in _ADDED_COLUMNS.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, typ in cols.items():
            if name not in have:
                try:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")
                except sqlite3.OperationalError:  # another process migrated first
                    pass


_EXTRA_FOLDS = str.maketrans({"ł": "l", "đ": "d", "ø": "o", "ı": "i", "æ": "ae", "œ": "oe", "ß": "ss"})


def fold_text(s: Optional[str]) -> str:
    """Lower-case without accents, so "jokic" finds "Jokić"."""
    if not s:
        return ""
    return "".join(ch for ch in unicodedata.normalize("NFKD", s.lower().translate(_EXTRA_FOLDS)) if not unicodedata.combining(ch))


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    p = Path(path) if path else default_path()
    if str(p) != ":memory:":
        p.parent.mkdir(parents=True, exist_ok=True)
    # Each request owns its connection but FastAPI may use it from different worker threads (never concurrently).
    conn = sqlite3.connect(str(p), check_same_thread=False, timeout=30)  # wait for another writer (the refresh job, a bulk import) instead of failing at once
    conn.row_factory = sqlite3.Row
    conn.create_function("fold", 1, fold_text, deterministic=True)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn
