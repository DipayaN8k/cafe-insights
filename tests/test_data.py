import pandas as pd
import pytest

from cafe_insights import data


def test_pos_column_names_are_recognised():
    raw = pd.DataFrame({
        "Bill No": ["B1", "B1", "B2"],
        "Bill Date": ["2026-01-05 09:10", "2026-01-05 09:10", "2026-01-05 10:00"],
        "Item Name": ["Latte", "Muffin", "Latte"],
        "Qty": [1, 2, 1],
        "Rate": [190, 130, 190],
    })
    report = data.CleaningReport()
    sales = data.clean_sales(raw, None, report)
    assert {"order_id", "timestamp", "item", "quantity", "unit_price", "revenue"} <= set(sales.columns)
    assert sales["revenue"].sum() == 190 + 260 + 190
    assert any("matched your columns" in s for s in report.steps)


def test_customer_personal_data_is_dropped():
    raw = pd.DataFrame({
        "Bill No": ["B1"], "Date": ["2026-01-05 09:10"], "Item Name": ["Latte"], "Qty": [1], "Rate": [190],
        "Customer Name": ["Asha"], "Mobile No": ["98xxxxxx01"], "Email": ["a@example.com"],
        "Cust_ID": ["C9"], "Delivery Address": ["Bandra"], "Channel": ["Swiggy"],
    })
    report = data.CleaningReport()
    sales = data.clean_sales(raw, None, report)
    assert not {"customer_name", "mobile_no", "email", "cust_id", "delivery_address"} & set(sales.columns)
    assert {"item", "channel"} <= set(sales.columns)
    assert any("personal data" in s for s in report.steps)


def test_business_columns_are_not_mistaken_for_personal():
    cols = ["order_id", "item_name", "unit_price", "channel", "category", "discount", "tax", "order_type"]
    df = pd.DataFrame(columns=cols)
    assert list(data.drop_personal_columns(df, data.CleaningReport()).columns) == cols


def test_missing_required_column_raises_clear_error():
    with pytest.raises(ValueError, match="timestamp"):
        data.clean_sales(pd.DataFrame({"order_id": ["1"], "item": ["Latte"]}), None, data.CleaningReport())


def test_typos_map_to_menu_names():
    menu = data.clean_menu(pd.DataFrame({"item": ["Cappuccino", "Butter Croissant"], "price": [180, 150]}), data.CleaningReport())
    raw = pd.DataFrame({
        "order_id": ["1", "2", "3", "4"],
        "timestamp": ["2026-01-01 09:00"] * 4,
        "item": ["cappucino", " CAPPUCCINO ", "Butter Croisant", "Cappuccino"],
        "quantity": [1, 1, 1, 1],
        "unit_price": [180, 180, 150, 180],
    })
    sales = data.clean_sales(raw, menu, data.CleaningReport())
    assert sorted(sales["item"].unique()) == ["Butter Croissant", "Cappuccino"]


def test_blanks_duplicates_and_voids():
    menu = data.clean_menu(pd.DataFrame({"item": ["Latte"], "price": [190]}), data.CleaningReport())
    raw = pd.DataFrame({
        "order_id": ["1", "1", "2", "3", "4"],
        "timestamp": ["2026-01-01 09:00", "2026-01-01 09:00", "2026-01-01 10:00", "2026-01-01 11:00", "not a date"],
        "item": ["Latte"] * 5,
        "quantity": [1, 1, None, -1, 1],
        "unit_price": [190, 190, None, 190, 190],
    })
    report = data.CleaningReport()
    sales = data.clean_sales(raw, menu, report)
    # duplicate of order 1 dropped, blank qty -> 1, blank price from menu, void and bad date dropped
    assert list(sales["order_id"]) == ["1", "2"]
    assert sales.loc[sales["order_id"] == "2", "unit_price"].item() == 190
    assert len(report.steps) >= 4


def test_day_first_dates():
    raw = pd.DataFrame({"order_id": ["1"], "timestamp": ["03/02/2026 09:00"], "item": ["Latte"], "unit_price": [190]})
    sales = data.clean_sales(raw, None, data.CleaningReport(), dayfirst=True)
    assert sales["timestamp"].iat[0] == pd.Timestamp("2026-02-03 09:00")


def test_sample_data_cleans(sample):
    sales, menu, weather, report = sample
    assert sales["item"].nunique() == len(menu) == 18
    assert sales["quantity"].notna().all() and (sales["revenue"] > 0).all()
    assert not sales.duplicated(["order_id", "timestamp", "item", "quantity", "unit_price"]).any()


# ---------- real public dataset formats ----------

def test_french_bakery_format():
    # Kaggle "French bakery daily sales": separate date/time, euro prices with decimal commas, junk "." items.
    raw = pd.DataFrame({
        "Unnamed: 0": [0, 1, 2, 3],
        "date": ["2021-01-02"] * 4, "time": ["08:38", "08:38", "09:14", "09:20"],
        "ticket_number": [150040.0, 150040.0, 150041.0, 150042.0],
        "article": ["BAGUETTE", "PAIN AU CHOCOLAT", ".", "BAGUETTE"],
        "Quantity": [1.0, 3.0, 1.0, -1.0],
        "unit_price": ["0,90 €", "1,20 €", "0,00 €", "0,90 €"],
    })
    sales = data.clean_sales(raw, None, data.CleaningReport())
    assert list(sales["item"]) == ["Baguette", "Pain Au Chocolat"]
    assert list(sales["order_id"]) == ["150040", "150040"]
    assert sales["timestamp"].iat[0] == pd.Timestamp("2021-01-02 08:38")
    assert sales["revenue"].sum() == pytest.approx(0.90 + 3 * 1.20)


def test_maven_coffee_format():
    raw = pd.DataFrame({
        "transaction_id": [1, 2], "transaction_date": ["2023-01-01", "2023-01-01"],
        "transaction_time": ["07:06:11", "07:08:56"], "transaction_qty": [2, 1], "store_id": [5, 5],
        "store_location": ["Lower Manhattan"] * 2, "product_id": [32, 57], "unit_price": [3.0, 3.1],
        "product_category": ["Coffee", "Tea"], "product_type": ["Gourmet brewed coffee", "Brewed Chai tea"],
        "product_detail": ["Ethiopia Rg", "Spicy Eye Opener Chai Lg"],
    })
    sales = data.clean_sales(raw, None, data.CleaningReport())
    assert list(sales["item"]) == ["Ethiopia Rg", "Spicy Eye Opener Chai Lg"]
    assert sales["revenue"].sum() == pytest.approx(9.1)
    assert set(sales["channel"]) == {"Lower Manhattan"}


def test_bread_basket_format_without_prices():
    # OpenML/Kaggle "The Bread Basket": no prices at all, day-first date_time.
    raw = pd.DataFrame({"Transaction": [1, 1, 2], "Item": ["Bread", "Coffee", "Coffee"],
                        "date_time": ["30-10-2016 09:58", "30-10-2016 09:58", "30-10-2016 10:05"],
                        "period_day": ["morning"] * 3, "weekday_weekend": ["weekend"] * 3})
    report = data.CleaningReport()
    sales = data.clean_sales(raw, None, report, dayfirst=True)
    assert len(sales) == 3 and not data.has_prices(sales)
    assert sales["timestamp"].iat[0] == pd.Timestamp("2016-10-30 09:58")
    assert any("No prices" in s for s in report.steps)


def test_no_order_id_treats_rows_as_bills():
    raw = pd.DataFrame({"datetime": ["2024-03-01 10:15", "2024-03-01 10:19"], "coffee_name": ["Latte", "Americano"],
                        "money": [38.7, 28.9], "cash_type": ["card", "card"], "card": ["ANON-1", "ANON-2"]})
    report = data.CleaningReport()
    sales = data.clean_sales(raw, None, report)
    assert sales["order_id"].nunique() == 2
    assert "card" not in sales.columns and any("personal data" in s for s in report.steps)


def test_estimated_menu_uses_cost_share():
    sales = data.clean_sales(pd.DataFrame({"order_id": ["1", "2"], "timestamp": ["2026-01-01"] * 2,
                                           "item": ["Latte", "Latte"], "unit_price": [200, 200]}), None, data.CleaningReport())
    menu = data.estimated_menu(sales, 0.30)
    assert menu.loc[0, "unit_cost"] == pytest.approx(60)


def test_parse_money_variants():
    s = pd.Series(["₹180", "0,90 €", "Rs. 1,250.00", "2,5", None])
    assert data.parse_money(s).tolist()[:4] == [180.0, 0.90, 1250.0, 2.5]


def test_year_first_dates_ignore_day_first_setting():
    raw = pd.DataFrame({"order_id": ["1", "2"], "timestamp": ["2021-01-02 08:00", "2021-03-04 09:00"], "item": ["A", "B"], "unit_price": [1, 1]})
    sales = data.clean_sales(raw, None, data.CleaningReport(), dayfirst=True)
    assert list(sales["timestamp"].dt.month) == [1, 3]
