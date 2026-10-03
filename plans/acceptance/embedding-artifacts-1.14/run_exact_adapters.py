"""Run only original exact cases with guarded registry/assets fixture adapters."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

PACKET = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    source = args.source_root.resolve()
    manifest = json.loads((PACKET / "EXACT-ADAPTER-FREEZE.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files_sha256"].items():
        if hashlib.sha256((PACKET / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"frozen adapter changed: {name}")
    sys.path.insert(0, str(PACKET))
    sys.path.insert(0, str(source / "src"))
    sys.dont_write_bytecode = True
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["CAIRNTIR_DISABLE_AUTOREGISTER"] = "1"
    os.environ["CAIRNTIR_DISABLE_UPDATE_CHECK"] = "1"
    os.environ.pop("FASTEMBED_CACHE_PATH", None)
    import socket
    def forbidden(*args, **kwargs):
        raise AssertionError("network disabled in public exact-case fixture adapter")
    socket.create_connection = forbidden
    socket.socket.connect = forbidden
    socket.socket.connect_ex = forbidden
    import pytest
    return pytest.main([
        "-q", "--no-cov", "-p", "e22_exact_fixture_adapter",
        "--basetemp", str(PACKET / "runs" / ("exact-adapters-" + uuid.uuid4().hex)),
        "--e22-adapter-report", str(args.report.resolve()),
        str(source / "tests" / "verification" / "test_embedding_adapter_outcomes.py"),
        str(source / "tests" / "unit" / "test_store.py") + "::test_provider_identity_distinguishes_algorithm_model_and_dimension",
    ])


if __name__ == "__main__":
    raise SystemExit(main())
