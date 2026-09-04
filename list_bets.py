import argparse
import json

import requests

GAMMA_HOST = "https://gamma-api.polymarket.com"


def fetch_markets(limit: int, order: str, active_only: bool, include_closed: bool):
    params = {
        "limit": limit,
        "order": order,
        "ascending": "false",
        "active": "true" if active_only else "false",
        "closed": "true" if include_closed else "false",
    }
    resp = requests.get(f"{GAMMA_HOST}/markets", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def format_market(market: dict) -> str:
    outcomes = json.loads(market.get("outcomes") or "[]")
    prices = json.loads(market.get("outcomePrices") or "[]")
    token_ids = json.loads(market.get("clobTokenIds") or "[]")

    lines = [
        f"Question   : {market.get('question')}",
        f"Slug       : {market.get('slug')}",
        f"Condition  : {market.get('conditionId')}",
        f"Status     : {'closed' if market.get('closed') else 'active'}"
        f", accepting_orders={market.get('acceptingOrders')}",
        f"End date   : {market.get('endDateIso') or market.get('endDate')}",
        f"Volume     : ${market.get('volumeNum', 0):,.2f} (24h: ${market.get('volume24hr', 0):,.2f})",
        f"Liquidity  : ${market.get('liquidityNum', 0):,.2f}",
    ]

    for i, outcome in enumerate(outcomes):
        price = prices[i] if i < len(prices) else "?"
        token_id = token_ids[i] if i < len(token_ids) else "?"
        lines.append(f"  Outcome[{i}]: {outcome!r} price={price} token_id={token_id}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="List known Polymarket bets with detailed info.")
    parser.add_argument("--limit", type=int, default=10, help="Number of markets to list")
    parser.add_argument(
        "--order",
        default="volume24hr",
        help="Field to sort by (e.g. volume24hr, volumeNum, liquidityNum)",
    )
    parser.add_argument("--include-closed", action="store_true", help="Include closed markets")
    parser.add_argument("--all", action="store_true", help="Include inactive markets too")
    args = parser.parse_args()

    markets = fetch_markets(
        limit=args.limit,
        order=args.order,
        active_only=not args.all,
        include_closed=args.include_closed,
    )

    print(f"Found {len(markets)} market(s)\n")
    for market in markets:
        print(format_market(market))
        print("-" * 80)


if __name__ == "__main__":
    main()
