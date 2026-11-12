"""Q08: a Crucible claim goes to a separate author, and the frozen tests are executed.

The authored test in ``claim_test_fixtures`` was written on 2026-11-11 by a
separate agent that saw only the exported packet (``AUTHOR-as-sent.md``),
never the subjects below. Its bytes are pinned so this file cannot quietly
replace it with a test written to fit the subject.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from cairntir.claim_tests import (
    ClaimTestError,
    Verdict,
    export_drawer_packet,
    export_packet,
    freeze_tests,
    qualify_claim_tests,
    run_claim_tests,
)
from cairntir.cli import app
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer

FIXTURES = Path(__file__).parent / "claim_test_fixtures"
AUTHORED = FIXTURES / "independent_author_test_claim.txt"
AUTHORED_SHA256 = "4cdc5e1b76c0dfed6917ab044b2e85075e542720585f3fdde4d2fe059b39387f"

CLAIM = (
    "reading_minutes(text) rounds the reading time up to whole minutes at 200 words "
    "per minute, and any text with at least one word takes at least one minute."
)
PREDICTED = (
    "reading_minutes('') == 0; one word gives 1; exactly 200 words gives 1; 201 words "
    "gives 2; 400 words gives 2; 401 words gives 3. Words are separated by any whitespace."
)
# Known-bad: rounds to the nearest minute, so one word is 0 and 201 words is 1.
KNOWN_BAD = "def reading_minutes(text):\n    return round(len(text.split()) / 200)\n"
CORRECTED = "def reading_minutes(text):\n    return -(-len(text.split()) // 200)\n"
TAUTOLOGY = (
    "import unittest\nimport readtime\n\n\nclass T(unittest.TestCase):\n"
    "    def test_self(self):\n"
    "        self.assertEqual(readtime.reading_minutes('a b'), readtime.reading_minutes('a b'))\n"
)

runner = CliRunner()


@pytest.fixture(autouse=True)
def _use_test_embedding_space(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "cairntir.cli.production_embedding_provider",
        lambda: HashEmbeddingProvider(dimension=384),
    )


def _subject(root: Path, source: str) -> Path:
    root.mkdir(parents=True)
    (root / "readtime.py").write_text(source, encoding="utf-8")
    return root


@pytest.fixture
def subjects(tmp_path: Path) -> dict[str, Path]:
    return {
        "bad": _subject(tmp_path / "bad", KNOWN_BAD),
        "fixed": _subject(tmp_path / "fixed", CORRECTED),
    }


def _packet(tmp_path: Path, name: str = "packet") -> Path:
    packet = tmp_path / name
    export_packet(
        packet,
        claim=CLAIM,
        predicted_outcome=PREDICTED,
        interface="readtime",
        claimant_id="claimant",
    )
    return packet


def _write_test(packet: Path, name: str, content: bytes) -> None:
    (packet / "tests" / name).write_bytes(content)


def _authored_packet(tmp_path: Path) -> Path:
    packet = _packet(tmp_path)
    _write_test(packet, "test_claim.py", AUTHORED.read_bytes())
    freeze_tests(packet, author_id="independent-author")
    return packet


def _store(path: Path) -> tuple[int, int]:
    with DrawerStore(path, HashEmbeddingProvider(dimension=384)) as store:
        falsifiable = store.add(
            Drawer(
                wing="demo",
                room="crucible",
                content="Crucible pre-flight for the reading-time estimate.",
                claim=CLAIM,
                predicted_outcome=PREDICTED,
            )
        )
        vague = store.add(
            Drawer(wing="demo", room="crucible", content="No prediction.", claim="It is fast.")
        )
    assert falsifiable.id is not None and vague.id is not None
    return falsifiable.id, vague.id


def test_the_authored_fixture_is_the_independent_authors_exact_bytes() -> None:
    assert hashlib.sha256(AUTHORED.read_bytes()).hexdigest() == AUTHORED_SHA256


def test_known_bad_behavior_falsifies_and_the_fix_holds(
    tmp_path: Path, subjects: dict[str, Path]
) -> None:
    packet = _authored_packet(tmp_path)
    bad = run_claim_tests(packet, subjects["bad"])
    fixed = run_claim_tests(packet, subjects["fixed"])
    assert bad.verdict is Verdict.FALSIFIED
    assert bad.failures > 0 and bad.tests_run == fixed.tests_run > 0
    assert fixed.verdict is Verdict.HELD
    assert (fixed.failures, fixed.errors, fixed.skipped) == (0, 0, 0)
    assert bad.artifacts == fixed.artifacts == (("tests/test_claim.py", AUTHORED_SHA256),)
    receipts = (packet / "RUNS.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["verdict"] for line in receipts] == ["FALSIFIED", "HELD"]


def test_qualify_requires_bad_to_fail_and_fix_to_pass(
    tmp_path: Path, subjects: dict[str, Path]
) -> None:
    packet = _authored_packet(tmp_path)
    good = qualify_claim_tests(packet, known_bad=subjects["bad"], corrected=subjects["fixed"])
    assert good["status"] == "QUALIFIED"
    swapped = qualify_claim_tests(packet, known_bad=subjects["fixed"], corrected=subjects["bad"])
    assert swapped["status"] == "NOT_QUALIFIED"
    assert len(swapped["reasons"]) == 2


def test_a_test_that_compares_the_subject_with_itself_is_not_an_oracle(
    tmp_path: Path, subjects: dict[str, Path]
) -> None:
    packet = _packet(tmp_path)
    _write_test(packet, "test_self.py", TAUTOLOGY.encode())
    freeze_tests(packet, author_id="someone-else")
    result = qualify_claim_tests(packet, known_bad=subjects["bad"], corrected=subjects["fixed"])
    assert result["status"] == "NOT_QUALIFIED"
    assert result["known_bad"]["verdict"] == "HELD"
    assert "do not detect the bad behavior" in result["reasons"][0]


def test_prompt_text_alone_is_never_an_executed_test(
    tmp_path: Path, subjects: dict[str, Path]
) -> None:
    packet = _packet(tmp_path)
    assert (packet / "AUTHOR.md").read_text(encoding="utf-8").count(CLAIM) == 1
    result = run_claim_tests(packet, subjects["fixed"])
    assert result.verdict is Verdict.NOT_EXECUTED
    assert result.tests_run == 0


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("import unittest\n", Verdict.NOT_EXECUTED),
        (
            "import unittest\n\n\nclass T(unittest.TestCase):\n"
            "    @unittest.skip('later')\n    def test_a(self):\n        pass\n",
            Verdict.NOT_EXECUTED,
        ),
        (
            "import unittest\n\n\nclass T(unittest.TestCase):\n"
            "    def test_a(self):\n        pass\n\n"
            "    @unittest.skip('later')\n    def test_b(self):\n        pass\n",
            Verdict.INCONCLUSIVE,
        ),
        (
            "import unittest\n\n\nclass T(unittest.TestCase):\n"
            "    @unittest.expectedFailure\n    def test_a(self):\n        self.fail()\n",
            Verdict.INCONCLUSIVE,
        ),
        (
            "import unittest\nimport no_such_subject_module\n",
            Verdict.INCONCLUSIVE,
        ),
        (
            "import unittest\nimport readtime\n\n\nclass T(unittest.TestCase):\n"
            "    def test_a(self):\n        readtime.reading_minutes(None)\n",
            Verdict.INCONCLUSIVE,
        ),
    ],
    ids=["no-cases", "all-skipped", "partly-skipped", "expected-failure", "import-error", "raises"],
)
def test_only_executed_assertions_decide_the_verdict(
    tmp_path: Path, subjects: dict[str, Path], body: str, expected: Verdict
) -> None:
    packet = _packet(tmp_path)
    _write_test(packet, "test_case.py", body.encode())
    freeze_tests(packet, author_id="someone-else")
    assert run_claim_tests(packet, subjects["fixed"]).verdict is expected


def test_the_claimant_cannot_author_its_own_tests(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    _write_test(packet, "test_claim.py", AUTHORED.read_bytes())
    with pytest.raises(ClaimTestError, match="must not be the claimant"):
        freeze_tests(packet, author_id=" Claimant ")
    assert not (packet / "FROZEN.json").exists()


def test_changed_tests_or_claim_after_freezing_are_refused(
    tmp_path: Path, subjects: dict[str, Path]
) -> None:
    packet = _authored_packet(tmp_path)
    test_file = packet / "tests" / "test_claim.py"
    original = test_file.read_bytes()
    test_file.write_bytes(original.replace(b'reading_minutes(""), 0)', b'reading_minutes(""), 1)'))
    with pytest.raises(ClaimTestError, match="changed after freezing"):
        run_claim_tests(packet, subjects["fixed"])
    test_file.write_bytes(original)
    _write_test(packet, "test_extra.py", b"import unittest\n")
    with pytest.raises(ClaimTestError, match="changed after freezing"):
        run_claim_tests(packet, subjects["fixed"])
    (packet / "tests" / "test_extra.py").unlink()
    claim = packet / "CLAIM.json"
    claim.write_bytes(claim.read_bytes().replace(b"200 words", b"250 words", 1))
    with pytest.raises(ClaimTestError, match="claim changed"):
        run_claim_tests(packet, subjects["fixed"])
    assert not (packet / "RUNS.jsonl").exists()


def test_unfrozen_tests_and_refreezing_are_refused(
    tmp_path: Path, subjects: dict[str, Path]
) -> None:
    packet = _packet(tmp_path)
    _write_test(packet, "test_claim.py", AUTHORED.read_bytes())
    with pytest.raises(ClaimTestError, match="not frozen"):
        run_claim_tests(packet, subjects["fixed"])
    freeze_tests(packet, author_id="independent-author")
    with pytest.raises(ClaimTestError, match="already frozen"):
        freeze_tests(packet, author_id="independent-author")


def test_export_refuses_reused_packets_and_bad_interfaces(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    with pytest.raises(ClaimTestError, match="new or empty"):
        _packet(tmp_path)
    assert (packet / "tests").is_dir()
    with pytest.raises(ClaimTestError, match="dotted Python module"):
        export_packet(
            tmp_path / "other",
            claim=CLAIM,
            predicted_outcome=PREDICTED,
            interface="readtime; rm -rf",
            claimant_id="claimant",
        )


def test_slow_tests_are_inconclusive(tmp_path: Path, subjects: dict[str, Path]) -> None:
    packet = _packet(tmp_path)
    _write_test(
        packet,
        "test_slow.py",
        b"import time\nimport unittest\n\n\nclass T(unittest.TestCase):\n"
        b"    def test_a(self):\n        time.sleep(30)\n",
    )
    freeze_tests(packet, author_id="someone-else")
    result = run_claim_tests(packet, subjects["fixed"], timeout=3)
    assert result.verdict is Verdict.INCONCLUSIVE
    assert "did not finish" in result.reason


def test_export_from_a_stored_drawer_carries_no_subject(tmp_path: Path) -> None:
    falsifiable, vague = _store(tmp_path / "memory.db")
    with DrawerStore(tmp_path / "memory.db", HashEmbeddingProvider(dimension=384)) as store:
        packet = export_drawer_packet(
            tmp_path / "p",
            store.reference_drawer(falsifiable),
            interface="readtime",
            claimant_id="claimant",
        )
        with pytest.raises(ClaimTestError, match="not falsifiable"):
            export_drawer_packet(
                tmp_path / "q",
                store.reference_drawer(vague),
                interface="readtime",
                claimant_id="claimant",
            )
        with pytest.raises(ClaimTestError, match="not found"):
            export_drawer_packet(
                tmp_path / "r", store.reference_drawer(9999), interface="x", claimant_id="c"
            )
    assert packet["source"]["drawer_id"] == falsifiable
    assert sorted(p.name for p in (tmp_path / "p").iterdir()) == [
        "AUTHOR.md",
        "CLAIM.json",
        "tests",
    ]
    assert not any((tmp_path / "p" / "tests").iterdir())
    assert not (tmp_path / "q").exists()


def _cli(*args: str) -> Any:
    return runner.invoke(app, ["claim-test", *args])


def test_cli_end_to_end_from_a_stored_claim(tmp_path: Path, subjects: dict[str, Path]) -> None:
    store = tmp_path / "memory.db"
    falsifiable, vague = _store(store)
    packet = tmp_path / "packet"
    common = ["--interface", "readtime", "--claimant", "claimant", "--store", str(store)]

    refused = _cli("export", str(tmp_path / "vague"), "--drawer", str(vague), *common)
    assert refused.exit_code == 2
    assert not (tmp_path / "vague").exists()

    exported = _cli("export", str(packet), "--drawer", str(falsifiable), *common)
    assert exported.exit_code == 0, exported.output
    assert json.loads(exported.stdout)["claim"] == CLAIM

    empty = _cli("run", str(packet), "--subject", str(subjects["fixed"]))
    assert empty.exit_code == 1
    assert json.loads(empty.stdout)["verdict"] == "NOT_EXECUTED"

    _write_test(packet, "test_claim.py", AUTHORED.read_bytes())
    assert _cli("freeze", str(packet), "--author", "claimant").exit_code == 2
    assert _cli("freeze", str(packet), "--author", "independent-author").exit_code == 0

    bad = _cli("run", str(packet), "--subject", str(subjects["bad"]))
    assert bad.exit_code == 1
    assert json.loads(bad.stdout)["verdict"] == "FALSIFIED"
    fixed = _cli("run", str(packet), "--subject", str(subjects["fixed"]))
    assert fixed.exit_code == 0
    assert json.loads(fixed.stdout)["verdict"] == "HELD"

    qualified = _cli(
        "qualify",
        str(packet),
        "--known-bad",
        str(subjects["bad"]),
        "--corrected",
        str(subjects["fixed"]),
    )
    assert qualified.exit_code == 0
    assert json.loads(qualified.stdout)["status"] == "QUALIFIED"
