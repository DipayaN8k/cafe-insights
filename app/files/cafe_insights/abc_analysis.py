"""ABC (Pareto) analysis: the few items that bring in most of the sales.

A items make up the first ~80% of sales, B the next ~15%, C the rest.
An item that crosses a cutoff belongs to the class it started in, so the
top seller is always an A item. Sales are measured in money when prices are
known, otherwise in units.
"""

import duckdb
import pandas as pd

ABC_SQL = """
WITH item_sales AS (
    SELECT item, SUM({metric}) AS sales, SUM(quantity) AS units, SUM(revenue) AS revenue
    FROM sales
    GROUP BY item
),
ranked AS (
    SELECT *,
           sales / SUM(sales) OVER () AS share,
           SUM(sales) OVER (ORDER BY sales DESC, item
                            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
             / SUM(sales) OVER () AS cum_share
    FROM item_sales
)
SELECT *,
       CASE WHEN cum_share - share < ? THEN 'A'
            WHEN cum_share - share < ? THEN 'B'
            ELSE 'C' END AS abc_class
FROM ranked
ORDER BY sales DESC, item
"""

# What an owner sees for each class.
GROUPS = {
    "A": {"name": "Never run out", "icon": "🔴", "do": "Check stock every day and keep extra in reserve."},
    "B": {"name": "Keep a steady supply", "icon": "🟡", "do": "Check stock once a week."},
    "C": {"name": "Order small amounts", "icon": "⚪", "do": "Buy little and often. Some could leave the menu."},
}


def classify(con: duckdb.DuckDBPyConnection, by_money: bool = True, a_cutoff: float = 0.80, b_cutoff: float = 0.95) -> pd.DataFrame:
    metric = "revenue" if by_money else "quantity"
    df = con.execute(ABC_SQL.format(metric=metric), [a_cutoff, b_cutoff]).df()
    df["group"] = df["abc_class"].map(lambda c: GROUPS[c]["name"])
    df["guidance"] = df["abc_class"].map(lambda c: GROUPS[c]["do"])
    return df


def headline(abc: pd.DataFrame, by_money: bool = True) -> str:
    a = abc[abc["abc_class"] == "A"]
    what = "of your money" if by_money else "of everything you sell"
    return f"Just {len(a)} of your {len(abc)} items bring in {a['share'].sum():.0%} {what}."
