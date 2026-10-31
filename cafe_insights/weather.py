"""Future weather for the forecast: live from Open-Meteo, or a seasonal fallback."""

import json
import sys

import pandas as pd

OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
    "&daily=temperature_2m_max,precipitation_sum&timezone=auto&forecast_days=16"
)


def _get_json(url: str, timeout: float) -> dict:
    if sys.platform == "emscripten":
        # Running in the browser (Pyodide): plain sockets don't exist, so use the browser's own fetch.
        from pyodide.http import open_url
        return json.loads(open_url(url).read())
    import requests
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def fetch_forecast(lat: float, lon: float, timeout: float = 8.0) -> pd.DataFrame:
    """Daily max temperature and rain for the next 16 days (free API, no key).

    Only the coordinates are sent; no sales data ever leaves the device.
    """
    daily = _get_json(OPEN_METEO_URL.format(lat=round(lat, 2), lon=round(lon, 2)), timeout)["daily"]
    return pd.DataFrame({
        "date": pd.to_datetime(daily["time"]),
        "temp_max_c": daily["temperature_2m_max"],
        "rain_mm": daily["precipitation_sum"],
    })


def seasonal_fallback(history: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Average weather for each calendar month in history: used when live data is unavailable."""
    by_month = history.assign(month=history["date"].dt.month).groupby("month")[["temp_max_c", "rain_mm"]].mean()
    overall = history[["temp_max_c", "rain_mm"]].mean()
    rows = [by_month.loc[d.month] if d.month in by_month.index else overall for d in dates]
    return pd.DataFrame(rows).reset_index(drop=True).assign(date=dates)[["date", "temp_max_c", "rain_mm"]]


def future_weather(history: pd.DataFrame, start: pd.Timestamp, days: int,
                   lat: float | None = None, lon: float | None = None, live: bool = True) -> tuple[pd.DataFrame, str]:
    """Weather for `days` days from `start`, plus a note saying where it came from.

    Live data only helps if the forecast window is the real near future; for an old
    export (history ending months ago) we fall back to seasonal averages.
    """
    dates = pd.date_range(start, periods=days, freq="D")
    if live and lat is not None and lon is not None:
        try:
            live_df = fetch_forecast(lat, lon)
            covered = live_df[live_df["date"].isin(dates)]
            if len(covered) == days:
                return covered.reset_index(drop=True), "Live forecast from Open-Meteo"
        except Exception:  # network down, API change: fall through to seasonal
            pass
    if history is None or history.empty:
        return pd.DataFrame({"date": dates}), "No weather data"
    return seasonal_fallback(history, dates), "Seasonal average for these months (live forecast not available for these dates)"
