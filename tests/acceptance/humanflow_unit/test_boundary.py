"""Independent R12 publication and attribution boundary controls."""

from __future__ import annotations

import json
from dataclasses import replace

import cairntir.obsidian as projection
import cairntir.paladin_python as api
from cairntir.codeglass import CODEGLASS_ROOM
from cairntir.provenance import Sensitivity

from .test_humanflow import FixtureAdapter, _flow, _selectors, _two
from .test_humanflow import prepared as prepared


def _walkthroughs(fixture):
    return tuple(fixture.store.list_by(wing="paladin", room=CODEGLASS_ROOM, limit=None))


def test_builtin_adapter_identity_matches_actual_request(prepared, monkeypatch):
    fixture = prepared()
    _, run, _, _ = _two(fixture)
    sent = {}

    class Response:
        status = 200

        def getheader(self, _name):
            return None

        def read(self, _limit):
            return sent["response"]

    class Connection:
        def __init__(self, host, port, timeout):
            assert host == "127.0.0.1" and port == 11434 and timeout == 1

        def request(self, method, path, body, headers):
            assert method == "POST" and path == "/api/generate"
            request = json.loads(body)
            sent["model"] = request["model"]
            bundle = json.loads(request["prompt"])
            result = FixtureAdapter().generate(
                bundle, reader_level="beginner", max_output_chars=12000
            )
            sent["response"] = json.dumps(
                {"model": request["model"], "done": True, "response": json.dumps(result)}
            ).encode()

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(api.http.client, "HTTPConnection", Connection)
    adapter = api.OllamaNarrationAdapter(
        endpoint="http://127.0.0.1:11434", model="actual-a", timeout_seconds=1
    )
    try:  # noqa: SIM105
        adapter.identity["model_id"] = "forged-b"
    except TypeError:
        pass
    narrator = _flow(run, adapter)
    draft = narrator.draft(reader_level="beginner", **_selectors(fixture))
    assert sent["model"] == "actual-a"
    assert draft["adapter"]["model_id"] == sent["model"]
    published = narrator.publish(draft)
    assert published["status"] == "PUBLISHED"
    assert (
        fixture.store.get(published["walkthrough_id"]).metadata["adapter"]["model_id"] == "actual-a"
    )


def test_publish_rechecks_source_inside_commit_action(prepared, monkeypatch):
    fixture = prepared()
    _, run, _, _ = _two(fixture)
    narrator = _flow(run, FixtureAdapter())
    draft = narrator.draft(reader_level="beginner", **_selectors(fixture))
    before = _walkthroughs(fixture)
    original = run._save

    def change_after_preflight(suffix, operation, request, produce):
        (fixture.snapshots[1] / "src/flow.py").write_text("changed after preflight")
        return original(suffix, operation, request, produce)

    monkeypatch.setattr(run, "_save", change_after_preflight)
    try:
        result = narrator.publish(draft)
    except api.PaladinPythonError:
        pass
    else:
        assert result["status"] != "PUBLISHED"
    assert _walkthroughs(fixture) == before


def test_publish_rejects_caller_mutation_during_recheck(prepared, monkeypatch):
    fixture = prepared()
    _, run, _, _ = _two(fixture)
    narrator = _flow(run, FixtureAdapter())
    draft = narrator.draft(reader_level="beginner", **_selectors(fixture))
    before = _walkthroughs(fixture)
    original = run.check_report

    def mutate_during_recheck(*args, **kwargs):
        draft["adapter"]["model_id"] = "forged-during-publish"
        draft["response_sha256"] = "0" * 64
        return original(*args, **kwargs)

    monkeypatch.setattr(run, "check_report", mutate_during_recheck)
    try:
        result = narrator.publish(draft)
    except api.PaladinPythonError:
        pass
    else:
        assert result["status"] != "PUBLISHED"
    assert _walkthroughs(fixture) == before


def test_r12_projection_rechecks_visibility_before_generated_write(prepared, monkeypatch):
    fixture = prepared()
    _, run, old, _ = _two(fixture)
    narrator = _flow(run, FixtureAdapter())
    draft = narrator.draft(reader_level="beginner", **_selectors(fixture))
    published = narrator.publish(draft)
    source_id = old["evidence"][-1]["drawer_id"]
    vault = fixture.root / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    first = projection.project_to_obsidian(fixture.store, vault=vault, wing="paladin")
    note = next(
        path
        for path in first.codeglass_notes
        if path.name.startswith(f"{published['walkthrough_id']}-")
    )
    human = b"Human text remains.\r\n"
    note.write_bytes(note.read_bytes() + human)
    original_check = projection._check_source_projectable
    revoked = False

    def revoke_after_validated(store, drawer_id, wing):
        nonlocal revoked
        visible = original_check(store, drawer_id, wing)
        if drawer_id == source_id and visible and not revoked:
            revoked = True
            provenance = fixture.store.get_provenance(source_id)
            with fixture.store.transaction():
                fixture.store._conn.execute(
                    "UPDATE drawers SET provenance = ? WHERE id = ?",
                    (replace(provenance, sensitivity=Sensitivity.SECRET).to_json(), source_id),
                )
        return visible

    monkeypatch.setattr(projection, "_check_source_projectable", revoke_after_validated)
    projection.project_to_obsidian(fixture.store, vault=vault, wing="paladin")
    generated = (
        note.read_bytes()
        .split(b"<!-- cairntir:generated:begin -->", 1)[1]
        .split(b"<!-- cairntir:generated:end -->", 1)[0]
    )
    assert revoked and b"unavailable" in generated.lower()
    assert b"test_negative" not in generated and b"Input -2" not in generated
    assert note.read_bytes().endswith(human)
