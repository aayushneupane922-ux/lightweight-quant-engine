# Fonts (Inter + JetBrains Mono)

The Obsidian Desk design system specifies Inter (UI) and JetBrains Mono
(numerics). Per docs/11 §11.11 the app is **localhost-only with no outbound
network**, so fonts are NOT loaded from a CDN. Drop the self-hosted `.woff2`
files here to ship them:

- `Inter.woff2` — Inter, SIL Open Font License 1.1 (permissive)
- `JetBrainsMono.woff2` — JetBrains Mono, SIL Open Font License 1.1

`theme/desk.css` references them via `@font-face` with `local()` first and a
system fallback stack (`system-ui` / `ui-monospace`), so the desk renders
correctly whether or not the binaries are present — absent them it degrades
gracefully rather than breaking or reaching out to the network.

The OFL is on the permissive allowlist; if these binaries are bundled into a
distributed build, include their OFL notice in `THIRD_PARTY_NOTICES.md`.
