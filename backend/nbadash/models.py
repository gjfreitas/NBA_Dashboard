"""Our own schema. NBA quirks (string scores, ISO clocks, nullable ids) stop at the normalizer."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

GameState = Literal["pre", "live", "final"]


class PeriodScore(BaseModel):
    period: int
    score: int


class TeamSummary(BaseModel):
    id: int
    tricode: str
    city: str
    name: str
    score: int = 0
    wins: Optional[int] = None
    losses: Optional[int] = None
    periods: list[PeriodScore] = []


class Game(BaseModel):
    id: str
    state: GameState
    status_text: str
    period: int
    clock: str  # "MM:SS" or ""
    start_utc: Optional[str] = None
    home: TeamSummary
    away: TeamSummary


class PlayerLine(BaseModel):
    id: int
    name: str
    short_name: str
    jersey: str
    position: str
    starter: bool
    on_court: bool
    played: bool
    minutes: str  # "MM:SS"
    points: int
    rebounds: int
    assists: int
    steals: int
    blocks: int
    turnovers: int
    fouls: int
    fgm: int
    fga: int
    tpm: int
    tpa: int
    ftm: int
    fta: int
    plus_minus: float


class TeamBox(BaseModel):
    team: TeamSummary
    players: list[PlayerLine]
    totals: dict[str, float]


class BoxScore(BaseModel):
    game: Game
    arena: Optional[str] = None
    attendance: Optional[int] = None
    officials: list[str] = []
    home: TeamBox
    away: TeamBox


class Play(BaseModel):
    id: int  # actionNumber, the stable key for diffing
    order: int
    period: int
    clock: str
    team: Optional[str] = None  # tricode
    player_id: Optional[int] = None
    type: str
    subtype: str = ""
    text: str
    home_score: int
    away_score: int
    is_shot: bool = False
    made: Optional[bool] = None
    points: int = 0
    x: Optional[float] = None  # 0-100 court coordinates (NBA normalized)
    y: Optional[float] = None
    sx: Optional[int] = None  # shot-chart coordinates: tenths of a foot from the rim, +y toward half court (same units as player shots)
    sy: Optional[int] = None
    distance: Optional[float] = None  # feet
    time_utc: Optional[str] = None
    edited_utc: Optional[str] = None
