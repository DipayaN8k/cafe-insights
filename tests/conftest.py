import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cafe_insights import data  # noqa: E402


@pytest.fixture(scope="session")
def sample():
    """The bundled sample cafe, cleaned once for the whole test run."""
    report = data.CleaningReport()
    menu = data.clean_menu(pd.read_csv(ROOT / "sample_data" / "menu.csv"), report)
    sales = data.clean_sales(pd.read_csv(ROOT / "sample_data" / "sales.csv"), menu, report)
    weather = data.clean_weather(pd.read_csv(ROOT / "sample_data" / "weather.csv"), report)
    return sales, menu, weather, report


def make_sales(rows):
    """rows: (order_id, timestamp, item, quantity, unit_price)."""
    df = pd.DataFrame(rows, columns=["order_id", "timestamp", "item", "quantity", "unit_price"])
    return data.clean_sales(df, None, data.CleaningReport())
