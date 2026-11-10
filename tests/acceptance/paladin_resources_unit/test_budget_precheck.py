import hashlib
import json
import zipfile
from pathlib import Path

from cairntir.access import AccessDenied, bind_grant, issue_grant, revoke_grant
from cairntir.managed import ManagedRuntime
from cairntir.paladin_resources import PaladinResourcesError, PaladinResourcesRun

from .acceptance import fixture

PRIMARY = Path(__file__).resolve().parent
FIXTURE_SHA256 = "e57bd1c0221cdc1b6233361ed691a296d8476b87f3b4f35b9b1a13a6e659b002"


def _fixture_module():
    path = PRIMARY / "acceptance/fixture.py"
    if hashlib.sha256(path.read_bytes()).hexdigest() != FIXTURE_SHA256:
        raise RuntimeError("Q05 primary fixture changed")
    return fixture


def test_actual_compressed_wheel_budget_is_rejected_before_overbudget_member_expansion(
    tmp_path, monkeypatch
):
    module = _fixture_module()
    fixture = module.ResourceFixture(tmp_path / "compressed-wheel-budget")
    try:
        payload = b"0" * (256 * 1024)
        (fixture.snapshot / "src/q05_notes/payload.bin").write_bytes(payload)
        fixture.contract["inputs"] = module.inventory(fixture.snapshot)
        budget = fixture.contract["policy"]["bundle_uncompressed_bytes"]
        attempted = []
        original_read = zipfile.ZipFile.read

        def bounded_read(archive, name, *args, **kwargs):
            member = name if isinstance(name, zipfile.ZipInfo) else archive.getinfo(name)
            if member.file_size > budget:
                attempted.append({"member": member.filename, "bytes": member.file_size})
                raise RuntimeError(
                    "independent guard refused expansion beyond declared bundle budget"
                )
            return original_read(archive, name, *args, **kwargs)

        with monkeypatch.context() as patcher:
            patcher.setattr(zipfile.ZipFile, "read", bounded_read)
            receipt = PaladinResourcesRun(fixture.runtime, contract=fixture.contract).execute(
                "bundle", fixture.action("bundle")
            )
        wheel = fixture.output / "bundle/q05_notes-0.0.1-py3-none-any.whl"
        with zipfile.ZipFile(wheel) as archive:
            assert archive.read("q05_notes/payload.bin") == payload
            assert archive.testzip() is None
            uncompressed = sum(item.file_size for item in archive.infolist() if not item.is_dir())
        observed = {
            "receipt": receipt,
            "forbidden_member_expansions": attempted,
            "compressed_bytes": wheel.stat().st_size,
            "uncompressed_bytes": uncompressed,
            "payload_bytes": len(payload),
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "actual_wheel_crc_verified_after_guard": True,
        }
        (fixture.root / "independent-budget-observation.json").write_text(
            json.dumps(observed, indent=2) + "\n", encoding="utf-8"
        )
        assert receipt["managed_result"]["outcome_drawer_id"] > 0
        assert receipt["managed_result"]["exit_code"] == 0
        assert wheel.stat().st_size <= fixture.contract["policy"]["bundle_compressed_bytes"]
        assert uncompressed > budget
        assert receipt["status"] == "FAIL", observed
        assert "BUNDLE_UNCOMPRESSED_BUDGET" in receipt["diagnostics"]
        assert receipt["metrics"]["compressed_bytes"] == wheel.stat().st_size
        assert receipt["metrics"]["uncompressed_bytes"] == uncompressed
        assert attempted == []
        assert (
            PaladinResourcesRun(fixture.runtime, contract=fixture.contract).report()["disposition"]
            == "BLOCKED"
        )
    finally:
        fixture.close()


def test_scoped_complete_report_refuses_revocation_during_final_artifact_validation(
    tmp_path, monkeypatch
):
    module = _fixture_module()
    fixture = module.ResourceFixture(tmp_path / "mid-report-revocation")
    try:
        owner_run = PaladinResourcesRun(fixture.runtime, contract=fixture.contract)
        for stage in fixture.contract["stages"]:
            assert (
                owner_run.execute(stage["stage_id"], fixture.action(stage["stage_id"]))["status"]
                == "PASS"
            )
        token = issue_grant(fixture.store, scopes=[{"wing": "resources"}], capabilities=["read"])
        runtime = ManagedRuntime(bind_grant(fixture.store, token), config=fixture.config)
        scoped_run = PaladinResourcesRun(runtime, contract=fixture.contract)
        assert scoped_run.report()["disposition"] == "COMPLETE"
        original_closure = PaladinResourcesRun._closure
        interleaved = []

        def revoke_after_final_closure(run, stage_id):
            artifacts = original_closure(run, stage_id)
            if run is scoped_run and stage_id == "security" and not interleaved:
                revoke_grant(fixture.store, token)
                interleaved.append(fixture.state())
            return artifacts

        returned = None
        refused = False
        with monkeypatch.context() as patcher:
            patcher.setattr(PaladinResourcesRun, "_closure", revoke_after_final_closure)
            try:
                returned = scoped_run.report()
            except (AccessDenied, PaladinResourcesError):
                refused = True
        revoked = fixture.store._conn.execute("SELECT revoked FROM access_grants").fetchall()
        observed = {
            "refused": refused,
            "returned": returned,
            "interleavings": len(interleaved),
            "revoked_rows": [row[0] for row in revoked],
            "db_unchanged_after_owner_revocation": bool(interleaved)
            and fixture.state() == interleaved[0],
        }
        (fixture.root / "independent-revocation-observation.json").write_text(
            json.dumps(observed, indent=2) + "\n", encoding="utf-8"
        )
        assert len(interleaved) == 1
        assert [row[0] for row in revoked] == [1]
        assert fixture.state() == interleaved[0]
        assert refused, observed
    finally:
        fixture.close()
