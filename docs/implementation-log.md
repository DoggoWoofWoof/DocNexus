# Implementation Log

This file records the sequence of implementation decisions so the project history is easy to explain during review.

## 2026-05-28 - Architecture And First Backend Slice

What changed:

- Added the initial README with stack selection, architecture diagram, agent design, sandbox strategy, and development plan.
- Added architecture decision records for FastAPI, Mistral, LangGraph, SQLite, artifact generation, E2B/local sandboxing, and React/Vite.
- Added `.env.example`, `.gitignore`, and `requirements.txt`.
- Created the FastAPI backend skeleton under `backend/app`.
- Added a seeded mock physician dataset with 36 records across specialties, states, ICD-10 profiles, and volume tiers.
- Added SQLite/SQLModel database initialization and idempotent seeding.
- Added `GET /health` for environment and dependency readiness.
- Added `GET /physicians` with filters for specialty, state, region, ICD-10 codes, volume threshold, and board certification.

Why this came first:

- The assignment's agents all need grounded physician data, so the dataset and filtering service are the foundation.
- Starting with `/health` and `/physicians` gives a testable backend before introducing LLM calls.
- The orchestrator will later call the same physician service through the `get_physician_data` tool, which avoids duplicate data-access logic.
- Documentation was updated alongside code so architectural decisions remain traceable.

Notes:

- `volume_threshold=high` is treated as a minimum threshold, so it includes both `high` and `very_high` physicians.
- Region filtering currently supports `northeast`, `west`, `south`, and `midwest`.
- The physician seed data is mock data for demo purposes only.

## 2026-05-28 - Orchestration Contract

What changed:

- Added shared camelCase schema support for API contracts.
- Added query request/response schemas.
- Added artifact reference, trace event, judge decision, sandbox output, and tool-call schemas.
- Added Mistral-style orchestrator tool definitions for all required assignment tools.
- Added prompt files for the orchestrator, PPT Agent, Excel Agent, Report Agent, Sandbox Agent, and Judge Agent.
- Added `docs/orchestration-contract.md` to describe the planned `/query` boundary and trace model.

Why this came next:

- The orchestrator should not be built as a vague blob of code. It needs typed contracts before the Mistral client and LangGraph workflow are added.
- Tool schemas make the requirement explicit: Mistral will decide routing through native tool/function calling, while backend services will execute the tools.
- Prompt files are part of the assignment's evaluation surface, so they should be source-controlled from the beginning.

Notes:

- `POST /query` is not implemented yet. This step intentionally defines the contract without faking routing.
- The next implementation step should add the Mistral client and a minimal LangGraph workflow that can call `get_physician_data`.

## 2026-05-29 - Query Orchestration Shell

What changed:

- Added a prompt loader for source-controlled prompt files.
- Added a trace builder for started/completed/failed/skipped events.
- Added a Mistral client wrapper for native tool/function calling.
- Added an orchestrator service that sends the query and tool schemas to Mistral.
- Added execution support for the `get_physician_data` tool using the existing physician service.
- Added `POST /query`.
- Artifact-agent calls are traced as pending/skipped until those agents are implemented.

Why this came next:

- It connects the architecture to the assignment's core requirement: the LLM chooses tools through native function calling.
- The data retrieval tool now reuses the same deterministic service as `GET /physicians`.
- The endpoint fails gracefully when `MISTRAL_API_KEY` is missing, which makes local setup easier to debug.

Verification:

- Created a local `.venv` and installed dependencies.
- Ran backend smoke tests with FastAPI `TestClient`.
- `GET /health` returned `200`.
- `GET /physicians` returned `200` and matched filtered physician data.
- `POST /query` returned `503` with `MISTRAL_API_KEY is not configured`, which is the expected behavior without credentials.

Notes:

- At this point in the build, LangGraph, real artifact agents, the judge node, sandbox execution, and artifact downloads were still pending.

## 2026-05-29 - Excel Artifact Path

What changed:

- Added an artifact database model for generated file metadata.
- Added an artifact registry service.
- Added `GET /artifacts/{id}` for server-side downloads.
- Added the Excel Agent.
- Wired `call_excel_agent` into the orchestrator.
- Added context reuse so Excel generation can use physician records retrieved earlier by `get_physician_data`.

Excel output:

- Sheet 1: `Raw Physician Data`
- Sheet 2: `State x Specialty Summary`
- Sheet 3: `ICD-10 Breakdown`
- Formatting: bold colored headers, alternating row fills, frozen header row, and auto-width columns.

Why this came next:

- Excel is one of the required artifact types and is the fastest useful artifact to implement deterministically.
- It validates the artifact registry/download flow before adding PPTX and DOCX.
- It proves the orchestrator can move from LLM-selected tools to a real downloadable server-side file.

Verification:

- Ran Python compilation across the backend.
- Used a fake Mistral response to trigger `get_physician_data` and `call_excel_agent` without needing an API key.
- Confirmed one `.xlsx` artifact was generated.
- Opened the workbook with `openpyxl` and verified the three required sheet names.
- Downloaded the artifact through `GET /artifacts/{id}` and received `200` with the XLSX MIME type.

Notes:

- PPT, Report, Sandbox, LangGraph, and Judge Agent execution are still pending.

## 2026-05-29 - PPT Artifact Path

What changed:

- Added the PPT Agent.
- Wired `call_ppt_agent` into the orchestrator.
- Reused filtered physician context from `get_physician_data`.
- Registered generated PPTX files in the artifact store.

PPT output:

- Slide 1: title slide with query summary, physician count, ICD-10 scope, and geography scope
- Slide 2: physician population overview with key metrics and ranked lists
- Slide 3: grounded key insights
- Slide 4: top 10 physicians by NSCLC claim volume

Why this came next:

- The assignment's expected walkthrough includes a query that produces both PowerPoint and Excel artifacts.
- Adding PPT after Excel validates that the orchestrator can fan out to multiple artifact agents using the same filtered data.

Verification:

- Ran Python compilation across the backend.
- Used a fake Mistral response to trigger `get_physician_data`, `call_ppt_agent`, and `call_excel_agent`.
- Confirmed one `.pptx` and one `.xlsx` artifact were generated.
- Opened the PPTX with `python-pptx` and verified it contains 4 slides.
- Opened the workbook with `openpyxl` and verified the required sheets.
- Downloaded both artifacts through `GET /artifacts/{id}` and received `200` with the expected MIME types.

Notes:

- Report, Sandbox, LangGraph, and Judge Agent execution are still pending.

## 2026-05-29 - Report Agent Path

What changed:

- Added plain text completion support to the Mistral client wrapper.
- Added the Report Agent.
- Wired `call_report_agent` into the orchestrator.
- Saved generated report markdown as a downloadable artifact.
- Returned generated markdown as `answerMarkdown` for UI rendering.

Why this came next:

- Written reports are one of the required output types.
- The Report Agent should be prompt-driven rather than a hardcoded template, so it uses its own source-controlled system prompt and a separate Mistral text completion call.
- Returning markdown directly keeps the UI simple while still allowing downloads through the artifact endpoint.

Verification:

- Ran Python compilation across the backend.
- Used a fake Mistral planner and fake report text completion to trigger `get_physician_data` and `call_report_agent`.
- Confirmed markdown was returned in the query response.
- Confirmed a `.md` artifact was written.
- Downloaded the markdown artifact through `GET /artifacts/{id}` and received `200` with `text/markdown`.

Notes:

- Optional DOCX export is still pending.
- Sandbox, LangGraph, and Judge Agent execution are still pending.

## 2026-05-29 - Sandbox Agent Local Execution

What changed:

- Added the Sandbox Agent.
- Added restricted local Python `exec()` subprocess execution.
- Added AST validation to block imports and dangerous calls.
- Added one retry path for failed generated code.
- Wired `call_sandbox_agent` into the orchestrator.
- Registered generated chart images as downloadable PNG artifacts.
- Returned sandbox code, stdout, stderr, execution status, and chart artifact id in the query response.

Why this came next:

- Sandbox execution is a major assignment criterion.
- The user specifically remembered a Python `exec()` sandbox pattern from a previous project, so this implementation follows that idea while keeping execution out of the FastAPI process.
- The local subprocess runner keeps the project demoable without requiring E2B credentials.

Verification:

- Ran Python compilation across the backend.
- Used fake Mistral tool calls and fake generated Python code to trigger `get_physician_data` and `call_sandbox_agent`.
- Confirmed the sandbox subprocess completed.
- Confirmed stdout contained state-level NSCLC claim output.
- Confirmed `chart.png` was generated and registered as a `chart_png` artifact.
- Downloaded the chart through `GET /artifacts/{id}` and received `200` with `image/png`.

Notes:

- This local runner is not presented as production-grade arbitrary-code isolation.
- E2B integration remains a future hardening step.
- LangGraph and Judge Agent execution are still pending.

## 2026-05-29 - React Frontend

What changed:

- Added a React + Vite + TypeScript frontend.
- Added typed API helpers for `/query`, `/physicians`, and artifact downloads.
- Built the main query workspace UI.
- Added preference controls for ICD-10 codes, states, regions, specialties, volume threshold, and board certification.
- Added sample query buttons.
- Added agent trace rendering.
- Added markdown result rendering.
- Added artifact download links.
- Added sandbox code/stdout/stderr/chart rendering.
- Added physician preview table.

Why this came next:

- The backend now has enough functionality to support a real demo experience.
- The assignment requires a clean single-page UI with trace, rendered results, and downloads.
- Building the UI now makes remaining gaps easier to see from a user's perspective.

Verification:

- Installed frontend dependencies.
- Ran `npm run build`; production build passed.
- Started the Vite dev server and confirmed `http://127.0.0.1:5173` returned `200`.

Notes:

- Browser visual QA was attempted with the Codex in-app Browser plugin, but the plugin failed to attach in this Windows sandbox.
- Manual browser verification is still recommended once the local app is opened normally.

## 2026-05-29 - Judge Agent

What changed:

- Updated the Judge Agent prompt to require strict JSON.
- Added the Judge Agent service.
- Wired judge execution into the end of the orchestrator flow.
- Added `judgeDecision` to query responses.
- Added judge trace events.

Why this came next:

- The original architecture called for an LLM-as-judge quality gate.
- The judge gives the demo a stronger orchestration story than simple tool execution.
- It creates a future path for targeted revision loops without restarting the entire workflow.

Verification:

- Ran Python compilation across the backend.
- Used fake Mistral tool calls and fake judge JSON.
- Confirmed `judgeDecision.status` returned `approved`.
- Confirmed the trace includes a `judge` event.

Notes:

- The judge currently evaluates and reports a decision. The targeted revision loop is still a future enhancement.
- LangGraph workflow integration is still pending.

## 2026-05-29 - LangGraph Query Workflow

What changed:

- Replaced the one-node LangGraph wrapper with an explicit multi-node `StateGraph`.
- Added graph nodes for `initialize`, `plan`, `execute_tools`, `stop_planning`, `judge`, and `finalize`.
- Added conditional edges from `plan` to either `execute_tools` or `judge`.
- Added conditional edges from `execute_tools` back to `plan` until the maximum planning step limit is reached.
- Added graph metadata to query responses.

Why this came next:

- The selected architecture uses LangGraph for stateful orchestration.
- This moves the planning loop itself into LangGraph instead of hiding it inside a service method.
- It makes the system easier to explain in the demo: Mistral chooses tools, LangGraph controls state and loop edges, and backend services execute tools.
- Future work can still split each specialized tool into its own graph node for finer-grained graph visualization and targeted revision.

Verification:

- Ran Python compilation across the backend.
- Called `POST /query` without `MISTRAL_API_KEY` and confirmed it still returns the expected graceful `503`.
- Ran a fake full workflow through `run_query_workflow`.
- Confirmed graph metadata reports `workflow=langgraph`.
- Confirmed generated artifact types included PPTX, XLSX, markdown, and chart PNG.
- Confirmed the judge returned `approved`.
- Confirmed sandbox execution completed.
- Confirmed PPTX and XLSX outputs remained structurally valid.

## 2026-05-29 - Per-Agent LangGraph Nodes And Revision Edge

What changed:

- Replaced the generic `execute_tools` graph node with explicit `data_agent`, `excel_agent`, `ppt_agent`, `report_agent`, and `sandbox_agent` nodes.
- Added a `route_tool` node that dispatches Mistral tool calls to the matching graph node.
- Added `prepare_revision`, which maps judge targets such as `report`, `excel`, `ppt`, and `sandbox` back to the corresponding tool call.
- Added a one-attempt revision edge: `judge -> prepare_revision -> targeted agent -> judge`.
- Added `revisionAttempts`, `revisionHistory`, and per-tool `isRevision` metadata to query responses.
- Added a trace `retrying` status so targeted judge retries are visible in the UI trace.
- Passed judge revision instructions into report and sandbox prompts, plus tool argument metadata for PPT and Excel reruns.
- Removed stale response artifact references for the revised agent before adding the revised output.

Why this came next:

- This completes the architectural reason for using LangGraph instead of a single LangChain-style chain.
- The graph now expresses real branch and retry behavior instead of only wrapping a service loop.
- The revision path keeps the workflow efficient because a report problem does not force the deck, workbook, sandbox, and data retrieval to restart.

Verification:

- Ran Python compilation across the backend.
- Ran a fake full workflow through `run_query_workflow`.
- Confirmed graph metadata now reports per-agent nodes.
- Confirmed generated artifact types included PPTX, XLSX, markdown, and chart PNG.
- Ran a fake judge revision workflow where the first judge decision returned `needs_revision` for `report`.
- Confirmed the graph reran only `call_report_agent` as a revision and the second judge returned `approved`.
- Confirmed response metadata showed `revisionAttempts=1` and the revised report became the final answer.

## 2026-05-29 - Demo Seed Alignment

What changed:

- Tuned the mock physician seed data so the assignment's expected CA/NY high-volume Medical Oncology walkthrough returns 12 physicians.
- Changed startup seeding from first-run insert-only behavior to upsert behavior so an existing local `docnexus.db` picks up seed corrections automatically.

Why this came next:

- The original assignment gives a concrete end-to-end expected query and says to use it for validation.
- Matching that query exactly makes the live demo easier to trust and easier to compare against the rubric.

Verification:

- Confirmed the seed file still contains 36 physician records.
- Confirmed `Medical Oncology` + CA/NY + `C341,C342` + `volume_threshold=high` returns 12 records.
- Confirmed `GET /physicians` returns `count=12` for the same filter after application startup.

## 2026-05-29 - Live Streaming Trace

What changed:

- Added an optional trace callback to `TraceBuilder` so every trace event can be emitted as it is recorded.
- Added `POST /query/stream`, which runs the same LangGraph workflow and streams newline-delimited JSON events.
- Kept `POST /query` unchanged for non-streaming clients.
- Updated the React API client to consume the readable response stream with `fetch()`.
- Updated the UI so trace events append immediately while the workflow is still running.
- Added frontend types for `QueryStreamEvent` and `JudgeDecision`.
- Added trace styling for `started`, `retrying`, and `skipped` statuses.
- Documented the streaming contract and the POST + NDJSON architecture decision.

Why this came next:

- The original assignment explicitly asks for a live agent trace as agents are called.
- Streaming trace makes the multi-agent behavior visible during long-running artifact and sandbox work.
- POST + NDJSON keeps the request payload clean while avoiding `EventSource`'s GET-only limitation.

Verification:

- Ran Python compilation across the backend.
- Built the frontend with `npm run build`.
- Tested `POST /query/stream` with a fake Mistral client.
- Confirmed the stream emitted multiple `trace` events followed by one `result` event.
- Confirmed `/query/stream` returns the expected `503` when `MISTRAL_API_KEY` is missing.

## 2026-05-29 - Artifact Provenance Hashes

What changed:

- Added request, tool call, prompt, input, artifact hash, file size, and provenance fields to artifact metadata.
- Added SQLite startup migration logic so existing local databases receive the new nullable artifact columns.
- Added stable SHA-256 helpers for prompt text, structured input payloads, and generated files.
- Updated PPT, Excel, Report, and Sandbox artifact generation to finalize file hashes after writing files.
- Returned provenance fields in `ArtifactRef` API responses.
- Updated README and orchestration contract documentation.

Why this came next:

- Artifact traceability is a strong interview story for agent systems.
- The judge and trace layers need more than a filename to explain why an artifact is grounded.
- Prompt and input hashes make it possible to answer which prompt and structured payload produced a file.

Verification:

- Ran Python compilation across the backend.
- Ran a fake LangGraph workflow that generated an Excel artifact.
- Confirmed the response artifact included `requestId`, `toolCallId`, `promptSha256`, `inputSha256`, `artifactSha256`, `fileSizeBytes`, and provenance metadata.

## 2026-05-29 - Deterministic Artifact Validation

What changed:

- Added `ArtifactValidationCheck` and `ArtifactValidationResult` response schemas.
- Added deterministic validators for PPTX, XLSX, markdown report, and chart artifacts.
- Added `artifactValidations` to query responses.
- Added a validation step before the LLM judge runs.
- Passed validation results into the judge prompt payload.
- Emitted validation scores in trace metadata.
- Updated frontend response types and documentation.

Why this came next:

- The LLM judge should not have to infer file correctness from filenames alone.
- Deterministic checks are better for structural requirements such as required workbook sheets and slide counts.
- The LLM judge can then focus on semantic quality, relevance, grounding, and preference alignment.

Verification:

- Ran Python compilation across the backend.
- Ran a fake LangGraph workflow that generated an Excel artifact.
- Confirmed the validator returned `passed=true` and `score=100`.
- Confirmed the judge received `artifactValidations`.
- Confirmed the trace includes the deterministic validation step.

## 2026-05-29 - Judge Scoring Rubric

What changed:

- Added `JudgeScores` with relevance, completion, grounding, artifact quality, preference alignment, and overall metrics.
- Updated the Judge Agent prompt to require score JSON and critical failures.
- Added fallback score handling for older or malformed judge responses.
- Added an 85/100 approval threshold in the LangGraph workflow.
- Forced targeted revision when the judge returns `approved` but the overall score is below threshold.
- Included judge score summaries in trace metadata and trace messages.
- Added a compact judge scorecard to the React results panel.

Why this came next:

- A scorecard makes the LLM-as-judge behavior easier to defend in interviews.
- It gives the revision edge a measurable trigger instead of relying only on a binary label.
- The UI can show quality progression when the graph reruns a targeted agent.

Verification:

- Ran Python compilation across the backend.
- Ran a fake workflow where the first judge response returned `approved` with `overall=70`.
- Confirmed LangGraph converted that into a targeted Excel revision.
- Confirmed the second judge response with `overall=92` approved the final result.
- Confirmed trace messages include both judge scores.

## 2026-05-29 - LLM Plans For PPT And Excel Agents

What changed:

- Added focused LLM planning calls inside the PPT Agent and Excel Agent.
- Updated `ppt_agent.md` to require structured JSON with title, subtitle, insight bullets, and table rationale.
- Updated `excel_agent.md` to require structured JSON with workbook title, summary, sheet plan, and analysis notes.
- Kept `python-pptx` and `openpyxl` as deterministic renderers for real file generation.
- Stored each agent's LLM plan in artifact provenance under `llmPlan`.
- Passed PPT and Excel planning calls through the existing Mistral text-generation wrapper.

Why this came next:

- The assignment says each specialized agent should be a focused LLM call or code-execution step with its own system prompt.
- This removes ambiguity around PPT and Excel agents being purely deterministic services.
- The judge can now inspect both the rendered file validation and the LLM content plan that drove the artifact.

Verification:

- Ran Python compilation across the backend.
- Ran a fake workflow that generated both PPTX and XLSX artifacts.
- Confirmed both returned artifacts included `provenance.llmPlan`.
- Confirmed deterministic validators passed for both generated files.
- Confirmed the judge received the planned artifacts and returned a scored approval.

## 2026-05-29 - E2B Sandbox Execution And Markdown Table Rendering

What changed:

- Wired `SANDBOX_PROVIDER=e2b` plus `E2B_API_KEY` into the Sandbox Agent execution path.
- Kept the restricted local subprocess runner as an automatic fallback when E2B is unavailable.
- Added `executionProvider` to sandbox outputs and trace metadata.
- Added GitHub-Flavored Markdown rendering in the React UI with `remark-gfm`.
- Normalized compressed markdown table row breaks before rendering.
- Tightened the orchestrator and sandbox prompts so tables use real row-level newlines.
- Allowed both `localhost:5173` and `127.0.0.1:5173` as local frontend origins.

Why this came next:

- The demo should clearly prove whether code ran in E2B or the local fallback.
- The previous UI could show model-generated markdown tables as one unreadable line.
- Local browser testing often uses `127.0.0.1`, while the original CORS config only allowed `localhost`.

Verification:

- Ran backend compilation across `backend/app`.
- Ran the frontend production build.
- Ran a direct sandbox smoke test that executed in E2B and returned `executionProvider=e2b`.

## 2026-05-29 - Query-Only UI And Rich Trace Details

What changed:

- Removed manual ICD/state/specialty/volume inputs from the React UI.
- Sent empty optional override fields from the frontend so Mistral performs natural-language extraction through tool calling.
- Added response metadata for `inferredFilters`, `physicianCount`, and `physicianPreview`.
- Added an orchestrator trace event showing selected tools, artifact intent, and inferred filters.
- Rendered trace metadata as readable chips in the UI instead of hiding it inside JSON.
- Added renderer/provider details to PPT and Excel trace metadata.

Why this came next:

- The demo should feel like natural-language-to-data orchestration, not a manual form wrapped around an LLM.
- Interviewers can now see exactly what the model parsed from the query and which tools the graph selected.
- Rich trace chips make the LangGraph state transitions easier to explain live.

Verification:

- Ran backend compilation across `backend/app`.
- Ran the frontend production build.
- Ran a streamed Mistral smoke test with empty preferences and confirmed the trace included `Medical Oncology`, `CA/NY`, `C341/C342`, and `high`.

## 2026-05-29 - Analysis Routing Guard And Grounding Fix

What changed:

- Added a LangGraph workflow guard for analysis/ranking/concentration queries.
- If Mistral stops after data retrieval for an analysis request, the graph now adds the missing `call_sandbox_agent` step before judging.
- Strengthened the Sandbox Agent prompt to keep concentration analysis grounded in the supplied physician dataset.
- Allowed safe analysis imports such as pandas/matplotlib while still blocking unsafe imports and calls.
- Added validation against hardcoded external population denominators such as state population maps or per-capita claims.
- Updated the Judge Agent prompt to reject external denominators unless they are present in the supplied data.

Why this came next:

- A query asking to "run an analysis" should not end after data retrieval.
- The trace previously showed the judge asking for sandbox work only after the workflow had already reached the retry limit.
- A generated analysis briefly used external state population denominators, which weakened grounding and needed a deterministic guard.

Verification:

- Ran backend compilation for the changed workflow and sandbox modules.
- Ran the frontend production build.
- Ran the exact streamed query: "Run an analysis and show me which states have the highest concentration of high-volume NSCLC prescribers."
- Confirmed the workflow now goes data -> sandbox -> judge, uses E2B, has no failed trace events, avoids external population denominators, and receives judge approval.

## 2026-05-30 - Canonical Agent Context And Sandbox Chart Contract

What changed:

- Made downstream PPT, Excel, Report, and Sandbox agents use the canonical filtered physician context from the data node.
- Updated tool schemas so Mistral does not need to serialize full `physician_list` or `dataset` payloads in tool arguments.
- Added a query-evidence guard that removes invented specialty filters when the user asks for generic NSCLC prescribers instead of a specialty-specific cohort.
- Added sandbox preflight checks for requested charts: generated code must create a real matplotlib plot and save it to `chart.png`.
- Added a sandbox guard against narrowing an already-filtered `high` cohort to only `volumeTier == "very_high"`.
- Improved analysis fallback markdown with the filtered record count, concentration definition, stdout table, and one bound chart artifact.
- Removed the duplicate chart image from the Sandbox Output panel; the chart now appears once in Results and remains downloadable from Artifacts.
- Added short Mistral retry delays for rate-limit responses and deterministic judge resilience when semantic judge calls are temporarily unavailable.

Why this came next:

- Mistral occasionally inferred `Medical Oncology` from generic "NSCLC prescribers", which changed the record count from 30 to 21.
- Mistral also sometimes passed partial physician rows into artifact-agent tool arguments, causing Pydantic validation errors in PPT/Excel/Report flows.
- Sandbox code could print a table without saving a chart, or re-filter the cohort to `very_high`, which made results inconsistent with the data-agent filter semantics.
- The UI should show one chart artifact with a clear writeup, not duplicate chart renderings or a broken `chart.png` markdown link.

Verification:

- Ran backend compilation for the changed agents, schemas, client, and workflow modules.
- Ran the frontend production build.
- Ran a mocked LangGraph analysis workflow where Mistral invented `Medical Oncology` and generated bad `volumeTier == "very_high"` sandbox code.
- Confirmed the guard removed the invented specialty, retrieved 30 records, rejected the bad sandbox code, retried, generated one chart artifact, bound `/artifacts/{id}` into Results, and received judge approval.
- Ran direct PPT, Excel, and Report tool executions with malformed `physician_list` arguments and confirmed all three used the 12 canonical filtered records instead of the bad model-supplied list.
- Restarted the FastAPI backend on `127.0.0.1:8000` and confirmed `/health` returned `status=ok`.

## 2026-05-30 - Optional Preference Panel And Override Enforcement

What changed:

- Added an optional structured preference panel to the React query UI.
- The panel supports ICD-10 codes, states, regions, specialties, volume threshold, and board certification.
- Kept the default experience natural-language-first; the panel starts empty and collapsed.
- Wired non-empty preferences into the `/query/stream` payload.
- Added backend enforcement so structured preferences override model omissions or weaker inferred filters on `get_physician_data`.
- Kept artifact routing in Mistral tool calling; preferences only constrain physician retrieval.
- Updated README and orchestration docs to describe the preference override behavior.

Why this came next:

- The assignment explicitly asks for a query input plus user preference panel.
- The earlier query-only UI was cleaner, but it left a visible compliance gap.
- Backend enforcement prevents the panel from being cosmetic: if the user enters `CA` and `C341`, those constraints are applied even if the model omits them.

Verification:

- Ran frontend production build.
- Ran Python compilation for the LangGraph workflow.
- Ran the required PPT+Excel walkthrough with mocked Mistral calls and confirmed 12 physicians, PPTX+XLSX artifacts, and judge approval.
- Ran a preference override workflow where Mistral supplied no filters and the request preferences supplied `CA`, `C341`, and `high`; confirmed the final inferred filters and physician count came from the structured preferences.

## 2026-05-30 - Parallel PPT And Excel Branches

What changed:

- Added a `parallel_agents` LangGraph node for compatible independent artifact branches.
- PPT and Excel now execute concurrently when Mistral selects both after data retrieval.
- Each parallel branch gets its own SQLModel session and isolated `OrchestratorService`.
- The branches share the canonical filtered physician context and merge generated artifact references back into the main workflow state.
- Made `TraceBuilder` append events under a lock so concurrent trace events are safe to stream.
- Added trace metadata for `parallelTools` so the UI can show which tools ran together.

Why this came next:

- The assignment's expected walkthrough explicitly says PPT and Excel should run in parallel.
- The previous implementation allowed Mistral to select both tools in the same planning step, but the graph drained them serially.
- Running branches with separate database sessions keeps the implementation honest without sharing a mutable SQLAlchemy session across threads.

Verification:

- Ran Python compilation for the workflow, orchestrator, and trace modules.
- Ran a mocked required walkthrough and confirmed the trace now shows `Executing independent agents in parallel`, then both `excel started` and `ppt started` before either completed.
- Confirmed the walkthrough still returns 12 physicians, PPTX + XLSX artifacts, and judge approval.
