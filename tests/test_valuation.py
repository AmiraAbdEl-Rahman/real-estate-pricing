import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from valuation import confidence_level, diff_pct, linear_forecast, round_price, verdict  # noqa: E402


def test_diff_pct():
    assert round(diff_pct(2_100_000, 1_850_000), 1) == 13.5
    assert diff_pct(900, 1000) == -10.0


def test_verdict_thresholds():
    assert verdict(10.1) == "overpriced"
    assert verdict(10.0) == "fair"
    assert verdict(-10.0) == "fair"
    assert verdict(-10.1) == "opportunity"


def test_confidence_levels():
    assert confidence_level(5) == "low"
    assert confidence_level(30) == "medium"
    assert confidence_level(100) == "high"


def test_round_price():
    assert round_price(1_852_300) == 1_850_000
    assert round_price(1_853_000) == 1_855_000


def test_linear_forecast_and_gaps():
    assert linear_forecast([100, 110, 120, 130], 2) == [140, 150]
    assert linear_forecast([100, None, 120, None, 140], 1) == [150]
    assert linear_forecast([100, 110], 3) == []
