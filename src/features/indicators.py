"""Deterministic technical indicators grouped into roles (spec section 4)."""

import math
from statistics import fmean, pstdev

WINDOW = 60

ROLES: tuple[str, ...] = (
    "trend",
    "momentum",
    "mean_reversion",
    "volatility",
    "breakout",
)

ROLE_INDICATORS: dict[str, tuple[str, ...]] = {
    "trend": ("trend_slope_bp", "close_vs_sma20_pct", "close_vs_sma60_pct"),
    "momentum": ("ret5_pct", "ret10_pct", "ret20_pct"),
    "mean_reversion": ("zscore20",),
    "volatility": ("vol10_pct", "vol59_pct", "vol_ratio"),
    "breakout": ("range_pos20",),
}

ALL_KEYS: tuple[str, ...] = tuple(k for r in ROLES for k in ROLE_INDICATORS[r])


def _slope_bp(closes: list[float]) -> float:
    """OLS slope of ln(close) on the bar index, in basis points per bar."""
    logs = [math.log(c) for c in closes]
    n = len(logs)
    xm = (n - 1) / 2
    ym = fmean(logs)
    sxx = sum((i - xm) ** 2 for i in range(n))
    sxy = sum((i - xm) * (y - ym) for i, y in enumerate(logs))
    return sxy / sxx * 1e4


def _sma_dev(closes: list[float], n: int) -> float:
    """Percent deviation of the last close from the mean of the last n."""
    return (closes[-1] / fmean(closes[-n:]) - 1) * 100


def _ret(closes: list[float], k: int) -> float:
    """K-bar log return in percent."""
    return math.log(closes[-1] / closes[-1 - k]) * 100


def _vol(closes: list[float], n: int) -> float:
    """Population stdev of the last n one-bar log returns, in percent."""
    rets = [
        math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - n, len(closes))
    ]
    return pstdev(rets) * 100


def compute_indicators(closes: list[float]) -> dict[str, float]:
    """Compute all 11 indicators from exactly 60 closes, rounded to 4 dp.

    Degenerate windows yield neutral values (never NaN or division by zero).
    """
    if len(closes) != WINDOW:
        raise ValueError(f"expected exactly {WINDOW} closes, got {len(closes)}")
    last20 = closes[-20:]
    sd20 = pstdev(last20)
    z = (closes[-1] - fmean(last20)) / sd20 if sd20 > 0 else 0.0
    lo, hi = min(last20), max(last20)
    pos = (closes[-1] - lo) / (hi - lo) if hi > lo else 0.5
    vol10, vol59 = _vol(closes, 10), _vol(closes, 59)
    ratio = vol10 / vol59 if vol59 > 0 else 1.0
    raw = {
        "trend_slope_bp": _slope_bp(closes),
        "close_vs_sma20_pct": _sma_dev(closes, 20),
        "close_vs_sma60_pct": _sma_dev(closes, 60),
        "ret5_pct": _ret(closes, 5),
        "ret10_pct": _ret(closes, 10),
        "ret20_pct": _ret(closes, 20),
        "zscore20": z,
        "vol10_pct": vol10,
        "vol59_pct": vol59,
        "vol_ratio": ratio,
        "range_pos20": pos,
    }
    # round() can yield -0.0; adding 0.0 normalises it to 0.0
    return {k: round(v, 4) + 0.0 for k, v in raw.items()}


def role_state(closes: list[float], role: str) -> dict[str, float]:
    """Return only the indicators belonging to the given role."""
    ind = compute_indicators(closes)
    return {k: ind[k] for k in ROLE_INDICATORS[role]}


def all_state(closes: list[float]) -> dict[str, float]:
    """Return the union of all role indicators in fixed key order."""
    ind = compute_indicators(closes)
    return {k: ind[k] for k in ALL_KEYS}


def feature_vector(closes: list[float]) -> list[float]:
    """Return all indicator values in ALL_KEYS order."""
    return list(all_state(closes).values())
