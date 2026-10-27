"""Create the SQLite database and load properties from a CSV.

Usage: python db/init_db.py [csv_path] [--source synthetic|real]
CSV columns: district, city, area_m2, age_years, rooms, bathrooms, floor, finishing, price, sale_date
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import DB_PATH  # noqa: E402

COORDS = {  # optional coordinates for future map features
    "توريل": (31.0409, 31.3785), "الجمهورية": (31.0364, 31.3807), "المشاية": (31.0450, 31.3700),
    "الجامعة": (31.0460, 31.3580), "قناة السويس": (31.0290, 31.3900),
    "المختلط": (31.0500, 31.3850), "جديلة": (31.0600, 31.3600),
}


def build(db_path=DB_PATH, csv_path=ROOT / "data" / "properties_synthetic.csv", source="synthetic"):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    df = pd.read_csv(csv_path)
    con = sqlite3.connect(db_path)
    con.executescript((ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))
    ids = {}
    for (name, city), _ in df.groupby(["district", "city"]):
        lat, lng = COORDS.get(name, (None, None))
        cur = con.execute("INSERT INTO districts (name, city, lat, lng) VALUES (?,?,?,?)",
                          (name, city, lat, lng))
        ids[(name, city)] = cur.lastrowid
    rows = [(ids[(r.district, r.city)], float(r.area_m2), int(r.age_years), int(r.rooms), int(r.bathrooms),
             int(r.floor), r.finishing, float(r.price), r.sale_date) for r in df.itertuples()]
    con.executemany("""INSERT INTO properties
        (district_id, area_m2, age_years, rooms, bathrooms, floor, finishing, price, sale_date)
        VALUES (?,?,?,?,?,?,?,?,?)""", rows)
    con.execute("INSERT INTO meta (key, value) VALUES ('data_source', ?)", (source,))
    con.commit()
    con.close()
    return len(rows)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    src = "real" if "--source" in sys.argv and sys.argv[sys.argv.index("--source") + 1] == "real" else "synthetic"
    csv = args[0] if args and args[0].endswith(".csv") else ROOT / "data" / "properties_synthetic.csv"
    n = build(csv_path=csv, source=src)
    print(f"loaded {n} properties into {DB_PATH} (source={src})")
