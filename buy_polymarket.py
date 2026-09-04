import argparse
import json
import os
import re
import sys

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import MarketOrderArgs, OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY

from list_bets import resolve_markets_by_slug

# --- Configurations ---
HOST = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon Mainnet
DRY_RUN_PLACEHOLDER_TOKEN_ID = "0" * 64


def load_private_key() -> str:
    key = os.environ.get("POLYMARKET_PRIVATE_KEY", "").strip()
    if not key:
        sys.exit("POLYMARKET_PRIVATE_KEY is not set.")
    if not key.startswith("0x"):
        key = "0x" + key
    # A Polygon/Ethereum private key is 32 bytes = 64 hex characters.
    if not re.fullmatch(r"0x[0-9a-fA-F]{64}", key):
        sys.exit("POLYMARKET_PRIVATE_KEY must be a 64-character hex string (optionally 0x-prefixed).")
    return key


def market_outcomes(market: dict) -> dict:
    """Maps outcome name (lowercased) -> (price, token_id) for a Gamma market."""
    names = json.loads(market.get("outcomes") or "[]")
    prices = json.loads(market.get("outcomePrices") or "[]")
    token_ids = json.loads(market.get("clobTokenIds") or "[]")
    return {
        name.strip().lower(): (float(price), token_id)
        for name, price, token_id in zip(names, prices, token_ids)
    }


def prompt_choice(prompt: str, valid: set) -> str:
    while True:
        choice = input(prompt).strip().lower()
        if choice in valid:
            return choice
        print(f"  Please enter one of: {', '.join(sorted(valid))}")


def prompt_float(prompt: str, min_value: float = None, max_value: float = None) -> float:
    while True:
        raw = input(prompt).strip()
        try:
            value = float(raw)
        except ValueError:
            print("  Please enter a number.")
            continue
        if min_value is not None and value < min_value:
            print(f"  Must be at least {min_value}.")
            continue
        if max_value is not None and value > max_value:
            print(f"  Must be at most {max_value}.")
            continue
        return value


def select_token_interactively(markets: list):
    """Walks the user through each market, asking buy yes/no/skip. Returns (label, token_id, current_price)."""
    for i, market in enumerate(markets, 1):
        outcomes = market_outcomes(market)
        yes, no = outcomes.get("yes"), outcomes.get("no")
        print(f"\n[{i}/{len(markets)}] {market.get('question') or market.get('slug')}")
        if yes:
            print(f"  yes: price={yes[0]}")
        if no:
            print(f"  no : price={no[0]}")

        choice = prompt_choice("  Buy [y]es / [n]o / [s]kip / [q]uit? ", {"y", "n", "s", "q"})
        if choice == "q":
            sys.exit("Cancelled.")
        if choice == "s":
            continue
        if choice == "y" and yes:
            return "YES", yes[1], yes[0]
        if choice == "n" and no:
            return "NO", no[1], no[0]
        print("  That outcome isn't available for this market; skipping.")

    return None, None, None


def resolve_order_amounts(args, token_id: str, current_price: float = None):
    """Returns (price, size, amount) for the chosen mode, prompting for a total money
    budget when it isn't fully specified on the command line.
    """
    if args.mode == "market":
        # Market orders take a dollar amount directly; the API prices it off the
        # current best price, so the user's budget IS the amount — no conversion needed.
        amount = args.amount if args.amount is not None else args.money
        if amount is None:
            amount = prompt_float("Enter total USDC amount to spend: $", min_value=0.01)
        return None, None, amount

    # Limit mode: the user needs a price before a money budget can be turned into shares.
    price = args.price
    if price is None:
        # Local import: avoids a circular import, since order_book.py itself imports from this module.
        from order_book import fetch_order_book, print_order_book

        try:
            print_order_book(fetch_order_book(token_id), depth=5)
        except Exception as e:
            print(f"  (Could not load order book: {e})")

        hint = f" (current price: {current_price})" if current_price is not None else ""
        price = prompt_float(f"Enter your limit price{hint}, between 0 and 1: $", min_value=0.0001, max_value=0.9999)

    size = args.size
    if size is None:
        money = args.money
        if money is None:
            money = prompt_float("Enter total USDC amount to spend: $", min_value=0.01)
        # Shares are whole units; round down so the spend never exceeds the budget.
        size = int(money // price)
        if size < 1:
            sys.exit(f"${money} at a price of {price} buys less than 1 share.")
        print(f"  -> floor({money} / {price}) = {size} shares (${size * price:.2f})")
    return price, size, None


def parse_args():
    parser = argparse.ArgumentParser(description="Buy a Polymarket outcome token at a limit or market price.")
    parser.add_argument("--url", help="A Polymarket bet page link (or bare slug); lets you pick yes/no interactively")
    parser.add_argument(
        "--token-id",
        default=os.environ.get("POLYMARKET_TOKEN_ID", "").strip(),
        help="Outcome token ID to buy directly (or set POLYMARKET_TOKEN_ID). Not needed when using --url.",
    )
    parser.add_argument(
        "--mode",
        choices=["limit", "market"],
        default="limit",
        help="'limit': buy N shares at your own price cap. 'market': spend $X at the best available price.",
    )
    parser.add_argument("--price", type=float, help="Limit price per share, between 0 and 1 (--mode limit)")
    parser.add_argument("--size", type=float, help="Number of shares to buy (--mode limit)")
    parser.add_argument("--amount", type=float, help="USDC amount to spend (--mode market)")
    parser.add_argument(
        "--money",
        type=float,
        help="Total USDC budget to spend; used as --amount (market) or converted to --size via price (limit)"
        " when those aren't given directly. Prompted for interactively if omitted entirely.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be submitted without needing a private key and without posting an order",
    )
    return parser.parse_args()


def resolve_token(args) -> tuple:
    """Returns (label_or_None, token_id, current_price_or_None)."""
    if args.url:
        markets = resolve_markets_by_slug(args.url)
        label, token_id, current_price = select_token_interactively(markets)
        if not token_id:
            sys.exit("No option selected.")
        return label, token_id, current_price

    if args.token_id:
        return None, args.token_id, None

    if args.dry_run:
        print("[DRY RUN] No --url/--token-id given; using a placeholder token ID.")
        return None, DRY_RUN_PLACEHOLDER_TOKEN_ID, None

    sys.exit("A token ID is required: pass --url, --token-id, or set POLYMARKET_TOKEN_ID.")


def print_order_summary(label, token_id, mode, price, size, amount, header="Order summary"):
    print(f"\n{header}:")
    print(f"  token_id : {token_id}" + (f"  ({label})" if label else ""))
    print("  side     : BUY")
    print(f"  mode     : {mode}")
    if mode == "limit":
        print(f"  price    : {price}")
        print(f"  size     : {size}")
        print(f"  total    : ${price * size:.2f}")
    else:
        print(f"  amount   : ${amount:.2f} (total money to spend)")


def main():
    args = parse_args()
    label, token_id, current_price = resolve_token(args)
    price, size, amount = resolve_order_amounts(args, token_id, current_price)

    if args.dry_run:
        print_order_summary(label, token_id, args.mode, price, size, amount, header="[DRY RUN] Would submit")
        return

    print_order_summary(label, token_id, args.mode, price, size, amount)
    if prompt_choice("Confirm and place this order? [y/n] ", {"y", "n"}) != "y":
        sys.exit("Cancelled.")

    private_key = load_private_key()
    client = ClobClient(host=HOST, key=private_key, chain_id=CHAIN_ID)
    client.set_api_creds(client.create_or_derive_api_creds())

    if args.mode == "limit":
        order_args = OrderArgs(price=price, size=size, side=BUY, token_id=token_id)
        signed_order = client.create_order(order_args)
        response = client.post_order(signed_order, OrderType.GTC)
    else:
        # Market order: price=None lets the client price it off the current order book.
        # FOK (fill-or-kill) either fills the whole order immediately or is cancelled.
        order_args = MarketOrderArgs(token_id=token_id, amount=amount, side=BUY)
        signed_order = client.create_market_order(order_args)
        response = client.post_order(signed_order, OrderType.FOK)

    print("Order Response:", response)


if __name__ == "__main__":
    main()
