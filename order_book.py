import argparse
import sys

import requests

from buy_polymarket import market_outcomes, prompt_choice
from list_bets import resolve_markets_by_slug

CLOB_HOST = "https://clob.polymarket.com"


def fetch_order_book(token_id: str) -> dict:
    resp = requests.get(f"{CLOB_HOST}/book", params={"token_id": token_id}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def select_outcome_interactively(markets: list):
    """Walks the user through each market, asking view yes/no/skip. Returns (label, token_id)."""
    for i, market in enumerate(markets, 1):
        outcomes = market_outcomes(market)
        yes, no = outcomes.get("yes"), outcomes.get("no")
        print(f"\n[{i}/{len(markets)}] {market.get('question') or market.get('slug')}")
        if yes:
            print(f"  yes: price={yes[0]}")
        if no:
            print(f"  no : price={no[0]}")

        choice = prompt_choice("  View [y]es / [n]o / [s]kip / [q]uit? ", {"y", "n", "s", "q"})
        if choice == "q":
            sys.exit("Cancelled.")
        if choice == "s":
            continue
        if choice == "y" and yes:
            return "YES", yes[1]
        if choice == "n" and no:
            return "NO", no[1]
        print("  That outcome isn't available for this market; skipping.")

    return None, None


def resolve_token(target: str) -> tuple:
    """Returns (label_or_None, token_id). A long numeric string is treated as a token ID directly."""
    if target.isdigit() and len(target) > 20:
        return None, target

    markets = resolve_markets_by_slug(target)
    label, token_id = select_outcome_interactively(markets)
    if not token_id:
        sys.exit("No option selected.")
    return label, token_id


def format_level(level: dict) -> str:
    price = float(level["price"])
    size = float(level["size"])
    total = price * size
    return f"  {price * 100:>6.1f}\u00a2   {size:>14,.2f}   ${total:>14,.2f}"


def print_order_book(book: dict, depth: int):
    asks = book.get("asks") or []
    bids = book.get("bids") or []

    # asks[] is sorted highest->lowest; the last `depth` entries are the ones closest to the spread.
    top_asks = asks[-depth:]
    # bids[] is sorted lowest->highest; reverse so the best (highest) bid is shown first, near the spread.
    top_bids = list(reversed(bids[-depth:]))

    print(f"{'':>2}{'PRICE':>7}   {'SHARES':>14}   {'TOTAL':>15}")

    print("Asks:")
    for level in top_asks:
        print(format_level(level))

    best_bid = float(top_bids[0]["price"]) if top_bids else None
    best_ask = float(top_asks[-1]["price"]) if top_asks else None
    last_price = book.get("last_trade_price")
    last_str = f"{float(last_price) * 100:.1f}\u00a2" if last_price not in (None, "") else "n/a"
    spread_str = f"{(best_ask - best_bid) * 100:.1f}\u00a2" if best_bid is not None and best_ask is not None else "n/a"
    print(f"Last: {last_str}   Spread: {spread_str}")

    print("Bids:")
    for level in top_bids:
        print(format_level(level))


def main():
    parser = argparse.ArgumentParser(description="Show the top bids/asks for a Polymarket outcome token.")
    parser.add_argument("target", help="A token ID, or a Polymarket bet page URL/slug (opens an interactive picker)")
    parser.add_argument("--depth", type=int, default=5, help="Number of price levels to show per side (default 5)")
    args = parser.parse_args()

    label, token_id = resolve_token(args.target)
    book = fetch_order_book(token_id)

    print(f"\nOrder book for token {token_id}" + (f"  ({label})" if label else ""))
    print_order_book(book, depth=args.depth)


if __name__ == "__main__":
    main()
