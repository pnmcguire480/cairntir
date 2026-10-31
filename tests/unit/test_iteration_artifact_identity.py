"""Artifact source identity controls for path and descriptor timestamp views."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from cairntir.iteration_artifacts import IterationArtifactError, _source

_CREATED_NS = 1793316246127935300
_CHANGED_NS = 1793316246178913300
_ORIGINAL = b"solid initial\nendsolid initial\n"
_REVISED = b"solid changed\nendsolid changed\n"


class _StatView:
    def __init__(self, info: os.stat_result, **fields: int | float) -> None:
        self._info = info
        self._fields = fields

    def __getattr__(self, name: str) -> object:
        return self._fields[name] if name in self._fields else getattr(self._info, name)


@dataclass
class _Clock:
    change_ns: int = _CREATED_NS
    descriptor_observations: int = 0
    on_open: Callable[[], None] | None = None


def _windows_views(source: Path, monkeypatch: pytest.MonkeyPatch) -> _Clock:
    original_lstat = Path.lstat
    original_fstat = os.fstat
    clock = _Clock()

    def path_view(path: Path, *args: object, **kwargs: object) -> object:
        info = original_lstat(path, *args, **kwargs)
        if path != source:
            return info
        return _StatView(
            info,
            st_ctime_ns=_CREATED_NS,
            st_ctime=_CREATED_NS / 1_000_000_000,
            st_birthtime_ns=_CREATED_NS,
            st_birthtime=_CREATED_NS / 1_000_000_000,
        )

    def descriptor_view(fd: int) -> object:
        info = original_fstat(fd)
        change_ns = clock.change_ns
        clock.descriptor_observations += 1
        if clock.descriptor_observations == 1 and clock.on_open is not None:
            clock.on_open()
        return _StatView(
            info,
            st_ctime_ns=change_ns,
            st_ctime=change_ns / 1_000_000_000,
            st_birthtime_ns=_CREATED_NS,
            st_birthtime=_CREATED_NS / 1_000_000_000,
        )

    monkeypatch.setattr(Path, "lstat", path_view)
    monkeypatch.setattr(os, "fstat", descriptor_view)
    return clock


def test_source_reads_current_bytes_after_completed_rewrite(tmp_path: Path) -> None:
    source = tmp_path / "mesh.stl"
    source.write_bytes(_ORIGINAL)
    source.write_bytes(_REVISED)

    assert _source(source, "stl", None, 1024) == ("mesh.stl", _REVISED)


def test_source_reads_stable_file_with_windows_mixed_ctime_views(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "mesh.stl"
    source.write_bytes(_ORIGINAL)
    source.write_bytes(_REVISED)
    clock = _windows_views(source, monkeypatch)
    clock.change_ns = _CHANGED_NS

    assert _source(source, "stl", None, 1024) == ("mesh.stl", _REVISED)
    assert clock.descriptor_observations == 2


def test_source_refuses_same_size_write_with_restored_mtime_and_changed_descriptor_ctime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "mesh.stl"
    source.write_bytes(_ORIGINAL)
    before = source.stat()
    clock = _windows_views(source, monkeypatch)

    def change_during_read() -> None:
        source.write_bytes(_REVISED)
        os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
        clock.change_ns = _CHANGED_NS

    clock.on_open = change_during_read
    with pytest.raises(IterationArtifactError) as caught:
        _source(source, "stl", None, 1024)

    assert caught.value.code == "UNSAFE_SOURCE"
    assert clock.descriptor_observations == 2
    assert source.read_bytes() == _REVISED
    assert source.stat().st_size == before.st_size
    assert source.stat().st_mtime_ns == before.st_mtime_ns


@pytest.mark.parametrize("changed", [_ORIGINAL + b"extra", _ORIGINAL[:-1]], ids=["grow", "shrink"])
def test_source_refuses_size_change_with_unchanged_mtime_and_ctime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: bytes
) -> None:
    source = tmp_path / "mesh.stl"
    source.write_bytes(_ORIGINAL)
    before = source.stat()
    clock = _windows_views(source, monkeypatch)

    def change_during_read() -> None:
        source.write_bytes(changed)
        os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))

    clock.on_open = change_during_read
    with pytest.raises(IterationArtifactError) as caught:
        _source(source, "stl", None, 1024)

    assert caught.value.code == "UNSAFE_SOURCE"
    assert clock.descriptor_observations == 2
    assert source.read_bytes() == changed
    assert source.stat().st_mtime_ns == before.st_mtime_ns


def test_source_refuses_mtime_change_with_unchanged_bytes_and_ctime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "mesh.stl"
    source.write_bytes(_ORIGINAL)
    before = source.stat()
    clock = _windows_views(source, monkeypatch)
    changed_mtime = before.st_mtime_ns + 1_000_000_000
    clock.on_open = lambda: os.utime(source, ns=(before.st_atime_ns, changed_mtime))

    with pytest.raises(IterationArtifactError) as caught:
        _source(source, "stl", None, 1024)

    assert caught.value.code == "UNSAFE_SOURCE"
    assert clock.descriptor_observations == 2
    assert source.read_bytes() == _ORIGINAL
    assert source.stat().st_mtime_ns == changed_mtime


@pytest.mark.parametrize("phase", ["opening", "final_path"])
def test_source_refuses_replacement_with_matching_bytes_size_and_timestamps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    source = tmp_path / "mesh.stl"
    replacement = tmp_path / "replacement.stl"
    source.write_bytes(_ORIGINAL)
    replacement.write_bytes(_ORIGINAL)
    before = source.stat()
    os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert replacement.stat().st_ino != before.st_ino
    clock = _windows_views(source, monkeypatch)
    replaced = False

    def replace() -> None:
        nonlocal replaced
        os.replace(replacement, source)
        replaced = True

    if phase == "opening":
        original_open = os.open

        def replace_before_open(*args: object, **kwargs: object) -> int:
            replace()
            return original_open(*args, **kwargs)

        monkeypatch.setattr(os, "open", replace_before_open)
    else:
        original_lstat = Path.lstat

        def replace_before_final_path(path: Path, *args: object, **kwargs: object) -> object:
            if path == source and clock.descriptor_observations == 2 and not replaced:
                replace()
            return original_lstat(path, *args, **kwargs)

        monkeypatch.setattr(Path, "lstat", replace_before_final_path)

    with pytest.raises(IterationArtifactError) as caught:
        _source(source, "stl", None, 1024)

    assert caught.value.code == "UNSAFE_SOURCE"
    assert replaced
    assert clock.descriptor_observations == (1 if phase == "opening" else 2)
    assert source.read_bytes() == _ORIGINAL
    assert source.stat().st_size == before.st_size
    assert source.stat().st_mtime_ns == before.st_mtime_ns


@pytest.mark.parametrize("location", ["source", "ancestor"])
@pytest.mark.parametrize("link", ["symlink", "reparse"])
def test_source_refuses_linked_path_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, location: str, link: str
) -> None:
    source = tmp_path / "mesh.stl"
    source.write_bytes(_ORIGINAL)
    target = source if location == "source" else source.parent
    original_lstat = Path.lstat

    def linked_view(path: Path, *args: object, **kwargs: object) -> object:
        info = original_lstat(path, *args, **kwargs)
        if path != target:
            return info
        if link == "symlink":
            return _StatView(info, st_mode=stat.S_IFLNK | stat.S_IMODE(info.st_mode))
        return _StatView(info, st_file_attributes=getattr(info, "st_file_attributes", 0) | 0x400)

    monkeypatch.setattr(Path, "lstat", linked_view)
    with pytest.raises(IterationArtifactError) as caught:
        _source(source, "stl", None, 1024)

    assert caught.value.code == "UNSAFE_SOURCE"
    assert source.read_bytes() == _ORIGINAL


@pytest.mark.parametrize("data", [b"", b"x" * 1025], ids=["empty", "oversized"])
def test_source_refuses_unbounded_file(tmp_path: Path, data: bytes) -> None:
    source = tmp_path / "mesh.stl"
    source.write_bytes(data)

    with pytest.raises(IterationArtifactError) as caught:
        _source(source, "stl", None, 1024)

    assert caught.value.code == "UNSAFE_SOURCE"
