from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlmodel import Session

from backend.app.core.config import Settings, get_settings
from backend.app.db.session import get_session
from backend.app.schemas.health import HealthResponse


router = APIRouter(tags=["health"])


@router.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"service": "DocNexus Agent Orchestrator", "status": "ok"}


@router.get("/health", response_model=HealthResponse)
def health(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    database_status = "ok"
    try:
        session.exec(text("SELECT 1")).one()
    except Exception:
        database_status = "error"

    return HealthResponse(
        service=settings.app_name,
        status="ok" if database_status == "ok" else "degraded",
        environment=settings.app_env,
        database=database_status,
        artifactDir=str(settings.resolved_artifact_dir),
        llmProvider=settings.llm_provider,
        llmModel=settings.mistral_model,
        sandboxProvider=settings.sandbox_provider,
    )
