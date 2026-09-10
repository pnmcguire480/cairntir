"""Protect the pre-verification frozen artifacts and coverage surface."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "dc2607f2146b931e4fa9243fc847583d6bf99ebb"
COUNCIL_MANIFESTS = {
    "plans/council-mcp.freeze.json": (
        "d6df7785d58facfa4b3ad444f437cab42811c7d86cfb0240917c3eb383bb84d1"
    ),
    "plans/council-registration.freeze.json": (
        "0f8c4e721a9b3155e2696defb02297514347ffc6d5319b1d63b3552501247ba1"
    ),
    "plans/council-store-identity.freeze.json": (
        "3ed7a021465e304ec4fa94245749f194496212cbb74e7d455eaa5d227eb45df1"
    ),
}


def check_council(root: Path) -> list[str]:
    """Enforce pinned council manifests and the exact artifact hashes they declare."""
    failures = []
    for name, expected in COUNCIL_MANIFESTS.items():
        path = root / name
        if not path.is_file():
            failures.append(f"frozen council manifest is missing: {name}")
            continue
        content = path.read_bytes().replace(b"\r\n", b"\n")
        if hashlib.sha256(content).hexdigest() != expected:
            failures.append(f"frozen council manifest differs from accepted hash: {name}")
            continue
        manifest = json.loads(content)
        fields = manifest.get("files", manifest.get("frozen_inputs", manifest.get("artifacts")))
        artifacts = (
            fields.items()
            if isinstance(fields, dict)
            else ((item["path"], item["sha256"]) for item in fields)
        )
        for artifact, digest in artifacts:
            path = root / artifact
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                failures.append(f"frozen council artifact differs from accepted hash: {artifact}")
    return failures


def check() -> list[str]:
    """Compare frozen artifacts with the accepted baseline, including prior amendments."""
    result = subprocess.run(  # noqa: S603 - pinned repository history, no shell
        [  # noqa: S607 - Git resolves through the user's configured PATH
            "git",
            "archive",
            "--format=zip",
            BASE,
            "tests",
            "plans",
            "docs/recipes",
            "pyproject.toml",
        ],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    failures = check_council(ROOT)
    with zipfile.ZipFile(io.BytesIO(result.stdout)) as archive:
        names = set(archive.namelist())
        manifests = {
            name
            for name in names
            if name.startswith("plans/") and "freeze" in name and name.endswith(".json")
        }
        protected = set(manifests)
        for name in manifests:
            manifest = json.loads(archive.read(name))
            fields = manifest.get("artifacts", manifest.get("files"))
            paths = fields.keys() if isinstance(fields, dict) else [item["path"] for item in fields]
            protected.update(
                path for path in paths if path.startswith(("tests/", "plans/", "docs/recipes/"))
            )
        for name in sorted(protected):
            path = ROOT / name
            if name not in names or not path.is_file() or path.read_bytes() != archive.read(name):
                failures.append(f"frozen artifact differs from accepted baseline: {name}")
        baseline = tomllib.loads(archive.read("pyproject.toml").decode())["tool"]["coverage"]
        baseline["report"]["precision"] = 6
        current = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
            "coverage"
        ]
        current["run"].pop("patch", None)
        if current != baseline:
            failures.append("coverage surface or exclusions differ from the accepted baseline")
    print(
        f"Checked {len(manifests)} baseline freeze manifests, {len(protected)} artifacts, "
        f"{len(COUNCIL_MANIFESTS)} council manifests and coverage scope."
    )
    return failures


if __name__ == "__main__":
    problems = check()
    for problem in problems:
        print(f"FAIL: {problem}")
    raise SystemExit(bool(problems))
