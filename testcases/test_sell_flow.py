import io
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
    {"token_id": "222", "current_size": 50, "avg_price": 0.4, "current_price": 0.45, "current_value": 22.5,
     "total_pnl": 2.5, "percent_pnl": 12.5, "title": "Fake market?", "outcome": "No", "redeemable": False},
]
items = m.build_items([], fake_positions)

order_book_calls = []


def fake_show_order_book(token_id):
    order_book_calls.append(token_id)
    print(f"(fake order book for {token_id})")


m.show_order_book = fake_show_order_book

# Drive: select bet 0, confirm sell, enter 0 (refresh order book), then a real
# price, shares, and confirm. The lone 0 exercises the refresh-and-reprompt path.
sys.stdin = io.StringIO("0\ny\n0\n0.5\n25\ny\n")
m.process_selection(FakeClient(), items, dry_run=True)

# Initial book + one refresh triggered by entering 0 at the price prompt.
assert len(order_book_calls) == 2, order_book_calls

# Entering 1 at the sell-price prompt exits the program.
sys.stdin = io.StringIO("0\ny\n1\n")
try:
    m.process_selection(FakeClient(), items, dry_run=True)
    raise AssertionError("expected SystemExit when entering 1 at the price prompt")
except SystemExit:
    pass

print("DONE")
