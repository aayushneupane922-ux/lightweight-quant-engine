# viz3d vendor slot (three.js / 3d-force-graph)

docs/05 §5.5 names **three.js + `3d-force-graph`** (both MIT) for the neural-web
scene. This build ships a **dependency-free `<canvas>` force-graph** instead
(`viz3d/neural_web.js`) — a deliberate, flagged deviation, in the same spirit
as the native-indicators (over pandas-ta), native-drift (over River), and
FastAPI (over NiceGUI) calls:

- The app is **localhost-only with no CDN / no outbound network at runtime**
  (docs/11 §11.11), so the library must be self-hosted regardless.
- A minified three.js + 3d-force-graph bundle (~2 MB) is not vendorable in
  this offline build environment and would be a heavy, hard-to-audit blob.
- The canvas renderer delivers the M10 **acceptance criteria** already:
  animates real model / attention / promotion state from the audit log,
  replays deterministically via the timeline scrubber, shows sandbox vs
  tracked as visually distinct regions, carries the honesty overlays, is
  `127.0.0.1`-only, and respects `prefers-reduced-motion`.

To get the full WebGL experience, drop `three.min.js` and
`3d-force-graph.min.js` here and point `neural_web.js` at them (both MIT —
add their notices to `THIRD_PARTY_NOTICES.md` if you bundle them into a
distributed build). The `/api/graph` `GraphPayload` contract is unchanged, so
only the renderer swaps.
