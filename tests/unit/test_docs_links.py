from __future__ import annotations

import runpy
from pathlib import Path

CHECKER = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/check_docs_links.py"))


def test_missing_relative_and_repository_main_links_fail(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "[missing](docs/gone.md)\n"
        "[repo](https://github.com/pnmcguire480/cairntir/blob/main/gone.md)\n",
        encoding="utf-8",
    )
    assert CHECKER["missing_links"](tmp_path) == [
        "README.md: docs/gone.md",
        "README.md: gone.md",
    ]


def test_existing_links_fragments_external_and_code_examples_pass(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "[self](README.md#intro) [external](https://example.invalid) [anchor](#intro)\n"
        "```markdown\n[example](missing.md)\n```\n",
        encoding="utf-8",
    )
    assert CHECKER["missing_links"](tmp_path) == []


def test_the_maintained_repository_has_no_broken_local_links() -> None:
    assert CHECKER["missing_links"](CHECKER["REPO_ROOT"]) == []
