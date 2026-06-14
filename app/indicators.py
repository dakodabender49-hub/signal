"""
indicators.py - Verified technical math for SIGNAL.

Pure standard library (no third-party deps) so it runs anywhere and is easy to
unit-test against known values. Every function here is covered by golden-file
tests in test_indicators.py. Accuracy of these formulas is the top priority of
the whole project, so they are intentionally simple and auditable.
"""
from __future__ import annotations
import math
from typing import Sequence, Optional

FIB_RETRACE = [0.236, 0.382, 0.5, 0.618, 0.786]
FIB_EXTEND = [1.272, 1.618, 2.0]
GOLDEN_POCKET = (0.618, 0.65)


def sma(values: Sequence[float], period: int) -> Optional[float]:
    """Simple moving average of the last `period` values."""
    if values is None or len(values) < period or period <= 0:
        return None
    return sum(values[-period:]) / period


def ema(values: Sequence[float], period: int) -> Optional[float]:
    """Exponential moving average, seeded with the SMA of the first `period`."""
    if values is None or len(values) < period or period <= 0:
        return None
    k = 2.0 / (period + 1.0)
    e = sum(values[:period]) / period
    for v in values[period:]:
        e = v * k + e * (1.0 - k)
    return e


def true_ranges(highs, lows, closes):
    """True Range for each bar i>=1: max(H-L, |H-prevC|, |L-prevC|)."""
    trs = []
    for i in range(1, len(closes)):
        h, l, pc = highs[i], lows[i], closes[i - 1]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return trs


def atr(highs, lows, closes, period: int = 14, method: str = "wilder") -> Optional[float]:
    """Average True Range. `wilder` (default, platform-standard) or `simple` mean."""
    trs = true_ranges(highs, lows, closes)
    if not trs:
        return None
    if len(trs) < period:
        return sum(trs) / len(trs)
    if method == "simple":
        return sum(trs[-period:]) / period
    a = sum(trs[:period]) / period
    for tr in trs[period:]:
        a = (a * (period - 1) + tr) / period
    return a


def classic_pivots(high: float, low: float, close: float) -> dict:
    """Classic (floor-trader) daily pivot points from the prior session HLC."""
    pp = (high + low + close) / 3.0
    return {
        "pp": pp,
        "r1": 2 * pp - low,
        "s1": 2 * pp - high,
        "r2": pp + (high - low),
        "s2": pp - (high - low),
        "r3": high + 2 * (pp - low),
        "s3": low - 2 * (high - pp),
    }


def find_pivots(highs, lows, width: int = 3):
    """Fractal pivots: strict extreme within +/- `width` bars. Returns (ph, pl)."""
    ph, pl = [], []
    n = len(highs)
    for i in range(width, n - width):
        wh = highs[i - width:i + width + 1]
        wl = lows[i - width:i + width + 1]
        left_h = highs[i - width:i]
        left_l = lows[i - width:i]
        if highs[i] == max(wh) and highs[i] > (max(left_h) if left_h else highs[i] - 1):
            ph.append(i)
        if lows[i] == min(wl) and lows[i] < (min(left_l) if left_l else lows[i] + 1):
            pl.append(i)
    return ph, pl


def trend_state(highs, lows, width: int = 3) -> str:
    """uptrend (HH+HL) / downtrend (LH+LL) / range, from the last two pivots."""
    ph, pl = find_pivots(highs, lows, width)
    if len(ph) < 2 or len(pl) < 2:
        return "range"
    hh = highs[ph[-1]] > highs[ph[-2]]
    hl = lows[pl[-1]] > lows[pl[-2]]
    lh = highs[ph[-1]] < highs[ph[-2]]
    ll = lows[pl[-1]] < lows[pl[-2]]
    if hh and hl:
        return "uptrend"
    if lh and ll:
        return "downtrend"
    return "range"


def active_swing(highs, lows, lookback: int = 60):
    """Active-leg swing high/low = extreme high & low over the lookback window."""
    h = highs[-lookback:]
    l = lows[-lookback:]
    return max(h), min(l)


def fib_retracements(swing_high: float, swing_low: float, trend: str) -> dict:
    """Retracements off the active swing.
    Uptrend pullback:  level = SH - (SH-SL)*r
    Downtrend bounce:  level = SL + (SH-SL)*r
    """
    rng = swing_high - swing_low
    levels = []
    for r in FIB_RETRACE:
        price = (swing_low + rng * r) if trend == "downtrend" else (swing_high - rng * r)
        levels.append({"r": r, "price": round(price, 2)})
    gp = []
    for r in GOLDEN_POCKET:
        price = (swing_low + rng * r) if trend == "downtrend" else (swing_high - rng * r)
        gp.append(price)
    gp.sort()
    return {
        "swing_high": round(swing_high, 2),
        "swing_low": round(swing_low, 2),
        "levels": levels,
        "golden_pocket": [round(gp[0], 2), round(gp[1], 2)],
    }


def fib_extensions(swing_high: float, swing_low: float, trend: str) -> list:
    """Extension targets projected beyond the swing (1.272, 1.618, 2.0)."""
    rng = swing_high - swing_low
    out = []
    for e in FIB_EXTEND:
        price = (swing_high - rng * e) if trend == "downtrend" else (swing_low + rng * e)
        out.append({"e": e, "price": round(price, 2)})
    return out


def round_number_levels(price: float):
    """A couple of psychological round numbers bracketing price."""
    if price <= 0:
        return []
    magnitude = 10 ** (math.floor(math.log10(price)) - 1)
    step = max(magnitude, 1)
    base = math.floor(price / step) * step
    cands = {base, base + step, base - step}
    return [c for c in cands if c > 0]


def collect_levels(ctx: dict) -> list:
    """Gather every candidate level as (price, label)."""
    levels = []
    for L in ctx["fib"]["levels"]:
        levels.append((L["price"], f"Fib {L['r']}"))
    for key, label in [("ema8", "8-EMA"), ("ema21", "21-EMA"),
                       ("sma50", "50-SMA"), ("sma200", "200-SMA")]:
        v = ctx["ma"].get(key)
        if v:
            levels.append((round(v, 2), label))
    for key in ["pp", "r1", "r2", "s1", "s2"]:
        levels.append((round(ctx["pivots"][key], 2), f"pivot {key.upper()}"))
    pdh, pdl, pdc = ctx["prior"]
    levels += [(round(pdh, 2), "prior-day high"),
               (round(pdl, 2), "prior-day low"),
               (round(pdc, 2), "prior close")]
    for p in ctx.get("recent_swing_highs", []):
        levels.append((round(p, 2), "swing high"))
    for p in ctx.get("recent_swing_lows", []):
        levels.append((round(p, 2), "swing low"))
    for rn in round_number_levels(ctx["close"]):
        levels.append((float(rn), "round number"))
    return levels


def cluster_levels(levels, price: float, atr_val: float, side: str):
    """Merge levels within +/-0.5*ATR into zones on one side of price.
    Confluence score = number of distinct evidence labels in the zone."""
    band = 0.5 * (atr_val or (price * 0.005))
    if side == "above":
        sel = [(p, l) for p, l in levels if p > price]
    else:
        sel = [(p, l) for p, l in levels if p < price]
    sel.sort(key=lambda x: abs(x[0] - price))
    zones = []
    for p, l in sel:
        placed = False
        for z in zones:
            if abs(z["center"] - p) <= band:
                z["members"].append((p, l))
                z["center"] = sum(m[0] for m in z["members"]) / len(z["members"])
                placed = True
                break
        if not placed:
            zones.append({"center": p, "members": [(p, l)]})
    out = []
    for z in zones:
        prices = [m[0] for m in z["members"]]
        labels = list(dict.fromkeys(m[1] for m in z["members"]))
        out.append({
            "low": round(min(prices), 2),
            "high": round(max(prices), 2),
            "price": round(sum(prices) / len(prices), 2),
            "score": len(labels),
            "evidence": labels,
        })
    out.sort(key=lambda z: abs(z["price"] - price))
    return out
