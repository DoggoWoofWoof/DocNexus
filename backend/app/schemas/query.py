from enum import Enum
from typing import Any, Literal

from pydantic import Field

from backend.app.schemas.artifact import ArtifactRef, ArtifactType, ArtifactValidationResult
from backend.app.schemas.base import CamelModel
from backend.app.schemas.trace import TraceEvent


class VolumeTier(str, Enum):
    low = "low"
    high = "high"
    very_high = "very_high"


class QueryPreferences(CamelModel):
    icd10_codes: list[str] = Field(default_factory=list)
    states: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    specialties: list[str] = Field(default_factory=list)
    volume_threshold: VolumeTier | None = None
    board_certified: bool | None = None


class QueryRequest(CamelModel):
    query: str = Field(min_length=3, max_length=2000)
    preferences: QueryPreferences = Field(default_factory=QueryPreferences)
    requested_artifacts: list[ArtifactType] = Field(default_factory=list)
    include_trace: bool = True


class JudgeStatus(str, Enum):
    approved = "approved"
    needs_revision = "needs_revision"
    failed_after_retry = "failed_after_retry"


class JudgeScores(CamelModel):
    relevance: int = Field(default=0, ge=0, le=100)
    completion: int = Field(default=0, ge=0, le=100)
    grounding: int = Field(default=0, ge=0, le=100)
    artifact_quality: int = Field(default=0, ge=0, le=100)
    preference_alignment: int = Field(default=0, ge=0, le=100)
    overall: int = Field(default=0, ge=0, le=100)


class JudgeDecision(CamelModel):
    status: JudgeStatus
    reason: str
    scores: JudgeScores = Field(default_factory=JudgeScores)
    critical_failures: list[str] = Field(default_factory=list)
    target_agent: str | None = None
    revision_instructions: str | None = None


class SandboxOutput(CamelModel):
    code: str
    stdout: str = ""
    stderr: str = ""
    chart_artifact_id: str | None = None
    execution_status: Literal["completed", "failed"] = "completed"


class QueryResponse(CamelModel):
    request_id: str
    query: str
    answer_markdown: str | None = None
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    artifact_validations: list[ArtifactValidationResult] = Field(default_factory=list)
    sandbox_output: SandboxOutput | None = None
    trace: list[TraceEvent] = Field(default_factory=list)
    judge_decision: JudgeDecision | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
