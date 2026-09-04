import os
import re
import sys

import requests
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import AssetType, BalanceAllowanceParams

HOST = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon Mainnet
GEOBLOCK_URL = "https://polymarket.com/api/geoblock"  # public, unauthenticated eligibility check


def load_private_key() -> str:
    key = os.environ.get("POLYMARKET_PRIVATE_KEY", "").strip()
    if not key:
        return ""
    if not key.startswith("0x"):
        key = "0x" + key
    if not re.fullmatch(r"0x[0-9a-fA-F]{64}", key):
        sys.exit("POLYMARKET_PRIVATE_KEY must be a 64-character hex string (optionally 0x-prefixed).")
    return key


def check(label, fn):
    try:
        result = fn()
        print(f"[OK]   {label}: {result}")
        return result
    except Exception as e:
        print(f"[FAIL] {label}: {e}")
        return None


def check_trading_eligibility():
    resp = requests.get(GEOBLOCK_URL, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("blocked"):
        raise RuntimeError(f"IP is geo-blocked from trading: {data}")
    return data


def test_without_key():
    """Level 0: public endpoints, no private key required."""
    print("=== Test: without key (public endpoints) ===")
    client = ClobClient(host=HOST, chain_id=CHAIN_ID)

    check("Server health", client.get_ok)
    check("Server time", client.get_server_time)
    check("IP can buy/sell (not geo-blocked)", check_trading_eligibility)


def test_with_key():
    """Level 1/2: signer + API creds, requires POLYMARKET_PRIVATE_KEY."""
    print("\n=== Test: with key (authenticated endpoints) ===")
    private_key = load_private_key()
    if not private_key:
        print("[SKIP] POLYMARKET_PRIVATE_KEY not set.")
        return

    client = ClobClient(host=HOST, chain_id=CHAIN_ID, key=private_key)

    address = check("Wallet address", client.get_address)

    creds = check("Derive/create API creds", client.create_or_derive_api_creds)
    if not creds:
        return
    client.set_api_creds(creds)

    check("API keys", client.get_api_keys)
    if address:
        check(
            "Collateral balance/allowance",
            lambda: client.get_balance_allowance(
                BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            ),
        )


def main():
    test_without_key()
    test_with_key()


if __name__ == "__main__":
    main()
