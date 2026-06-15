"""
datafeed.py - free EOD data with cross-source verification (LIVE mode).

Two keyless free sources, made resilient so the dashboard is never empty just
because one of them is briefly down:
  * yfinance (Yahoo)  - primary (full, reliable history)
  * Stooq (CSV)       - independent cross-check

Policy:
  - both respond & agree within tolerance -> verified
  - both respond & DISAGREE beyond tolerance -> raise (fail-closed, withheld)
  - only one responds -> accept it (one reputable source) so the board shows data
  - neither responds -> raise (withheld)

Runs inside your GitHub Action; not used in sample mode. Both pulled UNADJUSTED
so the cross-check compares like-with-like.
"""
from __future__ import annotations
import csv
import io
import math
from integrity import reconcile_close, validate_series

# A real browser User-Agent: Stooq returns 404 to the default requests UA.
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def _is_nan(v):
    return v is None or (isinstance(v, float) and v != v)


def _stooq_symbol(sym: str) -> str:
    return sym.lower() + ".us"


def fetch_stooq(symbol: str):
    import requests
    url = f"https://stooq.com/q/d/l/?s={_stooq_symbol(symbol)}&i=d"
    r = requests.get(url, timeout=25, headers=UA)
    r.raise_for_status()
    text = (r.text or "").strip()
    low = text.lower()
    if not text or text[0] == "<" or "no data" in low or "exceeded" in low:
        raise ValueError("stooq: no data / rate-limited")
    bars = []
    for row in csv.DictReader(io.StringIO(text)):
        c = row.get("Close")
        if not c or c in ("N/D", "null"):
            continue
        try:
            bars.append({"date": row["Date"],
                         "open": float(row["Open"]), "high": float(row["High"]),
                         "low": float(row["Low"]), "close": float(row["Close"]),
                         "volume": float(row.get("Volume") or 0)})
        except (ValueError, KeyError):
            continue
    if not bars:
        raise ValueError("stooq: empty after parse")
    return bars


def fetch_yf(symbol: str):
    import yfinance as yf
    df = yf.download(symbol, period="2y", interval="1d", auto_adjust=False,
                     progress=False, threads=False)
    if df is None or len(df) == 0:
        raise ValueError("yfinance: empty")
    # recent yfinance returns MultiIndex columns even for one ticker -> flatten
    try:
        if df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)
    except Exception:
        pass
    bars = []
    for idx, row in df.iterrows():
        try:
            o, h, l, c = row["Open"], row["High"], row["Low"], row["Close"]
            if any(_is_nan(x) for x in (o, h, l, c)):
                continue  # skip incomplete bars (e.g. today's forming bar)
            v = row["Volume"]
            bars.append({"date": idx.strftime("%Y-%m-%d"),
                         "open": float(o), "high": float(h),
                         "low": float(l), "close": float(c),
                         "volume": 0.0 if _is_nan(v) else float(v)})
        except (ValueError, KeyError, TypeError):
            continue
    if not bars:
        raise ValueError("yfinance: empty after parse")
    return bars


def get_verified_history(symbol: str, settings: dict):
    """Return a validated EOD series, cross-checked when possible (fail-closed on
    disagreement). Accepts a single reputable source rather than showing nothing."""
    # floor the tolerance at 0.5%: two independent free feeds differ slightly by
    # rounding/adjustment, and we don't want a false "disagreement" to hide data.
    tol = max(settings.get("reconcile_tolerance_pct", 0.005), 0.005)

    series = {}
    for name, fn in (("yfinance", fetch_yf), ("stooq", fetch_stooq)):
        try:
            bars = fn(symbol)
            ok, _ = validate_series(bars)
            if ok:
                series[name] = bars
        except Exception:
            continue

    if not series:
        raise ValueError("no free source returned valid data")

    # cross-check the latest common close when we have both
    if "yfinance" in series and "stooq" in series:
        y = {b["date"]: b["close"] for b in series["yfinance"]}
        s = {b["date"]: b["close"] for b in series["stooq"]}
        common = sorted(set(y) & set(s))
        if common:
            d = common[-1]
            mid, status = reconcile_close(y[d], s[d], tol)
            if mid is None:
                raise ValueError(f"sources disagree on {d}: {status}")

    # prefer the fuller Yahoo series; fall back to Stooq if that's all we have
    return series.get("yfinance") or series.get("stooq")
