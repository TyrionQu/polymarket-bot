import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import list_open_orders as m


class FakeClient:
    def create_order(self, args):
        raise AssertionError("should not be called in dry-run")

    def post_order(self, order, order_type):
        raise AssertionError("should not be called in dry-run")


fake_positions = [
    {"asset": "222", "size": 50, "avgPrice": 0.4, "curPrice": 0.45, "currentValue": 22.5,
     "cashPnl": 2.5, "percentPnl": 12.5, "title": "Fake market?", "outcome": "No", "redeemable": False},
]
items = m.build_items([], fake_positions)


def fake_show_order_book(token_id):
    print(f"(fake order book for {token_id})")


m.show_order_book = fake_show_order_book
m.process_selection(FakeClient(), items, dry_run=True)
print("DONE")
