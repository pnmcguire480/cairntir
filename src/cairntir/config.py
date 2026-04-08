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


def cairntir_home() -> Path:
    """Return the Cairntir home directory, creating it if it does not exist."""
    env = os.environ.get("CAIRNTIR_HOME")
    home = Path(env) if env else Path(user_data_dir(_APP_NAME, appauthor=False))
    home.mkdir(parents=True, exist_ok=True)
    return home


def db_path() -> Path:
    """Return the absolute path to the sqlite-vec database file."""
    return cairntir_home() / _DB_FILENAME
