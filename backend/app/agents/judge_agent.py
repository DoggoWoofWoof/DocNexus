import json
from collections.abc import Callable
from typing import Any

from backend.app.schemas.artifact import ArtifactRef, ArtifactValidationResult
from backend.app.schemas.query import JudgeDecision, SandboxOutput
from backend.app.services.prompts import load_prompt


TextGenerator = Callable[[list[dict[str, object]]], str]


def judge_outputs(
    *,
    generate_text: TextGenerator,
    query: str,
    artifacts: list[ArtifactRef],
    artifact_validations: list[ArtifactValidationResult],
    answer_markdown: str | None,
    sandbox_output: SandboxOutput | None,
    tool_calls: list[dict[str, object]],
) -> JudgeDecision:
    prompt = load_prompt("judge_agent.md")
    messages: list[dict[str, object]] = [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "query": query,
                    "artifacts": [artifact.model_dump(by_alias=True) for artifact in artifacts],
                    "artifactValidations": [
                        validation.model_dump(by_alias=True) for validation in artifact_validations
                    ],
                    "hasAnswerMarkdown": bool(answer_markdown),
                    "sandboxOutput": sandbox_output.model_dump(by_alias=True) if sandbox_output else None,
                    "toolCalls": tool_calls,
                }
            ),
        },
    ]
    raw = _strip_code_fences(generate_text(messages))
    try:
        payload: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError:
        payload = {
            "status": "needs_revision",
            "reason": "Judge response was not valid JSON.",
            "targetAgent": "judge",
            "revisionInstructions": "Return only the required JSON decision object.",
        }

    return JudgeDecision.model_validate(payload)


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines)
    return stripped
