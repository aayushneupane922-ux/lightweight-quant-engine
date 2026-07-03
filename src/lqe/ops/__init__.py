"""Operational tooling for the local install (docs/10 M12): a `doctor`
health check and `backup` snapshots. Pure-stdlib + core imports only, so
`lqe doctor`/`lqe backup` run without the optional `ui`/`search`/`models`
extras present.
"""

from __future__ import annotations
