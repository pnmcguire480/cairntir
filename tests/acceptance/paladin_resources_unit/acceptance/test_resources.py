import hashlib
import json
import math
import pstats
import zipfile
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from cairntir.access import AccessDenied, bind_grant, issue_grant, revoke_grant
from cairntir.managed import ManagedRuntime
from cairntir.paladin_resources import PaladinResourcesError, PaladinResourcesRun

from .fixture import STAGES, ResourceFixture


@pytest.fixture
def make_fixture(tmp_path):
    fixtures = []

    def make(**kwargs):
        value = ResourceFixture(tmp_path / f"fixture-{len(fixtures)}", **kwargs)
        fixtures.append(value)
        return value

    yield make
    for value in fixtures:
        value.close()


def execute(fixture, stage):
    return PaladinResourcesRun(fixture.runtime, contract=fixture.contract).execute(
        stage, fixture.action(stage)
    )


def test_actual_three_stages_replay_and_readonly_reopen(make_fixture):
    fixture = make_fixture()
    run = PaladinResourcesRun(fixture.runtime, contract=fixture.contract)
    for stage in STAGES:
        receipt = run.execute(stage, fixture.action(stage))
        assert receipt["status"] == "PASS", receipt
        assert receipt["evidence_ids"]
        assert receipt["managed_result"]["outcome_drawer_id"] > 0
        assert receipt["managed_result"]["exit_code"] == 0
        assert not receipt["managed_result"]["timed_out"]
    performance = run.report()["stages"][0]["receipt"]["metrics"]["datasets"]
    assert [row["size"] for row in performance] == [100, 1000]
    raw = json.loads((fixture.output / "performance/report.json").read_text())
    for row, raw_row in zip(performance, raw["datasets"]):  # noqa: B905
        assert len(row["wall_samples_ns"]) == 20
        assert all(type(value) is int and value > 0 for value in row["wall_samples_ns"])
        assert row["wall_samples_ns"] == raw_row["wall_samples_ns"]
        assert row["wall_p95_ns"] == sorted(row["wall_samples_ns"])[math.ceil(20 * 0.95) - 1]
        assert row["wall_p95_ns"] <= 250000000
        assert 0 < row["python_peak_bytes"] <= 8388608
        stats = pstats.Stats(str(fixture.output / "performance" / raw_row["profile_path"]))
        observed = sum(
            value[1]
            for key, value in stats.stats.items()
            if "'execute' of 'sqlite3.Connection'" in key[2]
        )
        assert observed == row["profile_sql_calls"] == 256
        expected = [f"note-{(index * 17) % row['size'] + 1:05d}" for index in range(256)]
        expected_hash = hashlib.sha256(
            json.dumps(expected, separators=(",", ":")).encode()
        ).hexdigest()
        declared = next(
            item["expected_output_sha256"]
            for item in fixture.contract["policy"]["expected_outputs"]
            if item["size"] == row["size"]
        )
        assert row["oracle_sha256"] == expected_hash == declared == raw_row["oracle_sha256"]
    launches = (fixture.output / "performance/launches.jsonl").read_bytes()
    assert len(launches.splitlines()) == 48
    replay = run.execute("performance", fixture.actions["performance"])
    assert replay["replayed"] and replay["status"] == "PASS"
    assert (fixture.output / "performance/launches.jsonl").read_bytes() == launches
    wheel = fixture.output / "bundle/q05_notes-0.0.1-py3-none-any.whl"
    bundle = run.report()["stages"][1]["receipt"]["metrics"]
    with zipfile.ZipFile(wheel) as archive:
        assert (
            archive.read("q05_notes/notes.py")
            == (fixture.snapshot / "src/q05_notes/notes.py").read_bytes()
        )
        assert bundle["uncompressed_bytes"] == sum(item.file_size for item in archive.infolist())
    assert bundle["compressed_bytes"] == wheel.stat().st_size
    assert json.loads((fixture.output / "security/report.json").read_text()) == []
    assert run.report()["disposition"] == "COMPLETE"
    fixture.reopen()
    reopened = PaladinResourcesRun(fixture.runtime, contract=fixture.contract)
    before = fixture.state()
    assert reopened.report()["disposition"] == "COMPLETE"
    assert reopened.report()["qualification"]["status"] == "CURRENT"
    assert fixture.state() == before
    assert (fixture.output / "performance/launches.jsonl").read_bytes() == launches


def test_redundant_actual_sql_work_fails_named_budget_with_same_outputs(make_fixture):
    fixture = make_fixture(variant="redundant")
    receipt = execute(fixture, "performance")
    assert receipt["status"] == "FAIL", receipt
    assert "PERFORMANCE_SQL_CALL_BUDGET" in receipt["diagnostics"]
    assert "FUNCTIONAL_ORACLE" not in receipt["diagnostics"]
    assert [row["profile_sql_calls"] for row in receipt["metrics"]["datasets"]] == [20256, 20256]
    assert all(row["oracle_sha256"] for row in receipt["metrics"]["datasets"])
    assert (
        PaladinResourcesRun(fixture.runtime, contract=fixture.contract).report()["disposition"]
        == "BLOCKED"
    )


def test_actual_python_allocation_regression_fails_named_budget(make_fixture):
    fixture = make_fixture(variant="allocation")
    receipt = execute(fixture, "performance")
    assert receipt["status"] == "FAIL", receipt
    assert "PERFORMANCE_PYTHON_ALLOCATION_BUDGET" in receipt["diagnostics"]
    assert "FUNCTIONAL_ORACLE" not in receipt["diagnostics"]
    assert all(row["python_peak_bytes"] > 8388608 for row in receipt["metrics"]["datasets"])
    assert all(row["profile_sql_calls"] == 256 for row in receipt["metrics"]["datasets"])


def test_prospective_one_nanosecond_budget_fails_actual_wall_measurements(make_fixture):
    fixture = make_fixture()
    fixture.contract["policy"]["wall_p95_ns"] = 1
    receipt = execute(fixture, "performance")
    assert receipt["status"] == "FAIL", receipt
    assert "PERFORMANCE_WALL_BUDGET" in receipt["diagnostics"]
    assert all(row["wall_p95_ns"] > 1 for row in receipt["metrics"]["datasets"])
    assert all(row["profile_sql_calls"] == 256 for row in receipt["metrics"]["datasets"])


def test_actual_oversized_wheel_fails_measured_archive_budget(make_fixture):
    fixture = make_fixture(variant="oversized")
    receipt = execute(fixture, "bundle")
    assert receipt["status"] == "FAIL", receipt
    assert "BUNDLE_COMPRESSED_BUDGET" in receipt["diagnostics"]
    assert "BUNDLE_UNCOMPRESSED_BUDGET" in receipt["diagnostics"]
    wheel = fixture.output / "bundle/q05_notes-0.0.1-py3-none-any.whl"
    with zipfile.ZipFile(wheel) as archive:
        assert len(archive.read("q05_notes/payload.bin")) == 1048576
    assert receipt["metrics"]["compressed_bytes"] == wheel.stat().st_size > 65536


@pytest.mark.parametrize("variant", ["unsafe", "unsafe-noqa"])
def test_actual_ruff_eval_finding_fails_exact_rule_and_source(make_fixture, variant):
    fixture = make_fixture(variant=variant)
    receipt = execute(fixture, "security")
    assert receipt["status"] == "FAIL", receipt
    assert "SECURITY_FINDING_S307" in receipt["diagnostics"]
    raw = json.loads((fixture.output / "security/report.json").read_text())
    assert len(raw) == 1 and raw[0]["code"] == "S307"
    assert raw[0]["filename"].replace("\\", "/").endswith("/src/q05_notes/notes.py")
    assert raw[0]["location"]["row"] > 0
    assert receipt["metrics"]["findings"] == raw
    assert receipt["managed_result"]["exit_code"] == 1


def test_actual_wrong_functional_output_cannot_pass_resource_limits(make_fixture):
    fixture = make_fixture(variant="wrong")
    receipt = execute(fixture, "performance")
    assert receipt["status"] == "FAIL", receipt
    assert "FUNCTIONAL_ORACLE" in receipt["diagnostics"]


@pytest.mark.parametrize(
    "field",
    [
        "wall_p95_ns",
        "python_peak_bytes",
        "profile_sql_calls",
        "bundle_compressed_bytes",
        "bundle_uncompressed_bytes",
        "security_rules",
        "maximum_findings",
        "expected_outputs",
    ],
)
def test_missing_budget_or_threat_policy_refuses_without_dispatch(make_fixture, field):
    fixture = make_fixture()
    del fixture.contract["policy"][field]
    before = fixture.state()
    with pytest.raises(PaladinResourcesError):
        PaladinResourcesRun(fixture.runtime, contract=fixture.contract)
    assert fixture.state() == before
    assert not (fixture.output / "performance/launches.jsonl").exists()


def test_missing_scanner_payload_never_passes(make_fixture):
    fixture = make_fixture()
    missing = fixture.root / "missing-ruff"
    missing.mkdir()
    next(tool for tool in fixture.contract["tools"] if tool["id"] == "ruff")["payload_root"] = str(
        missing
    )
    try:
        receipt = execute(fixture, "security")
    except PaladinResourcesError:
        pass
    else:
        assert receipt["status"] == "INCONCLUSIVE", receipt
    assert not (fixture.output / "security/report.json").exists()


def test_declared_output_digest_is_compared_generically_to_actual_workload(make_fixture):
    fixture = make_fixture()
    fixture.contract["policy"]["expected_outputs"][0]["expected_output_sha256"] = "0" * 64
    receipt = execute(fixture, "performance")
    assert receipt["status"] == "FAIL", receipt
    assert "FUNCTIONAL_ORACLE" in receipt["diagnostics"]
    raw = json.loads((fixture.output / "performance/report.json").read_text())
    assert (
        raw["datasets"][0]["oracle_sha256"]
        == "1db455f8afc6340d2159eabcfbbca09e51ba36cc3e3a804d6a642b593165d919"
    )


@pytest.mark.parametrize("defect", ["wrong_type", "duplicate", "missing_size"])
def test_oracle_digest_manifest_requires_typed_complete_unique_datasets(make_fixture, defect):
    fixture = make_fixture()
    rows = fixture.contract["policy"]["expected_outputs"]
    if defect == "wrong_type":
        rows[0]["size"] = True
    elif defect == "duplicate":
        rows.append(deepcopy(rows[0]))
    else:
        rows.pop()
    before = fixture.state()
    with pytest.raises(PaladinResourcesError):
        PaladinResourcesRun(fixture.runtime, contract=fixture.contract)
    assert fixture.state() == before
    assert not (fixture.output / "performance/launches.jsonl").exists()


@pytest.mark.parametrize("target", ["source", "producer"])
def test_changed_bound_input_refuses_before_dispatch(make_fixture, target):
    fixture = make_fixture()
    path = (
        fixture.snapshot / "src/q05_notes/notes.py"
        if target == "source"
        else fixture.producer / "measure.py"
    )
    path.write_bytes(path.read_bytes() + b"\n")
    try:
        receipt = execute(fixture, "performance")
    except PaladinResourcesError:
        pass
    else:
        assert receipt["status"] == "INCONCLUSIVE", receipt
    assert not (fixture.output / "performance/launches.jsonl").exists()


def test_changed_profile_cannot_run_alternate_command(make_fixture):
    fixture = make_fixture()
    fixture.contract["stages"][0]["command"]["argv"].append("--undeclared")
    try:
        receipt = execute(fixture, "performance")
    except PaladinResourcesError:
        pass
    else:
        assert receipt["status"] == "INCONCLUSIVE", receipt
    assert not (fixture.output / "performance/launches.jsonl").exists()


@pytest.mark.parametrize("change", ["delete", "corrupt"])
def test_reopen_blocks_changed_actual_artifact_without_erasing_history(make_fixture, change):
    fixture = make_fixture()
    assert execute(fixture, "security")["status"] == "PASS"
    report = fixture.output / "security/report.json"
    report.unlink() if change == "delete" else report.write_text(
        '{"forged":true}', encoding="utf-8"
    )
    fixture.reopen()
    run = PaladinResourcesRun(fixture.runtime, contract=fixture.contract)
    before = fixture.state()
    current = run.report()
    assert current["disposition"] == "BLOCKED"
    assert current["qualification"]["status"] != "CURRENT"
    assert current["stages"][2]["receipt"]["status"] == "PASS"
    assert fixture.state() == before


def test_exit_zero_receipt_without_real_measurements_cannot_pass(make_fixture):
    fixture = make_fixture(producer_variant="receipt-only")
    receipt = execute(fixture, "performance")
    assert receipt["managed_result"]["exit_code"] == 0
    assert receipt["status"] == "INCONCLUSIVE", receipt
    assert "INVALID_PERFORMANCE_ARTIFACT" in receipt["diagnostics"]


def test_actual_timeout_is_inconclusive_and_cannot_relaunch(make_fixture):
    fixture = make_fixture(producer_variant="timeout")
    run = PaladinResourcesRun(fixture.runtime, contract=fixture.contract)
    receipt = run.execute("performance", fixture.action("performance"))
    assert receipt["status"] == "INCONCLUSIVE", receipt
    assert receipt["managed_result"]["timed_out"]
    replay = run.execute("performance", fixture.actions["performance"])
    assert replay["replayed"] and replay["status"] == "INCONCLUSIVE"
    with pytest.raises(PaladinResourcesError):
        run.execute("performance", fixture.action("performance"))


def test_contract_replacement_cannot_reuse_committed_run(make_fixture):
    fixture = make_fixture()
    assert execute(fixture, "security")["status"] == "PASS"
    modified = deepcopy(fixture.contract)
    modified["policy"]["maximum_findings"] = 1
    with pytest.raises(PaladinResourcesError):
        PaladinResourcesRun(fixture.runtime, contract=modified).execute(
            "security", fixture.actions["security"]
        )


def test_different_task_cannot_authorize_this_run(make_fixture):
    fixture = make_fixture()
    fixture.contract["task_id"] = str(uuid4())
    action = fixture.action("security")
    before = fixture.state()
    with pytest.raises(PaladinResourcesError):
        PaladinResourcesRun(fixture.runtime, contract=fixture.contract).execute("security", action)
    assert fixture.state() == before
    assert not (fixture.output / "security/report.json").exists()


def test_revoked_scoped_reader_cannot_recover_resource_evidence(make_fixture):
    fixture = make_fixture()
    assert execute(fixture, "security")["status"] == "PASS"
    token = issue_grant(
        fixture.store, scopes=[{"wing": "resources"}], capabilities=["read", "write"]
    )
    runtime = ManagedRuntime(bind_grant(fixture.store, token), config=deepcopy(fixture.config))
    run = PaladinResourcesRun(runtime, contract=fixture.contract)
    assert run.report()["stages"][2]["receipt"]["status"] == "PASS"
    revoke_grant(fixture.store, token)
    before = fixture.state()
    with pytest.raises((PaladinResourcesError, AccessDenied)):
        run.report()
    assert fixture.state() == before


def test_committed_managed_outcome_recovers_after_lost_reply_without_relaunch(
    make_fixture, monkeypatch
):
    fixture = make_fixture()
    run = PaladinResourcesRun(fixture.runtime, contract=fixture.contract)
    action = fixture.action("performance")
    dispatch = ManagedRuntime.dispatch
    committed = []

    class ReplyLost(BaseException):
        pass

    def lose_reply(runtime, request):
        result = dispatch(runtime, request)
        committed.append(result)
        raise ReplyLost("simulated controller termination after real committed managed outcome")

    with monkeypatch.context() as patcher:
        patcher.setattr(ManagedRuntime, "dispatch", lose_reply)
        with pytest.raises(ReplyLost):
            run.execute("performance", action)
    assert len(committed) == 1
    assert committed[0]["outcome_drawer_id"] > 0
    assert committed[0]["exit_code"] == 0
    launches = (fixture.output / "performance/launches.jsonl").read_bytes()
    assert len(launches.splitlines()) == 48
    fixture.reopen()
    fixture.runtime.start(str(uuid4()), task_id=fixture.capture["task_id"])

    def no_dispatch(*args, **kwargs):
        raise AssertionError("committed action recovery must not dispatch again")

    with monkeypatch.context() as patcher:
        patcher.setattr(ManagedRuntime, "dispatch", no_dispatch)
        recovered = PaladinResourcesRun(fixture.runtime, contract=fixture.contract).execute(
            "performance", action
        )
    assert recovered["replayed"] and recovered["status"] == "PASS"
    assert recovered["managed_result"]["outcome_drawer_id"] == committed[0]["outcome_drawer_id"]
    assert (fixture.output / "performance/launches.jsonl").read_bytes() == launches


@pytest.mark.parametrize("target", ["profile", "child-output", "wheel"])
def test_reopen_revalidates_raw_artifact_closure_without_erasing_history(make_fixture, target):
    fixture = make_fixture()
    stage = "bundle" if target == "wheel" else "performance"
    assert execute(fixture, stage)["status"] == "PASS"
    path = {
        "profile": fixture.output / "performance/profile-100.prof",
        "child-output": fixture.output / "performance/child-100-wall-0.stdout",
        "wheel": fixture.output / "bundle/q05_notes-0.0.1-py3-none-any.whl",
    }[target]
    path.write_bytes(path.read_bytes() + b" ")
    fixture.reopen()
    run = PaladinResourcesRun(fixture.runtime, contract=fixture.contract)
    before = fixture.state()
    report = run.report()
    assert report["disposition"] == "BLOCKED"
    assert report["qualification"]["status"] != "CURRENT"
    assert report["stages"][STAGES.index(stage)]["receipt"]["status"] == "PASS"
    assert fixture.state() == before


@pytest.mark.parametrize("target", ["source", "producer"])
def test_reopen_revalidates_bound_input_bytes_after_pass(make_fixture, target):
    fixture = make_fixture()
    assert execute(fixture, "security")["status"] == "PASS"
    path = (
        fixture.snapshot / "src/q05_notes/notes.py"
        if target == "source"
        else fixture.producer / "measure.py"
    )
    path.write_bytes(path.read_bytes() + b"\n")
    fixture.reopen()
    run = PaladinResourcesRun(fixture.runtime, contract=fixture.contract)
    before = fixture.state()
    report = run.report()
    assert report["disposition"] == "BLOCKED"
    assert report["qualification"]["status"] != "CURRENT"
    assert report["stages"][2]["receipt"]["status"] == "PASS"
    assert fixture.state() == before


def test_reopen_revalidates_copied_tool_payload_without_touching_originals(make_fixture):
    fixture = make_fixture(copy_uv=True)
    original_tool = next(tool for tool in fixture.platform["tools"] if tool["id"] == "uv")
    copied_tool = next(tool for tool in fixture.contract["tools"] if tool["id"] == "uv")
    original = Path(original_tool["payload_root"]) / "build-constraints.txt"
    copied = Path(copied_tool["payload_root"]) / "build-constraints.txt"
    original_bytes = original.read_bytes()
    assert original.resolve() != copied.resolve()
    assert copied.read_bytes() == original_bytes
    assert execute(fixture, "bundle")["status"] == "PASS"
    copied.write_bytes(original_bytes + b"\n")
    fixture.reopen()
    run = PaladinResourcesRun(fixture.runtime, contract=fixture.contract)
    before = fixture.state()
    report = run.report()
    assert report["disposition"] == "BLOCKED"
    assert report["qualification"]["status"] != "CURRENT"
    assert report["stages"][1]["receipt"]["status"] == "PASS"
    assert fixture.state() == before
    assert original.read_bytes() == original_bytes


def resource_rows(fixture):
    prefix = f"paladin-resources:{fixture.contract['run_id']}:"
    return [
        dict(row)
        for row in fixture.store._conn.execute(
            "SELECT * FROM workflow_runs WHERE substr(idempotency_key,1,?)=?",
            (len(prefix), prefix),
        ).fetchall()
    ]


def projection(fixture, *, scopes=None, **selectors):
    token = issue_grant(
        fixture.store, scopes=scopes or [{"wing": "resources"}], capabilities=["read"]
    )
    scoped = bind_grant(fixture.store, token)
    selected = {
        "wing": "resources",
        "room": "requests",
        "run_id": fixture.contract["run_id"],
        "task_id": fixture.capture["task_id"],
        **selectors,
    }
    return scoped, selected


def test_complete_wing_readonly_projection_matches_authoritative_registry(make_fixture):
    fixture = make_fixture()
    assert execute(fixture, "security")["status"] == "PASS"
    rows = resource_rows(fixture)
    assert len(rows) == 3
    scoped, selected = projection(fixture)
    runtime = ManagedRuntime(scoped, config=deepcopy(fixture.config))
    run = PaladinResourcesRun(runtime, contract=fixture.contract)
    before = fixture.state()
    result = scoped._paladin_resources_records(**selected)
    assert result.keys() == {"resources", "managed"}
    expected = {
        row["idempotency_key"]: {
            "idempotency_key": row["idempotency_key"],
            "operation": row["operation"],
            "request_hash": row["request_hash"],
            "state": row["state"],
            "result": json.loads(row["result"]),
        }
        for row in rows
    }
    assert {row["idempotency_key"]: row for row in result["resources"]} == expected
    assert {row["_managed"]["operation"] for row in result["managed"]} == {
        "managed.event.v1",
        "managed.dispatch.v1",
        "managed.outcome.v1",
    }
    for row in result["managed"]:
        if row["_managed"]["operation"] == "managed.event.v1":
            assert row["event_id"] == fixture.capture["event_id"]
        else:
            assert row["action_id"] == fixture.actions["security"]["action_id"]
    assert run.report()["stages"][2]["receipt"]["status"] == "PASS"
    assert fixture.state() == before


@pytest.mark.parametrize(
    "defect", ["partial", "foreign-wing", "foreign-room", "foreign-task", "malformed-run"]
)
def test_projection_refuses_partial_or_foreign_context_and_malformed_selectors(
    make_fixture, defect
):
    fixture = make_fixture()
    assert execute(fixture, "security")["status"] == "PASS"
    scopes = [{"wing": "resources", "rooms": ["requests"]}] if defect == "partial" else None
    overrides = {
        "foreign-wing": {"wing": "elsewhere"},
        "foreign-room": {"room": "elsewhere"},
        "foreign-task": {"task_id": str(uuid4())},
        "malformed-run": {"run_id": "not-a-canonical-uuid"},
    }.get(defect, {})
    scoped, selected = projection(fixture, scopes=scopes, **overrides)
    before = fixture.state()
    with pytest.raises(AccessDenied):
        scoped._paladin_resources_records(**selected)
    assert fixture.state() == before


@pytest.mark.parametrize(
    "defect", ["request-hash", "source-body", "managed-action", "duplicate-namespace"]
)
def test_projection_refuses_forged_or_duplicate_authoritative_bindings(make_fixture, defect):
    fixture = make_fixture()
    assert execute(fixture, "security")["status"] == "PASS"
    rows = resource_rows(fixture)
    result_row = next(row for row in rows if row["operation"] == "paladin.resources.result.v1")
    envelope = json.loads(result_row["result"])
    with fixture.store.transaction():
        if defect == "request-hash":
            fixture.store._conn.execute(
                "UPDATE workflow_runs SET request_hash=? WHERE idempotency_key=?",
                ("0" * 64, result_row["idempotency_key"]),
            )
        elif defect == "source-body":
            drawer_id = envelope["evidence"]["drawer_id"]
            body = json.loads(
                fixture.store._conn.execute(
                    "SELECT content FROM drawers WHERE id=?", (drawer_id,)
                ).fetchone()[0]
            )
            body["operation"] = "paladin.resources.forged.v1"
            fixture.store._conn.execute(
                "UPDATE drawers SET content=? WHERE id=?", (json.dumps(body), drawer_id)
            )
        elif defect == "managed-action":
            row = fixture.store._conn.execute(
                "SELECT idempotency_key,result FROM workflow_runs "
                "WHERE operation='managed.outcome.v1'"
            ).fetchone()
            managed = json.loads(row["result"])
            managed["action_id"] = str(uuid4())
            fixture.store._conn.execute(
                "UPDATE workflow_runs SET result=? WHERE idempotency_key=?",
                (json.dumps(managed), row["idempotency_key"]),
            )
        else:
            duplicate = "grant:" + "e" * 64 + ":" + result_row["idempotency_key"]
            columns = list(result_row)
            values = [
                duplicate if name == "idempotency_key" else result_row[name] for name in columns
            ]
            fixture.store._conn.execute(
                "INSERT INTO workflow_runs ("  # noqa: S608
                + ",".join(columns)
                + ") VALUES ("
                + ",".join("?" for _ in values)
                + ")",
                values,
            )
    scoped, selected = projection(fixture)
    runtime = ManagedRuntime(scoped, config=deepcopy(fixture.config))
    before = fixture.state()
    with pytest.raises(AccessDenied):
        scoped._paladin_resources_records(**selected)
    with pytest.raises((AccessDenied, PaladinResourcesError)):
        PaladinResourcesRun(runtime, contract=fixture.contract).report()
    assert fixture.state() == before


def test_source_drawers_cannot_substitute_for_missing_committed_registry(make_fixture):
    fixture = make_fixture()
    assert execute(fixture, "security")["status"] == "PASS"
    rows = resource_rows(fixture)
    assert len(rows) == 3
    source_ids = [json.loads(row["result"])["evidence"]["drawer_id"] for row in rows]
    source_before = [
        fixture.store._conn.execute("SELECT content FROM drawers WHERE id=?", (key,)).fetchone()[0]
        for key in source_ids
    ]
    with fixture.store.transaction():
        fixture.store._conn.executemany(
            "DELETE FROM workflow_runs WHERE idempotency_key=?",
            [(row["idempotency_key"],) for row in rows],
        )
    scoped, selected = projection(fixture)
    runtime = ManagedRuntime(scoped, config=deepcopy(fixture.config))
    before = fixture.state()
    assert scoped._paladin_resources_records(**selected) == {"resources": [], "managed": []}
    try:
        current = PaladinResourcesRun(runtime, contract=fixture.contract).report()
    except (AccessDenied, PaladinResourcesError):
        pass
    else:
        assert current["disposition"] == "BLOCKED"
        assert all(row["status"] != "PASS" for row in current["stages"])
    assert [
        fixture.store._conn.execute("SELECT content FROM drawers WHERE id=?", (key,)).fetchone()[0]
        for key in source_ids
    ] == source_before
    assert fixture.state() == before


def test_preparation_without_managed_intent_stays_readable_and_cannot_relaunch(
    make_fixture, monkeypatch
):
    fixture = make_fixture()
    action = fixture.action("security")

    class PreparedInterrupted(BaseException):
        pass

    def interrupt_before_dispatch(*args, **kwargs):
        raise PreparedInterrupted(
            "simulated interruption after preparation and before managed intent"
        )

    with monkeypatch.context() as patcher:
        patcher.setattr(ManagedRuntime, "dispatch", interrupt_before_dispatch)
        with pytest.raises(PreparedInterrupted):
            PaladinResourcesRun(fixture.runtime, contract=fixture.contract).execute(
                "security", action
            )
    assert len(resource_rows(fixture)) == 2
    assert not (fixture.output / "security/report.json").exists()
    scoped, selected = projection(fixture)
    runtime = ManagedRuntime(scoped, config=deepcopy(fixture.config))
    before = fixture.state()
    records = scoped._paladin_resources_records(**selected)
    assert len(records["resources"]) == 2
    assert all(row["_managed"]["operation"] == "managed.event.v1" for row in records["managed"])
    report = PaladinResourcesRun(runtime, contract=fixture.contract).report()
    assert report["disposition"] == "BLOCKED"
    assert report["stages"][2]["status"] in {"PENDING", "INCONCLUSIVE"}
    assert fixture.state() == before
    with pytest.raises(PaladinResourcesError):
        PaladinResourcesRun(fixture.runtime, contract=fixture.contract).execute("security", action)
    assert not (fixture.output / "security/report.json").exists()
