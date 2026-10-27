"""Generate a SYNTHETIC demo dataset (CSV).

The numbers are fabricated for development and demos only. They imitate the
structure of real sales (district effect, age depreciation, finishing, floor,
monthly price growth) but are NOT real market prices.
Replace data/properties_synthetic.csv with real transactions using the same
columns, then run: python db/init_db.py <csv> --source real && python ml/train.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parents[1] / "data" / "properties_synthetic.csv"

# (name, city, base price per m2 in EGP at month 0, number of sales)
DISTRICTS = [
    ("توريل", "المنصورة", 9800, 520),
    ("الجمهورية", "المنصورة", 8400, 560),
    ("المشاية", "المنصورة", 8100, 440),
    ("الجامعة", "المنصورة", 9300, 480),
    ("قناة السويس", "المنصورة", 7200, 400),
    ("المختلط", "المنصورة", 6800, 300),
    ("جديلة", "المنصورة", 5900, 25),      # deliberately small district (low confidence)
]
FINISH = {"none": 0.82, "semi": 0.92, "full": 1.00, "luxury": 1.12}
N_MONTHS = 46                  # month 0 = 2023-01 ... month 45 = 2026-10
MONTHLY_GROWTH = 0.011


def main(seed: int = 42) -> None:
    rng = np.random.default_rng(seed)
    rows = []
    for name, city, base, n in DISTRICTS:
        month = np.minimum((N_MONTHS * rng.beta(1.6, 1.0, n)).astype(int), N_MONTHS - 1)   # more sales recently
        area = np.clip(rng.normal(125, 35, n), 55, 300).round()
        age = np.clip(rng.exponential(9, n), 0, 40).astype(int)
        rooms = np.clip(np.round(area / 42 + rng.normal(0, .5, n)), 1, 6).astype(int)
        baths = np.clip(np.round(rooms / 1.8 + rng.normal(0, .4, n)), 1, 4).astype(int)
        floor = rng.choice(np.arange(0, 11), n, p=[.1, .14, .14, .14, .12, .1, .08, .07, .05, .03, .03])
        fin = rng.choice(list(FINISH), n, p=[.12, .28, .45, .15])
        ppm = (base
               * (1 + MONTHLY_GROWTH) ** month
               * np.exp(-0.011 * age)
               * (area / 120) ** -0.08
               * np.array([FINISH[f] for f in fin])
               * (1 + 0.01 * np.minimum(floor, 6) - 0.05 * (floor == 0))
               * np.exp(rng.normal(0, 0.07, n)))
        price = (ppm * area / 5000).round() * 5000
        for i in range(n):
            y, m = divmod(int(month[i]), 12)
            day = int(rng.integers(1, 28))
            rows.append((name, city, area[i], age[i], rooms[i], baths[i], floor[i], fin[i],
                         price[i], f"{2023 + y}-{m + 1:02d}-{day:02d}"))
    df = pd.DataFrame(rows, columns=["district", "city", "area_m2", "age_years", "rooms",
                                     "bathrooms", "floor", "finishing", "price", "sale_date"])
    OUT.parent.mkdir(exist_ok=True)
    df.to_csv(OUT, index=False, encoding="utf-8")
    print(f"wrote {len(df)} rows -> {OUT}")


if __name__ == "__main__":
    main()
