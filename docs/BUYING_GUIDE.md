# How to Buy a Polymarket Bet with `buy_polymarket.py`

This guide walks through placing a buy order on Polymarket using [buy_polymarket.py](../buy_polymarket.py),
either at a **limit price** (you set the price) or at **market price** (fills immediately at
the best available price).

## 1. Prerequisites

- A Polygon wallet private key that holds USDC (and a small amount of MATIC/POL for gas
  on some actions) and has traded on Polymarket before, or is ready to be onboarded.
- Dependencies installed: `pip install -r requirements.txt`

## 2. Set your private key

The script reads your key from an environment variable — it is never hard-coded in the file.

```bash
export POLYMARKET_PRIVATE_KEY=0xyour64charhexkey
```

Verify it works first with the connection test script:

```bash
python3 test_connection.py
```

You should see `[OK]` for wallet address, API creds, and API keys under the "with key" section.

## 3. Have the bet's page link? Just point the script at it

You don't need to look up a `token_id` yourself. Pass the bet's page URL with `--url` and
`buy_polymarket.py` resolves it and walks you through every outcome interactively:

```bash
python3 buy_polymarket.py --url "https://polymarket.com/event/epl-2027-champion-20260701200428749" --mode market --amount 25
```

For each option it prints the current Yes/No prices and asks:

```
[3/24] Will Bournemouth win the 2026-27 English Premier League (EPL) Championship?
  yes: price=0.0015
  no : price=0.9985
  Buy [y]es / [n]o / [s]kip / [q]uit?
```

- `y` / `n` — buys that outcome immediately using the mode/price/size/amount you passed on
  the command line, and grabs the correct token ID for you.
- `s` — skips to the next option in the event.
- `q` — cancels without buying anything.

This works for:
- Single-market ("Yes"/"No") bet pages — you're asked about that one market.
- Multi-market event pages (e.g. one market per team/candidate) — you're walked through
  each one until you buy or reach the end.

A bare slug (the last path segment of the URL) also works instead of the full link.

## 4. Prefer to browse first, or already have a token ID?

Use [list_bets.py](../list_bets.py) to browse markets without buying:

```bash
python3 list_bets.py --limit 10
```

or resolve a specific link the same way, just to inspect it:

```bash
python3 list_bets.py --url "https://polymarket.com/event/will-there-be-no-change-in-fed-interest-rates-after-the-september-2026-meeting-615"
```

If you already have a `token_id`, skip `--url` entirely and pass it directly (either
`export POLYMARKET_TOKEN_ID=...` or `--token-id <id>` on `buy_polymarket.py`).

## 5. Choose limit or market, and run it

You never have to compute shares yourself — just tell the script how much money you want
to spend with `--money` (or leave it out and it'll ask). It converts that budget into the
right field for whichever mode you pick.

### Option A: Limit order (`--mode limit`, the default)

You pick the price cap; the order only fills at that price or better and can sit unfilled
(`GTC` — good till cancelled) if the market doesn't reach it.

```bash
python3 buy_polymarket.py --url "https://polymarket.com/event/epl-2027-champion-20260701200428749" --mode limit --money 50
```

Since `--price` isn't given, once you pick an outcome you're prompted for your limit price
(with that option's current price shown as a hint), then the size is computed as
`floor(money / price)` — shares are whole units, so the size is rounded down to keep the
spend at or under your budget. What happens with each flag:

- `--price` — your limit price per share (0–1). Optional: pass it directly to skip the
  prompt (useful for scripting), or leave it out to be prompted per-option.
- `--money` — total USDC budget. Size is computed as `floor(money / price)`. If omitted
  (and `--size` isn't given either), you're prompted for it.
- `--size` — set this instead of `--money` if you'd rather specify the exact share count
  directly (not rounded).

### Option B: Market order (`--mode market`)

The script prices it off the live order book and submits as `FOK` (fill-or-kill) — it
either fills immediately in full or is cancelled.

```bash
python3 buy_polymarket.py --mode market --money 50
```

- `--money` (or `--amount`) is the USDC amount you want to spend — for market orders this
  IS the amount sent to the API directly (it resolves the best price for you), no
  conversion needed. If omitted, you're prompted for it.
- No `--price` is needed; you'll get the best price currently available.

If you're using `--url`, the mode/price/size/money flags apply to whichever outcome you
select interactively — no `--token-id` needed. Otherwise, add `--token-id <id>` (or export
`POLYMARKET_TOKEN_ID`).

Before anything is submitted, the script always prints a summary of the exchange:

- **Market mode**: the total USDC amount you're spending.
- **Limit mode**: price, size (shares), and the total cost (`price * size`).

For a **real order** (no `--dry-run`), you're then asked to confirm:

```
Enter your limit price (current price: 0.495), between 0 and 1: $0.52
Enter total USDC amount to spend: $50
  -> floor(50.0 / 0.52) = 96 shares ($49.92)

Order summary:
  token_id : 5615282760875985231868508008056959876238536896643315063916840237042205273721  (YES)
  side     : BUY
  mode     : limit
  price    : 0.52
  size     : 96
  total    : $49.92
Confirm and place this order? [y/n] y
```

Answering anything other than `y` cancels immediately — no private key is loaded and no
order is placed unless you confirm.

On success it prints the order response, including the order ID and status
(e.g. `matched`, `live`, or `delayed`).

## 6. Try it risk-free with `--dry-run`

Add `--dry-run` to preview the same summary, without needing `POLYMARKET_PRIVATE_KEY`,
without posting a real order, and without the confirmation prompt (it's already just a
preview):

```bash
python3 buy_polymarket.py --dry-run --url "https://polymarket.com/event/epl-2027-champion-20260701200428749" --mode limit
```

Since `--price`/`--money` aren't given, you'll be prompted after picking an outcome:

```
[3/24] Will Bournemouth win the 2026-27 English Premier League (EPL) Championship?
  yes: price=0.0015
  no : price=0.9985
  Buy [y]es / [n]o / [s]kip / [q]uit? y
Enter your limit price (current price: 0.0015), between 0 and 1: $0.002
Enter total USDC amount to spend: $10
  -> floor(10.0 / 0.002) = 5000 shares ($10.00)

[DRY RUN] Would submit:
  token_id : 917268...142  (YES)
  side     : BUY
  mode     : limit
  price    : 0.002
  size     : 5000
  total    : $10.00
```

Pass `--price`/`--money`/`--amount`/`--size` on the command line to skip any of these
prompts (useful for scripting).


You can even dry-run with no `--url`/`--token-id` at all — a placeholder token ID is used
just to exercise the argument validation.

## 7. Using a proxy or deposit wallet

If you log into Polymarket with email/Magic-link, or trade through a browser wallet
connected via Polymarket's UI, your funds live in a separate wallet from your raw signer
address. Tell the script which kind of wallet you have with `--signature-type`:

| Wallet | `--signature-type` |
| --- | --- |
| Plain wallet (EOA) | `0` (default) |
| Email/Magic-link login | `1` |
| Browser wallet via Polymarket's Gnosis Safe proxy | `2` |
| Polymarket deposit wallet | `3` |

For anything other than `0`, add the address that actually holds your funds (find it in
Polymarket's account settings) to `config.yaml`:

```yaml
polymarket:
  funder: "0xYourPolymarketDepositWalletAddress"
```

(`POLYMARKET_FUNDER` also works as an env var override.) This isn't a `--flag` since it
rarely changes between runs — set it once in `config.yaml` and just pass `--signature-type`:

```bash
python3 buy_polymarket.py --url "..." --signature-type 3 --mode limit --money 50
```

## Troubleshooting

| Error | Meaning |
| --- | --- |
| `POLYMARKET_PRIVATE_KEY is not set` | Export the env var before running (not needed with `--dry-run`). |
| `...must be a 64-character hex string` | Your key is malformed — check for typos or missing characters. |
| `A token ID is required` | Pass `--url`, `--token-id`, set `POLYMARKET_TOKEN_ID`, or add `--dry-run`. |
| `No option selected.` | You skipped or quit every option in the interactive `--url` walkthrough. |
| `Cancelled.` (after the summary) | You answered anything other than `y` at the confirmation prompt — no order was placed. |
| `maker address not allowed, please use the deposit wallet flow` | Try `--signature-type 3` (see [section 7](#7-using-a-proxy-or-deposit-wallet)) with `polymarket.funder` set in `config.yaml`. |
| 403 / geo-block errors | Run `python3 test_connection.py` — the "without key" test flags if your IP is region-blocked. |
| Insufficient balance/allowance errors | Fund your wallet with USDC and ensure Polymarket allowances are set (this normally happens automatically the first time you trade via the official UI). |

## Safety notes

- This script places a **real order with real funds** — double-check the mode, price/amount,
  size, and token ID before running.
- Market orders execute immediately at the best available price — there's no chance to
  cancel once submitted.
- Never commit your private key or `config.yaml` to source control.
