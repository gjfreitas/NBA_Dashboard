import json

import pytest

from nbadash.normalize import (normalize_boxscore, normalize_playbyplay,
                               normalize_scoreboard, parse_clock)

GAME = "0022600001"


def load(fixtures_dir, name):
    return json.loads((fixtures_dir / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("raw,expected", [
    ("PT10M36.00S", "10:36"), ("PT00M00.00S", "0:00"), ("PT33M15.00S", "33:15"),
    ("PT05.30S", "0:05"), ("", ""), (None, ""),
])
def test_parse_clock(raw, expected):
    assert parse_clock(raw) == expected


def test_scoreboard(fixtures_dir):
    games = normalize_scoreboard(load(fixtures_dir, "todaysScoreboard_00.json"))
    assert games and games[0].state == "pre"
    assert games[0].home.tricode and games[0].away.tricode


def test_boxscore(fixtures_dir):
    box = normalize_boxscore(load(fixtures_dir, f"boxscore_{GAME}.json"))
    assert box.game.state == "final"
    for side in (box.home, box.away):
        assert sum(p.points for p in side.players) == side.team.score
        assert any(p.starter for p in side.players)
    assert box.home.players[0].minutes.count(":") == 1


def test_playbyplay(fixtures_dir):
    box = normalize_boxscore(load(fixtures_dir, f"boxscore_{GAME}.json"))
    plays = normalize_playbyplay(load(fixtures_dir, f"playbyplay_{GAME}.json"))
    ids = [p.id for p in plays]
    assert len(set(ids)) == len(ids)  # actionNumber is a unique identity, but NOT a chronological order
    last = plays[-1]
    assert (last.home_score, last.away_score) == (box.home.team.score, box.away.team.score)
    shots = [p for p in plays if p.is_shot]
    assert shots and all(p.x is not None and p.made is not None for p in shots)
    assert any(p.points == 3 for p in shots)
    # shot-chart coordinates: every field goal has them, they sit on the half court, and made 3s are far from the rim
    assert all(p.sx is not None and p.sy is not None and p.distance is not None for p in shots)
    assert all(-250 <= p.sx <= 250 and -60 <= p.sy <= 430 for p in shots)
    threes = [p for p in shots if p.points == 3]
    assert all((p.sx ** 2 + p.sy ** 2) ** 0.5 / 10 > 21 for p in threes)  # at least the corner-three distance (22 ft) from the rim, within rounding
    assert all(p.sx is None for p in plays if not p.is_shot)


def test_points_are_shot_values_and_sum_to_final_score(fixtures_dir):
    plays = normalize_playbyplay(load(fixtures_dir, f"playbyplay_{GAME}.json"))
    box = normalize_boxscore(load(fixtures_dir, f"boxscore_{GAME}.json"))
    assert {p.points for p in plays} <= {0, 1, 2, 3}
    for tri, team in ((box.home.team.tricode, box.home.team), (box.away.team.tricode, box.away.team)):
        assert sum(p.points for p in plays if p.team == tri) == team.score


@pytest.mark.parametrize("gid", ["0022600001", "0022600002"])
def test_plays_are_in_game_clock_order(fixtures_dir, gid):
    """Regression: sorting by actionNumber put 11-30 plays per game out of order; orderNumber is correct."""
    plays = normalize_playbyplay(load(fixtures_dir, f"playbyplay_{gid}.json"))
    assert [p.order for p in plays] == sorted(p.order for p in plays)

    def remaining(c):
        m, s = c.split(":")
        return int(m) * 60 + int(s)

    real = [p for p in plays if p.type not in ("period", "game")]
    keys = [(p.period, -remaining(p.clock)) for p in real]
    assert keys == sorted(keys)
    assert [p.id for p in plays] != sorted(p.id for p in plays)  # proves the two orders really differ
