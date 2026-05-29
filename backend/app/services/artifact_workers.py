import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from backend.app.core.config import Settings


class ArtifactWorkerError(RuntimeError):
    pass


def run_artifact_worker(
    *,
    settings: Settings,
    module: str,
    payload: dict[str, Any],
    output_path: Path,
    e2b_script: str | None = None,
    packages: list[str] | None = None,
) -> dict[str, object]:
    if settings.sandbox_provider.lower().strip() == "e2b" and settings.e2b_api_key and e2b_script:
        try:
            return _run_e2b_artifact_worker(
                settings=settings,
                payload=payload,
                output_path=output_path,
                script=e2b_script,
                packages=packages or [],
            )
        except Exception as exc:
            fallback = _run_local_artifact_worker(
                settings=settings,
                module=module,
                payload=payload,
                output_path=output_path,
            )
            fallback["executionProvider"] = "local_artifact_worker_fallback"
            fallback["fallbackReason"] = _safe_error(exc)
            return fallback

    return _run_local_artifact_worker(
        settings=settings,
        module=module,
        payload=payload,
        output_path=output_path,
    )


def _run_local_artifact_worker(
    *,
    settings: Settings,
    module: str,
    payload: dict[str, Any],
    output_path: Path,
) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="docnexus_artifact_worker_") as tmp:
        tmp_path = Path(tmp)
        payload_path = tmp_path / "payload.json"
        payload_path.write_text(json.dumps(payload, default=str), encoding="utf-8")

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                module,
                "--render-worker",
                str(payload_path),
                str(output_path),
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            timeout=settings.sandbox_timeout_seconds,
            check=False,
        )

    if completed.returncode != 0:
        raise ArtifactWorkerError(
            f"Artifact worker failed with exit code {completed.returncode}: {completed.stderr[-1200:]}"
        )
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise ArtifactWorkerError("Artifact worker completed without writing an output file.")

    return {
        "executionProvider": "local_artifact_worker",
        "stdout": completed.stdout[-1200:],
        "stderr": completed.stderr[-1200:],
    }


def _run_e2b_artifact_worker(
    *,
    settings: Settings,
    payload: dict[str, Any],
    output_path: Path,
    script: str,
    packages: list[str],
) -> dict[str, object]:
    from e2b_code_interpreter import Sandbox as E2BSandbox

    remote_output = f"/home/user/output{output_path.suffix}"
    sandbox = E2BSandbox.create(
        api_key=settings.e2b_api_key,
        timeout=max(settings.sandbox_timeout_seconds + 120, 180),
        allow_internet_access=True,
    )
    try:
        if packages:
            install = sandbox.run_code(
                f"python -m pip install --quiet {' '.join(packages)}",
                language="bash",
                timeout=120,
                request_timeout=150,
            )
            if install.error:
                raise ArtifactWorkerError(f"E2B package install failed: {install.error.value}")

        sandbox.files.write("/home/user/payload.json", json.dumps(payload, default=str))
        sandbox.files.write("/home/user/render_worker.py", script)
        execution = sandbox.run_code(
            f"python /home/user/render_worker.py /home/user/payload.json {remote_output}",
            language="bash",
            timeout=settings.sandbox_timeout_seconds,
            request_timeout=max(settings.sandbox_timeout_seconds + 30, 60),
        )
        if execution.error:
            raise ArtifactWorkerError(
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

        artifact_bytes = sandbox.files.read(remote_output, format="bytes")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(bytes(artifact_bytes))
        return {
            "executionProvider": "e2b_artifact_worker",
            "stdout": "\n".join(execution.logs.stdout)[-1200:],
            "stderr": "\n".join(execution.logs.stderr)[-1200:],
            "installedPackages": packages,
        }
    finally:
        sandbox.kill()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _safe_error(exc: Exception) -> str:
    message = str(exc).replace("\n", " ").strip()
    return message[:300] or exc.__class__.__name__
