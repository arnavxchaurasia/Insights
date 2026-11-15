from collections.abc import Iterator
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import BACKEND_DIR, settings


def prepare_sqlite_dir(database_url: str) -> bool:
    """Ensure a file-based SQLite database's parent directory exists.

    Returns True when a directory was prepared (a file-backed SQLite URL).
    A no-op — returning False — for in-memory SQLite and for every other
    backend (e.g. Postgres), whose storage is managed by the server, not us.
    """
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite" and url.database not in (None, "", ":memory:"):
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        return True
    return False


def make_engine(database_url: str) -> Engine:
    """Create the SQLAlchemy engine for a database URL.

    For non-SQLite backends (Postgres in production) we enable `pool_pre_ping`
    so a connection dropped by the server or a pooler is detected and replaced
    instead of surfacing as a stale-connection error on the next request.
    """
    kwargs: dict[str, Any] = {}
    if make_url(database_url).get_backend_name() != "sqlite":
        kwargs["pool_pre_ping"] = True
    return create_engine(database_url, **kwargs)


prepare_sqlite_dir(settings.database_url)
engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def run_migrations(database_url: str | None = None) -> None:
    """Run Alembic migrations up to head against the target database."""
    from alembic.config import Config
    from sqlalchemy import inspect

    from alembic import command

    target_url = database_url or settings.database_url
    prepare_sqlite_dir(target_url)

    alembic_ini_path = BACKEND_DIR / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", target_url)
    alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))

    # If the database already has tables from pre-Alembic runs but no alembic_version,
    # stamp it with the baseline revision so upgrade head applies subsequent migrations.
    eng = make_engine(target_url)
    inspector = inspect(eng)
    table_names = set(inspector.get_table_names())
    if "sources" in table_names and "alembic_version" not in table_names:
        command.stamp(alembic_cfg, "65b6f5261d25")

    command.upgrade(alembic_cfg, "head")


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
