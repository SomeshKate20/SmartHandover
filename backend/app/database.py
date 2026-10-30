from collections.abc import Generator
import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./digiplus.db")


def ensure_sqlite_directory() -> None:
    """Create the configured SQLite parent directory before opening the database."""
    url = make_url(DATABASE_URL)
    if not url.drivername.startswith("sqlite") or not url.database or url.database == ":memory:":
        return
    Path(url.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


ensure_sqlite_directory()
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_task_assignee_column() -> None:
    with engine.begin() as connection:
        if "tasks" not in inspect(connection).get_table_names():
            return
        columns = {column["name"] for column in inspect(connection).get_columns("tasks")}
        if "assignee_clerk_id" not in columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN assignee_clerk_id VARCHAR(255)"))
