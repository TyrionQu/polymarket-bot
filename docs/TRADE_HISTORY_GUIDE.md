# Listing Your Trade History with `list_trade_history.py`

[list_trade_history.py](../list_trade_history.py) prints your **filled trades** (completed
buys and sells) for the wallet configured in `config.yaml`. It reads from Polymarket's
public [data-api](https://data-api.polymarket.com) `/trades` endpoint, so no CLOB
authentication is needed — only your wallet **address** is required.

For an EOA wallet (`--signature-type 0`, the default) that address is derived from your
private key, so the script prompts to decrypt it. For a proxy/deposit wallet the address is
the `funder` from your config, and no key is loaded at all. You can also pass `--address`
to inspect any wallet without a key.

> This script is **read-only** — it never places or cancels anything, so there's no
> `--dry-run` or confirmation prompt.

## 1. Prerequisites

- Dependencies installed: `pip install -r requirements.txt`
- One of the following so the script knows which wallet to look up:
  - `polymarket.encrypted_private_key` in `config.yaml` (see [encrypt_key.py](../encrypt_key.py)),
    or the `POLYMARKET_PRIVATE_KEY` env var — for an EOA wallet.
  - `polymarket.funder` in `config.yaml` (or `POLYMARKET_FUNDER`) — for a proxy/deposit
    wallet used with `--signature-type 1/2/3`.
  - Or nothing at all, if you pass `--address`.

## 2. Basic usage

List your most recent trades (EOA wallet; prompts for your key password):

```bash
python3 list_trade_history.py
```

Each trade is printed like this:

```
Question : Will Shakhtar Donetsk win the 2026-27 UEFA Champions League Championship?
Side     : BUY   Outcome: Yes
Price    : 0.002
Size     : 5.0 shares
Total    : $0.01
Time     : 2026-09-30 14:32 UTC
Tx       : 0xcf5fa3489caca51abb1e12ef9db43a5bb44ec91048800ba417e31c1d0d5acc01
```

## 3. Options

| Flag | Default | Purpose |
| --- | --- | --- |
| `--signature-type` | `0` (or `POLYMARKET_SIGNATURE_TYPE`) | Wallet type: 0=EOA, 1=email/Magic proxy, 2=browser/Gnosis Safe proxy, 3=deposit wallet. Non-zero types read the address from `funder`. |
| `--address` | — | List trades for this wallet address instead of the configured one. Skips the key prompt entirely. |
| `--limit` | `50` | Maximum number of trades to fetch. |
| `--offset` | `0` | Number of trades to skip, for paging through older history. |
| `--side` | — | Only show `BUY` or `SELL` trades. |

Examples:

```bash
# Look up another wallet, no key needed
python3 list_trade_history.py --address 0xc69bd5567b40ef4d11922eaa57e1f9be1c642076 --limit 20

# Only your sells, skipping the 50 most recent trades (a deposit wallet)
python3 list_trade_history.py --signature-type 3 --side SELL --offset 50
```

## 4. Troubleshooting

| Symptom | Likely cause / fix |
| --- | --- |
| `No trade history found for address ...` | That wallet has no trades, or you're looking at the wrong address (check `--signature-type` / `funder`). |
| `--signature-type N needs a funder address` | You selected a proxy/deposit wallet but didn't set `polymarket.funder` (or `POLYMARKET_FUNDER`). |
| Prompted for a key password you didn't expect | You're on the default `--signature-type 0`; pass `--address` or set a `funder` + `--signature-type` to avoid loading the key. |
| `No key found ...` | EOA lookup with no `encrypted_private_key` in `config.yaml` and no `POLYMARKET_PRIVATE_KEY`. Add one, or use `--address`. |
| Empty `Question` line | The data-api returned a trade with no title/slug; the raw condition/asset id is shown instead. |
