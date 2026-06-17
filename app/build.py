"""
build.py - orchestrator.  validate -> compute -> write state.json + dashboard.

    python app/build.py --mode sample        # offline demo (default)
    python app/build.py --mode live          # cross-checked free data (in CI)

Writes docs/state.json and docs/index.html (GitHub Pages serves /docs).
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import indicators as ind
import integrity as integ
import read_engine as rd
import sample_data

NAMES = {"SPY": "S&P 500 ETF", "QQQ": "Nasdaq 100 ETF", "AAPL": "Apple",
         "MSFT": "Microsoft", "GOOGL": "Alphabet", "AMZN": "Amazon",
         "NVDA": "Nvidia", "META": "Meta", "TSLA": "Tesla", "MU": "Micron"}


def load_watchlist():
    with open(os.path.join(ROOT, "config", "watchlist.json")) as f:
        return json.load(f)


BACKDROP_SYMS = [("VIX", "^VIX", 1), ("10Y", "^TNX", 2), ("30Y", "^TYX", 2),
                 ("DXY", "DX-Y.NYB", 2), ("Oil", "CL=F", 2), ("Gold", "GC=F", 2)]


def backdrop_live(settings):
    """Real intermarket backdrop via the verified datafeed. Fail-closed to '-'."""
    import datafeed
    out = []
    for name, sym, dec in BACKDROP_SYMS:
        try:
            bars = datafeed.get_verified_history(sym, settings)
            last, prev = bars[-1]["close"], bars[-2]["close"]
            if name in ("10Y", "30Y") and last > 20:   # ^TNX/^TYX can quote yield x10
                last /= 10; prev /= 10
            out.append({"name": name, "value": round(last, dec),
                        "change": round(last - prev, dec), "note": ""})
        except Exception:
            out.append({"name": name, "value": "-", "change": 0, "note": "n/a"})
    return out


def backdrop_sample():
    return [
        {"name": "VIX", "value": 14.2, "change": -0.6, "note": "calm regime"},
        {"name": "10Y", "value": 4.31, "change": 0.02, "note": "yields firm"},
        {"name": "2Y", "value": 4.05, "change": 0.01, "note": "2s10s +26bp"},
        {"name": "DXY", "value": 104.1, "change": -0.2, "note": "dollar soft"},
        {"name": "WTI", "value": 71.8, "change": 0.5, "note": "crude steady"},
        {"name": "Gold", "value": 2410.0, "change": 7.0, "note": "bid"},
        {"name": "Breadth", "value": 63, "change": 2, "note": "% S&P > 50-day"},
    ]


def fed_econ_sample():
    return [
        {"date": "2026-06-17", "time": "14:00 ET", "event": "FOMC rate decision",
         "impact": "high", "prior": "4.25-4.50%", "consensus": "4.25-4.50%", "actual": None},
        {"date": "2026-06-17", "time": "14:30 ET", "event": "Fed press conference",
         "impact": "high", "prior": "-", "consensus": "-", "actual": None},
        {"date": "2026-06-11", "time": "08:30 ET", "event": "CPI (YoY)",
         "impact": "high", "prior": "3.3%", "consensus": "3.2%", "actual": "3.1%"},
        {"date": "2026-06-12", "time": "08:30 ET", "event": "Initial jobless claims",
         "impact": "medium", "prior": "229K", "consensus": "232K", "actual": "227K"},
    ]


def _num(info, key):
    v = info.get(key)
    return v if isinstance(v, (int, float)) and v == v else None


def fundamentals(symbol):
    """Live fundamentals via yfinance .info (resilient; missing fields -> None)."""
    info = {}
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).info or {}
    except Exception:
        info = {}
    edate = None
    ts = info.get("earningsTimestamp") or info.get("earningsTimestampStart")
    if ts:
        try:
            edate = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            edate = None
    rev_g = _num(info, "revenueGrowth")
    eps_g = _num(info, "earningsGrowth")
    pe = _num(info, "trailingPE")
    fpe = _num(info, "forwardPE")
    return {
        "pe": round(pe, 1) if pe else None,
        "forward_pe": round(fpe, 1) if fpe else None,
        "market_cap": _num(info, "marketCap"),
        "rev_growth": round(rev_g * 100, 1) if rev_g is not None else None,
        "eps_growth": round(eps_g * 100, 1) if eps_g is not None else None,
        "earnings_date": edate,
        "sector": info.get("sector"),
        "w52_high": _num(info, "fiftyTwoWeekHigh"),
        "w52_low": _num(info, "fiftyTwoWeekLow"),
        "rs_3m": None, "pos52": None,
    }


def fundamentals_sample(symbol):
    import random
    r = random.Random(sum(ord(c) for c in symbol))
    return {"pe": round(r.uniform(15, 40), 1), "forward_pe": round(r.uniform(12, 35), 1),
            "market_cap": r.choice([3.1e12, 2.4e11, 8.0e11, 1.5e11]),
            "rev_growth": round(r.uniform(-5, 25), 1), "eps_growth": round(r.uniform(-10, 30), 1),
            "earnings_date": "2026-07-24", "sector": "Technology",
            "w52_high": None, "w52_low": None,
            "rs_3m": round(r.uniform(-8, 8), 1), "pos52": r.randint(20, 95)}


def compute_instrument(symbol, name, typ, bars, settings):
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    last, prev = bars[-1], bars[-2]
    close, as_of = last["close"], last["date"]

    trend = ind.trend_state(highs, lows, settings["pivot_width"])
    sh, sl = ind.active_swing(highs, lows, settings["fib_swing_lookback"])
    fib = ind.fib_retracements(sh, sl, trend)
    ext = ind.fib_extensions(sh, sl, trend)
    ma = {"ema8": ind.ema(closes, 8), "ema21": ind.ema(closes, 21),
          "sma50": ind.sma(closes, 50), "sma200": ind.sma(closes, 200)}
    pivots = ind.classic_pivots(prev["high"], prev["low"], prev["close"])
    atr14 = ind.atr(highs, lows, closes, settings["atr_period"])

    ph, pl = ind.find_pivots(highs, lows, settings["pivot_width"])
    recent_sh = [highs[i] for i in ph[-3:]]
    recent_sl = [lows[i] for i in pl[-3:]]
    ctx = {"close": close, "fib": fib, "ma": ma, "pivots": pivots,
           "prior": (prev["high"], prev["low"], prev["close"]),
           "recent_swing_highs": recent_sh, "recent_swing_lows": recent_sl}
    levels = ind.collect_levels(ctx)
    za = ind.cluster_levels(levels, close, atr14, "above")[:4]
    zb = ind.cluster_levels(levels, close, atr14, "below")[:4]

    changed = []
    if ma["ema21"]:
        t_above = close >= ma["ema21"]
        y_above = prev["close"] >= ma["ema21"]
        if t_above and not y_above:
            changed.append("reclaimed the 21-EMA")
        elif y_above and not t_above:
            changed.append("lost the 21-EMA")
    if recent_sl:
        changed.append(f"nearest swing low {recent_sl[-1]:.2f}")

    r = rd.build_read(symbol, as_of, close, trend, ma, fib, za, zb, atr14, changed, True)
    return {
        "symbol": symbol, "name": name, "type": typ, "verified": True, "as_of": as_of,
        "ohlc": {k: last[k] for k in ("open", "high", "low", "close")},
        "prev_close": prev["close"],
        "change_pct": round((close - prev["close"]) / prev["close"] * 100, 2),
        "structure": trend, "location": r["location"],
        "fib": fib, "extensions": ext,
        "ma": {k: (round(v, 2) if v else None) for k, v in ma.items()},
        "pivots": {k: round(v, 2) for k, v in pivots.items()},
        "atr14": round(atr14, 2) if atr14 else None,
        "levels_above": za, "levels_below": zb,
        "confluence": [z for z in (za + zb) if z["score"] >= 2][:4],
        "bull_trigger": r["bull_trigger"], "bear_trigger": r["bear_trigger"],
        "line_in_sand": r["line_in_sand"], "changed": changed, "read": r["read"],
        "history": [[b["date"], b["open"], b["high"], b["low"], b["close"]] for b in bars[-180:]],
    }


def get_bars(symbol, mode, settings):
    if mode == "sample":
        return sample_data.generate(symbol)
    import datafeed
    return datafeed.get_verified_history(symbol, settings)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="sample", choices=["sample", "live"])
    ap.add_argument("--session", default="pre-open")
    args = ap.parse_args()

    wl = load_watchlist()
    settings = wl["settings"]
    universe = ([("index", s) for s in wl["indexes"]]
                + [("stock", s) for s in wl["stocks"]]
                + [("crypto", s) for s in wl.get("crypto", [])])

    instruments, problems = [], []
    for typ, sym in universe:
        try:
            bars = get_bars(sym, args.mode, settings)
            ok, why = integ.validate_series(bars)
            if not ok:
                problems.append({"symbol": sym, "reason": why})
                instruments.append({"symbol": sym, "name": NAMES.get(sym, sym),
                                    "type": typ, "verified": False,
                                    "read": f"{sym}: {why} - withheld (fail-closed)."})
                continue
            inst = compute_instrument(sym, NAMES.get(sym, sym), typ, bars, settings)
            if typ == "stock":
                inst["fundamentals"] = fundamentals(sym) if args.mode == "live" else fundamentals_sample(sym)
            instruments.append(inst)
        except Exception as e:
            problems.append({"symbol": sym, "reason": str(e)})
            instruments.append({"symbol": sym, "name": NAMES.get(sym, sym),
                                "type": typ, "verified": False,
                                "read": f"{sym}: {e} - withheld (fail-closed)."})

    # relative strength vs SPY (3m) + 52-week position
    _spy = next((i for i in instruments if i.get("symbol") == "SPY" and i.get("verified")), None)

    def _ret(hist, n):
        return (hist[-1][4] / hist[-1 - n][4] - 1) * 100 if hist and len(hist) > n else None

    _spy3 = _ret(_spy["history"], 63) if _spy and _spy.get("history") else None
    for _i in instruments:
        _fu = _i.get("fundamentals")
        if not _fu or not _i.get("verified"):
            continue
        _h = _i.get("history")
        if _h and _spy3 is not None:
            _s3 = _ret(_h, 63)
            if _s3 is not None:
                _fu["rs_3m"] = round(_s3 - _spy3, 1)
        _close = _i.get("ohlc", {}).get("close")
        _hi, _lo = _fu.get("w52_high"), _fu.get("w52_low")
        if _close and _hi and _lo and _hi > _lo:
            _fu["pos52"] = round((_close - _lo) / (_hi - _lo) * 100)

    as_of = max([i.get("as_of", "") for i in instruments if i.get("as_of")] or [""])
    state = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "session": args.session,
            "data_mode": "SAMPLE" if args.mode == "sample" else "LIVE",
            "as_of_date": as_of,
            "disclaimer": ("Structural reads and screens only - not financial advice. "
                           "In SAMPLE mode the numbers are simulated for layout and are "
                           "NOT live market data."),
            "problems": problems,
        },
        "backdrop": backdrop_live(settings) if args.mode == "live" else backdrop_sample(),
        "fed_econ": fed_econ_sample(),
        "instruments": instruments,
        "screener": {"note": "Movers + objective setup screens arrive in Phase 3.",
                     "movers": [], "setups": []},
    }

    docs = os.path.join(ROOT, "docs")
    os.makedirs(docs, exist_ok=True)
    with open(os.path.join(docs, "state.json"), "w") as f:
        json.dump(state, f, indent=2)
    tpl = open(os.path.join(ROOT, "site", "template.html")).read()
    html = tpl.replace("__STATE_JSON__", json.dumps(state))
    with open(os.path.join(docs, "index.html"), "w") as f:
        f.write(html)

    verified = sum(1 for i in instruments if i.get("verified"))
    print(f"Built {len(instruments)} instruments ({verified} verified, "
          f"{len(problems)} withheld) | mode={state['meta']['data_mode']} | as_of={as_of}")
    for i in instruments[:3]:
        if i.get("verified"):
            print("  -", i["read"][:150])


if __name__ == "__main__":
    main()
