"""Look and feel for the Streamlit app: theme-aware CSS and small HTML building blocks.

Everything visual lives here so app.py can stay about the analysis. Item names come from
uploaded files, so every piece of text is HTML-escaped before it is placed in markup.
"""

from html import escape

FONT_CSS = [
    "https://cdn.jsdelivr.net/npm/@fontsource/bricolage-grotesque@5.3.0/400.css",
    "https://cdn.jsdelivr.net/npm/@fontsource/bricolage-grotesque@5.3.0/600.css",
    "https://cdn.jsdelivr.net/npm/@fontsource/bricolage-grotesque@5.3.0/800.css",
]

PALETTES = {
    "light": {
        "bg": "#f2f5f1", "surface": "#ffffff", "surface2": "#e7eee8", "ink": "#18211c", "ink2": "#4b5a52",
        "line": "#d6dfd8", "hero1": "#1d3529", "hero2": "#2f5140", "accent": "#df9f12", "on_hero": "#eef3ef",
        "on_hero2": "#b9cbbf", "glow1": "rgba(223,159,18,0.10)", "glow2": "rgba(46,107,80,0.10)",
        "shadow": "0 1px 2px rgba(24,33,28,.06), 0 8px 24px -12px rgba(24,33,28,.18)",
    },
    "dark": {
        "bg": "#0f1713", "surface": "#17211c", "surface2": "#1e2a24", "ink": "#e8efe9", "ink2": "#a9b8af",
        "line": "#2a3832", "hero1": "#16291f", "hero2": "#24402f", "accent": "#e9ad2b", "on_hero": "#eef3ef",
        "on_hero2": "#b9cbbf", "glow1": "rgba(233,173,43,0.08)", "glow2": "rgba(80,160,120,0.08)",
        "shadow": "0 1px 2px rgba(0,0,0,.3), 0 10px 28px -14px rgba(0,0,0,.6)",
    },
}

FONT = "'Bricolage Grotesque', system-ui, -apple-system, 'Segoe UI', sans-serif"


def css(theme: str) -> str:
    p = PALETTES["dark" if theme == "dark" else "light"]
    imports = "\n".join(f"@import url('{u}');" for u in FONT_CSS)
    return f"""<style>
{imports}
:root {{
  --ci-bg: {p['bg']}; --ci-surface: {p['surface']}; --ci-surface2: {p['surface2']};
  --ci-ink: {p['ink']}; --ci-ink2: {p['ink2']}; --ci-line: {p['line']}; --ci-accent: {p['accent']};
  --ci-shadow: {p['shadow']};
}}

/* ---------- canvas ---------- */
[data-testid="stAppViewContainer"] {{
  background:
    radial-gradient(900px 500px at 100% -10%, {p['glow1']}, transparent 60%),
    radial-gradient(800px 600px at -10% 30%, {p['glow2']}, transparent 60%),
    var(--ci-bg);
}}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stMainBlockContainer"] {{ padding-top: 2.2rem; max-width: 1180px; }}

/* ---------- type: our font on text, never on icon glyphs ---------- */
.stApp, .stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
.stApp button, .stApp input, .stApp textarea, .stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stCaptionContainer"], .stApp [data-testid="stWidgetLabel"] {{
  font-family: {FONT} !important;
}}
.stApp h2, .stApp h3 {{ letter-spacing: -0.02em; }}

/* ---------- motion ---------- */
@keyframes ci-rise {{ from {{ opacity: 0; transform: translateY(14px); }} to {{ opacity: 1; transform: none; }} }}
@keyframes ci-drift {{ 0% {{ background-position: 0% 50%; }} 50% {{ background-position: 100% 50%; }} 100% {{ background-position: 0% 50%; }} }}
@keyframes ci-pop {{ from {{ transform: scale(.6); opacity: 0; }} to {{ transform: scale(1); opacity: 1; }} }}
.ci-rise {{ animation: ci-rise .7s cubic-bezier(.2,.8,.2,1) both; animation-delay: var(--d, 0s); }}
@media (prefers-reduced-motion: reduce) {{
  .ci-rise, .ci-hero, .ci-badge {{ animation: none !important; }}
  .ci-card, .ci-action {{ transition: none !important; }}
}}

/* ---------- hero ---------- */
.ci-hero {{
  position: relative; overflow: hidden; border-radius: 26px; padding: 34px 34px 26px;
  background: linear-gradient(120deg, {p['hero1']}, {p['hero2']}, {p['hero1']});
  background-size: 220% 220%; animation: ci-drift 18s ease-in-out infinite;
  color: {p['on_hero']}; box-shadow: var(--ci-shadow);
}}
.ci-hero::after {{
  content: ""; position: absolute; right: -80px; top: -120px; width: 340px; height: 340px; border-radius: 50%;
  background: radial-gradient(circle, rgba(223,159,18,.35), transparent 65%); pointer-events: none;
}}
.ci-hero .ci-hello {{ font-size: .95rem; color: {p['on_hero2']}; margin: 0 0 4px; }}
.ci-hero h1 {{ font-size: clamp(1.9rem, 3.6vw, 2.8rem); line-height: 1.05; font-weight: 800; letter-spacing: -0.03em;
  margin: 0 0 8px; color: {p['on_hero']}; padding: 0; }}
.ci-hero .ci-sub {{ color: {p['on_hero2']}; margin: 0 0 24px; font-size: 1rem; }}
.ci-kpis {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; position: relative; z-index: 1; }}
.ci-kpi {{ background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.10); border-radius: 18px; padding: 14px 16px; }}
.ci-kpi .l {{ font-size: .82rem; color: {p['on_hero2']}; display: flex; gap: 6px; align-items: center; }}
.ci-kpi .v {{ font-size: clamp(1.3rem, 2.4vw, 1.9rem); font-weight: 800; letter-spacing: -0.02em; margin-top: 4px; color: #fff; }}
@media (max-width: 760px) {{ .ci-kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} .ci-hero {{ padding: 24px 20px 20px; }} }}

/* ---------- section heads ---------- */
.ci-section {{ margin: 6px 0 14px; }}
.ci-section h2 {{ font-size: clamp(1.5rem, 2.6vw, 2rem); font-weight: 800; margin: 0 0 10px; padding: 0; color: var(--ci-ink); }}
.ci-how {{ display: inline-flex; gap: 10px; align-items: flex-start; background: var(--ci-surface2); color: var(--ci-ink2);
  border-radius: 14px; padding: 10px 14px; font-size: .93rem; line-height: 1.45; max-width: 820px; }}
.ci-how b {{ color: var(--ci-ink); }}
.ci-headline {{ font-size: clamp(1.15rem, 2vw, 1.45rem); font-weight: 700; color: var(--ci-ink); margin: 18px 0 6px; letter-spacing: -0.01em; }}
.ci-label {{ font-weight: 600; color: var(--ci-ink2); margin: 14px 0 0; font-size: .95rem; }}

/* ---------- action cards ---------- */
.ci-actions-head {{ display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin: 26px 0 12px; }}
.ci-actions-head h2 {{ font-size: 1.45rem; font-weight: 800; margin: 0; padding: 0; color: var(--ci-ink); }}
.ci-actions-head span {{ color: var(--ci-ink2); font-size: .9rem; }}
.ci-actions {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }}
.ci-action {{ display: flex; gap: 14px; align-items: flex-start; background: var(--ci-surface); border: 1px solid var(--ci-line);
  border-radius: 20px; padding: 16px 18px; box-shadow: var(--ci-shadow); transition: transform .25s ease, box-shadow .25s ease; }}
.ci-action:hover {{ transform: translateY(-3px); }}
.ci-badge {{ flex: none; width: 42px; height: 42px; border-radius: 14px; display: grid; place-items: center; font-size: 1.25rem;
  background: color-mix(in srgb, var(--tone) 16%, transparent); animation: ci-pop .5s cubic-bezier(.3,1.6,.5,1) both; animation-delay: var(--d, 0s); }}
.ci-action .t {{ font-weight: 700; color: var(--ci-ink); line-height: 1.3; margin-bottom: 4px; }}
.ci-action .b {{ color: var(--ci-ink2); font-size: .92rem; line-height: 1.45; }}

/* ---------- group cards ---------- */
.ci-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr)); gap: 14px; margin-top: 10px; }}
.ci-card {{ background: var(--ci-surface); border: 1px solid var(--ci-line); border-radius: 22px; padding: 18px 20px 16px;
  box-shadow: var(--ci-shadow); position: relative; overflow: hidden; transition: transform .25s ease; }}
.ci-card:hover {{ transform: translateY(-3px); }}
.ci-card::before {{ content: ""; position: absolute; inset: 0 0 auto 0; height: 5px; background: var(--tone); }}
.ci-card .h {{ display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }}
.ci-card .h .i {{ width: 36px; height: 36px; border-radius: 12px; display: grid; place-items: center; font-size: 1.1rem;
  background: color-mix(in srgb, var(--tone) 16%, transparent); }}
.ci-card .h .n {{ font-weight: 800; font-size: 1.15rem; color: var(--ci-ink); letter-spacing: -0.01em; }}
.ci-card .h .c {{ margin-left: auto; font-size: .8rem; color: var(--ci-ink2); background: var(--ci-surface2); padding: 3px 10px; border-radius: 999px; }}
.ci-card .m {{ color: var(--ci-ink2); font-size: .92rem; margin: 2px 0 10px; line-height: 1.45; }}
.ci-card .do {{ font-weight: 600; color: var(--ci-ink); font-size: .92rem; margin-bottom: 10px; }}
.ci-card ul {{ list-style: none; margin: 0 !important; padding: 0 !important; }}
.ci-card li {{ margin: 0 !important; padding: 9px 0; border-top: 1px dashed var(--ci-line); font-size: .9rem; color: var(--ci-ink2); line-height: 1.45; }}
.ci-card li b {{ color: var(--ci-ink); }}
.ci-chips {{ display: flex; flex-wrap: wrap; gap: 6px; }}
.ci-chip {{ background: var(--ci-surface2); color: var(--ci-ink); border-radius: 999px; padding: 4px 11px; font-size: .86rem; }}
.ci-more {{ color: var(--ci-ink2); font-size: .82rem; margin-top: 8px; }}

/* ---------- combo cards ---------- */
.ci-pair {{ font-weight: 800; font-size: 1.15rem; color: var(--ci-ink); margin: 2px 0 8px; letter-spacing: -0.01em; }}
.ci-tag {{ display: inline-block; font-size: .8rem; font-weight: 600; border-radius: 999px; padding: 4px 10px; margin-bottom: 10px;
  background: color-mix(in srgb, var(--tone) 16%, transparent); color: var(--ci-ink); }}
.ci-stats {{ display: flex; gap: 22px; margin-top: 12px; padding-top: 10px; border-top: 1px dashed var(--ci-line); }}
.ci-stats div {{ font-size: .8rem; color: var(--ci-ink2); }}
.ci-stats b {{ display: block; font-size: 1.2rem; color: var(--ci-ink); letter-spacing: -0.01em; }}

/* ---------- Streamlit widgets, restyled ---------- */
/* tabs as pills (two selector sets: newer Streamlit uses react-aria, older uses baseweb) */
[data-testid="stTabs"] [role="tablist"], [data-baseweb="tab-list"] {{
  gap: 6px; background: var(--ci-surface2); padding: 6px; border-radius: 999px; width: fit-content; max-width: 100%;
  overflow-x: auto; border: none !important; box-shadow: none !important; }}
[data-testid="stTab"], [data-baseweb="tab"] {{
  border-radius: 999px !important; padding: 8px 18px !important; height: auto !important; margin: 0 !important;
  transition: background .2s ease, transform .2s ease; }}
[data-testid="stTab"]:hover, [data-baseweb="tab"]:hover {{ transform: translateY(-1px); }}
[data-testid="stTab"][aria-selected="true"], [data-baseweb="tab"][aria-selected="true"] {{
  background: var(--ci-surface) !important; box-shadow: var(--ci-shadow); }}
[data-testid="stTab"] p {{ font-weight: 600; }}
.react-aria-SelectionIndicator, [data-baseweb="tab-highlight"], [data-baseweb="tab-border"] {{ display: none !important; }}
[data-testid="stExpander"] details {{ border-radius: 16px !important; border-color: var(--ci-line) !important; background: var(--ci-surface); }}
[data-testid="stAlert"] {{ border-radius: 16px; }}
[data-testid="stPlotlyChart"] {{ background: var(--ci-surface); border: 1px solid var(--ci-line); border-radius: 22px; padding: 10px 8px 4px; box-shadow: var(--ci-shadow); }}
[data-testid="stDataFrame"] {{ border-radius: 14px; overflow: hidden; }}
[data-testid="stSidebar"] {{ border-right: 1px solid var(--ci-line); }}
[data-testid="stSidebar"] h2 {{ font-weight: 800; letter-spacing: -0.01em; }}
</style>"""


def _tone(color: str) -> str:
    return f"--tone:{color};"


__all__ = ["css", "escape", "hero", "actions", "section", "headline", "label", "group_cards", "chip_cards", "combo_cards"]


def hero(hello: str, title: str, sub: str, kpis: list[tuple[str, str, str]]) -> str:
    tiles = "".join(
        f'<div class="ci-kpi ci-rise" style="--d:{0.15 + i * 0.08:.2f}s"><div class="l">{icon} {escape(label)}</div>'
        f'<div class="v">{escape(value)}</div></div>'
        for i, (icon, label, value) in enumerate(kpis))
    return (f'<div class="ci-hero"><p class="ci-hello ci-rise">{escape(hello)}</p>'
            f'<h1 class="ci-rise" style="--d:.05s">{escape(title)}</h1>'
            f'<p class="ci-sub ci-rise" style="--d:.1s">{escape(sub)}</p><div class="ci-kpis">{tiles}</div></div>')


def actions(items: list[dict]) -> str:
    """items: {icon, title, body, color}. Title and body may contain <b> from our own code only."""
    cards = "".join(
        f'<div class="ci-action ci-rise" style="--d:{0.1 + i * 0.07:.2f}s;{_tone(a["color"])}">'
        f'<div class="ci-badge" style="--d:{0.25 + i * 0.07:.2f}s">{a["icon"]}</div>'
        f'<div><div class="t">{a["title"]}</div><div class="b">{a["body"]}</div></div></div>'
        for i, a in enumerate(items))
    return (f'<div class="ci-actions-head"><h2>Your top actions this week</h2>'
            f'<span>Each one comes from your own sales</span></div><div class="ci-actions">{cards}</div>')


def section(question: str, how: str) -> str:
    return (f'<div class="ci-section ci-rise"><h2>{escape(question)}</h2>'
            f'<div class="ci-how">💡<span><b>How to read this:</b> {escape(how)}</span></div></div>')


def headline(text: str) -> str:
    return f'<div class="ci-headline ci-rise">{escape(text)}</div>'


def label(text: str) -> str:
    return f'<div class="ci-label">{escape(text)}</div>'


def group_cards(groups: list[dict], max_items: int = 8) -> str:
    """groups: {icon, name, color, meaning, do, items: [(name, detail)]}."""
    cards = []
    for i, g in enumerate(groups):
        rows = "".join(f"<li><b>{escape(n)}</b>: {escape(d)}</li>" for n, d in g["items"][:max_items])
        more = (f'<div class="ci-more">…and {len(g["items"]) - max_items} more in the table below.</div>'
                if len(g["items"]) > max_items else "")
        body = f"<ul>{rows}</ul>{more}" if g["items"] else '<div class="ci-more">None right now.</div>'
        count = len(g["items"])
        cards.append(
            f'<div class="ci-card ci-rise" style="--d:{0.05 + i * 0.07:.2f}s;{_tone(g["color"])}">'
            f'<div class="h"><span class="i">{g["icon"]}</span><span class="n">{escape(g["name"])}</span>'
            f'<span class="c">{count} item{"s" if count != 1 else ""}</span></div>'
            f'<div class="m">{escape(g["meaning"])}</div><div class="do">What to do: {escape(g["do"])}</div>{body}</div>')
    return f'<div class="ci-grid">{"".join(cards)}</div>'


def chip_cards(groups: list[dict], max_items: int = 18) -> str:
    """groups: {icon, name, color, do, items: [names]}."""
    cards = []
    for i, g in enumerate(groups):
        chips = "".join(f'<span class="ci-chip">{escape(n)}</span>' for n in g["items"][:max_items])
        more = f'<div class="ci-more">and {len(g["items"]) - max_items} more</div>' if len(g["items"]) > max_items else ""
        cards.append(
            f'<div class="ci-card ci-rise" style="--d:{0.05 + i * 0.07:.2f}s;{_tone(g["color"])}">'
            f'<div class="h"><span class="i">{g["icon"]}</span><span class="n">{escape(g["name"])}</span>'
            f'<span class="c">{len(g["items"])} items</span></div><div class="do">{escape(g["do"])}</div>'
            f'<div class="ci-chips">{chips or "None right now."}</div>{more}</div>')
    return f'<div class="ci-grid">{"".join(cards)}</div>'


def combo_cards(cards: list[dict]) -> str:
    """cards: {pair, tag, color, pitch, stats: [(label, value)]}."""
    out = []
    for i, c in enumerate(cards):
        stats = "".join(f"<div><b>{escape(v)}</b>{escape(k)}</div>" for k, v in c["stats"])
        out.append(
            f'<div class="ci-card ci-rise" style="--d:{0.05 + i * 0.06:.2f}s;{_tone(c["color"])}">'
            f'<div class="ci-pair">{escape(c["pair"])}</div><span class="ci-tag">{escape(c["tag"])}</span>'
            f'<div class="m">{escape(c["pitch"])}</div><div class="ci-stats">{stats}</div></div>')
    return f'<div class="ci-grid">{"".join(out)}</div>'
