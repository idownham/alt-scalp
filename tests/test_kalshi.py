import httpx
import pytest

from altscalp.kalshi import BASE_URL, KalshiClient, parse_book, price_e4, size_e2
from conftest import BOOK_FP, TRADE


def test_units_are_exact_integers():
    assert price_e4("0.5100") == 5100
    assert price_e4("0.0001") == 1
    assert size_e2("102.94") == 10294
    assert size_e2("30034.00") == 3003400


@pytest.mark.parametrize("bad", ["0.51005", "0.123456"])
def test_price_with_extra_precision_is_rejected(bad):
    with pytest.raises(ValueError):
        price_e4(bad)


def test_size_with_extra_precision_is_rejected():
    with pytest.raises(ValueError):
        size_e2("1.001")


def test_book_levels_sorted_best_first_and_ask_is_complement():
    book = parse_book("T", BOOK_FP)
    assert [lvl.price_e4 for lvl in book.yes_bids] == [5400, 5000, 100]
    assert [lvl.price_e4 for lvl in book.no_bids] == [3800, 3000, 100]
    assert book.best_yes_bid_e4 == 5400
    assert book.best_yes_ask_e4 == 6200  # 1 - 0.38
    assert book.raw is BOOK_FP  # kept as received for the evidence trail


def test_empty_book_has_no_best_prices():
    book = parse_book("T", {"no_dollars": [], "yes_dollars": []})
    assert book.best_yes_bid_e4 is None and book.best_yes_ask_e4 is None


def _client(handler):
    http = httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    return KalshiClient(http=http, sleep=lambda s: None)


def test_orderbooks_sends_repeated_tickers_param():
    seen = {}

    def handler(request):
        seen["tickers"] = request.url.params.get_list("tickers")
        return httpx.Response(200, json={"orderbooks": [
            {"ticker": t, "orderbook_fp": BOOK_FP} for t in seen["tickers"]]})

    books = _client(handler).orderbooks(["A", "B"])
    assert seen["tickers"] == ["A", "B"]
    assert set(books) == {"A", "B"}


def test_orderbooks_rejects_more_than_100_tickers():
    with pytest.raises(ValueError):
        _client(lambda r: httpx.Response(200, json={})).orderbooks([f"T{i}" for i in range(101)])


def test_orderbooks_does_not_retry_429_by_default_but_counts_it():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, json={"error": "too many requests"})

    client = _client(handler)
    with pytest.raises(httpx.HTTPStatusError):
        client.orderbooks(["A"])
    assert len(calls) == 1
    assert client.rate_limits.count == 1


def test_trades_follow_cursor():
    pages = {"": {"trades": [TRADE], "cursor": "next"}, "next": {"trades": [dict(TRADE, trade_id="x")], "cursor": ""}}

    def handler(request):
        assert request.url.params["ticker"] == "T"
        assert request.url.params["min_ts"] == "100"
        return httpx.Response(200, json=pages[request.url.params.get("cursor", "")])

    assert [t["trade_id"] for t in _client(handler).trades("T", 100, 200)] == [TRADE["trade_id"], "x"]


def test_incentives_use_next_cursor():
    pages = {"": {"incentive_programs": [{"id": "1"}], "next_cursor": "n"}, "n": {"incentive_programs": [{"id": "2"}]}}

    def handler(request):
        return httpx.Response(200, json=pages[request.url.params.get("cursor", "")])

    assert [p["id"] for p in _client(handler).active_incentive_programs()] == ["1", "2"]


@pytest.mark.live
def test_live_public_endpoints_need_no_auth():
    with KalshiClient() as client:
        series = client.series("KXNHLGAME")
        assert series["fee_type"] == "quadratic_with_maker_fees"
        milestones = list(client.milestones("NHL", "2026-10-13T00:00:00Z"))
        assert milestones and all("start_date" in m for m in milestones)
