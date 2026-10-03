"""Seal the append-only public diagnostic amendment and its raw evidence."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PUBLIC = Path(
    r"C:\Users\pnmcg\AppData\Local\Temp\cairntir-questions-work-20261003"
) / "plans/acceptance/questions-installed-ci-1.16-v2"
bindings = {}
for source in HERE.rglob("*"):
    if not source.is_file() or any(
        part in ("__pycache__", ".pytest_cache", ".ruff_cache") for part in source.parts
    ):
        continue
    if source.name == "SEAL.json":
        continue
    relative = source.relative_to(HERE)
    content = source.read_bytes()
    bindings[relative.as_posix()] = hashlib.sha256(content).hexdigest()
    destination = PUBLIC / relative
    if destination.exists():
        if destination.read_bytes() != content:
            raise RuntimeError(f"existing public artifact differs: {relative}")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
seal = {
    "sealed_at_utc": datetime.now(UTC).isoformat(),
    "files_sha256": bindings,
    "status": "READY_FOR_ONE_DIAGNOSTIC_HOSTED_ATTEMPT",
    "original_failure_cause": "UNRESOLVED",
    "original_v1_packet": "unchanged",
}
target = HERE / "SEAL.json"
if target.exists() or (PUBLIC / target.name).exists():
    raise RuntimeError("append-only seal already exists")
target.write_text(json.dumps(seal, indent=2), encoding="utf-8")
(PUBLIC / target.name).write_bytes(target.read_bytes())
print(json.dumps({"artifacts": len(bindings), "seal_sha256": hashlib.sha256(target.read_bytes()).hexdigest()}))
