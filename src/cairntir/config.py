"""Configuration: resolve Cairntir's home directory and database path.

Precedence: ``CAIRNTIR_HOME`` environment variable → platform user-data dir.
No hardcoded absolute paths — ever.
"""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_data_dir

_APP_NAME = "cairntir"
_DB_FILENAME = "cairntir.db"
_MODEL_DIRNAME = "models"


def cairntir_home() -> Path:
    """Return the Cairntir home directory, creating it if it does not exist."""
    env = os.environ.get("CAIRNTIR_HOME")
    home = Path(env) if env else Path(user_data_dir(_APP_NAME, appauthor=False))
    home.mkdir(parents=True, exist_ok=True)
    return home


def db_path() -> Path:
    """Return the absolute path to the sqlite-vec database file."""
    return cairntir_home() / _DB_FILENAME


def model_cache_dir() -> Path:
    """Return the directory holding the downloaded ONNX embedding model.

    Precedence: ``FASTEMBED_CACHE_PATH`` → ``cairntir_home()/models``.

    Why this exists rather than letting fastembed pick. ``define_cache_dir``
    falls back to ``tempfile.gettempdir()/fastembed_cache`` when
    ``FASTEMBED_CACHE_PATH`` is unset, and a temp directory is *ambient*: a
    login shell and an MCP server launched by a desktop host do not reliably
    resolve the same one. That is not cosmetic. ``cairntir reindex`` would
    download the model to whichever cache its shell resolved, rebuild every
    vector, and stamp the store to that model's 512-dimension space — after
    which the server resolved a *different* cache, found no model, and
    ``HF_HUB_OFFLINE=1`` forbade fetching it. ``_require_embedding_space``
    gates both ``add()`` and ``search()``, so reads and writes failed closed
    and the error told the user to run the very command that had done this.

    Anchoring the cache to :func:`cairntir_home` makes the two agree by the
    same mechanism that already makes them agree about :func:`db_path`. If a
    client can find the database, it can find the model beside it.
    """
    env = os.environ.get("FASTEMBED_CACHE_PATH")
    cache = Path(env) if env else cairntir_home() / _MODEL_DIRNAME
    cache.mkdir(parents=True, exist_ok=True)
    return cache
