# ☕ Cafe Insights

**Live demo:** https://dipayan8k.github.io/cafe-insights/ (the app runs entirely in your browser; the first load downloads about 30 MB)

Upload a cafe's POS export and get four answers an owner actually acts on:

| Question | Feature | Method |
|---|---|---|
| Which items are good, which are bad? | **Menu matrix** | Menu engineering (Kasavana & Smith): popularity × profit per unit → Stars, Plowhorses, Puzzles, Dogs |
| What must never run out? | **Stock priorities** | ABC / Pareto analysis on revenue (A = first 80%, B = next 15%, C = rest) |
| How much should I prep tomorrow? | **Prep forecast** | Per-item Poisson regression on weekday, holidays, temperature and rain, with live weather from Open-Meteo |
| What should I bundle or upsell? | **Combos** | Market basket analysis (support, confidence, lift) via a SQL self-join |

It also refuses to guess. A brand-new cafe with no sales gets told so, not a made-up stocking list. Each feature checks whether the data can support it before it runs.

## Run it

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

The app opens with a sample Mumbai cafe (one year, ~80k sales rows). Switch to **Upload my files** to use real data.

Regenerate the sample data or run the tests:

```bash
.venv/bin/python scripts/generate_sample_data.py
.venv/bin/pytest -q
```

## The website (GitHub Pages or Netlify)

The public site is fully static. The Streamlit app runs **inside the visitor's browser** via [stlite](https://github.com/whitphx/stlite) (Python on WebAssembly), so uploaded sales files never reach any server. That's what makes the privacy promise true, and it's why it works on Netlify, which can't run a Python server.

```
site/                 landing page, app shell, legal pages (templates)
  _partials/          shared header and footer
  app/index.html      mounts the Python app with stlite
  privacy/ terms/ refund/ delivery/ contact/
site_config.json      your business details, used on every page
scripts/build_site.py builds dist/ (fills placeholders, copies the Python app)
scripts/serve_dist.py local server that applies netlify.toml headers
netlify.toml          build command + security headers (CSP etc.)
```

**Preview locally**

```bash
python3 scripts/build_site.py && python3 scripts/serve_dist.py
```

Then open http://localhost:8888. The first app load downloads about 30 MB of Python libraries.

**Deploy to GitHub Pages** (current live site)

```bash
scripts/publish_pages.sh
```

This builds with `--target github` (links prefixed with `/cafe-insights/`, the security policy placed in each page because GitHub Pages can't send custom headers) and pushes the result to the `gh-pages` branch, which GitHub Pages serves.

**Deploy to Netlify**

1. Fill in every `TODO` in `site_config.json`: legal name, address, Grievance Officer, emails, domain, effective date. The Netlify build (`--strict`) refuses to publish while any TODO remains.
2. Push the repo to GitHub, then in Netlify choose *Add new site → Import an existing project*. `netlify.toml` already sets the build command and the `dist` publish folder.
3. Under *Domain management*, add your domain. Netlify issues the HTTPS certificate automatically.

**Moving off Netlify later.** `dist/` is plain files, so any static host works (Cloudflare Pages, AWS S3 + CloudFront in Mumbai, Vercel). Copy the headers from `netlify.toml` into the new host's format.

**Legal pages.** These were written against the DPDP Act 2023 and Rules 2025, IT Act s.43A and SPDI Rules 2011, CERT-In Directions 2022, Consumer Protection (E-Commerce) Rules 2020, and the RBI E-mandate Framework 2026. The page set also meets Razorpay's website checklist (privacy, terms, refunds, delivery, contact, pricing). They describe the site as it works today: no accounts, no payments, no analytics. Update them before adding any of those, and have a lawyer review them before you charge money.

## Practise with real cafe data

No cafe has to hand over its data for you to test the system. These public datasets come from real (or realistic) cafes and open directly in the app:

| Dataset | What it is | Notes |
|---|---|---|
| [French bakery daily sales](https://www.kaggle.com/datasets/matthieugimbert/french-bakery-daily-sales) (Kaggle) | A real bakery in France, Jan 2021 – Sep 2022, about 234,000 rows with bill numbers and prices | Choose € in the sidebar. Costs aren't included, so use "Estimate them for me" |
| [The Bread Basket](https://www.openml.org/d/43422) (OpenML, public domain) | A real bakery in Edinburgh, Oct 2016 – Apr 2017, about 20,000 rows | No prices: the app ranks by units sold. Keep day-first ticked |
| [Coffee shop sales](https://mavenanalytics.io/data-playground/coffee-shop-sales) (Maven Analytics) | Three fictional New York coffee shops, Jan–Jun 2023, about 149,000 rows | Choose $. Each row is its own bill, so there are no combo ideas |
| [Coffee sales](https://www.kaggle.com/datasets/ihelon/coffee-sales) (Kaggle) | A real coffee vending machine | No bill numbers, so no combo ideas |

Kaggle needs a free account to download. The importer understands each dataset's column names, decimal-comma euro prices, separate date and time columns, and missing prices or bill numbers. `tests/test_data.py` checks each format.

## Your data

| File | Required columns | Notes |
|---|---|---|
| Sales | `order_id`, `timestamp`, `item` | plus `quantity`, `unit_price`, `channel` if available. Common POS names (*Bill No*, *Item Name*, *Qty*, *Rate*) are mapped automatically |
| Menu | `item`, `unit_cost` | plus `category`, `price`. Without costs you get ABC and forecasts, but no profit-based matrix |
| Weather | `date`, `temp_max_c`, `rain_mm` | optional; enables weather effects in the forecast |

Columns holding customer personal data (names, phone numbers, emails, addresses, customer IDs) are dropped the moment a file is read. The cleaning step then fixes item-name typos and casing (fuzzy-matched to the menu), fills blank quantities and prices, drops voids, bad dates and duplicate rows, and reports every change it made.

## How the analysis works

**Menu matrix.** An item is *popular* if its share of units is at least 70% of a fair share (1 / number of items), and *profitable* if its margin per unit beats the menu's sales-weighted average. Each group gets a specific action. For example, a Plowhorse gets the price rise needed to reach the average margin.

**ABC.** A window-function query ranks items by revenue and assigns each to the class its running total *started* in, so the top seller is always A.

**Prep forecast.** One Poisson GLM per item, with weekday dummies, a holiday flag (from the `holidays` package), scaled temperature and rain, and a trend. Because the model is log-linear, every coefficient is a multiplier, which is what makes the advice explainable:

- *Weekly rhythm*: cafe-wide busy and quiet days.
- *Item-specific rules*: only swings beyond the cafe-wide pattern that pass a rough Poisson significance check (|z| ≥ 3). This filters out noise on low-volume items.
- *Daily prep plan*: compared with **a usual day of the same weekday** (last 8 weeks). The "why" column credits weather against the conditions on those same days.
- *Accuracy check*: a 28-day holdout compared with a naive "average of the same weekday" guess. On the sample data the model is off by 24% per item per day (naive: 27%) and by 8% on the daily total.

**Combos.** Pairs with lift ≥ 1.2 and at least 20 shared orders. Pairs that use a Star to sell a weaker item rank first. If 30%+ of customers already buy both, the advice is a staff upsell prompt rather than a discount, because a discount would just give money back on sales you'd make anyway.

## Project layout

```
app.py                      Streamlit UI
cafe_insights/
  data.py                   column mapping, cleaning, DuckDB connection
  readiness.py              what the data can honestly support
  menu_engineering.py       SQL + classification
  abc_analysis.py           SQL with window functions
  basket.py                 SQL self-join pairs, combo pricing
  forecast.py               Poisson models, prep advice, backtest
  weather.py                Open-Meteo forecast with seasonal fallback
scripts/generate_sample_data.py
sample_data/                sales.csv, menu.csv, weather.csv
tests/                      31 pytest tests
site/, scripts/build_site.py, netlify.toml   the public website (see above)
```

## Known limits

- The sample data is synthetic, with patterns planted on purpose: a Monday croissant dip, heat boosting cold drinks, specific item pairings. Real data will be noisier.
- Forecasts need at least 4 weeks of history; holiday effects need about a year.
- Profit uses a fixed unit cost per item. Ingredient price changes over time aren't modelled yet.
- Each upload is analysed on its own; nothing is stored between sessions.
- The first visit to the web app downloads about 30 MB, which takes 20–40 s on mobile data. After that the browser caches it.
