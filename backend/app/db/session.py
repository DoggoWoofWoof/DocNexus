from collections.abc import Generator

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from backend.app.core.config import Settings, get_settings


def _connect_args(settings: Settings) -> dict[str, bool]:
    if settings.is_sqlite:
        return {"check_same_thread": False}
    return {}


settings = get_settings()
engine: Engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args=_connect_args(settings),
)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)
    _ensure_artifact_columns()


def _ensure_artifact_columns() -> None:
    if not settings.is_sqlite:
        return

    inspector = inspect(engine)
    if "artifacts" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("artifacts")}
    migrations = {
        "request_id": "ALTER TABLE artifacts ADD COLUMN request_id VARCHAR",
        "tool_call_id": "ALTER TABLE artifacts ADD COLUMN tool_call_id VARCHAR",
        "prompt_name": "ALTER TABLE artifacts ADD COLUMN prompt_name VARCHAR",
        "prompt_sha256": "ALTER TABLE artifacts ADD COLUMN prompt_sha256 VARCHAR",
        "input_sha256": "ALTER TABLE artifacts ADD COLUMN input_sha256 VARCHAR",
        "artifact_sha256": "ALTER TABLE artifacts ADD COLUMN artifact_sha256 VARCHAR",
        "file_size_bytes": "ALTER TABLE artifacts ADD COLUMN file_size_bytes INTEGER",
        "provenance": "ALTER TABLE artifacts ADD COLUMN provenance JSON DEFAULT '{}'",
    }
    with engine.begin() as connection:
        for column_name, statement in migrations.items():
            if column_name not in existing_columns:
                connection.execute(text(statement))


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
