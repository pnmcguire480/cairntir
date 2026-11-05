import subprocess
import sys
from pathlib import Path


def test_persistent_counter(tmp_path):
    module = Path(__file__).parents[1] / "src/paladin_fixture/counter.py"
    database = tmp_path / "counter.db"
    first = subprocess.run(
        [sys.executable, "-I", "-B", str(module), "write", str(database), "37"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert first.returncode == 0, first.stderr
    second = subprocess.run(
        [sys.executable, "-I", "-B", str(module), "read", str(database)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert second.returncode == 0, second.stderr
    assert second.stdout.strip() == "37"
