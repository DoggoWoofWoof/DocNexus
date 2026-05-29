from collections.abc import Callable
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from sqlmodel import Session

from backend.app.agents.tool_definitions import get_orchestrator_tools
from backend.app.clients.mistral import MistralToolCall
from backend.app.core.config import Settings
from backend.app.schemas.artifact import ArtifactRef, ArtifactValidationResult
from backend.app.schemas.query import JudgeDecision, JudgeStatus, QueryRequest, QueryResponse, SandboxOutput
from backend.app.schemas.trace import AgentName
from backend.app.schemas.trace import TraceEvent
from backend.app.services.orchestrator import OrchestratorService
from backend.app.services.prompts import load_prompt
from backend.app.services.trace import TraceBuilder


MAX_PLANNING_STEPS = 3
MAX_REVISION_ATTEMPTS = 1
JUDGE_APPROVAL_THRESHOLD = 85

TOOL_NODE_BY_NAME = {
    "get_physician_data": "data_agent",
    "call_excel_agent": "excel_agent",
    "call_ppt_agent": "ppt_agent",
    "call_report_agent": "report_agent",
    "call_sandbox_agent": "sandbox_agent",
}

AGENT_BY_TOOL_NAME = {
    "get_physician_data": AgentName.data,
    "call_excel_agent": AgentName.excel,
    "call_ppt_agent": AgentName.ppt,
    "call_report_agent": AgentName.report,
    "call_sandbox_agent": AgentName.sandbox,
}

TOOL_EXECUTION_ORDER = {
    "get_physician_data": 0,
    "call_excel_agent": 1,
    "call_ppt_agent": 2,
    "call_report_agent": 3,
    "call_sandbox_agent": 4,
}

GRAPH_NODES = [
    "initialize",
    "plan",
    "route_tool",
    "data_agent",
    "excel_agent",
    "ppt_agent",
    "report_agent",
    "sandbox_agent",
    "unsupported_tool",
    "stop_planning",
    "judge",
    "prepare_revision",
    "finalize",
]


class QueryWorkflowState(TypedDict, total=False):
    request: QueryRequest
    runtime: OrchestratorService
    trace: TraceBuilder
    request_id: str
    orchestrator_start_id: str
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    step_count: int
    pending_tool_calls: list[MistralToolCall]
    current_tool_call: MistralToolCall | None
    tool_call_records: list[dict[str, object]]
    answer_markdown: str | None
    final_answer: str
    artifacts: list[ArtifactRef]
    artifact_validations: list[ArtifactValidationResult]
    sandbox_output: SandboxOutput | None
    judge_decision: JudgeDecision | None
    revision_count: int
    revision_history: list[dict[str, object]]
    active_revision: bool
    response: QueryResponse


def run_query_workflow(
    *,
    settings: Settings,
    session: Session,
    request: QueryRequest,
    trace_sink: Callable[[TraceEvent], None] | None = None,
) -> QueryResponse:
    graph = StateGraph(QueryWorkflowState)

    def initialize_node(state: QueryWorkflowState) -> dict[str, object]:
        request_id = f"req_{uuid4().hex[:12]}"
        runtime = OrchestratorService(settings=settings, session=session, request_id=request_id)
        trace = TraceBuilder(on_event=trace_sink)
        start_id = trace.started(
            agent=AgentName.orchestrator,
            message="Parsing query and selecting tools.",
            metadata={"model": settings.mistral_model, "workflow": "langgraph"},
        )

        return {
            "request_id": request_id,
            "runtime": runtime,
            "trace": trace,
            "orchestrator_start_id": start_id,
            "messages": [
                {"role": "system", "content": load_prompt("orchestrator.md")},
                {"role": "user", "content": runtime.build_user_message(state["request"])},
            ],
            "tools": get_orchestrator_tools(),
            "step_count": 0,
            "pending_tool_calls": [],
            "current_tool_call": None,
            "tool_call_records": [],
            "answer_markdown": None,
            "revision_count": 0,
            "revision_history": [],
            "active_revision": False,
        }

    def plan_node(state: QueryWorkflowState) -> dict[str, object]:
        runtime = state["runtime"]
        model_message = runtime.mistral.complete_with_tools(
            messages=state["messages"],
            tools=state["tools"],
            tool_choice="auto",
            parallel_tool_calls=True,
        )
        step_count = state["step_count"] + 1

        if not model_message.tool_calls:
            guard_tool_call = _missing_required_followup_tool(state)
            if guard_tool_call is not None:
                state["trace"].retrying(
                    agent=AgentName.orchestrator,
                    message=f"Workflow guard added missing {guard_tool_call.name} step.",
                    metadata={
                        "reason": "The query asks for analysis/ranking, but Mistral stopped after data retrieval.",
                        "selectedTools": [guard_tool_call.name],
                    },
                )
                return {
                    "step_count": step_count,
                    "pending_tool_calls": [guard_tool_call],
                    "messages": [
                        *state["messages"],
                        runtime.assistant_tool_call_message([guard_tool_call]),
                    ],
                }

            state["trace"].completed(
                started_event_id=state["orchestrator_start_id"],
                agent=AgentName.orchestrator,
                message="Orchestrator produced a final response.",
                metadata={"steps": step_count},
            )
            return {
                "step_count": step_count,
                "pending_tool_calls": [],
                "answer_markdown": model_message.content,
            }

        tool_calls = _order_tool_calls(model_message.tool_calls)
        state["trace"].completed(
            started_event_id=None,
            agent=AgentName.orchestrator,
            message=f"Mistral selected {len(tool_calls)} tool call(s).",
            metadata=_tool_selection_metadata(tool_calls, step_count),
        )
        return {
            "step_count": step_count,
            "pending_tool_calls": tool_calls,
            "messages": [
                *state["messages"],
                runtime.assistant_tool_call_message(tool_calls),
            ],
        }

    def route_tool_node(state: QueryWorkflowState) -> dict[str, object]:
        pending_tool_calls = list(state.get("pending_tool_calls") or [])
        if not pending_tool_calls:
            return {"current_tool_call": None}

        current_tool_call = pending_tool_calls.pop(0)
        return {
            "current_tool_call": current_tool_call,
            "pending_tool_calls": pending_tool_calls,
        }

    def data_agent_node(state: QueryWorkflowState) -> dict[str, object]:
        return _execute_current_tool(state)

    def excel_agent_node(state: QueryWorkflowState) -> dict[str, object]:
        return _execute_current_tool(state)

    def ppt_agent_node(state: QueryWorkflowState) -> dict[str, object]:
        return _execute_current_tool(state)

    def report_agent_node(state: QueryWorkflowState) -> dict[str, object]:
        return _execute_current_tool(state)

    def sandbox_agent_node(state: QueryWorkflowState) -> dict[str, object]:
        return _execute_current_tool(state)

    def unsupported_tool_node(state: QueryWorkflowState) -> dict[str, object]:
        return _execute_current_tool(state)

    def stop_planning_node(state: QueryWorkflowState) -> dict[str, object]:
        state["trace"].completed(
            started_event_id=state["orchestrator_start_id"],
            agent=AgentName.orchestrator,
            message="Stopped after the maximum orchestration planning steps.",
            metadata={"maxSteps": MAX_PLANNING_STEPS},
        )
        return {}

    def judge_node(state: QueryWorkflowState) -> dict[str, object]:
        runtime = state["runtime"]
        fallback_answer = (
            f"Generated {len(runtime.artifact_refs)} artifact(s)."
            if runtime.artifact_refs
            else "Orchestration completed without file artifacts."
        )
        final_answer = runtime.report_markdown or state.get("answer_markdown") or fallback_answer
        artifact_validations = runtime.validate_generated_artifacts(trace=state["trace"])
        runtime.run_judge(
            trace=state["trace"],
            query=state["request"].query,
            artifacts=runtime.artifact_refs,
            artifact_validations=artifact_validations,
            answer_markdown=final_answer,
            sandbox_output=runtime.sandbox_output,
            tool_calls=state["tool_call_records"],
        )

        decision = runtime.judge_decision
        if decision and _should_force_revision(decision, artifact_validations):
            decision = JudgeDecision(
                status=JudgeStatus.needs_revision,
                reason=(
                    f"Judge overall score {decision.scores.overall}/100 is below "
                    f"the {JUDGE_APPROVAL_THRESHOLD}/100 approval threshold."
                ),
                scores=decision.scores,
                critical_failures=decision.critical_failures,
                target_agent=decision.target_agent or _fallback_revision_target(artifact_validations),
                revision_instructions=decision.revision_instructions
                or _score_revision_instructions(decision),
            )
            runtime.set_judge_decision(decision)
            state["trace"].retrying(
                agent=AgentName.judge,
                message=f"Judge score {decision.scores.overall}/100 requires revision.",
                metadata={
                    "threshold": JUDGE_APPROVAL_THRESHOLD,
                    "scores": decision.scores.model_dump(by_alias=True),
                    "targetAgent": decision.target_agent,
                },
            )

        if (
            decision
            and decision.status == JudgeStatus.needs_revision
            and state.get("revision_count", 0) >= MAX_REVISION_ATTEMPTS
        ):
            decision = JudgeDecision(
                status=JudgeStatus.failed_after_retry,
                reason=f"Judge still requested revision after {MAX_REVISION_ATTEMPTS} targeted retry.",
                scores=decision.scores,
                critical_failures=decision.critical_failures,
                target_agent=decision.target_agent,
                revision_instructions=decision.revision_instructions,
            )
            runtime.set_judge_decision(decision)
            state["trace"].failed(
                started_event_id=None,
                agent=AgentName.judge,
                message="Judge requested another revision after the retry limit.",
                metadata={"targetAgent": decision.target_agent},
            )

        return {
            "final_answer": final_answer,
            "artifacts": runtime.artifact_refs,
            "artifact_validations": artifact_validations,
            "sandbox_output": runtime.sandbox_output,
            "judge_decision": decision,
        }

    def prepare_revision_node(state: QueryWorkflowState) -> dict[str, object]:
        decision = state.get("judge_decision")
        if decision is None:
            return {"current_tool_call": None, "active_revision": False}

        tool_name = _tool_name_for_judge_target(decision.target_agent)
        if tool_name is None:
            failed_decision = JudgeDecision(
                status=JudgeStatus.failed_after_retry,
                reason=f"Judge requested a revision for an unsupported target: {decision.target_agent}.",
                target_agent=decision.target_agent,
                revision_instructions=decision.revision_instructions,
            )
            state["runtime"].set_judge_decision(failed_decision)
            state["trace"].failed(
                started_event_id=None,
                agent=AgentName.judge,
                message="Judge revision target could not be routed to a graph node.",
                metadata={"targetAgent": decision.target_agent},
            )
            return {
                "judge_decision": failed_decision,
                "current_tool_call": None,
                "active_revision": False,
            }

        revision_instructions = decision.revision_instructions or decision.reason
        revision_call = MistralToolCall(
            id=f"revision_{uuid4().hex[:12]}",
            name=tool_name,
            arguments=_revision_arguments(
                tool_name=tool_name,
                state=state,
                revision_instructions=revision_instructions,
            ),
        )
        revision_count = state.get("revision_count", 0) + 1
        revision_record = {
            "attempt": revision_count,
            "targetAgent": decision.target_agent,
            "toolName": tool_name,
            "instructions": revision_instructions,
        }

        state["runtime"].prepare_for_revision(tool_name)
        state["trace"].retrying(
            agent=AGENT_BY_TOOL_NAME.get(tool_name, AgentName.orchestrator),
            message=f"Routing judge revision to {AGENT_BY_TOOL_NAME.get(tool_name, AgentName.orchestrator).value} agent.",
            metadata=revision_record,
        )

        return {
            "current_tool_call": revision_call,
            "active_revision": True,
            "revision_count": revision_count,
            "revision_history": [*state.get("revision_history", []), revision_record],
        }

    def finalize_node(state: QueryWorkflowState) -> dict[str, QueryResponse]:
        request = state["request"]
        response = QueryResponse(
            request_id=state["request_id"],
            query=request.query,
            answer_markdown=state["final_answer"],
            artifacts=state["artifacts"],
            artifact_validations=state.get("artifact_validations", []),
            sandbox_output=state.get("sandbox_output"),
            trace=state["trace"].events if request.include_trace else [],
            judge_decision=state.get("judge_decision"),
            metadata={
                "toolCalls": state["tool_call_records"],
                "implementedTools": list(TOOL_NODE_BY_NAME.keys()),
                "pendingTools": [],
                "workflow": "langgraph",
                "graphNodes": GRAPH_NODES,
                "revisionAttempts": state.get("revision_count", 0),
                "revisionHistory": state.get("revision_history", []),
                "inferredFilters": _inferred_data_filters(state["tool_call_records"]),
                "physicianCount": len(state["runtime"].physician_context),
                "physicianPreview": state["runtime"].physician_context[:12],
            },
        )
        return {"response": response}

    def after_plan(state: QueryWorkflowState) -> str:
        if state.get("pending_tool_calls"):
            return "route_tool"
        return "judge"

    def route_current_tool(state: QueryWorkflowState) -> str:
        tool_call = state.get("current_tool_call")
        if tool_call is None:
            return "unsupported_tool"
        return TOOL_NODE_BY_NAME.get(tool_call.name, "unsupported_tool")

    def after_tool(state: QueryWorkflowState) -> str:
        if state.get("active_revision"):
            return "judge"
        if state.get("pending_tool_calls"):
            return "route_tool"
        if state["step_count"] >= MAX_PLANNING_STEPS:
            return "stop_planning"
        return "plan"

    def after_judge(state: QueryWorkflowState) -> str:
        decision = state.get("judge_decision")
        if (
            decision
            and decision.status == JudgeStatus.needs_revision
            and state.get("revision_count", 0) < MAX_REVISION_ATTEMPTS
        ):
            return "prepare_revision"
        return "finalize"

    def after_prepare_revision(state: QueryWorkflowState) -> str:
        if state.get("current_tool_call") is None:
            return "finalize"
        return route_current_tool(state)

    graph.add_node("initialize", initialize_node)
    graph.add_node("plan", plan_node)
    graph.add_node("route_tool", route_tool_node)
    graph.add_node("data_agent", data_agent_node)
    graph.add_node("excel_agent", excel_agent_node)
    graph.add_node("ppt_agent", ppt_agent_node)
    graph.add_node("report_agent", report_agent_node)
    graph.add_node("sandbox_agent", sandbox_agent_node)
    graph.add_node("unsupported_tool", unsupported_tool_node)
    graph.add_node("stop_planning", stop_planning_node)
    graph.add_node("judge", judge_node)
    graph.add_node("prepare_revision", prepare_revision_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "initialize")
    graph.add_edge("initialize", "plan")
    graph.add_conditional_edges("plan", after_plan)
    graph.add_conditional_edges("route_tool", route_current_tool)
    graph.add_conditional_edges("data_agent", after_tool)
    graph.add_conditional_edges("excel_agent", after_tool)
    graph.add_conditional_edges("ppt_agent", after_tool)
    graph.add_conditional_edges("report_agent", after_tool)
    graph.add_conditional_edges("sandbox_agent", after_tool)
    graph.add_conditional_edges("unsupported_tool", after_tool)
    graph.add_edge("stop_planning", "judge")
    graph.add_conditional_edges("judge", after_judge)
    graph.add_conditional_edges("prepare_revision", after_prepare_revision)
    graph.add_edge("finalize", END)

    compiled = graph.compile()
    final_state = compiled.invoke({"request": request})
    response = final_state.get("response")
    if response is None:
        raise RuntimeError("Query workflow completed without a response.")
    return response


def _execute_current_tool(state: QueryWorkflowState) -> dict[str, object]:
    tool_call = state.get("current_tool_call")
    if tool_call is None:
        return {}

    runtime = state["runtime"]
    messages = list(state["messages"])
    tool_call_records = list(state["tool_call_records"])
    is_revision = bool(state.get("active_revision"))
    record = {
        "id": tool_call.id,
        "name": tool_call.name,
        "arguments": tool_call.arguments,
        "isRevision": is_revision,
    }
    if is_revision:
        record["revisionAttempt"] = state.get("revision_count", 0)
    tool_call_records.append(record)

    tool_result = runtime.execute_tool(tool_call, state["trace"])
    messages.append(
        {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": tool_call.name,
            "content": _json_dumps(tool_result),
        }
    )

    return {
        "messages": messages,
        "tool_call_records": tool_call_records,
        "current_tool_call": None,
    }


def _order_tool_calls(tool_calls: list[MistralToolCall]) -> list[MistralToolCall]:
    return sorted(tool_calls, key=lambda tool_call: TOOL_EXECUTION_ORDER.get(tool_call.name, 99))


def _missing_required_followup_tool(state: QueryWorkflowState) -> MistralToolCall | None:
    request = state["request"]
    runtime = state["runtime"]
    tool_records = state.get("tool_call_records", [])

    if (
        _query_requires_sandbox(request.query)
        and runtime.physician_context
        and runtime.sandbox_output is None
        and not _tool_was_called("call_sandbox_agent", tool_records)
    ):
        return MistralToolCall(
            id=f"guard_{uuid4().hex[:12]}",
            name="call_sandbox_agent",
            arguments={
                "code_goal": request.query,
                "dataset": runtime.physician_context,
                "chart_type": "bar" if _query_likely_wants_chart(request.query) else None,
            },
        )

    return None


def _query_requires_sandbox(query: str) -> bool:
    normalized = query.lower()
    analysis_terms = [
        "analysis",
        "analyze",
        "show me which",
        "which states",
        "highest",
        "lowest",
        "rank",
        "ranking",
        "concentration",
        "distribution",
        "compare",
        "chart",
        "plot",
    ]
    return any(term in normalized for term in analysis_terms)


def _query_likely_wants_chart(query: str) -> bool:
    normalized = query.lower()
    return any(term in normalized for term in ["chart", "plot", "distribution", "concentration", "compare"])


def _tool_was_called(tool_name: str, tool_call_records: list[dict[str, object]]) -> bool:
    return any(record.get("name") == tool_name for record in tool_call_records)


def _tool_selection_metadata(tool_calls: list[MistralToolCall], step_count: int) -> dict[str, object]:
    return {
        "planningStep": step_count,
        "selectedTools": [tool_call.name for tool_call in tool_calls],
        "artifactRequests": _artifact_requests(tool_calls),
        "inferredFilters": _inferred_filters_from_tool_calls(tool_calls),
    }


def _artifact_requests(tool_calls: list[MistralToolCall]) -> list[str]:
    artifacts: list[str] = []
    for tool_call in tool_calls:
        if tool_call.name == "call_ppt_agent":
            artifacts.append("pptx")
        elif tool_call.name == "call_excel_agent":
            artifacts.append("xlsx")
        elif tool_call.name == "call_report_agent":
            artifacts.append("markdown")
        elif tool_call.name == "call_sandbox_agent":
            artifacts.append("analysis")
    return artifacts


def _inferred_filters_from_tool_calls(tool_calls: list[MistralToolCall]) -> dict[str, object]:
    for tool_call in tool_calls:
        if tool_call.name != "get_physician_data":
            continue
        return _normalize_filter_arguments(tool_call.arguments)
    return {}


def _inferred_data_filters(tool_call_records: list[dict[str, object]]) -> dict[str, object]:
    for record in tool_call_records:
        if record.get("name") != "get_physician_data":
            continue
        arguments = record.get("arguments")
        if not isinstance(arguments, dict):
            return {}
        return _normalize_filter_arguments(arguments)
    return {}


def _normalize_filter_arguments(arguments: dict[str, object]) -> dict[str, object]:
    return {
        "specialty": arguments.get("specialty") or [],
        "states": arguments.get("state") or [],
        "regions": arguments.get("region") or [],
        "icd10Codes": arguments.get("icd10_codes") or [],
        "volumeThreshold": arguments.get("volume_threshold"),
        "boardCertified": arguments.get("board_certified"),
    }


def _tool_name_for_judge_target(target_agent: str | None) -> str | None:
    if not target_agent:
        return None

    normalized = target_agent.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "data": "get_physician_data",
        "data_agent": "get_physician_data",
        "physician_data": "get_physician_data",
        "get_physician_data": "get_physician_data",
        "excel": "call_excel_agent",
        "excel_agent": "call_excel_agent",
        "spreadsheet": "call_excel_agent",
        "xlsx": "call_excel_agent",
        "call_excel_agent": "call_excel_agent",
        "ppt": "call_ppt_agent",
        "ppt_agent": "call_ppt_agent",
        "powerpoint": "call_ppt_agent",
        "powerpoint_agent": "call_ppt_agent",
        "slide": "call_ppt_agent",
        "slides": "call_ppt_agent",
        "call_ppt_agent": "call_ppt_agent",
        "report": "call_report_agent",
        "report_agent": "call_report_agent",
        "markdown": "call_report_agent",
        "call_report_agent": "call_report_agent",
        "sandbox": "call_sandbox_agent",
        "sandbox_agent": "call_sandbox_agent",
        "analysis": "call_sandbox_agent",
        "code": "call_sandbox_agent",
        "call_sandbox_agent": "call_sandbox_agent",
    }
    return aliases.get(normalized)


def _revision_arguments(
    *,
    tool_name: str,
    state: QueryWorkflowState,
    revision_instructions: str,
) -> dict[str, object]:
    previous = _latest_tool_record_for(tool_name, state.get("tool_call_records", []))
    arguments = dict(previous.get("arguments", {})) if previous else _default_revision_arguments(tool_name, state)
    runtime = state["runtime"]

    if tool_name in {"call_excel_agent", "call_ppt_agent", "call_report_agent"} and not arguments.get("physician_list"):
        arguments["physician_list"] = runtime.physician_context
    if tool_name == "call_sandbox_agent" and not arguments.get("dataset"):
        arguments["dataset"] = runtime.physician_context

    arguments["revision_instructions"] = revision_instructions

    if tool_name == "call_sandbox_agent":
        code_goal = str(arguments.get("code_goal") or "Analyze the filtered physician dataset.")
        arguments["code_goal"] = f"{code_goal}\nRevision instructions: {revision_instructions}"
    if tool_name == "call_ppt_agent":
        style_notes = arguments.get("style_notes")
        arguments["style_notes"] = _append_instruction(style_notes, revision_instructions)
    if tool_name == "call_report_agent":
        sections = arguments.get("sections") or [
            "Executive Summary",
            "Physician Landscape Overview",
            "Geographic & Specialty Distribution",
            "Key Insights & Implications",
            "Recommended Next Steps",
        ]
        arguments["sections"] = sections

    return arguments


def _latest_tool_record_for(
    tool_name: str,
    tool_call_records: list[dict[str, object]],
) -> dict[str, object] | None:
    for record in reversed(tool_call_records):
        if record.get("name") == tool_name:
            return record
    return None


def _default_revision_arguments(tool_name: str, state: QueryWorkflowState) -> dict[str, object]:
    request = state["request"]
    runtime = state["runtime"]
    preferences = request.preferences

    if tool_name == "get_physician_data":
        return {
            "specialty": preferences.specialties,
            "state": preferences.states,
            "region": preferences.regions,
            "icd10_codes": preferences.icd10_codes,
            "volume_threshold": preferences.volume_threshold.value if preferences.volume_threshold else None,
            "board_certified": preferences.board_certified,
        }
    if tool_name == "call_excel_agent":
        return {
            "analysis_type": "physician_breakdown",
            "physician_list": runtime.physician_context,
            "dimensions": ["state", "specialty", "icd10_code"],
            "icd10_codes": preferences.icd10_codes,
        }
    if tool_name == "call_ppt_agent":
        return {
            "topic": request.query[:120],
            "physician_list": runtime.physician_context,
            "icd10_codes": preferences.icd10_codes,
            "slide_count": 4,
        }
    if tool_name == "call_report_agent":
        return {
            "report_type": "Physician Landscape Report",
            "sections": [
                "Executive Summary",
                "Physician Landscape Overview",
                "Geographic & Specialty Distribution",
                "Key Insights & Implications",
                "Recommended Next Steps",
            ],
            "physician_list": runtime.physician_context,
            "icd10_context": preferences.icd10_codes,
            "geographic_scope": [*preferences.states, *preferences.regions],
        }
    if tool_name == "call_sandbox_agent":
        return {
            "code_goal": request.query,
            "dataset": runtime.physician_context,
            "chart_type": "bar",
        }
    return {}


def _append_instruction(existing: object, revision_instructions: str) -> str:
    if isinstance(existing, str) and existing.strip():
        return f"{existing}\nRevision instructions: {revision_instructions}"
    return f"Revision instructions: {revision_instructions}"


def _json_dumps(value: object) -> str:
    import json

    return json.dumps(value)


def _should_force_revision(
    decision: JudgeDecision,
    artifact_validations: list[ArtifactValidationResult],
) -> bool:
    if decision.status != JudgeStatus.approved:
        return False
    if decision.scores.overall < JUDGE_APPROVAL_THRESHOLD:
        return True
    return any(not validation.passed for validation in artifact_validations)


def _fallback_revision_target(artifact_validations: list[ArtifactValidationResult]) -> str:
    failed = [validation for validation in artifact_validations if not validation.passed]
    if failed:
        return failed[0].source_agent
    if artifact_validations:
        return min(artifact_validations, key=lambda validation: validation.score).source_agent
    return "report"


def _score_revision_instructions(decision: JudgeDecision) -> str:
    scores = decision.scores.model_dump(by_alias=True)
    score_text = ", ".join(f"{key}: {value}" for key, value in scores.items())
    return (
        "Revise the output to raise the judge score above "
        f"{JUDGE_APPROVAL_THRESHOLD}/100. Current scores: {score_text}. "
        f"Reason: {decision.reason}"
    )
