"""Pure helper functions for the valuation logic (easy to unit-test)."""
from config import (CONFIDENCE_LOW_BELOW, CONFIDENCE_MEDIUM_BELOW,
                    OPPORTUNITY_BELOW_PCT, OVERPRICED_ABOVE_PCT, PRICE_ROUNDING_STEP)


def diff_pct(asking: float, predicted: float) -> float:
    """(asking - predicted) / predicted * 100"""
    if predicted <= 0:
        raise ValueError("predicted price must be positive")
    return (asking - predicted) / predicted * 100


def verdict(diff: float) -> str:
    if diff > OVERPRICED_ABOVE_PCT:
        return "overpriced"
    if diff < OPPORTUNITY_BELOW_PCT:
        return "opportunity"
    return "fair"


def confidence_level(n_sales: int) -> str:
    if n_sales < CONFIDENCE_LOW_BELOW:
        return "low"
    if n_sales < CONFIDENCE_MEDIUM_BELOW:
        return "medium"
    return "high"


def round_price(value: float, step: int = PRICE_ROUNDING_STEP) -> int:
    return int(round(value / step) * step)


def linear_forecast(values, horizon):
    """Least-squares line through the last points, extended `horizon` steps.
    `values` may contain None (gaps) - they are skipped."""
    pts = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(pts) < 3 or horizon <= 0:
        return []
    pts = pts[-12:]
    n = len(pts)
    sx = sum(p[0] for p in pts); sy = sum(p[1] for p in pts)
    sxx = sum(p[0] ** 2 for p in pts); sxy = sum(p[0] * p[1] for p in pts)
    den = n * sxx - sx ** 2
    if den == 0:
        return []
    slope = (n * sxy - sx * sy) / den
    intercept = (sy - slope * sx) / n
    start = len(values)
    return [round(intercept + slope * (start + k)) for k in range(horizon)]
