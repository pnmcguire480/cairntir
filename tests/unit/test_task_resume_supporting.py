"""Post-freeze independent transaction-release probes, not replacement acceptance."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from test_task_resume_acceptance import (
    _advance,
    _embedder,
    _require_api,
    _resume,
    _save,
    _state,
)

from cairntir.errors import CairntirError
from cairntir.memory.store import DrawerStore


@pytest.mark.parametrize("existing_task", [False, True])
def test_post_append_failure_releases_transaction_for_an_independent_writer(
    tmp_cairntir_home: Path, monkeypatch: pytest.MonkeyPatch, existing_task: bool
) -> None:
    _require_api()
    monkeypatch.delenv("CAIRNTIR_GRANT_FILE", raising=False)
    database = tmp_cairntir_home / "cairntir.db"
    assert Path(os.environ["CAIRNTIR_HOME"]) == tmp_cairntir_home
    with DrawerStore(database, _embedder()) as owner:
        created = _save(owner) if existing_task else None
        checkpoint = _advance(created) if created else None
        before = _state()
        append = owner.add
        observed = []

        def interrupted_append(*args: Any, **kwargs: Any) -> Any:
            saved = append(*args, **kwargs)
            observed.append(saved.id)
            raise CairntirError("supporting probe interruption after real drawer append")

        with monkeypatch.context() as patch:
            patch.setattr(owner, "add", interrupted_append)
            with pytest.raises(CairntirError, match="supporting probe interruption"):
                _save(owner, checkpoint=checkpoint)
        assert len(observed) == 1
        assert owner._conn.in_transaction is False
        assert _state() == before
        with DrawerStore(database, _embedder()) as independent:
            saved = _save(independent, checkpoint=checkpoint)
            assert saved["revision"] == (2 if existing_task else 1)
            assert saved["replayed"] is False
        resumed = _resume(owner, task_id=saved["task_id"])
        assert resumed["status"] == "ready"
        assert resumed["revision"] == saved["revision"]
