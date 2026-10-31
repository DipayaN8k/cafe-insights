"""Cafe Insights: upload a POS export, get menu, stock, prep and combo advice in plain English.

Run: streamlit run app.py
"""

from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ui
from cafe_insights import abc_analysis, basket, data, forecast, menu_engineering, readiness
from cafe_insights import weather as weather_mod
from cafe_insights.text import money, times

SAMPLE_DIR = Path(__file__).parent / "sample_data"
SAMPLE = "Sample cafe (Mumbai, 1 year)"
UPLOAD = "Upload my files"
NEW_CAFE = "Brand-new cafe (no sales yet)"
STATUS_ICON = {"ready": "✅", "limited": "⚠️", "blocked": "⛔"}

st.set_page_config(page_title="Cafe Insights", page_icon="☕", layout="wide")
THEME = "dark" if st.context.theme.type == "dark" else "light"
st.html(ui.css(THEME))


# ---------- colors (validated categorical slots + ordinal blue ramp) ----------

def palette() -> dict:
    dark = THEME == "dark"
    return {
        "Star": "#3987e5" if dark else "#2a78d6",
        "Plowhorse": "#d95926" if dark else "#eb6834",
        "Puzzle": "#199e70" if dark else "#1baf7a",
        "Dog": "#898781",
        "A": "#3987e5" if dark else "#1c5cab",
        "B": "#256abf" if dark else "#3987e5",
        "C": "#184f95" if dark else "#86b6ef",
        "actual": "#3987e5" if dark else "#2a78d6",
        "forecast": "#e9ad2b" if dark else "#df9f12",
        "ink": "#e8efe9" if dark else "#18211c",
        "ink2": "#a9b8af" if dark else "#4b5a52",
        "grid": "#2a3832" if dark else "#e3e9e4",
        "violet": "#9085e9" if dark else "#6250d6",
    }


colors = palette()


def style(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=8, r=16, t=12, b=8), hoverlabel=dict(font_size=14, font_family=ui.FONT),
                      legend=dict(orientation="h", y=1.08, x=0, font=dict(size=13)),
                      font=dict(size=13, family=ui.FONT, color=colors["ink2"]),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig


def bar_chart(names, values, bar_colors, labels, hover, height_per_bar=32, legend=None) -> go.Figure:
    """Horizontal bars, biggest at the top, value written on each bar. One axis, nothing else."""
    fig = go.Figure()
    groups = legend or {None: None}
    for group, color in groups.items():
        mask = [c == color for c in bar_colors] if legend else [True] * len(bar_colors)
        fig.add_trace(go.Bar(
            x=[v for v, m in zip(values, mask) if m], y=[n for n, m in zip(names, mask) if m],
            orientation="h", name=group,
            marker=dict(color=[c for c, m in zip(bar_colors, mask) if m], cornerradius=6),
            text=[t for t, m in zip(labels, mask) if m], textposition="outside", cliponaxis=False,
            textfont=dict(color=colors["ink"]),
            hovertext=[h for h, m in zip(hover, mask) if m], hoverinfo="text"))
    fig.update_yaxes(categoryorder="array", categoryarray=list(names)[::-1], title=None,
                     tickfont=dict(color=colors["ink"]))
    fig.update_xaxes(visible=False, range=[0, max(values) * 1.3 if len(values) else 1])
    fig.update_layout(bargap=0.32, barmode="overlay", showlegend=bool(legend))
    return style(fig, height_per_bar * len(names) + 80)


CHART_CONFIG = {"displayModeBar": False}


def html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


# ---------- data loading ----------

@st.cache_data(show_spinner="Reading and cleaning your data…")
def load(sales_raw, menu_raw, weather_raw, dayfirst: bool):
    report = data.CleaningReport()
    menu = data.clean_menu(menu_raw, report) if menu_raw is not None else None
    sales = data.clean_sales(sales_raw, menu, report, dayfirst=dayfirst) if sales_raw is not None and not sales_raw.empty else None
    weather = data.clean_weather(weather_raw, report) if weather_raw is not None else None
    return sales, menu, weather, report.steps


@st.cache_data(show_spinner=False)
def read_sample():
    return (pd.read_csv(SAMPLE_DIR / "sales.csv"), pd.read_csv(SAMPLE_DIR / "menu.csv"),
            pd.read_csv(SAMPLE_DIR / "weather.csv"))


@st.cache_resource(show_spinner="Learning your weekly patterns…")
def fit_forecast(sales: pd.DataFrame, weather: pd.DataFrame | None, country: str):
    return forecast.fit(sales, weather, country)


@st.cache_data(show_spinner="Checking how accurate the forecast is…")
def run_backtest(sales: pd.DataFrame, weather: pd.DataFrame | None, country: str):
    result = forecast.backtest(sales, weather, country)
    result.pop("detail")
    return result


@st.cache_data(ttl=3600, show_spinner="Getting the weather forecast…")
def get_future_weather(history, start, days, lat, lon, live):
    return weather_mod.future_weather(history, start, days, lat, lon, live)


def read_upload(f) -> pd.DataFrame | None:
    if f is None:
        return None
    return pd.read_excel(f) if f.name.lower().endswith((".xlsx", ".xls")) else pd.read_csv(f)


# ---------- sidebar ----------

with st.sidebar:
    st.header("☕ Your data")
    start_on_upload = st.query_params.get("upload") == "1"  # landing page "Analyse my own sales"
    source = st.radio("Data source", [SAMPLE, UPLOAD, NEW_CAFE], index=1 if start_on_upload else 0,
                      label_visibility="collapsed")
    dayfirst, currency, cafe_name = False, "₹", "Sample Cafe, Mumbai"
    sales_raw = menu_raw = weather_raw = None

    if source == SAMPLE:
        sales_raw, menu_raw, weather_raw = read_sample()
    elif source == UPLOAD:
        sales_file = st.file_uploader("Sales file (required)", type=["csv", "xlsx", "xls"],
                                      help="One row per item sold: bill number, date and time, item, quantity, price.")
        menu_file = st.file_uploader("Menu with costs (optional, for profit)", type=["csv", "xlsx", "xls"],
                                     help="Columns: item, price, unit_cost (what one portion costs you to make).")
        weather_file = st.file_uploader("Past weather (optional)", type=["csv", "xlsx", "xls"],
                                        help="Columns: date, temp_max_c, rain_mm.")
        dayfirst = st.checkbox("Dates are written day first (31/10/2026)", value=True)
        currency = st.selectbox("Currency in your file", ["₹", "$", "€", "£"])
        st.caption("🔒 Your files are analysed inside this browser tab and are never uploaded to our servers. "
                   "Customer names, phone numbers and emails are removed automatically.")
        try:
            sales_raw, menu_raw, weather_raw = read_upload(sales_file), read_upload(menu_file), read_upload(weather_file)
        except Exception as e:
            st.error(f"Couldn't read a file: {e}")
        cafe_name = Path(sales_file.name).stem.replace("_", " ") if sales_file is not None else "your cafe"

    cost_share = None
    if source == UPLOAD and sales_raw is not None:
        st.subheader("Don't know your costs?")
        if st.toggle("Estimate them for me", value=menu_raw is None,
                     help="Used only when your menu file has no costs."):
            cost_share = st.slider("Ingredients and packaging, as a share of price", 15, 60, 30, 5, format="%d%%",
                                   help="Most cafes spend 25–35% of the price on ingredients.") / 100

    with st.expander("Weather and holidays"):
        col1, col2 = st.columns(2)
        lat = col1.number_input("Latitude", value=19.0760, format="%.4f")
        lon = col2.number_input("Longitude", value=72.8777, format="%.4f")
        country = st.text_input("Holiday calendar (country code)", value="IN", max_chars=2).upper() or "IN"
        live_weather = st.toggle("Use live weather forecast", value=True,
                                 help="Sends only these coordinates (rounded) to Open-Meteo; none of your sales data.")

    with st.expander("What should my file look like?"):
        st.markdown(
            "**Sales file** (required): one row per item on a bill, with the bill number, date and time, item name, "
            "quantity and price. Exports from Petpooja, Vyapar, myBillBook and most billing apps work as they are.\n\n"
            "**Menu file** (optional): item, price and unit cost (what one portion costs you to make). "
            "This unlocks profit.\n\n"
            "**Weather file** (optional): date, temp_max_c, rain_mm."
        )
    with st.expander("Practice with real cafe data"):
        st.markdown(
            "Free public datasets you can download and open here:\n\n"
            "- [French bakery daily sales](https://www.kaggle.com/datasets/matthieugimbert/french-bakery-daily-sales): "
            "a real bakery in France, 2021–22, with prices. Choose **€** and untick day-first.\n"
            "- [The Bread Basket](https://www.openml.org/d/43422): a real bakery in Edinburgh, 2016–17. "
            "No prices, so you'll see units sold. Keep day-first ticked and set holidays to **GB**.\n"
            "- [Coffee shop sales](https://mavenanalytics.io/data-playground/coffee-shop-sales) (Maven Analytics): "
            "three New York coffee shops, Jan–Jun 2023. Choose **$** and holidays **US**.\n"
            "- [Coffee sales](https://www.kaggle.com/datasets/ihelon/coffee-sales): a real coffee machine. "
            "No bill numbers, so combo ideas are off."
        )


# ---------- load + readiness ----------

if source == UPLOAD and sales_raw is None:
    html(ui.hero("Welcome", "Let's look at your sales", "Upload your sales file in the sidebar to begin, "
                 "or switch to the sample cafe to explore.", []))
    st.stop()

try:
    sales, menu, weather, cleaning_steps = load(sales_raw, menu_raw, weather_raw, dayfirst)
except ValueError as e:
    st.error(str(e))
    st.stop()

if sales is None:
    html(ui.hero("Welcome", "No sales history yet", "We won't guess what a brand-new cafe should stock.", []))
    st.write("")
    html(ui.group_cards([
        {"icon": "📝", "name": "Your first 4 weeks", "color": colors["forecast"],
         "meaning": "Advice made up without data sounds confident, but it's only a guess, and a wrong guess costs real money in wasted stock.",
         "do": "Start recording now.",
         "items": [("Every sale", "Record it in your billing app, item by item (no \"misc\" entries)."),
                   ("Every cost", "Write down what each item costs you to make: ingredients and packaging."),
                   ("A small menu", "Each item then collects enough sales to judge.")]},
        {"icon": "🔓", "name": "What unlocks when", "color": colors["Puzzle"],
         "meaning": "Each insight switches on by itself once there's enough history.", "do": "Upload again after 4 weeks.",
         "items": [("What never to run out of", f"after {readiness.MIN_DAYS} days of sales"),
                   ("Which items make money", f"after {readiness.MIN_DAYS} days, once costs are added"),
                   ("How much to prepare", f"after {readiness.MIN_DAYS} days (sharper after {readiness.MIN_FORECAST_DAYS})"),
                   ("Combo ideas", f"after {readiness.MIN_BASKET_ORDERS} bills with 2 or more items")]},
    ]))
    st.stop()

priced = data.has_prices(sales)
costs_known = menu is not None and "unit_cost" in menu.columns and menu["unit_cost"].notna().any()
estimated = False
if priced and not costs_known and cost_share is not None:
    menu, estimated = data.estimated_menu(sales, cost_share), True
    cleaning_steps = cleaning_steps + [f"Estimated each item's cost as {cost_share:.0%} of its price (you can change this in the sidebar)"]

status = readiness.assess(sales, menu, weather)
ready = {r.feature: r.status != "blocked" for r in status}
con = data.connect(sales, menu)

first, last = sales["date"].min(), sales["date"].max()
orders = sales["order_id"].nunique()
recent = sales[sales["date"] > last - pd.Timedelta(days=28)]
recent_days = max(recent["date"].nunique(), 1)
if priced:
    kpis = [("💰", "Total sales", money(sales["revenue"].sum(), currency)), ("🧾", "Bills", f"{orders:,}"),
            ("🛍️", "Average bill", money(sales["revenue"].sum() / orders, currency)),
            ("📅", "Average day (4 wks)", money(recent["revenue"].sum() / recent_days, currency))]
else:
    kpis = [("🥐", "Items sold", f"{sales['quantity'].sum():,.0f}"), ("🧾", "Bills", f"{orders:,}"),
            ("🛍️", "Items per bill", f"{sales['quantity'].sum() / orders:.1f}"),
            ("📅", "Items a day (4 wks)", f"{recent['quantity'].sum() / recent_days:,.0f}")]
hour = datetime.now().hour
hello = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
html(ui.hero(f"{hello} 👋", f"Here's how {cafe_name} is doing",
             f"Sales from {first:%d %b %Y} to {last:%d %b %Y} · {sales['item'].nunique()} items on the menu", kpis))


# ---------- run the analyses once; the summary and the tabs share the results ----------

matrix = menu_engineering.classify(con, currency=currency) if ready["Menu matrix"] else pd.DataFrame()
abc = abc_analysis.classify(con, by_money=priced) if ready["Stock priorities (ABC)"] else pd.DataFrame()
fm = pred = None
if ready["Demand forecast"]:
    fm = fit_forecast(sales, weather, country)
    days_ahead = 7
    fc_start = fm.history_end + pd.Timedelta(days=1)
    future_wx, wx_note = get_future_weather(weather, fc_start, days_ahead, lat, lon, live_weather and fm.use_weather)
    pred = forecast.predict(fm, future_wx if fm.use_weather else None, days_ahead)
pair_df = basket.pairs(con) if ready["Combo suggestions"] else pd.DataFrame()
combos_default = (basket.combo_suggestions(pair_df, menu, matrix if not matrix.empty else None, currency=currency)
                  if not pair_df.empty else pd.DataFrame())


# ---------- this week's top actions ----------

acts = []
if not matrix.empty:
    plow = matrix[matrix["class"] == "Plowhorse"].sort_values("extra_per_year", ascending=False)
    if not plow.empty:
        r = plow.iloc[0]
        acts.append({"icon": "💰", "color": colors["forecast"],
                     "title": f"Raise the price of {ui.escape(r['item'])} by {money(r['price_rise'], currency)}",
                     "body": f"A best-seller with a thin profit. This adds about <b>{money(r['extra_per_year'], currency)}</b> a year."})
    gems = matrix[matrix["class"] == "Puzzle"].sort_values("unit_margin", ascending=False)
    if not gems.empty:
        r = gems.iloc[0]
        acts.append({"icon": "💎", "color": colors["Puzzle"], "title": f"Recommend {ui.escape(r['item'])}",
                     "body": f"It earns you {money(r['unit_margin'], currency)} per sale, more than most items, but few people order it."})
    dogs = matrix[matrix["class"] == "Dog"].sort_values("total_margin")
    if not dogs.empty:
        acts.append({"icon": "⚠️", "color": colors["Dog"], "title": f"Rethink {ui.escape(dogs.iloc[0]['item'])}",
                     "body": "It sells little and earns little. Change the recipe or price, or replace it."})
if pred is not None:
    first_day = pred[pred["date"] == pred["date"].min()]
    up = first_day[first_day["advice"].str.contains("more")].sort_values("vs_usual", ascending=False)
    if not up.empty:
        r = up.iloc[0]
        acts.append({"icon": "🧁", "color": colors["actual"],
                     "title": f"{r['date']:%A}: make about {r['vs_usual']:.0%} more {ui.escape(r['item'])}",
                     "body": f"Than a usual {r['date']:%A}. Why: {ui.escape(r['reasons'])}."})
if not combos_default.empty:
    r = combos_default.iloc[0]
    acts.append({"icon": "🤝", "color": colors["violet"],
                 "title": f"Offer {ui.escape(r['offer'])} with every {ui.escape(r['anchor'])}",
                 "body": f"They're bought together {times(r['lift'])} more often than usual."})
if acts:
    html(ui.actions(acts))
st.write("")

with st.expander("🧹 What we cleaned in your file, and what your data can show"):
    st.markdown("\n".join(f"- {s}" for s in cleaning_steps))
    names = {"Menu matrix": "Which items make you money", "Stock priorities (ABC)": "What should never run out",
             "Demand forecast": "How much to prepare", "Combo suggestions": "Combo ideas"}
    st.markdown("\n".join(f"- {STATUS_ICON[r.status]} **{names[r.feature]}:** {r.message}" for r in status))


def gate(feature: str) -> bool:
    """Show the readiness message for a feature; False means don't run it."""
    r = readiness.status_of(status, feature)
    if r.status == "blocked":
        st.warning(f"⛔ {r.message}")
        return False
    if r.status == "limited":
        st.info(f"⚠️ {r.message}")
    return True


tab_menu, tab_abc, tab_fc, tab_combo = st.tabs(
    ["💰 Money makers", "📦 Never run out", "🧁 Prep plan", "🤝 Combo ideas"])

# ---------- which items make money (menu engineering) ----------

with tab_menu:
    html(ui.section("Which items make you money?",
                    "for every item we checked two things: how often it sells, and how much you keep from each sale "
                    "after paying for ingredients. That puts each item in one of the four groups below."))
    if gate("Menu matrix"):
        if estimated:
            st.warning(f"These profits use an **estimated** cost of {cost_share:.0%} of each price. With estimated costs, "
                       "pricier items always look more profitable. Add your real costs in a menu file for a true picture.")
        missing = menu_engineering.items_without_cost(con)
        if missing:
            st.caption(f"Left out because the menu file has no cost for them: {', '.join(missing)}")

        s = menu_engineering.summary(matrix)
        html(ui.headline(f"Your winners bring in {s['star_margin_share']:.0%} of all your profit."))

        groups = menu_engineering.GROUPS
        top = matrix.sort_values("total_margin", ascending=False).head(20)
        html(ui.label("How much profit each item made you"))
        st.plotly_chart(bar_chart(
            names=top["item"], values=top["total_margin"].clip(lower=0),
            bar_colors=[colors[c] for c in top["class"]],
            labels=[money(v, currency) for v in top["total_margin"]],
            hover=[f"<b>{i}</b><br>{u:,.0f} sold × {money(m, currency)} kept each = {money(t, currency)}"
                   for i, u, m, t in zip(top["item"], top["units"], top["unit_margin"], top["total_margin"])],
            legend={f"{groups[c]['icon']} {groups[c]['name']}": colors[c] for c in menu_engineering.ORDER
                    if c in set(top["class"])},
        ), width="stretch", config=CHART_CONFIG)
        if len(matrix) > len(top):
            st.caption(f"Showing your top {len(top)} of {len(matrix)} items. All items are in the table below.")

        html(ui.group_cards([
            {"icon": groups[c]["icon"], "name": groups[c]["name"], "color": colors[c],
             "meaning": groups[c]["meaning"], "do": groups[c]["do"],
             "items": list(zip(matrix.loc[matrix["class"] == c, "item"], matrix.loc[matrix["class"] == c, "action"]))}
            for c in menu_engineering.ORDER
        ]))
        st.write("")
        with st.expander("See the full numbers"):
            st.dataframe(
                matrix[["item", "group", "units", "avg_price", "unit_cost", "unit_margin", "total_margin"]],
                hide_index=True, width="stretch",
                column_config={
                    "item": "Item", "group": "Group", "units": st.column_config.NumberColumn("Sold", format="%d"),
                    "avg_price": st.column_config.NumberColumn("Price", format="%.2f"),
                    "unit_cost": st.column_config.NumberColumn("Cost to make", format="%.2f"),
                    "unit_margin": st.column_config.NumberColumn("You keep per sale", format="%.2f"),
                    "total_margin": st.column_config.NumberColumn("Total profit", format="localized"),
                },
            )
        with st.expander("How we worked this out"):
            st.markdown(
                f"- **Profit per sale** = price − cost to make. The average across your menu is "
                f"{money(matrix['margin_threshold'].iat[0], currency)}.\n"
                f"- An item counts as **popular** if it sells at least 70% of what an average item would "
                f"(here: {matrix['popularity_threshold'].iat[0] * matrix['units'].sum():,.0f} or more sold).\n"
                "- Popular + above-average profit = Winner. Popular + below-average = Popular, low profit. "
                "Not popular + above-average = Hidden gem. Not popular + below-average = Under-performer.\n"
                "- This is the *menu engineering* method used by restaurants worldwide since the 1980s."
            )

# ---------- what never to run out of (ABC) ----------

with tab_abc:
    html(ui.section("What should never run out?",
                    "a few items bring in most of your " + ("money" if priced else "sales") +
                    ". If one of them runs out, you lose the most. Longer bars matter more."))
    if gate("Stock priorities (ABC)"):
        html(ui.headline(abc_analysis.headline(abc, by_money=priced)))
        top = abc.head(20)
        groups = abc_analysis.GROUPS
        st.plotly_chart(bar_chart(
            names=top["item"], values=top["sales"], bar_colors=[colors[c] for c in top["abc_class"]],
            labels=[money(v, currency) if priced else f"{v:,.0f} sold" for v in top["sales"]],
            hover=[f"<b>{i}</b><br>{(money(v, currency) if priced else f'{v:,.0f} sold')} ({sh:.0%} of the total)"
                   for i, v, sh in zip(top["item"], top["sales"], top["share"])],
            legend={f"{n}. {groups[c]['name']}": colors[c] for n, c in enumerate("ABC", 1) if c in set(top["abc_class"])},
        ), width="stretch", config=CHART_CONFIG)
        if len(abc) > len(top):
            st.caption(f"Showing your top {len(top)} of {len(abc)} items.")

        html(ui.chip_cards([
            {"icon": ["🔴", "🟡", "⚪"][n], "name": f"{n + 1}. {groups[c]['name']}", "color": colors[c],
             "do": groups[c]["do"], "items": abc.loc[abc["abc_class"] == c, "item"].tolist()}
            for n, c in enumerate("ABC")
        ]))
        st.write("")
        with st.expander("See the full numbers"):
            st.dataframe(
                abc[["item", "group", "sales", "share", "units"]], hide_index=True, width="stretch",
                column_config={
                    "item": "Item", "group": "Group",
                    "sales": st.column_config.NumberColumn("Sales" if priced else "Units sold", format="localized"),
                    "share": st.column_config.NumberColumn("Share of total", format="percent"),
                    "units": st.column_config.NumberColumn("Units sold", format="%d"),
                },
            )
        with st.expander("How we worked this out"):
            st.markdown(
                "- We ranked items from biggest seller to smallest and added them up from the top.\n"
                "- The items that make up the first 80% are group 1, the next 15% group 2, the last 5% group 3.\n"
                "- This is called *ABC analysis* (or the 80/20 rule), used by shops and warehouses everywhere."
            )

# ---------- how much to prepare (forecast) ----------

with tab_fc:
    html(ui.section("How much to prepare next week",
                    "we learned your weekly pattern from past sales, then adjusted for public holidays and the "
                    "weather forecast. \"Usual\" means the average of the last 8 of the same weekday."))
    if gate("Demand forecast"):
        bt = run_backtest(sales, weather, country)
        per_day = pred.groupby("date")[["forecast_units", "usual_units"]].sum().reset_index()
        busiest = per_day.loc[per_day["forecast_units"].idxmax(), "date"]
        quietest = per_day.loc[per_day["forecast_units"].idxmin(), "date"]
        html(ui.headline(f"Busiest day: {busiest:%A}. Quietest: {quietest:%A}."))

        bar_cols = [colors["forecast"] if d == busiest else colors["actual"] for d in per_day["date"]]
        fig = go.Figure(go.Bar(
            x=[f"{d:%a %d %b}" for d in per_day["date"]], y=per_day["forecast_units"],
            marker=dict(color=bar_cols, cornerradius=8), text=[f"{f:,.0f}" for f in per_day["forecast_units"]],
            textposition="outside", cliponaxis=False, textfont=dict(color=colors["ink"]),
            hovertext=[f"{d:%A}: about {f:,.0f} items (a usual {d:%A}: {u:,.0f})"
                       for d, f, u in zip(per_day["date"], per_day["forecast_units"], per_day["usual_units"])],
            hoverinfo="text"))
        fig.update_yaxes(visible=False, range=[0, per_day["forecast_units"].max() * 1.2])
        fig.update_xaxes(tickfont=dict(color=colors["ink"]))
        html(ui.label("Expected items sold each day (busiest day in yellow)"))
        st.plotly_chart(style(fig, 300), width="stretch", config=CHART_CONFIG)

        cafe_wide, item_specific = forecast.weekday_tips(fm)
        html(ui.group_cards([
            {"icon": "📆", "name": "Your weekly rhythm", "color": colors["actual"],
             "meaning": "How the whole menu moves through the week.", "do": "Plan staff and overall prep around it.",
             "items": [(t.split(":")[0], t.split(":", 1)[1].strip()) for t in cafe_wide]},
            {"icon": "🎯", "name": "Items with their own pattern", "color": colors["forecast"],
             "meaning": "Items that break from the weekly rhythm. Your gut feeling won't catch these.",
             "do": "Adjust these items on top of the rhythm.",
             "items": [(t.split(":")[0], t.split(":", 1)[1].strip()) for t in item_specific]},
        ]))

        st.write("")
        day_options = list(pd.DatetimeIndex(pred["date"].unique()))
        chosen = st.segmented_control("Prep list for", day_options, default=day_options[0],
                                      format_func=lambda d: f"{d:%a %d %b}") or day_options[0]
        st.caption("Your prep list: roughly how many of each item to make, and why it differs from a usual day.")
        today = pred[pred["date"] == chosen].sort_values("forecast_units", ascending=False)
        st.dataframe(
            today[["item", "forecast_units", "usual_units", "advice", "reasons"]],
            hide_index=True, width="stretch", height=min(38 + 35 * len(today), 600),
            column_config={
                "item": "Item",
                "forecast_units": st.column_config.NumberColumn("Make about", format="%.0f"),
                "usual_units": st.column_config.NumberColumn(f"A usual {chosen:%A}", format="%.0f"),
                "advice": "What to do", "reasons": "Why",
            },
        )

        item = st.selectbox("Is an item going up or down? Pick one", sorted(fm.items),
                            index=sorted(fm.items).index(today["item"].iat[0]))
        hist = forecast.daily_item_units(sales)
        hist = hist[(hist["item"] == item) & (hist["date"] > fm.history_end - pd.Timedelta(days=56))]
        fut = pred[pred["item"] == item]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=hist["date"], y=hist["units"], name="What you sold", mode="lines",
                                 line=dict(color=colors["actual"], width=2.5, shape="spline", smoothing=0.6),
                                 fill="tozeroy", fillcolor="rgba(42,120,214,0.08)",
                                 hovertemplate="%{x|%a %d %b}: %{y:.0f} sold<extra></extra>"))
        fig.add_trace(go.Scatter(x=fut["date"], y=fut["forecast_units"], name="What we expect", mode="lines+markers",
                                 line=dict(color=colors["forecast"], width=2.5, dash="dash"), marker=dict(size=9),
                                 customdata=fut[["advice"]],
                                 hovertemplate="%{x|%a %d %b}: about %{y:.0f}<br>%{customdata[0]}<extra></extra>"))
        fig.update_layout(hovermode="x unified")
        fig.update_yaxes(title="Sold per day", rangemode="tozero", gridcolor=colors["grid"])
        fig.update_xaxes(gridcolor=colors["grid"])
        st.plotly_chart(style(fig, 320), width="stretch", config=CHART_CONFIG)

        with st.expander("How accurate is this?"):
            regular = (f"- **Regular items** ({bt['regular_items']} items selling 3+ a day) were off by about "
                       f"{bt['regular_model_wape']:.0%}; a simple \"same as the last few weeks\" guess would be off by "
                       f"{bt['regular_naive_wape']:.0%}.\n" if bt["regular_items"] else "")
            st.markdown(
                f"We hid the last {bt['holdout_days']} days of your sales, predicted them, and compared:\n\n"
                f"- **Whole-day totals** were off by about **{bt['model_daily_total_wape']:.0%}** on average.\n"
                f"{regular}"
                f"- **Across all items**, including rare ones, the error was {bt['model_wape']:.0%} "
                f"(simple guess: {bt['naive_wape']:.0%}). Items that sell only now and then are hard for anyone to "
                "predict, so make those to order.\n\n"
                f"Weather: {wx_note if fm.use_weather else 'not used (no past weather in your data)'}. "
                f"Holidays: {country} public holiday calendar."
            )

# ---------- combo ideas (basket analysis) ----------

with tab_combo:
    html(ui.section("Which items do customers buy together?",
                    "we looked at every bill and found pairs of items that appear together far more often than "
                    "you'd expect. Each card says whether to make a combo deal or simply have staff suggest it."))
    if gate("Combo suggestions"):
        discount = st.slider("Combo discount", 5, 25, 10, 5, format="%d%%",
                             help="How much cheaper the pair is than buying both separately.") / 100
        combos = basket.combo_suggestions(pair_df, menu, matrix if not matrix.empty else None,
                                          discount=discount, currency=currency)
        if combos.empty:
            st.info("No pairs are bought together often enough yet to suggest a combo.")
        else:
            cards = []
            for _, c in combos.iterrows():
                deal = c["tactic"] == "Combo deal"
                stats = [("bills with both", f"{c['together']:,}"), ("more often than usual", times(c["lift"]))]
                if deal and pd.notna(c["combo_price"]):
                    stats.append(("combo price", money(c["combo_price"], currency)))
                cards.append({"pair": f"{c['item_a']} + {c['item_b']}", "color": colors["forecast"] if deal else colors["Puzzle"],
                              "tag": "🏷️ Make a combo deal" if deal else "💬 Just ask, no discount",
                              "pitch": c["pitch"], "stats": stats})
            html(ui.combo_cards(cards))
            st.write("")
            with st.expander("See all pairs we found"):
                st.dataframe(
                    pair_df.assign(pct=pair_df[["confidence_a_to_b", "confidence_b_to_a"]].max(axis=1))[
                        ["item_a", "item_b", "together", "pct", "lift"]],
                    hide_index=True, width="stretch",
                    column_config={
                        "item_a": "Item", "item_b": "Bought with", "together": "Bills with both",
                        "pct": st.column_config.NumberColumn("Share of buyers who add the other", format="percent"),
                        "lift": st.column_config.NumberColumn("Times more often than usual", format="%.1f"),
                    },
                )
            with st.expander("How we worked this out"):
                st.markdown(
                    "- For every pair of items we counted the bills that contain both.\n"
                    "- We compared that with how often they'd appear together by pure chance. "
                    "\"6 times more often\" means the pair is a real habit, not a coincidence.\n"
                    "- If 3 or more in 10 buyers already add the second item, we suggest asking rather than "
                    "discounting, because a discount would mostly go to people who'd buy both anyway.\n"
                    "- This is called *market basket analysis*, the same idea online shops use for "
                    "\"customers also bought\"."
                )
