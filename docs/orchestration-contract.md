# Orchestration Contract

This document describes the API and internal contracts that will support the Mistral + LangGraph orchestration layer.

## Current Status

Implemented:

- Query request/response schemas
- Preference schema
- Artifact reference schema
- Trace event schema
- Judge decision schema
- Sandbox output schema
- Tool argument schemas
- Mistral-style orchestrator tool definitions
- Source-controlled prompt files for the orchestrator and specialized agents
- `POST /query` route
- `POST /query/stream` route for live trace events
- Multi-node LangGraph query workflow
- Mistral tool-calling client wrapper
- Trace builder
- Orchestrator shell that executes `get_physician_data`
- Artifact registry and download endpoint
- PPT Agent execution for `call_ppt_agent`
- Excel Agent execution for `call_excel_agent`
- LLM-backed Report Agent execution for `call_report_agent`
- LLM-backed Sandbox Agent execution for `call_sandbox_agent`
- LLM Judge Agent execution
- Per-agent LangGraph nodes for data, Excel, PPT, report, and sandbox execution
- Targeted revision edge from judge `needs_revision` decisions back to the relevant agent
- Trace callback plumbing from `TraceBuilder` into the streaming endpoint

Not implemented yet:

- Optional DOCX report export

## Query Request

The current `POST /query` and `POST /query/stream` endpoints accept:

```json
{
  "query": "Give me a slide deck and Excel breakdown of high-volume NSCLC oncologists in California and New York.",
  "preferences": {
    "icd10Codes": ["C341", "C342"],
    "states": ["CA", "NY"],
    "regions": [],
    "specialties": ["Medical Oncology"],
    "volumeThreshold": "high",
    "boardCertified": true
  },
  "requestedArtifacts": ["pptx", "xlsx"],
  "includeTrace": true
}
```

The frontend can provide structured preferences, but the orchestrator still has to interpret the natural language query and decide which tools to call.

## Query Streaming

The React frontend uses `POST /query/stream` so it can send the full query payload and receive live workflow events. The response media type is:

```text
application/x-ndjson
```

Each line is a JSON event:

```json
{"type":"trace","data":{"agent":"data","status":"started","message":"Retrieving filtered physician data."}}
{"type":"result","data":{"requestId":"req_123","artifacts":[],"metadata":{"workflow":"langgraph"}}}
{"type":"error","data":{"message":"Mistral chat completion failed: ..."}}
```

Why NDJSON instead of browser `EventSource`:

- The workflow needs a POST body containing query text, structured preferences, and requested artifact types.
- Native `EventSource` is GET-only without workarounds.
- `fetch()` with a readable stream keeps the API simple and lets the UI parse trace events incrementally.

`POST /query` remains available for non-streaming clients and automated checks that only need the final response.

## Query Response

The response shape is:

```json
{
  "requestId": "req_123",
  "query": "Give me a slide deck and Excel breakdown...",
  "answerMarkdown": "Generated two artifacts grounded in 12 filtered physicians.",
  "artifacts": [
    {
      "id": "art_123",
      "type": "pptx",
      "filename": "high_volume_nsclc_oncologists.pptx",
      "mimeType": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
      "downloadUrl": "/artifacts/art_123",
      "sourceAgent": "ppt",
      "requestId": "req_123",
      "toolCallId": "call_456",
      "promptName": "ppt_agent.md",
      "promptSha256": "3f...",
      "inputSha256": "9a...",
      "artifactSha256": "b4...",
      "fileSizeBytes": 32894
    }
  ],
  "artifactValidations": [
    {
      "artifactId": "art_123",
      "artifactType": "pptx",
      "sourceAgent": "ppt",
      "passed": true,
      "score": 100,
      "checks": [
        {
          "name": "slide_count",
          "passed": true,
          "message": "PPTX has at least four slides.",
          "metadata": {"slideCount": 4}
        }
      ]
    }
  ],
  "sandboxOutput": null,
  "trace": [],
  "judgeDecision": {
    "status": "approved",
    "reason": "Artifacts match the requested PPTX and XLSX outputs.",
    "scores": {
      "relevance": 95,
      "completion": 95,
      "grounding": 95,
      "artifactQuality": 95,
      "preferenceAlignment": 95,
      "overall": 95
    },
    "criticalFailures": []
  },
  "metadata": {}
}
```

## Artifact Provenance

Every generated artifact stores provenance metadata in SQLite and returns it in the API response:

- `requestId`: the workflow request that produced the artifact.
- `toolCallId`: the exact orchestrator tool call that produced the artifact.
- `promptName` and `promptSha256`: the source-controlled prompt associated with the agent.
- `inputSha256`: a stable hash of the structured agent input.
- `artifactSha256` and `fileSizeBytes`: a hash and byte count of the generated file on disk.
- `provenance`: lightweight extra metadata such as model name, tool name, source agent, and input record count.

This makes artifact traceability explicit. Reviewers can see not just that a file exists, but which prompt, payload, tool call, and model path produced it.

## Deterministic Artifact Validation

Before the LLM judge makes a semantic decision, backend validators inspect the generated artifacts:

- PPTX: file exists, at least four slides, title text, overview slide, insights slide, top physicians slide.
- XLSX: required sheets exist and contain data rows.
- Markdown: report exists, is substantive, and includes required section headings.
- Chart PNG/SVG: file exists, is non-empty, and PNG files have a valid signature.

The validators produce `artifactValidations` with per-check pass/fail data and a deterministic score. These results are returned to the UI, included in trace metadata, and passed to the LLM judge as grounding evidence.

## Trace Events

Trace events are designed for the frontend live agent trace.

Example:

```json
{
  "id": "trace_001",
  "agent": "orchestrator",
  "status": "started",
  "message": "Parsing query and selecting tools.",
  "timestamp": "2026-05-28T22:45:00Z",
  "elapsedMs": null,
  "metadata": {
    "model": "mistral-small-latest"
  }
}
```

Allowed agents:

- `orchestrator`
- `data`
- `ppt`
- `excel`
- `report`
- `sandbox`
- `judge`

Allowed statuses:

- `started`
- `completed`
- `failed`
- `retrying`
- `skipped`

## Tool Call Boundary

The orchestrator exposes these tools to Mistral:

- `get_physician_data`
- `call_ppt_agent`
- `call_excel_agent`
- `call_report_agent`
- `call_sandbox_agent`

Mistral decides which tools to call. The backend executes those tool calls through deterministic Python services.

This split is important:

- The LLM handles semantic interpretation and routing.
- Backend services handle data access, artifact generation, validation, and file storage.

Current execution support:

- `get_physician_data`: implemented
- `call_ppt_agent`: implemented
- `call_excel_agent`: implemented
- `call_report_agent`: implemented for markdown reports
- `call_sandbox_agent`: implemented with restricted local subprocess execution

## Prompt Files

Prompt files live in:

```text
backend/app/prompts/
```

Current prompts:

- `orchestrator.md`
- `ppt_agent.md`
- `excel_agent.md`
- `report_agent.md`
- `sandbox_agent.md`
- `judge_agent.md`

Keeping prompts in files makes them reviewable and easy to discuss in the video demo.

## LangGraph Flow

The current LangGraph flow is:

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

The `plan` node calls Mistral with native tools. If tool calls are returned, `route_tool` sends each call to its own agent node. Data retrieval is ordered before artifact agents so the same filtered physician context can be reused across PPT, Excel, report, and sandbox outputs. The graph loops back to `plan` for up to three planning steps.

## Judge Loop

The current LangGraph flow includes a judge step:

```text
agent outputs
  -> judge_outputs_node
    -> approved
    -> needs_revision -> prepare_revision -> targeted agent -> judge_outputs_node
    -> failed_after_retry
```

The judge checks semantic quality, such as whether outputs are grounded in the same physician data. Deterministic checks, such as file existence and expected sheet names, will stay in code.

The revision loop is intentionally bounded to one targeted retry. `prepare_revision` maps judge targets such as `report`, `excel`, `ppt`, or `sandbox` back to the corresponding tool node, injects the judge's revision instructions into the tool arguments, removes that agent's stale artifact references from the final response, and re-runs only that node.

The judge returns a scored rubric:

- `relevance`
- `completion`
- `grounding`
- `artifactQuality`
- `preferenceAlignment`
- `overall`

The approval threshold is 85/100. If the judge returns `approved` with an `overall` score below 85, or if deterministic validation has failed, the graph treats the result as `needs_revision` and routes back to the best target agent.
