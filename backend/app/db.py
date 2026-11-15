from collections.abc import Iterator
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


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


def init_db(engine: Engine) -> None:
    """Create all tables and ensure columns like cluster_id exist on existing databases."""
    Base.metadata.create_all(engine)
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "articles" in inspector.get_table_names():
        cols = {col["name"] for col in inspector.get_columns("articles")}
        if "cluster_id" not in cols:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE articles ADD COLUMN cluster_id VARCHAR(64)"))
                conn.commit()


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
