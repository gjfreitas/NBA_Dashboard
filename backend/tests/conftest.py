import os
from pathlib import Path

os.environ["NBA_AUTOCREATE"] = "1"  # app module builds a default app; tests build their own
os.environ["NBA_SOURCE"] = "replay"

import pytest

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
GAME = "0022600001"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture(autouse=True)
def no_availability_network(monkeypatch, request):
    """refresh_once runs the injury/lineup poll on every pass; keep it off the network except in tests that provide fake files."""
    if "real_availability" in request.keywords:
        return
    from nbadash import refresh
    monkeypatch.setattr(refresh, "refresh_availability", lambda conn: {})


@pytest.fixture(autouse=True)
def no_real_fetch(monkeypatch):
    """webget.fetch is the only door to NBA/ESPN-hosted files. Tests pass their own getters or patch this; the real one must never run."""
    from nbadash import webget

    def blocked(url, **kw):
        raise AssertionError(f"a test tried to fetch {url} from the real network")

    monkeypatch.setattr(webget, "fetch", blocked)


@pytest.fixture(autouse=True)
def no_real_odds(monkeypatch):
    """Odds keys in the developer's environment must not leak into tests, and odds.http_get must never reach a real provider."""
    from nbadash import odds

    for k in ("THE_ODDS_API_KEY", "SPORTSGAMEODDS_API_KEY", "ODDS_PROVIDER", "ODDS_MARKETS", "ODDS_MONTHLY_BUDGET", "ODDS_MIN_HOURS", "ODDS_BOOKMAKERS", "ODDS_REGIONS"):
        monkeypatch.delenv(k, raising=False)

    def blocked(url, headers, params):
        raise AssertionError(f"a test tried to call {url} on the real network")

    monkeypatch.setattr(odds, "http_get", blocked)
