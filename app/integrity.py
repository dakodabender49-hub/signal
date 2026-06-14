"""
integrity.py - The accuracy guarantee for SIGNAL.

Every number is untrusted until it passes these gates. The rule is FAIL-CLOSED:
if a value cannot be verified, it is withheld (None / "unverified") rather than
guessed. Omission over error, always.
"""
from __future__ import annotations
from datetime import date, datetime
from typing import Optional, Tuple

DEFAULT_TOLERANCE_PCT = 0.001  # 0.1% max disagreement between price sources


def validate_ohlc(bar: dict) -> Tuple[bool, str]:
    """OHLC invariants: low <= open,close <= high; no negatives; sane volume."""
    try:
        o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]
    except (KeyError, TypeError):
        return False, "missing OHLC fields"
    if any(x is None for x in (o, h, l, c)):
        return False, "null OHLC field"
    if any(x < 0 for x in (o, h, l, c)):
        return False, "negative price"
    if not (l <= min(o, c) and max(o, c) <= h):
        return False, "OHLC invariant violated (need L<=O,C<=H)"
    if bar.get("volume", 0) < 0:
        return False, "negative volume"
    return True, "ok"


def validate_series(bars: list) -> Tuple[bool, str]:
    """Non-empty, each bar valid, strictly increasing dates, no duplicates."""
    if not bars:
        return False, "empty series"
    seen = set()
    prev_d = None
    for b in bars:
        ok, why = validate_ohlc(b)
        if not ok:
            return False, f"{b.get('date','?')}: {why}"
        d = b.get("date")
        if d in seen:
            return False, f"duplicate date {d}"
        seen.add(d)
        if prev_d is not None and d is not None and d <= prev_d:
            return False, f"timestamps not increasing at {d}"
        prev_d = d
    return True, "ok"


def plausible_move(prev_close, close, max_pct: float = 0.30) -> Tuple[bool, str]:
    """Flag day-over-day moves beyond a circuit-breaker-ish bound for review."""
    if prev_close in (None, 0):
        return True, "no prior close"
    pct = abs(close - prev_close) / prev_close
    if pct > max_pct:
        return False, f"implausible move {pct*100:.1f}%"
    return True, "ok"


def reconcile_close(close_a: Optional[float], close_b: Optional[float],
                    tol: float = DEFAULT_TOLERANCE_PCT) -> Tuple[Optional[float], str]:
    """Compare a close from two independent sources. Agree within tolerance ->
    return mean (verified). Otherwise FAIL CLOSED -> (None, reason)."""
    if close_a is None and close_b is None:
        return None, "no sources"
    if close_a is None or close_b is None:
        return None, "single source only (unverified)"
    mid = (close_a + close_b) / 2.0
    if mid == 0:
        return None, "zero price"
    diff = abs(close_a - close_b) / mid
    if diff > tol:
        return None, f"sources disagree {diff*100:.3f}% (unverified)"
    return mid, "verified"


def check_freshness(as_of: Optional[str], max_age_days: int = 5) -> Tuple[bool, str]:
    """Reject data older than max_age_days (e.g., a stale feed on a holiday)."""
    if not as_of:
        return False, "no timestamp"
    try:
        d = datetime.strptime(as_of, "%Y-%m-%d").date()
    except ValueError:
        return False, f"bad date {as_of}"
    age = (date.today() - d).days
    if age > max_age_days:
        return False, f"stale ({age}d old)"
    return True, "ok"
