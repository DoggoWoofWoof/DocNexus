from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from backend.app.api.routes_artifacts import router as artifacts_router
from backend.app.api.routes_health import router as health_router
from backend.app.api.routes_physicians import router as physicians_router
from backend.app.api.routes_query import router as query_router
from backend.app.core.config import get_settings
from backend.app.db.seed import seed_physicians
from backend.app.db.session import create_db_and_tables, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.resolved_artifact_dir.mkdir(parents=True, exist_ok=True)
    create_db_and_tables()

    with Session(engine) as session:
        app.state.seeded_physicians = seed_physicians(session)

    yield


def create_app() -> FastAPI:
    settings = get_settings()
    allowed_origins = {
        settings.frontend_origin,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    }
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Multi-agent physician intelligence artifact generation API.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(physicians_router)
    app.include_router(query_router)
    app.include_router(artifacts_router)
    return app


app = create_app()
