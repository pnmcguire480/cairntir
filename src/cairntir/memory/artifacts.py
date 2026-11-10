"""Portable byte identity for locally resolved FastEmbed assets."""

from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import stat
from pathlib import Path
from typing import Any

from cairntir.errors import EmbeddingError

_REQUIRED = {"config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json"}


class MissingArtifactsError(EmbeddingError):
    """Absent assets that explicit first-use acquisition may populate."""


def _asset_path(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or ":" in value
        or "\x00" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise EmbeddingError(f"invalid embedding asset path: {value!r}")
    return value


def _file_entry(root: Path, name: str) -> dict[str, Any]:
    try:
        roots = [root]
        repository = root.parent.parent
        if root.parent.name == "snapshots" and repository.name.startswith("models--"):
            blobs = (repository / "blobs").resolve()
            if blobs.is_relative_to(repository):
                roots.append(blobs)
        path = (root / name).resolve()
        if not any(path.is_relative_to(allowed) for allowed in roots):
            raise EmbeddingError(f"embedding asset escapes its model directory: {name}")
        if not stat.S_ISREG(path.stat().st_mode):
            raise EmbeddingError(f"embedding asset is not an ordinary file: {name}")
        size = 0
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                size += len(chunk)
                digest.update(chunk)
        return {"path": name, "size_bytes": size, "sha256": digest.hexdigest()}
    except FileNotFoundError as exc:
        raise MissingArtifactsError(f"missing embedding asset {name!r} beneath {root}") from exc
    except (OSError, RuntimeError) as exc:
        raise EmbeddingError(f"cannot read embedding asset {name!r} beneath {root}: {exc}") from exc


class PinnedArtifacts:
    """One resolved model directory and the immutable identity of its consumed files."""

    def __init__(self, model_name: str) -> None:
        """Resolve and hash existing assets without constructing an inference model."""
        from cairntir.config import model_cache_dir
        from cairntir.memory.embeddings import _cached_fastembed_model

        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise EmbeddingError("fastembed is not installed; reinstall core dependencies") from exc
        try:
            self.cache = model_cache_dir(create=False).resolve()
            descriptions = TextEmbedding.list_supported_models()
            description = next(
                (
                    item
                    for item in descriptions
                    if str(item["model"]).casefold() == model_name.casefold()
                ),
                None,
            )
        except (OSError, RuntimeError, AttributeError, KeyError, TypeError) as exc:
            raise EmbeddingError(f"cannot resolve embedding registry/cache: {exc}") from exc
        if description is None:
            raise EmbeddingError(f"unsupported embedding model {model_name!r}")
        model_file = _asset_path(description.get("model_file"))
        dimension = description.get("dim")
        if type(dimension) is not int or dimension < 1:
            raise EmbeddingError("embedding registry must declare a positive integer dimension")
        additional = description.get("additional_files", [])
        if not isinstance(additional, list):
            raise EmbeddingError("embedding additional_files must be an asset path list")
        names = sorted(_REQUIRED | {model_file} | {_asset_path(name) for name in additional})
        try:
            runtime = {
                name: importlib.metadata.version(name)
                for name in ("fastembed", "onnxruntime", "tokenizers", "numpy")
            }
        except importlib.metadata.PackageNotFoundError as exc:
            raise EmbeddingError(f"embedding runtime version is unavailable: {exc}") from exc
        if any(not isinstance(value, str) or not value.strip() for value in runtime.values()):
            raise EmbeddingError("embedding runtime versions must be nonempty strings")
        if not self.cache.is_dir():
            if self.cache.exists():
                raise EmbeddingError(f"embedding cache is not a directory: {self.cache}")
            raise MissingArtifactsError(
                f"embedding requires an existing local model cache: {self.cache}"
            )
        try:
            self.root = _cached_fastembed_model(model_name, self.cache).resolve(strict=True)
        except FileNotFoundError as exc:
            raise MissingArtifactsError(f"embedding model directory is unavailable: {exc}") from exc
        except (OSError, RuntimeError, KeyError, TypeError, AttributeError, UnicodeError) as exc:
            raise EmbeddingError(f"embedding model directory is unavailable: {exc}") from exc
        if not self.root.is_relative_to(self.cache) or not self.root.is_dir():
            raise EmbeddingError(
                "embedding model directory is invalid or escapes the configured cache"
            )
        entries = []
        missing: MissingArtifactsError | None = None
        for name in names:
            try:
                entries.append(_file_entry(self.root, name))
            except MissingArtifactsError as exc:
                # Absence must not mask a later invalid path/type in this snapshot.
                missing = exc
        if missing is not None:
            raise missing
        self._manifest: dict[str, Any] = {
            "schema": "cairntir.embedding-artifacts.v1",
            "model": str(description["model"]),
            "dimension": dimension,
            "model_file": model_file,
            "files": entries,
            "pipeline": "fastembed.TextEmbedding/defaults-v1",
            "runtime": runtime,
        }
        raw = json.dumps(
            self._manifest,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        self.identity = f"fastembed/text-embedding-v2/sha256={hashlib.sha256(raw).hexdigest()}"
        self.dimension = dimension

    def manifest(self) -> dict[str, Any]:
        """Return a detached copy, never the internal manifest."""
        return copy.deepcopy(self._manifest)

    def verify(self) -> None:
        """Rehash immediately before loading, without resolving mutable refs again."""
        for entry in self._manifest["files"]:
            if _file_entry(self.root, entry["path"]) != entry:
                raise EmbeddingError(f"pinned embedding asset changed: {entry['path']}")
