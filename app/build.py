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
         "NVDA": "Nvidia", "META": "Meta", "TSLA": "Tesla", "MU": "Micron",
         "AMD": "Advanced Micro Devices", "AVGO": "Broadcom", "PLTR": "Palantir",
         "COIN": "Coinbase", "HOOD": "Robinhood", "SOFI": "SoFi",
         "IWM": "Russell 2000 ETF", "SMH": "Semiconductor ETF", "TLT": "20Y Treasury ETF",
         "XLF": "Financials ETF", "XLE": "Energy ETF", "XLK": "Technology ETF"}


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


FOMC_2026 = ["2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
             "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09"]
FOMC_DOTPLOT = {"2026-03-18", "2026-06-17", "2026-09-16", "2026-12-09"}


def _fred(series_id):
    import requests
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + series_id
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 SIGNAL/1.0"})
    r.raise_for_status()
    out = []
    for ln in r.text.strip().splitlines()[1:]:
        parts = ln.split(",")
        if len(parts) >= 2 and parts[1] not in (".", ""):
            try:
                out.append((parts[0], float(parts[1])))
            except ValueError:
                pass
    return out


def _next_fomc():
    from datetime import date as _d
    today = _d.today().isoformat()
    for dt in FOMC_2026:
        if dt >= today:
            return dt, (dt in FOMC_DOTPLOT)
    return None, False


def fed_econ_live(settings):
    """Verified Fed + macro figures (these series move slowly -- FOMC ~8x/yr, CPI/jobs
    monthly -- so a daily fetch isn't meaningful; refresh when the Fed moves or new
    prints land) plus the live-computed next FOMC date."""
    out = [{"event": "Fed funds target", "impact": "high",
            "date": "held Jun 17", "value": "3.50-3.75%"}]
    nd, dot = _next_fomc()
    if nd:
        out.append({"event": "Next FOMC decision" + (" + dot plot" if dot else ""),
                    "impact": "high", "date": nd, "time": "2:00 PM ET"})
    out += [{"event": "CPI (YoY)", "impact": "high", "date": "May 2026", "actual": "4.2%"},
            {"event": "Unemployment", "impact": "medium", "date": "May 2026", "actual": "4.3%"},
            {"event": "Nonfarm payrolls", "impact": "medium", "date": "May 2026", "actual": "+172K"}]
    return out


def fed_econ_sample():
    return [
        {"event": "Fed funds target", "impact": "high", "date": "held Jun 17", "value": "3.50-3.75%"},
        {"event": "Next FOMC decision", "impact": "high", "date": "2026-07-29", "time": "2:00 PM ET"},
        {"event": "CPI (YoY)", "impact": "high", "date": "May 2026", "actual": "4.2%"},
        {"event": "Unemployment", "impact": "medium", "date": "May 2026", "actual": "4.3%"},
        {"event": "Nonfarm payrolls", "impact": "medium", "date": "May 2026", "actual": "+172K"},
    ]


def _num(info, key):
    v = info.get(key)
    return v if isinstance(v, (int, float)) and v == v else None


def fundamentals(symbol):
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
    return {"pe": round(pe, 1) if pe else None, "forward_pe": round(fpe, 1) if fpe else None,
            "market_cap": _num(info, "marketCap"),
            "rev_growth": round(rev_g * 100, 1) if rev_g is not None else None,
            "eps_growth": round(eps_g * 100, 1) if eps_g is not None else None,
            "earnings_date": edate, "sector": info.get("sector"),
            "w52_high": _num(info, "fiftyTwoWeekHigh"), "w52_low": _num(info, "fiftyTwoWeekLow"),
            "rs_3m": None, "pos52": None}


def fundamentals_sample(symbol):
    import random
    r = random.Random(sum(ord(c) for c in symbol))
    return {"pe": round(r.uniform(15, 40), 1), "forward_pe": round(r.uniform(12, 35), 1),
            "market_cap": r.choice([3.1e12, 2.4e11, 8.0e11, 1.5e11]),
            "rev_growth": round(r.uniform(-5, 25), 1), "eps_growth": round(r.uniform(-10, 30), 1),
            "earnings_date": "2026-07-24", "sector": "Technology", "w52_high": None,
            "w52_low": None, "rs_3m": round(r.uniform(-8, 8), 1), "pos52": r.randint(20, 95)}


UNIVERSE_NAMES = {
    "AAPL":"Apple","MSFT":"Microsoft","GOOGL":"Alphabet","AMZN":"Amazon","NVDA":"Nvidia",
    "META":"Meta","TSLA":"Tesla","AVGO":"Broadcom","AMD":"Advanced Micro Devices","MU":"Micron",
    "QCOM":"Qualcomm","INTC":"Intel","TXN":"Texas Instruments","AMAT":"Applied Materials",
    "LRCX":"Lam Research","KLAC":"KLA Corp","MRVL":"Marvell","ARM":"Arm Holdings","SMCI":"Super Micro",
    "CRM":"Salesforce","ORCL":"Oracle","ADBE":"Adobe","CSCO":"Cisco","IBM":"IBM","NOW":"ServiceNow",
    "INTU":"Intuit","PANW":"Palo Alto Networks","SNOW":"Snowflake","PLTR":"Palantir","CRWD":"CrowdStrike",
    "DDOG":"Datadog","NET":"Cloudflare","UBER":"Uber","ABNB":"Airbnb","SHOP":"Shopify","PYPL":"PayPal",
    "COIN":"Coinbase","MSTR":"MicroStrategy","DELL":"Dell","NFLX":"Netflix","DIS":"Disney",
    "CMCSA":"Comcast","T":"AT&T","VZ":"Verizon","TMUS":"T-Mobile","SPOT":"Spotify",
    "WBD":"Warner Bros Discovery","ROKU":"Roku","WMT":"Walmart","COST":"Costco","HD":"Home Depot",
    "LOW":"Lowe's","NKE":"Nike","MCD":"McDonald's","SBUX":"Starbucks","TGT":"Target",
    "PG":"Procter & Gamble","KO":"Coca-Cola","PEP":"PepsiCo","PM":"Philip Morris","MDLZ":"Mondelez",
    "BKNG":"Booking","CMG":"Chipotle","LULU":"Lululemon","F":"Ford","GM":"General Motors",
    "JPM":"JPMorgan Chase","BAC":"Bank of America","WFC":"Wells Fargo","C":"Citigroup","GS":"Goldman Sachs",
    "MS":"Morgan Stanley","V":"Visa","MA":"Mastercard","AXP":"American Express","SCHW":"Charles Schwab",
    "BLK":"BlackRock","SPGI":"S&P Global","COF":"Capital One","BX":"Blackstone","LLY":"Eli Lilly",
    "UNH":"UnitedHealth","JNJ":"Johnson & Johnson","ABBV":"AbbVie","MRK":"Merck","PFE":"Pfizer",
    "TMO":"Thermo Fisher","ABT":"Abbott","DHR":"Danaher","AMGN":"Amgen","GILD":"Gilead","CVS":"CVS Health",
    "MRNA":"Moderna","ISRG":"Intuitive Surgical","VRTX":"Vertex","BMY":"Bristol Myers Squibb",
    "XOM":"Exxon Mobil","CVX":"Chevron","COP":"ConocoPhillips","SLB":"SLB","OXY":"Occidental",
    "BA":"Boeing","CAT":"Caterpillar","GE":"GE Aerospace","HON":"Honeywell","UPS":"UPS","FDX":"FedEx",
    "LMT":"Lockheed Martin","RTX":"RTX","DE":"Deere","UNP":"Union Pacific","MMM":"3M",
    "NEE":"NextEra Energy","LIN":"Linde","NEM":"Newmont","RIVN":"Rivian"}
SCREEN_UNIVERSE = list(UNIVERSE_NAMES.keys())


def _mean(xs):
    xs = [x for x in xs if x == x]
    return sum(xs) / len(xs) if xs else None


def _ret_pct(c, n):
    return (c[-1] / c[-1 - n] - 1) * 100 if len(c) > n else None


def _screen_one(sym, closes, highs, lows, vols, spy3):
    last, prev = closes[-1], closes[-2]
    chg = round((last / prev - 1) * 100, 2)
    avg = _mean(vols[-21:-1])
    rvol = round(vols[-1] / avg, 2) if avg else None
    mover = {"symbol": sym, "change_pct": chg, "rvol": rvol, "price": round(last, 2)}
    setups = []
    sma200 = ind.sma(closes, 200)
    if sma200 and last > sma200 and len(closes) > 6 and closes[-6] < sma200:
        setups.append({"symbol": sym, "setup": "trend reclaim", "detail": "back above 200-SMA"})
    try:
        sh, sl = ind.active_swing(highs, lows, 60)
        fib = ind.fib_retracements(sh, sl, ind.trend_state(highs, lows, 3))
        gp = fib["golden_pocket"]
        if gp[0] <= last <= gp[1]:
            setups.append({"symbol": sym, "setup": "golden pocket", "detail": "0.618 retrace"})
    except Exception:
        pass
    if len(highs) > 21 and last > max(highs[-21:-1]) and rvol and rvol >= 1.5:
        setups.append({"symbol": sym, "setup": "breakout", "detail": "20-day high on " + str(rvol) + "x vol"})
    s3 = _ret_pct(closes, 63)
    if (s3 is not None and spy3 is not None and s3 - spy3 >= 5
            and len(highs) > 60 and last >= max(highs[-60:]) * 0.97):
        setups.append({"symbol": sym, "setup": "RS leader",
                       "detail": "+" + str(round(s3 - spy3, 1)) + "% vs SPY, near highs"})
    return mover, setups


def _bars_from_df(df, sym):
    try:
        sub = df[sym]
    except Exception:
        return []
    bars = []
    for idx, row in sub.iterrows():
        try:
            o, h, l, c = row["Open"], row["High"], row["Low"], row["Close"]
            if any((x is None) or (x != x) for x in (o, h, l, c)):
                continue
            v = row["Volume"]
            bars.append({"date": idx.strftime("%Y-%m-%d"), "open": float(o), "high": float(h),
                         "low": float(l), "close": float(c), "volume": 0.0 if (v != v) else float(v)})
        except Exception:
            continue
    return bars


def screener(settings):
    try:
        import yfinance as yf
        df = yf.download(SCREEN_UNIVERSE + ["SPY"], period="1y", interval="1d",
                         auto_adjust=False, group_by="ticker", threads=True, progress=False)
    except Exception:
        return {"movers": [], "setups": [], "note": "screener feed unavailable"}

    def series(sym, field):
        try:
            return [x for x in df[sym][field].tolist() if x == x]
        except Exception:
            return []

    spy_c = series("SPY", "Close")
    spy3 = _ret_pct(spy_c, 63) if spy_c else None
    movers, setups, bulk_px = [], [], {}
    for sym in SCREEN_UNIVERSE:
        closes, highs = series(sym, "Close"), series(sym, "High")
        lows, vols = series(sym, "Low"), series(sym, "Volume")
        if len(closes) < 60 or len(vols) < 22:
            continue
        if closes[-1] <= 0 or not (lows[-1] <= closes[-1] <= highs[-1]):
            continue
        bulk_px[sym] = closes[-1]
        try:
            mv, st = _screen_one(sym, closes, highs, lows, vols, spy3)
            if mv["price"] >= 5:
                movers.append(mv)
            setups.extend(st)
        except Exception:
            continue
    movers = [m for m in movers if m.get("rvol")]
    movers.sort(key=lambda m: m["rvol"], reverse=True)
    movers, setups = movers[:8], setups[:10]
    import datafeed
    cache = {}

    def vclose(sym):
        if sym not in cache:
            try:
                b = datafeed.get_verified_history(sym, settings)
                cache[sym] = (b[-1]["close"], b[-2]["close"]) if b and len(b) > 1 else None
            except Exception:
                cache[sym] = None
        return cache[sym]

    def ok(sym):
        vc = vclose(sym)
        if not vc:
            return None
        vlast, vprev = vc
        bp = bulk_px.get(sym)
        if bp and vlast and abs(bp - vlast) / vlast > 0.02:
            return None
        return (round(vlast, 2), round((vlast / vprev - 1) * 100, 2))

    clean_movers = []
    for m in movers:
        v = ok(m["symbol"])
        if v:
            m["price"], m["change_pct"] = v[0], v[1]
            clean_movers.append(m)
    clean_setups = [x for x in setups if ok(x["symbol"])]
    searchable = {}
    for _sym in SCREEN_UNIVERSE:
        _b = _bars_from_df(df, _sym)
        if len(_b) < 60:
            continue
        try:
            _full = compute_instrument(_sym, UNIVERSE_NAMES.get(_sym, _sym), "stock", _b, settings)
            _slim = {k: _full[k] for k in ("symbol", "name", "type", "verified", "as_of", "ohlc",
                     "change_pct", "structure", "atr14", "read", "bull_trigger", "bear_trigger",
                     "levels_above", "levels_below", "ma", "fib") if k in _full}
            _slim["history"] = _full["history"][-60:]
            searchable[_sym] = _slim
        except Exception:
            continue
    out = {"movers": clean_movers, "setups": clean_setups, "note": "", "_searchable": searchable}
    if not out["movers"] and not out["setups"]:
        out["note"] = "No verified movers or setups this scan."
    return out


def screener_sample():
    return {"movers": [
        {"symbol": "NVDA", "change_pct": 3.1, "rvol": 2.4, "price": 172.4},
        {"symbol": "PLTR", "change_pct": -4.5, "rvol": 3.1, "price": 62.3},
        {"symbol": "COIN", "change_pct": 5.8, "rvol": 2.8, "price": 310.0},
        {"symbol": "AMD", "change_pct": 2.2, "rvol": 2.0, "price": 168.0}],
        "setups": [
        {"symbol": "MSFT", "setup": "trend reclaim", "detail": "back above 200-SMA"},
        {"symbol": "AVGO", "setup": "breakout", "detail": "20-day high on 1.8x vol"},
        {"symbol": "META", "setup": "RS leader", "detail": "+7.2% vs SPY, near highs"},
        {"symbol": "AMZN", "setup": "golden pocket", "detail": "0.618 retrace"}],
        "note": ""}


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
        "history": [[b["date"], round(b["open"], 2), round(b["high"], 2), round(b["low"], 2), round(b["close"], 2), int(b.get("volume", 0) or 0)] for b in bars[-180:]],
    }


def get_bars(symbol, mode, settings):
    if mode == "sample":
        return sample_data.generate(symbol)
    import datafeed
    return datafeed.get_verified_history(symbol, settings)


def instrument_flags(i):
    """Notable, computable 'what changed' signals for a verified instrument."""
    flags = []
    ohlc = i.get("ohlc", {})
    close, hi, lo = ohlc.get("close"), ohlc.get("high"), ohlc.get("low")
    chg, atr = i.get("change_pct"), i.get("atr14")
    if close is None:
        return flags
    if chg is not None and abs(chg) >= 3:
        flags.append({"k": "move", "t": f"{('+' if chg > 0 else '')}{chg}% day"})

    def _state(p):
        if not p or not close:
            return None
        if lo is not None and hi is not None and lo <= p <= hi:
            return "tag"
        return "near" if abs(close - p) / close <= 0.0075 else None

    def _flag_levels(zlist, kind):
        for z in (zlist or []):
            if z.get("score", 0) < 2:        # only confluence (key) levels
                continue
            st = _state(z.get("price")); ev = (z.get("evidence") or [""])[0]
            if st == "tag":
                flags.append({"k": "tag", "t": f"tagged {kind} {z['price']:.2f}" + (f" ({ev})" if ev else "")}); return
            if st == "near":
                flags.append({"k": "near", "t": f"testing {kind} {z['price']:.2f}"}); return

    _flag_levels(i.get("levels_above"), "resistance")
    _flag_levels(i.get("levels_below"), "support")
    for c in (i.get("changed") or []):
        if "EMA" in c or "SMA" in c:
            flags.append({"k": "ma", "t": c})
    pos = (i.get("fundamentals") or {}).get("pos52")
    if pos is not None:
        if pos >= 95:
            flags.append({"k": "hi", "t": "near 52-wk high"})
        elif pos <= 5:
            flags.append({"k": "lo", "t": "near 52-wk low"})
    return flags


def _market_phase(now_utc):
    """Rough US market phase by wall clock (ET = UTC-4 in summer/EDT)."""
    import datetime as _dt
    et = now_utc - _dt.timedelta(hours=4)
    if et.weekday() >= 5:
        return "closed"
    mins = et.hour * 60 + et.minute
    if 4 * 60 <= mins < 9 * 60 + 30:
        return "pre-market"
    if 9 * 60 + 30 <= mins < 16 * 60:
        return "live"
    if 16 * 60 <= mins < 20 * 60:
        return "after-hours"
    return "closed"


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

    batch_df = None
    if args.mode == "live":
        try:
            import yfinance as yf
            _syms = [s for _t, s in universe]
            batch_df = yf.download(_syms, period="2y", interval="1d", auto_adjust=False,
                                   group_by="ticker", threads=True, progress=False)
        except Exception:
            batch_df = None

    instruments, problems = [], []
    for typ, sym in universe:
        try:
            try:
                bars = get_bars(sym, args.mode, settings)
            except Exception as _e_primary:
                bars = _bars_from_df(batch_df, sym) if batch_df is not None else []
                if not bars:
                    raise _e_primary
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

    alerts = []
    for _i in instruments:
        if not _i.get("verified"):
            continue
        _fl = instrument_flags(_i)
        if _fl:
            _i["flags"] = _fl
            alerts.append({"symbol": _i["symbol"], "name": _i.get("name", _i["symbol"]), "flags": _fl})

    # live / pre-market quote per verified name (freshest price; EOD levels unchanged)
    if args.mode == "live":
        try:
            import yfinance as yf
            _vs = [i["symbol"] for i in instruments if i.get("verified")]
            if _vs:
                _intr = yf.download(_vs, period="1d", interval="1m", prepost=True,
                                    group_by="ticker", threads=True, progress=False)
                for _i in instruments:
                    if not _i.get("verified"):
                        continue
                    _sym = _i["symbol"]
                    try:
                        _ser = (_intr[_sym]["Close"] if len(_vs) > 1 else _intr["Close"]).dropna()
                        if len(_ser):
                            _lp = float(_ser.iloc[-1]); _pc = _i.get("ohlc", {}).get("close")
                            if _lp > 0 and _pc:
                                _i["live"] = {"price": round(_lp, 2),
                                              "change_pct": round((_lp / _pc - 1) * 100, 2),
                                              "phase": _market_phase(datetime.now(timezone.utc))}
                    except Exception:
                        pass
        except Exception:
            pass

    as_of = max([i.get("as_of", "") for i in instruments if i.get("as_of")] or [""])
    scr = screener(settings) if args.mode == "live" else screener_sample()
    searchable = scr.pop("_searchable", {}) if isinstance(scr, dict) else {}
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
        "fed_econ": fed_econ_live(settings) if args.mode == "live" else fed_econ_sample(),
        "instruments": instruments,
        "alerts": alerts,
        "screener": scr,
        "searchable": searchable,
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
