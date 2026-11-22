"""Render the live stats card shown at the top of each radar's README."""
import datetime as dt

BG, CREAM, MUTED = "#0D0F12", "#F3EFE6", "#A3A9B4"
SANS = "'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(path, stats, accent, label="LIVE DASHBOARD"):
    """stats: list of (big_value, caption) — up to 4."""
    w, h = 1280, 190
    today = dt.date.today().strftime("%d %b %Y").upper()
    col = (w - 128) / len(stats)
    cells = []
    for i, (val, cap) in enumerate(stats):
        x = 64 + i * col
        if i:
            cells.append(f'<line x1="{x - 24:.0f}" x2="{x - 24:.0f}" y1="70" y2="160" stroke="rgba(243,239,230,0.14)"/>')
        cells.append(
            f'<text x="{x:.0f}" y="128" font-size="52" font-weight="700" letter-spacing="-1.5" fill="{CREAM}">{esc(val)}</text>'
            f'<text x="{x:.0f}" y="158" font-family="{MONO}" font-size="13" letter-spacing="1.6" fill="{MUTED}">{esc(str(cap).upper())}</text>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="Live statistics, updated {today}">
<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="20" fill="{BG}" stroke="rgba(243,239,230,0.16)" stroke-width="2"/>
<g font-family="{SANS}">
<circle cx="72" cy="40" r="6" fill="{accent}"><animate attributeName="opacity" values="1;.25;1" dur="1.6s" repeatCount="indefinite"/></circle>
<text x="88" y="45" font-family="{MONO}" font-size="13" letter-spacing="2.5" fill="{accent}">{esc(label)}</text>
<text x="{w - 64}" y="45" text-anchor="end" font-family="{MONO}" font-size="13" letter-spacing="2" fill="{MUTED}">UPDATED {today}</text>
{''.join(cells)}
</g>
</svg>'''
    open(path, "w", encoding="utf-8").write(svg)
