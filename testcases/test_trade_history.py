import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import list_trade_history as m


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


# --- fetch_trades builds the expected query params and passes through the payload ---
captured = {}


def fake_get(url, params=None, timeout=15):
    captured["url"] = url
    captured["params"] = params
    return FakeResp([{"side": "BUY"}])


m.requests.get = fake_get

result = m.fetch_trades("0xabc", limit=10, offset=5, side="BUY")
assert result == [{"side": "BUY"}], result
assert captured["url"].endswith("/trades"), captured["url"]
assert captured["params"] == {"user": "0xabc", "limit": 10, "offset": 5, "side": "BUY"}, captured["params"]

# side omitted -> no side key in params
m.fetch_trades("0xabc", limit=3)
assert "side" not in captured["params"], captured["params"]


# --- format_trade renders the key fields and computes total = price * size ---
trade = {
    "side": "BUY",
    "outcome": "Yes",
    "size": 5,
    "price": 0.4,
    "timestamp": 1790778602,
    "title": "Will X win?",
    "transactionHash": "0xdeadbeef",
}
text = m.format_trade(trade)
assert "Will X win?" in text, text
assert "Side     : BUY" in text, text
assert "Outcome: Yes" in text, text
assert "Total    : $2.00" in text, text
assert "0xdeadbeef" in text, text

# Empty title falls back to slug.
fallback = m.format_trade({"title": "", "slug": "some-slug", "size": 1, "price": 0.1})
assert "some-slug" in fallback, fallback


# --- resolve_address: explicit --address wins and never touches the key ---
def make_args(**kw):
    defaults = {"signature_type": 0, "address": None}
    defaults.update(kw)
    return types.SimpleNamespace(**defaults)


m.load_private_key = lambda: (_ for _ in ()).throw(AssertionError("should not load key when --address is given"))
assert m.resolve_address(make_args(address="0xExplicit")) == "0xExplicit"

# Non-EOA wallet uses the funder address (still no key needed).
m.load_polymarket_config = lambda: {"funder": "0xFunder"}
os.environ.pop("POLYMARKET_FUNDER", None)
assert m.resolve_address(make_args(signature_type=1)) == "0xFunder"

# Non-EOA with no funder configured is an error.
m.load_polymarket_config = lambda: {}
try:
    m.resolve_address(make_args(signature_type=2))
    raise AssertionError("expected SystemExit when a proxy wallet has no funder")
except SystemExit:
    pass

# EOA derives the address from the private key via the CLOB client.
m.load_polymarket_config = lambda: {}
m.load_private_key = lambda: "0x" + "1" * 64


class FakeClient:
    def __init__(self, **kwargs):
        pass

    def get_address(self):
        return "0xDerivedFromKey"


m.ClobClient = FakeClient
assert m.resolve_address(make_args(signature_type=0)) == "0xDerivedFromKey"

print("DONE")
