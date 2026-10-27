# Real Estate Pricing Platform

Predictive real-estate pricing: enter a property's details and its asking price, get a fair estimated price with a range, a verdict (overpriced / fair / opportunity), a 24-month district price trend, and comparable sales.

Stack: Flask, SQLite, scikit-learn, vanilla HTML/CSS/JS, Chart.js and Leaflet (both bundled, no CDN). Arabic-first RTL UI.

Pages: **/** estimate (form, interactive district map, result) and **/history** (your past estimates).

> **Demo data notice.** `data/properties_synthetic.csv` is **fabricated** demo data (7 districts of Mansoura, 2,725 sales). The UI shows a banner while the database is flagged as synthetic. Model accuracy figures below describe the synthetic data only and say nothing about real-market accuracy. Load real transactions before relying on any number.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py                                          # http://127.0.0.1:5000
```

The repository ships with a built database (`db/real_estate.db`) and a trained model (`ml/model_v1.joblib`), so it runs immediately. To rebuild everything from scratch:

```bash
python ml/generate_data.py      # fabricate demo CSV (skip when using real data)
python db/init_db.py            # create SQLite + load CSV
python ml/train.py              # train, evaluate, export model + metrics
python -m pytest                # 19 tests
```

## Using real data

1. Prepare a CSV with columns: `district, city, area_m2, age_years, rooms, bathrooms, floor, finishing, price, sale_date`
   (`finishing` in `none | semi | full | luxury`, `sale_date` as `YYYY-MM-DD`, `price` is the closed sale price).
2. `python db/init_db.py your_data.csv --source real` (removes the demo banner).
3. `python ml/train.py`, then restart the app.

Prefer closed-sale prices over advertised prices; advertised prices are usually higher. If you scrape listings, check each site's terms of service first.

## Project layout

```
app.py              Flask app factory + REST API
config.py           Settings (name, thresholds, limits, paths)
valuation.py        Pure logic: diff %, verdict, confidence, rounding, forecast
ml/                 generate_data.py, train.py, model_v1.joblib, metrics.json
db/                 schema.sql, init_db.py, real_estate.db
data/               properties_synthetic.csv
templates/, static/ Single-page UI (css, js, bundled Chart.js and fonts)
tests/              API and logic tests (pytest)
```

## API

| Endpoint | Description |
|---|---|
| `GET /api/meta` | Cities, districts (with sales counts), finishing options, limits, thresholds, data source |
| `POST /api/predict` | Body: `city, district, area_m2, age_years, rooms, bathrooms, floor, finishing, asking_price`. Returns `predicted, range, asking_price, diff_pct, diff_amount, verdict, confidence, district_sales, per_m2` |
| `GET /api/trend/<district>?city=` | Monthly average price per m² for 24 months plus a 3-month linear forecast |
| `GET /api/comparables?district=&city=&area=` | Up to 5 similar sales from the last 12 months |
| `GET /api/history?page=&verdict=` | Your past estimates (10 per page), filter by verdict, plus summary counts |
| `DELETE /api/history/<id>` | Delete one of your estimates |
| `DELETE /api/history` | Clear all of your estimates |

Validation errors return `400` with `{error, fields: {name: message}}`; an unknown district returns `404`.

## How the estimate works

- Features: district, finishing (one-hot), area, age, rooms, bathrooms, floor, sale month. Target: `log(price)`.
- `ml/train.py` trains Linear Regression, Random Forest and Gradient Boosting on an 80/20 split and keeps the lowest test MAE. Current run (synthetic data): Gradient Boosting, MAPE about 6%, R² about 0.95.
- Price range = prediction x the 10th/90th percentile of actual/predicted ratios on the test set (80% interval).
- `diff % = (asking - predicted) / predicted x 100`. Above +10% = overpriced, below -10% = opportunity, otherwise fair (`config.py`).
- Confidence by number of district sales: under 30 low, under 100 medium, otherwise high.
- Predictions always use the latest month seen in training. Retrain regularly as the market moves.

## Map

The map shows one circle per district (darker = higher average price per m² over the last 12 months; tooltip shows price and number of sales). Clicking a district selects it in the form, and picking a district in the form highlights it on the map. The dropdown stays the primary control, so the form works without the map.

- District coordinates in `db/init_db.py` are approximate placeholders. Replace them with accurate centroids for your real districts (or add `lat`/`lng` per district when loading real data).
- Tiles come from OpenStreetMap by default (`MAP_TILE_URL`, `MAP_ATTRIBUTION`). That server is fine for demos and light use; use a tile provider suited to your traffic before going public, and keep the attribution.
- If the map libraries or tiles cannot load, the rest of the page keeps working.

## History

Each visitor gets an anonymous signed cookie; estimates are stored with that id, so a visitor only sees and deletes their own history. There are no accounts and no personal data. Set a long random `SECRET_KEY` in production (the default is for development only), otherwise cookies can be forged and visitors could be impersonated. Clearing cookies starts a fresh history. Databases created before this feature are upgraded automatically on startup.

## Configuration

Environment variables: `PLATFORM_NAME` (working name is "سعّر"), `SECRET_KEY`, `DB_PATH`, `MODEL_PATH`, `METRICS_PATH`, `MAP_TILE_URL`, `MAP_ATTRIBUTION`. Thresholds and limits are in `config.py`.

## Deployment notes

Use a production server (`gunicorn "app:create_app()"`), keep debug off, and back up `db/real_estate.db`. Render or PythonAnywhere work for a prototype. The bundled model was trained with scikit-learn 1.9.1; keep that version pinned when loading it, or retrain the model after changing versions.

## Not implemented yet

English UI toggle, and the extra features from the design doc (rental yield, alerts, office accounts, PDF export beyond the browser's print dialog). The map is a district picker, not a free-form pin: the model predicts per district, not per exact coordinate.
