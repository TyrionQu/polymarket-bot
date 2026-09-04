import os
import re
import sys
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY

# --- Configurations ---
HOST = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon Mainnet
PRIVATE_KEY = os.environ.get("POLYMARKET_PRIVATE_KEY", "").strip()

if not PRIVATE_KEY:
    sys.exit("POLYMARKET_PRIVATE_KEY is not set.")

if not PRIVATE_KEY.startswith("0x"):
    PRIVATE_KEY = "0x" + PRIVATE_KEY

# A Polygon/Ethereum private key is 32 bytes = 64 hex characters.
if not re.fullmatch(r"0x[0-9a-fA-F]{64}", PRIVATE_KEY):
    sys.exit("POLYMARKET_PRIVATE_KEY must be a 64-character hex string (optionally 0x-prefixed).")

# Initialize the Client
client = ClobClient(
    host=HOST,
    key=PRIVATE_KEY,
    chain_id=CHAIN_ID,
)

# Set API Credentials
client.set_api_creds(client.create_or_derive_api_creds())

# --- Order Parameters ---
# Token ID corresponds to the specific outcome (YES/NO) on Polymarket
TOKEN_ID = os.environ.get("POLYMARKET_TOKEN_ID", "").strip()
if not TOKEN_ID:
    sys.exit("POLYMARKET_TOKEN_ID is not set.")

PRICE = 0.52   # Limit price ($0.52)
SIZE = 100.0   # Number of shares to buy

# Create and Post Order
order_args = OrderArgs(
    price=PRICE,
    size=SIZE,
    side=BUY,
    token_id=TOKEN_ID,
)

signed_order = client.create_order(order_args)
response = client.post_order(signed_order, OrderType.GTC)

print("Order Response:", response)
