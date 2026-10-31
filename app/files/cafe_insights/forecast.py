"""Item-level daily demand forecast from weekday, holidays and weather.

One Poisson regression per item. The model is log-linear, so every coefficient
turns into a plain multiplier ("Mondays: 0.78× a typical day"), which is what
lets us explain each forecast in words instead of handing over a black box.
"""

from dataclasses import dataclass

import holidays as holidays_lib
import numpy as np
import pandas as pd
from sklearn.linear_model import PoissonRegressor

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
CHANGE_THRESHOLD = 0.15  # only call out prep changes of 15% or more...
MIN_UNIT_CHANGE = 3      # ...that are also at least 3 units (+75% on 4 cups is not worth acting on)
BASELINE_DAYS = 28
USUAL_WEEKS = 8  # "a usual Saturday" = the average of the last 8 Saturdays
MIN_Z = 3.0  # how sure we must be before calling an item-specific weekday swing real
MIN_DAILY_UNITS = 3  # item-specific weekday rules only for items selling at least this many a day


@dataclass
class ItemModel:
    item: str
    model: PoissonRegressor
    features: list[str]
    baseline: float  # average daily units over the last BASELINE_DAYS
    weekday_units: np.ndarray  # total units sold on each weekday in history
    weekday_usual: np.ndarray  # average units on each weekday over the last USUAL_WEEKS weeks


@dataclass
class ForecastModel:
    items: dict[str, ItemModel]
    use_weather: bool
    use_holidays: bool
    scale: dict[str, tuple[float, float]]
    country: str
    history_start: pd.Timestamp
    history_end: pd.Timestamp
    # Scaled weather on each weekday over the last USUAL_WEEKS weeks: the conditions behind "a usual Saturday".
    recent_weather: dict[int, dict[str, float]]


def holiday_flags(dates: pd.Series, country: str = "IN") -> pd.Series:
    years = sorted(set(pd.DatetimeIndex(dates).year))
    cal = holidays_lib.country_holidays(country, years=years)
    return pd.Series([d.date() in cal for d in pd.DatetimeIndex(dates)], index=dates.index, dtype=float)


def daily_item_units(sales: pd.DataFrame) -> pd.DataFrame:
    """Units per item per day, with zeros filled in for days an item didn't sell."""
    days = pd.date_range(sales["date"].min(), sales["date"].max(), freq="D")
    grid = pd.MultiIndex.from_product([days, sorted(sales["item"].unique())], names=["date", "item"])
    units = sales.groupby(["date", "item"])["quantity"].sum().reindex(grid, fill_value=0.0)
    return units.rename("units").reset_index()


def _features(dates: pd.Series, weather: pd.DataFrame | None, use_weather: bool, use_holidays: bool,
              scale: dict, country: str, start: pd.Timestamp) -> pd.DataFrame:
    X = pd.DataFrame(index=dates.index)
    wd = pd.DatetimeIndex(dates).day_of_week
    for i, name in enumerate(WEEKDAYS):
        X[f"is_{name.lower()}"] = (wd == i).astype(float)
    X["trend"] = (pd.DatetimeIndex(dates) - start).days.to_numpy() / 365.0
    if use_holidays:
        X["holiday"] = holiday_flags(dates, country).to_numpy()
    if use_weather:
        w = pd.DataFrame({"date": dates.to_numpy()}).merge(weather, on="date", how="left")
        for col in ("temp_max_c", "rain_mm"):
            mean, std = scale[col]
            X[col] = ((w[col].fillna(mean) - mean) / std).to_numpy()
    return X


def fit(sales: pd.DataFrame, weather: pd.DataFrame | None = None, country: str = "IN",
        use_holidays: bool = True, alpha: float = 1e-3) -> ForecastModel:
    daily = daily_item_units(sales)
    start = daily["date"].min()
    use_weather = weather is not None and {"temp_max_c", "rain_mm"} <= set(weather.columns) and not weather.empty
    scale = {}
    if use_weather:
        hist = weather[weather["date"].between(start, daily["date"].max())]
        for col in ("temp_max_c", "rain_mm"):
            std = hist[col].std()
            scale[col] = (hist[col].mean(), std if std and std > 0 else 1.0)

    dates = pd.Series(sorted(daily["date"].unique()))
    X = _features(dates, weather, use_weather, use_holidays, scale, country, start)
    X.index = dates

    models = {}
    for item, grp in daily.groupby("item"):
        y = grp.set_index("date")["units"].reindex(dates).to_numpy()
        # fit_intercept=False: the seven weekday dummies act as the intercept.
        m = PoissonRegressor(alpha=alpha, fit_intercept=False, max_iter=1000).fit(X.to_numpy(), y)
        baseline = float(y[-BASELINE_DAYS:].mean())
        weekdays = pd.DatetimeIndex(dates).day_of_week
        weekday_units = np.bincount(weekdays, weights=y, minlength=7)
        recent = slice(-USUAL_WEEKS * 7, None)
        weekday_usual = (np.bincount(weekdays[recent], weights=y[recent], minlength=7)
                         / np.maximum(np.bincount(weekdays[recent], minlength=7), 1))
        models[item] = ItemModel(item, m, list(X.columns), baseline, weekday_units, weekday_usual)

    recent_weather = {}
    if use_weather:
        recent_X = X.iloc[-USUAL_WEEKS * 7:]
        by_day = recent_X[["temp_max_c", "rain_mm"]].groupby(pd.DatetimeIndex(recent_X.index).day_of_week).mean()
        recent_weather = {wd: row.to_dict() for wd, row in by_day.iterrows()}

    return ForecastModel(models, use_weather, use_holidays, scale, country, start, daily["date"].max(), recent_weather)


def _coefs(im: ItemModel) -> dict[str, float]:
    return dict(zip(im.features, im.model.coef_))


def weekday_multipliers(fm: ForecastModel) -> pd.DataFrame:
    """Item × weekday table: 1.20 means 20% more than that item's average day."""
    rows = {}
    for item, im in fm.items.items():
        c = _coefs(im)
        logs = np.array([c[f"is_{d.lower()}"] for d in WEEKDAYS])
        rows[item] = np.exp(logs - logs.mean())
    return pd.DataFrame(rows, index=WEEKDAYS).T


def weekday_tips(fm: ForecastModel, busy_threshold: float = 0.10, item_threshold: float = 0.08,
                 top_n: int = 6) -> tuple[list[str], list[str]]:
    """Plain-language prep rules, split in two.

    Cafe-wide: days when the whole menu moves together ("Saturdays: prep ~29% more").
    Item-specific: items that swing beyond the cafe-wide pattern, which is the part an
    owner can't guess from footfall alone ("Butter Croissant: 28% fewer on Mondays").
    """
    mult = weekday_multipliers(fm)
    weights = pd.Series({item: im.baseline for item, im in fm.items.items()})
    overall = (mult.mul(weights, axis=0).sum() / weights.sum())

    cafe_wide = [
        f"{day}s: {'busy' if m > 1 else 'quiet'} day, prep ~{abs(m - 1):.0%} {'more' if m > 1 else 'less'} across the menu"
        for day, m in overall.items() if abs(m - 1) >= busy_threshold
    ]

    found = []
    days = (fm.history_end - fm.history_start).days + 1
    for item, row in mult.iterrows():
        # Rare items (a T-shirt sold twice on Saturdays) produce huge, meaningless swings; skip them.
        if fm.items[item].weekday_units.sum() / days < MIN_DAILY_UNITS:
            continue
        for i, (day, m) in enumerate(row.items()):
            relative = m / overall[day] - 1
            # Rough Poisson z-score: low-volume items need a bigger swing before we trust it.
            z = abs(np.log1p(relative)) * np.sqrt(fm.items[item].weekday_units[i])
            if abs(relative) >= item_threshold and abs(m - 1) >= CHANGE_THRESHOLD and z >= MIN_Z:
                found.append((abs(relative), item, day, m, overall[day]))
    found.sort(reverse=True)
    item_specific = [
        f"{item}: prep {abs(m - 1):.0%} {'more' if m > 1 else 'fewer'} on {day}s "
        f"(the whole menu: {abs(o - 1):.0%} {'more' if o > 1 else 'less'})"
        for _, item, day, m, o in found[:top_n]
    ]
    return cafe_wide, item_specific


def predict(fm: ForecastModel, future_weather: pd.DataFrame | None, days: int = 7) -> pd.DataFrame:
    """Forecast the next `days` days per item, with prep advice and the reasons behind it.

    Advice compares against a usual day of the same weekday ("vs a usual Saturday"),
    since owners already know weekends are busy; the weekly rhythm is reported separately.
    """
    dates = pd.Series(pd.date_range(fm.history_end + pd.Timedelta(days=1), periods=days, freq="D"))
    X = _features(dates, future_weather, fm.use_weather, fm.use_holidays, fm.scale, fm.country, fm.history_start)
    is_holiday = X["holiday"].to_numpy() if fm.use_holidays else np.zeros(len(dates))

    rows = []
    for item, im in fm.items.items():
        c = _coefs(im)
        mu = im.model.predict(X.to_numpy())
        wd_logs = np.array([c[f"is_{d.lower()}"] for d in WEEKDAYS])
        for i, d in enumerate(dates):
            day = WEEKDAYS[d.weekday()]
            usual = im.weekday_usual[d.weekday()]
            reasons = []
            def effect(change: float) -> str:
                return f"about {abs(change):.0%} {'more' if change > 0 else 'fewer'}"

            if is_holiday[i] and "holiday" in c:
                reasons.append(f"public holiday, so {effect(np.exp(c['holiday']) - 1)}")
            if fm.use_weather:
                # Compare with the weather on the recent days that make up "usual", not the yearly average.
                ref = fm.recent_weather.get(d.weekday(), {"temp_max_c": 0.0, "rain_mm": 0.0})
                temp_x = X["temp_max_c"].iat[i] - ref["temp_max_c"]
                rain_x = X["rain_mm"].iat[i] - ref["rain_mm"]
                heat = np.exp(c["temp_max_c"] * temp_x) - 1
                rain = np.exp(c["rain_mm"] * rain_x) - 1
                if abs(heat) >= 0.05:
                    reasons.append(f"{'hotter' if temp_x > 0 else 'cooler'} than recent {day}s, so {effect(heat)}")
                if abs(rain) >= 0.05:
                    reasons.append(f"{'rainier' if rain_x > 0 else 'drier'} than recent {day}s, so {effect(rain)}")
            vs = mu[i] / usual - 1 if usual > 0 else 0.0
            if im.baseline < 1:
                advice = "Low seller: make to order"
            elif abs(mu[i] - usual) < MIN_UNIT_CHANGE:
                advice = f"Normal {day} prep"
            elif vs <= -CHANGE_THRESHOLD:
                advice = f"Prep ~{abs(vs):.0%} fewer than a usual {day}"
            elif vs >= CHANGE_THRESHOLD:
                advice = f"Prep ~{vs:.0%} more than a usual {day}"
            else:
                advice = f"Normal {day} prep"
            rows.append({
                "date": d, "item": item, "forecast_units": mu[i], "usual_units": usual,
                "vs_usual": vs, "advice": advice, "reasons": "; ".join(reasons) or "normal conditions",
            })
    return pd.DataFrame(rows)


def backtest(sales: pd.DataFrame, weather: pd.DataFrame | None = None, country: str = "IN", holdout_days: int = 28) -> dict:
    """Hide the last `holdout_days`, forecast them, and compare against a naive guess.

    The naive guess is "same weekday, averaged over the previous four weeks",
    which is roughly what an experienced owner does in their head.
    WAPE = total absolute error / total actual units (lower is better).
    """
    cutoff = sales["date"].max() - pd.Timedelta(days=holdout_days)
    train, test = sales[sales["date"] <= cutoff], sales[sales["date"] > cutoff]
    fm = fit(train, weather, country)

    actual = daily_item_units(test)
    preds = []
    dates = pd.Series(sorted(actual["date"].unique()))
    X = _features(dates, weather, fm.use_weather, fm.use_holidays, fm.scale, country, fm.history_start)
    for item, im in fm.items.items():
        preds.append(pd.DataFrame({"date": dates, "item": item, "pred": im.model.predict(X.to_numpy())}))
    merged = actual.merge(pd.concat(preds), on=["date", "item"], how="left").fillna({"pred": 0.0})

    hist = daily_item_units(train)
    hist["weekday"] = hist["date"].dt.day_of_week
    recent = hist[hist["date"] > cutoff - pd.Timedelta(days=28)]
    naive = recent.groupby(["item", "weekday"])["units"].mean().rename("naive").reset_index()
    merged["weekday"] = merged["date"].dt.day_of_week
    merged = merged.merge(naive, on=["item", "weekday"], how="left").fillna({"naive": 0.0})

    def wape(df, col):
        return float((df["units"] - df[col]).abs().sum() / df["units"].sum()) if df["units"].sum() else float("nan")

    # Rare items sell in random bursts that no model predicts well; report regular items separately.
    daily_avg = hist.groupby("item")["units"].mean()
    regular = merged["item"].map(daily_avg).fillna(0) >= MIN_DAILY_UNITS
    by_day = merged.groupby("date")[["units", "pred", "naive"]].sum()
    return {
        "holdout_days": holdout_days,
        "model_wape": wape(merged, "pred"),
        "naive_wape": wape(merged, "naive"),
        "regular_items": int(merged.loc[regular, "item"].nunique()),
        "regular_model_wape": wape(merged[regular], "pred"),
        "regular_naive_wape": wape(merged[regular], "naive"),
        "model_daily_total_wape": wape(by_day, "pred"),
        "detail": merged,
    }
