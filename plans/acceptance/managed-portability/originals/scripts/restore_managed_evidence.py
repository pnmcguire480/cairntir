"""Reconstruct frozen managed evidence in a new disposable verification directory.

Historical resources are preserved byte-for-byte in a pinned archive; corrected
maintained controls remain ordinary analyzed Python. No checkout file is written.
"""

from __future__ import annotations

import hashlib
import io
import os
import stat
import zipfile
from pathlib import Path

ARCHIVE_RELATIVE = "plans/acceptance/managed-evidence-archive/resources.zip"
ARCHIVE_SHA256 = "1edcbfc15631a0803aa79b6b2cee7cc0524abab7681040b686bd73e5cd9f9735"
_ENTRIES = (
    (
        "managed-installed-qualification/originals/test_managed_projection.py",
        "d2596ed498de7a30a2f835c268a1f134000be7c60b8ae91e518fabb350f9cbed",
        14931,
    ),
    (
        "managed-session-port/marker-amendment-v2/test_managed_durable_boundaries_v2.py",
        "1404d419ef7e8f1f766d87e4cae1c0ee3c0f1f81c6b86a92ac237bbba958626a",
        10915,
    ),
    (
        "managed-session-port/raw-projection-amendment-v3/test_managed_durable_boundaries_v3.py",
        "0fdb5c914a9bd912084f1a110ba0cc3f1c634b0baa0ae2ab4a7ad4aa4ca2ed94",
        11197,
    ),
    (
        "managed-session-port/test_managed_durable_boundaries.py",
        "06e88054c2a8a291a0bcea04c8d47866cb5834ddc7ba5e7ca60cd35a225a3406",
        10895,
    ),
    (
        "managed-session-port/visibility-v1/test_hidden_event.py",
        "b8130fee1de2e94a16c0f708a9e3163c810358c23f4f2623bed89f7719c24992",
        3868,
    ),
    (
        "managed-session-port/visibility-v2/test_hidden_event_v2.py",
        "1fb15d60edfd8205b4156c63d07ba93fae64b49ab1887388b70d6cf7d7e64eb5",
        3897,
    ),
    (
        "v2-managed-projection/test_managed_projection.py",
        "d2596ed498de7a30a2f835c268a1f134000be7c60b8ae91e518fabb350f9cbed",
        14931,
    ),
    (
        "v2-managed-runtime/evidence/repair-2-independent/run.py",
        "25ad27c31bbd487d45a1a42258d240f77318481af5107711b43791122eb52cd3",
        6394,
    ),
)
FILES = {"plans/acceptance/" + name: digest for name, digest, _ in _ENTRIES}
SIZES = {"plans/acceptance/" + name: size for name, _, size in _ENTRIES}
PACKETS = (
    "managed-installed-qualification",
    "managed-session-port",
    "v2-managed-projection",
    "v2-managed-runtime",
)


def _regular(path: Path, *, directory: bool = False) -> None:
    """Reject links, Windows reparse points and unexpected filesystem objects."""
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError(f"frozen evidence path is a link or reparse point: {path}")
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode):
        raise ValueError(f"frozen evidence path has an unexpected file type: {path}")


def _parents(path: Path) -> None:
    """Check every existing ancestor before resolving or writing a path."""
    for parent in reversed((path, *path.parents)):
        if parent.exists() or parent.is_symlink():
            _regular(parent, directory=True)


def _resources(source: Path) -> dict[str, bytes]:
    """Validate exact archive membership and bytes before producing any output."""
    path = source / ARCHIVE_RELATIVE
    _parents(path.parent)
    _regular(path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("frozen managed archive digest changed")
    result = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)) or set(names) != set(FILES):
            raise ValueError("frozen managed archive membership changed")
        # Choose output names from the fixed trusted map, never archive metadata.
        for name, expected in FILES.items():
            entry = archive.getinfo(name)
            if (
                entry.is_dir()
                or entry.flag_bits & 1
                or entry.compress_type != zipfile.ZIP_STORED
                or not stat.S_ISREG(entry.external_attr >> 16)
                or entry.file_size != SIZES[name]
            ):
                raise ValueError(f"frozen managed archive entry changed: {name}")
            data = archive.read(entry)
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError(f"frozen managed resource changed: {name}")
            result[name] = data
    return result


def restore(source_root: Path, destination_root: Path) -> Path:
    """Copy four exact capsules and archived resources into a new destination.

    Validate everything before the first write. Refuse existing destinations,
    unsafe filesystem entries, and altered duplicate resource files. The caller
    owns the disposable output's lifetime; a failed write stays visible.
    """
    source = Path(source_root).absolute()
    destination = Path(destination_root).absolute()
    _parents(source)
    _regular(source, directory=True)
    _parents(destination.parent)
    source = source.resolve(strict=True)
    destination = destination.resolve(strict=False)
    if destination.exists() or destination.is_symlink():
        raise ValueError("managed evidence destination must be new")
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError("managed evidence destination must be outside the source")
    files = _resources(source)
    for packet in PACKETS:
        root = source / "plans/acceptance" / packet
        _parents(root)
        _regular(root, directory=True)
        for directory, children, names in os.walk(root, followlinks=False, onerror=_walk_error):
            current = Path(directory)
            for child in children:
                _regular(current / child, directory=True)
            children[:] = [
                name for name in children if name not in {"__pycache__", ".pytest_cache"}
            ]
            for name in names:
                path = current / name
                _regular(path)
                if path.suffix in {".pyc", ".pyo"}:
                    continue
                relative = path.relative_to(source).as_posix()
                raw = path.read_bytes()
                if relative in files and raw != files[relative]:
                    raise ValueError(f"frozen managed duplicate resource changed: {relative}")
                files[relative] = raw
    destination.mkdir()
    for relative, raw in files.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as output:
            output.write(raw)
    return destination


def _walk_error(error: OSError) -> None:
    """Surface unreadable source evidence instead of silently omitting it."""
    raise error
