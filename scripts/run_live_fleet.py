#!/usr/bin/env python3
"""Deprecated: this used to be a standalone script for the live multi-model
paper trading extension. It has been ported into the tagged CLI as
`lqe live` (docs/12 M14) -- same flags, same behavior, now with test
coverage and `--adapter csv` for offline runs. This file is kept as a thin
compatibility wrapper only.

    python scripts/run_live_fleet.py --llm --llm-model llama3.2:3b
    # is now equivalent to:
    lqe live --llm --llm-model llama3.2:3b
"""

from __future__ import annotations

import sys

from lqe.cli import main as cli_main


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    return cli_main(["live", *args])


if __name__ == "__main__":
    raise SystemExit(main())
