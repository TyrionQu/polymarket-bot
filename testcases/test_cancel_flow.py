import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import list_open_orders as m


class FakeClient:
    def cancel_order(self, payload):
        raise AssertionError("should not be called in dry-run")


fake_orders = [
    {"id": "0xORDER1", "asset_id": "111", "outcome": "Yes", "side": "BUY", "price": "0.5",
     "original_size": "100", "size_matched": "0", "status": "LIVE", "order_type": "GTC", "created_at": 1780000000},
]
items = m.build_items(fake_orders, [])
m.process_selection(FakeClient(), items, dry_run=True)
print("DONE")
