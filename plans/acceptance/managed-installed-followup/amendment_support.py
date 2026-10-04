"""The five exact authorized verifier source changes, independently fixed."""

NEW_FREEZE = "4553f721df2f9beebbe68ae72df75c47f587655e77bd4923fb94b700c4ccd71b"
OLD_FREEZE = "53a59ffa4e0dbfded002cc505ad335062074321faf8f70d4a841b1f4c612e0ad"
OLD_MANAGED = "31452b541883edae15687dc8587234ff38ef97d5b9500ab5f985dbcc94c2866b"
NEW_MANAGED = "7d1c1bfb8ebee9ee3eff89b5bdd5b87c9108830a98091c02d54cdd4dff652a93"


def expected_verifier(original):
    changes = [
        (
            b'TemporaryDirectory(prefix="installed-", dir=output)',
            b'TemporaryDirectory(prefix="installed-")',
        ),
        (b"directory = Path(temporary)\n", b"directory = Path(temporary).resolve()\n"),
        (
            b'managed_source = restored / "plans/acceptance/managed-installed-qualification"',
            b'managed_source = ROOT / "plans/acceptance/managed-installed-followup"',
        ),
        (f'managed_hash = "{OLD_FREEZE}"'.encode(), f'managed_hash = "{NEW_FREEZE}"'.encode()),
        (
            b'managed_copy = directory / "managed_proof"',
            b'managed_copy = restored.parent / "managed_proof"',
        ),
    ]
    for before, after in changes:
        assert original.count(before) == 1, before
        original = original.replace(before, after)
    return original
