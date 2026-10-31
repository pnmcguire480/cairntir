from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from cairntir import _paladin_ui_worker as worker

FIXTURES = Path(__file__).resolve().parents[1] / "acceptance/paladin_ui_unit"
TOOL_IDS = (
    "python",
    "node",
    "playwright",
    "playwright-core",
    "chrome",
    "pngjs",
    "pixelmatch",
    "worker",
    "producer",
)


def encoded(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def reference(path, name=None):
    value = path.read_bytes()
    return {
        "path": str(path) if name is None else name,
        "sha256": digest(value),
        "bytes": len(value),
    }


def inventory(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.fixture
def prepared(tmp_path):
    root = tmp_path.resolve()
    project = root / "project"
    project.mkdir()
    shutil.copytree(FIXTURES / "fixtures/assets", project / "assets")
    shutil.copy2(FIXTURES / "fixtures/clean.html", project / "index.html")
    media = {
        ".html": "text/html",
        ".ttf": "font/ttf",
        ".txt": "text/plain",
        ".svg": "image/svg+xml",
    }
    files = [
        {**reference(path, path.relative_to(project).as_posix()), "media_type": media[path.suffix]}
        for path in sorted(
            project.rglob("*"), key=lambda item: item.relative_to(project).as_posix()
        )
        if path.is_file()
    ]
    tools = []
    for name in TOOL_IDS:
        directory = root / "tools" / name
        directory.mkdir(parents=True)
        entry = directory / "entry.txt"
        entry.write_text("Validation input only: " + name, encoding="utf-8")
        tools.append(
            {
                "id": name,
                "root": str(directory),
                "entry_path": entry.name,
                "version": "validation-fixture",
                "files": [reference(entry, entry.name)],
            }
        )
    manifest = {
        "schema": "cairntir.paladin-ui-tools.v1",
        "tools": tools,
        "packaged_chromium_version": "151.0.7922.34",
    }
    manifest_path = root / "tools.json"
    manifest_path.write_bytes(encoded(manifest))
    output = root / "output"
    output.mkdir()
    template = {
        "schema": "cairntir.paladin-ui-producer-template.v1",
        "mode": "capture-baseline",
        "project": {
            "project_id": "boundary-project",
            "route_id": "index",
            "state_id": "initial",
            "source_revision": "fixture-v1",
            "snapshot_root": str(project),
            "snapshot_sha256": digest(encoded(files)),
            "files": files,
            "entry_path": "index.html",
        },
        "output_root": str(output),
        "selected_tools": reference(manifest_path),
        "render_policy": json.loads((FIXTURES / "RENDER-POLICY.json").read_bytes()),
        "checks": json.loads((FIXTURES / "CHECKS.json").read_bytes()),
        "baseline_reference": None,
    }
    return root, template, manifest


def test_valid_owned_inputs_validate_without_launch_or_artifacts(prepared, monkeypatch):
    root, template, _ = prepared
    before = inventory(root)

    def unexpected_launch(*_args, **_kwargs):
        pytest.fail("Input validation attempted to launch a producer")

    monkeypatch.setattr(worker.subprocess, "Popen", unexpected_launch)
    monkeypatch.setattr(worker, "OwnedProcess", unexpected_launch)
    validated = worker.validate_template(template)
    assert validated == template and validated is not template
    selected = worker._tools(validated, time.monotonic() + 10)
    assert set(selected) == set(TOOL_IDS)
    worker._project(validated, time.monotonic() + 10)
    validated["project"]["source_revision"] = "detached"
    assert template["project"]["source_revision"] == "fixture-v1"
    assert inventory(root) == before
    assert list((root / "output").iterdir()) == []


@pytest.mark.parametrize(
    "attack,error",
    [
        ("tool-bytes", "Pinned file changed"),
        ("tool-escape", "Unsafe relative path"),
        ("project-bytes", "Complete project snapshot changed"),
        ("project-escape", "Unsafe relative path"),
        ("request-substitution", "Request template differs"),
    ],
)
def test_rejects_substitution_before_producer_launch_or_artifact_writes(prepared, attack, error):
    root, template, manifest = prepared
    outside = root / "outside.txt"
    outside.write_text("Outside selected input roots", encoding="utf-8")
    if attack == "tool-bytes":
        entry = Path(manifest["tools"][0]["root"]) / "entry.txt"
        entry.write_text("Substituted tool bytes", encoding="utf-8")
    elif attack == "tool-escape":
        selected = manifest["tools"][0]
        selected["entry_path"] = "../../outside.txt"
        selected["files"] = [reference(outside, "../../outside.txt")]
        manifest_path = Path(template["selected_tools"]["path"])
        manifest_path.write_bytes(encoded(manifest))
        template["selected_tools"] = reference(manifest_path)
    elif attack == "project-bytes":
        (root / "project/index.html").write_text("Substituted project bytes", encoding="utf-8")
    elif attack == "project-escape":
        template["project"]["files"].append(
            {**reference(outside, "../outside.txt"), "media_type": "text/plain"}
        )
        template["project"]["files"].sort(key=lambda item: item["path"])
        template["project"]["snapshot_sha256"] = digest(encoded(template["project"]["files"]))
    template_path = root / "template.json"
    template_path.write_bytes(encoded(template))
    template_hash = digest(template_path.read_bytes())
    supplied = deepcopy(template)
    if attack == "request-substitution":
        supplied["project"]["source_revision"] = "substituted-request"
    request = {
        "schema": "cairntir.paladin-ui-producer.v1",
        "run_id": str(uuid4()),
        "attempt_id": str(uuid4()),
        "action_id": str(uuid4()),
        "contract_sha256": digest(b"fixed acceptance contract"),
        "template_sha256": template_hash,
        "template": supplied,
    }
    request_path = root / "output/request.json"
    request_path.write_bytes(encoded(request))
    before = inventory(root)
    result = subprocess.run(  # noqa: S603 - fixed validator; invalid inputs must refuse before native launch.
        [
            str(Path(sys.executable).resolve()),
            "-I",
            "-B",
            "-X",
            "pycache_prefix=" + str(root / "output/runtime/python-cache"),
            str(Path(worker.__file__).resolve()),
            "--request",
            str(request_path),
            "--template",
            str(template_path),
            "--template-sha256",
            template_hash,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert error in result.stderr, result.stderr
    assert result.stdout == ""
    assert inventory(root) == before
    assert {path.name for path in (root / "output").iterdir()} == {"request.json"}
