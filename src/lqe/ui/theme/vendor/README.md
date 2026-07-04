# ui/theme/vendor — TradingView Lightweight Charts + Lucide icons

`lightweight-charts.standalone.production.js` is the official standalone
UMD build of **TradingView Lightweight Charts v5.2.0**
(https://github.com/tradingview/lightweight-charts), fetched once from
`https://unpkg.com/lightweight-charts@5.2.0/dist/lightweight-charts.standalone.production.js`
and committed here as a static asset — the app is `127.0.0.1`-only with no
CDN / no outbound network at runtime (docs/11 §11.11), so it must be
self-hosted, same rule as the fonts in `theme/fonts/`.

- **License:** Apache License 2.0 (`ALLOW` under the tiered license gate,
  docs/11 §11.11 / CLAUDE.md non-negotiable #8) — full text at
  https://www.apache.org/licenses/LICENSE-2.0, copyright notice preserved
  verbatim in the file's leading comment block.
- **SHA-256:** `c0992580867c4912cc9385b3c2728315bcc1a76c7f1087dca908430fccdf31d7`
- **Why not `scripts/license_gate.py`:** that gate scans the *Python*
  runtime dependency closure via `pip-licenses`; this is a vendored static
  JS asset, not a pip package, so it's out of that scan's scope by
  construction — recorded here by hand instead, same as the note in
  `viz3d/vendor/README.md` for three.js/3d-force-graph.
- **Used by:** `theme/desk.js`'s chart module (docs/13 M19 — Floor's hero
  price/equity chart), loaded via `<script src="/theme/vendor/
  lightweight-charts.standalone.production.js">` before `desk.js`. Exposes
  the global `window.LightweightCharts`.

To upgrade: replace this file with a newer `lightweight-charts.standalone
.production.js`, update the version/hash above, and smoke-test the Floor
chart still renders.

## `vendor/lucide/` — nav spine icons (V5 M26)

Eight **Lucide** (`lucide-static` v1.23.0, https://lucide.dev) icon SVGs,
fetched once from `https://unpkg.com/lucide-static@1.23.0/icons/<name>.svg`
and committed as static assets, same no-CDN/no-outbound-network rule as the
chart above. They retire the ad-hoc Unicode glyphs (▦, ▤, ◇, …) the spine
nav previously used.

- **License:** ISC (`ALLOW` under the tiered license gate, docs/11 §11.11 /
  CLAUDE.md non-negotiable #8) — the `@license lucide-static ... - ISC`
  comment is preserved verbatim as the first line of each file.
- **Files → nav item:** `layout-grid.svg` → Floor, `list.svg` → Catalog,
  `flask-conical.svg` → Research, `sparkles.svg` → Intel, `network.svg` →
  Engine, `shield-alert.svg` → Risk, `calendar-days.svg` → Daily,
  `receipt.svg` → Blotter.
- **Why not `scripts/license_gate.py`:** same reason as the chart above —
  that gate scans the *Python* runtime dependency closure via
  `pip-licenses`; these are vendored static SVGs, not a pip package.
- **Used by:** these files are the source-of-truth reference copies; the
  actual spine rendering inlines each icon's inner shape markup directly
  in `ui/app.py`'s `_NAV_ICONS` dict (`nav_icon()` Jinja global) so a page
  load doesn't cost 8 extra static-file requests. If you change an icon,
  update both this file and the matching entry in `_NAV_ICONS`.

To add or swap an icon: fetch the new `<name>.svg` from the same source,
save it here, and copy its inner `<path>`/`<rect>`/... markup (everything
between the `<svg ...>` and `</svg>` tags) into `_NAV_ICONS`.
