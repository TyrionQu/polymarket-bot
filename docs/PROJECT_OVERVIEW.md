# Polymarket Bot — Project Overview

A collection of small, self-contained Python CLI scripts for interacting with
[Polymarket](https://polymarket.com)'s CLOB (Central Limit Order Book) API and public
Gamma/Data APIs: browsing markets, viewing order books, buying/selling outcome tokens, and
managing open orders and positions.

There is no single "app" entry point — each script is an independent tool you run directly
with `python3 <script>.py`. Scripts import small shared helpers from each other (see
"How the scripts relate" below) but there is no framework or web server involved.

## Quick start

```bash
pip install -r requirements.txt
cp config.yaml.example config.yaml   # fill in your GitHub token if using setup_github_repo.py
python3 test_connection.py           # sanity-check connectivity (works with no key)
```

See [docs/BUYING_GUIDE.md](BUYING_GUIDE.md) for the full walkthrough of buying a bet.

## Scripts

| Script | Purpose |
| --- | --- |
| [`buy_polymarket.py`](../buy_polymarket.py) | Buy an outcome token at a limit or market price. Supports resolving a bet page URL interactively, shows the live order book before you enter a price, computes share size from a USDC budget, and supports `--dry-run`. |
| [`list_bets.py`](../list_bets.py) | Browse/list Polymarket markets (public Gamma API), or resolve a bet page URL/slug straight to its outcome token IDs. |
| [`order_book.py`](../order_book.py) | Print the top N bids/asks for a token ID or bet URL. |
| [`list_open_orders.py`](../list_open_orders.py) | List your unfilled orders and currently-held (not-yet-resolved) positions; interactively cancel an order or sell a position. |
| [`test_connection.py`](../test_connection.py) | Verify connectivity: public endpoints (health, geo-block) always run; authenticated endpoint checks run if a key is configured. |
| [`encrypt_key.py`](../encrypt_key.py) | Encrypts your Polygon private key (AES-256-GCM, password-derived key) into a base64 blob to store in `config.yaml`, so the raw key is never stored on disk. |
| [`key_crypto.py`](../key_crypto.py) | Shared AES-256-GCM encrypt/decrypt + private-key-format validation, used by `encrypt_key.py` and `buy_polymarket.py`. |
| [`masked_input.py`](../masked_input.py) | Reads one line of input echoing `*` per character (used when entering the private key). |
| [`setup_github_repo.py`](../setup_github_repo.py) | One-time utility: verifies the GitHub token in `config.yaml` and publishes this project to a new GitHub repo (never includes `config.yaml`). |
| [`testcases/`](../testcases/) | Ad hoc test scripts exercising interactive flows (e.g. `list_open_orders.py`'s cancel/sell prompts) with fake data/clients. |

## How the scripts relate

There's no central "core" module — instead, small generic helpers are imported directly
between scripts to avoid duplicating logic:

- `list_bets.py` owns `resolve_markets_by_slug()` (Gamma API market/event resolution by
  URL or slug) — imported by `buy_polymarket.py` and `order_book.py`.
- `buy_polymarket.py` owns shared interactive-prompt helpers (`prompt_choice`,
  `prompt_float`), `show_order_book()`, private-key loading (`load_private_key`), and
  `config.yaml` reading (`load_polymarket_config`) — imported by `order_book.py` and
  `list_open_orders.py`.
- `order_book.py` owns `fetch_order_book()`/`print_order_book()` — imported (via a
  function-local import, to avoid a circular import) by `buy_polymarket.py`.
- `key_crypto.py` and `masked_input.py` are leaf modules with no repo-internal imports.

## Configuration (`config.yaml`)

`config.yaml` is git-ignored — never commit it. See [`config.yaml.example`](../config.yaml.example)
for the full template. Fields used:

```yaml
github:
  token: ghp_...                 # used only by setup_github_repo.py

polymarket:
  encrypted_private_key: "..."   # output of encrypt_key.py; decrypted at runtime with a password prompt
  funder: "0x..."                # your Polymarket deposit/proxy wallet address (see signature types below)
```

## Environment variables

All scripts also accept plain environment variables as an alternative to `config.yaml`,
useful for scripting/automation:

| Variable | Used for |
| --- | --- |
| `POLYMARKET_PRIVATE_KEY` | Fallback when `polymarket.encrypted_private_key` isn't set in `config.yaml`. |
| `POLYMARKET_TOKEN_ID` | Default `--token-id` for `buy_polymarket.py`. |
| `POLYMARKET_SIGNATURE_TYPE` | Default `--signature-type` (0=EOA, 1=Proxy/email, 2=Gnosis Safe, 3=Deposit Wallet). |
| `POLYMARKET_FUNDER` | Default deposit/proxy wallet address (fallback for `polymarket.funder`). |

## Security model

- Private keys are never hard-coded or logged. They're loaded from `config.yaml`
  (AES-256-GCM encrypted, password-protected) or an environment variable, held only in
  memory for the duration of a script run.
- `config.yaml` is git-ignored; `config.yaml.example` is the committed template with no
  real secrets.
- GitHub tokens are only ever passed to git via a throwaway `GIT_ASKPASS` helper — never
  written into `.git/config` or passed as a CLI argument.
- All trading scripts default to `--dry-run`-friendly behavior and require an explicit
  `[y/n]` confirmation before submitting a real order or cancellation.

## For AI coding agents

If you (an AI agent) are extending this repo, see [`.github/copilot-instructions.md`](../.github/copilot-instructions.md)
for the required conventions — in short: **write a test case under `testcases/` and update/add
a doc under `docs/` for every new script or non-trivial function you add.**
