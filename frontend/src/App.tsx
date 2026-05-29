import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  BarChart3,
  BrainCircuit,
  Download,
  FileSpreadsheet,
  FileText,
  FlaskConical,
  Loader2,
  Play,
  Presentation,
  Search,
} from "lucide-react";

import { API_BASE_URL, artifactUrl, fetchPhysicians, runQueryStream } from "./api";
import type { ArtifactRef, ArtifactType, Physician, QueryPreferences, QueryResponse, TraceEvent } from "./types";

const SAMPLE_QUERIES = [
  "Give me a slide deck and an Excel breakdown of high-volume NSCLC oncologists in California and New York.",
  "Build an Excel breakdown of C341 claim volume by physician specialty and state.",
  "Write a two-page market access report on NSCLC physician density in the Northeast.",
  "Run an analysis and show me which states have the highest concentration of high-volume NSCLC prescribers.",
];

const DEFAULT_QUERY = SAMPLE_QUERIES[0];

function App() {
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [icd10Codes, setIcd10Codes] = useState("C341, C342");
  const [states, setStates] = useState("CA, NY");
  const [regions, setRegions] = useState("");
  const [specialties, setSpecialties] = useState("Medical Oncology");
  const [volumeThreshold, setVolumeThreshold] = useState<"low" | "high" | "very_high">("high");
  const [boardCertified, setBoardCertified] = useState(true);
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [liveTrace, setLiveTrace] = useState<TraceEvent[]>([]);
  const [physicians, setPhysicians] = useState<Physician[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoadingPhysicians, setIsLoadingPhysicians] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const preferences = useMemo<QueryPreferences>(
    () => ({
      icd10Codes: splitList(icd10Codes),
      states: splitList(states).map((state) => state.toUpperCase()),
      regions: splitList(regions),
      specialties: splitList(specialties),
      volumeThreshold,
      boardCertified,
    }),
    [boardCertified, icd10Codes, regions, specialties, states, volumeThreshold],
  );

  const requestedArtifacts = useMemo<ArtifactType[]>(() => inferRequestedArtifacts(query), [query]);

  async function handlePreviewPhysicians() {
    setIsLoadingPhysicians(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      preferences.states.forEach((state) => params.append("state", state));
      preferences.regions.forEach((region) => params.append("region", region));
      preferences.specialties.forEach((specialty) => params.append("specialty", specialty));
      preferences.icd10Codes.forEach((code) => params.append("icd10_codes", code));
      if (preferences.volumeThreshold) {
        params.set("volume_threshold", preferences.volumeThreshold);
      }
      if (preferences.boardCertified !== null && preferences.boardCertified !== undefined) {
        params.set("board_certified", String(preferences.boardCertified));
      }

      const result = await fetchPhysicians(params);
      setPhysicians(result.physicians);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load physicians.");
    } finally {
      setIsLoadingPhysicians(false);
    }
  }

  async function handleRunQuery() {
    setIsRunning(true);
    setError(null);
    setResponse(null);
    setLiveTrace([]);
    try {
      const result = await runQueryStream(
        {
          query,
          preferences,
          requestedArtifacts,
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
      if (result.metadata.toolCalls) {
        void handlePreviewPhysicians();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Query failed.");
    } finally {
      setIsRunning(false);
    }
  }

  const chartArtifact = response?.artifacts.find((artifact) => artifact.id === response.sandboxOutput?.chartArtifactId);

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

          <div className="preference-grid">
            <Field label="ICD-10 Codes">
              <input value={icd10Codes} onChange={(event) => setIcd10Codes(event.target.value)} />
            </Field>
            <Field label="States">
              <input value={states} onChange={(event) => setStates(event.target.value)} />
            </Field>
            <Field label="Regions">
              <input value={regions} onChange={(event) => setRegions(event.target.value)} placeholder="northeast" />
            </Field>
            <Field label="Specialties">
              <input value={specialties} onChange={(event) => setSpecialties(event.target.value)} />
            </Field>
            <Field label="Volume">
              <select value={volumeThreshold} onChange={(event) => setVolumeThreshold(event.target.value as typeof volumeThreshold)}>
                <option value="low">Low+</option>
                <option value="high">High+</option>
                <option value="very_high">Very high</option>
              </select>
            </Field>
            <label className="check-row">
              <input checked={boardCertified} type="checkbox" onChange={(event) => setBoardCertified(event.target.checked)} />
              Board certified
            </label>
          </div>

          <div className="action-row">
            <button className="secondary" type="button" onClick={handlePreviewPhysicians} disabled={isLoadingPhysicians}>
              {isLoadingPhysicians ? <Loader2 className="spin" size={17} /> : <Search size={17} />}
              Preview Physicians
            </button>
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
              <ReactMarkdown>{response.answerMarkdown}</ReactMarkdown>
            </div>
          ) : (
            <EmptyState text="Run a query to render report text, generated analysis, and artifact links." />
          )}

          {response?.sandboxOutput ? (
            <div className="sandbox-box">
              <div className="sandbox-header">
                <FlaskConical size={17} />
                <strong>Sandbox Output</strong>
                <span>{response.sandboxOutput.executionStatus}</span>
              </div>
              <pre>{response.sandboxOutput.code}</pre>
              {response.sandboxOutput.stdout ? <code className="stdout">{response.sandboxOutput.stdout}</code> : null}
              {response.sandboxOutput.stderr ? <code className="stderr">{response.sandboxOutput.stderr}</code> : null}
              {chartArtifact ? <img alt="Sandbox chart" src={artifactUrl(chartArtifact.downloadUrl)} /> : null}
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
                  <span>{artifact.filename}</span>
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

function Field({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
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
        </li>
      ))}
    </ol>
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

function EmptyState({ text }: { text: string }) {
  return <div className="empty-state">{text}</div>;
}

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function inferRequestedArtifacts(value: string): ArtifactType[] {
  const lower = value.toLowerCase();
  const artifacts = new Set<ArtifactType>();
  if (lower.includes("slide") || lower.includes("deck") || lower.includes("powerpoint") || lower.includes("ppt")) {
    artifacts.add("pptx");
  }
  if (lower.includes("excel") || lower.includes("spreadsheet") || lower.includes("workbook") || lower.includes("breakdown")) {
    artifacts.add("xlsx");
  }
  if (lower.includes("report") || lower.includes("memo") || lower.includes("brief")) {
    artifacts.add("markdown");
  }
  if (lower.includes("analysis") || lower.includes("chart") || lower.includes("plot") || lower.includes("distribution")) {
    artifacts.add("chart_png");
  }
  return Array.from(artifacts);
}

function artifactIcon(type: ArtifactType) {
  if (type === "pptx") return <Presentation size={17} />;
  if (type === "xlsx") return <FileSpreadsheet size={17} />;
  if (type === "chart_png" || type === "chart_svg") return <BarChart3 size={17} />;
  return <FileText size={17} />;
}

export default App;
