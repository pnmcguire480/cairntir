"""Fetch the exact public Q07 wheel inputs before offline product tests."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
import zipfile
from pathlib import Path

_PACKAGE = Path(__file__).resolve().parents[1] / "tests/acceptance/bootstrap_real_unit"


def fetch(output: Path) -> None:
    """Verify and fetch six approved archives into a new directory."""
    manifest = json.loads((_PACKAGE / "wheel-inputs.json").read_bytes())
    lock = (_PACKAGE / "approved-pytest.lock").read_bytes()
    if hashlib.sha256(lock).hexdigest() != manifest["approved_lock_sha256"]:
        raise ValueError("Approved Q07 lock changed")
    rows = manifest["wheels"]
    if len(rows) != 6:
        raise ValueError("Expected exactly six approved wheel inputs")
    output.mkdir(parents=True)
    for name, row in rows.items():
        if Path(name).name != name or not row["url"].startswith("https://files.pythonhosted.org/"):
            raise ValueError("Unapproved wheel input path or host")
        with urllib.request.urlopen(row["url"], timeout=60) as response:  # noqa: S310
            data = response.read(row["bytes"] + 1)
        if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise ValueError(f"Downloaded wheel differs from approved input: {name}")
        path = output / name
        with path.open("xb") as stream:
            stream.write(data)
        with zipfile.ZipFile(path) as wheel:
            if wheel.testzip() is not None:
                raise ValueError(f"Invalid wheel CRC: {name}")


def main() -> None:
    """Fetch the fixed Q07 inputs without installing or executing them."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    fetch(parser.parse_args().output)


if __name__ == "__main__":
    main()
