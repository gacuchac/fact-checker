import type {
  ClaimRun,
  ConfirmedStatements,
  ConfirmIssue,
  Doc,
  DocSummary,
  Edit,
  ProposedClaim,
  RunSummary,
  Trace,
} from "./types";

const STORAGE_KEY = "fc-access-code";

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown) {
    super(detailOf(body) ?? `request failed with status ${status}`);
    this.status = status;
    this.body = body;
  }
}

export type AccessCodePrompt = () => Promise<string>;

let prompt: AccessCodePrompt | null = null;
let pendingCode: Promise<string> | null = null;

function detailOf(body: unknown): string | null {
  if (typeof body === "object" && body !== null && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    return typeof detail === "string" ? detail : null;
  }
  return null;
}

export function getAccessCode(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function saveAccessCode(code: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, code);
  } catch {
    // storage unavailable: the code is only kept for this request
  }
}

/** Register the function that asks the user for an access code on a 401; pass null to remove it. */
export function setAccessCodePrompt(fn: AccessCodePrompt | null): void {
  prompt = fn;
}

function askForCode(): Promise<string> {
  if (prompt === null) return Promise.reject(new ApiError(401, { detail: "access code required" }));
  pendingCode ??= prompt().finally(() => {
    pendingCode = null;
  });
  return pendingCode;
}

async function send(path: string, init: RequestInit, code: string | null): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body !== undefined) headers.set("Content-Type", "application/json");
  if (code) headers.set("X-Access-Code", code);
  return fetch(path, { ...init, headers });
}

async function parse(response: Response): Promise<unknown> {
  const text = await response.text();
  if (text === "") return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return { detail: text };
  }
}

/** Fetch JSON from the API with the stored access code; on a 401, ask for a code, save it and retry once. Throws ApiError on any non-2xx. */
export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response = await send(path, init, getAccessCode());
  if (response.status === 401) {
    const code = await askForCode();
    saveAccessCode(code);
    response = await send(path, init, code);
  }
  const body = await parse(response);
  if (!response.ok) throw new ApiError(response.status, body);
  return body as T;
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
}

export function createClaim(claim: string): Promise<ProposedClaim> {
  return post("/api/claims", { claim });
}

export function confirmClaim(runId: string, edits: Edit[]): Promise<{ confirmed: ConfirmedStatements }> {
  return post(`/api/claims/${runId}/confirm`, { edits });
}

export function verifyClaim(runId: string): Promise<{ run_id: string; status: string }> {
  return post(`/api/claims/${runId}/verify`);
}

export function getClaim(runId: string): Promise<ClaimRun> {
  return request(`/api/claims/${runId}`);
}

export function listRuns(limit = 50): Promise<RunSummary[]> {
  return request(`/api/runs?limit=${limit}`);
}

export function getTrace(runId: string): Promise<Trace> {
  return request(`/api/runs/${runId}/trace`);
}

export function searchDocs(q: string, limit = 20): Promise<DocSummary[]> {
  return request(`/api/docs?q=${encodeURIComponent(q)}&limit=${limit}`);
}

export function getDoc(docId: string): Promise<Doc> {
  return request(`/api/docs/${encodeURIComponent(docId)}`);
}

export function confirmIssues(error: unknown): ConfirmIssue[] | null {
  if (!(error instanceof ApiError) || error.status !== 422) return null;
  const body = error.body as { issues?: ConfirmIssue[] } | null;
  return body?.issues ?? null;
}
