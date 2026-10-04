"""Freeze finite independent public protocol controls before execution."""

import hashlib
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    files = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted(root.iterdir()) if path.is_file() and path.name != "FROZEN.json"}
    frozen = {"files_sha256": files, "normal_cases": 33, "wrong_control_cases": 1,
              "scope": "Existing foreground managed JSONL routing, errors and close semantics; no feature expansion"}
    (root / "FROZEN.json").write_text(json.dumps(frozen, indent=2) + "\n")
    print(hashlib.sha256((root / "FROZEN.json").read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
