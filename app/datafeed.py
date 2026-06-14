"""
datafeed.py - free EOD data with cross-source verification (LIVE mode).

Two independent free sources:
  * Stooq   - CSV, no API key
  * yfinance - Yahoo, no API key
The latest close is reconciled across both (integrity.reconcile_close). If they
disagree beyond tolerance, the whole series is rejected -> the instrument is
withheld from the brief (fail-closed). Runs inside your GitHub Action; it is NOT
used in sample mode, so the demo never touches the network.

Note on adjustment: both sources are pulled UNADJUSTED so the cross-check
compares like-with-like. For level math across a stock split you would switch
both to split-adjusted; documented here so the comparison stays apples-to-apples.
"""
from __future__ import annotations
import csv
import io
from integrity import reconcile_close, validate_series


def _stooq_symbol(sym: str) -> str:
    return sym.lower() + ".us"


def fetch_stooq(symbol: str):
    import requests
    url = f"https://stooq.com/q/d/l/?s={_stooq_symbol(symbol)}&i=d"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.text)))
    bars = []
    for row in rows:
        if not row.get("Close"):
            continue
        try:
            bars.append({
                "date": row["Date"],
                "open": float(row["Open"]), "high": float(row["High"]),
                "low": float(row["Low"]), "close": float(row["Close"]),
                "volume": float(row.get("Volume") or 0),
            })
        except (ValueError, KeyError):
            continue
    return bars


def fetch_yf(symbol: str):
    import yfinance as yf
    df = yf.download(symbol, period="2y", interval="1d",
                     auto_adjust=False, progress=False)
    bars = []
    for idx, row in df.iterrows():
        bars.append({
            "date": idx.strftime("%Y-%m-%d"),
            "open": float(row["Open"]), "high": float(row["High"]),
            "low": float(row["Low"]), "close": float(row["Close"]),
            "volume": float(row["Volume"]),
        })
    return bars


def get_verified_history(symbol: str, settings: dict):
    """Return a validated, cross-checked EOD series or raise (fail-closed)."""
    tol = settings.get("reconcile_tolerance_pct", 0.001)
    primary = fetch_stooq(symbol)
    if not primary:
        raise ValueError("no primary (stooq) data")
    try:
        secondary = fetch_yf(symbol)
    except Exception as e:  # secondary is best-effort
        secondary = None
    if secondary:
        sec = {b["date"]: b for b in secondary}
        last = primary[-1]
        other = sec.get(last["date"])
        mid, status = reconcile_close(last["close"],
                                      other["close"] if other else None, tol)
        if mid is None:
            raise ValueError(f"latest close not verified: {status}")
    else:
        raise ValueError("only one source available - latest close unverified")
    ok, why = validate_series(primary)
    if not ok:
        raise ValueError(why)
    return primary
