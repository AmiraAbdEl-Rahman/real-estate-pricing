PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS districts (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL,
    city  TEXT NOT NULL,
    lat   REAL,
    lng   REAL,
    UNIQUE (name, city)
);

CREATE TABLE IF NOT EXISTS properties (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    district_id  INTEGER NOT NULL REFERENCES districts(id),
    area_m2      REAL    NOT NULL,
    age_years    INTEGER NOT NULL,
    rooms        INTEGER,
    bathrooms    INTEGER,
    floor        INTEGER,
    finishing    TEXT,
    price        REAL    NOT NULL,
    sale_date    DATE    NOT NULL
);

CREATE TABLE IF NOT EXISTS predictions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    input_json       TEXT NOT NULL,
    predicted_price  REAL NOT NULL,
    asking_price     REAL NOT NULL,
    diff_pct         REAL NOT NULL,
    verdict          TEXT NOT NULL,
    session_id       TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_properties_district_date ON properties(district_id, sale_date);
CREATE INDEX IF NOT EXISTS idx_predictions_session ON predictions(session_id, id);
