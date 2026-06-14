"""
read_engine.py - The objectivity engine.

Turns computed structure + levels into an objective, no-opinion read with BOTH a
bull and a bear trigger. Language is conditional and structural only: "bullish/
bearish" mean above/below a named level, never sentiment. Banned: I think,
should, will, buy, sell, target.
"""
from __future__ import annotations


def _f(x):
    return "-" if x is None else f"{x:,.2f}"


def _nearest_fib(close, fib):
    best = None
    for L in fib["levels"]:
        d = abs(L["price"] - close)
        if best is None or d < best[0]:
            best = (d, L)
    return best[1] if best else None


def build_read(symbol, as_of, close, trend, ma, fib, zones_above, zones_below,
               atr14, changed, verified=True):
    if not verified:
        return {"symbol": symbol, "verified": False,
                "location": "-", "bull_trigger": "-", "bear_trigger": "-",
                "line_in_sand": None,
                "read": f"{symbol}: data unverified for {as_of} - withheld (fail-closed)."}

    loc = []
    if ma.get("ema21"):
        loc.append(f"{'above' if close >= ma['ema21'] else 'below'} the 21-EMA at {_f(ma['ema21'])}")
    if ma.get("sma200"):
        loc.append(f"{'above' if close >= ma['sma200'] else 'below'} the 200-SMA")
    nf = _nearest_fib(close, fib)
    if nf:
        side = "holding" if close >= nf["price"] else "testing"
        loc.append(f"{side} the {nf['r']} retracement at {_f(nf['price'])}")
    location = "; ".join(loc) if loc else "-"

    a1 = zones_above[0] if zones_above else None
    a2 = zones_above[1] if len(zones_above) > 1 else None
    b1 = zones_below[0] if zones_below else None
    b2 = zones_below[1] if len(zones_below) > 1 else None

    bull = (f"acceptance above {_f(a1['price'])} opens "
            f"{_f(a2['price']) if a2 else 'higher'}") if a1 else "-"
    bear = (f"loss of {_f(b1['price'])} exposes "
            f"{_f(b2['price']) if b2 else 'lower'}") if b1 else "-"
    line = b1["price"] if b1 else None

    structure_word = {"uptrend": "bullish", "downtrend": "bearish", "range": "neutral"}[trend]
    tail = f" above {_f(line)}" if (line is not None and trend != "downtrend") else ""
    read = (f"{symbol} ({as_of}): {trend}. At {_f(close)}, {location}. "
            f"Structure is {structure_word}{tail}. "
            f"Above: {bull}. Below: {bear}. ATR(14) {_f(atr14)}.")
    return {"symbol": symbol, "verified": True, "location": location,
            "bull_trigger": bull, "bear_trigger": bear, "line_in_sand": line,
            "read": read}
