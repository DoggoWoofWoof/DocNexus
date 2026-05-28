from enum import Enum

from pydantic import Field

from backend.app.schemas.base import CamelModel
from backend.app.schemas.physician import PhysicianRead


class ToolName(str, Enum):
    get_physician_data = "get_physician_data"
    call_ppt_agent = "call_ppt_agent"
    call_excel_agent = "call_excel_agent"
    call_report_agent = "call_report_agent"
    call_sandbox_agent = "call_sandbox_agent"


class GetPhysicianDataArgs(CamelModel):
    specialty: list[str] = Field(default_factory=list)
    state: list[str] = Field(default_factory=list)
    region: list[str] = Field(default_factory=list)
    icd10_codes: list[str] = Field(default_factory=list)
    volume_threshold: str | None = None
    board_certified: bool | None = None


class PptAgentArgs(CamelModel):
    topic: str
    physician_list: list[PhysicianRead] = Field(default_factory=list)
    icd10_codes: list[str] = Field(default_factory=list)
    slide_count: int = Field(default=4, ge=1, le=12)
    style_notes: str | None = None
    revision_instructions: str | None = None


class ExcelAgentArgs(CamelModel):
    analysis_type: str
    physician_list: list[PhysicianRead] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    icd10_codes: list[str] = Field(default_factory=list)
    revision_instructions: str | None = None


class ReportAgentArgs(CamelModel):
    report_type: str
    sections: list[str] = Field(default_factory=list)
    physician_list: list[PhysicianRead] = Field(default_factory=list)
    icd10_context: list[str] = Field(default_factory=list)
    geographic_scope: list[str] = Field(default_factory=list)
    revision_instructions: str | None = None


class SandboxAgentArgs(CamelModel):
    code_goal: str
    dataset: list[dict[str, object]] = Field(default_factory=list)
    chart_type: str | None = None
    revision_instructions: str | None = None


class ToolCallRecord(CamelModel):
    name: ToolName
    arguments: dict[str, object]
    reason: str
