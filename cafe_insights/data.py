"""Load and clean POS exports, and expose them to DuckDB for SQL analysis."""

import difflib
import re
from dataclasses import dataclass, field

import duckdb
import pandas as pd

# Common column names seen in POS / billing exports and public datasets, mapped to our schema.
# Order matters: the first name found wins.
SALES_ALIASES = {
    "order_id": ["order_id", "order", "order_no", "bill_no", "bill_number", "invoice", "invoice_no", "receipt_no",
                 "ticket_number", "ticket", "transaction_id", "transaction"],
    "timestamp": ["timestamp", "datetime", "date_time", "created_at", "order_datetime"],
    "item": ["item", "item_name", "product", "product_name", "menu_item", "dish", "article",
             "product_detail", "coffee_name", "product_type"],
    "quantity": ["quantity", "qty", "units", "count", "transaction_qty"],
    "unit_price": ["unit_price", "price", "rate", "selling_price", "mrp", "money", "amount"],
    "channel": ["channel", "order_type", "source", "platform", "store_location"],
}
# Exports often split the moment of sale into a date column and a time column.
DATE_ALIASES = ["date", "bill_date", "order_date", "transaction_date", "sale_date"]
TIME_ALIASES = ["time", "bill_time", "order_time", "transaction_time", "sale_time"]

MENU_ALIASES = {
    "item": SALES_ALIASES["item"],
    "category": ["category", "group", "section", "type", "product_category"],
    "price": ["price", "selling_price", "rate", "mrp", "unit_price"],
    "unit_cost": ["unit_cost", "cost", "food_cost", "cogs", "cost_price"],
}
WEATHER_ALIASES = {
    "date": ["date", "day"],
    "temp_max_c": ["temp_max_c", "temp_max", "max_temp", "temperature", "temperature_2m_max"],
    "rain_mm": ["rain_mm", "rain", "precipitation", "precipitation_sum", "rainfall"],
}

# Columns that hold customer personal data. We never need them, so they are dropped
# the moment a file is read (data minimisation under the DPDP Act, 2023).
PERSONAL_COLUMN_PATTERN = re.compile(
    r"(^|_)(customer|cust|guest|client|buyer|patron)(_|$)"
    r"|phone|mobile|e_?mail|address|contact|whatsapp|aadhaar|aadhar|(^|_)pan(_|$)"
    r"|(^|_)dob(_|$)|birth|loyalty|(^|_)upi(_|$)|(^|_)card(_|$)|card_?(no|number)"
)


@dataclass
class CleaningReport:
    steps: list[str] = field(default_factory=list)

    def add(self, message: str) -> None:
        self.steps.append(message)


def _snake(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def standardize_columns(df: pd.DataFrame, aliases: dict, required: list[str], report: CleaningReport, label: str) -> pd.DataFrame:
    df = df.rename(columns={c: _snake(c) for c in df.columns})
    rename = {}
    for target, options in aliases.items():
        if target in df.columns:
            continue
        match = next((c for c in options if c in df.columns and c not in rename and c not in aliases), None)
        if match:
            rename[match] = target
    if rename:
        df = df.rename(columns=rename)
        report.add(f"{label}: matched your columns " + ", ".join(f"'{a}' → '{b}'" for a, b in rename.items()))
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{label} is missing required column(s): {', '.join(missing)}")
    return df


def drop_personal_columns(df: pd.DataFrame, report: CleaningReport) -> pd.DataFrame:
    """Remove customer names, phone numbers, emails and similar before any analysis."""
    personal = [c for c in df.columns if PERSONAL_COLUMN_PATTERN.search(_snake(c))]
    if personal:
        report.add("Removed customer personal data columns (never used): " + ", ".join(f"'{c}'" for c in personal))
        df = df.drop(columns=personal)
    return df


def parse_money(values: pd.Series) -> pd.Series:
    """Turn '₹180', '0,90 €', 'Rs. 1,250.00' or 180 into numbers."""
    if pd.api.types.is_numeric_dtype(values):
        return values.astype(float)
    # Keep digits, separators and minus; strip dots left over from "Rs." and similar.
    text = values.astype("string").str.replace(r"[^\d,.\-]", "", regex=True).str.strip(".")
    # "0,90" (comma as decimal point, common in Europe) vs "1,250.00" (comma as thousands separator).
    decimal_comma = text.str.match(r"^-?\d+,\d{1,2}$", na=False).fillna(False).astype(bool)
    text = text.where(~decimal_comma, text.str.replace(",", ".", regex=False))
    text = text.str.replace(",", "", regex=False)
    return pd.to_numeric(text, errors="coerce")


def _combine_date_time(sales: pd.DataFrame, report: CleaningReport) -> pd.DataFrame:
    if "timestamp" in sales.columns:
        return sales
    date_col = next((c for c in DATE_ALIASES if c in sales.columns), None)
    time_col = next((c for c in TIME_ALIASES if c in sales.columns), None)
    if date_col and time_col:
        sales["timestamp"] = sales[date_col].astype("string") + " " + sales[time_col].astype("string")
        report.add(f"Joined '{date_col}' and '{time_col}' into one date-and-time")
    elif date_col:
        sales["timestamp"] = sales[date_col]
        has_time = sales[date_col].astype("string").str.contains(":", na=False).mean() > 0.5
        report.add(f"Used '{date_col}' as the date and time" if has_time
                   else f"Used '{date_col}' as the date (no time of day in this file)")
    return sales


def _tidy_name(name: str) -> str:
    return re.sub(r"\s+", " ", str(name)).strip().title()


def canonicalize_items(items: pd.Series, reference: list[str] | None, report: CleaningReport) -> pd.Series:
    """Map spelling variants ("cappucino", " CAPPUCCINO ") onto one canonical name."""
    tidy = items.map(_tidy_name)
    if reference:
        canon = [_tidy_name(r) for r in reference]
    else:
        # Without a menu, trust the most frequent spelling of each name.
        canon = list(tidy.value_counts().index)
    canon_by_key = {c.lower(): c for c in canon}

    mapping = {}
    for raw in tidy.unique():
        if raw.lower() in canon_by_key:
            mapping[raw] = canon_by_key[raw.lower()]
            continue
        close = difflib.get_close_matches(raw.lower(), list(canon_by_key), n=1, cutoff=0.85)
        mapping[raw] = canon_by_key[close[0]] if close else raw

    cleaned = tidy.map(mapping)
    tidied = int((items != tidy).sum())
    fixed = int((tidy != cleaned).sum())
    merged = sorted({f"'{a}' → '{b}'" for a, b in mapping.items() if a != b})
    if tidied:
        report.add(f"Tidied capitals and spacing in {tidied:,} item names")
    if fixed:
        report.add(f"Fixed {fixed:,} misspelt item names: {', '.join(merged[:6])}")
    return cleaned


def clean_menu(raw: pd.DataFrame, report: CleaningReport) -> pd.DataFrame:
    menu = standardize_columns(raw, MENU_ALIASES, ["item"], report, "Menu")
    menu["item"] = menu["item"].map(_tidy_name)
    menu = menu.drop_duplicates("item", keep="last")
    for col in ("price", "unit_cost"):
        if col in menu.columns:
            menu[col] = parse_money(menu[col])
    if "category" not in menu.columns:
        menu["category"] = "Uncategorized"
    return menu.reset_index(drop=True)


def clean_sales(raw: pd.DataFrame, menu: pd.DataFrame | None, report: CleaningReport, dayfirst: bool = False) -> pd.DataFrame:
    sales = drop_personal_columns(raw, report)
    sales = sales.rename(columns={c: _snake(c) for c in sales.columns})
    sales = _combine_date_time(sales, report)
    sales = standardize_columns(sales, SALES_ALIASES, ["timestamp", "item"], report, "Sales")
    start_rows = len(sales)

    # "2021-01-02" (year first) is unambiguous; only apply day-first to dates like "02/01/2021".
    year_first = sales["timestamp"].astype("string").str.match(r"^\s*\d{4}-\d{1,2}-\d{1,2}", na=False).mean() > 0.5
    sales["timestamp"] = pd.to_datetime(sales["timestamp"], errors="coerce", format="mixed",
                                        dayfirst=dayfirst and not year_first)
    if "order_id" not in sales.columns:
        # Without a bill number we can't tell which items were bought together; treat each row as its own bill.
        sales["order_id"] = pd.RangeIndex(len(sales)).astype(str)
        report.add("No bill/order number column: each row is treated as a separate bill (combo ideas need bill numbers)")
    sales["order_id"] = sales["order_id"].astype("string").str.strip().str.removesuffix(".0")
    sales["item"] = sales["item"].astype("string").str.strip()
    junk = sales["item"].isna() | ~sales["item"].str.contains(r"[A-Za-z0-9]", na=False)
    bad = sales["timestamp"].isna() | sales["order_id"].isna() | junk
    if bad.any():
        report.add(f"Dropped {int(bad.sum()):,} rows with no date, bill number or item name")
        sales = sales[~bad]

    sales["item"] = canonicalize_items(sales["item"], list(menu["item"]) if menu is not None else None, report)

    no_quantity_column = "quantity" not in sales.columns
    if no_quantity_column:
        sales["quantity"] = 1.0
    sales["quantity"] = pd.to_numeric(sales["quantity"], errors="coerce")
    missing_qty = sales["quantity"].isna()
    if missing_qty.any():
        sales.loc[missing_qty, "quantity"] = 1.0
        report.add(f"Filled {int(missing_qty.sum()):,} blank quantities with 1")
    returns = sales["quantity"] <= 0
    if returns.any():
        report.add(f"Removed {int(returns.sum()):,} zero/negative quantity rows (voids or returns)")
        sales = sales[~returns]

    sales["unit_price"] = parse_money(sales["unit_price"]) if "unit_price" in sales.columns else pd.Series(float("nan"), index=sales.index)
    if menu is not None and "price" in menu.columns:
        no_price = sales["unit_price"].isna()
        if no_price.any():
            sales.loc[no_price, "unit_price"] = sales.loc[no_price, "item"].map(dict(zip(menu["item"], menu["price"])))
            report.add(f"Took {int(no_price.sum()):,} missing prices from the menu")
    if sales["unit_price"].isna().all():
        report.add("No prices in this file: rankings use units sold instead of money. Add a menu file with prices to see revenue and profit.")
    elif sales["unit_price"].isna().any():
        n = int(sales["unit_price"].isna().sum())
        report.add(f"Dropped {n:,} rows with no price available")
        sales = sales[sales["unit_price"].notna()]

    before = len(sales)
    if no_quantity_column:
        # Without a quantity column, two coffees on one bill appear as two identical rows.
        # Those are real sales, so count them instead of deleting them as duplicates.
        keys = [c for c in sales.columns if c != "quantity"]
        sales = sales.groupby(keys, dropna=False, as_index=False, sort=False)["quantity"].sum()
        report.add("No quantity column: repeated rows on the same bill were counted as quantity "
                   f"(2 rows of Coffee = 2 coffees), {before - len(sales):,} rows merged")
    else:
        sales = sales.drop_duplicates(subset=["order_id", "timestamp", "item", "quantity", "unit_price"])
        if len(sales) < before:
            report.add(f"Removed {before - len(sales):,} duplicate rows")

    if "channel" not in sales.columns:
        sales["channel"] = "Unknown"
    sales["channel"] = sales["channel"].fillna("Unknown").astype("string")
    sales["quantity"] = sales["quantity"].astype(float)
    sales["unit_price"] = sales["unit_price"].astype(float)
    sales["revenue"] = sales["quantity"] * sales["unit_price"]
    sales["date"] = sales["timestamp"].dt.normalize()

    keep = ["order_id", "timestamp", "date", "item", "quantity", "unit_price", "revenue", "channel"]
    if no_quantity_column:
        report.add(f"Kept {int(sales['quantity'].sum()):,} of {start_rows:,} items sold")
    else:
        report.add(f"Kept {len(sales):,} of {start_rows:,} rows")
    return sales[keep].sort_values("timestamp").reset_index(drop=True)


def has_prices(sales: pd.DataFrame) -> bool:
    return bool(sales["revenue"].notna().any())


def estimated_menu(sales: pd.DataFrame, cost_share: float) -> pd.DataFrame:
    """A stand-in menu when the owner hasn't entered costs: each item's typical price,
    with cost assumed to be a fixed share of it. Clearly an estimate."""
    menu = sales.groupby("item", as_index=False)["unit_price"].median().rename(columns={"unit_price": "price"})
    menu["unit_cost"] = (menu["price"] * cost_share).round(2)
    menu["category"] = "Uncategorized"
    return menu


def clean_weather(raw: pd.DataFrame, report: CleaningReport) -> pd.DataFrame:
    weather = standardize_columns(raw, WEATHER_ALIASES, ["date"], report, "Weather")
    weather["date"] = pd.to_datetime(weather["date"], errors="coerce").dt.normalize()
    weather = weather.dropna(subset=["date"]).drop_duplicates("date", keep="last")
    for col in ("temp_max_c", "rain_mm"):
        if col in weather.columns:
            weather[col] = pd.to_numeric(weather[col], errors="coerce")
            weather[col] = weather[col].fillna(weather[col].median())
    return weather[[c for c in ("date", "temp_max_c", "rain_mm") if c in weather.columns]].reset_index(drop=True)


def connect(sales: pd.DataFrame, menu: pd.DataFrame | None = None) -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with `sales` (and `menu`, if given) registered as tables."""
    con = duckdb.connect()
    con.register("sales", sales)
    if menu is not None:
        con.register("menu", menu)
    return con
