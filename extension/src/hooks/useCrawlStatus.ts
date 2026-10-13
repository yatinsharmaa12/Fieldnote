import { useEffect, useState } from "react";
import { getCrawlJob } from "../api/crawl";
import type { CrawlJob } from "../types";

const terminal = new Set(["COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"]);
export function useCrawlStatus(companyId: number | null, jobId: number | null) {
  const [job, setJob] = useState<CrawlJob | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!companyId || !jobId) { setJob(null); setError(""); return; }
    let active = true; let timer: number | undefined;
    const poll = async () => {
      try {
        const next = await getCrawlJob(companyId, jobId);
        if (!active) return;
        setJob(next);
        if (!terminal.has(next.status)) timer = window.setTimeout(poll, 2500);
      } catch (e) { if (active) setError(e instanceof Error ? e.message : "Unable to load crawl status."); }
    };
    poll();
    return () => { active = false; if (timer) window.clearTimeout(timer); };
  }, [companyId, jobId]);
  return { job, error, setJob };
}
