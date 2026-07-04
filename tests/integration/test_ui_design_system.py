"""Obsidian Desk design-system application (docs/13 M19): CSS token
contrast, focus-visible rings, tabular numerals, sticky table headers,
reduced-motion, the command palette, and toasts -- applied across the
built FastAPI + Jinja UI, not just described in the spec.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from lqe.live.control import ControlPlane
from lqe.storage.state_reader import StateReader
from lqe.ui.app import create_app
from lqe.ui.data import DeskData

_THEME = Path(__file__).resolve().parents[2] / "src" / "lqe" / "ui" / "theme"
_TEMPLATES = Path(__file__).resolve().parents[2] / "src" / "lqe" / "ui" / "templates"

_DESK_CSS = (_THEME / "desk.css").read_text(encoding="utf-8")

# Every declared color token, parsed straight out of the CSS `:root` block
# rather than hand-copied, so this test can't silently drift from the
# actual values shipped.
_TOKENS: dict[str, str] = dict(
    re.findall(r"--([a-z]+):\s*(#[0-9A-Fa-f]{6})", _DESK_CSS)
)
_BACKGROUNDS = ["void", "desk", "slab"]
_TEXT_COLORS = ["ink", "mute", "amber", "long", "short", "intel"]


def _client() -> TestClient:
    data = DeskData(state_reader=StateReader([]), control=ControlPlane())
    return TestClient(create_app(data))


def _linearize(c: int) -> float:
    c_srgb = c / 255.0
    return c_srgb / 12.92 if c_srgb <= 0.03928 else ((c_srgb + 0.055) / 1.055) ** 2.4


def _luminance(hex_color: str) -> float:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _linearize(r) + 0.7152 * _linearize(g) + 0.0722 * _linearize(b)


def _contrast(fg: str, bg: str) -> float:
    l1, l2 = _luminance(fg), _luminance(bg)
    l1, l2 = max(l1, l2), min(l1, l2)
    return (l1 + 0.05) / (l2 + 0.05)


# -- contrast (docs/13 M19: "every text pair >= 4.5:1") --------------------


def test_every_declared_text_color_clears_aa_on_every_declared_background() -> None:
    failures = [
        (fg, bg, round(_contrast(_TOKENS[fg], _TOKENS[bg]), 2))
        for bg in _BACKGROUNDS
        for fg in _TEXT_COLORS
        if _contrast(_TOKENS[fg], _TOKENS[bg]) < 4.5
    ]
    assert not failures, f"sub-AA text/background pairs: {failures}"


# -- a11y: focus rings, tabular numbers, sticky headers, reduced-motion ----


def test_focus_visible_rings_are_declared() -> None:
    assert ":focus-visible" in _DESK_CSS
    assert "outline:2px solid var(--amber)" in _DESK_CSS


def test_reduced_motion_disables_all_transitions_and_animation() -> None:
    assert "prefers-reduced-motion: reduce" in _DESK_CSS
    block = re.search(r"@media \(prefers-reduced-motion: reduce\)\s*\{[^}]*\{[^}]*\}", _DESK_CSS)
    assert block is not None
    assert "transition" in block.group(0) and "!important" in block.group(0)
    assert "animation" in block.group(0) and "none" in block.group(0)


def test_data_table_cells_declare_tabular_numerals() -> None:
    assert "table.data td" in _DESK_CSS
    # the rule block for table.data td must include tabular-nums
    block = re.search(r"table\.data td\s*\{[^}]*\}", _DESK_CSS)
    assert block is not None
    assert "tabular-nums" in block.group(0)


def test_data_table_headers_are_sticky() -> None:
    block = re.search(r"table\.data thead th\s*\{[^}]*\}", _DESK_CSS)
    assert block is not None
    assert "sticky" in block.group(0)


def test_no_disallowed_emoji_icons() -> None:
    # a narrow, deliberate check: real emoji (colorful pictographs), not the
    # project's existing typographic glyphs (star/check/cross/diamond used
    # as "pair color with a glyph" markers since M7-M10, not emoji-as-icon).
    disallowed = ["🚀", "✅", "❌", "🎉", "🔥", "💰", "💯", "👍", "⚠️", "🟢", "🔴"]
    sources = list(_TEMPLATES.glob("*.html")) + list(_THEME.glob("*.js"))
    offenders = [
        str(p.name) for p in sources if any(e in p.read_text(encoding="utf-8") for e in disallowed)
    ]
    assert not offenders, f"emoji-as-icon found in: {offenders}"


# -- command palette + toasts (rendered on every page) ---------------------


def test_command_palette_markup_is_present_on_every_page() -> None:
    html = _client().get("/").text
    assert 'id="palette-overlay"' in html
    assert 'id="palette-input"' in html
    assert 'id="palette-list"' in html
    assert 'role="dialog"' in html


def test_toast_host_is_present_with_aria_live() -> None:
    html = _client().get("/").text
    assert 'id="toasts"' in html
    assert 'aria-live="polite"' in html


def test_command_palette_hint_shown_in_status_rail() -> None:
    assert "Ctrl/" in _client().get("/").text


def test_command_palette_overlay_is_actually_hidden_by_default() -> None:
    # regression: `.palette-overlay { display:flex; ... }` alone always wins
    # over the browser's default `[hidden] { display:none }` UA rule (same
    # specificity, author beats UA), so the JS's `overlay.hidden = true`
    # toggle (desk.js `close()`) silently did nothing and the palette stayed
    # visible on every page load. Found by actually rendering the page in a
    # browser, not by reading the HTML -- a curl-only check can't see this.
    block = re.search(r"\.palette-overlay\[hidden\]\s*\{[^}]*\}", _DESK_CSS)
    assert block is not None, "no CSS rule forces .palette-overlay to hide when [hidden]"
    assert "display:none" in block.group(0).replace(" ", "")


def test_candlestick_series_uses_fill_vs_outline_not_hue_alone() -> None:
    # docs/13 M19 a11y: bullish/bearish must survive colorblindness, so the
    # up candle is hollow/outline-only (near-transparent fill + a colored
    # border) while the down candle is solid-filled -- not hue alone.
    chart_js = (_THEME / "chart.js").read_text(encoding="utf-8")
    assert "borderVisible: true" in chart_js
    assert "rgba(38,166,154" in chart_js  # near-transparent bullish body
    assert "#EF5350" in chart_js  # solid bearish body
