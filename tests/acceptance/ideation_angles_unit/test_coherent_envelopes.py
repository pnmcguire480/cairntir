import pytest

from cairntir.errors import ProjectionError
from cairntir.ideation_angles import generate_angle_set

from . import test_i02 as fixture


@pytest.mark.parametrize("damage", ("done_false", "different_actual_model"))
def test_coherently_rehashed_incomplete_or_wrong_model_cannot_commit(tmp_path, damage):
    prepared = fixture.prepared.__wrapped__(tmp_path)
    adapter = fixture.FixtureAdapter()
    generate = adapter.generate

    def coherent_broken(bundle):
        envelope = generate(bundle)
        if damage == "done_false":
            envelope["done"] = False
        else:
            envelope["actual_model"] = "different-model"
        body = {
            "actual_model": envelope["actual_model"],
            "done": envelope["done"],
            "candidates": envelope["candidates"],
        }
        envelope["raw_response_sha256"] = fixture._sha(fixture._canonical(body))
        return envelope

    adapter.generate = coherent_broken
    with pytest.raises(ProjectionError):
        generate_angle_set(**fixture._request(prepared, adapter))
    assert adapter.calls == 1
    assert fixture._angle_rows(prepared["store"]) == 0
    assert not (prepared["vault"] / "cairntir-sync" / prepared["wing"] / "ideation").exists()
