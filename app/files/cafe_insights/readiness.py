"""Decide which analyses the data can honestly support.

A brand-new cafe has no history, so we refuse to guess what it should stock.
Each feature gets a status: "ready", "limited" (works, with caveats) or "blocked".
"""

from dataclasses import dataclass

import pandas as pd

MIN_DAYS = 28            # four of each weekday: the least for stable item rankings
MIN_FORECAST_DAYS = 56   # eight of each weekday for a weekday pattern
FULL_YEAR_DAYS = 330     # enough to see seasons and most holidays once
MIN_BASKET_ORDERS = 200  # multi-item orders needed for trustworthy pairings
LOW_BASKET_ORDERS = 50


@dataclass
class Readiness:
    feature: str
    status: str
    message: str


def assess(sales: pd.DataFrame | None, menu: pd.DataFrame | None = None, weather: pd.DataFrame | None = None) -> list[Readiness]:
    if sales is None or sales.empty:
        msg = ("No sales history yet, so there is nothing to learn from. We won't guess what a new cafe "
               "should stock: record every sale from day one, and these insights unlock after 4 weeks.")
        return [Readiness(f, "blocked", msg) for f in ("Menu matrix", "Stock priorities (ABC)", "Demand forecast", "Combo suggestions")]

    days = int((sales["date"].max() - sales["date"].min()).days) + 1
    has_costs = menu is not None and "unit_cost" in menu.columns and menu["unit_cost"].notna().any()
    has_prices = bool(sales["revenue"].notna().any())
    sizes = sales.groupby("order_id")["item"].nunique()
    multi = int((sizes > 1).sum())
    out = []

    if days < 7:
        out.append(Readiness("Menu matrix", "blocked", f"Only {days} day(s) of sales. Need at least {MIN_DAYS} days to rank items fairly."))
    elif not has_prices:
        out.append(Readiness("Menu matrix", "blocked", "Your file has no prices, so we can't work out profit. Add a menu file with each item's price and cost."))
    elif not has_costs:
        out.append(Readiness("Menu matrix", "blocked", "Needs each item's cost (ingredients + packaging) to work out profit. Add a unit_cost column to the menu file."))
    elif days < MIN_DAYS:
        out.append(Readiness("Menu matrix", "limited", f"{days} days of sales. Rankings may shift once you have {MIN_DAYS}+ days."))
    else:
        missing = menu["unit_cost"].isna().sum()
        note = f" {missing} item(s) have no cost and are left out." if missing else ""
        out.append(Readiness("Menu matrix", "ready", f"{days} days of sales with item costs.{note}"))

    if days < 7:
        out.append(Readiness("Stock priorities (ABC)", "blocked", f"Only {days} day(s) of sales. Need at least {MIN_DAYS} days."))
    elif days < MIN_DAYS:
        out.append(Readiness("Stock priorities (ABC)", "limited", f"{days} days of sales. A few busy days can distort the ranking."))
    else:
        out.append(Readiness("Stock priorities (ABC)", "ready", f"{days} days of sales."))

    if days < MIN_DAYS:
        out.append(Readiness("Demand forecast", "blocked", f"{days} days of sales. Need at least {MIN_DAYS} days ({MIN_FORECAST_DAYS}+ is better) to learn weekly patterns."))
    else:
        caveats = []
        if days < MIN_FORECAST_DAYS:
            caveats.append(f"only {days} days, so weekday patterns are rough")
        if days < FULL_YEAR_DAYS:
            caveats.append("less than a year, so holiday and seasonal effects are guesses")
        if weather is None or weather.empty:
            caveats.append("no weather history, so weather effects are not modelled")
        status = "limited" if caveats else "ready"
        detail = "; ".join(caveats).capitalize() + "." if caveats else f"{days} days of sales with weather and holidays."
        out.append(Readiness("Demand forecast", status, detail))

    if multi < LOW_BASKET_ORDERS:
        out.append(Readiness("Combo suggestions", "blocked", f"Only {multi} orders with 2+ items. Need {MIN_BASKET_ORDERS}+ to spot real pairings."))
    elif multi < MIN_BASKET_ORDERS:
        out.append(Readiness("Combo suggestions", "limited", f"{multi} orders with 2+ items. Treat pairings as early hints."))
    else:
        out.append(Readiness("Combo suggestions", "ready", f"{multi:,} orders with 2+ items."))

    return out


def status_of(results: list[Readiness], feature: str) -> Readiness:
    return next(r for r in results if r.feature == feature)
