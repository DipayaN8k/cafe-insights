# Datasets

Real and realistic cafe sales data for trying the app without asking any business for its data.

| Folder | Source | Licence | In this repo? |
|---|---|---|---|
| `bread_basket/bread_basket.csv` | [The Bread Basket](https://www.openml.org/d/43422), a bakery in Edinburgh, Oct 2016 – Apr 2017, 20,507 rows | CC0 (public domain) | Yes |
| `maven_coffee_shop/` | [Coffee Shop Sales](https://mavenanalytics.io/data-playground/coffee-shop-sales), Maven Analytics: three fictional New York shops, Jan – Jun 2023, 149,116 rows | Public domain (per Maven's Data Playground) | No (23 MB): download it from Maven |
| — | [French bakery daily sales](https://www.kaggle.com/datasets/matthieugimbert/french-bakery-daily-sales), a bakery in France, 2021 – 2022 | See Kaggle page | No: needs a free Kaggle account |

## Using them in the app

- **Bread Basket:** no prices, so rankings use units sold. Keep "Dates are written day first" ticked and set the holiday calendar to `GB`.
- **Maven coffee shop:** choose `$`, switch on "Estimate them for me" for costs, holiday calendar `US`. Each transaction is a single product, so there are no combo ideas.
- **French bakery:** choose `€`, untick day-first, and switch on "Estimate them for me".

`bread_basket.csv` was converted from the original ARFF file on OpenML; the rows are unchanged.
