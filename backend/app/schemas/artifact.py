from enum import Enum

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
