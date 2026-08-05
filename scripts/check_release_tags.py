"""Ban changelog versions that were never tagged.

Cairntir's release workflow fires only on a pushed ``v*.*.*`` tag. Writing a
``## [x.y.z]`` header into CHANGELOG.md does not publish anything. Between
2026-04-17 and 2026-08-01 that gap silently swallowed two releases: 1.0.1 and
1.1.3 were both committed and changelogged, neither was ever tagged, and so
neither reached PyPI. The 1.1.3 cold-start fix (12min to 1.4s) sat unreleased
for three months while every ``pip install cairntir`` kept resolving to 1.1.2.

This check closes that gap. Every released version in CHANGELOG.md must have a
matching git tag, with two deliberate exemptions:

* The version currently in ``pyproject.toml`` is exempt. During release prep the
  changelog header is written before the tag exists; that is the normal order.
* Versions in :data:`KNOWN_UNRELEASED` are exempt because they are historical
  fact. They are recorded here rather than hidden, and retagging them now would
  re-trigger the publish workflow against a stale commit.

A tag, in turn, is a claim, not a fact. The second half of this check verifies
every released tag actually published to PyPI, because that is the exact class
of miss the tag half cannot see: ``v1.1.1`` was tagged and released on GitHub
and never reached PyPI, unnoticed. Versions in :data:`KNOWN_UNPUBLISHED` are
historical fact, recorded rather than hidden. This half requires network
access to pypi.org and fails closed when it cannot verify — a gate that cannot
check is not a gate.

Exit code 1 if any violations are found. Used as a CI check and a release gate.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
PYPROJECT = REPO_ROOT / "pyproject.toml"

CHANGELOG_VERSION = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.MULTILINE)

# Versions changelogged before this check existed that were never tagged or
# published. Documented, not swept away. Do not add to this set to silence a
# new failure -- tag the release instead.
KNOWN_UNRELEASED = {
    "1.0.1": "changelogged 2026-04-17, never tagged, never published to PyPI",
    "1.1.3": "changelogged 2026-05-03, never tagged; the cold-start fix it "
    "describes shipped inside 1.2.0 on 2026-08-01",
}

# Versions that were tagged but never published to PyPI. Documented, not swept
# away. Do not add to this set to silence a new failure -- publish the release
# instead. Retagging would re-trigger the publish workflow against a stale
# commit, so these are recorded as historical fact.
KNOWN_UNPUBLISHED = {
    "0.1.0": "tagged 2026-04-08 as the bootstrap release with a GitHub "
    "Release, never published to PyPI",
    "1.1.1": "tagged 2026-04-25, released on GitHub, never reached PyPI -- "
    "the miss that proved tags alone are not enough",
}

PYPI_PACKAGE_URL = "https://pypi.org/pypi/cairntir/json"
"""The JSON endpoint listing every published release of this package."""


def changelog_versions() -> list[str]:
    """Return every released version header in CHANGELOG.md, newest first."""
    return CHANGELOG_VERSION.findall(CHANGELOG.read_text(encoding="utf-8"))


def current_version() -> str:
    """Return the version declared in pyproject.toml."""
    with PYPROJECT.open("rb") as handle:
        project = tomllib.load(handle)
    version = project["project"]["version"]
    if not isinstance(version, str):
        raise TypeError(f"pyproject project.version must be a string, got {type(version)}")
    return version


def existing_tags() -> set[str]:
    """Return every ``vx.y.z`` tag known to the local repository."""
    git = shutil.which("git")
    if git is None:
        raise OSError("could not find `git` on PATH")
    result = subprocess.run(  # noqa: S603 - executable resolved by shutil.which
        [git, "tag", "--list", "v*.*.*"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def fetch_pypi_json(url: str) -> str:
    """Fetch the package JSON from PyPI. Raises on any network failure."""
    request = urllib.request.Request(url, headers={"User-Agent": "cairntir-release-gate"})  # noqa: S310
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return str(response.read().decode("utf-8"))


def pypi_published_versions(fetch: Callable[[str], str] = fetch_pypi_json) -> set[str]:
    """Return the versions PyPI actually serves files for.

    A version key with an empty file list was yanked into the index without
    artefacts and does not count as published.
    """
    payload = json.loads(fetch(PYPI_PACKAGE_URL))
    releases = payload.get("releases", {})
    if not isinstance(releases, dict):
        raise TypeError(f"PyPI returned an unexpected releases shape: {type(releases)}")
    return {version for version, files in releases.items() if files}


def unpublished(versions: list[str], published: set[str]) -> list[str]:
    """Return the tagged versions missing from PyPI, in the order given."""
    return [version for version in versions if version not in published]


def main() -> int:
    """Entry point. Returns 1 if a released changelog version has no tag."""
    try:
        tags = existing_tags()
    except (subprocess.CalledProcessError, OSError) as exc:
        print(f"ERROR: could not list git tags: {exc}", file=sys.stderr)
        return 1

    if not tags:
        print(
            "ERROR: no v*.*.* tags visible. Fetch tags before running this check "
            "(actions/checkout needs fetch-depth: 0).",
            file=sys.stderr,
        )
        return 1

    in_flight = current_version()
    violations: list[str] = []
    released: list[str] = []

    for version in changelog_versions():
        if version == in_flight:
            continue
        if version in KNOWN_UNRELEASED:
            continue
        if f"v{version}" not in tags:
            violations.append(version)
        else:
            released.append(version)

    for version in KNOWN_UNRELEASED:
        print(f"note: {version} is a known-unreleased version ({KNOWN_UNRELEASED[version]})")
    for version in KNOWN_UNPUBLISHED:
        print(f"note: {version} is a known-unpublished version ({KNOWN_UNPUBLISHED[version]})")

    if violations:
        print(file=sys.stderr)
        for version in violations:
            print(
                f"CHANGELOG.md declares {version} but tag v{version} does not exist.",
                file=sys.stderr,
            )
        print(
            f"\n{len(violations)} changelogged version(s) were never tagged.\n"
            "Cairntir policy: a changelog entry is not a release. The release "
            "workflow fires only on a pushed v*.*.* tag.",
            file=sys.stderr,
        )
        return 1

    # A tag is a claim, not a fact: verify it published. Versions in
    # KNOWN_UNPUBLISHED are historical fact and stay exempt.
    to_verify = [v for v in released if v not in KNOWN_UNPUBLISHED]
    try:
        published = pypi_published_versions()
    except (urllib.error.URLError, TimeoutError, TypeError, json.JSONDecodeError, OSError) as exc:
        print(
            f"ERROR: could not verify PyPI presence: {exc}\n"
            "Failing closed: a gate that cannot check is not a gate. If you "
            "believe this is a transient network failure, re-run.",
            file=sys.stderr,
        )
        return 1

    missing = unpublished(to_verify, published)
    if missing:
        print(file=sys.stderr)
        for version in missing:
            print(
                f"tag v{version} exists but PyPI serves no files for {version}.",
                file=sys.stderr,
            )
        print(
            f"\n{len(missing)} tagged version(s) never published to PyPI.\n"
            "Cairntir policy: a tag is not a release until `pip install "
            "cairntir` can resolve it.",
            file=sys.stderr,
        )
        return 1

    print(f"ok: every released changelog version is tagged and published (in-flight: {in_flight})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
