"""Obsidian Desk design-system application (docs/13 M19): CSS token
contrast, focus-visible rings, tabular numerals, sticky table headers,
reduced-motion, and toasts -- applied across the built FastAPI + Jinja
UI, not just described in the spec.
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


# -- toasts (rendered on every page) ----------------------------------------


def test_toast_host_is_present_with_aria_live() -> None:
    html = _client().get("/").text
    assert 'id="toasts"' in html
    assert 'aria-live="polite"' in html


def test_no_leftover_command_palette_markup_or_styling() -> None:
    # the command palette (docs/13 M19) was removed post-v4.0: it opened on
    # every page load/navigation instead of only on Ctrl/Cmd+K (a CSS
    # cascade bug -- `.palette-overlay { display:flex }` always beat the
    # browser's `[hidden]{display:none}`), and wasn't judged worth fixing
    # further since it added no real value. Guards against it creeping back.
    html = _client().get("/").text
    assert "palette" not in html.lower()
    assert "palette" not in _DESK_CSS.lower()
    desk_js = (_THEME / "desk.js").read_text(encoding="utf-8")
    assert "palette" not in desk_js.lower()


def test_v5_m26_type_scale_meets_the_new_floor() -> None:
    # V5 M26 audit §1: body >= 14px, the label selectors named in the
    # build plan's design quick-reference >= 11px, tags/badges >= 10px.
    body_block = re.search(r"\nbody \{[^}]*\}", _DESK_CSS)
    assert body_block is not None
    assert "font-size:14px" in body_block.group(0)

    for selector in [".stat .k {", ".mode {", ".foot {", ".kv .k {"]:
        idx = _DESK_CSS.find(selector)
        assert idx != -1, f"missing selector: {selector}"
        block = _DESK_CSS[idx : _DESK_CSS.index("}", idx) + 1]
        size = re.search(r"font-size:(\d+(?:\.\d+)?)px", block)
        assert size is not None, f"no font-size declared for {selector}"
        assert float(size.group(1)) >= 11, f"{selector} is below the 11px label floor"

    for selector in [".badge {", ".tag-unproven {", ".tag-validated {"]:
        idx = _DESK_CSS.find(selector)
        assert idx != -1, f"missing selector: {selector}"
        block = _DESK_CSS[idx : _DESK_CSS.index("}", idx) + 1]
        size = re.search(r"font-size:(\d+(?:\.\d+)?)px", block)
        assert size is not None
        assert float(size.group(1)) >= 10, f"{selector} is below the 10px tag floor"


def test_v5_m26_section_h_class_replaces_repeated_inline_headings() -> None:
    assert ".section-h" in _DESK_CSS
    for name in ("intel.html", "blotter.html", "risk.html"):
        html = (_TEMPLATES / name).read_text(encoding="utf-8")
        assert 'class="section-h"' in html
        # the old fully-inline duplicated style block must be gone, not
        # just supplemented -- this was the actual "tokenize" ask.
        assert "text-transform:uppercase; color:var(--intel)" not in html


def test_v5_m26_press_feedback_declared_on_interactive_controls() -> None:
    assert ":active" in _DESK_CSS
    active_block = re.search(r"\.kill:active[^{]*\{[^}]*\}", _DESK_CSS)
    assert active_block is not None
    assert "scale(.97)" in active_block.group(0)


def test_v5_m26_kill_is_a_hold_to_confirm_gesture_not_a_single_click() -> None:
    desk_js = (_THEME / "desk.js").read_text(encoding="utf-8")
    assert "KILL_HOLD_MS" in desk_js
    assert "mousedown" in desk_js and "kill" in desk_js.lower()
    assert ".kill-fill" in _DESK_CSS
    assert "kill.holding" in _DESK_CSS.replace(" ", "")


def test_v5_m26_nav_spine_uses_vendored_svg_icons_not_text_glyphs() -> None:
    base_html = (_TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert "nav_icon(id)" in base_html
    vendor_dir = _THEME / "vendor" / "lucide"
    assert vendor_dir.is_dir()
    svgs = list(vendor_dir.glob("*.svg"))
    assert len(svgs) == 8
    for svg in svgs:
        assert "ISC" in svg.read_text(encoding="utf-8")


def test_candlestick_series_uses_fill_vs_outline_not_hue_alone() -> None:
    # docs/13 M19 a11y: bullish/bearish must survive colorblindness, so the
    # up candle is hollow/outline-only (near-transparent fill + a colored
    # border) while the down candle is solid-filled -- not hue alone.
    chart_js = (_THEME / "chart.js").read_text(encoding="utf-8")
    assert "borderVisible: true" in chart_js
    assert "rgba(38,166,154" in chart_js  # near-transparent bullish body
    assert "#EF5350" in chart_js  # solid bearish body
