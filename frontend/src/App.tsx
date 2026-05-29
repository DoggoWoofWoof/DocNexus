import { useState, type ComponentProps } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  BarChart3,
  BrainCircuit,
  ChevronDown,
  Download,
  FileSpreadsheet,
  FileText,
  FlaskConical,
  Loader2,
  Play,
  Presentation,
  RotateCcw,
  Search,
  SlidersHorizontal,
} from "lucide-react";

import { API_BASE_URL, artifactUrl, runQueryStream } from "./api";
import type { ArtifactRef, ArtifactType, Physician, QueryPreferences, QueryResponse, TraceEvent } from "./types";

const SAMPLE_QUERIES = [
  "Give me a slide deck and an Excel breakdown of high-volume NSCLC oncologists in California and New York.",
  "Build an Excel breakdown of C341 claim volume by physician specialty and state.",
  "Write a two-page market access report on NSCLC physician density in the Northeast.",
  "Run an analysis and show me which states have the highest concentration of high-volume NSCLC prescribers.",
];

const DEFAULT_QUERY = SAMPLE_QUERIES[0];

type PreferenceDraft = {
  icd10Codes: string;
  states: string;
  regions: string;
  specialties: string;
  volumeThreshold: "" | "low" | "high" | "very_high";
  boardCertified: "" | "true" | "false";
};

const EMPTY_PREFERENCES: PreferenceDraft = {
  icd10Codes: "",
  states: "",
  regions: "",
  specialties: "",
  volumeThreshold: "",
  boardCertified: "",
};

function App() {
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [preferences, setPreferences] = useState<PreferenceDraft>(EMPTY_PREFERENCES);
  const [showPreferences, setShowPreferences] = useState(false);
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [liveTrace, setLiveTrace] = useState<TraceEvent[]>([]);
  const [physicians, setPhysicians] = useState<Physician[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRunQuery() {
    setIsRunning(true);
    setError(null);
    setResponse(null);
    setLiveTrace([]);
    setPhysicians([]);
    try {
      const result = await runQueryStream(
        {
          query,
          preferences: toQueryPreferences(preferences),
          requestedArtifacts: [],
          includeTrace: true,
        },
        {
          onTrace: (event) => {
            setLiveTrace((current) => {
              if (current.some((existing) => existing.id === event.id)) {
                return current;
              }
              return [...current, event];
            });
          },
        },
      );
      setResponse(result);
      setPhysicians(metadataPhysicians(result.metadata));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Query failed.");
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <main className="app-shell">
      <section className="workspace-header">
        <div>
          <p className="eyebrow">DocNexus AI Engineer Demo</p>
          <h1>Physician Intelligence Orchestrator</h1>
        </div>
        <div className="status-strip">
          <span>API</span>
          <strong>{API_BASE_URL}</strong>
        </div>
      </section>

      <section className="workspace-grid">
        <div className="query-panel">
          <div className="panel-heading">
            <BrainCircuit size={19} />
            <h2>Query</h2>
          </div>
          <textarea value={query} onChange={(event) => setQuery(event.target.value)} />

          <div className="sample-row">
            {SAMPLE_QUERIES.map((sample) => (
              <button key={sample} type="button" onClick={() => setQuery(sample)}>
                {sample}
              </button>
            ))}
          </div>

          <div className="preference-header">
            <button className="secondary compact" type="button" onClick={() => setShowPreferences((value) => !value)}>
              <SlidersHorizontal size={16} />
              Preferences
              <ChevronDown className={showPreferences ? "chevron open" : "chevron"} size={16} />
            </button>
            {hasPreferenceDraft(preferences) ? (
              <button className="secondary compact" type="button" onClick={() => setPreferences(EMPTY_PREFERENCES)}>
                <RotateCcw size={16} />
                Clear
              </button>
            ) : null}
          </div>

          {showPreferences ? <PreferencePanel preferences={preferences} onChange={setPreferences} /> : null}

          <div className="action-row">
            <button className="primary" type="button" onClick={handleRunQuery} disabled={isRunning || query.trim().length < 3}>
              {isRunning ? <Loader2 className="spin" size={17} /> : <Play size={17} />}
              Run Agent Workflow
            </button>
          </div>

          {error ? <div className="error-box">{error}</div> : null}
        </div>

        <aside className="trace-panel">
          <div className="panel-heading">
            <BarChart3 size={19} />
            <h2>Agent Trace</h2>
          </div>
          <TraceList trace={response?.trace.length ? response.trace : liveTrace} isRunning={isRunning} />
        </aside>
      </section>

      <section className="results-grid">
        <div className="results-panel">
          <div className="panel-heading">
            <FileText size={19} />
            <h2>Results</h2>
          </div>
          {response?.answerMarkdown ? (
            <div className="markdown-body">
              <ReactMarkdown components={{ img: MarkdownImage }} remarkPlugins={[remarkGfm]}>
                {normalizeMarkdown(response.answerMarkdown)}
              </ReactMarkdown>
            </div>
          ) : (
            <EmptyState text="Run a query to render report text, generated analysis, and artifact links." />
          )}

          {response?.judgeDecision ? <JudgeScorecard response={response} /> : null}
          {response ? <InferredScope metadata={response.metadata} /> : null}

          {response?.sandboxOutput ? (
            <div className="sandbox-box">
              <div className="sandbox-header">
                <FlaskConical size={17} />
                <strong>Sandbox Output</strong>
                <span>{response.sandboxOutput.executionStatus} · {response.sandboxOutput.executionProvider}</span>
              </div>
              <details className="code-panel" open>
                <summary>Generated analysis code</summary>
                <pre>{response.sandboxOutput.code}</pre>
              </details>
              {response.sandboxOutput.stdout ? <pre className="stdout">{normalizeMarkdown(response.sandboxOutput.stdout)}</pre> : null}
              {response.sandboxOutput.stderr ? <pre className="stderr">{response.sandboxOutput.stderr}</pre> : null}
            </div>
          ) : null}
        </div>

        <aside className="artifacts-panel">
          <div className="panel-heading">
            <Download size={19} />
            <h2>Artifacts</h2>
          </div>
          {response?.artifacts.length ? (
            <div className="artifact-list">
              {response.artifacts.map((artifact) => (
                <a key={artifact.id} href={artifactUrl(artifact.downloadUrl)}>
                  {artifactIcon(artifact.type)}
                  <span>
                    {artifact.filename}
                    <small>{artifact.sourceAgent} · {artifactProvider(artifact)}</small>
                  </span>
                  <Download size={16} />
                </a>
              ))}
            </div>
          ) : (
            <EmptyState text="Generated files will appear here." />
          )}
        </aside>
      </section>

      <section className="physician-panel">
        <div className="panel-heading">
          <Search size={19} />
          <h2>Physician Preview</h2>
          <span className="count-pill">{physicians.length}</span>
        </div>
        {physicians.length ? <PhysicianTable physicians={physicians} /> : <EmptyState text="Preview filtered physicians before or after running a query." />}
      </section>
    </main>
  );
}

function PreferencePanel({
  preferences,
  onChange,
}: {
  preferences: PreferenceDraft;
  onChange: (preferences: PreferenceDraft) => void;
}) {
  function update<K extends keyof PreferenceDraft>(key: K, value: PreferenceDraft[K]) {
    onChange({ ...preferences, [key]: value });
  }

  return (
    <div className="preference-grid">
      <label className="field">
        <span>ICD-10</span>
        <input value={preferences.icd10Codes} onChange={(event) => update("icd10Codes", event.target.value)} placeholder="C341, C342" />
      </label>
      <label className="field">
        <span>States</span>
        <input value={preferences.states} onChange={(event) => update("states", event.target.value)} placeholder="CA, NY" />
      </label>
      <label className="field">
        <span>Regions</span>
        <input value={preferences.regions} onChange={(event) => update("regions", event.target.value)} placeholder="northeast" />
      </label>
      <label className="field">
        <span>Specialties</span>
        <input value={preferences.specialties} onChange={(event) => update("specialties", event.target.value)} placeholder="Medical Oncology" />
      </label>
      <label className="field">
        <span>Volume</span>
        <select value={preferences.volumeThreshold} onChange={(event) => update("volumeThreshold", event.target.value as PreferenceDraft["volumeThreshold"])}>
          <option value="">Any</option>
          <option value="low">Low+</option>
          <option value="high">High+</option>
          <option value="very_high">Very high</option>
        </select>
      </label>
      <label className="field">
        <span>Board</span>
        <select value={preferences.boardCertified} onChange={(event) => update("boardCertified", event.target.value as PreferenceDraft["boardCertified"])}>
          <option value="">Any</option>
          <option value="true">Certified</option>
          <option value="false">Not certified</option>
        </select>
      </label>
    </div>
  );
}

function MarkdownImage({ src = "", alt = "", ...props }: ComponentProps<"img">) {
  const resolvedSrc = typeof src === "string" && src.startsWith("/artifacts/") ? artifactUrl(src) : src;
  return <img {...props} alt={alt} src={resolvedSrc} />;
}

function TraceList({ trace, isRunning }: { trace: TraceEvent[]; isRunning: boolean }) {
  if (!trace.length) {
    return <EmptyState text={isRunning ? "Agent workflow is starting." : "Trace events will appear here."} />;
  }

  return (
    <ol className="trace-list">
      {trace.map((event) => (
        <li key={event.id} className={event.status}>
          <span className="agent">{event.agent}</span>
          <p>{event.message}</p>
          {event.elapsedMs !== null && event.elapsedMs !== undefined ? <small>{event.elapsedMs} ms</small> : null}
          <TraceMetadata metadata={event.metadata} />
        </li>
      ))}
    </ol>
  );
}

function TraceMetadata({ metadata }: { metadata: Record<string, unknown> }) {
  const items = traceMetadataItems(metadata);
  if (!items.length) {
    return null;
  }

  return (
    <div className="trace-meta">
      {items.map(([label, value]) => (
        <span key={`${label}:${value}`}>
          {label}: {value}
        </span>
      ))}
    </div>
  );
}

function traceMetadataItems(metadata: Record<string, unknown>): Array<readonly [string, string]> {
  const items: Array<readonly [string, string]> = [];

  appendValue(items, "Tools", metadata.selectedTools);
  appendValue(items, "Parallel", metadata.parallelTools);
  appendValue(items, "Artifacts", metadata.artifactRequests);
  appendFilterItems(items, metadata.inferredFilters, "");
  appendFilterItems(items, metadata.arguments, "");
  appendFilterItems(items, metadata.filters, "Applied ");
  appendValue(items, "Records", metadata.count);
  appendValue(items, "Physicians", metadata.physicianCount);
  appendValue(items, "Chart", metadata.chartArtifactId);
  appendValue(items, "Attempts", metadata.attemptCount);
  appendValue(items, "Contract", metadata.contractStatus);
  appendValue(items, "Judge", metadata.judgeProvider);
  appendRenderItems(items, metadata.renderExecution);
  appendScoreItems(items, metadata.scores);
  appendValue(items, "Target", metadata.targetAgent);

  return dedupeItems(items);
}

function appendFilterItems(
  items: Array<readonly [string, string]>,
  value: unknown,
  prefix: string,
) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return;
  }

  const filters = value as Record<string, unknown>;
  appendValue(items, `${prefix}Specialty`, filters.specialty);
  appendValue(items, `${prefix}States`, filters.states ?? filters.state);
  appendValue(items, `${prefix}Regions`, filters.regions ?? filters.region);
  appendValue(items, `${prefix}ICD-10`, filters.icd10Codes ?? filters.icd10_codes);
  appendValue(items, `${prefix}Volume`, filters.volumeThreshold ?? filters.volume_threshold);
  appendValue(items, `${prefix}Board`, filters.boardCertified ?? filters.board_certified);
}

function appendRenderItems(items: Array<readonly [string, string]>, value: unknown) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return;
  }

  const render = value as Record<string, unknown>;
  appendValue(items, "Renderer", render.executionProvider);
  appendValue(items, "Fallback", render.fallbackReason);
}

function appendScoreItems(items: Array<readonly [string, string]>, value: unknown) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return;
  }

  const scores = value as Record<string, unknown>;
  appendValue(items, "Overall", scores.overall);
  appendValue(items, "Grounding", scores.grounding);
  appendValue(items, "Completion", scores.completion);
}

function appendValue(items: Array<readonly [string, string]>, label: string, value: unknown) {
  const formatted = formatMetadataValue(value);
  if (formatted) {
    items.push([label, formatted]);
  }
}

function dedupeItems(items: Array<readonly [string, string]>): Array<readonly [string, string]> {
  const seen = new Set<string>();
  return items.filter(([label, value]) => {
    const key = `${label}:${value}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function InferredScope({ metadata }: { metadata: Record<string, unknown> }) {
  const filters = metadata.inferredFilters;
  if (!filters || typeof filters !== "object") {
    return null;
  }

  const entries = Object.entries(filters)
    .map(([key, value]) => [labelFor(key), formatMetadataValue(value)] as const)
    .filter(([, value]) => value);

  if (!entries.length) {
    return null;
  }

  return (
    <div className="scope-card">
      <strong>Inferred Scope</strong>
      <div>
        {entries.map(([label, value]) => (
          <span key={label}>
            {label}: {value}
          </span>
        ))}
      </div>
    </div>
  );
}

function PhysicianTable({ physicians }: { physicians: Physician[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Physician</th>
            <th>Specialty</th>
            <th>State</th>
            <th>Affiliation</th>
            <th>Claims</th>
            <th>Tier</th>
          </tr>
        </thead>
        <tbody>
          {physicians.slice(0, 12).map((physician) => (
            <tr key={physician.id}>
              <td>{physician.firstName} {physician.lastName}</td>
              <td>{physician.specialty}</td>
              <td>{physician.state}</td>
              <td>{physician.affiliation}</td>
              <td>{physician.totalNSCLCClaims}</td>
              <td>{physician.volumeTier}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function JudgeScorecard({ response }: { response: QueryResponse }) {
  const scores = response.judgeDecision?.scores;
  if (!scores) {
    return null;
  }

  const metrics = [
    ["Relevance", scores.relevance],
    ["Completion", scores.completion],
    ["Grounding", scores.grounding],
    ["Artifact Quality", scores.artifactQuality],
    ["Preference Fit", scores.preferenceAlignment],
  ] as const;

  return (
    <div className="judge-card">
      <div className="judge-summary">
        <span>{response.judgeDecision?.status}</span>
        <strong>{scores.overall}/100</strong>
      </div>
      <p>{response.judgeDecision?.reason}</p>
      <div className="score-grid">
        {metrics.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <div className="empty-state">{text}</div>;
}

function normalizeMarkdown(value: string): string {
  return value.replace(/\|\s+\|/g, "|\n|");
}

function toQueryPreferences(preferences: PreferenceDraft): QueryPreferences {
  return {
    icd10Codes: splitList(preferences.icd10Codes).map((value) => value.toUpperCase()),
    states: splitList(preferences.states).map((value) => value.toUpperCase()),
    regions: splitList(preferences.regions).map((value) => value.toLowerCase()),
    specialties: splitList(preferences.specialties),
    volumeThreshold: preferences.volumeThreshold || null,
    boardCertified: preferences.boardCertified === "" ? null : preferences.boardCertified === "true",
  };
}

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

function hasPreferenceDraft(preferences: PreferenceDraft): boolean {
  return Object.values(preferences).some((value) => value !== "");
}

function artifactIcon(type: ArtifactType) {
  if (type === "pptx") return <Presentation size={17} />;
  if (type === "xlsx") return <FileSpreadsheet size={17} />;
  if (type === "chart_png" || type === "chart_svg") return <BarChart3 size={17} />;
  return <FileText size={17} />;
}

function metadataPhysicians(metadata: Record<string, unknown>): Physician[] {
  return Array.isArray(metadata.physicianPreview) ? (metadata.physicianPreview as Physician[]) : [];
}

function artifactProvider(artifact: ArtifactRef): string {
  const render = artifact.provenance?.renderExecution;
  if (render && typeof render === "object" && "executionProvider" in render) {
    return String((render as { executionProvider: unknown }).executionProvider);
  }
  return "agent output";
}

function labelFor(value: string): string {
  return value.replace(/([A-Z])/g, " $1").replace(/^./, (letter) => letter.toUpperCase());
}

function formatMetadataValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  if (value === null || value === undefined || value === "") {
    return "";
  }
  return String(value);
}

export default App;
