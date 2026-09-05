"""Check locked registry packages against PyPI's public advisory feed."""

from __future__ import annotations

import json
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.request import urlopen

REPO_ROOT = Path(__file__).resolve().parent.parent


def audit_package(package: tuple[str, str]) -> list[str]:
    """Return active advisory ids or a withdrawn-release finding for a package."""
    name, version = package
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    with urlopen(url, timeout=20) as response:  # noqa: S310 - fixed HTTPS origin
        data: dict[str, Any] = json.load(response)
    findings = [
        f"{name}=={version}: {advisory['id']}"
        for advisory in data["vulnerabilities"]
        if not advisory.get("withdrawn")
    ]
    if data["info"]["yanked"]:
        findings.append(f"{name}=={version}: release is yanked")
    return findings


def main() -> int:
    """Fail closed on advisories, withdrawn releases, or an unavailable feed."""
    with (REPO_ROOT / "uv.lock").open("rb") as stream:
        lock = tomllib.load(stream)
    packages = sorted(
        {
            (package["name"], package["version"])
            for package in lock["package"]
            if "registry" in package.get("source", {})
        }
    )
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            findings = [
                finding for result in pool.map(audit_package, packages) for finding in result
            ]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR: dependency advisory check incomplete: {exc}", file=sys.stderr)
        return 1
    for finding in findings:
        print(f"ADVISORY: {finding}", file=sys.stderr)
    print(f"checked {len(packages)} locked registry packages; {len(findings)} finding(s)")
    return bool(findings)


if __name__ == "__main__":
    sys.exit(main())
