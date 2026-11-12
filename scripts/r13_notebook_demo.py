"""Build a synthetic study export for trying NotebookLM delivery by hand.

Never touches a real memory store: it makes its own small database inside the
folder you give it, filled with made-up notes.

    python scripts/r13_notebook_demo.py FOLDER first    # four sources to upload
    python scripts/r13_notebook_demo.py FOLDER update   # change two, print the plan
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.study import export_study_sources, stage_notebook_delivery

WING = "r13-demo"
KEY = "r13-demo-notebook"
CATEGORIES = ("patterns", "rules", "walkthroughs", "projects")
FIRST = {
    "patterns": "The Lighthouse pattern: when a task keeps failing, step back and name the goal.",
    "rules": "The Compass rule: every claim in a report must point at something observed.",
    "walkthroughs": "The Harbor walkthrough: open the log, find the first error, then read upward.",
    "projects": "The Kestrel project: a small tool that sorts seed packets by planting month.",
}
SECOND = {
    "rules": "The Compass rule, revised: every claim must cite an observation and its date.",
    "projects": "The Kestrel project, revised: it now also sorts seed packets by sun needs.",
}


def _add(store: DrawerStore, category: str, text: str, supersedes: int | None = None) -> int:
    drawer = Drawer(
        wing=WING,
        room=category,
        content=text,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        supersedes_id=supersedes,
    )
    saved = store.add(drawer).id
    if saved is None:
        raise RuntimeError("the demo store did not return a drawer id")
    return saved


def main(argv: list[str]) -> int:
    """Run one phase of the demo and print the plan."""
    if len(argv) != 3 or argv[2] not in {"first", "update"}:
        print(__doc__)
        return 2
    root = Path(argv[1]).absolute()
    root.mkdir(parents=True, exist_ok=True)
    state = root / "demo-state.json"
    store = DrawerStore(root / "demo.db", HashEmbeddingProvider(32), automatic_backups=False)
    try:
        if argv[2] == "first":
            if state.exists():
                print("This folder already has a demo. Use an empty folder.")
                return 1
            ids = {c: _add(store, c, FIRST[c]) for c in CATEGORIES}
        else:
            ids = json.loads(state.read_bytes())
            for category, text in SECOND.items():
                ids[category] = _add(store, category, text, supersedes=ids[category])
        state.write_text(json.dumps(ids), encoding="utf-8")
        selection = {c: [store.portable_identity(ids[c])] for c in CATEGORIES}
        export_study_sources(
            store, wing=WING, notebook_key=KEY, selection=selection, output=root / "export"
        )
        plan = stage_notebook_delivery(root / "export", root / "upload")
    finally:
        store.close()
    print(f"Files to upload are in: {root / 'upload'}")
    for row in plan["plan"]:
        if row["action"] == "keep":
            print(f"keep     {row['name']}")
            continue
        if row["remove"]:
            print(f"remove   {row['remove']}   (delete this source from the notebook)")
        print(f"upload   {row['upload']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
