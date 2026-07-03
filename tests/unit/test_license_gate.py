"""docs/11 §11.11/§11.12: the license gate must classify every tier
correctly and, above all, fail closed on anything it doesn't recognize —
that silent pass-through was the real defect being fixed here.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from license_gate import classify_license, runtime_closure  # noqa: E402


def test_mpl_2_0_is_allowed_unmodified() -> None:
    # this is exactly certifi's real pip-licenses string
    assert classify_license("Mozilla Public License 2.0 (MPL 2.0)") == "ALLOW"
    assert classify_license("MPL-2.0") == "ALLOW"


def test_common_permissive_licenses_are_allowed() -> None:
    for text in [
        "MIT", "BSD-3-Clause", "Apache-2.0", "ISC License", "PSF-2.0",
        "Python Software Foundation License", "NCSA", "0BSD", "Unlicense",
        "Apache-2.0 AND MIT", "MIT OR Apache-2.0",
    ]:
        assert classify_license(text) == "ALLOW", text


def test_lgpl_is_allowed_with_note_not_denied() -> None:
    assert classify_license("GNU Lesser General Public License v3 (LGPLv3)") == "ALLOW_WITH_NOTE"
    assert classify_license("LGPL-2.1") == "ALLOW_WITH_NOTE"


def test_gpl_family_is_denied() -> None:
    for text in [
        "GNU General Public License v3 (GPLv3)",
        "GPL-3.0",
        "GNU Affero General Public License v3",
        "AGPL-3.0",
        "Server Side Public License (SSPL)",
        "Business Source License",
        "Commons Clause",
    ]:
        assert classify_license(text) == "DENY", text


def test_unknown_or_missing_license_fails_closed() -> None:
    assert classify_license("UNKNOWN") == "REVIEW"
    assert classify_license("") == "REVIEW"
    assert classify_license("Some Proprietary Thing Nobody Has Heard Of") == "REVIEW"


def test_a_dual_license_string_with_a_deny_marker_fails_closed() -> None:
    # ambiguous dual-license strings that include a GPL-family marker are
    # never quietly allowed just because a permissive marker also appears
    assert classify_license("BSD License; GNU General Public License (GPL)") == "DENY"


def test_real_environment_closure_includes_certifi_via_ccxt() -> None:
    closure, missing_roots = runtime_closure()
    assert missing_roots == set()
    assert "certifi" in closure  # transitive via ccxt/httpx/requests
    assert "ccxt" in closure  # a declared root
    assert "fastapi" in closure  # the promoted 'ui' extra's root
