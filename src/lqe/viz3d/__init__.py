"""The 3D neural-web (docs/05 §5.5, docs/10 M10).

The scene is realized as:
- the read-only `GraphPayload` built by `storage.state_reader.StateReader.graph()`
  (the protocol home per docs/11 §11.2/§11.9) and served at `/api/graph`;
- `neural_web.js` — a dependency-free `<canvas>` force-graph rendering that
  payload (the `ui` app mounts this package at `/viz3d`);
- the `/engine` view (`ui/templates/engine.html`).

`vendor/README.md` documents the three.js / 3d-force-graph slot and why this
build ships the canvas renderer instead. This package holds only static
frontend assets — no importable Python, no `Order` construction, read-only.
"""

from __future__ import annotations
