import ast
import json
import shutil
import subprocess
import sys
import tempfile
from uuid import uuid4
from collections.abc import Callable
from pathlib import Path

from sqlmodel import Session

from backend.app.core.config import Settings
from backend.app.schemas.artifact import ArtifactType
from backend.app.schemas.query import SandboxOutput
from backend.app.services.artifacts import finalize_artifact_file, register_artifact
from backend.app.services.prompts import load_prompt


TextGenerator = Callable[[list[dict[str, object]]], str]

BANNED_NODES = (ast.Import, ast.ImportFrom)
BANNED_CALLS = {"eval", "exec", "compile", "__import__", "open", "input", "breakpoint"}
BANNED_NAMES = {"os", "sys", "subprocess", "socket", "shutil", "pathlib", "requests", "urllib"}
RUNNER = r"""
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

dataset = json.loads(Path("dataset.json").read_text(encoding="utf-8"))
code = Path("analysis_code.py").read_text(encoding="utf-8")

safe_builtins = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "print": print,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}

globals_dict = {
    "__builtins__": safe_builtins,
    "Counter": Counter,
    "defaultdict": defaultdict,
    "dataset": dataset,
    "json": json,
    "math": math,
    "pd": pd,
    "plt": plt,
    "statistics": statistics,
}

exec(compile(code, "analysis_code.py", "exec"), globals_dict, {})
"""


def generate_and_run_sandbox_code(
    *,
    session: Session,
    settings: Settings,
    generate_text: TextGenerator,
    code_goal: str,
    dataset: list[dict[str, object]],
    chart_type: str | None,
    revision_instructions: str | None = None,
    artifact_provenance: dict[str, object] | None = None,
) -> SandboxOutput:
    code = _generate_code(
        generate_text=generate_text,
        code_goal=code_goal,
        dataset=dataset,
        chart_type=chart_type,
        revision_instructions=revision_instructions,
        previous_error=None,
    )
    result, chart_path = _run_local_exec_sandbox(settings=settings, code=code, dataset=dataset)

    if result.execution_status == "failed":
        corrected_code = _generate_code(
            generate_text=generate_text,
            code_goal=code_goal,
            dataset=dataset,
            chart_type=chart_type,
            revision_instructions=revision_instructions,
            previous_error=result.stderr,
        )
        corrected_result, chart_path = _run_local_exec_sandbox(settings=settings, code=corrected_code, dataset=dataset)
        corrected_result.code = corrected_code
        result = corrected_result
    else:
        result.code = code

    if result.chart_artifact_id:
        return result

    if chart_path:
        artifact, artifact_path = register_artifact(
            session,
            settings=settings,
            artifact_type=ArtifactType.chart_png,
            filename="sandbox_chart.png",
            source_agent="sandbox",
            **(artifact_provenance or {}),
        )
        shutil.copyfile(chart_path, artifact_path)
        finalize_artifact_file(session, artifact, artifact_path)
        result.chart_artifact_id = artifact.id

    return result


def _generate_code(
    *,
    generate_text: TextGenerator,
    code_goal: str,
    dataset: list[dict[str, object]],
    chart_type: str | None,
    revision_instructions: str | None,
    previous_error: str | None,
) -> str:
    prompt = load_prompt("sandbox_agent.md")
    messages: list[dict[str, object]] = [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "codeGoal": code_goal,
                    "chartType": chart_type,
                    "revisionInstructions": revision_instructions,
                    "datasetPreview": dataset[:5],
                    "datasetCount": len(dataset),
                    "availableVariables": ["dataset", "pd", "plt", "json", "math", "statistics", "Counter"],
                    "instructions": [
                        "Return only Python code.",
                        "Do not include markdown fences.",
                        "Do not import modules; pd, plt, dataset, and helpers are already available.",
                        "Use dataset as the input list of records.",
                        "Save any chart to chart.png.",
                    ],
                    "previousError": previous_error,
                }
            ),
        },
    ]
    return _strip_code_fences(generate_text(messages)).strip()


def _run_local_exec_sandbox(
    *,
    settings: Settings,
    code: str,
    dataset: list[dict[str, object]],
) -> tuple[SandboxOutput, Path | None]:
    try:
        _validate_code(code)
    except ValueError as exc:
        return SandboxOutput(code=code, stderr=str(exc), execution_status="failed"), None

    with tempfile.TemporaryDirectory(prefix="docnexus_sandbox_") as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "dataset.json").write_text(json.dumps(dataset), encoding="utf-8")
        (tmp_path / "analysis_code.py").write_text(code, encoding="utf-8")
        (tmp_path / "runner.py").write_text(RUNNER, encoding="utf-8")

        try:
            completed = subprocess.run(
                [sys.executable, "-I", str(tmp_path / "runner.py")],
                cwd=tmp_path,
                capture_output=True,
                text=True,
                timeout=settings.sandbox_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return (
                SandboxOutput(
                    code=code,
                    stdout=exc.stdout or "",
                    stderr=f"Sandbox timed out after {settings.sandbox_timeout_seconds} seconds.",
                    execution_status="failed",
                ),
                None,
            )

        output = SandboxOutput(
            code=code,
            stdout=completed.stdout,
            stderr=completed.stderr,
            execution_status="completed" if completed.returncode == 0 else "failed",
        )

        chart_path = tmp_path / "chart.png"
        if chart_path.exists() and chart_path.stat().st_size > 0:
            persistent_tmp = settings.resolved_artifact_dir / f"tmp_chart_{uuid4().hex[:12]}.png"
            shutil.copyfile(chart_path, persistent_tmp)
            return output, persistent_tmp

        return output, None


def _validate_code(code: str) -> None:
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, BANNED_NODES):
            raise ValueError("Sandbox code may not import modules. Use the provided pd, plt, and dataset variables.")

        if isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            raise ValueError(f"Sandbox code may not access `{node.id}`.")

        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name) and function.id in BANNED_CALLS:
                raise ValueError(f"Sandbox code may not call `{function.id}`.")


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines)
    return text
