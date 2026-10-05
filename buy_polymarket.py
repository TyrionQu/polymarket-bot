import argparse
import getpass
import json
import os
import sys

import requests
import yaml

from key_crypto import decrypt_private_key, normalize_private_key, verify_private_key
from list_bets import resolve_markets_by_slug

# --- Configurations ---
HOST = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon Mainnet
DRY_RUN_PLACEHOLDER_TOKEN_ID = "0" * 64
CONFIG_PATH = "config.yaml"

# Polymarket's collateral is USDC.e on Polygon; balanceOf it over a public RPC to size bets.
USDC_CONTRACT = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
DEFAULT_RPC_URL = "https://polygon.drpc.org"
DEFAULT_KELLY_FRACTION = 0.5  # half Kelly: lower variance than full Kelly


def load_polymarket_config(config_path: str = CONFIG_PATH) -> dict:
    if not os.path.exists(config_path):
        return {}
    with open(config_path) as f:
        config = yaml.safe_load(f) or {}
    return config.get("polymarket") or {}


def load_encrypted_private_key(config_path: str = CONFIG_PATH):
    return (load_polymarket_config(config_path).get("encrypted_private_key") or "").strip() or None


def load_private_key() -> str:
    encrypted = load_encrypted_private_key()
    if encrypted:
        password = getpass.getpass("Enter password to decrypt your private key: ")
        try:
            key = decrypt_private_key(encrypted, password)
        except ValueError as e:
            sys.exit(str(e))
        if not verify_private_key(key):
            sys.exit("Decrypted value is not a valid private key.")
        return normalize_private_key(key)

    # Fall back to the environment variable (kept for scripting/automation).
    key = os.environ.get("POLYMARKET_PRIVATE_KEY", "").strip()
    if not key:
        sys.exit(
            "No key found: add polymarket.encrypted_private_key to config.yaml (see encrypt_key.py)"
            " or set POLYMARKET_PRIVATE_KEY."
        )
    if not verify_private_key(key):
        sys.exit("POLYMARKET_PRIVATE_KEY must be a 64-character hex string (optionally 0x-prefixed).")
    return normalize_private_key(key)


def market_outcomes(market: dict) -> dict:
    """Maps outcome name (lowercased) -> (price, token_id) for a Gamma market."""
    names = json.loads(market.get("outcomes") or "[]")
    prices = json.loads(market.get("outcomePrices") or "[]")
    token_ids = json.loads(market.get("clobTokenIds") or "[]")
    return {
        name.strip().lower(): (float(price), token_id)
        for name, price, token_id in zip(names, prices, token_ids)
    }


def is_tradeable(market: dict) -> bool:
    """True when a market is still open for orders with a live CLOB book.

    Resolved/closed markets have no order book (their /book endpoint 404s) and their
    prices are pinned to 0/1, so they should never be offered as a buy option.
    """
    return (
        not market.get("closed")
        and bool(market.get("acceptingOrders"))
        and bool(market.get("enableOrderBook"))
    )


def prompt_choice(prompt: str, valid: set, default: str = None) -> str:
    while True:
        choice = input(prompt).strip().lower()
        if not choice and default is not None:
            return default
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


def show_order_book(token_id: str):
    # Local import: avoids a circular import, since order_book.py itself imports from this module.
    from order_book import fetch_order_book, print_order_book

    try:
        print_order_book(fetch_order_book(token_id), depth=5)
    except Exception as e:
        print(f"  (Could not load order book: {e})")


def select_token_interactively(markets: list, args):
    """Walks the user through each market, asking buy yes/no/skip. Returns (label, token_id, current_price).

    After picking yes/no, the user can still back out with [r]eturn to re-pick for the
    same market instead of committing to an amount.
    """
    tradeable = [m for m in markets if is_tradeable(m)]
    skipped = len(markets) - len(tradeable)
    if skipped:
        print(f"  (Skipping {skipped} resolved/closed market(s) that can't be traded.)")
    if not tradeable:
        sys.exit("No tradeable markets found for this bet (all resolved or closed).")

    for i, market in enumerate(tradeable, 1):
        outcomes = market_outcomes(market)
        yes, no = outcomes.get("yes"), outcomes.get("no")
        # Pressing Enter skips to the next option, or quits on the last one.
        default = "q" if i == len(tradeable) else "s"

        while True:
            print(f"\n[{i}/{len(tradeable)}] {market.get('question') or market.get('slug')}")
            if yes:
                print(f"  yes: price={yes[0]}")
            if no:
                print(f"  no : price={no[0]}")

            choice = prompt_choice(
                f"  Buy [y]es / [n]o / [s]kip / [q]uit? (Enter = {'quit' if default == 'q' else 'skip'}) ",
                {"y", "n", "s", "q"},
                default=default,
            )
            if choice == "q":
                sys.exit("Cancelled.")
            if choice == "s":
                break
            if choice == "y" and yes:
                label, token_id, current_price = "YES", yes[1], yes[0]
            elif choice == "n" and no:
                label, token_id, current_price = "NO", no[1], no[0]
            else:
                print("  That outcome isn't available for this market; skipping.")
                continue

            decision = prompt_choice("  [r]eturn to outcome selection or [e]nter amount? ", {"r", "e"})
            if decision == "r":
                continue
            return label, token_id, current_price

    return None, None, None


def kelly_fraction(price: float, win_prob: float) -> float:
    """Full-Kelly fraction of bankroll to stake on a $1-payout token bought at ``price``.

    For a token that pays $1 on win and $0 on loss, f* = (p - price) / (1 - price).
    Returns 0 when there's no edge (your estimate p is not above the market price).
    """
    if not 0 < price < 1:
        return 0.0
    return max(0.0, (win_prob - price) / (1 - price))


def kelly_stake(bankroll: float, price: float, win_prob: float, fraction: float) -> float:
    """Suggested USDC stake = fraction * full-Kelly * bankroll (0 when there's no edge)."""
    return fraction * kelly_fraction(price, win_prob) * bankroll


def get_usdc_balance(address: str, rpc_url: str = DEFAULT_RPC_URL) -> float:
    """Reads an address's USDC.e (Polymarket collateral) balance via a public Polygon RPC."""
    # balanceOf(address): selector 0x70a08231 followed by the 32-byte left-padded address.
    data = "0x70a08231" + address.lower().removeprefix("0x").rjust(64, "0")
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [{"to": USDC_CONTRACT, "data": data}, "latest"],
    }
    resp = requests.post(rpc_url, json=payload, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    if result.get("error"):
        raise RuntimeError(result["error"].get("message", "RPC error"))
    return int(result["result"], 16) / 1_000_000  # USDC has 6 decimals


def resolve_balance_address(args, client=None):
    """The address whose USDC balance funds the bet: the funder/proxy if configured,
    an explicit --address, or the EOA signing address derived by the client."""
    if args.funder:
        return args.funder
    if args.address:
        return args.address
    if client is not None:
        try:
            return client.get_address()
        except Exception:
            return None
    return None


def fetch_collateral_balance(client):
    """The wallet's USDC collateral balance as tracked by the CLOB exchange (dollars),
    or None if it can't be fetched. This is what you can actually trade with (and matches
    list_open_orders.py); a raw ERC20 balanceOf misses proxy/deposit-wallet collateral.
    """
    from py_clob_client_v2 import AssetType, BalanceAllowanceParams

    try:
        result = client.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
        # Collateral balance is returned in 6-decimal base units (1 USDC = 1_000_000).
        return int(result["balance"]) / 1_000_000
    except Exception as e:
        print(f"  (Could not fetch wallet balance: {e})")
        return None


def resolve_bankroll(args, client=None) -> float:
    """Returns the Kelly bankroll. Prefers the CLOB-tracked collateral balance (what you can
    actually trade with); falls back to an on-chain balanceOf (dry-run) or a manual prompt."""
    if client is not None:
        balance = fetch_collateral_balance(client)
        if balance is not None:
            print(f"  Bankroll: ${balance:.2f} USDC (Polymarket collateral)")
            return balance

    address = resolve_balance_address(args, client)
    if address:
        try:
            balance = get_usdc_balance(address, args.rpc_url)
            print(f"  Bankroll: ${balance:.2f} USDC  [{address}]")
            return balance
        except Exception as e:
            print(f"  (Could not read wallet balance: {e})")
    bankroll = prompt_float(
        "Enter your bankroll (total USDC to size the bet against, 0 to exit): $", min_value=0.0
    )
    if bankroll == 0:
        sys.exit("Exiting (no bankroll entered).")
    return bankroll


def resolve_stake(args, token_id: str, current_price: float, client=None):
    """Returns (price, size, info): the limit buy price, the number of whole shares to buy
    at that price, and the Kelly inputs for the summary (info is None when an explicit
    --amount/--money override skips Kelly).

    Shows the top-5 bids/asks, then asks for your buy price; the Kelly suggestion is
    (re)computed from whatever price you enter, so you can re-quote until you're happy. The
    dollar stake is converted to shares via floor(stake / price), so you never overpay.
    """
    # Show the top-of-book so the user can choose a realistic buy price.
    show_order_book(token_id)

    hint = f" (current {current_price})" if current_price is not None else ""
    win_prob = args.win_prob
    bankroll = None
    override = args.amount if args.amount is not None else args.money
    while True:
        price = prompt_float(
            f"Enter your buy price{hint}, between 0 and 1 (0 to refresh the order book): $",
            min_value=0.0,
            max_value=1.0,
        )
        if price == 0:
            show_order_book(token_id)
            continue
        if not 0.0001 <= price <= 0.9999:
            print("  Enter a price between 0.0001 and 0.9999.")
            continue

        if override is not None:
            amount, info = override, None
        else:
            if win_prob is None:
                win_prob = prompt_float("  Your estimated chance this wins (0-1): ", min_value=0.0, max_value=1.0)

            frac = kelly_fraction(price, win_prob)
            if frac <= 0:
                print(
                    f"  No edge: your estimate ({win_prob:.4f}) is not above your buy price"
                    f" ({price:.4f}); Kelly recommends NOT betting."
                )
                decision = prompt_choice("  [r]e-enter price / [m]anual amount / [q]uit? ", {"r", "m", "q"})
                if decision == "r":
                    continue
                if decision == "q":
                    sys.exit("Cancelled (no edge).")
                amount, info = prompt_float("Enter total USDC amount to spend: $", min_value=0.01), None
            else:
                if bankroll is None:
                    bankroll = resolve_bankroll(args, client)
                suggested = round(kelly_stake(bankroll, price, win_prob, args.kelly_fraction), 2)
                print(
                    f"  Kelly edge f*={frac:.4f}; {args.kelly_fraction:g}x Kelly on ${bankroll:.2f}"
                    f" -> suggested stake ${suggested:.2f}"
                )
                choice = prompt_choice(
                    f"  [a]ccept ${suggested:.2f} / [c]ustom amount / [r]e-enter price / [q]uit? ",
                    {"a", "c", "r", "q"},
                )
                if choice == "q":
                    sys.exit("Cancelled.")
                if choice == "r":
                    continue
                if choice == "c":
                    amount = prompt_float("Enter total USDC amount to spend: $", min_value=0.01)
                else:
                    amount = suggested
                info = {"price": price, "win_prob": win_prob, "bankroll": bankroll, "fraction": args.kelly_fraction}

        # Shares are whole units; floor so the spend never exceeds the dollar stake.
        size = int(amount // price)
        if size < 1:
            print(f"  ${amount:.2f} at {price:.4f} buys less than 1 share; use a larger amount or a lower price.")
            continue
        print(f"  -> {size} shares at {price:.4f} = ${size * price:.2f}")
        if info is not None:
            info["size"] = size
        return price, size, info


def parse_args():
    parser = argparse.ArgumentParser(
        description="Buy a Polymarket outcome token, sizing the stake with the Kelly criterion."
    )
    parser.add_argument("--url", help="A Polymarket bet page link (or bare slug); lets you pick yes/no interactively")
    parser.add_argument(
        "--token-id",
        default=os.environ.get("POLYMARKET_TOKEN_ID", "").strip(),
        help="Outcome token ID to buy directly (or set POLYMARKET_TOKEN_ID). Not needed when using --url.",
    )
    parser.add_argument(
        "--win-prob",
        type=float,
        help="Your estimated probability (0-1) that the outcome wins; prompted for if omitted."
        " Drives the Kelly stake suggestion.",
    )
    parser.add_argument(
        "--kelly-fraction",
        type=float,
        default=DEFAULT_KELLY_FRACTION,
        help=f"Fraction of full Kelly to stake (default {DEFAULT_KELLY_FRACTION} = half Kelly).",
    )
    parser.add_argument("--amount", type=float, help="USDC amount to spend; overrides the Kelly suggestion when given.")
    parser.add_argument("--money", type=float, help="Alias for --amount; overrides the Kelly suggestion when given.")
    parser.add_argument(
        "--address",
        default=os.environ.get("POLYMARKET_ADDRESS", "").strip() or None,
        help="Wallet address to read the USDC bankroll from (defaults to your funder, or your EOA signing address).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be submitted without needing a private key and without posting an order",
    )
    parser.add_argument(
        "--signature-type",
        type=int,
        default=int(os.environ.get("POLYMARKET_SIGNATURE_TYPE", "0")),
        help="Wallet type: 0=EOA/plain wallet (default), 1=email/Magic proxy wallet, 2=browser wallet via Polymarket's"
        " Gnosis Safe proxy, 3=Polymarket deposit wallet. If you see 'maker address not allowed, please use the"
        " deposit wallet flow', use --signature-type 3. (or set POLYMARKET_SIGNATURE_TYPE)",
    )
    args = parser.parse_args()

    if args.kelly_fraction <= 0:
        sys.exit("--kelly-fraction must be greater than 0.")

    config = load_polymarket_config()

    # Public Polygon RPC used to read the wallet's USDC balance (the Kelly bankroll).
    args.rpc_url = (
        os.environ.get("POLYMARKET_RPC_URL", "").strip() or (config.get("rpc_url") or "").strip() or DEFAULT_RPC_URL
    )

    # Deposit/proxy wallet address: not a CLI flag, since it rarely changes between runs.
    args.funder = (
        os.environ.get("POLYMARKET_FUNDER", "").strip() or (config.get("funder") or "").strip()
    ) or None
    if args.signature_type != 0 and not args.funder:
        sys.exit(
            "--signature-type other than 0 requires a funder address: set POLYMARKET_FUNDER or"
            " polymarket.funder in config.yaml (your Polymarket deposit/proxy wallet address)."
        )
    return args


def resolve_token(args) -> tuple:
    """Returns (label_or_None, token_id, current_price_or_None)."""
    if args.url:
        markets = resolve_markets_by_slug(args.url)
        label, token_id, current_price = select_token_interactively(markets, args)
        if not token_id:
            sys.exit("No option selected.")
        return label, token_id, current_price

    if args.token_id:
        return None, args.token_id, None

    if args.dry_run:
        print("[DRY RUN] No --url/--token-id given; using a placeholder token ID.")
        return None, DRY_RUN_PLACEHOLDER_TOKEN_ID, None

    sys.exit("A token ID is required: pass --url, --token-id, or set POLYMARKET_TOKEN_ID.")


def print_order_summary(label, token_id, price, size, info=None, header="Order summary"):
    print(f"\n{header}:")
    print(f"  token_id : {token_id}" + (f"  ({label})" if label else ""))
    print("  side     : BUY")
    print("  type     : limit (GTC)")
    print(f"  price    : {price:.4f} (your buy price)")
    print(f"  size     : {size} shares")
    print(f"  total    : ${size * price:.2f}")
    if info:
        print(f"  your p   : {info['win_prob']:.4f}")
        print(f"  bankroll : ${info['bankroll']:.2f}")
        print(f"  kelly    : {info['fraction']:g}x")


def build_client(args):
    """Loads the private key and returns an authenticated CLOB client."""
    from py_clob_client_v2 import ClobClient

    client = ClobClient(
        host=HOST,
        key=load_private_key(),
        chain_id=CHAIN_ID,
        signature_type=args.signature_type,
        funder=args.funder,
    )
    client.set_api_creds(client.create_or_derive_api_key())
    return client


def place_limit_order(client, token_id: str, price: float, size: int):
    """Submits a GTC limit BUY for ``size`` shares at ``price`` (fills at that price or
    better, and rests on the book if it can't fill immediately)."""
    from py_clob_client_v2 import OrderArgs, OrderType
    from py_clob_client_v2.order_builder.constants import BUY

    order_args = OrderArgs(price=price, size=size, side=BUY, token_id=token_id)
    signed_order = client.create_order(order_args)
    return client.post_order(signed_order, OrderType.GTC)


def main():
    args = parse_args()
    label, token_id, current_price = resolve_token(args)

    # EOA wallets derive their balance address from the key, so build the client up front
    # (one password prompt) and reuse it for both the bankroll lookup and the order.
    client = None if args.dry_run else build_client(args)

    price, size, info = resolve_stake(args, token_id, current_price, client)

    if args.dry_run:
        print_order_summary(label, token_id, price, size, info, header="[DRY RUN] Would submit")
        return

    print_order_summary(label, token_id, price, size, info)
    if prompt_choice("Confirm and place this order? [y/n] ", {"y", "n"}) != "y":
        sys.exit("Cancelled.")

    response = place_limit_order(client, token_id, price, size)
    print("Order Response:", response)


if __name__ == "__main__":
    main()
