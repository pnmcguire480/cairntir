"""Only the standard owned relative venv lib64 alias may be normalized."""

import errno
import hashlib
import os
import stat
from pathlib import Path

import pytest

from cairntir import paladin_bootstrap as bootstrap


def snapshot(root):
    result = {}
    for directory, names, files in os.walk(root, followlinks=False):
        for name in sorted(names + files):
            path = Path(directory) / name
            info = path.lstat()
            row = {"mode": stat.S_IMODE(info.st_mode)}
            if stat.S_ISLNK(info.st_mode):
                row.update(kind="symlink", target=os.readlink(path))
            elif stat.S_ISDIR(info.st_mode):
                assert not getattr(info, "st_file_attributes", 0) & 0x400
                row["kind"] = "directory"
            else:
                assert stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                assert not getattr(info, "st_file_attributes", 0) & 0x400
                row.update(
                    kind="file",
                    bytes=info.st_size,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            result[path.relative_to(root).as_posix()] = row
    return result


def symlink(path, target):
    try:
        path.symlink_to(target, target_is_directory=True)
    except NotImplementedError:
        pytest.skip("Host cannot create real directory symlinks; no POSIX qualification")
    except OSError as exc:
        if (
            exc.errno in {errno.EPERM, errno.EACCES, errno.ENOTSUP, errno.EOPNOTSUPP}
            or getattr(exc, "winerror", None) == 1314
        ):
            pytest.skip("Host denies real directory symlinks; no POSIX qualification")
        raise
    assert path.is_symlink()
    return os.readlink(path)


def plain_venv(path):
    (path / "lib").mkdir(parents=True)
    (path / "lib/preserved.bin").write_bytes(b"Owned lib bytes.\r\n\x00")
    return path


def test_only_standard_relative_lib64_alias_is_removed(tmp_path):
    venv = plain_venv(tmp_path / "venv")
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"Never touch sibling bytes.\r\n")
    alias = venv / "lib64"
    assert symlink(alias, "lib") == "lib"
    before = snapshot(tmp_path)
    del before["venv/lib64"]

    bootstrap._remove_venv_lib64_alias(venv)

    assert not alias.exists() and not alias.is_symlink()
    assert snapshot(tmp_path) == before
    assert bootstrap._plain(venv / "lib") == venv / "lib"
    assert bootstrap._files(venv) == {
        "lib/preserved.bin": hashlib.sha256(b"Owned lib bytes.\r\n\x00").hexdigest()
    }


def test_unexpected_aliases_remain_intact_and_unsafe(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "preserved.bin").write_bytes(b"External target must stay exact.\r\n\x00")
    for kind in ("external-relative", "absolute", "other-relative"):
        venv = plain_venv(tmp_path / kind)
        (venv / "other").mkdir()
        (venv / "other/preserved.bin").write_bytes(b"Other target must stay exact.\n")
        target = {
            "external-relative": "../outside",
            "absolute": str(venv / "lib"),
            "other-relative": "other",
        }[kind]
        alias = venv / "lib64"
        original_target = symlink(alias, target)
        before = snapshot(tmp_path)
        try:
            bootstrap._remove_venv_lib64_alias(venv)
        except bootstrap.BootstrapError as exc:
            assert exc.code == "UNSAFE_INPUT"
        assert alias.is_symlink() and os.readlink(alias) == original_target
        assert snapshot(tmp_path) == before
        for action, argument in ((bootstrap._plain, alias), (bootstrap._files, venv)):
            with pytest.raises(bootstrap.BootstrapError) as refused:
                action(argument)
            assert refused.value.code == "UNSAFE_INPUT"


def test_linked_lib_target_is_rejected_without_removing_alias(tmp_path):
    venv = tmp_path / "venv"
    venv.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "preserved.bin").write_bytes(b"Linked target must stay exact.\r\n\x00")
    symlink(venv / "lib", "../outside")
    assert symlink(venv / "lib64", "lib") == "lib"
    before = snapshot(tmp_path)

    with pytest.raises(bootstrap.BootstrapError) as refused:
        bootstrap._remove_venv_lib64_alias(venv)

    assert refused.value.code == "UNSAFE_INPUT"
    assert snapshot(tmp_path) == before
    with pytest.raises(bootstrap.BootstrapError) as unsafe:
        bootstrap._files(venv)
    assert unsafe.value.code == "UNSAFE_INPUT"


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_regular_lib64_entries_remain_exact(tmp_path, kind):
    venv = plain_venv(tmp_path / "venv")
    alias = venv / "lib64"
    if kind == "directory":
        alias.mkdir()
        (alias / "preserved.bin").write_bytes(b"Regular lib64 directory bytes.\r\n")
    else:
        alias.write_bytes(b"Regular lib64 file bytes.\r\n")
    before = snapshot(tmp_path)
    files_before = bootstrap._files(venv)

    bootstrap._remove_venv_lib64_alias(venv)

    assert not alias.is_symlink()
    assert snapshot(tmp_path) == before
    assert bootstrap._files(venv) == files_before
