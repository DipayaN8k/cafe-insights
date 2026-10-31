"""Build the static website into dist/ for Netlify or GitHub Pages.

- Fills {{PLACEHOLDERS}} in every page from site_config.json and inserts the
  shared header/footer ({{> header}}, {{> footer}}).
- Copies the Python app (app.py, cafe_insights/, sample data) into dist/app/files/
  so stlite can run it inside the visitor's browser. No server-side Python.

Usage:
    python3 scripts/build_site.py                           # local preview; TODOs allowed
    python3 scripts/build_site.py --strict                  # Netlify production
    python3 scripts/build_site.py --strict --target github  # GitHub Pages (served under /<repo>/)
"""

import datetime as dt
import json
import os
import re
import shutil
import sys
import tomllib
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
ROOT_LINK = re.compile(r'(href|src)="/(?!/)')


def target_settings(target: str, config: dict) -> dict:
    """Where the site is served from changes its base path, its address and who hosts it."""
    if target == "github":
        owner, repo = os.environ.get("GITHUB_REPOSITORY", "DipayaN8k/cafe-insights").split("/")
        return {"BASE": f"/{repo}/", "DOMAIN": f"{owner.lower()}.github.io/{repo}",
                "HOST_PROVIDER": "GitHub, Inc. (GitHub Pages)", "HOST_LOCATION": "United States and global network",
                "meta_csp": True}  # GitHub Pages can't send custom headers, so put the policy in the page
    return {"BASE": "/", "DOMAIN": config["DOMAIN"], "HOST_PROVIDER": "Netlify, Inc.",
            "HOST_LOCATION": "United States and global edge network", "meta_csp": False}


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


def csp_for(rel_path: str) -> str:
    """The Content-Security-Policy netlify.toml would send for this page, minus header-only directives."""
    policy = ""
    for rule in tomllib.loads((ROOT / "netlify.toml").read_text()).get("headers", []):
        pattern = rule["for"].rstrip("*")
        if ("/" + rel_path).startswith(pattern) and "Content-Security-Policy" in rule["values"]:
            policy = rule["values"]["Content-Security-Policy"]
    # frame-ancestors only works as a real header; browsers ignore (and warn about) it in a meta tag.
    return "; ".join(d for d in policy.split("; ") if not d.startswith("frame-ancestors"))


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


def main(strict: bool, target: str) -> None:
    config = load_config(strict)
    settings = target_settings(target, config)
    if DIST.exists():
        shutil.rmtree(DIST)
    files = app_files()
    values = {**config, **{k: v for k, v in settings.items() if isinstance(v, str)},
              "STLITE_VERSION": STLITE_VERSION, "APP_FILES_JSON": json.dumps(files, indent=2),
              "REQUIREMENTS_JSON": json.dumps(REQUIREMENTS)}
    partials = {p.stem: p.read_text() for p in (SITE / "_partials").glob("*.html")}

    pages = 0
    for src in SITE.rglob("*"):
        rel = src.relative_to(SITE)
        if src.is_dir() or rel.parts[0] == "_partials":
            continue
        dest = DIST / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix == ".html":
            html = render(src.read_text(), values, partials, src)
            html = ROOT_LINK.sub(lambda m: f'{m.group(1)}="{settings["BASE"]}', html)
            if settings["meta_csp"]:
                meta = f'<meta http-equiv="Content-Security-Policy" content="{csp_for(rel.as_posix())}">'
                html = html.replace('<meta charset="utf-8">', f'<meta charset="utf-8">\n  {meta}', 1)
            dest.write_text(html)
            pages += 1
        else:
            shutil.copy2(src, dest)

    print(f"Built {pages} pages and {len(files)} app files into {DIST.relative_to(ROOT)}/ "
          f"for {target} (served at {settings['DOMAIN']})")


if __name__ == "__main__":
    args = sys.argv[1:]
    target = args[args.index("--target") + 1] if "--target" in args else "netlify"
    main(strict="--strict" in args, target=target)
