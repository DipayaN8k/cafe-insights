import pandas as pd

from cafe_insights import abc_analysis, basket, data, forecast, menu_engineering, readiness
from conftest import make_sales


# ---------- menu engineering ----------

def test_menu_matrix_quadrants():
    # Two items per quadrant. Popular = many units; profitable = margin above the weighted average.
    menu = pd.DataFrame({
        "item": ["Star A", "Star B", "Plow A", "Plow B", "Puzzle A", "Puzzle B", "Dog A", "Dog B"],
        "category": ["x"] * 8,
        "price": [200, 200, 100, 100, 300, 300, 100, 100],
        "unit_cost": [50, 50, 80, 80, 50, 50, 90, 90],
    })
    units = {"Star A": 100, "Star B": 100, "Plow A": 100, "Plow B": 100,
             "Puzzle A": 5, "Puzzle B": 5, "Dog A": 5, "Dog B": 5}
    price = dict(zip(menu["item"], menu["price"]))
    rows = [(f"{item}-{i}", "2026-01-01 09:00", item, 1, price[item]) for item, n in units.items() for i in range(n)]
    sales = make_sales(rows)
    result = menu_engineering.classify(data.connect(sales, menu)).set_index("item")["class"]
    assert result["Star A"] == "Star" and result["Plow A"] == "Plowhorse"
    assert result["Puzzle A"] == "Puzzle" and result["Dog A"] == "Dog"


def test_sample_menu_matrix_finds_planted_items(sample):
    sales, menu, _, _ = sample
    m = menu_engineering.classify(data.connect(sales, menu)).set_index("item")["class"]
    assert m["Masala Chai"] == "Plowhorse"      # best seller, ₹68 margin
    assert m["Cappuccino"] == "Star"
    assert m["Avocado Toast"] == "Dog"          # ₹320 price but ₹230 cost, rarely ordered
    assert m["Cold Brew"] == "Puzzle"           # highest margin, low sales


def test_items_without_cost_are_reported():
    menu = pd.DataFrame({"item": ["Latte", "Muffin"], "category": ["x", "x"], "price": [190, 130], "unit_cost": [45, None]})
    sales = make_sales([("1", "2026-01-01", "Latte", 1, 190), ("2", "2026-01-01", "Muffin", 1, 130)])
    con = data.connect(sales, menu)
    assert menu_engineering.items_without_cost(con) == ["Muffin"]
    assert list(menu_engineering.classify(con)["item"]) == ["Latte"]


# ---------- ABC ----------

def test_abc_classes():
    revenue = {"A1": 500, "A2": 300, "B1": 100, "B2": 50, "C1": 30, "C2": 20}
    sales = make_sales([(k, "2026-01-01", k, 1, v) for k, v in revenue.items()])
    abc = abc_analysis.classify(data.connect(sales)).set_index("item")["abc_class"]
    # A1 starts at 0%, A2 starts at 50% -> A; B1 starts at 80% -> B; B2 at 90% -> B; C1 at 95% -> C
    assert abc.to_dict() == {"A1": "A", "A2": "A", "B1": "B", "B2": "B", "C1": "C", "C2": "C"}


def test_top_item_is_always_a():
    sales = make_sales([("1", "2026-01-01", "Only", 1, 100), ("2", "2026-01-01", "Tiny", 1, 1)])
    abc = abc_analysis.classify(data.connect(sales))
    assert abc.iloc[0]["item"] == "Only" and abc.iloc[0]["abc_class"] == "A"


# ---------- basket ----------

def test_basket_finds_real_pair_and_ignores_chance():
    rows = []
    for i in range(100):
        rows.append((f"o{i}", "2026-01-01", "Coffee", 1, 180))
        if i < 40:
            rows.append((f"o{i}", "2026-01-01", "Croissant", 1, 150))
    for i in range(100, 160):
        rows.append((f"o{i}", "2026-01-01", "Tea", 1, 80))
    for i in range(160, 170):
        rows.append((f"o{i}", "2026-01-01", "Croissant", 1, 150))
    # A Tea+Croissant pair seen only by chance-level co-occurrence (3 times) is filtered out.
    for i in range(100, 103):
        rows.append((f"o{i}", "2026-01-01", "Croissant", 1, 150))
    p = basket.pairs(data.connect(make_sales(rows)), min_together=10)
    assert list(zip(p["item_a"], p["item_b"])) == [("Coffee", "Croissant")]
    row = p.iloc[0]
    n, coffee, croissant = 170, 100, 53
    assert row["together"] == 40
    assert abs(row["confidence_a_to_b"] - 40 / coffee) < 1e-9     # Coffee orders that include Croissant
    assert abs(row["confidence_b_to_a"] - 40 / croissant) < 1e-9  # Croissant orders that include Coffee
    assert abs(row["lift"] - (40 / n) / ((coffee / n) * (croissant / n))) < 1e-9


def test_combo_tactic_and_price(sample):
    sales, menu, _, _ = sample
    con = data.connect(sales, menu)
    combos = basket.combo_suggestions(basket.pairs(con), menu, menu_engineering.classify(con), discount=0.10)
    assert not combos.empty
    for _, c in combos.iterrows():
        assert c["combo_price"] < c["full_price"]
        expected = "Upsell prompt" if max(c["confidence_a_to_b"], c["confidence_b_to_a"]) >= basket.UPSELL_CONFIDENCE else "Combo deal"
        assert c["tactic"] == expected
    # The planted Iced Latte + Cheesecake pairing is the strongest.
    assert {combos.iloc[0]["item_a"], combos.iloc[0]["item_b"]} == {"Iced Latte", "Blueberry Cheesecake"}


# ---------- forecast ----------

def test_forecast_learns_planted_monday_croissant_dip(sample):
    sales, _, weather, _ = sample
    fm = forecast.fit(sales, weather)
    _, item_tips = forecast.weekday_tips(fm)
    assert any(t.startswith("Butter Croissant") and "Mondays" in t and "fewer" in t for t in item_tips)
    mult = forecast.weekday_multipliers(fm)
    assert mult.loc["Butter Croissant", "Saturday"] > 1.15 > 1 > mult.loc["Butter Croissant", "Monday"]


def test_forecast_learns_heat_lifts_cold_drinks(sample):
    sales, _, weather, _ = sample
    fm = forecast.fit(sales, weather)
    coef = dict(zip(fm.items["Cold Coffee"].features, fm.items["Cold Coffee"].model.coef_))
    hot = dict(zip(fm.items["Masala Chai"].features, fm.items["Masala Chai"].model.coef_))
    assert coef["temp_max_c"] > 0 > hot["temp_max_c"]


def test_predict_shape_and_advice(sample):
    sales, _, weather, _ = sample
    fm = forecast.fit(sales, weather)
    future = pd.DataFrame({"date": pd.date_range(fm.history_end + pd.Timedelta(days=1), periods=7),
                           "temp_max_c": 31.0, "rain_mm": 0.0})
    pred = forecast.predict(fm, future, days=7)
    assert len(pred) == 7 * sales["item"].nunique()
    assert (pred["forecast_units"] >= 0).all()
    assert pred["advice"].str.len().gt(0).all()


def test_forecast_beats_naive_on_holdout(sample):
    sales, _, weather, _ = sample
    bt = forecast.backtest(sales, weather)
    assert bt["model_wape"] < bt["naive_wape"]


def test_forecast_without_weather(sample):
    sales, _, _, _ = sample
    fm = forecast.fit(sales, None)
    assert not fm.use_weather
    assert len(forecast.predict(fm, None, days=3)) == 3 * sales["item"].nunique()


# ---------- readiness (cold start honesty) ----------

def test_new_cafe_gets_no_guesses():
    results = readiness.assess(None)
    assert all(r.status == "blocked" for r in results)
    assert "won't guess" in results[0].message


def test_short_history_is_limited_or_blocked():
    rows = [(f"o{d}-{i}", f"2026-01-{d:02d} 09:00", "Latte", 1, 190) for d in range(1, 15) for i in range(5)]
    sales = make_sales(rows)
    menu = pd.DataFrame({"item": ["Latte"], "category": ["x"], "price": [190], "unit_cost": [45]})
    status = {r.feature: r.status for r in readiness.assess(sales, menu)}
    assert status == {"Menu matrix": "limited", "Stock priorities (ABC)": "limited",
                      "Demand forecast": "blocked", "Combo suggestions": "blocked"}


def test_menu_matrix_needs_costs(sample):
    sales, menu, weather, _ = sample
    r = readiness.status_of(readiness.assess(sales, menu.drop(columns="unit_cost"), weather), "Menu matrix")
    assert r.status == "blocked" and "cost" in r.message


def test_sample_is_fully_ready(sample):
    sales, menu, weather, _ = sample
    assert all(r.status == "ready" for r in readiness.assess(sales, menu, weather))
