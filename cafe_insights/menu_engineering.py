"""Menu engineering matrix (Kasavana & Smith method).

Popularity: an item is "high" if its share of units sold is at least 70% of a fair
share (1 / number of items). Profit: an item is "high" if its margin per unit beats
the menu's average margin per unit, weighted by units sold.

Owners see plain names instead of the textbook ones (see GROUPS).
"""

import duckdb
import pandas as pd

from cafe_insights.text import money, nice_amount

POPULARITY_FACTOR = 0.70

# Textbook name -> what an owner sees.
GROUPS = {
    "Star": {"name": "Winners", "icon": "⭐", "meaning": "Sell a lot and earn you a lot.",
             "do": "Keep them exactly as they are and show them first on the menu."},
    "Plowhorse": {"name": "Popular, low profit", "icon": "🐎", "meaning": "Customers love them, but you keep little from each sale.",
                  "do": "Raise the price a little, or make them cheaper to prepare."},
    "Puzzle": {"name": "Hidden gems", "icon": "💎", "meaning": "Earn you a lot per sale, but few people order them.",
               "do": "Recommend them, give them a better spot on the menu, or pair them with a winner."},
    "Dog": {"name": "Under-performers", "icon": "⚠️", "meaning": "Sell little and earn little.",
            "do": "Change the recipe or price, or replace them with something new."},
}
ORDER = ["Star", "Plowhorse", "Puzzle", "Dog"]

CLASS_SQL = """
WITH item_stats AS (
    SELECT s.item,
           m.category,
           SUM(s.quantity)                    AS units,
           SUM(s.revenue)                     AS revenue,
           SUM(s.revenue) / SUM(s.quantity)   AS avg_price,
           m.unit_cost
    FROM sales s
    JOIN menu m USING (item)
    WHERE m.unit_cost IS NOT NULL
    GROUP BY s.item, m.category, m.unit_cost
),
margins AS (
    SELECT *,
           avg_price - unit_cost                         AS unit_margin,
           units * (avg_price - unit_cost)               AS total_margin,
           units / SUM(units) OVER ()                    AS mix_share,
           COUNT(*) OVER ()                              AS n_items
    FROM item_stats
)
SELECT *,
       ? / n_items                                       AS popularity_threshold,
       SUM(total_margin) OVER () / SUM(units) OVER ()    AS margin_threshold
FROM margins
"""


def classify(con: duckdb.DuckDBPyConnection, popularity_factor: float = POPULARITY_FACTOR, currency: str = "₹") -> pd.DataFrame:
    df = con.execute(CLASS_SQL, [popularity_factor]).df()
    if df.empty:
        return df
    days = con.execute("SELECT COUNT(DISTINCT date) FROM sales").fetchone()[0] or 1
    df["units_per_year"] = df["units"] * 365 / days
    df["high_popularity"] = df["mix_share"] >= df["popularity_threshold"]
    df["high_profit"] = df["unit_margin"] >= df["margin_threshold"]
    df["class"] = [
        ("Star" if prof else "Plowhorse") if pop else ("Puzzle" if prof else "Dog")
        for pop, prof in zip(df["high_popularity"], df["high_profit"])
    ]
    df["group"] = df["class"].map(lambda c: GROUPS[c]["name"])
    # Suggested price rise for low-profit popular items: close the gap to the average margin,
    # but never more than 10% of the price in one go.
    gap = (df["margin_threshold"] - df["unit_margin"]).clip(lower=0)
    df["price_rise"] = [nice_amount(min(g, 0.10 * p)) if c == "Plowhorse" else 0.0
                        for g, p, c in zip(gap, df["avg_price"], df["class"])]
    df["extra_per_year"] = df["price_rise"] * df["units_per_year"]
    df["action"] = df.apply(lambda r: _action(r, currency), axis=1)
    rank = {c: i for i, c in enumerate(ORDER)}
    return df.sort_values(["class", "total_margin"], key=lambda s: s.map(rank) if s.name == "class" else -s).reset_index(drop=True)


def _action(row: pd.Series, cur: str) -> str:
    # The group card already says what to do; each line adds only this item's facts.
    sold = f"{row['units']:,.0f} sold"
    keep = f"you keep {money(row['unit_margin'], cur)} from each"
    if row["class"] == "Star":
        return f"{sold}, and {keep}."
    if row["class"] == "Plowhorse":
        return (f"{sold}, but {keep} (average: {money(row['margin_threshold'], cur)}). "
                f"Raising the price by {money(row['price_rise'], cur)} would bring in about "
                f"{money(row['extra_per_year'], cur)} more a year, if the same number sell.")
    if row["class"] == "Puzzle":
        return f"{keep.capitalize()}, but only {sold}."
    return f"Only {sold}, and {keep}."


def items_without_cost(con: duckdb.DuckDBPyConnection) -> list[str]:
    return con.execute("""
        SELECT DISTINCT s.item FROM sales s
        LEFT JOIN menu m USING (item)
        WHERE m.unit_cost IS NULL
        ORDER BY 1
    """).df()["item"].tolist()


def summary(matrix: pd.DataFrame) -> dict:
    counts = matrix["class"].value_counts().to_dict()
    total = matrix["total_margin"].sum()
    star_share = matrix.loc[matrix["class"] == "Star", "total_margin"].sum() / total if total else 0
    return {"counts": counts, "star_margin_share": star_share, "total_margin": total}
