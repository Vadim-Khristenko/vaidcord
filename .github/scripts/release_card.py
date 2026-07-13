#!/usr/bin/env python3
"""Generate a release card SVG for VaidCord package releases.

Produces a 1200x630 dark, gradient-accented card highlighting the release:
package, version, language, headline stats (tests, commits, diff) and up to
four feature highlights. Pure stdlib; used by the release workflows.

Example:
    python release_card.py \
        --package vaidcord --version 0.2.0 --language Python \
        --tag py-v0.2.0 --repo Vadim-Khristenko/vaidcord \
        --stat "473=tests passing" --stat "89=new API methods" \
        --highlight "Complete voice protocol: play & listen" \
        --out card.svg
"""

from __future__ import annotations

import argparse
import datetime as _dt
from pathlib import Path
from xml.sax.saxutils import escape

WIDTH, HEIGHT = 1200, 630

ACCENTS = {
    "python": ("#38bdf8", "#818cf8"),
    "rust": ("#fb923c", "#f43f5e"),
    "go": ("#22d3ee", "#3b82f6"),
}
DEFAULT_ACCENT = ("#38bdf8", "#818cf8")

FONT = "'Segoe UI', 'Helvetica Neue', Arial, sans-serif"
MONO = "'Cascadia Code', 'JetBrains Mono', 'Fira Code', Consolas, monospace"


def _truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_svg(args: argparse.Namespace) -> str:
    accent_a, accent_b = ACCENTS.get(args.language.lower(), DEFAULT_ACCENT)
    package = escape(args.package.upper())
    version = escape(args.version)
    language = escape(args.language)
    tag = escape(args.tag or f"v{args.version}")
    repo = escape(args.repo)
    date = escape(args.date or _dt.date.today().isoformat())

    stats: list[tuple[str, str]] = []
    for raw in args.stat[:4]:
        value, _, label = raw.partition("=")
        stats.append((escape(_truncate(value, 10)), escape(_truncate(label or "", 22))))

    highlights = [escape(_truncate(h, 76)) for h in args.highlight[:4]]

    dots = []
    for row in range(7):
        for col in range(13):
            dots.append(
                f'<circle cx="{80 + col * 88}" cy="{120 + row * 72}" r="1.6" '
                f'fill="#ffffff" opacity="0.05"/>'
            )
    dot_grid = "".join(dots)

    stat_tiles = []
    tile_w, tile_h, gap = 236, 118, 20
    x0, y0 = 640, 172
    for index, (value, label) in enumerate(stats):
        x = x0 + (index % 2) * (tile_w + gap)
        y = y0 + (index // 2) * (tile_h + gap)
        stat_tiles.append(
            f"""
  <g>
    <rect x="{x}" y="{y}" width="{tile_w}" height="{tile_h}" rx="18"
          fill="#ffffff" fill-opacity="0.045" stroke="#ffffff" stroke-opacity="0.10"/>
    <text x="{x + 24}" y="{y + 52}" font-family="{FONT}" font-size="40"
          font-weight="700" fill="url(#accent)">{value}</text>
    <text x="{x + 24}" y="{y + 86}" font-family="{FONT}" font-size="17"
          fill="#94a3b8" letter-spacing="1.5">{label.upper()}</text>
  </g>"""
        )

    highlight_rows = []
    hy = 452
    for highlight in highlights:
        highlight_rows.append(
            f"""
  <g>
    <circle cx="76" cy="{hy - 6}" r="4" fill="url(#accent)"/>
    <text x="94" y="{hy}" font-family="{FONT}" font-size="20" fill="#cbd5e1">{highlight}</text>
  </g>"""
        )
        hy += 36

    return f"""<svg width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}"
     xmlns="http://www.w3.org/2000/svg" role="img"
     aria-label="{package} {version} release card">
  <defs>
    <linearGradient id="accent" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{accent_a}"/>
      <stop offset="100%" stop-color="{accent_b}"/>
    </linearGradient>
    <radialGradient id="glowA" cx="0.85" cy="0.05" r="0.9">
      <stop offset="0%" stop-color="{accent_b}" stop-opacity="0.28"/>
      <stop offset="55%" stop-color="{accent_b}" stop-opacity="0.06"/>
      <stop offset="100%" stop-color="{accent_b}" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="glowB" cx="0.08" cy="0.95" r="0.8">
      <stop offset="0%" stop-color="{accent_a}" stop-opacity="0.22"/>
      <stop offset="60%" stop-color="{accent_a}" stop-opacity="0.05"/>
      <stop offset="100%" stop-color="{accent_a}" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#0b0e17"/>
      <stop offset="100%" stop-color="#080b12"/>
    </linearGradient>
  </defs>

  <rect width="{WIDTH}" height="{HEIGHT}" fill="url(#bg)"/>
  <rect width="{WIDTH}" height="{HEIGHT}" fill="url(#glowA)"/>
  <rect width="{WIDTH}" height="{HEIGHT}" fill="url(#glowB)"/>
  {dot_grid}
  <rect x="0" y="0" width="{WIDTH}" height="8" fill="url(#accent)"/>

  <text x="72" y="112" font-family="{FONT}" font-size="26" font-weight="600"
        fill="#e2e8f0" letter-spacing="6">{package}</text>
  <rect x="72" y="136" width="150" height="38" rx="19"
        fill="#ffffff" fill-opacity="0.06" stroke="url(#accent)" stroke-opacity="0.8"/>
  <text x="147" y="162" text-anchor="middle" font-family="{FONT}" font-size="19"
        font-weight="600" fill="url(#accent)">{language}</text>

  <text x="66" y="308" font-family="{FONT}" font-size="150" font-weight="800"
        fill="url(#accent)">v{version}</text>
  <text x="74" y="360" font-family="{MONO}" font-size="21" fill="#64748b">{tag} · {date}</text>

  <text x="72" y="412" font-family="{FONT}" font-size="16" font-weight="700"
        fill="#94a3b8" letter-spacing="3">WHAT'S INSIDE</text>
  {''.join(highlight_rows)}
  {''.join(stat_tiles)}

  <line x1="72" y1="576" x2="{WIDTH - 72}" y2="576" stroke="#ffffff" stroke-opacity="0.08"/>
  <text x="72" y="606" font-family="{MONO}" font-size="17" fill="#64748b">{repo}</text>
  <text x="{WIDTH - 72}" y="606" text-anchor="end" font-family="{FONT}" font-size="17"
        font-weight="600" fill="url(#accent)">RELEASE</text>
</svg>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--language", required=True)
    parser.add_argument("--tag", default="")
    parser.add_argument("--repo", default="Vadim-Khristenko/vaidcord")
    parser.add_argument("--date", default="")
    parser.add_argument(
        "--stat",
        action="append",
        default=[],
        help="Stat tile as 'VALUE=label'; up to 4.",
    )
    parser.add_argument(
        "--highlight",
        action="append",
        default=[],
        help="Feature highlight line; up to 4.",
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    Path(args.out).write_text(build_svg(args), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
