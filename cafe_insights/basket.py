"""Market basket analysis: which items are bought together, and combos to sell.

support    = share of all orders containing both items
confidence = of orders with A, the share that also have B
lift       = how much more often they appear together than by chance (>1 = real pairing)
"""

import duckdb
import pandas as pd

from cafe_insights.text import money, times

UPSELL_CONFIDENCE = 0.30

PAIRS_SQL = """
WITH order_items AS (
    SELECT DISTINCT order_id, item FROM sales
),
n AS (SELECT COUNT(DISTINCT order_id) AS orders FROM order_items),
item_orders AS (
    SELECT item, COUNT(*) AS orders_with FROM order_items GROUP BY item
),
pairs AS (
    SELECT a.item AS item_a, b.item AS item_b, COUNT(*) AS together
    FROM order_items a
    JOIN order_items b ON a.order_id = b.order_id AND a.item < b.item
    GROUP BY 1, 2
)
SELECT p.item_a, p.item_b, p.together,
       p.together / n.orders                                    AS support,
       p.together / ia.orders_with                              AS confidence_a_to_b,
       p.together / ib.orders_with                              AS confidence_b_to_a,
       (p.together / n.orders) / ((ia.orders_with / n.orders) * (ib.orders_with / n.orders)) AS lift
FROM pairs p
CROSS JOIN n
JOIN item_orders ia ON ia.item = p.item_a
JOIN item_orders ib ON ib.item = p.item_b
WHERE p.together >= ?
ORDER BY lift DESC, together DESC
"""


def pairs(con: duckdb.DuckDBPyConnection, min_together: int = 20, min_lift: float = 1.2) -> pd.DataFrame:
    df = con.execute(PAIRS_SQL, [min_together]).df()
    return df[df["lift"] >= min_lift].reset_index(drop=True)


def combo_suggestions(
    pair_df: pd.DataFrame,
    menu: pd.DataFrame | None,
    classes: pd.DataFrame | None = None,
    discount: float = 0.10,
    top_n: int = 6,
    currency: str = "₹",
) -> pd.DataFrame:
    """Turn strong pairings into priced combos.

    Pairs that use a popular Star to lift a Puzzle or Plowhorse rank first,
    since that combo moves an item the menu matrix says needs help.
    """
    if pair_df.empty:
        return pair_df.assign(combo_price=[], pitch=[])
    df = pair_df.copy()

    price = dict(zip(menu["item"], menu["price"])) if menu is not None and "price" in menu.columns else {}
    cost = dict(zip(menu["item"], menu["unit_cost"])) if menu is not None and "unit_cost" in menu.columns else {}
    cls = dict(zip(classes["item"], classes["class"])) if classes is not None and not classes.empty else {}

    df["full_price"] = df["item_a"].map(price) + df["item_b"].map(price)
    df["combo_price"] = (df["full_price"] * (1 - discount)).map(_round_price)
    df["discount_per_combo"] = df["full_price"] - df["combo_price"]
    df["combo_margin"] = df["combo_price"] - (df["item_a"].map(cost) + df["item_b"].map(cost))
    # If many customers already buy both, a discount mostly gives money back on sales
    # you'd make anyway. A staff prompt ("add a croissant?") converts the rest for free.
    df["tactic"] = ["Upsell prompt" if max(a, b) >= UPSELL_CONFIDENCE else "Combo deal"
                    for a, b in zip(df["confidence_a_to_b"], df["confidence_b_to_a"])]
    df["class_a"] = df["item_a"].map(cls)
    df["class_b"] = df["item_b"].map(cls)

    def needs_help(c):
        return c in ("Puzzle", "Plowhorse", "Dog")

    df["helps_weak_item"] = [
        (a == "Star" and needs_help(b)) or (b == "Star" and needs_help(a))
        for a, b in zip(df["class_a"], df["class_b"])
    ]
    # Who to ask, and what to offer them: lead with the item most buyers already start with,
    # unless the pair can lift a weaker item, in which case offer the weak item to the Star's buyers.
    leads = df["confidence_a_to_b"] >= df["confidence_b_to_a"]
    df["anchor"] = df["item_a"].where(leads, df["item_b"])
    df["offer"] = df["item_b"].where(leads, df["item_a"])
    weak_is_b = df["helps_weak_item"] & (df["class_a"] == "Star")
    weak_is_a = df["helps_weak_item"] & (df["class_b"] == "Star")
    df.loc[weak_is_b, ["anchor", "offer"]] = df.loc[weak_is_b, ["item_a", "item_b"]].to_numpy()
    df.loc[weak_is_a, ["anchor", "offer"]] = df.loc[weak_is_a, ["item_b", "item_a"]].to_numpy()
    df["pitch"] = df.apply(lambda r: _pitch(r, currency), axis=1)
    df = df.sort_values(["helps_weak_item", "lift", "together"], ascending=[False, False, False])
    return df.head(top_n).reset_index(drop=True)


def _round_price(x: float) -> float:
    """Menu-friendly price: ₹374 -> ₹370, €4.63 -> €4.6."""
    if pd.isna(x):
        return x
    step = 10 if x >= 100 else 1 if x >= 10 else 0.1
    return round(round(x / step) * step, 2)


def _pitch(row: pd.Series, currency: str = "₹") -> str:
    """Plain-English advice for one pair, written for an owner, not an analyst."""
    conf = max(row["confidence_a_to_b"], row["confidence_b_to_a"])
    lead, follow = (row["item_a"], row["item_b"]) if row["confidence_a_to_b"] >= row["confidence_b_to_a"] else (row["item_b"], row["item_a"])
    out_of_10 = max(1, round(conf * 10))
    text = (f"About {out_of_10} in every 10 people who buy {lead} also buy {follow}. "
            f"People who order one are {times(row['lift'])} more likely than other customers to order the other.")
    offer, anchor = row["offer"], row["anchor"]
    if row["tactic"] == "Upsell prompt":
        text += f" Many already buy both, so no discount is needed: have staff ask \"Would you like a {offer} with your {anchor}?\""
    elif pd.notna(row["combo_price"]):
        text += f" Most {lead} buyers don't add it yet. Try selling both together for {money(row['combo_price'], currency)}."
    else:
        text += f" Most {lead} buyers don't add it yet. Try selling both together at a small discount."
    return text
