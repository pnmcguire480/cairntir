"""Version only the prior verifier byte expectations and local data routing."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent
PREVIOUS = ROOT / "originals/boundary"
SUPPORT = """\n_SUPPORT_SPEC = importlib.util.spec_from_file_location(
    "followup_amendment_support", PACKET / "amendment_support.py"
)
assert _SUPPORT_SPEC is not None and _SUPPORT_SPEC.loader is not None
_SUPPORT = importlib.util.module_from_spec(_SUPPORT_SPEC)
_SUPPORT_SPEC.loader.exec_module(_SUPPORT)
"""


def write(name, text):
    path = ROOT / name
    if path.exists():
        raise FileExistsError(path)
    path.write_text(text, encoding="utf-8", newline="\n")


def main():
    portability = (PREVIOUS / "test_portability_v3.py").read_text()
    portability = portability.replace(
        'ROOT = Path(__file__).resolve().parent / "originals/portability"',
        "PACKET = Path(__file__).resolve().parent\n"
        'ROOT = PACKET / "originals/boundary/originals/portability"',
    )
    portability = portability.replace(
        'CANDIDATE = Path(os.environ["MANAGED_PORTABILITY_CANDIDATE"]).resolve()',
        'CANDIDATE = Path(os.environ["MANAGED_PORTABILITY_CANDIDATE"]).resolve() '
        'if os.environ.get("MANAGED_PORTABILITY_CANDIDATE") else PACKET.parents[2]',
    )
    portability = portability.replace("BASELINE = json.loads", SUPPORT + "\nBASELINE = json.loads")
    start = portability.index("            original = original.replace(")
    end = portability.index("            expected = hashlib.sha256(original).hexdigest()", start)
    portability = (
        portability[:start]
        + "            original = _SUPPORT.expected_verifier(original)\n"
        + portability[end:]
    )
    write("test_portability_v4.py", portability)
    boundary = (PREVIOUS / "test_installed_boundary_v3.py").read_text()
    boundary = boundary.replace(
        "ROOT = Path(__file__).resolve().parent",
        'PACKET = Path(__file__).resolve().parent\nROOT = PACKET / "originals/boundary"',
    ).replace("CANDIDATE = ROOT.parents[2]", "CANDIDATE = PACKET.parents[2]")
    boundary = boundary.replace(
        '_PORTABILITY = load(ROOT / "test_portability_v3.py", "installed_portability_v3")',
        '_SUPPORT = load(PACKET / "amendment_support.py", "followup_amendment_support")\n'
        '_PORTABILITY = load(PACKET / "test_portability_v4.py", "installed_portability_v4")',
    )
    start = boundary.index("    expected = original.replace(")
    end = boundary.index("    current = (CANDIDATE", start)
    boundary = (
        boundary[:start] + "    expected = _SUPPORT.expected_verifier(original)\n" + boundary[end:]
    )
    write("test_installed_boundary_v4.py", boundary)


if __name__ == "__main__":
    main()
