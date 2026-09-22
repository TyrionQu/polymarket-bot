import io
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import buy_polymarket as buy
import list_bets


class FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def make_market(question, tradeable, tokens):
    return {
        "question": question,
        "slug": question.lower(),
        "closed": not tradeable,
        "acceptingOrders": tradeable,
        "enableOrderBook": True,
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.4", "0.6"]' if tradeable else '["0", "1"]',
        "clobTokenIds": f'["{tokens[0]}", "{tokens[1]}"]',
    }


EVENT_MARKETS = [
    make_market("Resolved-A", tradeable=False, tokens=["ra_yes", "ra_no"]),
    make_market("Live-B", tradeable=True, tokens=["lb_yes", "lb_no"]),
    make_market("Live-C", tradeable=True, tokens=["lc_yes", "lc_no"]),
]


def test_resolve_prefers_event_over_colliding_market():
    # The slug matches BOTH an event (3 markets) and a single resolved sub-market.
    def fake_get(url, timeout=15):
        if "/events/slug/" in url:
            return FakeResp(200, {"markets": EVENT_MARKETS})
        if "/markets/slug/" in url:
            return FakeResp(200, make_market("Resolved-A", tradeable=False, tokens=["ra_yes", "ra_no"]))
        return FakeResp(404, {})

    original = list_bets.requests.get
    list_bets.requests.get = fake_get
    try:
        markets = list_bets.resolve_markets_by_slug("https://polymarket.com/event/some-event")
    finally:
        list_bets.requests.get = original
    assert len(markets) == 3, markets


def test_resolve_falls_back_to_market_when_no_event():
    def fake_get(url, timeout=15):
        if "/events/slug/" in url:
            return FakeResp(404, {})
        if "/markets/slug/" in url:
            return FakeResp(200, make_market("Solo", tradeable=True, tokens=["s_yes", "s_no"]))
        return FakeResp(404, {})

    original = list_bets.requests.get
    list_bets.requests.get = fake_get
    try:
        markets = list_bets.resolve_markets_by_slug("solo")
    finally:
        list_bets.requests.get = original
    assert len(markets) == 1 and markets[0]["question"] == "Solo", markets


def test_is_tradeable():
    assert buy.is_tradeable(make_market("Live", tradeable=True, tokens=["a", "b"]))
    assert not buy.is_tradeable(make_market("Done", tradeable=False, tokens=["a", "b"]))
    assert not buy.is_tradeable({"closed": False, "acceptingOrders": True, "enableOrderBook": False})


def test_picker_skips_resolved_markets():
    # Resolved market is first; if filtering works, the tradeable "Live-B" is offered as [1/N].
    args = types.SimpleNamespace(mode="market")
    sys.stdin = io.StringIO("y\ne\n")  # buy Yes on the first tradeable market, then enter amount
    label, token_id, price = buy.select_token_interactively(EVENT_MARKETS, args)
    assert (label, token_id, price) == ("YES", "lb_yes", 0.4), (label, token_id, price)


test_resolve_prefers_event_over_colliding_market()
test_resolve_falls_back_to_market_when_no_event()
test_is_tradeable()
test_picker_skips_resolved_markets()
print("DONE")
