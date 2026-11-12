"""Record the R12 teaching artifact once (manual; pytest does not collect it).

1. Runs the real two-attempt flow in a temporary isolated store.
2. Writes ``artifact/bundle.json`` for the host model to read.
3. Waits for the host to write ``artifact/narration.json``.
4. Drafts and publishes through ``HostNarrationAdapter`` and the unchanged
   validator, then writes the published walkthrough and Obsidian note.

Usage, from the repository root:
``uv run python tests/acceptance/humanflow_teaching_unit/record.py``
"""

from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cairntir.codeglass import retention_report
from cairntir.obsidian import project_to_obsidian
from cairntir.paladin_python import HostNarrationAdapter, HumanFlowRun
from humanflow_teaching_unit.teaching import (
    ARTIFACT,
    prepare_fixture,
    run_two,
    selectors,
)


def _dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    """Record bundle, wait for host narration, publish, preserve outputs."""
    case = unittest.TestCase()
    try:
        fixture = prepare_fixture(case)
        run = run_two(fixture)
        placeholder = HostNarrationAdapter({}, model_id="reader", bundle_sha256="0" * 64)
        exported = HumanFlowRun(run, adapter=placeholder).prepare(**selectors(fixture))
        _dump(ARTIFACT / "bundle.json", exported)
        print("bundle written", exported["bundle_sha256"], flush=True)
        target = ARTIFACT / "narration.json"
        deadline = time.monotonic() + 3600
        while not target.exists():
            if time.monotonic() > deadline:
                print("no narration written", flush=True)
                return 1
            time.sleep(2)
        time.sleep(2)
        written = json.loads(target.read_text(encoding="utf-8"))
        adapter = HostNarrationAdapter(
            written["response"],
            model_id=written["model_id"],
            bundle_sha256=written["bundle_sha256"],
        )
        narrator = HumanFlowRun(run, adapter=adapter)
        draft = narrator.draft(reader_level=written["reader_level"], **selectors(fixture))
        published = narrator.publish(draft)
        walkthrough = fixture.store.get(published["walkthrough_id"])
        (ARTIFACT / "walkthrough.md").write_text(walkthrough.content, encoding="utf-8")
        vault = fixture.root / "vault"
        (vault / ".obsidian").mkdir(parents=True)
        projected = project_to_obsidian(fixture.store, vault=vault, wing="paladin")
        note = next(
            path for path in projected.codeglass_notes if path.name.startswith(f"{walkthrough.id}-")
        )
        (ARTIFACT / "obsidian-note.md").write_bytes(note.read_bytes())
        report = retention_report(fixture.store, walkthrough_id=walkthrough.id)
        _dump(
            ARTIFACT / "publication.json",
            {
                "status": published["status"],
                "walkthrough_id": published["walkthrough_id"],
                "adapter": draft["adapter"],
                "reader_level": draft["reader_level"],
                "bundle_sha256": draft["bundle_sha256"],
                "response_sha256": draft["response_sha256"],
                "humanflow_schema": walkthrough.metadata["humanflow_schema"],
                "retention": {
                    "immediate_score": report.immediate_score,
                    "delayed_score": report.delayed_score,
                    "retention_delta": report.retention_delta,
                },
            },
        )
        print("published", published, flush=True)
        return 0
    finally:
        case.doCleanups()


if __name__ == "__main__":
    raise SystemExit(main())
