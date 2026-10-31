import os
import platform
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from .oracle import PACKET, canonical, digest, read_json, semantic_status
from .unit_png import encode


def materialize(run, tools):
    root = run["output"]
    request = read_json(root / "request.json", 262144)
    template = request["template"]
    for relative in ("operations", "runtime", "producer"):
        (root / relative).mkdir()
    raw_paths = []

    def reference(relative):
        path = root / relative
        return {"path": relative, "bytes": path.stat().st_size, "sha256": digest(path.read_bytes())}

    def write(relative, value, raw=False):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else canonical(value))
        if raw:
            raw_paths.append(relative)
        return reference(relative)

    def tool(name):
        return next(item for item in tools["tools"] if item["id"] == name)

    def observation(name):
        row = tool(name)
        entry = Path(row["root"]) / row["entry_path"]
        return {
            "id": name,
            "entry_path": str(entry),
            "entry_sha256": digest(entry.read_bytes()),
            "version": row["version"],
        }

    visual_check = next(check for check in template["checks"] if check["kind"] == "rgba-diff")
    visual_policy = {
        key: value for key, value in visual_check.items() if key not in ("id", "kind", "family")
    }
    policy = {"render_policy": template["render_policy"], "visual_policy": visual_policy}
    policy_sha = digest(canonical(policy))
    font = template["render_policy"]["font"]
    renderer = {
        "browser": {
            "runtime_manifest_sha256": digest(canonical(tool("chrome")["files"])),
            "version": tool("chrome")["version"],
        },
        "os": {
            "platform": "win32" if os.name == "nt" else platform.system().lower(),
            "release": platform.release(),
            "arch": "x64"
            if platform.machine().lower() in ("amd64", "x86_64")
            else platform.machine(),
        },
        "font": {
            "file_sha256": font["sha256"],
            "custom_family": font["platform_family"],
            "postscript_name": font["postscript_name"],
        },
        "pngjs": {
            "payload_sha256": digest(canonical(tool("pngjs")["files"])),
            "version": tool("pngjs")["version"],
        },
        "pixelmatch": {
            "payload_sha256": digest(canonical(tool("pixelmatch")["files"])),
            "version": tool("pixelmatch")["version"],
        },
        "policy_sha256": policy_sha,
    }
    identities = {
        key: request[key]
        for key in ("run_id", "attempt_id", "action_id", "contract_sha256", "template_sha256")
    }
    identities["request_sha256"] = digest(canonical(request))
    argv = [
        str(Path(tool("node")["root"]) / tool("node")["entry_path"]),
        str(Path(tool("producer")["root"]) / tool("producer")["entry_path"]),
        "--request",
        str(root / "request.json"),
    ]
    started = datetime.now(UTC).isoformat()
    prefix = root / "runtime/python-cache"
    python = {
        **observation("python"),
        "isolated": True,
        "dont_write_bytecode": True,
        "optimize": 0,
        "pycache_prefix": str(prefix),
        "cache_prefix_state": "ABSENT",
    }
    ownership = {
        "schema": "cairntir.paladin-ui-ownership.v1",
        "phase": "START",
        **identities,
        "argv": argv,
        "cwd": template["project"]["snapshot_root"],
        "started_at": started,
        "finished_at": None,
        "timeout_seconds": 120,
        "elapsed_seconds": 0.0,
        "python": python,
        "worker": observation("worker"),
        "pid": os.getpid(),
        "direct_process_handle": 1,
        "job_handle": 2,
        "suspended_creation": True,
        "assigned_owned_job": True,
        "direct_exit_code": None,
        "timed_out": False,
        "cancelled": False,
        "output_truncated": False,
        "job_total_processes": 1,
        "job_active_processes": 1,
        "owned_tree_exit_observed": False,
        "job_handle_closed": False,
        "direct_process_handle_closed": False,
        "cleanup_uncertain": False,
        "errors": [],
    }
    write("operations/OWNERSHIP-START.json", ownership)
    environment = {
        "values": {
            key: str(root / "runtime" / key.lower())
            for key in (
                "HOME",
                "USERPROFILE",
                "APPDATA",
                "LOCALAPPDATA",
                "TEMP",
                "TMP",
                "XDG_CONFIG_HOME",
                "XDG_CACHE_HOME",
                "XDG_DATA_HOME",
            )
        },
        "absent": [
            "NODE_OPTIONS",
            "NODE_PATH",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "NO_PROXY",
            "PLAYWRIGHT_DOWNLOAD_HOST",
            "CAIRNTIR_HOME",
            "CAIRNTIR_GRANT_FILE",
        ],
    }
    environment["values"]["PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"] = "1"
    for key, value in environment["values"].items():
        if key != "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD":
            Path(value).mkdir()
    limits = read_json(PACKET / "contract/PRODUCER-SCHEMAS.json")["$defs"]["limits"]["const"]
    write(
        "operations/INVOCATION.json",
        {
            "schema": "cairntir.paladin-ui-invocation.v1",
            **identities,
            "selected_tools_sha256": template["selected_tools"]["sha256"],
            "argv": argv,
            "cwd": template["project"]["snapshot_root"],
            "environment_controls": environment,
            "limits": limits,
        },
    )
    network = []
    viewports = []
    for viewport in template["render_policy"]["viewports"]:
        name, width, height = viewport["id"], viewport["width"], viewport["height"]
        base = "producer/raw/" + name + "/"
        checks = template["checks"]
        selectors = []
        for check in checks:
            for key in ("selector", "start_selector", "control", "panel"):
                if key in check and check[key] not in selectors:
                    selectors.append(check[key])
            for key in ("selectors", "expected_focus"):
                for value in check.get(key, []):
                    if value not in selectors:
                        selectors.append(value)
        for selector in font["text_selectors"]:
            if selector not in selectors:
                selectors.append(selector)
        dom_rows, mappings, ax_nodes = [], [], []
        dom_map = {}
        for index, selector in enumerate(selectors, 1):
            visible = selector != "#details"
            element = {
                "node_id": index,
                "backend_node_id": 100 + index,
                "tag_name": (
                    "BODY"
                    if selector == "body"
                    else "INPUT"
                    if selector == "#email"
                    else "BUTTON"
                    if selector in ("#submit", "#details-toggle")
                    else "DIV"
                ),
                "id": selector.removeprefix("#") if selector != "body" else "",
                "text_content": "SYNTHETIC UNIT TEXT",
                "rect": {
                    "x": 24,
                    "y": 30 + index * 24,
                    "width": min(260, width - 48),
                    "height": 20,
                },
                "visible": visible,
                "display": "block" if visible else "none",
                "visibility": "visible",
                "opacity": 1,
                "font_family": font["css_family"],
            }
            if not visible:
                element["rect"] = {"x": 0, "y": 0, "width": 0, "height": 0}
            if run["variant"] == "keyboard-fault" and selector == "#details-toggle":
                element["tag_name"] = "DIV"
            if run["variant"] == "overflow-fault" and name == "mobile" and selector != "body":
                element["rect"]["width"] = 500
            dom_rows.append({"selector": selector, "count": 1, "matches": [element]})
            dom_map[selector] = element
            match = next(
                (
                    check
                    for check in checks
                    if check["kind"] == "ax-role-name" and check["selector"] == selector
                ),
                None,
            )
            role = match["role"] if match else "generic"
            label = match["name"] if match else ""
            if run["variant"] == "name-fault" and selector == "#email":
                label = ""
            node = {
                "nodeId": str(index),
                "ignored": False,
                "backendDOMNodeId": element["backend_node_id"],
                "role": {"type": "role", "value": role},
                "name": {"type": "computedString", "value": label},
            }
            ax_nodes.append(node)
            mappings.append(
                {
                    "selector": selector,
                    "node_ids": [index],
                    "backend_node_ids": [100 + index],
                    "ax_node_ids": [str(index)],
                }
            )
        overflow = 160 if run["variant"] == "overflow-fault" and name == "mobile" else 0
        document = {
            "language": "en",
            "title": "Printer notes",
            "url": "https://cairntir.invalid/index.html",
            "ready_state": "complete",
            "inner_width": width,
            "inner_height": height,
            "device_scale_factor": 1,
            "scroll_width": width + overflow,
            "client_width": width,
            "active_element": {"tag_name": "BODY", "id": ""},
        }
        dom = {
            "schema": "cairntir.paladin-ui-dom.v1",
            "viewport_id": name,
            "document": document,
            "selectors": dom_rows,
        }
        ax = {
            "schema": "cairntir.paladin-ui-ax.v1",
            "viewport_id": name,
            "nodes": ax_nodes,
            "selector_mappings": mappings,
        }
        fonts = [
            {
                "selector": selector,
                "backend_node_id": dom_map[selector]["backend_node_id"],
                "document_fonts_ready": True,
                "font_face_loaded": True,
                "computed_family": font["css_family"],
                "fonts": [
                    {
                        "family_name": font["platform_family"],
                        "postscript_name": font["postscript_name"],
                        "is_custom_font": True,
                        "glyph_count": 20,
                    }
                ],
            }
            for selector in font["text_selectors"]
        ]
        write(base + "dom.json", dom, True)
        write(base + "ax.json", ax, True)
        write(
            base + "fonts.json",
            {
                "schema": "cairntir.paladin-ui-fonts.v1",
                "viewport_id": name,
                "font_path": font["path"],
                "font_sha256": font["sha256"],
                "license_sha256": font["license_sha256"],
                "css_family": font["css_family"],
                "platform_family": font["platform_family"],
                "postscript_name": font["postscript_name"],
                "observations": fonts,
            },
            True,
        )
        current = write(
            base + "current.png",
            encode(
                width,
                height,
                (180, 56, 106, 255) if run["variant"] == "visual-fault" else (242, 245, 250, 255),
            ),
            True,
        )
        baseline, diff = None, None
        total, mismatch, allowed, ratio, exact = 0, None, None, None, None
        if template["mode"] == "compare":
            approved = read_json(template["baseline_reference"]["manifest_file"]["path"])
            source = next(row["png"] for row in approved["images"] if row["viewport_id"] == name)
            baseline = write(base + "baseline.png", Path(source["path"]).read_bytes(), True)
            total = width * height
            mismatch = exact = total if run["variant"] == "visual-fault" else 0
            allowed, ratio = int(total * 0.001), mismatch / total
            diff = write(
                base + "diff.png",
                encode(width, height, (255, 0, 0, 255) if mismatch else (253, 253, 253, 255)),
                True,
            )
        visual = {
            "current": current,
            "baseline": baseline,
            "diff": diff,
            "width": width,
            "height": height,
            "compared_pixels": total,
            "mismatched_pixels": mismatch,
            "exact_changed_pixels": exact,
            "allowed_diff_pixels": allowed,
            "diff_ratio": ratio,
        }
        if baseline is not None:
            write(base + "comparison.json", visual, True)
        rows, events = [], []
        for check in checks:
            kind = check["kind"]
            if kind == "document-equals":
                observed = {"value": document[check["property"]]}
                evidence = [base + "dom.json"]
            elif kind == "ax-role-name":
                mapping = next(item for item in mappings if item["selector"] == check["selector"])
                node = next(
                    item for item in ax_nodes if item["nodeId"] == mapping["ax_node_ids"][0]
                )
                observed = {
                    "selector_count": 1,
                    "backend_node_id": node["backendDOMNodeId"],
                    "ax_node_id": node["nodeId"],
                    "ignored": False,
                    "role": node["role"]["value"],
                    "name": node["name"]["value"],
                }
                evidence = [base + "dom.json", base + "ax.json"]
            elif kind == "keyboard-tab-order":
                steps = [
                    {
                        "key": "Tab",
                        "actual": {
                            "tag_name": dom_map[selector]["tag_name"],
                            "id": dom_map[selector]["id"],
                        },
                        "expected_selector_matches": True,
                    }
                    for selector in check["expected_focus"]
                ]
                observed = {
                    "initial": document["active_element"],
                    "start_matches": True,
                    "steps": steps,
                }
                events.extend(
                    [
                        {
                            "ordinal": len(events) + i + 1,
                            "check_id": check["id"],
                            "key": "Tab",
                            "active_element": step["actual"],
                        }
                        for i, step in enumerate(steps)
                    ]
                )
                evidence = [base + "keyboard.json"]
            elif kind == "keyboard-key-state":
                expanded = check["expanded"] if run["variant"] != "keyboard-fault" else False
                observed = {
                    "actual_focus": {
                        "tag_name": dom_map[check["control"]]["tag_name"],
                        "id": check["control"].removeprefix("#"),
                    },
                    "control_focused": True,
                    "control_count": 1,
                    "panel_count": 1,
                    "expanded": str(expanded).lower(),
                    "panel_visible": expanded,
                }
                events.append(
                    {
                        "ordinal": len(events) + 1,
                        "check_id": check["id"],
                        "key": check["key"],
                        "active_element": observed["actual_focus"],
                    }
                )
                evidence = [base + "keyboard.json"]
            elif kind == "required-visible":
                elements = []
                for selector in check["selectors"]:
                    element = dom_map[selector]
                    rect = element["rect"]
                    inside = (
                        rect["x"] >= -1
                        and rect["y"] >= -1
                        and rect["x"] + rect["width"] <= width + 1
                        and rect["y"] + rect["height"] <= height + 1
                    )
                    elements.append(
                        {
                            "selector": selector,
                            "count": 1,
                            "rect": rect,
                            "visible": True,
                            "within_viewport": inside,
                        }
                    )
                observed, evidence = {"elements": elements}, [base + "dom.json"]
            elif kind == "horizontal-overflow":
                observed = {
                    "scroll_width": width + overflow,
                    "client_width": width,
                    "viewport_width": width,
                    "overflow_css_pixels": overflow,
                }
                evidence = [base + "dom.json"]
            else:
                assert kind == "rgba-diff"
                observed, evidence = (
                    visual,
                    [base + "comparison.json"] if baseline else [base + "current.png"],
                )
            rows.append(
                {
                    "check": deepcopy(check),
                    "status": semantic_status(check, observed, width, height),
                    "observation": observed,
                    "evidence_paths": evidence,
                    "diagnostic": None,
                }
            )
        write(
            base + "keyboard.json",
            {
                "schema": "cairntir.paladin-ui-keyboard.v1",
                "viewport_id": name,
                "initial_active_element": document["active_element"],
                "events": events,
                "results": [row for row in rows if row["check"]["kind"].startswith("keyboard-")],
            },
            True,
        )
        viewports.append(
            {
                "id": name,
                "width": width,
                "height": height,
                "device_scale_factor": 1,
                "checks": rows,
                "font_observations": fonts,
            }
        )
        for project_file in template["project"]["files"]:
            if project_file["path"] in ("index.html", font["path"]):
                network.append(
                    {
                        "ordinal": len(network) + 1,
                        "viewport_id": name,
                        "url": "https://cairntir.invalid/" + project_file["path"],
                        "method": "GET",
                        "resource_type": "font"
                        if project_file["path"] == font["path"]
                        else "document",
                        "decision": "fulfilled",
                        "project_path": project_file["path"],
                        "sha256": project_file["sha256"],
                    }
                )
    write(
        "producer/network.json",
        {"schema": "cairntir.paladin-ui-network.v1", "events": network},
        True,
    )
    families = {}
    for family in ("accessibility", "responsive", "visual"):
        statuses = [
            row["status"]
            for viewport in viewports
            for row in viewport["checks"]
            if row["check"]["family"] == family
        ]
        families[family] = (
            "FAIL" if "FAIL" in statuses else ("UNREVIEWED" if "UNREVIEWED" in statuses else "PASS")
        )
    report = {
        "schema": "cairntir.paladin-ui-producer-result.v1",
        "status": "COMPLETE",
        **identities,
        "mode": template["mode"],
        "project_id": template["project"]["project_id"],
        "current_source_revision": template["project"]["source_revision"],
        "current_snapshot_sha256": template["project"]["snapshot_sha256"],
        "baseline_origin_snapshot_sha256": template["baseline_reference"][
            "baseline_origin_snapshot_sha256"
        ]
        if template["baseline_reference"]
        else None,
        "baseline_reference": template["baseline_reference"],
        "selected_tools_sha256": template["selected_tools"]["sha256"],
        "tool_observations": [
            observation(name)
            for name in ("node", "playwright", "playwright-core", "chrome", "pngjs", "pixelmatch")
        ],
        "policy_sha256": policy_sha,
        "renderer": renderer,
        "renderer_sha256": digest(canonical(renderer)),
        "browser_lifecycle": {
            "context_closed": True,
            "browser_closed": True,
            "disconnected_observed": True,
        },
        "viewports": viewports,
        "families": families,
        "diagnostics": ["SYNTHETIC_UNIT_EVIDENCE"],
        "raw_artifacts": [reference(path) for path in sorted(raw_paths)],
    }
    report_ref = write("producer/ui-result.json", b"{" if run["fault"] == "malformed" else report)
    ownership.update(
        phase="EXIT",
        finished_at=datetime.now(UTC).isoformat(),
        elapsed_seconds=0.01,
        direct_exit_code=1 if run["fault"] == "nonzero" else 0,
        job_active_processes=0,
        owned_tree_exit_observed=True,
        job_handle_closed=True,
        direct_process_handle_closed=True,
    )
    if run["fault"] == "unclosed":
        ownership.update(job_active_processes=1, job_handle_closed=False, cleanup_uncertain=True)
    ownership_ref = write("operations/OWNERSHIP-EXIT.json", ownership)
    write("operations/stdout.txt", b"")
    write("operations/stderr.txt", b"")
    closure_rows = [
        reference(path.relative_to(root).as_posix())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]
    closure_ref = write(
        "operations/CLOSURE.json",
        {
            "schema": "cairntir.paladin-ui-closure.v1",
            **{key: request[key] for key in ("run_id", "attempt_id", "action_id")},
            "request_sha256": identities["request_sha256"],
            "files": closure_rows,
            "file_count": len(closure_rows),
            "total_bytes": sum(row["bytes"] for row in closure_rows),
        },
    )
    summary = {
        "schema": "cairntir.paladin-ui-worker-summary.v1",
        **identities,
        "report": report_ref,
        "ownership": ownership_ref,
        "closure": closure_ref,
    }
    return {
        "exit_code": ownership["direct_exit_code"],
        "stdout": canonical(summary).decode() + "\n",
        "stderr": "SYNTHETIC_UNIT_EVIDENCE",
        "timed_out": False,
        "output_truncated": run["fault"] == "truncated",
        "cleanup_uncertain": run["fault"] == "unclosed",
    }
