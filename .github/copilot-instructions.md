# Copilot / AI Agent Instructions — Polymarket Bot

This repo is a collection of independent Python CLI scripts for trading on Polymarket
(buying/selling outcome tokens, browsing markets/order books, managing open orders and
positions). There is no web server, framework, or single entry point — each `*.py` file at
the repo root is run directly (`python3 script.py`).

Read [docs/PROJECT_OVERVIEW.md](../docs/PROJECT_OVERVIEW.md) first for what each script does
and how they import helpers from each other.

## Required workflow for any change

**For every new script, or every non-trivial function you add or change, you must:**

1. **Write a test case** under [`testcases/`](../testcases/). Follow the existing pattern in
   that folder: a small standalone script that imports the target module, uses a fake/stub
   client where network or wallet calls would otherwise happen, and drives interactive
   prompts via piped stdin. Prefer this over a full pytest suite unless one already exists.
2. **Write or update documentation** under [`docs/`](../docs/). Add a new `docs/*.md` file for
   a new script (mirroring `docs/BUYING_GUIDE.md`'s style: prerequisites, usage examples,
   troubleshooting table), or update the relevant section of `docs/PROJECT_OVERVIEW.md` and
   any affected guide for changes to existing scripts. Also update the script table in
   `docs/PROJECT_OVERVIEW.md`.

Do not consider a change complete until both of these exist.

## Conventions to follow

- **Self-contained scripts, minimal shared code.** Only extract a helper into another
  module when it's genuinely reused (see the import graph in `docs/PROJECT_OVERVIEW.md`).
  Avoid introducing a framework or package structure.
- **argparse CLIs.** Every script exposes its options via `argparse`, with `--dry-run`
  support on anything that can mutate state (place/cancel orders) and a `[y/n]`
  confirmation prompt before real (non-dry-run) mutating actions.
- **Secrets never touch disk or logs in plaintext.**
  - `config.yaml` is git-ignored; never remove it from `.gitignore` or commit a real one.
    `config.yaml.example` is the committed template — update it when adding new config keys.
  - The private key is stored only as an AES-256-GCM-encrypted, password-protected blob
    (`key_crypto.py` / `encrypt_key.py`) or read from an env var; it's decrypted into memory
    only for the duration of a run and never written back to disk or printed.
  - GitHub tokens are only ever passed to git via a throwaway `GIT_ASKPASS` script, never as
    a CLI argument or committed into `.git/config`.
- **Environment variable fallbacks.** Any value also settable in `config.yaml` should have
  a matching `POLYMARKET_*` env var fallback (see the table in `docs/PROJECT_OVERVIEW.md`).
- **Prefer the public Gamma/Data APIs over authenticated CLOB calls** when the data doesn't
  require a wallet (market listings, order books, positions) — keeps scripts usable without
  a key.

## Safety

This repo places real orders with real money when run without `--dry-run`. When adding or
modifying trading logic, preserve (or add) a `--dry-run` mode and a confirmation prompt, and
test the dry-run path before assuming a change is correct.
