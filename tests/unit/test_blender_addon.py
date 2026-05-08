"""Unit tests for the Cairntir Blender add-on's spool writer.

The add-on's ``__init__.py`` imports ``bpy`` (Blender's Python API),
which is not present in pytest. We sidestep that by loading
``spool_writer.py`` directly via :mod:`importlib.util` — the writer
itself is stdlib-only and has no Blender dependency.

The round-trip test is the load-bearing one: a file written by the
Blender writer must parse cleanly through Cairntir's daemon and
produce a Drawer with the right wing/room/layer/metadata. Without
that, the "horizon thesis" — that Cairntir doesn't care what is being
remembered — would be a marketing claim instead of a fact.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from cairntir.daemon.spool import parse_capture, pending_files


def _load_spool_writer() -> ModuleType:
    """Load addons/cairntir_blender/spool_writer.py without importing the package."""
    repo_root = Path(__file__).resolve().parents[2]
    target = repo_root / "addons" / "cairntir_blender" / "spool_writer.py"
    assert target.is_file(), f"spool_writer.py missing at {target}"
    spec = importlib.util.spec_from_file_location("blender_spool_writer", target)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def writer() -> ModuleType:
    return _load_spool_writer()


# --------- happy paths -------------------------------------------------


def test_write_capture_drops_a_valid_spool_file(
    writer: ModuleType, tmp_path: Path
) -> None:
    """A normal write produces a parseable JSON spool file."""
    final = writer.write_capture(
        wing="blender-print",
        room="pla",
        content="first iteration captured from Blender",
        home=tmp_path,
    )
    assert final.exists()
    assert final.suffix == ".json"
    payload = json.loads(final.read_text(encoding="utf-8"))
    assert payload["wing"] == "blender-print"
    assert payload["room"] == "pla"
    assert payload["content"] == "first iteration captured from Blender"
    assert payload["layer"] == "on_demand"


def test_write_capture_attaches_metadata(writer: ModuleType, tmp_path: Path) -> None:
    final = writer.write_capture(
        wing="w",
        room="r1",
        content="x",
        metadata={"source": "blender", "kind": "decision", "frame": 42},
        home=tmp_path,
    )
    payload = json.loads(final.read_text(encoding="utf-8"))
    assert payload["metadata"]["source"] == "blender"
    assert payload["metadata"]["frame"] == 42


def test_writer_creates_spool_subdir_under_home(
    writer: ModuleType, tmp_path: Path
) -> None:
    """``home`` is the cairntir home; the writer creates ``home/spool``."""
    final = writer.write_capture(
        wing="w", room="r1", content="x", home=tmp_path
    )
    spool = tmp_path / "spool"
    assert spool.is_dir()
    assert final.parent == spool
    assert (spool / "failed").is_dir()


def test_cairntir_home_uses_env_var(
    writer: ModuleType, tmp_path: Path, monkeypatch: object
) -> None:
    """The CAIRNTIR_HOME env var wins over the default."""
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path / "custom"))  # type: ignore[attr-defined]
    resolved = writer.cairntir_home()
    assert resolved == tmp_path / "custom"


def test_cairntir_home_falls_back_to_user_home(
    writer: ModuleType, monkeypatch: object
) -> None:
    monkeypatch.delenv("CAIRNTIR_HOME", raising=False)  # type: ignore[attr-defined]
    resolved = writer.cairntir_home()
    assert resolved == Path.home() / ".cairntir"


# --------- validation --------------------------------------------------


def test_empty_wing_rejected(writer: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="wing"):
        writer.write_capture(wing="", room="r1", content="x", home=tmp_path)


def test_empty_room_rejected(writer: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="room"):
        writer.write_capture(wing="w", room="", content="x", home=tmp_path)


def test_whitespace_content_rejected(writer: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="content"):
        writer.write_capture(wing="w", room="r1", content="   ", home=tmp_path)


def test_unknown_layer_rejected(writer: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="layer"):
        writer.write_capture(
            wing="w", room="r1", content="x", layer="cosmic", home=tmp_path
        )


# --------- print outcome helper ----------------------------------------


def test_write_print_outcome_encodes_parameters(
    writer: ModuleType, tmp_path: Path
) -> None:
    final = writer.write_print_outcome(
        wing="blender-print",
        material="PETG",
        parameters={
            "nozzle_temp_c": 240,
            "bed_temp_c": 80,
            "infill_pct": 30,
            "layer_height_mm": 0.2,
        },
        outcome="layer adhesion strong; cooling sufficient",
        success=True,
        notes="first PETG run after switching from PLA",
        home=tmp_path,
    )
    payload = json.loads(final.read_text(encoding="utf-8"))
    assert payload["wing"] == "blender-print"
    # Material was passed as "PETG"; identifier convention lowercases.
    assert payload["room"] == "petg"
    assert "nozzle_temp_c: 240" in payload["content"]
    assert "Outcome" in payload["content"]
    md = payload["metadata"]
    assert md["source"] == "blender"
    assert md["kind"] == "print_outcome"
    # Metadata preserves the original material casing for display.
    assert md["material"] == "PETG"
    assert md["success"] is True
    assert md["parameters"]["nozzle_temp_c"] == 240


def test_write_capture_lowercases_wing_and_room(
    writer: ModuleType, tmp_path: Path
) -> None:
    """Cairntir's taxonomy regex requires lowercase; the writer normalizes."""
    final = writer.write_capture(
        wing="Blender-Print",
        room="PLA",
        content="lowercased",
        home=tmp_path,
    )
    payload = json.loads(final.read_text(encoding="utf-8"))
    assert payload["wing"] == "blender-print"
    assert payload["room"] == "pla"


# --------- round-trip with the actual cairntir daemon ------------------


def test_writer_output_round_trips_through_cairntir_daemon(
    writer: ModuleType, tmp_path: Path
) -> None:
    """The load-bearing test: a file written by the Blender writer
    parses cleanly through ``cairntir.daemon.spool.parse_capture`` and
    appears in ``pending_files()``. This is what makes Cairntir's
    horizon thesis — "doesn't care what is being remembered" — true
    in practice rather than aspiration."""
    writer.write_capture(
        wing="blender-print",
        room="pla",
        content="round-trip iteration",
        metadata={"source": "blender", "kind": "decision"},
        home=tmp_path,
    )
    # The Blender writer drops files into the same spool dir layout
    # the daemon expects — confirm the daemon discovers them.
    spool = tmp_path / "spool"
    files = pending_files(spool)
    assert len(files) == 1
    drawer = parse_capture(files[0])
    assert drawer.wing == "blender-print"
    assert drawer.room == "pla"
    assert drawer.content == "round-trip iteration"
    assert drawer.layer.value == "on_demand"
    assert drawer.metadata["source"] == "blender"


def test_print_outcome_round_trips_through_daemon(
    writer: ModuleType, tmp_path: Path
) -> None:
    writer.write_print_outcome(
        wing="blender-print",
        material="PLA",
        parameters={"nozzle_temp_c": 200, "bed_temp_c": 60},
        outcome="warping at corners",
        success=False,
        home=tmp_path,
    )
    spool = tmp_path / "spool"
    drawer = parse_capture(pending_files(spool)[0])
    assert drawer.wing == "blender-print"
    # Material lowercased to satisfy taxonomy regex.
    assert drawer.room == "pla"
    assert "Print iteration" in drawer.content
    assert "warping at corners" in drawer.content
    assert drawer.metadata["kind"] == "print_outcome"
    assert drawer.metadata["success"] is False


def test_writer_atomic_write_leaves_no_tmp_file(
    writer: ModuleType, tmp_path: Path
) -> None:
    """The .tmp file is renamed atomically — pending_files never sees it."""
    writer.write_capture(wing="w", room="r1", content="atomic check", home=tmp_path)
    spool = tmp_path / "spool"
    # No leftover .tmp dotfiles; pending_files filters them anyway.
    visible = list(spool.iterdir())
    tmp_files = [p for p in visible if p.name.startswith(".") and p.suffix == ".tmp"]
    assert tmp_files == []
    # The single produced file is what pending_files returns.
    assert len(pending_files(spool)) == 1
