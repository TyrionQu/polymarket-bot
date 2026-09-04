import argparse
import os
from datetime import datetime, timezone

import requests
from py_clob_client_v2 import ClobClient

from buy_polymarket import CHAIN_ID, HOST, load_polymarket_config, load_private_key

GAMMA_HOST = "https://gamma-api.polymarket.com"
DATA_HOST = "https://data-api.polymarket.com"


def question_for_token(token_id: str) -> str:
    """Best-effort lookup of a token's market question via the public Gamma API."""
    try:
        resp = requests.get(f"{GAMMA_HOST}/markets", params={"clob_token_ids": token_id}, timeout=10)
        resp.raise_for_status()
        markets = resp.json()
        if markets:
            return markets[0].get("question") or token_id
    except Exception:
        pass
    return token_id


def format_order(order: dict) -> str:
    token_id = order.get("asset_id", "")
    price = float(order.get("price", 0))
    original_size = float(order.get("original_size", 0))
    size_matched = float(order.get("size_matched", 0))
    remaining = original_size - size_matched

    created_str = ""
    created = order.get("created_at")
    if created:
        try:
            created_str = datetime.fromtimestamp(int(created), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        except (ValueError, TypeError):
            created_str = str(created)

    return "\n".join([
        f"Question : {question_for_token(token_id)}",
        f"Order ID : {order.get('id')}",
        f"Outcome  : {order.get('outcome')}  side={order.get('side')}",
        f"Price    : {price}",
        f"Size     : {original_size} total (filled: {size_matched}, remaining: {remaining})",
        f"Status   : {order.get('status')} ({order.get('order_type')})",
        f"Created  : {created_str}",
    ])


def fetch_held_positions(address: str) -> list:
    """Positions currently held for a wallet, via the public data-api (no CLOB auth needed)."""
    resp = requests.get(f"{DATA_HOST}/positions", params={"user": address, "limit": 500}, timeout=15)
    resp.raise_for_status()
    positions = resp.json()
    # "redeemable" means the market already resolved and this token can be cashed out;
    # exclude those to show only bets that haven't been decided win/lose yet.
    return [p for p in positions if not p.get("redeemable") and float(p.get("size") or 0) > 0]


def format_position(position: dict) -> str:
    size = float(position.get("size", 0))
    avg_price = float(position.get("avgPrice", 0))
    cur_price = float(position.get("curPrice", 0))
    current_value = float(position.get("currentValue", 0))
    cash_pnl = float(position.get("cashPnl", 0))
    percent_pnl = position.get("percentPnl")

    return "\n".join([
        f"Question    : {position.get('title')}",
        f"Outcome     : {position.get('outcome')}",
        f"Shares held : {size}",
        f"Avg price   : {avg_price}   Current price: {cur_price}",
        f"Value       : ${current_value:.2f}   PnL: ${cash_pnl:.2f}"
        + (f" ({percent_pnl:.2f}%)" if percent_pnl is not None else ""),
    ])


def main():
    parser = argparse.ArgumentParser(
        description="List your unfinished orders (unfilled) and held bets (bought, not yet resolved)."
    )
    parser.add_argument(
        "--signature-type",
        type=int,
        default=int(os.environ.get("POLYMARKET_SIGNATURE_TYPE", "0")),
        help="Wallet type: 0=EOA (default), 1=email/Magic proxy, 2=browser/Gnosis Safe proxy, 3=deposit wallet.",
    )
    args = parser.parse_args()

    # Deposit/proxy wallet address: not a CLI flag, since it rarely changes between runs.
    args.funder = (
        os.environ.get("POLYMARKET_FUNDER", "").strip() or (load_polymarket_config().get("funder") or "").strip()
    ) or None

    private_key = load_private_key()
    client = ClobClient(
        host=HOST,
        key=private_key,
        chain_id=CHAIN_ID,
        signature_type=args.signature_type,
        funder=args.funder,
    )
    client.set_api_creds(client.create_or_derive_api_key())

    orders = client.get_open_orders()
    if orders:
        print(f"Found {len(orders)} open order(s)\n")
        for order in orders:
            print(format_order(order))
            print("-" * 80)
    else:
        print("No open (unfinished) orders.")

    # Positions are tracked by the address that actually holds the funds/shares:
    # the deposit/proxy wallet for signature types 1-3, or the signer itself for a plain EOA.
    holder_address = args.funder if args.signature_type != 0 else client.get_address()
    positions = fetch_held_positions(holder_address)

    print(f"\nFound {len(positions)} held bet(s) not yet decided (address {holder_address})\n")
    for position in positions:
        print(format_position(position))
        print("-" * 80)


if __name__ == "__main__":
    main()
