"""Train, evaluate and export the price model.

Reads properties from SQLite, trains Linear Regression / Random Forest /
Gradient Boosting on log(price), keeps the model with the lowest test MAE,
and writes ml/model_v1.joblib + ml/metrics.json.
"""
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import DB_PATH, METRICS_PATH, MODEL_PATH  # noqa: E402

CAT = ["district", "finishing"]
NUM = ["area_m2", "age_years", "rooms", "bathrooms", "floor", "month_idx"]
FEATURES = CAT + NUM


def load_frame(db_path=DB_PATH) -> pd.DataFrame:
    con = sqlite3.connect(db_path)
    df = pd.read_sql_query("""SELECT d.name AS district, p.area_m2, p.age_years, p.rooms, p.bathrooms,
                                     p.floor, p.finishing, p.price, p.sale_date
                              FROM properties p JOIN districts d ON d.id = p.district_id""", con)
    con.close()
    d = pd.to_datetime(df["sale_date"])
    df["month_idx"] = (d.dt.year - 2023) * 12 + d.dt.month - 1   # months since 2023-01
    return df


def make_pipeline(regressor) -> Pipeline:
    pre = ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore"), CAT),
                             ("num", "passthrough", NUM)])
    return Pipeline([("pre", pre),
                     ("model", TransformedTargetRegressor(regressor=regressor, func=np.log, inverse_func=np.exp))])


def main():
    df = load_frame()
    X, y = df[FEATURES], df["price"]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)

    candidates = {
        "linear_regression": LinearRegression(),
        "random_forest": RandomForestRegressor(n_estimators=300, min_samples_leaf=2, random_state=42, n_jobs=-1),
        "gradient_boosting": GradientBoostingRegressor(n_estimators=400, learning_rate=0.05, max_depth=3, random_state=42),
    }
    results, fitted = {}, {}
    for name, reg in candidates.items():
        pipe = make_pipeline(reg).fit(X_tr, y_tr)
        pred = pipe.predict(X_te)
        results[name] = {"mae": round(float(mean_absolute_error(y_te, pred))),
                         "mape_pct": round(float(mean_absolute_percentage_error(y_te, pred)) * 100, 2),
                         "r2": round(float(r2_score(y_te, pred)), 4)}
        fitted[name] = pipe
        print(f"{name:20s} {results[name]}")

    best = min(results, key=lambda k: results[k]["mae"])
    pipe = fitted[best]
    ratio = (y_te / pipe.predict(X_te)).to_numpy()
    metrics = {
        "selected_model": best,
        "results": results,
        "range_ratio_q10": round(float(np.quantile(ratio, 0.10)), 4),   # 80% interval of actual/predicted
        "range_ratio_q90": round(float(np.quantile(ratio, 0.90)), 4),
        "latest_month_idx": int(df["month_idx"].max()),
        "n_rows": int(len(df)),
        "district_counts": df["district"].value_counts().to_dict(),
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, MODEL_PATH)
    METRICS_PATH.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"selected: {best} -> {MODEL_PATH}")


if __name__ == "__main__":
    main()
