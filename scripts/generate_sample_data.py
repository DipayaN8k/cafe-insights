"""Generate a realistic year of sales for a fictional Mumbai cafe.

The data has patterns planted on purpose so every analysis has something to find:
weekend and holiday lifts, hot days boosting cold drinks, rain boosting hot drinks,
items that are usually bought together, and some messy rows to clean.

Usage: python scripts/generate_sample_data.py [output_dir]
"""

import sys
from pathlib import Path

import holidays
import numpy as np
import pandas as pd

SEED = 42
START, END = "2025-11-01", "2026-10-30"

# item, category, price (INR), unit cost (INR), base popularity weight
MENU = [
    ("Espresso", "Hot Drinks", 120, 25, 8),
    ("Cappuccino", "Hot Drinks", 180, 40, 30),
    ("Cafe Latte", "Hot Drinks", 190, 45, 22),
    ("Masala Chai", "Hot Drinks", 80, 12, 40),
    ("Hot Chocolate", "Hot Drinks", 200, 60, 6),
    ("Iced Latte", "Cold Drinks", 210, 50, 14),
    ("Cold Brew", "Cold Drinks", 220, 45, 6),
    ("Iced Tea", "Cold Drinks", 150, 20, 8),
    ("Mango Smoothie", "Cold Drinks", 230, 80, 5),
    ("Cold Coffee", "Cold Drinks", 190, 45, 24),
    ("Butter Croissant", "Bakery", 150, 55, 26),
    ("Chocolate Muffin", "Bakery", 130, 40, 18),
    ("Banana Bread", "Bakery", 140, 35, 4),
    ("Blueberry Cheesecake", "Desserts", 280, 120, 5),
    ("Veg Sandwich", "Food", 220, 80, 16),
    ("Chicken Sandwich", "Food", 260, 110, 12),
    ("Paneer Wrap", "Food", 240, 95, 13),
    ("Avocado Toast", "Food", 320, 230, 3),
]

# If the first item is ordered, chance the second is added to the same order.
PAIRINGS = {
    "Cappuccino": [("Butter Croissant", 0.35)],
    "Cafe Latte": [("Butter Croissant", 0.20), ("Banana Bread", 0.10)],
    "Masala Chai": [("Veg Sandwich", 0.25)],
    "Cold Coffee": [("Chocolate Muffin", 0.30)],
    "Iced Latte": [("Blueberry Cheesecake", 0.22)],
    "Chicken Sandwich": [("Iced Tea", 0.25)],
}

WEEKDAY_TRAFFIC = {0: 0.82, 1: 0.90, 2: 0.95, 3: 0.97, 4: 1.10, 5: 1.35, 6: 1.30}
# Office crowd skips the cafe on Mondays, so morning bakery sells less that day.
MONDAY_DIP = {"Butter Croissant": 0.75, "Chocolate Muffin": 0.85}

CHANNELS = ["Dine-in", "Takeaway", "Swiggy", "Zomato"]
CHANNEL_P = [0.50, 0.20, 0.17, 0.13]

TYPOS = {
    "Cappuccino": ["cappucino", " Cappuccino ", "CAPPUCCINO"],
    "Masala Chai": ["masala  chai", "Masala chai"],
    "Butter Croissant": ["Butter Croisant", "butter croissant"],
    "Cold Coffee": ["Cold coffee "],
}


def make_weather(dates: pd.DatetimeIndex, rng: np.random.Generator) -> pd.DataFrame:
    doy = dates.day_of_year.to_numpy()
    # Mumbai: hottest in May, cooler in January, monsoon June to September.
    temp = 31.5 + 2.5 * np.sin(2 * np.pi * (doy - 60) / 365) + rng.normal(0, 1.2, len(dates))
    monsoon = np.isin(dates.month, [6, 7, 8, 9])
    rain_day = rng.random(len(dates)) < np.where(monsoon, 0.70, 0.04)
    rain = np.where(rain_day, rng.gamma(1.6, np.where(monsoon, 18, 5)), 0.0)
    temp = temp - np.where(rain > 20, 2.0, 0.0)
    return pd.DataFrame({"date": dates.date, "temp_max_c": temp.round(1), "rain_mm": rain.round(1)})


def item_weights(menu: pd.DataFrame, temp: float, rain: float, weekday: int, hour: int) -> np.ndarray:
    w = menu["weight"].to_numpy(dtype=float).copy()
    cat = menu["category"].to_numpy()
    heat = (temp - 31.5) / 3.0
    w[cat == "Cold Drinks"] *= np.exp(0.35 * heat)
    w[cat == "Hot Drinks"] *= np.exp(-0.15 * heat)
    if rain > 10:
        w[cat == "Hot Drinks"] *= 1.30
        w[cat == "Cold Drinks"] *= 0.75
    if hour < 11:
        w[np.isin(cat, ["Hot Drinks", "Bakery"])] *= 1.6
        w[cat == "Food"] *= 0.6
    elif 12 <= hour <= 15:
        w[cat == "Food"] *= 1.7
    if weekday == 0:
        for item, factor in MONDAY_DIP.items():
            w[menu.index[menu["item"] == item]] *= factor
    return w / w.sum()


def main(out_dir: Path) -> None:
    rng = np.random.default_rng(SEED)
    out_dir.mkdir(parents=True, exist_ok=True)

    menu = pd.DataFrame(MENU, columns=["item", "category", "price", "unit_cost", "weight"])
    dates = pd.date_range(START, END, freq="D")
    weather = make_weather(dates, rng)
    holiday_dates = set(holidays.country_holidays("IN", years=sorted(set(dates.year))))
    price = dict(zip(menu["item"], menu["price"]))

    rows = []
    order_no = 100000
    hours = np.arange(8, 23)
    hour_p = np.array([4, 7, 8, 6, 5, 8, 9, 7, 6, 6, 7, 8, 7, 5, 3], dtype=float)
    hour_p /= hour_p.sum()

    for day, wx in zip(dates, weather.itertuples(index=False)):
        traffic = WEEKDAY_TRAFFIC[day.weekday()]
        if day.date() in holiday_dates:
            traffic *= 1.30
        if wx.rain_mm > 30:
            traffic *= 0.85
        traffic *= 1 + 0.10 * (day - dates[0]).days / len(dates)  # slow growth over the year
        n_orders = rng.poisson(150 * traffic)

        for _ in range(n_orders):
            order_no += 1
            hour = int(rng.choice(hours, p=hour_p))
            ts = day + pd.Timedelta(hours=hour, minutes=int(rng.integers(0, 60)))
            channel = rng.choice(CHANNELS, p=CHANNEL_P)
            p = item_weights(menu, wx.temp_max_c, wx.rain_mm, day.weekday(), hour)

            items = [menu["item"].iat[rng.choice(len(menu), p=p)]]
            for partner, prob in PAIRINGS.get(items[0], []):
                if rng.random() < prob:
                    items.append(partner)
            if rng.random() < 0.18:
                extra = menu["item"].iat[rng.choice(len(menu), p=p)]
                if extra not in items:
                    items.append(extra)

            for item in items:
                qty = 1 if rng.random() < 0.88 else 2
                rows.append((f"ORD{order_no}", ts, item, qty, price[item], channel))

    sales = pd.DataFrame(rows, columns=["order_id", "timestamp", "item", "quantity", "unit_price", "channel"])

    # Make it messy like a real POS export: typos, a few blanks, duplicated rows.
    for clean_name, variants in TYPOS.items():
        idx = sales.index[sales["item"] == clean_name]
        pick = rng.choice(idx, size=int(len(idx) * 0.04), replace=False)
        sales.loc[pick, "item"] = rng.choice(variants, size=len(pick))
    sales["quantity"] = sales["quantity"].astype("Float64")
    sales.loc[rng.choice(sales.index, size=40, replace=False), "quantity"] = pd.NA
    sales = pd.concat([sales, sales.sample(60, random_state=SEED)]).sort_values("timestamp")

    sales.to_csv(out_dir / "sales.csv", index=False)
    menu.drop(columns="weight").to_csv(out_dir / "menu.csv", index=False)
    weather.to_csv(out_dir / "weather.csv", index=False)
    print(f"Wrote {len(sales):,} sales rows, {len(menu)} menu items, {len(weather)} weather days to {out_dir}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "sample_data")
