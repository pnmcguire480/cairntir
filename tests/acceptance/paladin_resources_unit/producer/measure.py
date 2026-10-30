import argparse
import cProfile
import hashlib
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path


def encoded(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def fingerprint(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def identifiers(size):
    return [(index * 17) % size + 1 for index in range(256)]


def expected(size):
    return [f"note-{key:05d}" for key in identifiers(size)]


def child(args):
    spec = importlib.util.spec_from_file_location(
        "q05_subject", args.snapshot / "src/q05_notes/notes.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    connection = sqlite3.connect(args.database.as_uri() + "?mode=ro", uri=True)
    try:
        keys = identifiers(args.size)
        if args.mode == "profile":
            profiler = cProfile.Profile()
            values = profiler.runcall(module.read_batch, connection, keys)
            profiler.dump_stats(args.profile)
            peak = None
        elif args.mode == "allocation":
            tracemalloc.start()
            values = module.read_batch(connection, keys)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        else:
            values = module.read_batch(connection, keys)
            peak = None
        print(json.dumps({"values": values, "python_peak_bytes": peak}))
    finally:
        connection.close()


def parent(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with (output / "launches.jsonl").open("a", encoding="utf-8") as launches:
        datasets = []
        for size in (100, 1000):
            database = output / f"notes-{size}.db"
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT NOT NULL)")
                connection.executemany(
                    "INSERT INTO notes VALUES (?, ?)",
                    [(key, f"note-{key:05d}") for key in range(1, size + 1)],
                )
            oracle = expected(size)
            oracle_hash = fingerprint(oracle)

            def invoke(mode, ordinal):
                argv = [
                    sys.executable, "-I", "-B", str(Path(__file__).resolve()),
                    "--child", "--snapshot", str(args.snapshot.resolve()),
                    "--database", str(database), "--size", str(size), "--mode", mode,
                    "--profile", str(output / f"profile-{size}.prof"),
                ]
                started = time.perf_counter_ns()
                run = subprocess.run(argv, capture_output=True, check=False, timeout=30)
                elapsed = time.perf_counter_ns() - started
                launches.write(json.dumps({"argv": argv, "mode": mode, "size": size,
                                           "ordinal": ordinal, "exit_code": run.returncode}) + "\n")
                launches.flush()
                (output / f"child-{size}-{mode}-{ordinal}.stdout").write_bytes(run.stdout)
                (output / f"child-{size}-{mode}-{ordinal}.stderr").write_bytes(run.stderr)
                if run.returncode:
                    raise RuntimeError(f"workload child failed: {run.returncode}")
                value = json.loads(run.stdout)
                if value["values"] != oracle:
                    raise RuntimeError("FUNCTIONAL_ORACLE")
                return elapsed, value

            for index in range(2):
                invoke("wall", f"warmup-{index}")
            samples = [invoke("wall", index)[0] for index in range(20)]
            _, profiled = invoke("profile", 0)
            _, allocation = invoke("allocation", 0)
            datasets.append({
                "size": size,
                "oracle_sha256": oracle_hash,
                "wall_samples_ns": samples,
                "profile_path": f"profile-{size}.prof",
                "profile_output_sha256": fingerprint(profiled["values"]),
                "allocation_output_sha256": fingerprint(allocation["values"]),
                "python_peak_bytes": allocation["python_peak_bytes"],
            })
        report = {
            "schema": "cairntir.q05-performance.v1",
            "producer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "python": sys.version,
            "pid": os.getpid(),
            "datasets": datasets,
        }
        (output / "report.json").write_text(json.dumps(report, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--size", type=int)
    parser.add_argument("--mode", choices=("wall", "profile", "allocation"))
    parser.add_argument("--profile", type=Path)
    arguments = parser.parse_args()
    child(arguments) if arguments.child else parent(arguments)
