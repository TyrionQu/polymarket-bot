import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import list_open_orders as m


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


# Mimics the Data API v2 /v2/positions response: payload wrapped in "data" with
# snake_case fields. Includes one open bet, one resolved/redeemable bet, and one
# fully-closed (zero size) bet; only the first should survive filtering.
captured = {}


def fake_get(url, params=None, timeout=None):
    captured["url"] = url
    captured["params"] = params
    return FakeResponse({
        "data": [
            {"token_id": "111", "current_size": 50, "redeemable": False, "title": "Open bet?"},
            {"token_id": "222", "current_size": 10, "redeemable": True, "title": "Already resolved?"},
            {"token_id": "333", "current_size": 0, "redeemable": False, "title": "Closed out?"},
        ],
        "pagination": {"limit": 500, "offset": 0, "has_more": False, "next_cursor": None},
    })


m.requests.get = fake_get

held = m.fetch_held_positions("0xWALLET")

assert captured["url"].endswith("/v2/positions"), captured["url"]
assert captured["params"]["user"] == "0xWALLET", captured["params"]
assert len(held) == 1, held
assert held[0]["token_id"] == "111", held

# build_items must read the v2 "token_id" field as the address.
items = m.build_items([], held)
assert items[0]["address"] == "111", items

# A null "data" payload (documented as "no positions") must not crash.
m.requests.get = lambda url, params=None, timeout=None: FakeResponse({"data": None})
assert m.fetch_held_positions("0xWALLET") == []

# format_position must render without KeyError using v2 field names.
print(m.format_position(held[0]))

print("DONE")
