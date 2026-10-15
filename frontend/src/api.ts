import type { ChatResponse, Company, CrawlJob } from "./types";

const API_BASE = import.meta.env.VITE_API_URL ?? "/api";
const REQUEST_TIMEOUT_MS = 12000;
const CHAT_TIMEOUT_MS = 45000;
const pendingReads = new Map<string, Promise<unknown>>();

export const isAbortError = (error: unknown) => error instanceof DOMException && error.name === "AbortError";

function errorDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(item => typeof item?.msg === "string" ? item.msg : "Invalid input").join(". ");
  return "Something went wrong. Please try again.";
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const key = (sessionStorage.getItem("fieldnote_token") ?? "") + ":" + path;
  if (!options.signal && (!options.method || options.method === "GET")) {
    const pending = pendingReads.get(key);
    if (pending) return pending as Promise<T>;
    const promise = performRequest<T>(path, options).finally(() => pendingReads.delete(key));
    pendingReads.set(key, promise);
    return promise;
  }
  return performRequest<T>(path, options);
}

async function performRequest<T>(path: string, options: RequestInit): Promise<T> {
  const token = sessionStorage.getItem("fieldnote_token");
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (options.signal?.aborted) throw new DOMException("Request cancelled", "AbortError");
  options.signal?.addEventListener("abort", abort, { once: true });
  const timeout = window.setTimeout(abort, path === "/chat" ? CHAT_TIMEOUT_MS : REQUEST_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers, signal: controller.signal });
    if (!response.ok) {
      let message = "Something went wrong. Please try again.";
      try { message = errorDetail((await response.json()).detail); } catch (error) { if (isAbortError(error)) throw error; }
      if (response.status === 401 && token && sessionStorage.getItem("fieldnote_token") === token) {
        sessionStorage.removeItem("fieldnote_token");
        window.dispatchEvent(new Event("fieldnote:session-expired"));
      }
      throw new ApiError(response.status, message);
    }
    return await response.json() as T;
  } catch (error) {
    if (options.signal?.aborted) throw new DOMException("Request cancelled", "AbortError");
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(408, "This is taking longer than expected. Please try again.");
    }
    throw new ApiError(503, "Unable to reach the API. Start the backend on port 8000 and try again.");
  } finally {
    window.clearTimeout(timeout);
    options.signal?.removeEventListener("abort", abort);
  }
}

export const api = {
  login: (email: string, password: string) => request<{ access_token: string }>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  register: (email: string, password: string) => request<{ message: string }>("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => request<{ message: string }>("/auth/logout", { method: "POST" }),
  companies: () => request<Company[]>("/companies"),
  company: (id: number) => request<Company>(`/companies/${id}`),
  createCompany: (payload: { name: string; website_url: string }) => request<Company>("/companies", { method: "POST", body: JSON.stringify(payload) }),
  crawlJobs: (companyId: number) => request<CrawlJob[]>(`/companies/${companyId}/crawl-jobs`),
  crawlJob: (companyId: number, jobId: number, signal?: AbortSignal) => request<CrawlJob>(`/companies/${companyId}/crawl-jobs/${jobId}`, { signal }),
  createCrawl: (companyId: number, payload: { max_pages: number; max_depth: number }) => request<{ job_id: number; company_id: number; status: string }>(`/companies/${companyId}/crawl`, { method: "POST", body: JSON.stringify(payload) }),
  cancelCrawl: (companyId: number, jobId: number) => request<{ message: string }>(`/companies/${companyId}/crawl-jobs/${jobId}/cancel`, { method: "POST" }),
  chat: (company_id: number, question: string, signal?: AbortSignal) => request<ChatResponse>("/chat", { method: "POST", body: JSON.stringify({ company_id, question }), signal }),
};
