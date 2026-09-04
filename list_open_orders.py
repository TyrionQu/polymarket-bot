import argparse
import os
import sys
from datetime import datetime, timezone

import requests
from py_clob_client_v2 import ClobClient, OrderArgs, OrderPayload, OrderType
from py_clob_client_v2.order_builder.constants import SELL

from buy_polymarket import (
    CHAIN_ID,
    HOST,
    load_polymarket_config,
    load_private_key,
    prompt_choice,
    prompt_float,
    show_order_book,
)

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


def build_items(orders: list, positions: list) -> list:
    """Merges orders and positions into one numbered list, each tagged with its type and address (token_id)."""
    items = []
    for order in orders:
        items.append({"type": "order", "address": order.get("asset_id"), "data": order})
    for position in positions:
        items.append({"type": "position", "address": position.get("asset"), "data": position})
    return items


def print_items(items: list):
    for i, item in enumerate(items):
        print(f"[{i}] type={item['type']}  address={item['address']}")
        if item["type"] == "order":
            print(format_order(item["data"]))
        else:
            print(format_position(item["data"]))
        print("-" * 80)


def cancel_order_flow(client: ClobClient, order: dict, dry_run: bool):
    order_id = order.get("id")
    if prompt_choice(f"Cancel this order ({order_id})? [y/n] ", {"y", "n"}) != "y":
        return
    if dry_run:
        print(f"[DRY RUN] Would cancel order {order_id}")
        return
    result = client.cancel_order(OrderPayload(orderID=order_id))
    print("Cancel result:", result)


def sell_position_flow(client: ClobClient, position: dict, dry_run: bool):
    if prompt_choice("Sell this bet? [y/n] ", {"y", "n"}) != "y":
        return

    token_id = position.get("asset")
    held_size = float(position.get("size", 0))
    show_order_book(token_id)

    price = prompt_float("Enter your sell price, between 0 and 1: $", min_value=0.0001, max_value=0.9999)
    size = prompt_float(f"Enter number of shares to sell (you hold {held_size}): ", min_value=0.0001, max_value=held_size)

    print("\nSell order summary:")
    print(f"  token_id : {token_id}")
    print("  side     : SELL")
    print(f"  price    : {price}")
    print(f"  size     : {size}")
    print(f"  total    : ${price * size:.2f}")

    if prompt_choice("Confirm and place this sell order? [y/n] ", {"y", "n"}) != "y":
        sys.exit("Cancelled.")

    if dry_run:
        print("[DRY RUN] Would submit the sell order above; nothing was sent.")
        return

    order_args = OrderArgs(price=price, size=size, side=SELL, token_id=token_id)
    signed_order = client.create_order(order_args)
    response = client.post_order(signed_order, OrderType.GTC)
    print("Order Response:", response)


def process_selection(client: ClobClient, items: list, dry_run: bool):
    if not items:
        return
    choice = input("\nEnter the ID of a bet/order to process (or press Enter to skip): ").strip()
    if not choice:
        return
    try:
        item = items[int(choice)]
    except (ValueError, IndexError):
        sys.exit(f"Invalid ID: {choice!r}")

    if item["type"] == "order":
        cancel_order_flow(client, item["data"], dry_run)
    else:
        sell_position_flow(client, item["data"], dry_run)


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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview a cancel/sell action without actually submitting it",
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
    holder_address = args.funder if args.signature_type != 0 else client.get_address()
    positions = fetch_held_positions(holder_address)

    items = build_items(orders, positions)
    if not items:
        print("No open orders or held bets.")
        return

    print(f"Found {len(orders)} open order(s) and {len(positions)} held bet(s) not yet decided"
          f" (address {holder_address})\n")
    print_items(items)
    process_selection(client, items, args.dry_run)


if __name__ == "__main__":
    main()
