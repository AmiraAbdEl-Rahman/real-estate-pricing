"""Central configuration. Override with environment variables when needed."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

PLATFORM_NAME = os.getenv("PLATFORM_NAME", "سعّر")          # working name, change freely
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "db" / "real_estate.db"))
MODEL_PATH = Path(os.getenv("MODEL_PATH", BASE_DIR / "ml" / "model_v1.joblib"))
METRICS_PATH = Path(os.getenv("METRICS_PATH", BASE_DIR / "ml" / "metrics.json"))

# Verdict thresholds (difference between asking and predicted price, in %)
OVERPRICED_ABOVE_PCT = 10.0
OPPORTUNITY_BELOW_PCT = -10.0

# Confidence tiers by number of training sales in the district
CONFIDENCE_LOW_BELOW = 30
CONFIDENCE_MEDIUM_BELOW = 100

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")   # signs the anonymous visitor cookie
HISTORY_PAGE_SIZE = 10

# Map (Leaflet). The default OpenStreetMap tile server is fine for demos and light use;
# for production traffic use a tile provider that fits your usage and keep the attribution.
MAP_TILE_URL = os.getenv("MAP_TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
MAP_ATTRIBUTION = os.getenv("MAP_ATTRIBUTION", "&copy; OpenStreetMap contributors")
MAP_CENTER = (31.0409, 31.3785)
MAP_ZOOM = 12
PRICE_WINDOW_MONTHS = 12          # window for the per-district average price shown on the map

PRICE_ROUNDING_STEP = 5000        # EGP
TREND_MONTHS = 24
FORECAST_MONTHS = 3
COMPARABLES_LIMIT = 5

# Input validation limits
LIMITS = {
    "area_m2": (20, 1000),
    "age_years": (0, 100),
    "rooms": (1, 15),
    "bathrooms": (1, 10),
    "floor": (0, 60),
}
FINISHING_OPTIONS = ["none", "semi", "full", "luxury"]
