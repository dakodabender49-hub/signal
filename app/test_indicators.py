"""
Golden-file tests - the accuracy harness. Run: python app/test_indicators.py
(also pytest-compatible). These lock the indicator math to known values so a
regression can never silently ship a wrong number.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import indicators as ind
import integrity as integ


def approx(a, b, t=1e-9):
    return abs(a - b) <= t


def test_fib_uptrend():
    f = ind.fib_retracements(100, 80, "uptrend")
    g = {L["r"]: L["price"] for L in f["levels"]}
    assert approx(g[0.618], 87.64), g
    assert approx(g[0.382], 92.36), g
    assert approx(g[0.5], 90.0), g
    # golden pocket = SH - rng*0.618 and SH - rng*0.65 -> [87.0, 87.64]
    assert f["golden_pocket"] == [87.0, 87.64], f["golden_pocket"]


def test_fib_downtrend():
    f = ind.fib_retracements(100, 80, "downtrend")
    g = {L["r"]: L["price"] for L in f["levels"]}
    assert approx(g[0.618], 92.36), g


def test_extensions():
    e = ind.fib_extensions(100, 80, "uptrend")
    d = {x["e"]: x["price"] for x in e}
    assert approx(d[1.618], 80 + 20 * 1.618), d  # 112.36


def test_pivots():
    p = ind.classic_pivots(110, 90, 100)
    assert (p["pp"], p["r1"], p["s1"]) == (100, 110, 90), p
    assert p["r2"] == 120 and p["s2"] == 80
    assert p["s1"] <= p["pp"] <= p["r1"]


def test_atr():
    highs = [101, 103, 102, 104]
    lows = [99, 100, 99, 101]
    closes = [100, 102, 101, 103]
    assert approx(ind.atr(highs, lows, closes, 3, "simple"), 3.0)
    assert ind.atr(highs, lows, closes, 3, "wilder") > 0


def test_moving_averages():
    assert ind.sma([1, 2, 3, 4, 5], 5) == 3.0
    assert ind.ema([10] * 10, 5) == 10.0   # constant series -> EMA = the value
    assert ind.sma([1, 2], 5) is None       # not enough data -> None, not a guess


def test_validation_gate():
    ok, _ = integ.validate_ohlc({"open": 100, "high": 104, "low": 99, "close": 103})
    assert ok
    bad, _ = integ.validate_ohlc({"open": 100, "high": 104, "low": 101, "close": 103})
    assert not bad   # low > open violates the invariant


def test_reconcile_fail_closed():
    v, st = integ.reconcile_close(100.0, 100.05)     # within 0.1%
    assert v is not None and st == "verified"
    n, _ = integ.reconcile_close(100.0, 101.0)        # 1% disagreement
    assert n is None                                  # FAIL CLOSED
    n2, _ = integ.reconcile_close(100.0, None)        # single source
    assert n2 is None


def run():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print(f"\nALL {len(fns)} GOLDEN TESTS PASSED")


if __name__ == "__main__":
    run()
