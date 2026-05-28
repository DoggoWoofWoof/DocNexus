from collections.abc import Generator

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


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
