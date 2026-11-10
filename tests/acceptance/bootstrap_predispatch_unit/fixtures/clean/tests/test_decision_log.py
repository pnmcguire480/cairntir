import pytest
from decision_log import DecisionLog


def test_reversal_preserves_history_but_changes_current_decision() -> None:
    log = DecisionLog()
    postgres = log.record("db-1", "database", "Postgres")
    sqlite = log.record("db-2", "database", "SQLite", supersedes_id=postgres.id)

    assert log.history("database") == (postgres, sqlite)
    assert postgres.choice == "Postgres"
    assert sqlite.supersedes_id == postgres.id
    assert log.current("database") == (sqlite,)


def test_successive_reversals_do_not_change_other_topics() -> None:
    log = DecisionLog()
    postgres = log.record("db-1", "database", "Postgres")
    auth = log.record("auth-1", "authentication", "Passkeys")
    sqlite = log.record("db-2", "database", "SQLite", supersedes_id=postgres.id)
    duckdb = log.record("db-3", "database", "DuckDB", supersedes_id=sqlite.id)

    assert log.history("database") == (postgres, sqlite, duckdb)
    assert log.current("database") == (duckdb,)
    assert log.current("authentication") == (auth,)


def test_reversal_requires_known_current_decision_in_same_topic() -> None:
    log = DecisionLog()
    postgres = log.record("db-1", "database", "Postgres")
    auth = log.record("auth-1", "authentication", "Passkeys")

    with pytest.raises(ValueError, match="same topic"):
        log.record("db-2", "database", "SQLite", supersedes_id="missing")
    with pytest.raises(ValueError, match="same topic"):
        log.record("db-2", "database", "SQLite", supersedes_id=auth.id)

    log.record("db-2", "database", "SQLite", supersedes_id=postgres.id)
    with pytest.raises(ValueError, match="already superseded"):
        log.record("db-3", "database", "DuckDB", supersedes_id=postgres.id)
    with pytest.raises(ValueError, match="duplicate"):
        log.record("db-2", "database", "MySQL")

    assert len(log.history("database")) == 2
