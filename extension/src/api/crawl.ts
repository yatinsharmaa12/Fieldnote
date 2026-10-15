import { request } from "./client";
import type { CrawlJob } from "../types";
export const listCrawlJobs = (companyId: number) => request<CrawlJob[]>(`/companies/${companyId}/crawl-jobs`);
export const getCrawlJob = (companyId: number, jobId: number, signal?: AbortSignal) => request<CrawlJob>(`/companies/${companyId}/crawl-jobs/${jobId}`, { signal });
export const startCrawl = (companyId: number, payload = { max_pages: 5, max_depth: 1 }) => request<{ job_id: number }>(`/companies/${companyId}/crawl`, { method: "POST", body: JSON.stringify(payload) });
export const cancelCrawl = (companyId: number, jobId: number) => request<{ message: string }>(`/companies/${companyId}/crawl-jobs/${jobId}/cancel`, { method: "POST" });
