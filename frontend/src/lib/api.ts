import type {
  DatasetName,
  DQIssue,
  EvaluationReport,
  IssueResult,
  ModelStatusResponse,
  OverviewResponse,
  ReviewRecord,
} from "./types";

export const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

const CACHE_TTL_MS = 30_000;
const responseCache = new Map<string, { ts: number; data: unknown }>();
const inflightCache = new Map<string, Promise<unknown>>();

export function clearApiCache() {
  responseCache.clear();
  inflightCache.clear();
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method || "GET").toUpperCase();
  if (method !== "GET") {
    clearApiCache();
  } else {
    const cached = responseCache.get(path);
    if (cached && Date.now() - cached.ts < CACHE_TTL_MS) {
      return cached.data as T;
    }
    const inflight = inflightCache.get(path);
    if (inflight) {
      return (await inflight) as T;
    }
  }

  const reqPromise = (async () => {
    const res = await fetch(`${API_BASE}${path}`, {
      ...init,
      cache: "no-store",
    });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        if (body?.detail) detail = String(body.detail);
      } catch {
        // ignore parse failure
      }
      throw new Error(detail);
    }
    const data = (await res.json()) as T;
    if (method === "GET") {
      responseCache.set(path, { ts: Date.now(), data });
    }
    return data;
  })();

  if (method === "GET") {
    inflightCache.set(path, reqPromise);
  }
  try {
    return await reqPromise;
  } finally {
    if (method === "GET") {
      inflightCache.delete(path);
    }
  }
}

export function getOverview(dataset: DatasetName): Promise<OverviewResponse> {
  return apiFetch(`/api/overview?dataset=${dataset}`);
}

export function getIssues(
  dataset: DatasetName,
  params?: Record<string, string | boolean | undefined>
): Promise<{
  run_id: string;
  dataset: string;
  mode: string;
  variant: string;
  status: string;
  model: string | null;
  notes: string[];
  total: number;
  filtered: number;
  issues: IssueResult[];
}> {
  const q = new URLSearchParams({ dataset });
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") q.set(k, String(v));
    }
  }
  return apiFetch(`/api/issues?${q.toString()}`);
}

export function getIssueDetail(
  issueId: string,
  dataset: DatasetName
): Promise<{
  run_id: string;
  dataset: string;
  mode: string;
  variant: string;
  issue: IssueResult;
  reviews: ReviewRecord[];
  dq_related: DQIssue[];
}> {
  return apiFetch(`/api/issues/${encodeURIComponent(issueId)}?dataset=${dataset}`);
}

export function submitReview(
  issueId: string,
  dataset: DatasetName,
  payload: Record<string, unknown>
): Promise<{ run_id: string; issue: IssueResult; review: ReviewRecord }> {
  return apiFetch(`/api/issues/${encodeURIComponent(issueId)}/review?dataset=${dataset}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getReviews(
  dataset: DatasetName,
  issueId?: string
): Promise<{ run_id: string; count: number; reviews: ReviewRecord[] }> {
  const q = new URLSearchParams({ dataset });
  if (issueId) q.set("issue_id", issueId);
  return apiFetch(`/api/reviews?${q.toString()}`);
}

export function runRulesPipeline(dataset: DatasetName, version: "v1" | "v2") {
  return apiFetch<{ run_id: string; variant: string; status: string; notes: string[] }>(
    `/api/processing/rules?dataset=${dataset}&version=${version}`,
    { method: "POST" }
  );
}

export function runAiPipeline(dataset: DatasetName, promptVersion: "v1" | "v2" = "v1") {
  return apiFetch<{ run_id: string; variant: string; status: string; notes: string[]; model: string | null }>(
    `/api/processing/ai?dataset=${dataset}&prompt_version=${promptVersion}`,
    { method: "POST" }
  );
}

export function getLatestEvaluation(dataset: DatasetName): Promise<EvaluationReport> {
  return apiFetch(`/api/evaluation/latest?dataset=${dataset}`);
}

export function runEvaluation(dataset: DatasetName, includeAi: boolean): Promise<EvaluationReport> {
  return apiFetch(`/api/processing/evaluate?dataset=${dataset}&include_ai=${includeAi}`, { method: "POST" });
}

export function getQualityReport(dataset: DatasetName): Promise<{
  dataset: string;
  updated_at: string;
  files: Record<string, { rows: number; bytes: number }>;
  summary: { total: number; error: number; warning: number; info: number; human_review_required: number };
  issues: DQIssue[];
}> {
  return apiFetch(`/api/data/quality-report?dataset=${dataset}`);
}

export async function uploadCsv(kind: "bookings" | "inbox", dataset: DatasetName, file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/data/upload/${kind}?dataset=${dataset}`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const b = await res.json().catch(() => ({}));
    throw new Error(b.detail || `Upload failed (${res.status})`);
  }
  clearApiCache();
  return res.json();
}

export function resetDataset(dataset: DatasetName) {
  return apiFetch(`/api/data/reset?dataset=${dataset}`, { method: "POST" });
}

export function getModelStatus(): Promise<ModelStatusResponse> {
  return apiFetch(`/api/model/status`);
}

export function exportUrl(kind: "queue" | "evaluation" | "issues-report", format: string, dataset: DatasetName): string {
  return `${API_BASE}/api/exports/${kind}?format=${format}&dataset=${dataset}`;
}

