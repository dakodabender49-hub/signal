"""
sample_data.py - deterministic, clearly-labeled SAMPLE OHLC for the offline demo.
NOT live market data. Lets the dashboard render before API keys are wired.
Replaced by datafeed.py in live mode.
"""
import random
from datetime import date, timedelta

BASE = {"SPY": 600, "QQQ": 530, "AAPL": 210, "MSFT": 470, "GOOGL": 180,
        "AMZN": 205, "NVDA": 135, "META": 600, "TSLA": 340, "MU": 140}


def _business_days(n, end=None):
    end = end or date.today()
    days = []
    d = end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return list(reversed(days))


def generate(symbol, n=320):
    """Seeded geometric random walk with gentle upward drift. Deterministic per
    symbol so the demo is stable. Guarantees valid OHLC."""
    seed = sum(ord(c) for c in symbol)
    rnd = random.Random(seed)
    price = BASE.get(symbol, 100) * 0.8
    mu, sigma = 0.0006, 0.011
    bars = []
    for d in _business_days(n):
        ret = mu + sigma * rnd.gauss(0, 1)
        price = max(1.0, price * (1 + ret))
        o = round(price * (1 + rnd.uniform(-0.004, 0.004)), 2)
        c = round(price, 2)
        h = round(max(o, c) * (1 + rnd.uniform(0.0003, 0.005)), 2)
        l = round(min(o, c) * (1 - rnd.uniform(0.0003, 0.005)), 2)
        bars.append({"date": d.strftime("%Y-%m-%d"), "open": o, "high": h,
                     "low": l, "close": c, "volume": int(rnd.uniform(2e6, 9e6))})
    return bars
