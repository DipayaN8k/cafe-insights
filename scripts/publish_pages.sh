#!/usr/bin/env bash
# Build the site for GitHub Pages and publish it to the gh-pages branch.
set -euo pipefail
cd "$(dirname "$0")/.."
repo_root="$(pwd)"
origin="$(git remote get-url origin)"

python3 scripts/build_site.py --strict --target github
touch dist/.nojekyll  # serve files as they are, no Jekyll processing

tmp="$(mktemp -d)"
cp -R dist/. "$tmp"
cd "$tmp"
git init -q -b gh-pages
git add -A
git commit -q -m "Publish site from $(git -C "$repo_root" rev-parse --short HEAD)"
git push -q -f "$origin" gh-pages
rm -rf "$tmp"
echo "Published. GitHub Pages updates within a minute or two."
