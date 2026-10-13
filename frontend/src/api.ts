import type { ChatResponse, Company, CrawlJob } from "./types";

const API_BASE = import.meta.env.VITE_API_URL ?? "/api";
const REQUEST_TIMEOUT_MS = 35000;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = sessionStorage.getItem("fieldnote_token");
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers, signal: controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(408, "The API took too long to respond. Is the backend running on port 8000?");
    }
    throw new ApiError(503, "Unable to reach the API. Start the backend on port 8000 and try again.");
  } finally {
    window.clearTimeout(timeout);
  }
  if (!response.ok) {
    let message = "Something went wrong. Please try again.";
    try {
      const body = await response.json();
      message = body.detail ?? message;
    } catch { /* non-JSON error */ }
    throw new ApiError(response.status, message);
  }
  return response.json() as Promise<T>;
}

export const api = {
  login: (email: string, password: string) => request<{ access_token: string }>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  register: (email: string, password: string) => request<{ message: string }>("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => request<{ message: string }>("/auth/logout", { method: "POST" }),
  companies: () => request<Company[]>("/companies"),
  company: (id: number) => request<Company>(`/companies/${id}`),
  createCompany: (payload: { name: string; website_url: string }) => request<Company>("/companies", { method: "POST", body: JSON.stringify(payload) }),
  crawlJobs: (companyId: number) => request<CrawlJob[]>(`/companies/${companyId}/crawl-jobs`),
  crawlJob: (companyId: number, jobId: number) => request<CrawlJob>(`/companies/${companyId}/crawl-jobs/${jobId}`),
  createCrawl: (companyId: number, payload: { max_pages: number; max_depth: number }) => request<{ job_id: number; company_id: number; status: string }>(`/companies/${companyId}/crawl`, { method: "POST", body: JSON.stringify(payload) }),
  cancelCrawl: (companyId: number, jobId: number) => request<{ message: string }>(`/companies/${companyId}/crawl-jobs/${jobId}/cancel`, { method: "POST" }),
  chat: (company_id: number, question: string) => request<ChatResponse>("/chat", { method: "POST", body: JSON.stringify({ company_id, question }) }),
};
