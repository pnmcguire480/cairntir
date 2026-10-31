import sqlite3
import sys


def main(arguments: list[str]) -> int:
    operation, filename, *values = arguments
    with sqlite3.connect(filename) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS counter (value INTEGER NOT NULL)"
        )
        if operation == "write":
            connection.execute("DELETE FROM counter")
            connection.execute("INSERT INTO counter VALUES (?)", (int(values[0]),))
        elif operation == "read":
            row = connection.execute("SELECT value FROM counter").fetchone()
            print(row[0] if row is not None else "missing")
        else:
            raise ValueError(operation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
