import copy
from datetime import datetime, timedelta, timezone

from altscalp.schedule import LEAGUES, game_from_milestone, is_home_market
from conftest import NHL_MARKETS, NHL_MILESTONE, START


def test_game_uses_milestone_start_not_market_occurrence():
    game = game_from_milestone(NHL_MILESTONE, LEAGUES["NHL"])
    assert game.event_ticker == "KXNHLGAME-26OCT19PITUTA"
    assert game.start == START  # 01:00Z, not the market's occurrence_datetime of 04:00Z
    assert game.window_start == START - timedelta(minutes=30)
    assert game.window_end == START + timedelta(minutes=20)


def test_milestone_for_another_series_is_ignored():
    m = copy.deepcopy(NHL_MILESTONE)
    assert game_from_milestone(m, LEAGUES["NBA"]) is None


def test_falls_back_to_primary_event_tickers():
    m = copy.deepcopy(NHL_MILESTONE)
    del m["details"]["main_game_event_ticker"]
    m["primary_event_tickers"] = ["KXNHLSPREAD-26OCT19PITUTA", "KXNHLGAME-26OCT19PITUTA"]
    assert game_from_milestone(m, LEAGUES["NHL"]).event_ticker == "KXNHLGAME-26OCT19PITUTA"


def test_nba_preseason_is_skipped():
    m = {
        "id": "x", "title": "CLE Cavaliers at ORL Magic", "start_date": "2026-10-13T23:00:00Z",
        "primary_event_tickers": ["KXNBAGAME-26OCT13CLEORL"],
        "details": {"main_game_event_ticker": "KXNBAGAME-26OCT13CLEORL", "home_team_id": "h"},
    }
    assert game_from_milestone(m, LEAGUES["NBA"]) is None
    # Opening night (Oct 20 ET, which is Oct 20 23:30Z) is regular season.
    m["start_date"] = "2026-10-20T23:30:00Z"
    assert game_from_milestone(m, LEAGUES["NBA"]) is not None


def test_nba_cutoff_keeps_late_oct_19_et_games_out():
    assert LEAGUES["NBA"].regular_season_start > datetime(2026, 10, 20, 4, tzinfo=timezone.utc)


def test_home_market_matched_by_team_id():
    home_id = NHL_MILESTONE["details"]["home_team_id"]
    assert is_home_market(NHL_MARKETS[0], home_id) is True  # UTA
    assert is_home_market(NHL_MARKETS[1], home_id) is False  # PIT
    assert is_home_market(NHL_MARKETS[0], None) is None
    assert is_home_market({"ticker": "X"}, home_id) is None
