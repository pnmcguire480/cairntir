"""Exercise the real CLI callback and store opener for R17 publication."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cairntir import cli
from cairntir.access import issue_grant
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.procedures import PracticeGovernance, ProcedureBook, ProcedureSpec

WING = "r17-cli-startup-proof"
CANARY = "R17_CLI_SOURCE_PRIVATE_CANARY"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_actual_cli_startup_owner_scoped_and_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    db = home / "cairntir.db"
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    with DrawerStore(db, HashEmbeddingProvider(dimension=16)) as store:
        source = store.add(Drawer(wing=WING, room="cases", content=CANARY))
        assert source.id is not None
        candidate = ProcedureBook(store, {}).propose(
            wing=WING,
            spec=ProcedureSpec(
                "CLI startup practice",
                ("local source",),
                "local use",
                ("inspect",),
                "recorded",
                ("return to source",),
                (source.id,),
                governance=PracticeGovernance(
                    "Owner label", "v1", "CLI startup rationale", "2026-12-01"
                ),
            ),
        )
        assert candidate.drawer_id is not None
        full = issue_grant(store, scopes=[{"wing": WING}], capabilities=["read"])
        limited = issue_grant(
            store,
            scopes=[{"wing": WING, "rooms": ["discoveries"]}],
            capabilities=["read"],
        )
    before = _digest(db)
    monkeypatch.setenv("CAIRNTIR_HOME", str(home))
    monkeypatch.setenv("PYTHONPATH", str(Path(cli.__file__).resolve().parents[1]))
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.delenv("CAIRNTIR_GRANT_FILE", raising=False)
    monkeypatch.setattr(
        cli, "production_embedding_provider", lambda: HashEmbeddingProvider(dimension=16)
    )

    def unexpected_startup(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("CLI registration or update hook ran before read-only publication")

    monkeypatch.setattr(cli, "ensure_registered", unexpected_startup)
    monkeypatch.setattr(cli, "maybe_check_in_background", unexpected_startup)
    real_store = cli.DrawerStore
    opened_read_only: list[bool] = []

    def observed_store(*args: object, **kwargs: object) -> DrawerStore:
        opened_read_only.append(kwargs.get("read_only") is True)
        return real_store(*args, **kwargs)

    monkeypatch.setattr(cli, "DrawerStore", observed_store)
    args = ["obsidian-project", str(vault), "--wing", WING, "--practice-register"]
    owner = CliRunner().invoke(cli.app, args)
    assert owner.exit_code == 0, repr(owner.exception) + owner.output
    assert "projected practice register" in owner.output
    assert "learning log" not in owner.output.lower()
    assert _digest(db) == before
    register = next(vault.rglob("register.md"))
    assert "CLI startup practice" in register.read_text(encoding="utf-8")

    grant_file = tmp_path / "grant.txt"
    grant_file.write_text(full, encoding="utf-8")
    monkeypatch.setenv("CAIRNTIR_GRANT_FILE", str(grant_file))
    scoped = CliRunner().invoke(cli.app, args)
    assert scoped.exit_code == 0, repr(scoped.exception) + scoped.output
    assert "projected practice register" in scoped.output
    assert _digest(db) == before

    grant_file.write_text(limited, encoding="utf-8")
    denied = CliRunner().invoke(cli.app, args)
    assert denied.exit_code != 0
    combined = denied.output + (denied.stderr or "")
    assert "practice register unavailable" in combined.lower()
    assert CANARY not in combined and str(source.id) not in combined
    assert "CLI startup practice" not in register.read_text(encoding="utf-8")
    assert _digest(db) == before
    assert opened_read_only == [True, True, True]
