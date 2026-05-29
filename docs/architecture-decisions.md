# Architecture Decisions

This file records why major technical choices were made. The goal is to make the submission easy to review and easy to explain in a follow-up interview.

## ADR 001 - Use FastAPI For The Backend

Decision: Use FastAPI as the backend framework.

Why:

- The assignment requires Python-heavy work: pandas analysis, PPTX/XLSX/DOCX generation, and sandbox execution.
- FastAPI gives typed request/response models through Pydantic.
- The API surface is small and maps cleanly to the required endpoints.
- Keeping orchestration, data processing, and artifact generation in Python avoids unnecessary cross-language glue.

Tradeoff:

- A Node backend would pair naturally with React, but would make Python artifact generation and sandbox analysis more awkward.

## ADR 002 - Use Mistral Native Function Calling For Routing

Decision: Use Mistral as the LLM provider and rely on native function/tool calling for orchestrator routing.

Why:

- The assignment explicitly requires native tool/function calling and says not to fake routing with string parsing or if/else logic.
- Mistral supports function calling with structured JSON tool schemas.
- Mistral free mode is suitable for evaluation and prototyping.
- Model selection can stay configurable through environment variables.

Tradeoff:

- Free mode has rate limits, so prompts must stay compact and the demo should avoid repeated unnecessary calls.

## ADR 003 - Use LangGraph, But Keep It Minimal

Decision: Use LangGraph to manage workflow state, context reuse, quality checks, and bounded retries, not to hide routing logic.

Why:

- The project has branching paths: PPT, Excel, report, sandbox analysis, or combinations of these.
- The UI needs a live trace of agent activity.
- Some agents may run in parallel after data retrieval.
- The Sandbox Agent needs retry/self-correction behavior.
- An LLM-as-judge node can evaluate whether agent outputs are grounded, complete, and aligned with the user's preferences.
- The graph can route back to a specific agent for one targeted revision instead of rerunning the entire pipeline.
- Shared state lets later agents reuse filtered physician records, summary statistics, prior insights, and judge feedback.
- LangGraph provides an explicit state model that is easier to explain than an ad hoc orchestration loop.

Tradeoff:

- LangGraph would be overkill for a single-agent chatbot. Here it is justified because the assignment is about multi-agent orchestration, output review, and reuse of intermediate work.

## ADR 004 - Use SQLite For The Demo Database

Decision: Use SQLite for seeded physician data and artifact metadata.

Why:

- The dataset is mock data with at least 30 physician records.
- SQLite keeps setup simple for reviewers and video demos.
- It avoids requiring Docker or a hosted database just to run the project.
- The schema can be written with SQLModel/SQLAlchemy so Postgres is a straightforward future migration.

Tradeoff:

- SQLite is not the target production choice for multi-user concurrent workloads.

## ADR 005 - Generate Artifacts Server-Side

Decision: Generate PPTX, XLSX, and DOCX artifacts on the backend.

Why:

- The assignment requires server-side PPT and Excel generation.
- Backend generation is easier to test and keeps generated files consistent.
- Artifact metadata can be stored and served through `/artifacts/{id}`.

Tradeoff:

- Frontend-only generation would be simpler for deployment, but would miss a core assignment requirement.

## ADR 006 - Use E2B As The Primary Sandbox With A Local Exec Fallback

Decision: Use E2B for sandboxed code execution when an API key is available. Include restricted local subprocess fallbacks for local development and demos.

Why:

- The Sandbox Agent must actually execute generated Python code.
- PPT and Excel renderers also benefit from an isolated execution boundary because they transform LLM-planned content into downloadable files.
- E2B provides isolated cloud sandboxes and avoids unsafe in-process execution.
- It supports the assignment's recommendation and has a free Hobby tier.
- A local fallback makes the project easier to demo when no E2B key is configured.
- Running `exec()` in a separate subprocess keeps generated code out of the FastAPI process.

Tradeoff:

- E2B requires an API key and network access. Restricted local subprocess workers can support local demos, but should be clearly labeled as fallback behavior rather than production-grade arbitrary-code isolation.

Local fallback guardrails:

- Validate generated code with AST checks before execution.
- Block dangerous imports such as process, filesystem, and network access modules.
- Provide a limited execution namespace.
- Run in a temporary working directory.
- Enforce timeout and capture stdout/stderr.
- Allow only expected analysis outputs such as text and chart image files.

## ADR 007 - Use React + Vite + TypeScript For The Frontend

Decision: Use React, Vite, and TypeScript for the UI.

Why:

- The assignment asks for a clean single-page UI.
- Vite keeps setup and development fast.
- TypeScript helps keep API payloads, trace events, and artifact models consistent.
- React is enough for the required workflow without the routing and server-rendering overhead of Next.js.

Tradeoff:

- Next.js would be useful for a larger product surface, but this project benefits from a smaller frontend stack.

## ADR 008 - Stream Agent Trace With POST NDJSON

Decision: Add `POST /query/stream` using newline-delimited JSON events instead of using browser `EventSource`.

Why:

- The query workflow needs a request body with natural language text, structured preferences, and requested artifact types.
- Browser `EventSource` only supports GET requests, which would force awkward query-string encoding or a separate session creation endpoint.
- `fetch()` readable streams work naturally with POST and let the UI append trace events as soon as the backend emits them.
- Keeping `/query` as a normal non-streaming endpoint preserves a simple API for tests and clients that only need the final result.

Tradeoff:

- NDJSON streaming is less standardized in browser APIs than SSE, so the frontend owns a small line parser. For a production multi-user workflow, SSE or WebSockets could still be added on top of the same trace callback boundary.

## ADR 009 - Keep Physician Rows In Backend State, Not Tool Arguments

Decision: Treat Mistral tool calls as intent and lightweight parameter selection. The backend injects the canonical filtered physician context from `get_physician_data` into PPT, Excel, Report, and Sandbox agents.

Why:

- Full physician rows are already available in LangGraph state after the data node runs.
- Asking the LLM to serialize large `physician_list` or `dataset` payloads can create malformed partial rows.
- Canonical backend injection guarantees that every downstream artifact uses the same filtered cohort.
- This makes trace counts easier to explain: the data node owns record selection, downstream agents own artifact or analysis generation.

Tradeoff:

- Downstream agent tool calls are slightly less self-contained, but the graph state is the right place for shared workflow context.
