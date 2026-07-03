"""Fail the build if a runtime dependency carries a disallowed license.

Runtime deps must be MIT/BSD/Apache/NCSA (or another clearly permissive
license). GPL-family and Commons Clause are never allowed in the runtime
(GUARDRAILS.md). Only `[project.dependencies]` (the base install) is
checked — dev/data/models/search/ui extras are not yet part of the
running product until their owning milestone promotes them.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

# Order matters: GPL-family/Commons Clause are checked first and always
# disallowed, even if a permissive marker also appears in a dual-license
# string (fail closed on ambiguity).
DISALLOWED_MARKERS = ("AGPL", "LGPL", "GPL", "Commons Clause", "SSPL")

ALLOWED_MARKERS = (
    "MIT",
    "BSD",
    "Apache",
    "NCSA",
    "ISC",
    "Unlicense",
    "Python Software Foundation",
)


def runtime_package_names() -> set[str]:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    deps = pyproject["project"]["dependencies"]
    names = set()
    for dep in deps:
        name = dep.split(">=")[0].split("==")[0].split("[")[0].strip()
        names.add(name.lower().replace("_", "-"))
    return names


def main() -> int:
    runtime_names = runtime_package_names()
    if not runtime_names:
        print("license_gate: no runtime dependencies declared yet — nothing to check.")
        return 0

    result = subprocess.run(
        [sys.executable, "-m", "piplicenses", "--format=json"],
        capture_output=True,
        text=True,
        check=True,
    )
    packages = json.loads(result.stdout)

    violations = []
    checked = []
    for pkg in packages:
        name = pkg["Name"].lower().replace("_", "-")
        if name not in runtime_names:
            continue
        license_str = pkg["License"]
        checked.append(name)
        is_disallowed = any(marker in license_str for marker in DISALLOWED_MARKERS)
        is_known_allowed = any(marker in license_str for marker in ALLOWED_MARKERS)
        if is_disallowed or not is_known_allowed:
            violations.append((pkg["Name"], license_str))

    missing = runtime_names - set(checked)
    if missing:
        print(f"license_gate: FAIL — runtime deps not found in environment: {sorted(missing)}")
        return 1

    if violations:
        print("license_gate: FAIL — disallowed or unrecognized runtime licenses:")
        for name, license_str in violations:
            print(f"  {name}: {license_str}")
        return 1

    print(f"license_gate: PASS — {len(checked)} runtime dependencies are permissively licensed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
