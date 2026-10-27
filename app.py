"""Flask application: REST API + single-page UI for the real-estate pricing platform."""
import json
import sqlite3
import uuid

import joblib
import pandas as pd
from flask import Flask, g, jsonify, render_template, request, session

import config
from valuation import confidence_level, diff_pct, linear_forecast, round_price, verdict

FIELD_LABELS = {
    "city": "المدينة", "district": "الحي", "area_m2": "المساحة", "age_years": "عمر العقار",
    "rooms": "عدد الغرف", "bathrooms": "عدد الحمامات", "floor": "الدور",
    "finishing": "التشطيب", "asking_price": "السعر المعروض",
}


def ensure_schema(db_path: str) -> None:
    """Upgrade databases created before the history feature (adds predictions.session_id)."""
    con = sqlite3.connect(db_path)
    cols = [r[1] for r in con.execute("PRAGMA table_info(predictions)")]
    if cols and "session_id" not in cols:
        con.execute("ALTER TABLE predictions ADD COLUMN session_id TEXT")
    if cols:
        con.execute("CREATE INDEX IF NOT EXISTS idx_predictions_session ON predictions(session_id, id)")
    con.commit()
    con.close()


def visitor_id() -> str:
    """Anonymous per-browser id stored in a signed cookie (no accounts, no personal data)."""
    if "sid" not in session:
        session["sid"] = uuid.uuid4().hex
    session.permanent = True
    return session["sid"]


def create_app(overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        PLATFORM_NAME=config.PLATFORM_NAME, DB_PATH=str(config.DB_PATH),
        MODEL_PATH=str(config.MODEL_PATH), METRICS_PATH=str(config.METRICS_PATH),
        JSON_AS_ASCII=False, SECRET_KEY=config.SECRET_KEY,
        PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 365,
        SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_HTTPONLY=True,
    )
    if overrides:
        app.config.update(overrides)

    ensure_schema(app.config["DB_PATH"])
    model = joblib.load(app.config["MODEL_PATH"])
    with open(app.config["METRICS_PATH"], encoding="utf-8") as fh:
        metrics = json.load(fh)

    # ---------------------------------------------------------------- db
    def db() -> sqlite3.Connection:
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DB_PATH"])
            g.db.row_factory = sqlite3.Row
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        con = g.pop("db", None)
        if con is not None:
            con.close()

    def district_row(name: str, city: str | None):
        if city:
            return db().execute("SELECT id, name, city FROM districts WHERE name=? AND city=?", (name, city)).fetchone()
        return db().execute("SELECT id, name, city FROM districts WHERE name=?", (name,)).fetchone()

    def district_sales(district_id: int) -> int:
        return db().execute("SELECT COUNT(*) FROM properties WHERE district_id=?", (district_id,)).fetchone()[0]

    def latest_month() -> str:
        return db().execute("SELECT MAX(substr(sale_date,1,7)) FROM properties").fetchone()[0]

    # ---------------------------------------------------------------- pages
    @app.get("/")
    def index():
        return render_template("index.html", platform=app.config["PLATFORM_NAME"], active="estimate")

    @app.get("/history")
    def history_page():
        return render_template("history.html", platform=app.config["PLATFORM_NAME"], active="history")

    # ---------------------------------------------------------------- api
    @app.get("/api/meta")
    def meta():
        end = latest_month()
        y, m = int(end[:4]), int(end[5:7])
        t = y * 12 + (m - 1) - (config.PRICE_WINDOW_MONTHS - 1)
        since = f"{t // 12}-{t % 12 + 1:02d}"
        rows = db().execute("""SELECT d.name, d.city, d.lat, d.lng, COUNT(p.id) AS sales,
                                      AVG(CASE WHEN substr(p.sale_date,1,7) >= ? THEN p.price / p.area_m2 END) AS avg_ppm
                               FROM districts d LEFT JOIN properties p ON p.district_id = d.id
                               GROUP BY d.id ORDER BY d.city, sales DESC""", (since,)).fetchall()
        cities: dict[str, list] = {}
        for r in rows:
            cities.setdefault(r["city"], []).append({
                "name": r["name"], "sales": r["sales"], "lat": r["lat"], "lng": r["lng"],
                "avg_ppm": round(r["avg_ppm"]) if r["avg_ppm"] else None})
        src = db().execute("SELECT value FROM meta WHERE key='data_source'").fetchone()
        best = metrics["results"][metrics["selected_model"]]
        return jsonify(
            platform=app.config["PLATFORM_NAME"],
            cities=[{"name": c, "districts": d} for c, d in cities.items()],
            finishing=config.FINISHING_OPTIONS,
            limits=config.LIMITS,
            data_source=src[0] if src else "unknown",
            thresholds={"overpriced_above": config.OVERPRICED_ABOVE_PCT,
                        "opportunity_below": config.OPPORTUNITY_BELOW_PCT},
            model={"name": metrics["selected_model"], "mape_pct": best["mape_pct"]},
            map={"tiles": config.MAP_TILE_URL, "attribution": config.MAP_ATTRIBUTION,
                 "center": list(config.MAP_CENTER), "zoom": config.MAP_ZOOM},
        )

    def validate(data: dict):
        errors, clean = {}, {}
        for f in ("city", "district", "finishing"):
            v = data.get(f)
            if not isinstance(v, str) or not v.strip():
                errors[f] = f"{FIELD_LABELS[f]} مطلوب."
            else:
                clean[f] = v.strip()
        if clean.get("finishing") and clean["finishing"] not in config.FINISHING_OPTIONS:
            errors["finishing"] = "مستوى التشطيب غير مدعوم."
        for f, (lo, hi) in config.LIMITS.items():
            try:
                v = float(data[f])
                if v != v or not (lo <= v <= hi):
                    raise ValueError
                clean[f] = v if f == "area_m2" else int(v)
            except (KeyError, TypeError, ValueError):
                errors[f] = f"{FIELD_LABELS[f]} لازم يكون رقم بين {lo} و{hi}."
        try:
            p = float(data["asking_price"])
            if not (0 < p < 1e10):
                raise ValueError
            clean["asking_price"] = p
        except (KeyError, TypeError, ValueError):
            errors["asking_price"] = f"{FIELD_LABELS['asking_price']} لازم يكون رقم أكبر من صفر."
        return clean, errors

    @app.post("/api/predict")
    def predict():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="الطلب لازم يكون JSON صحيح."), 400
        clean, errors = validate(data)
        if errors:
            return jsonify(error="في بيانات ناقصة أو غير صحيحة.", fields=errors), 400
        d = district_row(clean["district"], clean["city"])
        if d is None:
            return jsonify(error="الحي ده غير مدعوم حاليًا.", fields={"district": "اختار حي من القائمة."}), 404

        row = pd.DataFrame([{
            "district": clean["district"], "finishing": clean["finishing"], "area_m2": clean["area_m2"],
            "age_years": clean["age_years"], "rooms": clean["rooms"], "bathrooms": clean["bathrooms"],
            "floor": clean["floor"], "month_idx": metrics["latest_month_idx"],
        }])
        raw = float(model.predict(row)[0])
        predicted = round_price(raw)
        low = round_price(raw * metrics["range_ratio_q10"])
        high = round_price(raw * metrics["range_ratio_q90"])
        asking = clean["asking_price"]
        diff = diff_pct(asking, predicted)
        verd = verdict(diff)
        n_sales = district_sales(d["id"])

        db().execute("""INSERT INTO predictions (input_json, predicted_price, asking_price, diff_pct, verdict, session_id)
                        VALUES (?,?,?,?,?,?)""",
                     (json.dumps(clean, ensure_ascii=False), predicted, asking, diff, verd, visitor_id()))
        db().commit()

        area = clean["area_m2"]
        return jsonify(
            predicted=predicted, range=[low, high], asking_price=round(asking),
            diff_pct=round(diff, 1), diff_amount=round(asking - predicted), verdict=verd,
            confidence=confidence_level(n_sales), district_sales=n_sales,
            per_m2={"predicted": round(predicted / area), "asking": round(asking / area)},
        )

    @app.get("/api/trend/<district>")
    def trend(district):
        d = district_row(district, request.args.get("city"))
        if d is None:
            return jsonify(error="الحي ده غير مدعوم حاليًا."), 404
        end = latest_month()
        y, m = int(end[:4]), int(end[5:7])

        def shift(k):  # month label k months after (y, m)
            t = y * 12 + (m - 1) + k
            return f"{t // 12}-{t % 12 + 1:02d}"

        months = [shift(k) for k in range(-(config.TREND_MONTHS - 1), 1)]
        rows = db().execute("""SELECT substr(sale_date,1,7) AS ym, AVG(price/area_m2) AS avg_ppm, COUNT(*) AS n
                               FROM properties WHERE district_id=? AND substr(sale_date,1,7) >= ?
                               GROUP BY ym""", (d["id"], months[0])).fetchall()
        by = {r["ym"]: r["avg_ppm"] for r in rows}
        values = [round(by[mo]) if mo in by else None for mo in months]
        fc_months = [shift(k) for k in range(1, config.FORECAST_MONTHS + 1)]
        return jsonify(district=d["name"], city=d["city"], months=months, avg_price_m2=values,
                       forecast_months=fc_months,
                       forecast_avg_price_m2=linear_forecast(values, config.FORECAST_MONTHS))

    @app.get("/api/comparables")
    def comparables():
        d = district_row(request.args.get("district", ""), request.args.get("city"))
        if d is None:
            return jsonify(error="الحي ده غير مدعوم حاليًا."), 404
        try:
            area = float(request.args.get("area", ""))
        except ValueError:
            return jsonify(error="المساحة لازم تكون رقم."), 400
        end = latest_month()
        y, m = int(end[:4]), int(end[5:7])
        t = y * 12 + (m - 1) - 11
        since = f"{t // 12}-{t % 12 + 1:02d}"
        rows = db().execute("""SELECT area_m2, age_years, rooms, floor, finishing, price, sale_date
                               FROM properties WHERE district_id=? AND substr(sale_date,1,7) >= ?
                               ORDER BY ABS(area_m2 - ?) ASC, sale_date DESC LIMIT ?""",
                            (d["id"], since, area, config.COMPARABLES_LIMIT)).fetchall()
        return jsonify(items=[{
            "area_m2": r["area_m2"], "age_years": r["age_years"], "rooms": r["rooms"], "floor": r["floor"],
            "finishing": r["finishing"], "price": round(r["price"]), "price_per_m2": round(r["price"] / r["area_m2"]),
            "sale_date": r["sale_date"],
        } for r in rows])

    VERDICTS = ("overpriced", "fair", "opportunity")

    @app.get("/api/history")
    def history():
        sid = visitor_id()
        try:
            page = max(1, int(request.args.get("page", 1)))
            size = min(50, max(1, int(request.args.get("per_page", config.HISTORY_PAGE_SIZE))))
        except ValueError:
            return jsonify(error="رقم الصفحة غير صحيح."), 400
        flt = request.args.get("verdict")
        if flt and flt not in VERDICTS:
            return jsonify(error="قيمة الفلتر غير صحيحة."), 400

        counts = {r["verdict"]: r["n"] for r in db().execute(
            "SELECT verdict, COUNT(*) AS n FROM predictions WHERE session_id=? GROUP BY verdict", (sid,))}
        summary = {v: counts.get(v, 0) for v in VERDICTS}
        summary["total"] = sum(summary.values())
        total = summary[flt] if flt else summary["total"]
        pages = max(1, -(-total // size))
        page = min(page, pages)

        sql = """SELECT id, input_json, predicted_price, asking_price, diff_pct, verdict, created_at
                 FROM predictions WHERE session_id=?"""
        args: list = [sid]
        if flt:
            sql += " AND verdict=?"; args.append(flt)
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        rows = db().execute(sql, (*args, size, (page - 1) * size)).fetchall()
        items = [{"id": r["id"], "created_at": r["created_at"], "input": json.loads(r["input_json"]),
                  "predicted": round(r["predicted_price"]), "asking_price": round(r["asking_price"]),
                  "diff_pct": round(r["diff_pct"], 1), "verdict": r["verdict"]} for r in rows]
        return jsonify(items=items, page=page, pages=pages, total=total, summary=summary)

    @app.delete("/api/history/<int:pid>")
    def history_delete_one(pid):
        cur = db().execute("DELETE FROM predictions WHERE id=? AND session_id=?", (pid, visitor_id()))
        db().commit()
        if cur.rowcount == 0:
            return jsonify(error="التقدير ده مش موجود."), 404
        return jsonify(deleted=1)

    @app.delete("/api/history")
    def history_clear():
        cur = db().execute("DELETE FROM predictions WHERE session_id=?", (visitor_id(),))
        db().commit()
        return jsonify(deleted=cur.rowcount)

    @app.errorhandler(404)
    def not_found(_e):
        if request.path.startswith("/api/"):
            return jsonify(error="المسار غير موجود."), 404
        return render_template("index.html", platform=app.config["PLATFORM_NAME"], active="estimate"), 404

    @app.errorhandler(500)
    def server_error(_e):
        return jsonify(error="حصل خطأ غير متوقع. حاول مرة تانية."), 500

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
