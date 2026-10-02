"""Collect the independently frozen CLI diagnostics controls without editing them."""

import hashlib
import json
import runpy
from pathlib import Path

_PACKET = Path(__file__).resolve().parents[2] / "plans/acceptance/core-diagnostics-20261001"
_MANIFESTS = {
    "FROZEN.json": "f0807e6b99c66c7a904e0b887c8a46a1150ed2c104052e83c8a707ea5e86ace3",
    "LIVE-QUALIFICATION-AMENDMENT.json": (
        "5c13c2c580b1c3e1faa40ba6ae55f1a4d30072e1e9060a73a94b5eb74675bd7f"
    ),
}
for _name, _expected in _MANIFESTS.items():
    _manifest = _PACKET / _name
    assert hashlib.sha256(_manifest.read_bytes()).hexdigest() == _expected
    for _row in json.loads(_manifest.read_bytes())["files"]:
        assert hashlib.sha256((_PACKET / _row["path"]).read_bytes()).hexdigest() == _row["sha256"]

for _file in ("test_core_diagnostics.py", "test_live_qualification_overlay.py"):
    _namespace = runpy.run_path(str(_PACKET / _file))
    globals().update(
        {
            name: value
            for name, value in _namespace.items()
            if name.startswith("test_") or name == "isolated"
        }
    )

# Independent amendment replaces only this implementation-seam assertion.
# The original frozen file and historical outcomes remain intact.
_amendment = _PACKET.parent / "core-status-20261001/STATUS-SEAM-AMENDMENT.json"
assert hashlib.sha256(_amendment.read_bytes()).hexdigest() == (
    "cf48d913c45340290b555372e45071e77ed008c89d80b842fc3389efa21d2587"
)
del globals()[json.loads(_amendment.read_bytes())["obsolete_case"]]
