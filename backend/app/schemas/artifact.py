from enum import Enum
from typing import Any

from pydantic import Field

from backend.app.schemas.base import CamelModel


class ArtifactType(str, Enum):
    pptx = "pptx"
    xlsx = "xlsx"
    docx = "docx"
    markdown = "markdown"
    chart_png = "chart_png"
    chart_svg = "chart_svg"


class ArtifactRef(CamelModel):
    id: str
    type: ArtifactType
    filename: str
    mime_type: str
    download_url: str
    source_agent: str
    request_id: str | None = None
    tool_call_id: str | None = None
    prompt_name: str | None = None
    prompt_sha256: str | None = None
    input_sha256: str | None = None
    artifact_sha256: str | None = None
    file_size_bytes: int | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class ArtifactValidationCheck(CamelModel):
    name: str
    passed: bool
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactValidationResult(CamelModel):
    artifact_id: str
    artifact_type: ArtifactType
    source_agent: str
    passed: bool
    score: int
    checks: list[ArtifactValidationCheck] = Field(default_factory=list)
