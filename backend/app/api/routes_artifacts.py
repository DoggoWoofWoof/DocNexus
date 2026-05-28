from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlmodel import Session

from backend.app.db.session import get_session
from backend.app.services.artifacts import get_artifact


router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("/{artifact_id}")
def download_artifact(
    artifact_id: str,
    session: Session = Depends(get_session),
) -> FileResponse:
    artifact = get_artifact(session, artifact_id)
    path = Path(artifact.local_path)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact file is missing: {artifact_id}",
        )

    return FileResponse(
        path=path,
        media_type=artifact.mime_type,
        filename=artifact.filename,
    )
