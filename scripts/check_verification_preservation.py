"""Protect the pre-verification frozen artifacts and coverage surface."""

from __future__ import annotations

import io
import json
import subprocess
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "dc2607f2146b931e4fa9243fc847583d6bf99ebb"


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
    failures = []
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
        current = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
            "coverage"
        ]
        current["run"].pop("patch", None)
        if current != baseline:
            failures.append("coverage surface or exclusions differ from the accepted baseline")
    print(
        f"Checked {len(manifests)} freeze manifests, {len(protected)} artifacts and coverage scope."
    )
    return failures


if __name__ == "__main__":
    problems = check()
    for problem in problems:
        print(f"FAIL: {problem}")
    raise SystemExit(bool(problems))
