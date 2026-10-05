import io
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import buy_polymarket as buy

REAL_GET_BALANCE = buy.get_usdc_balance
# resolve_stake now shows the live order book first; stub it so tests stay offline.
buy.show_order_book = lambda *a, **k: None


def approx(a, b, tol=1e-9):
    return abs(a - b) <= tol


def make_args(**kw):
    base = dict(
        amount=None,
        money=None,
        win_prob=None,
        kelly_fraction=0.5,
        funder="0xfunder",
        address=None,
        rpc_url="http://rpc.test",
    )
    base.update(kw)
    return types.SimpleNamespace(**base)


def with_balance(stub, text, fn):
    """Runs fn() with get_usdc_balance stubbed and stdin fed from text, then restores both."""
    original_stdin, original_balance = sys.stdin, buy.get_usdc_balance
    sys.stdin = io.StringIO(text)
    buy.get_usdc_balance = stub
    try:
        return fn()
    finally:
        sys.stdin = original_stdin
        buy.get_usdc_balance = original_balance


def test_kelly_fraction_edges():
    # No edge: estimate == market price -> 0.
    assert buy.kelly_fraction(0.5, 0.5) == 0.0
    # Estimate below the price -> clamped to 0.
    assert buy.kelly_fraction(0.6, 0.4) == 0.0
    # Positive edge: f* = (p - price) / (1 - price).
    assert approx(buy.kelly_fraction(0.5, 0.6), 0.2)
    assert approx(buy.kelly_fraction(0.25, 0.5), 1 / 3)
    # Degenerate prices never bet.
    assert buy.kelly_fraction(0.0, 0.9) == 0.0
    assert buy.kelly_fraction(1.0, 0.9) == 0.0


def test_kelly_stake_scales_with_fraction_and_bankroll():
    # full-Kelly fraction at price 0.5, p 0.6 is 0.2; on $100 that's $20, half-Kelly $10.
    assert approx(buy.kelly_stake(100, 0.5, 0.6, 1.0), 20.0)
    assert approx(buy.kelly_stake(100, 0.5, 0.6, 0.5), 10.0)
    # No edge -> $0 regardless of bankroll.
    assert buy.kelly_stake(100, 0.5, 0.5, 0.5) == 0.0


def test_resolve_stake_accepts_kelly_suggestion():
    args = make_args(win_prob=0.6)  # buy price 0.5 -> f*=0.2, half-Kelly * 200 = $20 -> 40 shares
    price, size, info = with_balance(
        lambda address, rpc_url=None: 200.0,
        "0.5\na\n",  # enter price 0.5, then accept
        lambda: buy.resolve_stake(args, "tok", None, client=None),
    )
    assert approx(price, 0.5) and size == 40, (price, size)
    assert info["bankroll"] == 200.0 and approx(info["win_prob"], 0.6) and info["size"] == 40


def test_resolve_stake_prompts_for_win_prob():
    args = make_args()  # win_prob omitted -> prompted for after the price
    # price 0.5, p=0.75 (f*=0.5, half-Kelly * 100 = $25) -> floor(25/0.5) = 50 shares.
    price, size, info = with_balance(
        lambda address, rpc_url=None: 100.0,
        "0.5\n0.75\na\n",
        lambda: buy.resolve_stake(args, "tok", None, client=None),
    )
    assert approx(price, 0.5) and size == 50, (price, size)


def test_resolve_stake_reprices_and_runs_kelly_again():
    # Enter one price, re-quote with a different price, and accept the new suggestion.
    args = make_args(win_prob=0.6)
    # price 0.5 -> $20, [r]e-enter, price 0.25 -> f*=0.4667 -> ~$46.67 -> floor(46.67/0.25) = 186.
    price, size, info = with_balance(
        lambda address, rpc_url=None: 200.0,
        "0.5\nr\n0.25\na\n",
        lambda: buy.resolve_stake(args, "tok", None, client=None),
    )
    assert approx(price, 0.25) and size == 186, (price, size)


def test_resolve_stake_no_edge_manual_override():
    def boom(*a, **k):
        raise AssertionError("balance should not be fetched when there is no edge")

    args = make_args(win_prob=0.4)  # below the entered 0.5 price -> no edge
    # enter price 0.5 (no edge), choose [m]anual, then $12.50 -> floor(12.5/0.5) = 25 shares.
    price, size, info = with_balance(boom, "0.5\nm\n12.50\n", lambda: buy.resolve_stake(args, "tok", None, client=None))
    assert approx(price, 0.5) and size == 25, (price, size)
    assert info is None


def test_resolve_stake_amount_override_skips_kelly():
    def boom(*a, **k):
        raise AssertionError("balance should not be fetched when --amount is given")

    args = make_args(amount=33.0, win_prob=0.9)  # $33 at price 0.5 -> floor(33/0.5) = 66 shares
    price, size, info = with_balance(boom, "0.5\n", lambda: buy.resolve_stake(args, "tok", None, client=None))
    assert approx(price, 0.5) and size == 66 and info is None, (price, size, info)


def test_resolve_bankroll_zero_exits():
    # No address -> manual prompt; entering 0 exits instead of re-prompting.
    args = make_args(funder=None, address=None)
    original = sys.stdin
    sys.stdin = io.StringIO("0\n")
    try:
        buy.resolve_bankroll(args, client=None)
    except SystemExit:
        pass
    else:
        raise AssertionError("a bankroll of 0 should exit")
    finally:
        sys.stdin = original


def test_resolve_bankroll_prefers_collateral():
    # With a client, the CLOB collateral balance wins over any on-chain balanceOf.
    args = make_args()
    original = buy.fetch_collateral_balance
    buy.fetch_collateral_balance = lambda client: 462.70

    def boom(*a, **k):
        raise AssertionError("on-chain balanceOf should not be used when collateral is available")

    try:
        bankroll = with_balance(boom, "", lambda: buy.resolve_bankroll(args, client=object()))
    finally:
        buy.fetch_collateral_balance = original
    assert approx(bankroll, 462.70), bankroll


def test_get_usdc_balance_decodes_six_decimals():
    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            # 12_500000 (6 decimals) == $12.50.
            return {"result": hex(12_500000)}

    def fake_post(url, json=None, timeout=15):
        captured["url"] = url
        captured["data"] = json["params"][0]["data"]
        return FakeResp()

    original = buy.requests.post
    buy.requests.post = fake_post
    try:
        balance = REAL_GET_BALANCE("0xAbCdEf0000000000000000000000000000000001", "http://rpc.test")
    finally:
        buy.requests.post = original
    assert approx(balance, 12.5), balance
    assert captured["url"] == "http://rpc.test"
    # balanceOf selector + 32-byte left-padded, lowercased address.
    assert captured["data"] == "0x70a08231" + "abcdef0000000000000000000000000000000001".rjust(64, "0")


test_kelly_fraction_edges()
test_kelly_stake_scales_with_fraction_and_bankroll()
test_resolve_stake_accepts_kelly_suggestion()
test_resolve_stake_prompts_for_win_prob()
test_resolve_stake_reprices_and_runs_kelly_again()
test_resolve_stake_no_edge_manual_override()
test_resolve_stake_amount_override_skips_kelly()
test_resolve_bankroll_zero_exits()
test_resolve_bankroll_prefers_collateral()
test_get_usdc_balance_decodes_six_decimals()
print("DONE")
