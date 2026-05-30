import type { ArtifactRef, PhysicianListResponse, QueryRequest, QueryResponse, QueryStreamEvent, TraceEvent } from "./types";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export async function runQuery(payload: QueryRequest): Promise<QueryResponse> {
  const response = await fetch(`${API_BASE_URL}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Query failed with ${response.status}`);
  }

  return response.json();
}

export async function runQueryStream(
  payload: QueryRequest,
  handlers: { onTrace: (event: TraceEvent) => void },
): Promise<QueryResponse> {
  const response = await fetch(`${API_BASE_URL}/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Query failed with ${response.status}`);
  }

  if (!response.body) {
    throw new Error("Query stream did not include a response body.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult: QueryResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      buffer += decoder.decode();
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      finalResult = handleStreamLine(line, handlers) ?? finalResult;
    }
  }

  if (buffer.trim()) {
    finalResult = handleStreamLine(buffer, handlers) ?? finalResult;
  }

  if (!finalResult) {
    throw new Error("Query stream ended before returning a final result.");
  }

  return finalResult;
}

export async function fetchPhysicians(params: URLSearchParams): Promise<PhysicianListResponse> {
  const response = await fetch(`${API_BASE_URL}/physicians?${params.toString()}`);

  if (!response.ok) {
    throw new Error(`Physician request failed with ${response.status}`);
  }

  return response.json();
}

export function artifactUrl(downloadUrl: string): string {
  if (downloadUrl.startsWith("http")) {
    return downloadUrl;
  }
  return `${API_BASE_URL}${downloadUrl}`;
}

export async function downloadArtifact(artifact: ArtifactRef): Promise<void> {
  const response = await fetch(artifactUrl(artifact.downloadUrl));
  if (!response.ok) {
    throw new Error(`Artifact download failed with ${response.status}`);
  }

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = artifact.filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

function handleStreamLine(
  line: string,
  handlers: { onTrace: (event: TraceEvent) => void },
): QueryResponse | null {
  if (!line.trim()) {
    return null;
  }

  const event = JSON.parse(line) as QueryStreamEvent;
  if (event.type === "trace") {
    handlers.onTrace(event.data);
    return null;
  }
  if (event.type === "result") {
    return event.data;
  }
  throw new Error(event.data.message);
}
