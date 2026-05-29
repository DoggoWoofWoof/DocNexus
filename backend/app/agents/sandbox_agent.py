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

SAFE_IMPORTS = {"collections", "json", "math", "matplotlib", "matplotlib.pyplot", "pandas", "statistics"}
BANNED_CALLS = {"eval", "exec", "compile", "open", "input", "breakpoint"}
BANNED_NAMES = {"os", "sys", "subprocess", "socket", "shutil", "pathlib", "requests", "urllib"}
EXTERNAL_DENOMINATOR_PATTERNS = (
    "population =",
    "population_by_state",
    "state_population",
    "state_populations",
    "populations =",
    "population (",
    "per 10m",
    "per 100k",
    "millions",
)
RUNNER = r"""
import importlib
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

SAFE_IMPORTS = {"collections", "json", "math", "matplotlib", "matplotlib.pyplot", "pandas", "statistics"}


def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level != 0:
        raise ImportError("Relative imports are not allowed in the sandbox.")
    if name not in SAFE_IMPORTS and name.split(".")[0] not in SAFE_IMPORTS:
        raise ImportError(f"Import is not allowed in the sandbox: {name}")
    return __import__(name, globals, locals, fromlist, level)


safe_builtins = {
    "__import__": safe_import,
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
    result, chart_path = _run_configured_sandbox(settings=settings, code=code, dataset=dataset)

    if result.execution_status == "failed":
        corrected_code = _generate_code(
            generate_text=generate_text,
            code_goal=code_goal,
            dataset=dataset,
            chart_type=chart_type,
            revision_instructions=revision_instructions,
            previous_error=result.stderr,
        )
        corrected_result, chart_path = _run_configured_sandbox(
            settings=settings,
            code=corrected_code,
            dataset=dataset,
        )
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


def _run_configured_sandbox(
    *,
    settings: Settings,
    code: str,
    dataset: list[dict[str, object]],
) -> tuple[SandboxOutput, Path | None]:
    provider = settings.sandbox_provider.lower().strip()
    if provider == "e2b" and settings.e2b_api_key:
        try:
            return _run_e2b_sandbox(settings=settings, code=code, dataset=dataset)
        except Exception as exc:
            result, chart_path = _run_local_exec_sandbox(settings=settings, code=code, dataset=dataset)
            result.execution_provider = "local_subprocess_fallback"
            fallback_note = f"E2B was unavailable, so local fallback ran instead: {_safe_error(exc)}"
            result.stderr = "\n".join(part for part in [fallback_note, result.stderr] if part)
            return result, chart_path

    return _run_local_exec_sandbox(settings=settings, code=code, dataset=dataset)


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
                        "Use only the provided dataset; do not add external population, census, benchmark, or market-size values.",
                        "For concentration questions, compute count and share within the supplied dataset unless a denominator exists in the dataset.",
                        "Do not import unsafe modules; pd, plt, dataset, and helpers are already available.",
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
        return (
            SandboxOutput(
                code=code,
                stderr=str(exc),
                execution_status="failed",
                execution_provider="local_subprocess",
            ),
            None,
        )

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
                    execution_provider="local_subprocess",
                ),
                None,
            )

        output = SandboxOutput(
            code=code,
            stdout=completed.stdout,
            stderr=completed.stderr,
            execution_status="completed" if completed.returncode == 0 else "failed",
            execution_provider="local_subprocess",
        )

        chart_path = tmp_path / "chart.png"
        if chart_path.exists() and chart_path.stat().st_size > 0:
            persistent_tmp = settings.resolved_artifact_dir / f"tmp_chart_{uuid4().hex[:12]}.png"
            shutil.copyfile(chart_path, persistent_tmp)
            return output, persistent_tmp

        return output, None


def _run_e2b_sandbox(
    *,
    settings: Settings,
    code: str,
    dataset: list[dict[str, object]],
) -> tuple[SandboxOutput, Path | None]:
    try:
        _validate_code(code)
    except ValueError as exc:
        return (
            SandboxOutput(
                code=code,
                stderr=str(exc),
                execution_status="failed",
                execution_provider="e2b",
            ),
            None,
        )

    from e2b_code_interpreter import Sandbox as E2BSandbox

    sandbox = E2BSandbox.create(
        api_key=settings.e2b_api_key,
        timeout=max(settings.sandbox_timeout_seconds + 30, 60),
        allow_internet_access=False,
    )
    try:
        execution = sandbox.run_code(
            _build_e2b_code(code=code, dataset=dataset),
            language="python",
            timeout=settings.sandbox_timeout_seconds,
            request_timeout=max(settings.sandbox_timeout_seconds + 30, 60),
        )
        stdout = "\n".join(execution.logs.stdout)
        stderr_parts = ["\n".join(execution.logs.stderr)]
        if execution.error:
            stderr_parts.append(
                "\n".join(
                    part
                    for part in [
                        execution.error.name,
                        execution.error.value,
                        execution.error.traceback,
                    ]
                    if part
                )
            )
        output = SandboxOutput(
            code=code,
            stdout=stdout,
            stderr="\n".join(part for part in stderr_parts if part),
            execution_status="failed" if execution.error else "completed",
            execution_provider="e2b",
        )
        chart_path = _read_e2b_chart(sandbox=sandbox, settings=settings)
        return output, chart_path
    finally:
        sandbox.kill()


def _build_e2b_code(*, code: str, dataset: list[dict[str, object]]) -> str:
    dataset_json = json.dumps(dataset)
    return f"""
import json
import math
import statistics
from collections import Counter, defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

dataset = json.loads({dataset_json!r})

{code}
""".strip()


def _read_e2b_chart(*, sandbox, settings: Settings) -> Path | None:
    for remote_path in ("/home/user/chart.png", "chart.png"):
        try:
            chart_bytes = sandbox.files.read(remote_path, format="bytes")
        except Exception:
            continue

        if not chart_bytes:
            continue

        persistent_tmp = settings.resolved_artifact_dir / f"tmp_chart_{uuid4().hex[:12]}.png"
        persistent_tmp.write_bytes(bytes(chart_bytes))
        return persistent_tmp

    return None


def _validate_code(code: str) -> None:
    lowered_code = code.lower()
    if any(pattern in lowered_code for pattern in EXTERNAL_DENOMINATOR_PATTERNS):
        raise ValueError(
            "Sandbox analysis may not introduce external population denominators. "
            "Use only counts and shares from the supplied physician dataset."
        )

    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _validate_import(alias.name)

        if isinstance(node, ast.ImportFrom):
            _validate_import(node.module or "")

        if isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            raise ValueError(f"Sandbox code may not access `{node.id}`.")

        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name) and function.id in BANNED_CALLS:
                raise ValueError(f"Sandbox code may not call `{function.id}`.")


def _validate_import(module_name: str) -> None:
    if not module_name:
        raise ValueError("Relative imports are not allowed in sandbox code.")
    if module_name not in SAFE_IMPORTS and module_name.split(".")[0] not in SAFE_IMPORTS:
        raise ValueError(
            f"Sandbox code may not import `{module_name}`. "
            f"Allowed imports: {', '.join(sorted(SAFE_IMPORTS))}."
        )


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


def _safe_error(exc: Exception) -> str:
    message = str(exc).replace("\n", " ").strip()
    return message[:300] or exc.__class__.__name__
