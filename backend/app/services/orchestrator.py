import json
from uuid import uuid4

from sqlmodel import Session

from backend.app.agents.judge_agent import judge_outputs, score_summary
from backend.app.agents.ppt_agent import generate_ppt_deck
from backend.app.agents.report_agent import generate_report
from backend.app.agents.sandbox_agent import generate_and_run_sandbox_code
from backend.app.agents.tool_definitions import get_orchestrator_tools
from backend.app.agents.excel_agent import generate_excel_workbook
from backend.app.clients.mistral import MistralClientError, MistralToolCall, MistralToolClient
from backend.app.core.config import Settings
from backend.app.schemas.artifact import ArtifactRef, ArtifactValidationResult
from backend.app.schemas.query import JudgeDecision, JudgeScores, JudgeStatus, QueryRequest, QueryResponse
from backend.app.schemas.trace import AgentName
from backend.app.schemas.tools import ExcelAgentArgs, PptAgentArgs, ReportAgentArgs, SandboxAgentArgs
from backend.app.services.physicians import list_physicians
from backend.app.services.prompts import load_prompt
from backend.app.services.trace import TraceBuilder
from backend.app.services.artifacts import hash_payload, hash_text
from backend.app.services.artifact_validation import validate_artifacts


AGENT_TOOL_NAMES = {
    "call_ppt_agent": AgentName.ppt,
    "call_excel_agent": AgentName.excel,
    "call_report_agent": AgentName.report,
    "call_sandbox_agent": AgentName.sandbox,
}

SOURCE_AGENT_BY_TOOL_NAME = {
    "call_ppt_agent": "ppt",
    "call_excel_agent": "excel",
    "call_report_agent": "report",
    "call_sandbox_agent": "sandbox",
}


class OrchestratorService:
    def __init__(self, *, settings: Settings, session: Session, request_id: str | None = None):
        self.settings = settings
        self.session = session
        self.mistral = MistralToolClient(settings)
        self.request_id = request_id
        self.reset_context()

    def set_request_id(self, request_id: str) -> None:
        self.request_id = request_id

    def reset_context(self) -> None:
        self._physician_context: list[dict[str, object]] = []
        self._artifact_refs: list[ArtifactRef] = []
        self._artifact_validations: list[ArtifactValidationResult] = []
        self._report_markdown: str | None = None
        self._sandbox_output = None
        self._judge_decision = None

    @property
    def artifact_refs(self) -> list[ArtifactRef]:
        return self._artifact_refs

    @property
    def artifact_validations(self) -> list[ArtifactValidationResult]:
        return self._artifact_validations

    @property
    def physician_context(self) -> list[dict[str, object]]:
        return self._physician_context

    @property
    def report_markdown(self) -> str | None:
        return self._report_markdown

    @property
    def sandbox_output(self):
        return self._sandbox_output

    @property
    def judge_decision(self):
        return self._judge_decision

    def set_judge_decision(self, decision: JudgeDecision) -> None:
        self._judge_decision = decision

    def prepare_for_revision(self, tool_name: str) -> None:
        source_agent = SOURCE_AGENT_BY_TOOL_NAME.get(tool_name)
        if source_agent:
            self._artifact_refs = [ref for ref in self._artifact_refs if ref.source_agent != source_agent]
            self._artifact_validations = [
                result for result in self._artifact_validations if result.source_agent != source_agent
            ]

        if tool_name == "call_report_agent":
            self._report_markdown = None
        if tool_name == "call_sandbox_agent":
            self._sandbox_output = None

    def run(self, request: QueryRequest) -> QueryResponse:
        request_id = f"req_{uuid4().hex[:12]}"
        self.set_request_id(request_id)
        trace = TraceBuilder()
        prompt = load_prompt("orchestrator.md")
        tools = get_orchestrator_tools()
        tool_call_records: list[dict[str, object]] = []
        answer_markdown: str | None = None
        self.reset_context()

        start_id = trace.started(
            agent=AgentName.orchestrator,
            message="Parsing query and selecting tools.",
            metadata={"model": self.settings.mistral_model},
        )

        messages = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": self._build_user_message(request),
            },
        ]

        for step in range(3):
            model_message = self.mistral.complete_with_tools(
                messages=messages,
                tools=tools,
                tool_choice="auto",
                parallel_tool_calls=True,
            )

            if not model_message.tool_calls:
                answer_markdown = model_message.content
                trace.completed(
                    started_event_id=start_id,
                    agent=AgentName.orchestrator,
                    message="Orchestrator produced a final response.",
                    metadata={"steps": step + 1},
                )
                break

            messages.append(self._assistant_tool_call_message(model_message.tool_calls))

            for tool_call in model_message.tool_calls:
                tool_call_records.append(
                    {
                        "id": tool_call.id,
                        "name": tool_call.name,
                        "arguments": tool_call.arguments,
                    }
                )
                tool_result = self._execute_tool(tool_call, trace)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.name,
                        "content": json.dumps(tool_result),
                    }
                )
        else:
            trace.completed(
                started_event_id=start_id,
                agent=AgentName.orchestrator,
                message="Stopped after the maximum orchestration planning steps.",
                metadata={"maxSteps": 3},
            )

        fallback_answer = (
            f"Generated {len(self._artifact_refs)} artifact(s)."
            if self._artifact_refs
            else "Orchestration completed without file artifacts."
        )
        final_answer = self._report_markdown or answer_markdown or fallback_answer
        self.validate_generated_artifacts(trace=trace)
        self.run_judge(
            trace=trace,
            query=request.query,
            artifacts=self._artifact_refs,
            artifact_validations=self._artifact_validations,
            answer_markdown=final_answer,
            sandbox_output=self._sandbox_output,
            tool_calls=tool_call_records,
        )

        return QueryResponse(
            request_id=request_id,
            query=request.query,
            answer_markdown=final_answer,
            artifacts=self._artifact_refs,
            artifact_validations=self._artifact_validations,
            sandbox_output=self._sandbox_output,
            trace=trace.events if request.include_trace else [],
            judge_decision=self._judge_decision,
            metadata={
                "toolCalls": tool_call_records,
                "implementedTools": [
                    "get_physician_data",
                    "call_excel_agent",
                    "call_ppt_agent",
                    "call_report_agent",
                    "call_sandbox_agent",
                ],
                "pendingTools": [],
            },
        )

    def execute_tool(self, tool_call: MistralToolCall, trace: TraceBuilder) -> dict[str, object]:
        return self._execute_tool(tool_call, trace)

    def run_judge(
        self,
        *,
        trace: TraceBuilder,
        query: str,
        artifacts: list[ArtifactRef],
        artifact_validations: list[ArtifactValidationResult],
        answer_markdown: str | None,
        sandbox_output,
        tool_calls: list[dict[str, object]],
    ) -> None:
        self._run_judge(
            trace=trace,
            query=query,
            artifacts=artifacts,
            artifact_validations=artifact_validations,
            answer_markdown=answer_markdown,
            sandbox_output=sandbox_output,
            tool_calls=tool_calls,
        )

    def validate_generated_artifacts(self, *, trace: TraceBuilder) -> list[ArtifactValidationResult]:
        if not self._artifact_refs:
            self._artifact_validations = []
            return self._artifact_validations

        start_id = trace.started(
            agent=AgentName.judge,
            message="Running deterministic artifact validation.",
            metadata={"artifactIds": [artifact.id for artifact in self._artifact_refs]},
        )
        self._artifact_validations = validate_artifacts(
            self.session,
            [artifact.id for artifact in self._artifact_refs],
        )
        failed = [result for result in self._artifact_validations if not result.passed]
        trace.completed(
            started_event_id=start_id,
            agent=AgentName.judge,
            message=f"Validated {len(self._artifact_validations)} artifact(s).",
            metadata={
                "failedArtifactIds": [result.artifact_id for result in failed],
                "scores": {
                    result.artifact_id: result.score for result in self._artifact_validations
                },
            },
        )
        return self._artifact_validations

    def build_user_message(self, request: QueryRequest) -> str:
        return self._build_user_message(request)

    @staticmethod
    def assistant_tool_call_message(tool_calls: list[MistralToolCall]) -> dict[str, object]:
        return OrchestratorService._assistant_tool_call_message(tool_calls)

    def _execute_tool(self, tool_call: MistralToolCall, trace: TraceBuilder) -> dict[str, object]:
        if tool_call.name == "get_physician_data":
            return self._execute_get_physician_data(tool_call, trace)

        if tool_call.name == "call_excel_agent":
            return self._execute_excel_agent(tool_call, trace)

        if tool_call.name == "call_ppt_agent":
            return self._execute_ppt_agent(tool_call, trace)

        if tool_call.name == "call_report_agent":
            return self._execute_report_agent(tool_call, trace)

        if tool_call.name == "call_sandbox_agent":
            return self._execute_sandbox_agent(tool_call, trace)

        agent = AGENT_TOOL_NAMES.get(tool_call.name, AgentName.orchestrator)
        trace.skipped(
            agent=agent,
            message=f"{tool_call.name} was selected but the agent is not implemented yet.",
            metadata={"toolCallId": tool_call.id},
        )
        return {
            "status": "not_implemented",
            "message": f"{tool_call.name} is planned but not implemented yet.",
        }

    def _execute_get_physician_data(self, tool_call: MistralToolCall, trace: TraceBuilder) -> dict[str, object]:
        start_id = trace.started(
            agent=AgentName.data,
            message="Retrieving filtered physician data.",
            metadata={"toolCallId": tool_call.id, "arguments": tool_call.arguments},
        )
        args = tool_call.arguments
        physicians, filters = list_physicians(
            self.session,
            specialty=args.get("specialty") or [],
            state=args.get("state") or [],
            region=args.get("region") or [],
            icd10_codes=args.get("icd10_codes") or [],
            volume_threshold=args.get("volume_threshold"),
            board_certified=args.get("board_certified"),
        )
        trace.completed(
            started_event_id=start_id,
            agent=AgentName.data,
            message=f"Retrieved {len(physicians)} physician records.",
            metadata={"count": len(physicians), "filters": filters.model_dump(by_alias=True)},
        )
        self._physician_context = [physician.model_dump(by_alias=True) for physician in physicians]
        return {
            "status": "completed",
            "count": len(physicians),
            "filtersApplied": filters.model_dump(by_alias=True),
            "physicians": self._physician_context,
        }

    def _execute_excel_agent(self, tool_call: MistralToolCall, trace: TraceBuilder) -> dict[str, object]:
        start_id = trace.started(
            agent=AgentName.excel,
            message="Generating Excel workbook.",
            metadata={"toolCallId": tool_call.id},
        )

        args = {
            "analysis_type": "physician_breakdown",
            "dimensions": ["state", "specialty", "icd10_code"],
            "icd10_codes": [],
            "revision_instructions": None,
            **tool_call.arguments,
        }
        if self._physician_context:
            args["physician_list"] = self._physician_context

        excel_args = ExcelAgentArgs.model_validate(args)
        artifact_ref = generate_excel_workbook(
            session=self.session,
            settings=self.settings,
            generate_text=lambda messages: self.mistral.complete_text(messages=messages),
            analysis_type=excel_args.analysis_type,
            physicians=excel_args.physician_list,
            dimensions=excel_args.dimensions,
            icd10_codes=excel_args.icd10_codes,
            artifact_provenance=self._artifact_provenance(
                tool_call=tool_call,
                prompt_name="excel_agent.md",
                payload=excel_args.model_dump(by_alias=True),
            ),
        )
        self._artifact_refs.append(artifact_ref)

        trace.completed(
            started_event_id=start_id,
            agent=AgentName.excel,
            message=f"Generated Excel workbook: {artifact_ref.filename}.",
            metadata={
                "artifactId": artifact_ref.id,
                "physicianCount": len(excel_args.physician_list),
                "renderExecution": artifact_ref.provenance.get("renderExecution", {}),
                "revision": bool(excel_args.revision_instructions),
            },
        )
        return {
            "status": "completed",
            "artifact": artifact_ref.model_dump(by_alias=True),
        }

    def _execute_report_agent(self, tool_call: MistralToolCall, trace: TraceBuilder) -> dict[str, object]:
        start_id = trace.started(
            agent=AgentName.report,
            message="Generating markdown report.",
            metadata={"toolCallId": tool_call.id},
        )

        args = {
            "report_type": "Physician Landscape Report",
            "sections": [
                "Executive Summary",
                "Physician Landscape Overview",
                "Geographic & Specialty Distribution",
                "Key Insights & Implications",
                "Recommended Next Steps",
            ],
            "physician_list": self._physician_context,
            "icd10_context": [],
            "geographic_scope": [],
            "revision_instructions": None,
            **tool_call.arguments,
        }
        if self._physician_context:
            args["physician_list"] = self._physician_context

        report_args = ReportAgentArgs.model_validate(args)
        markdown, artifact_ref = generate_report(
            session=self.session,
            settings=self.settings,
            generate_text=lambda messages: self.mistral.complete_text(messages=messages),
            report_type=report_args.report_type,
            sections=report_args.sections,
            physicians=report_args.physician_list,
            icd10_context=report_args.icd10_context,
            geographic_scope=report_args.geographic_scope,
            revision_instructions=report_args.revision_instructions,
            artifact_provenance=self._artifact_provenance(
                tool_call=tool_call,
                prompt_name="report_agent.md",
                payload=report_args.model_dump(by_alias=True),
            ),
        )
        self._report_markdown = markdown
        self._artifact_refs.append(artifact_ref)

        trace.completed(
            started_event_id=start_id,
            agent=AgentName.report,
            message=f"Generated markdown report: {artifact_ref.filename}.",
            metadata={
                "artifactId": artifact_ref.id,
                "physicianCount": len(report_args.physician_list),
                "revision": bool(report_args.revision_instructions),
            },
        )
        return {
            "status": "completed",
            "artifact": artifact_ref.model_dump(by_alias=True),
            "markdown": markdown,
        }

    def _execute_sandbox_agent(self, tool_call: MistralToolCall, trace: TraceBuilder) -> dict[str, object]:
        start_id = trace.started(
            agent=AgentName.sandbox,
            message="Generating and executing sandbox analysis code.",
            metadata={"toolCallId": tool_call.id},
        )

        args = {
            "code_goal": "Analyze the filtered physician dataset.",
            "dataset": self._physician_context,
            "chart_type": None,
            "revision_instructions": None,
            **tool_call.arguments,
        }
        if self._physician_context:
            args["dataset"] = self._physician_context
        if not args.get("chart_type") and _goal_likely_wants_chart(str(args.get("code_goal") or "")):
            args["chart_type"] = "bar"

        sandbox_args = SandboxAgentArgs.model_validate(args)
        output = generate_and_run_sandbox_code(
            session=self.session,
            settings=self.settings,
            generate_text=lambda messages: self.mistral.complete_text(messages=messages),
            code_goal=sandbox_args.code_goal,
            dataset=sandbox_args.dataset,
            chart_type=sandbox_args.chart_type,
            revision_instructions=sandbox_args.revision_instructions,
            artifact_provenance=self._artifact_provenance(
                tool_call=tool_call,
                prompt_name="sandbox_agent.md",
                payload=sandbox_args.model_dump(by_alias=True),
            ),
        )
        self._sandbox_output = output

        if output.chart_artifact_id:
            from backend.app.services.artifacts import get_artifact, to_artifact_ref

            self._artifact_refs.append(to_artifact_ref(get_artifact(self.session, output.chart_artifact_id)))

        if output.execution_status == "completed":
            trace.completed(
                started_event_id=start_id,
                agent=AgentName.sandbox,
                message="Sandbox analysis completed.",
                metadata={
                    "chartArtifactId": output.chart_artifact_id,
                    "executionProvider": output.execution_provider,
                    "attemptCount": output.attempt_count,
                    "contractStatus": output.contract_status,
                    "contractMessages": output.contract_messages,
                },
            )
        else:
            trace.failed(
                started_event_id=start_id,
                agent=AgentName.sandbox,
                message="Sandbox analysis failed after retry.",
                metadata={
                    "stderr": output.stderr[-1000:],
                    "executionProvider": output.execution_provider,
                    "attemptCount": output.attempt_count,
                    "contractStatus": output.contract_status,
                    "contractMessages": output.contract_messages,
                },
            )

        return {
            "status": output.execution_status,
            "sandboxOutput": output.model_dump(by_alias=True),
        }

    def _execute_ppt_agent(self, tool_call: MistralToolCall, trace: TraceBuilder) -> dict[str, object]:
        start_id = trace.started(
            agent=AgentName.ppt,
            message="Generating PowerPoint deck.",
            metadata={"toolCallId": tool_call.id},
        )

        args = {
            "topic": "Physician Landscape Summary",
            "physician_list": self._physician_context,
            "icd10_codes": [],
            "slide_count": 4,
            "revision_instructions": None,
            **tool_call.arguments,
        }
        if self._physician_context:
            args["physician_list"] = self._physician_context

        ppt_args = PptAgentArgs.model_validate(args)
        artifact_ref = generate_ppt_deck(
            session=self.session,
            settings=self.settings,
            generate_text=lambda messages: self.mistral.complete_text(messages=messages),
            topic=ppt_args.topic,
            physicians=ppt_args.physician_list,
            icd10_codes=ppt_args.icd10_codes,
            slide_count=ppt_args.slide_count,
            style_notes=_append_revision_note(ppt_args.style_notes, ppt_args.revision_instructions),
            artifact_provenance=self._artifact_provenance(
                tool_call=tool_call,
                prompt_name="ppt_agent.md",
                payload=ppt_args.model_dump(by_alias=True),
            ),
        )
        self._artifact_refs.append(artifact_ref)

        trace.completed(
            started_event_id=start_id,
            agent=AgentName.ppt,
            message=f"Generated PowerPoint deck: {artifact_ref.filename}.",
            metadata={
                "artifactId": artifact_ref.id,
                "physicianCount": len(ppt_args.physician_list),
                "renderExecution": artifact_ref.provenance.get("renderExecution", {}),
                "revision": bool(ppt_args.revision_instructions),
            },
        )
        return {
            "status": "completed",
            "artifact": artifact_ref.model_dump(by_alias=True),
        }

    def _run_judge(
        self,
        *,
        trace: TraceBuilder,
        query: str,
        artifacts: list[ArtifactRef],
        artifact_validations: list[ArtifactValidationResult],
        answer_markdown: str | None,
        sandbox_output,
        tool_calls: list[dict[str, object]],
    ) -> None:
        start_id = trace.started(
            agent=AgentName.judge,
            message="Evaluating generated outputs.",
        )
        judge_provider = "mistral"
        try:
            self._judge_decision = judge_outputs(
                generate_text=lambda messages: self.mistral.complete_text(messages=messages),
                query=query,
                artifacts=artifacts,
                artifact_validations=artifact_validations,
                answer_markdown=answer_markdown,
                sandbox_output=sandbox_output,
                tool_calls=tool_calls,
            )
        except MistralClientError as exc:
            judge_provider = "deterministic_resilience"
            self._judge_decision = _deterministic_judge_decision(
                error=exc,
                artifacts=artifacts,
                artifact_validations=artifact_validations,
                answer_markdown=answer_markdown,
                sandbox_output=sandbox_output,
            )
        trace.completed(
            started_event_id=start_id,
            agent=AgentName.judge,
            message=f"Judge decision: {self._judge_decision.status.value} ({self._judge_decision.scores.overall}/100).",
            metadata={
                "judgeProvider": judge_provider,
                "reason": self._judge_decision.reason,
                "scores": score_summary(self._judge_decision),
                "criticalFailures": self._judge_decision.critical_failures,
                "artifactValidationScores": {
                    result.artifact_id: result.score for result in artifact_validations
                },
            },
        )

    def _build_user_message(self, request: QueryRequest) -> str:
        payload = {
            "query": request.query,
            "preferences": request.preferences.model_dump(by_alias=True),
            "requestedArtifacts": [artifact.value for artifact in request.requested_artifacts],
        }
        return json.dumps(payload)

    def _artifact_provenance(
        self,
        *,
        tool_call: MistralToolCall,
        prompt_name: str,
        payload: object,
    ) -> dict[str, object]:
        prompt = load_prompt(prompt_name)
        return {
            "request_id": self.request_id,
            "tool_call_id": tool_call.id,
            "prompt_name": prompt_name,
            "prompt_sha256": hash_text(prompt),
            "input_sha256": hash_payload(payload),
            "provenance": {
                "model": self.settings.mistral_model,
                "toolName": tool_call.name,
                "sourceAgent": SOURCE_AGENT_BY_TOOL_NAME.get(tool_call.name, tool_call.name),
                "inputRecordCount": _record_count(payload),
            },
        }

    @staticmethod
    def _assistant_tool_call_message(tool_calls: list[MistralToolCall]) -> dict[str, object]:
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": json.dumps(tool_call.arguments),
                    },
                }
                for tool_call in tool_calls
            ],
        }


def _append_revision_note(existing: str | None, revision_instructions: str | None) -> str | None:
    if not revision_instructions:
        return existing
    if not existing:
        return f"Revision instructions: {revision_instructions}"
    return f"{existing}\nRevision instructions: {revision_instructions}"


def _record_count(payload: object) -> int | None:
    if not isinstance(payload, dict):
        return None
    for key in ("physicianList", "dataset"):
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
    return None


def _goal_likely_wants_chart(goal: str) -> bool:
    normalized = goal.lower()
    return any(
        term in normalized
        for term in [
            "show me",
            "chart",
            "plot",
            "visualize",
            "highest",
            "lowest",
            "rank",
            "ranking",
            "concentration",
            "distribution",
            "compare",
        ]
    )


def _deterministic_judge_decision(
    *,
    error: Exception,
    artifacts: list[ArtifactRef],
    artifact_validations: list[ArtifactValidationResult],
    answer_markdown: str | None,
    sandbox_output,
) -> JudgeDecision:
    critical_failures: list[str] = []
    failed_validations = [validation for validation in artifact_validations if not validation.passed]
    if failed_validations:
        critical_failures.extend(
            f"Artifact {validation.artifact_id} failed validation."
            for validation in failed_validations
        )
    if sandbox_output and sandbox_output.execution_status != "completed":
        critical_failures.append("Sandbox execution did not complete.")
    if sandbox_output and sandbox_output.contract_status != "satisfied":
        critical_failures.append("Sandbox contract was not satisfied.")
    if not answer_markdown or not answer_markdown.strip():
        critical_failures.append("No final answer markdown was produced.")

    artifact_quality = 100 if artifacts and not failed_validations else 70 if artifacts else 60
    completion = 100 if answer_markdown and not critical_failures else 65
    grounding = 100 if not failed_validations else 70
    relevance = 85 if answer_markdown else 60
    preference_alignment = 85 if sandbox_output and sandbox_output.contract_status == "satisfied" else 65
    overall = min(relevance, completion, grounding, artifact_quality, preference_alignment)

    status = JudgeStatus.approved if overall >= 85 and not critical_failures else JudgeStatus.needs_revision
    target_agent = None
    if critical_failures:
        target_agent = failed_validations[0].source_agent if failed_validations else "sandbox"

    return JudgeDecision(
        status=status,
        reason=(
            "LLM judge was unavailable, so deterministic validation scored the completed output. "
            f"Judge error: {_safe_error(error)}"
        ),
        scores=JudgeScores(
            relevance=relevance,
            completion=completion,
            grounding=grounding,
            artifact_quality=artifact_quality,
            preference_alignment=preference_alignment,
            overall=overall,
        ),
        critical_failures=critical_failures,
        target_agent=target_agent,
        revision_instructions="Resolve deterministic validation failures." if critical_failures else None,
    )


def _safe_error(exc: Exception) -> str:
    message = str(exc).replace("\n", " ").strip()
    return message[:300] or exc.__class__.__name__
