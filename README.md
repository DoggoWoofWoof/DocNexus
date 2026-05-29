# DocNexus AI Engineer Intern Assignment

LLM-powered multi-agent orchestration demo for generating physician intelligence artifacts from natural language queries.

## Project Status

This repository is being built for the DocNexus AI Engineer Intern take-home assignment. The current implementation now covers the full demo path: React UI, FastAPI backend, SQLite physician data, Mistral tool-calling orchestration, LangGraph agent routing, artifact generation, sandbox execution, judge feedback, and traceable downloads.

Planned final deliverable:

- Single-page React interface for natural language physician intelligence queries
- FastAPI backend with a LangGraph-managed orchestration workflow
- Mistral native function calling for tool-based routing
- Real downloadable PPTX, XLSX, and optional DOCX artifacts generated server-side
- Sandbox Agent that executes Python analysis code and returns stdout plus charts
- Live agent trace showing the orchestration path and timing

Current implemented slice:

- Architecture documentation and decision log
- `.env.example` with planned runtime configuration
- FastAPI application factory and startup lifecycle
- SQLite database initialization
- Idempotent seed loading for 36 mock physician records
- `GET /health`
- `GET /physicians` with specialty, state, region, ICD-10, volume threshold, and board certification filters
- Query, trace, artifact, tool-call, sandbox, and judge schemas
- Mistral-style orchestrator tool definitions
- `POST /query` LangGraph workflow with Mistral tool calling, per-agent nodes, context reuse, judge evaluation, and targeted revision
- `POST /query/stream` NDJSON endpoint for live trace events plus the final response
- Artifact registry and `GET /artifacts/{id}` downloads
- LLM-backed PPT Agent that plans slide content, then renders real `.pptx` decks through the shared E2B/local sandbox execution layer
- LLM-backed Excel Agent that plans workbook purpose/analysis notes, then renders real `.xlsx` workbooks through the shared E2B/local sandbox execution layer
- LLM-backed Report Agent that returns markdown in the UI response and stores a downloadable `.md` artifact
- LLM-backed Sandbox Agent with E2B execution when configured, restricted local Python subprocess fallback, stdout capture, retry, and chart artifact registration
- LLM Judge Agent that returns an approve/revise/fail decision and appears in the trace
- Per-agent LangGraph nodes with a targeted revision edge from `needs_revision` back to the relevant agent once
- React/Vite frontend with query-only composer, inferred scope display, streaming trace timeline, result rendering, artifact downloads, sandbox output, and physician preview
- Source-controlled prompt files for every planned agent

## Assignment Goal

DocNexus users need to ask questions such as:

- "Give me a PowerPoint slide summarizing top oncologists in California treating NSCLC"
- "Build an Excel breakdown of C341 claim volume by physician specialty and state"
- "Write a two-page market access report on NSCLC physician density in the Northeast"
- "Run an analysis and show me which states have the highest concentration of high-volume NSCLC prescribers"

The system should understand the requested artifact, retrieve relevant mock physician data, route work to specialized agents, generate real files, and display a clear trace of what happened.

## Architecture

```text
User query
        |
        v
React UI
        |
        v
FastAPI backend
        |
        v
LangGraph workflow state
        |
        +--> Mistral orchestrator with native tool calling
        |       |
        |       +--> get_physician_data --> SQLite physician dataset
        |       +--> PPT Agent -----------+
        |       +--> Excel Agent ---------+
        |       +--> Report Agent --------+--> Artifact store --> GET /artifacts/{id}
        |       +--> Sandbox Agent -------+
        |                                  |
        |                                  +--> Shared E2B/local execution layer
        |
        +--> Deterministic artifact validation
        |
        +--> LLM Judge scorecard
                |
                +--> approved --> final response
                +--> needs_revision --> targeted agent node

TraceBuilder streams live events through POST /query/stream back to the React UI.
```

The key design choice is separating model judgment from workflow execution:

- Mistral decides which tools to call using native function calling.
- LangGraph manages state, traceability, retries, and fan-out across agents.
- FastAPI owns deterministic execution, artifact generation, file storage, and API contracts.

## Tech Stack

| Layer | Choice | Why |
| --- | --- | --- |
| Frontend | React + Vite + TypeScript | Fast single-page app setup, strong typing, simple integration with streaming trace events. |
| Styling | Custom CSS | Keeps the UI dependency-light while still supporting a polished operator-style dashboard. |
| Backend | FastAPI | Python-first backend fits LLM orchestration, artifact generation, data analysis, and sandbox execution cleanly. |
| Orchestration | LangGraph | Provides explicit workflow state, branching, retries, and traceable multi-agent execution without hiding the control flow. |
| LLM Provider | Mistral | Supports native function calling and has a free mode suitable for evaluation/prototyping. |
| Database | SQLite | Portable, zero-service storage for seeded mock physician data and a demo-scale artifact registry. |
| ORM | SQLModel or SQLAlchemy | Typed schema, clean filtering, and a path to Postgres if the project grows. |
| PPTX Generation | python-pptx | Server-side generation of real downloadable PowerPoint files. |
| Excel Generation | openpyxl | Server-side generation of real XLSX workbooks with formatting and multiple sheets. |
| Report Output | Markdown first, optional python-docx | Markdown renders well in the UI; DOCX can be added as a downloadable professional report artifact. |
| Analysis | pandas + matplotlib | Reliable tabular analysis and chart output for the Sandbox Agent. |
| Sandbox / Isolated Execution | E2B primary, restricted local subprocess fallback | E2B provides isolated cloud execution for analysis and artifact rendering; local fallback keeps demos usable if E2B is unavailable. |

References:

- Mistral function calling: https://docs.mistral.ai/studio-api/conversations/function-calling
- Mistral rate limits and free mode: https://docs.mistral.ai/admin/user-management-finops/tier
- LangGraph documentation: https://langchain-ai.github.io/langgraph/reference/
- E2B documentation: https://www.e2b.dev/docs
- E2B pricing/free tier: https://e2b.dev/pricing

## Why Mistral

Mistral is a good fit for this assignment because the evaluation requires native tool/function calling rather than fake string-based routing. The orchestrator can expose tools such as `get_physician_data`, `call_ppt_agent`, and `call_excel_agent`; Mistral then returns structured tool calls with arguments.

The free mode is appropriate for an internship take-home because this is an evaluation/prototype workload. The implementation will still keep model names configurable and prompts compact to reduce rate-limit risk during the demo.

Planned default:

```env
LLM_PROVIDER=mistral
MISTRAL_MODEL=mistral-small-latest
```

The final demo can switch to a stronger Mistral model if needed by changing environment configuration.

## Why LangGraph Instead Of LangChain-Only

LangChain alone is useful for prompts, model wrappers, and tools, but this assignment is fundamentally about a multi-agent workflow:

- A query can route to one agent or several agents.
- Agents may run in parallel after data retrieval.
- The UI must show a live trace of routing and progress.
- The Sandbox Agent needs retry/self-correction behavior.
- Outputs from one step should be passed as structured state to later steps.

LangGraph gives us an explicit state machine for these requirements. The current `/query` graph is:

```text
START
  -> initialize
  -> plan
  -> route_tool
  -> data_agent | excel_agent | ppt_agent | report_agent | sandbox_agent
  -> plan
  -> judge
  -> prepare_revision
  -> targeted agent
  -> judge
  -> finalize
END
```

The `plan` node calls Mistral with native tools. LangGraph then routes each selected tool call through its own graph node. The graph loops back to `plan` for up to three planning steps, then runs the judge. If the judge returns `needs_revision`, `prepare_revision` converts that feedback into a targeted tool call and routes back to only the failed agent once.

This is the main reason LangGraph makes more sense than a simple LangChain-only chain: the system can include an LLM-as-judge step after agent execution. For example, the judge can inspect whether the PPT and Excel outputs are grounded in the same filtered physician set, whether the report references the user's preferences, and whether sandbox code produced a valid chart. If an output fails, the graph can route back to the relevant agent once with targeted feedback.

Current quality loop:

```text
agent_output
  -> judge_outputs_node
    -> approved: collect_results_node
    -> needs_revision: prepare_revision_node -> targeted agent -> judge_outputs_node
    -> failed_after_retry: return visible failure context
```

The graph can also support reuse. If a query asks for a report after an Excel breakdown was already generated from the same filtered dataset, the workflow can reuse the filtered physician data, summary statistics, and prior insights instead of recomputing everything from scratch.

## Agent Design

### Orchestrator Agent

Responsibilities:

- Parse the user's artifact intent: slide deck, spreadsheet, report, analysis, or multiple artifacts
- Convert structured preferences into meaningful context
- Call `get_physician_data` before artifact agents when physician data is needed
- Route to the correct specialized agents using Mistral tool calls
- Return a unified result object containing trace events, generated artifacts, report text, and sandbox outputs

### Tool Definitions

The orchestrator will expose these tools to Mistral:

| Tool | Purpose |
| --- | --- |
| `get_physician_data` | Retrieve filtered mock physician records by specialty, geography, ICD-10 codes, and volume tier. |
| `call_ppt_agent` | Generate a PPTX deck from query context and physician data. |
| `call_excel_agent` | Generate an XLSX workbook from query context and physician data. |
| `call_report_agent` | Generate a structured markdown report and optional DOCX artifact. |
| `call_sandbox_agent` | Generate and execute Python analysis code, then return stdout, code, and chart images. |

### Specialized Agents

Each specialized agent will have its own prompt file and structured input/output schema.

PPT Agent:

- Input: topic, physician list, ICD-10 scope, slide count, style notes
- Output: downloadable `.pptx`
- LLM role: generate the deck title, subtitle, insight bullets, and table rationale as structured JSON
- Renderer role: use `python-pptx` inside the shared E2B/local artifact worker to create the actual PowerPoint file deterministically
- Minimum slides: title, population overview, key insights, top 10 physicians table

Excel Agent:

- Input: analysis type, physician list, dimensions, ICD-10 scope
- Output: downloadable `.xlsx`
- LLM role: generate workbook title, summary, sheet plan, and analysis notes as structured JSON
- Renderer role: use `openpyxl` inside the shared E2B/local artifact worker to create the actual workbook deterministically
- Sheets: raw data, state x specialty summary, ICD-10 breakdown

Report Agent:

- Input: report type, sections, physician list, ICD-10 context, geography
- Output: markdown rendered in UI, optional `.docx`
- Sections: executive summary, physician landscape, geographic and specialty distribution, insights, next steps

Sandbox Agent:

- Input: natural language analysis goal and dataset
- Output: generated Python code, stdout/stderr, chart image if generated
- Behavior: execute code in E2B when available; retry once with model self-correction if execution fails

Local fallback behavior:

- Run generated code through Python `exec()` inside a separate subprocess, never inside the FastAPI process
- Use a temporary working directory for input data and generated charts
- Pass the physician dataset as JSON/CSV files rather than exposing application objects
- Enforce a short timeout
- Capture stdout/stderr
- Apply AST checks before execution to block dangerous imports and operations
- Provide a limited global namespace with only approved analysis helpers
- Clearly label this mode as a local development fallback, not production-grade isolation

### Judge Agent

The Judge Agent is a lightweight LLM quality gate inside the LangGraph workflow.

Responsibilities:

- Check whether each artifact matches the user's requested artifact type
- Verify that outputs are grounded in the filtered physician data
- Confirm that preference context is explicitly referenced when required
- Detect missing required sections, sheets, slides, or chart outputs
- Score the response across relevance, completion, grounding, artifact quality, and preference alignment
- Decide whether to approve, request one targeted revision, or return a partial result with a clear trace

The judge will not replace deterministic validation. File existence, MIME type, sheet names, and artifact metadata will still be checked in code. The LLM judge is for semantic quality, not basic file validation.

The workflow uses an 85/100 approval threshold. If the judge returns `approved` but the overall score is below that threshold, LangGraph converts it into a targeted revision and emits the score in the trace. The UI renders the final judge scorecard alongside the generated result.

### Context Reuse

The graph state will preserve reusable intermediate results:

- Filtered physician records
- Inferred preference/filter summary
- Aggregate statistics
- Prior agent outputs from the current query
- Judge feedback

This lets later agents build on earlier work. For example, a report can reuse the same summary statistics created for an Excel workbook, which keeps multi-artifact outputs consistent.

## Backend API

Current endpoints:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Confirm backend, database, artifact path, and configured provider settings. |
| `GET` | `/physicians` | Return filtered physician data for the preference panel, orchestration tools, and debugging. |
| `POST` | `/query` | Run the full orchestration workflow and return the final response after completion. |
| `POST` | `/query/stream` | Run the same workflow while streaming trace events as newline-delimited JSON before the final response. |
| `GET` | `/artifacts/{id}` | Download generated artifacts from the server-side artifact store. |

Possible additional endpoints:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/models/health` | Confirm the configured Mistral model is accessible before a demo. |

Example physician filters:

```text
GET /physicians?specialty=oncology&state=CA&state=NY&icd10_codes=C341,C342&volume_threshold=high
GET /physicians?region=northeast&volume_threshold=high
GET /physicians?specialty=pulmonology&board_certified=true
```

`volume_threshold=high` is interpreted as a minimum threshold, so it returns both `high` and `very_high` physicians.

## Frontend Experience

The UI is a focused single-page workspace, not a marketing page.

Main regions:

- Query composer with large natural language input
- Inferred scope panel showing filters extracted by the LLM tool call
- Live agent trace with timing
- Results panel with rendered markdown report, sandbox code/output/chart, and artifact download buttons
- Physician data preview for transparency

Example trace:

```text
Orchestrator received query
Parsed request: PPTX + XLSX for high-volume NSCLC oncologists
Fetching physician data for CA, NY, C341, C342, high volume
Routing to PPT Agent and Excel Agent
Excel Agent generated workbook
PPT Agent generated slide deck
Done
```

## Data Strategy

The backend seeds 36 physician records with:

- `id`
- `npi`
- `firstName`
- `lastName`
- `specialty`
- `affiliation`
- `city`
- `state`
- `icd10ClaimVolume`
- `totalNSCLCClaims`
- `volumeTier`
- `email`
- `boardCertified`

SQLite is enough for this demo because the assignment uses mock data and a single-user workflow. The schema will be written so that moving to Postgres later would be straightforward.

The seed file lives at:

```text
backend/app/data/physicians_seed.json
```

The main assignment walkthrough is supported directly: filtering `Medical Oncology` physicians in CA/NY with `volume_threshold=high` and ICD-10 scope `C341,C342` returns 12 mock physicians. Startup seeding upserts rows so local demo databases pick up seed corrections without manually deleting `docnexus.db`.

## Artifact Strategy

Generated artifacts will be created server-side and stored under a local artifact directory. The database will keep metadata such as:

- artifact id
- artifact type
- filename
- MIME type
- local path
- source agent
- request id
- tool call id
- prompt name and prompt SHA-256
- input payload SHA-256
- generated file SHA-256 and size
- created timestamp

The browser will never generate PPTX or XLSX files. This keeps the implementation aligned with the assignment requirement and makes artifact generation testable from the backend.

The provenance hashes are intentionally stored with each artifact so the demo can answer: "Which prompt, model, tool call, and input payload produced this file?" This gives the judge and trace system a stronger audit trail than only storing filenames. PPT and Excel artifacts also store each agent's LLM-generated plan in provenance, so the judge can inspect the content plan that was rendered into the final file.

Before the LLM judge runs, the backend performs deterministic artifact validation:

- PPTX files are inspected for slide count and required slide concepts.
- XLSX files are inspected for required sheets and data rows.
- Markdown reports are inspected for required report sections.
- Chart files are inspected for file presence, size, and PNG signature when applicable.

These validation results are returned as `artifactValidations`, emitted in the trace, and passed into the LLM judge as evidence.

## Sandbox Strategy

The assignment requires the Sandbox Agent to actually execute generated Python code. The safest long-term path is to use E2B as the primary execution environment. That keeps arbitrary generated code outside the FastAPI process and gives the demo a credible isolation story.

The current implementation first uses E2B when `SANDBOX_PROVIDER=e2b` and `E2B_API_KEY` is configured. If E2B is unavailable, it falls back to restricted local subprocess execution. This same execution boundary is used in two places:

- Sandbox Agent: LLM-generated analysis code over the filtered physician dataset
- PPT/Excel artifact workers: deterministic renderer code for `python-pptx` and `openpyxl`

The local analysis fallback is inspired by feedback-oracle style evaluation loops:

```text
LLM generates Python analysis code
  -> backend validates code with AST checks
  -> backend writes dataset to a temp directory
  -> separate Python subprocess runs exec(code, restricted_globals, {})
  -> subprocess returns stdout, stderr, chart path, and exit status
```

The local runner is useful for the take-home demo and local development, but it should not be presented as equivalent to cloud/container isolation. The important safety boundary is that generated code never executes inside the main API server process.

Current local guardrails:

- The query response includes `sandboxOutput.executionProvider`, so the UI and trace show whether E2B, local subprocess, or local fallback executed analysis code.
- PPT/Excel artifacts store `provenance.renderExecution.executionProvider`, so downloads can be traced to E2B or the local artifact worker.
- Generated code runs in a separate Python subprocess.
- Code is AST-checked before execution.
- Imports and dangerous calls such as `eval`, `exec`, `open`, `subprocess`, and network/process modules are blocked.
- The subprocess receives only a JSON dataset and approved analysis helpers such as `pd`, `plt`, `math`, and `statistics`.
- Execution has a timeout.
- The agent retries once with corrected code if execution fails.

## Prompt Organization

Prompts live in source-controlled files rather than being hidden inside route handlers.

Current structure:

```text
backend/app/prompts/
  orchestrator.md
  ppt_agent.md
  excel_agent.md
  report_agent.md
  sandbox_agent.md
  judge_agent.md
```

Each prompt should include:

- Agent role
- Inputs and output contract
- Grounding rules
- What to avoid
- Formatting expectations
- Few-shot examples when useful

This matters because prompt engineering is a major part of the evaluation.

## Planned Project Structure

```text
.
  README.md
  requirements.txt
  .env.example
  docs/
    architecture-decisions.md
    implementation-log.md
    orchestration-contract.md
  backend/
    app/
      api/
      agents/
      core/
      db/
      prompts/
      schemas/
      services/
      data/
  frontend/
    src/
      components/
      lib/
      pages/
      types/
  artifacts/
```

## Environment Variables

Current `.env.example`:

```env
APP_ENV=development
DATABASE_URL=sqlite:///./docnexus.db
ARTIFACT_DIR=./artifacts

LLM_PROVIDER=mistral
MISTRAL_API_KEY=replace-me
MISTRAL_MODEL=mistral-small-latest

E2B_API_KEY=replace-me
SANDBOX_PROVIDER=e2b
SANDBOX_TIMEOUT_SECONDS=30

FRONTEND_ORIGIN=http://localhost:5173
```

## Local Setup

Create and activate a virtual environment:

```bash
python -m venv .venv
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Copy environment variables:

```bash
copy .env.example .env
```

Run the backend:

```bash
uvicorn backend.app.main:app --reload
```

Open the API docs:

```text
http://localhost:8000/docs
```

Check the first endpoints:

```text
http://localhost:8000/health
http://localhost:8000/physicians?state=CA&volume_threshold=high
```

Run the frontend:

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

Build the frontend:

```bash
cd frontend
npm run build
```

Current query behavior:

- Requires `MISTRAL_API_KEY`.
- Sends the orchestrator prompt, user query, empty optional override fields, and tool schemas to Mistral.
- Relies on Mistral tool calling to extract ICD-10 codes, geography, specialty, volume tier, and artifact intent from the query.
- Uses `/query/stream` from the frontend so trace events render while the workflow is still running.
- Executes `get_physician_data` through the same backend physician service used by `GET /physicians`.
- Executes `call_ppt_agent` when selected and generates a downloadable `.pptx` through the shared E2B/local artifact worker.
- Executes `call_excel_agent` when selected and generates a downloadable `.xlsx` through the shared E2B/local artifact worker.
- Executes `call_report_agent` when selected, using the Report Agent prompt to generate markdown.
- Executes `call_sandbox_agent` when selected, using the Sandbox Agent prompt to generate Python code and E2B or the restricted local subprocess fallback to execute it.
- Records trace events for orchestration, data retrieval, artifact generation, sandbox execution, judge decisions, and targeted retries.
- Routes `needs_revision` judge feedback back to the target agent once, replacing that agent's prior response artifact in the final response.

## Development Plan

1. Create repo skeleton, README, decision log, and `.env.example` - done
2. Build FastAPI backend with health checks and SQLite physician seed data - done
3. Implement `/physicians` filtering - done
4. Define Pydantic schemas for query payloads, tool calls, trace events, and artifacts - done
5. Implement Mistral client and orchestrator tool definitions - basic client/tool loop done
6. Add LangGraph state workflow around the orchestrator, context reuse, per-agent nodes, judge node, and targeted revision edge - done
7. Implement Excel Agent and PPT Agent first - done
8. Add React UI with query input, inferred scope display, streaming trace, and downloads - done
9. Implement Report Agent - markdown done, optional DOCX pending
10. Implement Sandbox Agent with E2B execution, restricted local fallback, and one retry on failure - done
11. Polish demo queries, tests, docs, and video script

## Known Limitations

- The physician dataset is mock data, not real production physician intelligence.
- Mistral free mode is rate-limited, so the demo should avoid unnecessary repeated LLM calls.
- SQLite is intentionally chosen for portability, not multi-user production scale.
- E2B requires an API key and network access; local subprocess fallback is restricted and clearly marked as a fallback.
- The local Python `exec()` fallback is designed for demo resilience, not production-grade arbitrary-code isolation.
- Current `/query` implementation can generate PPTX, Excel, markdown reports, sandbox stdout, and chart artifacts. Optional DOCX reports are still pending.
- Browser visual QA was attempted, but the in-app Browser plugin failed to attach in this Windows sandbox. The frontend production build passes.
- LangGraph targeted revision is limited to one retry and reruns one target agent at a time; a larger production workflow could support multi-agent revision plans.
- The first implementation will optimize for the required assignment flow before adding memory or user accounts.

## What I Would Build Next

If this moved beyond the take-home demo:

- Resumable trace streams over SSE or WebSockets for long-running multi-user jobs
- Persistent sessions and query history
- Real physician data API integration
- Postgres artifact and trace storage
- Background job queue for long-running artifact generation
- Stronger sandbox isolation policy and audit logs
- Evaluation suite for routing accuracy across many prompt variants
- Human-in-the-loop review before sending artifacts to external stakeholders
