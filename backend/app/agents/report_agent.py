import json
import re
from collections.abc import Callable

from sqlmodel import Session

from backend.app.core.config import Settings
from backend.app.schemas.artifact import ArtifactRef, ArtifactType
from backend.app.schemas.physician import PhysicianRead
from backend.app.services.artifacts import finalize_artifact_file, register_artifact, to_artifact_ref
from backend.app.services.prompts import load_prompt


TextGenerator = Callable[[list[dict[str, object]]], str]


def generate_report(
    *,
    session: Session,
    settings: Settings,
    generate_text: TextGenerator,
    report_type: str,
    sections: list[str],
    physicians: list[PhysicianRead],
    icd10_context: list[str],
    geographic_scope: list[str],
    revision_instructions: str | None = None,
    artifact_provenance: dict[str, object] | None = None,
) -> tuple[str, ArtifactRef]:
    prompt = load_prompt("report_agent.md")
    messages: list[dict[str, object]] = [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "reportType": report_type,
                    "sections": sections,
                    "physicianCount": len(physicians),
                    "icd10Context": icd10_context,
                    "geographicScope": geographic_scope,
                    "revisionInstructions": revision_instructions,
                    "physicians": [physician.model_dump(by_alias=True) for physician in physicians],
                }
            ),
        },
    ]
    markdown = generate_text(messages)

    filename = f"{_slugify(report_type or 'physician_report')}.md"
    artifact, path = register_artifact(
        session,
        settings=settings,
        artifact_type=ArtifactType.markdown,
        filename=filename,
        source_agent="report",
        **(artifact_provenance or {}),
    )
    path.write_text(markdown, encoding="utf-8")
    finalize_artifact_file(session, artifact, path)
    return markdown, to_artifact_ref(artifact)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug[:80] or "physician_report"
