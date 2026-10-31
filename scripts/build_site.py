"""Build the static website into dist/ for Netlify.

- Fills {{PLACEHOLDERS}} in every page from site_config.json and inserts the
  shared header/footer ({{> header}}, {{> footer}}).
- Copies the Python app (app.py, cafe_insights/, sample data) into dist/app/files/
  so stlite can run it inside the visitor's browser. No server-side Python.

Usage:
    python3 scripts/build_site.py            # local preview; TODOs allowed
    python3 scripts/build_site.py --strict   # production; fails while any TODO remains
"""

import datetime as dt
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE, DIST = ROOT / "site", ROOT / "dist"

# 1.12.0 is the first release whose Pyodide (Python 3.14) includes DuckDB; 1.11.0 fails to install it.
STLITE_VERSION = "1.12.0"
# Pyodide ships pandas, numpy, scikit-learn and duckdb; the rest come from PyPI and are pinned.
REQUIREMENTS = ["pandas", "numpy", "scikit-learn", "duckdb", "plotly==7.1.0", "holidays==0.107", "openpyxl==3.1.5"]
APP_FILES = ["app.py", "ui.py", "cafe_insights/*.py", "sample_data/*.csv"]

PLACEHOLDER = re.compile(r"\{\{\s*([A-Z_]+)\s*\}\}")
PARTIAL = re.compile(r"\{\{>\s*([a-z_]+)\s*\}\}")


def load_config(strict: bool) -> dict:
    config = {k: v for k, v in json.loads((ROOT / "site_config.json").read_text()).items() if not k.startswith("_")}
    todo = [k for k, v in config.items() if "TODO" in str(v)]
    if todo:
        msg = "site_config.json still has TODO values for: " + ", ".join(todo)
        if strict:
            sys.exit(f"ERROR: {msg}\nFill them in before publishing; legal pages must not go live with blanks.")
        print(f"WARNING: {msg}")
    config["YEAR"] = str(dt.date.today().year)
    return config


def app_files() -> dict:
    files = {}
    for pattern in APP_FILES:
        for src in sorted(ROOT.glob(pattern)):
            rel = src.relative_to(ROOT).as_posix()
            dest = DIST / "app" / "files" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            files[rel] = {"url": f"files/{rel}"}
    return files


def render(text: str, values: dict, partials: dict, path: Path) -> str:
    text = PARTIAL.sub(lambda m: partials[m.group(1)], text)
    missing = sorted({m.group(1) for m in PLACEHOLDER.finditer(text) if m.group(1) not in values})
    if missing:
        sys.exit(f"ERROR: {path.relative_to(SITE)} uses unknown placeholder(s): {', '.join(missing)}")
    return PLACEHOLDER.sub(lambda m: values[m.group(1)], text)


def main(strict: bool) -> None:
    config = load_config(strict)
    if DIST.exists():
        shutil.rmtree(DIST)
    files = app_files()
    values = {**config, "STLITE_VERSION": STLITE_VERSION,
              "APP_FILES_JSON": json.dumps(files, indent=2), "REQUIREMENTS_JSON": json.dumps(REQUIREMENTS)}
    partials = {p.stem: p.read_text() for p in (SITE / "_partials").glob("*.html")}

    pages = 0
    for src in SITE.rglob("*"):
        rel = src.relative_to(SITE)
        if src.is_dir() or rel.parts[0] == "_partials":
            continue
        dest = DIST / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix == ".html":
            dest.write_text(render(src.read_text(), values, partials, src))
            pages += 1
        else:
            shutil.copy2(src, dest)

    print(f"Built {pages} pages and {len(files)} app files into {DIST.relative_to(ROOT)}/")


if __name__ == "__main__":
    main(strict="--strict" in sys.argv)
