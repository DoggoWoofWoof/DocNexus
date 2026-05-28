from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, status
from sqlmodel import Session, select

from backend.app.core.config import Settings
from backend.app.db.models import Artifact
from backend.app.schemas.artifact import ArtifactRef, ArtifactType


MIME_TYPES = {
    ArtifactType.pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ArtifactType.xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ArtifactType.docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ArtifactType.markdown: "text/markdown",
    ArtifactType.chart_png: "image/png",
    ArtifactType.chart_svg: "image/svg+xml",
}


def new_artifact_id() -> str:
    return f"art_{uuid4().hex[:12]}"


def register_artifact(
    session: Session,
    *,
    settings: Settings,
    artifact_type: ArtifactType,
    filename: str,
    source_agent: str,
) -> tuple[Artifact, Path]:
    artifact_id = new_artifact_id()
    artifact_dir = settings.resolved_artifact_dir
    artifact_dir.mkdir(parents=True, exist_ok=True)

    path = artifact_dir / f"{artifact_id}_{filename}"
    artifact = Artifact(
        id=artifact_id,
        type=artifact_type.value,
        filename=filename,
        mime_type=MIME_TYPES[artifact_type],
        local_path=str(path),
        source_agent=source_agent,
    )
    session.add(artifact)
    session.commit()
    session.refresh(artifact)
    return artifact, path


def get_artifact(session: Session, artifact_id: str) -> Artifact:
    artifact = session.exec(select(Artifact).where(Artifact.id == artifact_id)).first()
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact not found: {artifact_id}",
        )
    return artifact


def to_artifact_ref(artifact: Artifact) -> ArtifactRef:
    return ArtifactRef(
        id=artifact.id,
        type=ArtifactType(artifact.type),
        filename=artifact.filename,
        mime_type=artifact.mime_type,
        download_url=f"/artifacts/{artifact.id}",
        source_agent=artifact.source_agent,
    )
