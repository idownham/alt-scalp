"""Which games to record, and when.

The scheduled start comes from the game's milestone `start_date`. Market
`occurrence_datetime` is the expected *end* of the game, so it is not used
(docs/s0-research.md, finding 3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

# Pre-registered window (docs/spec.md): 30 min before to 20 min after scheduled start.
WINDOW_BEFORE = timedelta(minutes=30)
WINDOW_AFTER = timedelta(minutes=20)


@dataclass(frozen=True)
class League:
    name: str  # the milestone `competition` filter
    series: str
    regular_season_start: datetime  # games before this are preseason and are skipped


LEAGUES = {
    "NFL": League("NFL", "KXNFLGAME", datetime(2026, 9, 1, tzinfo=timezone.utc)),
    # NBA regular season starts Oct 20 (ET); 2026-10-20T00:00Z is still Oct 19 evening ET, so cut at 12:00Z.
    "NBA": League("NBA", "KXNBAGAME", datetime(2026, 10, 20, 12, tzinfo=timezone.utc)),
    "NHL": League("NHL", "KXNHLGAME", datetime(2026, 10, 1, tzinfo=timezone.utc)),
}


@dataclass(frozen=True)
class Game:
    event_ticker: str
    league: str
    title: str
    start: datetime  # scheduled start, UTC
    home_team_id: str | None
    milestone_id: str

    @property
    def window_start(self) -> datetime:
        return self.start - WINDOW_BEFORE

    @property
    def window_end(self) -> datetime:
        return self.start + WINDOW_AFTER


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def game_from_milestone(milestone: dict[str, Any], league: League) -> Game | None:
    """The game a milestone describes, or None if it isn't a regular-season game in this league's series."""
    details = milestone.get("details") or {}
    event_ticker = details.get("main_game_event_ticker") or next(
        (t for t in milestone.get("primary_event_tickers", []) if t.startswith(league.series + "-")), None
    )
    if not event_ticker or not event_ticker.startswith(league.series + "-"):
        return None
    start = parse_time(milestone["start_date"])
    if start < league.regular_season_start:
        return None
    return Game(
        event_ticker=event_ticker,
        league=league.name,
        title=milestone.get("title", ""),
        start=start,
        home_team_id=details.get("home_team_id"),
        milestone_id=milestone["id"],
    )


def is_home_market(market: dict[str, Any], home_team_id: str | None) -> bool | None:
    """True if this market is 'home team wins', False if not, None if it can't be told.

    Each game market's `custom_strike` names its team ({"hockey_team": id}, etc.),
    and the milestone names the home team's id.
    """
    if not home_team_id:
        return None
    team_ids = set((market.get("custom_strike") or {}).values())
    if not team_ids:
        return None
    return home_team_id in team_ids
