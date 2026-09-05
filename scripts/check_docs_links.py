"""Check maintained Markdown links without crawling external sites or lineage."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPO_ROOT = Path(__file__).resolve().parent.parent
_LOCAL_GITHUB = "https://github.com/pnmcguire480/cairntir/"
_LINK = re.compile(r"\]\((<[^>]+>|[^\s)]+)(?:\s+\"[^\"]*\")?\)")


def missing_links(root: Path) -> list[str]:
    """Return broken local targets in maintained documentation."""
    documents = list(root.glob("*.md"))
    for directory in ("docs", "plans", "commands", "addons", ".github"):
        documents.extend((root / directory).rglob("*.md"))
    failures: list[str] = []
    for document in sorted(documents):
        text = document.read_text(encoding="utf-8")
        text = re.sub(r"(?ms)^(`{3,}|~{3,}).*?^\1\s*$", "", text)
        for match in _LINK.finditer(text):
            target = match.group(1).strip("<>")
            base = document.parent
            for prefix in (f"{_LOCAL_GITHUB}blob/main/", f"{_LOCAL_GITHUB}tree/main/"):
                if target.startswith(prefix):
                    target = target.removeprefix(prefix)
                    base = root
                    break
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            if not (base / unquote(parsed.path)).exists():
                failures.append(f"{document.relative_to(root).as_posix()}: {target}")
    return failures


def main() -> int:
    """Fail the build on broken local documentation links."""
    failures = missing_links(REPO_ROOT)
    for failure in failures:
        print(f"BROKEN: {failure}", file=sys.stderr)
    if not failures:
        print("ok: maintained documentation links resolve")
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
