"""Fail the build if a runtime dependency carries a disallowed license
(docs/11 §11.11, GUARDRAILS.md).

Tiered, transitive, fail-closed:
  ALLOW           MIT, BSD-2/3, Apache-2.0, ISC, PSF, NCSA, 0BSD, Unlicense,
                  MPL-2.0 (weak file-level copyleft — safe as an
                  *unmodified* dependency, e.g. `certifi`).
  ALLOW_WITH_NOTE LGPL (unmodified/dynamically imported; flag if ever
                  frozen into a single binary — not applicable to a local
                  Python app).
  DENY            GPL, AGPL, SSPL, BSL/Business Source, Commons Clause.
  REVIEW          unknown/missing/unrecognized license string. Fails
                  closed — an unrecognized license must block the build,
                  never slip through silently (that silent-pass was the
                  real defect in the previous version of this gate).

Scope: the **full runtime dependency closure** (transitive), computed from
`[project.dependencies]` plus whichever optional extras have actually been
promoted into the running product (currently just `ui`, as of M7 — see the
comment above it in pyproject.toml). `dev`/`data`/`models`/`search` are
research/tooling-only and stay out of scope until their own milestone
promotes them; this venv may have those installed too (for local dev), but
walking the dependency graph from the promoted roots naturally excludes
anything only reachable through them.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from importlib import metadata
from pathlib import Path
from typing import Literal

Tier = Literal["ALLOW", "ALLOW_WITH_NOTE", "DENY", "REVIEW"]

# Extras that are part of the *running* product as of this milestone.
# data/models/search remain research-only until their own milestone
# promotes them (see the per-extra comments in pyproject.toml).
PROMOTED_EXTRAS = ("ui",)

# Checked in this exact order — LGPL must be recognized before the bare
# "GPL" check below would otherwise misclassify it as a hard DENY.
_LGPL_RE = re.compile(r"\bL\s*GPL\b|Lesser General Public", re.IGNORECASE)
_DENY_RE = re.compile(
    r"\bAGPL\b|Affero|\bGPL\b|General Public License|\bSSPL\b|Server Side Public"
    r"|\bBSL\b|Business Source|Commons Clause",
    re.IGNORECASE,
)
_ALLOW_RE = re.compile(
    r"\bMIT\b|\bBSD\b|\bApache\b|\bISC\b|\bPSF\b|Python Software Foundation"
    r"|\bNCSA\b|\b0BSD\b|Unlicense|\bMPL-?2\.0\b|Mozilla Public License",
    re.IGNORECASE,
)


def classify_license(license_str: str) -> Tier:
    """Pure classification, deliberately separate from any environment/
    subprocess plumbing so it's directly unit-testable."""
    text = (license_str or "").strip()
    if not text or text.upper() == "UNKNOWN":
        return "REVIEW"
    if _LGPL_RE.search(text):
        return "ALLOW_WITH_NOTE"
    if _DENY_RE.search(text):
        return "DENY"
    if _ALLOW_RE.search(text):
        return "ALLOW"
    return "REVIEW"


def _normalize(name: str) -> str:
    return name.lower().replace("_", "-").strip()


def _root_package_names() -> set[str]:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    project = pyproject["project"]
    names = {_normalize(_strip_specifier(d)) for d in project["dependencies"]}
    optional = project.get("optional-dependencies", {})
    for extra in PROMOTED_EXTRAS:
        for dep in optional.get(extra, []):
            names.add(_normalize(_strip_specifier(dep)))
    return names


def _strip_specifier(requirement: str) -> str:
    return re.split(r"[\[<>=!~; ]", requirement, maxsplit=1)[0]


def _requires_names(dist: metadata.Distribution) -> set[str]:
    """Direct dependency names of an installed distribution, skipping any
    requirement gated behind the distribution's *own* optional extras
    (`; extra == "..."`) — those aren't pulled in by a plain install."""
    names = set()
    for req in dist.requires or []:
        if "extra ==" in req or "extra==" in req:
            continue
        names.add(_normalize(_strip_specifier(req)))
    return names


def runtime_closure() -> tuple[set[str], set[str]]:
    """BFS over installed distributions' `requires`, starting from the
    declared runtime roots, so only packages actually reachable from the
    shipped product are in scope — not everything in this dev venv.

    Returns `(closure, missing_roots)`. A root that isn't installed is a
    real error (a declared runtime dependency is missing). A *transitive*
    name that isn't installed is not an error on its own — `.requires`
    strings aren't marker-evaluated here (e.g. `; python_version < "3.11"`
    deps correctly aren't installed on 3.12), so it's simply not part of
    this environment's real closure and is dropped rather than walked.
    """
    by_name = {_normalize(dist.name): dist for dist in metadata.distributions() if dist.name}
    roots = _root_package_names()

    closure: set[str] = set()
    frontier = set(roots)
    while frontier:
        name = frontier.pop()
        if name in closure:
            continue
        dist = by_name.get(name)
        if dist is None:
            continue  # not installed here (marker-excluded, or a missing root — checked below)
        closure.add(name)
        frontier |= _requires_names(dist) - closure

    missing_roots = roots - closure
    return closure, missing_roots


def _pip_licenses_json() -> list[dict[str, str]]:
    result = subprocess.run(
        [
            sys.executable, "-m", "piplicenses",
            "--format=json", "--from=mixed", "--with-urls", "--with-system",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    packages: list[dict[str, str]] = json.loads(result.stdout)
    return packages


def main() -> int:
    closure, missing_roots = runtime_closure()
    if missing_roots:
        print(f"license_gate: FAIL — declared runtime deps not installed: {sorted(missing_roots)}")
        return 1

    packages = _pip_licenses_json()
    by_name = {_normalize(pkg["Name"]): pkg for pkg in packages}

    deny: list[tuple[str, str]] = []
    review: list[tuple[str, str]] = []
    note: list[tuple[str, str]] = []
    checked: list[str] = []
    missing: list[str] = []

    for name in sorted(closure):
        pkg = by_name.get(name)
        if pkg is None:
            missing.append(name)
            continue
        checked.append(name)
        tier = classify_license(pkg["License"])
        if tier == "DENY":
            deny.append((pkg["Name"], pkg["License"]))
        elif tier == "REVIEW":
            review.append((pkg["Name"], pkg["License"]))
        elif tier == "ALLOW_WITH_NOTE":
            note.append((pkg["Name"], pkg["License"]))

    if missing:
        print(f"license_gate: FAIL — in closure but not found by pip-licenses: {sorted(missing)}")
        return 1

    if deny or review:
        print("license_gate: FAIL")
        for pkg_name, license_str in deny:
            print(f"  DENY   {pkg_name}: {license_str}")
        for pkg_name, license_str in review:
            print(f"  REVIEW {pkg_name}: {license_str} (unrecognized — fails closed)")
        return 1

    for pkg_name, license_str in note:
        print(
            f"license_gate: note — {pkg_name} is LGPL ({license_str}), "
            "unmodified/dynamic-import only"
        )

    print(f"license_gate: PASS — {len(checked)} runtime dependencies (full transitive closure) OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
