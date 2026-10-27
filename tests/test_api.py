import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "db"))

from app import create_app  # noqa: E402
import init_db  # noqa: E402

VALID = {"city": "المنصورة", "district": "الجمهورية", "area_m2": 140, "age_years": 8, "rooms": 3,
         "bathrooms": 2, "floor": 4, "finishing": "full", "asking_price": 2_100_000}


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db_file = tmp_path_factory.mktemp("db") / "test.db"
    init_db.build(db_path=db_file, csv_path=ROOT / "data" / "properties_synthetic.csv")
    app = create_app({"DB_PATH": str(db_file), "TESTING": True})
    return app.test_client()


def test_index_page(client):
    r = client.get("/")
    assert r.status_code == 200 and "تقدير سعر عقار".encode() in r.data


def test_meta(client):
    d = client.get("/api/meta").get_json()
    names = [x["name"] for x in d["cities"][0]["districts"]]
    assert "الجمهورية" in names and d["data_source"] == "synthetic"


def test_predict_ok(client):
    r = client.post("/api/predict", json=VALID)
    d = r.get_json()
    assert r.status_code == 200
    assert d["range"][0] < d["predicted"] < d["range"][1]
    assert d["verdict"] in {"overpriced", "fair", "opportunity"}
    assert d["confidence"] == "high"


def test_predict_verdicts(client):
    base = client.post("/api/predict", json=VALID).get_json()["predicted"]
    assert client.post("/api/predict", json={**VALID, "asking_price": base * 1.25}).get_json()["verdict"] == "overpriced"
    assert client.post("/api/predict", json={**VALID, "asking_price": base * 0.75}).get_json()["verdict"] == "opportunity"
    assert client.post("/api/predict", json={**VALID, "asking_price": base}).get_json()["verdict"] == "fair"


def test_small_district_has_low_confidence(client):
    r = client.post("/api/predict", json={**VALID, "district": "جديلة"}).get_json()
    assert r["confidence"] == "low"


def test_predict_validation(client):
    bad = {k: v for k, v in VALID.items() if k != "district"}
    r = client.post("/api/predict", json=bad)
    assert r.status_code == 400 and "district" in r.get_json()["fields"]
    r = client.post("/api/predict", json={**VALID, "area_m2": -5, "asking_price": 0})
    assert {"area_m2", "asking_price"} <= set(r.get_json()["fields"])
    assert client.post("/api/predict", data="not json").status_code == 400


def test_unknown_district(client):
    assert client.post("/api/predict", json={**VALID, "district": "غير موجود"}).status_code == 404


def test_trend(client):
    d = client.get("/api/trend/الجمهورية?city=المنصورة").get_json()
    assert len(d["months"]) == 24 and len(d["avg_price_m2"]) == 24
    assert len(d["forecast_months"]) == 3 and len(d["forecast_avg_price_m2"]) == 3
    assert client.get("/api/trend/غير_موجود").status_code == 404


def test_comparables(client):
    d = client.get("/api/comparables", query_string={"district": "الجمهورية", "city": "المنصورة", "area": 140}).get_json()
    assert 0 < len(d["items"]) <= 5
    assert client.get("/api/comparables", query_string={"district": "الجمهورية", "area": "abc"}).status_code == 400


def test_meta_has_map_data(client):
    d = client.get("/api/meta").get_json()
    dist = d["cities"][0]["districts"][0]
    assert dist["lat"] and dist["lng"] and dist["avg_ppm"] > 0
    assert d["map"]["tiles"].startswith("https://") and len(d["map"]["center"]) == 2


def test_pages_render(client):
    assert client.get("/history").status_code == 200
    assert "سجل التقديرات".encode() in client.get("/history").data


def test_history_summary_filter_and_pagination(tmp_path):
    db_file = tmp_path / "h.db"
    init_db.build(db_path=db_file, csv_path=ROOT / "data" / "properties_synthetic.csv")
    c = create_app({"DB_PATH": str(db_file), "TESTING": True}).test_client()
    assert c.get("/api/history").get_json()["summary"]["total"] == 0
    base = c.post("/api/predict", json=VALID).get_json()["predicted"]
    for k in range(11):
        c.post("/api/predict", json={**VALID, "asking_price": base * 1.3})
    c.post("/api/predict", json={**VALID, "asking_price": base})
    c.post("/api/predict", json={**VALID, "asking_price": base * 0.7})
    d = c.get("/api/history").get_json()
    assert d["summary"] == {"overpriced": 12, "fair": 1, "opportunity": 1, "total": 14}
    assert len(d["items"]) == 10 and d["pages"] == 2 and d["items"][0]["verdict"] == "opportunity"
    d2 = c.get("/api/history?page=2").get_json()
    assert len(d2["items"]) == 4
    only = c.get("/api/history?verdict=opportunity").get_json()
    assert only["total"] == 1 and only["items"][0]["input"]["district"] == "الجمهورية"
    assert c.get("/api/history?verdict=bogus").status_code == 400
    assert c.get("/api/history?page=abc").status_code == 400
    assert c.get("/api/history?page=99").get_json()["page"] == 2      # clamped


def test_history_is_private_per_visitor_and_deletable(tmp_path):
    db_file = tmp_path / "p.db"
    init_db.build(db_path=db_file, csv_path=ROOT / "data" / "properties_synthetic.csv")
    app = create_app({"DB_PATH": str(db_file), "TESTING": True})
    a, b = app.test_client(), app.test_client()
    a.post("/api/predict", json=VALID); a.post("/api/predict", json=VALID)
    b.post("/api/predict", json=VALID)
    assert a.get("/api/history").get_json()["summary"]["total"] == 2
    assert b.get("/api/history").get_json()["summary"]["total"] == 1
    a_id = a.get("/api/history").get_json()["items"][0]["id"]
    assert b.delete(f"/api/history/{a_id}").status_code == 404          # cannot delete someone else's
    assert a.delete(f"/api/history/{a_id}").status_code == 200
    assert a.get("/api/history").get_json()["summary"]["total"] == 1
    assert a.delete("/api/history").get_json()["deleted"] == 1
    assert a.get("/api/history").get_json()["summary"]["total"] == 0
    assert b.get("/api/history").get_json()["summary"]["total"] == 1     # b untouched


def test_old_database_is_migrated(tmp_path):
    import sqlite3
    db_file = tmp_path / "old.db"
    init_db.build(db_path=db_file, csv_path=ROOT / "data" / "properties_synthetic.csv")
    con = sqlite3.connect(db_file)
    con.executescript("DROP TABLE predictions; CREATE TABLE predictions (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                      "input_json TEXT NOT NULL, predicted_price REAL NOT NULL, asking_price REAL NOT NULL, "
                      "diff_pct REAL NOT NULL, verdict TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);")
    con.close()
    c = create_app({"DB_PATH": str(db_file), "TESTING": True}).test_client()
    assert c.post("/api/predict", json=VALID).status_code == 200
    assert c.get("/api/history").get_json()["summary"]["total"] == 1
