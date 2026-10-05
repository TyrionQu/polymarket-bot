# How to Buy a Polymarket Bet with `buy_polymarket.py`

This guide walks through placing a buy order on Polymarket using [buy_polymarket.py](../buy_polymarket.py).
You enter the **buy price** you're willing to pay and the script places a **limit order** at that
price, sizing the stake for you with the **Kelly criterion** — you supply your own estimate of
the outcome's true win chance, and it suggests how much of your wallet to bet (then converts that
dollar stake into whole shares at your price).

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
python3 buy_polymarket.py --url "https://polymarket.com/event/epl-2027-champion-20260701200428749"
```

For each option it prints the current Yes/No prices and asks:

```
[3/24] Will Bournemouth win the 2026-27 English Premier League (EPL) Championship?
  yes: price=0.0015
  no : price=0.9985
  Buy [y]es / [n]o / [s]kip / [q]uit? (Enter = skip)
```

- `y` / `n` — selects that outcome (grabbing the correct token ID for you) and moves on to the
  Kelly sizing step (see [section 5](#5-let-kelly-size-your-bet)).
- `s` — skips to the next option in the event.
- `q` — cancels without buying anything.
- **Enter** (empty input) — defaults to `s` (skip) so you can tab through options quickly; on
  the **last** option it defaults to `q` (quit) instead.

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

## 5. Let Kelly size your bet

You don't pick a share count or a dollar amount up front. After you choose an outcome, the
script prints the **top-5 bids/asks** (the live order book), asks you to **enter the price you
want to evaluate**, reads your **wallet's USDC balance** as your bankroll, and suggests a stake
using the Kelly criterion. Enter a different price and the suggestion is **recomputed**, so you
can re-quote until you're happy (enter `0` at the price prompt to refresh the order book).

For a token that pays \$1 if it wins and \$0 if it loses, bought at price `P`, with your
estimated win probability `p`, the full-Kelly fraction of your bankroll is:

```
f* = (p - P) / (1 - P)
```

The script stakes a **fraction** of that (half-Kelly, `0.5`, by default \u2014 lower variance than
full Kelly), so the suggested amount is `kelly_fraction * f* * bankroll`. Because `P` is the
price you'd pay (the market's implied probability), Kelly only suggests a positive bet when your
estimate `p` is **higher** than that price (i.e. you believe you have an edge).

```bash
python3 buy_polymarket.py --url "https://polymarket.com/event/epl-2027-champion-20260701200428749"
```

A typical run after you pick an outcome:

```
   PRICE            SHARES             TOTAL
Asks:
   41.0¢         1,200.00        $    492.00
   40.5¢         3,400.00        $  1,377.00
Last: 40.0¢   Spread: 1.0¢
Bids:
   39.5¢         2,100.00        $    829.50
   39.0¢         5,000.00        $  1,950.00
Enter your buy price (current 0.4), between 0 and 1 (0 to refresh the order book): $0.40
  Your estimated chance this wins (0-1): 0.55
  Bankroll: $200.00 USDC (Polymarket collateral)
  Kelly edge f*=0.2500; 0.5x Kelly on $200.00 -> suggested stake $25.00
  [a]ccept $25.00 / [c]ustom amount / [r]e-enter price / [q]uit? a
  -> 62 shares at 0.4000 = $24.80

Order summary:
  token_id : 5615282760875985231868508008056959876238536896643315063916840237042205273721  (YES)
  side     : BUY
  type     : limit (GTC)
  price    : 0.4000 (your buy price)
  size     : 62 shares
  total    : $24.80
  your p   : 0.5500
  bankroll : $200.00
  kelly    : 0.5x
Confirm and place this order? [y/n] y
```

Flags that tune or skip the Kelly flow:

- `--win-prob` \u2014 your estimated win probability (0\u20131). Pass it to skip the prompt; omit it to
  be asked after you enter the price.
- `--kelly-fraction` — fraction of full Kelly to stake (default `0.5`). Use `1` for full Kelly
  (higher growth, higher variance) or a smaller number to be more conservative.
- `--amount` / `--money` — a fixed USDC amount to spend. Passing either **overrides the Kelly
  stake** (no probability prompt, no balance lookup); you still enter a buy price, and it buys
  `floor(amount / price)` shares at that price.
- `--address` \u2014 the wallet address whose USDC balance is read as the bankroll. Defaults to your
  `funder` (proxy/deposit wallets) or your EOA signing address. Handy with `--dry-run`.

**Where the bankroll comes from:** for a real run the script reads your **Polymarket collateral
balance** (the USDC the exchange lets you trade with — the same number `list_open_orders.py`
shows), via the authenticated CLOB client. You'll be asked for your decryption password up front
(one prompt, reused to place the order). In `--dry-run` there's no client, so it falls back to an
on-chain USDC `balanceOf` over a public RPC (`POLYMARKET_RPC_URL`) when a wallet address is known,
otherwise it prompts for a bankroll. Note a raw `balanceOf` can read `$0` for proxy/deposit
wallets even when you have funds, because the collateral isn't held as plain USDC in that address.

**No edge?** If your estimate isn't above the price you entered, `f*` is ≤ 0 and Kelly
recommends **not** betting. The script says so and lets you re-enter a different price, type a
manual amount anyway, or quit:

```
Enter your buy price, between 0 and 1 (0 to refresh the order book): $0.60
  Your estimated chance this wins (0-1): 0.55
  No edge: your estimate (0.5500) is not above your buy price (0.6000); Kelly recommends NOT betting.
  [r]e-enter price / [m]anual amount / [q]uit? q
Cancelled (no edge).
```

Answering anything other than `y` at the final confirmation cancels immediately \u2014 no private
key is loaded and no order is placed unless you confirm. On success it prints the order
response, including the order ID and status (e.g. `matched`, `live`, or `delayed`).

## 6. Try it risk-free with `--dry-run`

Add `--dry-run` to preview the same summary without needing `POLYMARKET_PRIVATE_KEY`, without
posting a real order, and without the confirmation prompt (it's already just a preview). In
dry-run the private key isn't required; if a wallet address is known (via `--address` or your
`funder`) the real balance is still fetched, otherwise you're prompted to type a bankroll
number so the math can be demonstrated:

```bash
python3 buy_polymarket.py --dry-run --token-id 917268...142 --address 0xYourWallet... --win-prob 0.55
```

```
Enter your buy price, between 0 and 1 (0 to refresh the order book): $0.40
  Bankroll: $200.00 USDC  [0xYourWallet...]
  Kelly edge f*=0.2500; 0.5x Kelly on $200.00 -> suggested stake $25.00
  [a]ccept $25.00 / [c]ustom amount / [r]e-enter price / [q]uit? a
  -> 62 shares at 0.4000 = $24.80

[DRY RUN] Would submit:
  token_id : 917268...142
  side     : BUY
  type     : limit (GTC)
  price    : 0.4000 (your buy price)
  size     : 62 shares
  total    : $24.80
  your p   : 0.5500
  bankroll : $200.00
  kelly    : 0.5x
```

You can also skip Kelly in a dry-run with a fixed amount (no network, no prompts):

```bash
python3 buy_polymarket.py --dry-run --token-id 917268...142 --amount 10
```

You can even dry-run with no `--url`/`--token-id` at all \u2014 a placeholder token ID is used
just to exercise the argument validation (pair it with `--amount` to skip the price lookup).

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
python3 buy_polymarket.py --url "..." --signature-type 3
```

## Troubleshooting

| Error | Meaning |
| --- | --- |
| `POLYMARKET_PRIVATE_KEY is not set` | Export the env var before running (not needed with `--dry-run`). |
| `...must be a 64-character hex string` | Your key is malformed — check for typos or missing characters. |
| `A token ID is required` | Pass `--url`, `--token-id`, set `POLYMARKET_TOKEN_ID`, or add `--dry-run`. |
| `No option selected.` | You skipped or quit every option in the interactive `--url` walkthrough. |
| `No tradeable markets found for this bet (all resolved or closed).` | Every market on that event has already resolved; there's nothing left to buy. |
| `(Skipping N resolved/closed market(s)...)` | Informational: resolved markets (prices pinned to 0/1, no live order book) are hidden from the buy picker. |
| `Could not load order book: 404 ... /book?token_id=...` | That token belongs to a resolved/closed market, which has no CLOB order book. Pick a market that's still accepting orders. |
| `(Could not read wallet balance: ...)` | The Polygon RPC call failed (network, rate limit, or unknown address); you'll be prompted to type a bankroll instead. Try another endpoint via `POLYMARKET_RPC_URL`. |
| `No edge: your estimate ... is not above the market price ...` | Your win-probability estimate is ≤ the market price, so Kelly recommends not betting. Only raise your estimate if you genuinely believe it, or enter a manual amount. |
| `Cancelled (no edge).` | You chose `[q]uit` at the no-edge prompt instead of re-entering a price or a manual amount — no order was placed. |
| `Cancelled.` (after the summary) | You answered anything other than `y` at the confirmation prompt — no order was placed. |
| `maker address not allowed, please use the deposit wallet flow` | Try `--signature-type 3` (see [section 7](#7-using-a-proxy-or-deposit-wallet)) with `polymarket.funder` set in `config.yaml`. |
| 403 / geo-block errors | Run `python3 test_connection.py` — the "without key" test flags if your IP is region-blocked. |
| Insufficient balance/allowance errors | Fund your wallet with USDC and ensure Polymarket allowances are set (this normally happens automatically the first time you trade via the official UI). |

## Safety notes

- This script places a **real order with real funds** — double-check your win-probability
  estimate, your buy price, the share count, and the token ID before confirming.
- It's a **limit (GTC)** order: it fills at your price or better and otherwise rests on the
  book unfilled until it fills or you cancel it (see `list_open_orders.py`). You won't overpay,
  but a price below the best ask may not fill right away.
- Never commit your private key or `config.yaml` to source control.
