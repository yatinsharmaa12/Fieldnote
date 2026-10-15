import { useEffect, useReducer, useState } from "react";
import { api, ApiError, isAbortError } from "../api";
import type { CrawlJob } from "../types";
const fetchJob = api.crawlJob;

const terminal = new Set(["COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"]);

export function useCrawlStatus(companyId: number | null, jobId: number | null) {
  const [snapshot, setSnapshot] = useState<{ companyId: number; jobId: number; job: CrawlJob } | null>(null);
  const [error, setError] = useState("");
  const [revision, retry] = useReducer(value => value + 1, 0);
  useEffect(() => {
    setError("");
    if (!companyId || !jobId) return;
    let active = true;
    let finished = false;
    let failures = 0;
    let timer: number | undefined;
    let controller: AbortController | null = null;
    const schedule = (delay: number) => { timer = window.setTimeout(poll, delay); };
    const poll = async () => {
      if (!active || finished || controller) return;
      if (document.hidden) { schedule(2500); return; }
      controller = new AbortController();
      try {
        const next = await fetchJob(companyId, jobId, controller.signal);
        if (!active) return;
        setSnapshot({ companyId, jobId, job: next });
        setError("");
        failures = 0;
        finished = terminal.has(next.status);
        if (!finished) schedule(2500);
      } catch (error) {
        if (!active || isAbortError(error)) return;
        setError(error instanceof Error ? error.message : "Unable to load crawl status.");
        if (error instanceof ApiError && [401, 403, 404].includes(error.status)) finished = true;
        else schedule(Math.min(1000 * 2 ** failures++, 10000));
      } finally { controller = null; }
    };
    const resume = () => {
      if (!document.hidden && !controller && !finished) {
        window.clearTimeout(timer);
        void poll();
      }
    };
    void poll();
    document.addEventListener("visibilitychange", resume);
    return () => {
      active = false;
      window.clearTimeout(timer);
      controller?.abort();
      document.removeEventListener("visibilitychange", resume);
    };
  }, [companyId, jobId, revision]);
  const job = snapshot?.companyId === companyId && snapshot?.jobId === jobId ? snapshot.job : null;
  return { job, error, retry };
}
