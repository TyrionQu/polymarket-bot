import argparse
import os
from datetime import datetime, timezone

import requests
from py_clob_client_v2 import ClobClient

from buy_polymarket import CHAIN_ID, HOST, load_polymarket_config, load_private_key

DATA_HOST = "https://data-api.polymarket.com"


def fetch_trades(address: str, limit: int, offset: int = 0, side: str = None) -> list:
    """Filled trades for a wallet, via the public data-api (no CLOB auth needed)."""
    params = {"user": address, "limit": limit, "offset": offset}
    if side:
        params["side"] = side
    resp = requests.get(f"{DATA_HOST}/trades", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def format_trade(trade: dict) -> str:
    size = float(trade.get("size", 0))
    price = float(trade.get("price", 0))

    when = ""
    ts = trade.get("timestamp")
    if ts:
        try:
            when = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        except (ValueError, TypeError):
            when = str(ts)

    # Older/edge trades sometimes come back with an empty title; fall back to slug then ids.
    question = trade.get("title") or trade.get("slug") or trade.get("conditionId") or trade.get("asset")

    return "\n".join([
        f"Question : {question}",
        f"Side     : {trade.get('side')}   Outcome: {trade.get('outcome') or '?'}",
        f"Price    : {price}",
        f"Size     : {size} shares",
        f"Total    : ${price * size:.2f}",
        f"Time     : {when}",
        f"Tx       : {trade.get('transactionHash', '')}",
    ])


def resolve_address(args) -> str:
    """The wallet whose trades to list: an explicit --address, else derived from the key/funder."""
    if args.address:
        return args.address

    funder = (
        os.environ.get("POLYMARKET_FUNDER", "").strip() or (load_polymarket_config().get("funder") or "").strip()
    ) or None

    # Non-EOA wallets (email/browser/deposit) trade under the funder address; an EOA's
    # address is derived from its private key, so only that path needs to load the key.
    if args.signature_type != 0:
        if not funder:
            raise SystemExit(
                f"--signature-type {args.signature_type} needs a funder address"
                " (set polymarket.funder in config.yaml or POLYMARKET_FUNDER)."
            )
        return funder

    private_key = load_private_key()
    client = ClobClient(
        host=HOST,
        key=private_key,
        chain_id=CHAIN_ID,
        signature_type=args.signature_type,
        funder=funder,
    )
    return client.get_address()


def main():
    parser = argparse.ArgumentParser(
        description="List your Polymarket trade history (filled trades) for the wallet configured in config.yaml."
    )
    parser.add_argument(
        "--signature-type",
        type=int,
        default=int(os.environ.get("POLYMARKET_SIGNATURE_TYPE", "0")),
        help="Wallet type: 0=EOA (default), 1=email/Magic proxy, 2=browser/Gnosis Safe proxy, 3=deposit wallet.",
    )
    parser.add_argument(
        "--address",
        help="List trades for this wallet address instead of the one from config.yaml (skips the key prompt).",
    )
    parser.add_argument("--limit", type=int, default=50, help="Max number of trades to fetch")
    parser.add_argument("--offset", type=int, default=0, help="Number of trades to skip (for pagination)")
    parser.add_argument("--side", choices=["BUY", "SELL"], help="Only show BUY or SELL trades")
    args = parser.parse_args()

    address = resolve_address(args)

    trades = fetch_trades(address, limit=args.limit, offset=args.offset, side=args.side)
    if not trades:
        print(f"No trade history found for address {address}.")
        return

    print(f"Found {len(trades)} trade(s) for address {address}\n")
    for trade in trades:
        print(format_trade(trade))
        print("-" * 80)


if __name__ == "__main__":
    main()
