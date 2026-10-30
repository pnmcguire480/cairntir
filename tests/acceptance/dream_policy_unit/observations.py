"""Original JSON and SQLite observations for fixed synthetic policy tables."""

import json
import sqlite3
from contextlib import closing


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf8")


def rows(path, table):
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        return [
            {k: ({"hex": v.hex()} if isinstance(v, bytes) else v) for k, v in dict(row).items()}
            for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid')  # noqa: S608 - Fixed original table list.
        ]
