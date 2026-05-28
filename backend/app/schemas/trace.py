from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import Field

from backend.app.schemas.base import CamelModel


class AgentName(str, Enum):
    orchestrator = "orchestrator"
    data = "data"
    ppt = "ppt"
    excel = "excel"
    report = "report"
    sandbox = "sandbox"
    judge = "judge"


class TraceStatus(str, Enum):
    started = "started"
    completed = "completed"
    failed = "failed"
    retrying = "retrying"
    skipped = "skipped"


class TraceEvent(CamelModel):
    id: str
    agent: AgentName
    status: TraceStatus
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    elapsed_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
