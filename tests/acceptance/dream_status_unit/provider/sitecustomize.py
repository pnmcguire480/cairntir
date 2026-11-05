import hashlib
import json
import os
import sys
import traceback
from pathlib import Path

try:
    expected = json.loads(Path(os.environ["DREAM_STATUS_EXPECTED"]).read_bytes())
    import cairntir

    package = Path(cairntir.__file__).resolve().parent
    modules = {
        p.relative_to(package).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(package.rglob("*.py"))
    }
    if package != Path(expected["package"]).resolve() or modules != expected["modules"]:
        raise AssertionError("wrong actual package origin or module bytes")  # noqa: TRY301 - Preserve fatal origin refusal.
    from cairntir.memory import embeddings

    embeddings.production_embedding_provider = lambda: embeddings.HashEmbeddingProvider(32)
    output = Path(os.environ["DREAM_STATUS_IMPORT"])
    output = output.with_name(output.stem + "-" + str(os.getpid()) + ".json")
    with output.open("x", encoding="utf8") as stream:
        json.dump(
            {
                "pid": os.getpid(),
                "parent_pid": os.getppid(),
                "package": str(package),
                "modules": modules,
            },
            stream,
        )
except BaseException:  # noqa: BLE001 - Original shim fails closed on any startup error.
    traceback.print_exc(file=sys.stderr)
    sys.stderr.flush()
    os._exit(79)
