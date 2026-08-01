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

Exit code 1 if any violations are found. Used as a CI check and a release gate.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tomllib
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

    for version in changelog_versions():
        if version == in_flight:
            continue
        if version in KNOWN_UNRELEASED:
            continue
        if f"v{version}" not in tags:
            violations.append(version)

    for version in KNOWN_UNRELEASED:
        print(f"note: {version} is a known-unreleased version ({KNOWN_UNRELEASED[version]})")

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

    print(f"ok: every released changelog version is tagged (in-flight: {in_flight})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
