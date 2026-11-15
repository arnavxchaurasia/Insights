from pathlib import Path

from app.db import make_engine, prepare_sqlite_dir


def test_prepare_sqlite_dir_creates_parent_for_file_sqlite(tmp_path: Path):
    db_path = tmp_path / "nested" / "dir" / "app.db"
    assert not db_path.parent.exists()
    created = prepare_sqlite_dir(f"sqlite:///{db_path.as_posix()}")
    assert created is True
    assert db_path.parent.is_dir()


def test_prepare_sqlite_dir_noop_for_memory_sqlite():
    assert prepare_sqlite_dir("sqlite://") is False


def test_prepare_sqlite_dir_noop_for_postgres_without_connecting():
    # A Postgres URL must not trigger any filesystem/directory work. This also
    # proves the guard never touches the network: no connection is opened here.
    assert prepare_sqlite_dir("postgresql+psycopg://user:pass@db.example:5432/mi") is False


def test_make_engine_sqlite_has_no_pool_pre_ping():
    engine = make_engine("sqlite://")
    assert engine.pool._pre_ping is False
    assert engine.dialect.name == "sqlite"


def test_make_engine_postgres_enables_pool_pre_ping_without_connecting():
    # create_engine is lazy — it builds the engine but opens no connection,
    # so this stays offline while still exercising the Postgres branch.
    engine = make_engine("postgresql+psycopg://user:pass@db.example:5432/mi")
    assert engine.pool._pre_ping is True
    assert engine.dialect.name == "postgresql"
