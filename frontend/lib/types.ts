export type GameState = "pre" | "live" | "final";

export interface PeriodScore { period: number; score: number }

export interface TeamSummary {
  id: number; tricode: string; city: string; name: string; score: number;
  wins: number | null; losses: number | null; periods: PeriodScore[];
}

export interface Game {
  id: string; state: GameState; status_text: string; period: number; clock: string;
  start_utc: string | null; home: TeamSummary; away: TeamSummary;
}

export interface PlayerLine {
  id: number; name: string; short_name: string; jersey: string; position: string;
  starter: boolean; on_court: boolean; played: boolean; minutes: string;
  points: number; rebounds: number; assists: number; steals: number; blocks: number;
  turnovers: number; fouls: number; fgm: number; fga: number; tpm: number; tpa: number;
  ftm: number; fta: number; plus_minus: number;
}

export interface TeamBox { team: TeamSummary; players: PlayerLine[]; totals: Record<string, number> }

export interface BoxScore {
  game: Game; arena: string | null; attendance: number | null; officials: string[];
  home: TeamBox; away: TeamBox;
}

export interface Play {
  id: number; order: number; period: number; clock: string; team: string | null;
  player_id: number | null; type: string; subtype: string; text: string;
  home_score: number; away_score: number; is_shot: boolean; made: boolean | null;
  points: number; x: number | null; y: number | null;
  sx?: number | null; sy?: number | null; distance?: number | null; // shot-chart coordinates (tenths of a foot from the rim) and feet
  time_utc: string | null; edited_utc: string | null;
}

export interface PlayerSummary {
  id: number; name: string; is_active: boolean; team: string | null; position: string | null; jersey: string | null;
}

export interface SeasonLine {
  season: string; season_type: "regular" | "playoffs"; team: string; age: number | null; gp: number; gs: number;
  mpg: number; ppg: number; rpg: number; apg: number; spg: number; bpg: number; tpg: number;
  fg_pct: number | null; fg3_pct: number | null; ft_pct: number | null; efg_pct: number | null; ts_pct: number | null;
  pts: number; reb: number; ast: number;
}

export interface DataAvailability { season: string; season_type: "regular" | "playoffs"; games: number; shots: number }

export interface PlayerProfile extends PlayerSummary {
  full_bio_loaded: boolean; birthdate: string | null; age: number | null; country: string | null;
  school: string | null; height: string | null; weight: string | null; team_name: string | null;
  draft: string | null; from_year: number | null; to_year: number | null; greatest_75: boolean;
  regular: SeasonLine[]; playoffs: SeasonLine[];
  career_regular: SeasonLine | null; career_playoffs: SeasonLine | null; available: DataAvailability[];
  injury?: PlayerInjury | null;
  espn_injury?: EspnInjury | null; // only when the official report doesn't cover the player
}

export interface GameLogRow {
  game_id: string; date: string; matchup: string; result: string | null; min: number; pts: number; reb: number;
  ast: number; stl: number; blk: number; tov: number; pf: number; fgm: number; fga: number; fg3m: number;
  fg3a: number; ftm: number; fta: number; plus_minus: number;
}

export interface Shot {
  game_id: string; period: number; clock: string; action: string; shot_type: string; zone: string;
  distance: number; x: number; y: number; made: boolean;
}

export interface ZoneSummary { zone: string; attempts: number; made: number; fg_pct: number }

export interface ShotChart {
  season: string; season_type: string; attempts: number; made: number; fg_pct: number | null;
  zones: ZoneSummary[]; shots: Shot[];
}

export interface Leader { player_id: number; name: string; gp: number; pts: number; reb: number; ast: number }
export interface FormGame { date: string; opp: string; home: boolean; result: string | null; pts: number; margin: number }

export interface TeamPreview {
  team_id: number; abbr: string | null; name: string; wins: number; losses: number;
  current_wins: number | null; current_losses: number | null;
  stats: Record<string, number | null>; ranks: Record<string, number | null>;
  form: FormGame[]; leaders: Leader[]; context?: TeamContext | null;
}
export interface RecordSplit { w: number; l: number; margin: number | null }
/** Schedule context going into a game, from games already played this season. */
export interface TeamContext {
  last_game_date: string | null; days_rest: number | null; back_to_back: boolean; games_last_7: number; streak: string | null;
  home: RecordSplit; away: RecordSplit; last5: RecordSplit | null;
}

export interface SeriesGame {
  date: string; season: string; home_abbr: string; away_abbr: string; home_pts: number; away_pts: number; winner_id: number;
}

export interface Preview {
  season: string; is_fallback: boolean; home: TeamPreview; away: TeamPreview;
  series: { games: SeriesGame[]; home_wins: number; away_wins: number };
}

export interface TeamInfo {
  id: number; abbr: string | null; city: string; name: string; conference: string | null; division: string | null;
}

export interface StandingRow {
  team: TeamInfo; conf_rank: number; div_rank: number; league_rank: number | null; w: number; l: number; pct: number;
  gb: number; home: string; road: string; l10: string; streak: string; conf_record: string; div_record: string;
  ppg: number; opp_ppg: number; diff: number; clinch: "" | "z" | "y" | "x" | "pi" | "e";
}

export interface Standings { season: string; seasons: string[]; min_games: number; teams: StandingRow[] }

export interface TeamProfile {
  team: TeamInfo; standing: StandingRow | null; standings_season: string | null;
  stats_season: string | null; is_fallback: boolean; detail: TeamPreview | null;
}

export interface RosterPlayer {
  player_id: number; name: string; gp: number; min: number; pts: number; reb: number; ast: number;
  position: string | null; jersey: string | null;
}
export interface Roster { season: string; players: RosterPlayer[] }

export interface ScheduleGame {
  game_id: string; date: string; start_utc: string | null; status: "pre" | "live" | "final"; status_text: string;
  home: boolean; opp_id: number; opp_abbr: string; opp_name: string; team_score: number | null;
  opp_score: number | null; result: "W" | "L" | null; label: string | null;
}
export interface Schedule { season: string; seasons: string[]; games: ScheduleGame[] }

// ---- Stats tab (props analysis)
export interface PropWindow { season: string; team_id: number; first: string; last: string }
export interface PropTeammate { player_id: number; name: string; games: number; windows: PropWindow[] }

export interface PropGame {
  game_id: string; date: string; season: string; season_type: "regular" | "playoffs"; team_id: number | null;
  opp_id: number | null; opp_abbr: string; home: boolean; result: "W" | "L" | null; min: number;
  pts: number; reb: number; ast: number; stl: number; blk: number; tov: number; pf: number;
  fgm: number; fga: number; fg3m: number; fg3a: number; ftm: number; fta: number; plus_minus: number | null;
  q1_pts: number | null; q1_reb: number | null; q1_ast: number | null; h1_pts: number | null;
  usg: number | null; rest_days: number | null; opp_def_rank: number | null; opp_pace_rank: number | null; mates: number[];
}

export interface PropNextGame {
  game_id: string; date: string; start_utc: string | null; opp_id: number; opp_abbr: string; opp_name: string; home: boolean;
}

export interface PropsData {
  player_id: number; name: string; seasons: string[]; games: PropGame[]; teammates: PropTeammate[]; next_game: PropNextGame | null;
}

export interface ZoneRow {
  zone: string; label: string; fgm: number; fga: number; fg_pct: number | null; share: number | null;
  league_fg_pct: number | null; opp_fg_pct: number | null; opp_rank: number | null;
}
export interface ShotTypeRow {
  key: string; label: string; fgm: number; fga: number; fg_pct: number | null; share: number | null;
  opp_efg_pct: number | null; opp_rank: number | null;
}
export interface PlayTypeRow {
  key: string; label: string; pts_pg: number; share: number; ppp: number | null; opp_ppp: number | null; opp_rank: number | null;
}
export interface Matchup {
  season: string; seasons: string[]; opponent: { id: number; abbr: string | null; name: string } | null;
  zones: ZoneRow[]; shot_types: ShotTypeRow[]; play_types: PlayTypeRow[]; free_throws_pg: number | null; points_pg: number | null;
}

// ---- similar players
export interface AvgLine {
  min: number; pts: number; reb: number; ast: number; stl: number; blk: number; tov: number; pf: number; fgm: number; fga: number;
  fg3m: number; fg3a: number; ftm: number; fta: number; q1_pts: number | null; q1_reb: number | null; q1_ast: number | null; h1_pts: number | null;
}
export interface SimilarPlayer {
  player_id: number; name: string; position: string | null; team_abbr: string | null; match: number; games_vs_opp: number; averages: AvgLine;
}
export interface SimilarGame extends PropGame { player_id: number; player_name: string; team_abbr: string | null }
export interface Similar {
  season: string; seasons: string[]; mode: "shots" | "position"; opponent: { id: number; abbr: string | null; name: string } | null;
  players: SimilarPlayer[]; games: SimilarGame[];
}

// ---- leaderboards
export interface PlayerLeader {
  rank: number; player_id: number; name: string; team_abbr: string | null; position: string | null; gp: number; value: number;
  min: number; pts: number; reb: number; ast: number; stl: number; blk: number; tov: number; fg3m: number;
  fg_pct: number | null; fg3_pct: number | null; ft_pct: number | null; ts_pct: number | null; usg: number | null; dd: number; td: number;
}
export interface PlayerLeaders {
  season: string; seasons: string[]; season_type: "regular" | "playoffs"; stat: string; label: string; mode: "pg" | "total";
  qualified: boolean; requirement: string | null; team_games: number; total: number; rows: PlayerLeader[];
}
export interface TeamLeader {
  rank: number; team_id: number; abbr: string | null; name: string; conference: string | null; w: number; l: number;
  value: number | null; stats: Record<string, number | null>;
}
export interface TeamLeaders {
  season: string; seasons: string[]; stat: string; label: string; lower_is_better: boolean; team_games: number; rows: TeamLeader[];
}

// ---- availability: official injury report + starting lineups
export type InjuryStatus = "Out" | "Doubtful" | "Questionable" | "Probable" | "Available";

export interface InjuryOut {
  player_id: number | null; name: string; team_id: number | null; team_abbr: string | null; status: InjuryStatus; reason: string;
  matchup: string | null; game_id: string | null; game_date: string | null; game_time: string | null;
  espn_return_date?: string | null; // ESPN's estimated return, when ESPN lists this player
}
/** ESPN's list: unofficial, in ESPN's own words (status is "Out" or "Day-To-Day"). */
export interface EspnInjury {
  player_id: number | null; name: string; team_id: number | null; team_abbr: string | null; status: string; injury: string;
  return_date: string | null; updated_at: string | null;
}
export interface EspnMeta { fetched_at: string; age_minutes: number }
export interface PendingTeam { team_id: number | null; team: string | null; matchup: string | null; game_date: string | null }
export interface ReportMeta { report_id: string; published_at: string; published_utc: string; age_minutes: number; stale: boolean }
export interface InjuryReport {
  report: ReportMeta | null; entries: InjuryOut[]; pending: PendingTeam[];
  espn?: EspnInjury[]; // ESPN entries for players NOT on the official report
  espn_meta?: EspnMeta | null;
}

export interface KeyAbsence { player_id: number | null; name: string; status: InjuryStatus; ppg: number | null }
/** One team's line on the scoreboard: lineup status and which top-five scorers are on the injury report. */
export interface TeamAvailabilitySummary {
  team_id: number; abbr: string | null; lineup_status: "Expected" | "Confirmed" | null; key_players: KeyAbsence[]; others_out: number; report_pending: boolean;
}
export interface GameAvailabilitySummary { game_id: string; away: TeamAvailabilitySummary; home: TeamAvailabilitySummary }

export type ChangeKind = "added" | "removed" | "worsened" | "improved";
/** A difference between two consecutive official reports. */
export interface InjuryChange {
  report_id: string; at: string; at_utc: string; kind: ChangeKind; player_id: number | null; name: string; team_id: number | null;
  team_abbr: string | null; matchup: string | null; game_id: string | null; game_date: string | null;
  from_status: InjuryStatus | null; to_status: InjuryStatus | null; reason: string;
}
export interface InjuryChanges { changes: InjuryChange[]; reports_compared: number }

export interface Starter { player_id: number; name: string; position: string | null; injury_status: InjuryStatus | null; injury_reason: string | null }
export interface TeamAvailability {
  team_id: number; abbr: string | null; name: string; lineup_status: "Expected" | "Confirmed" | null; lineup_updated: string | null;
  starters: Starter[]; injuries: InjuryOut[]; report_pending: boolean; espn_only?: EspnInjury[];
}
export interface GameAvailability { game_id: string; report: ReportMeta | null; home: TeamAvailability; away: TeamAvailability }
export interface PlayerInjury { status: InjuryStatus; reason: string; matchup: string | null; game_date: string | null; reported_at: string; espn_return_date?: string | null }

// ---- data status
export interface HealthItem {
  key: string; label: string; status: "ok" | "stale" | "error" | "never"; last_ok: string | null; age_minutes: number | null;
  max_age_minutes: number; detail: string; last_error: string | null; last_error_at: string | null;
}
export interface Health {
  status: "ok" | "degraded" | "down"; generated_at: string; items: HealthItem[];
  coverage: { players_loaded: number; players_active: number; latest_game_date: string | null; newest_injury_report: string | null; injury_reports_stored: number };
}
