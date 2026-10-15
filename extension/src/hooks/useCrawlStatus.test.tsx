import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useCrawlStatus } from "./useCrawlStatus";
import type { CrawlJob } from "../types";
import { getCrawlJob as fetchJob } from "../api/crawl";
vi.mock("../api/crawl", () => ({ getCrawlJob: vi.fn() }));

const job = { job_id: 8, company_id: 3, status: "RUNNING" } as CrawlJob;
beforeEach(() => { vi.useFakeTimers(); vi.clearAllMocks(); vi.spyOn(document, "hidden", "get").mockReturnValue(false); });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); });

it("recovers after a transient failure and stops polling timed-out jobs", async () => {
  vi.mocked(fetchJob).mockRejectedValueOnce(new Error("Connection lost")).mockResolvedValueOnce({ ...job, status: "TIMED_OUT" });
  const { result } = renderHook(() => useCrawlStatus(3, 8));
  await act(async () => {});
  expect(result.current.error).toBe("Connection lost");
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(result.current.job?.status).toBe("TIMED_OUT");
  expect(result.current.error).toBe("");
  await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
  expect(fetchJob).toHaveBeenCalledTimes(2);
});

it("aborts an old poll and ignores it after switching jobs", async () => {
  let resolveOld!: (job: CrawlJob) => void;
  vi.mocked(fetchJob).mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve; })).mockResolvedValueOnce({ ...job, job_id: 9, status: "COMPLETED" });
  const { result, rerender } = renderHook(({ id }) => useCrawlStatus(3, id), { initialProps: { id: 8 } });
  const signal = vi.mocked(fetchJob).mock.calls[0][2];
  rerender({ id: 9 });
  await act(async () => {});
  expect(signal?.aborted).toBe(true);
  await act(async () => resolveOld(job));
  expect(result.current.job?.job_id).toBe(9);
});

it("pauses requests while hidden and resumes on visibility", async () => {
  vi.spyOn(document, "hidden", "get").mockReturnValue(true);
  vi.mocked(fetchJob).mockResolvedValue({ ...job, status: "COMPLETED" });
  renderHook(() => useCrawlStatus(3, 8));
  expect(fetchJob).not.toHaveBeenCalled();
  vi.spyOn(document, "hidden", "get").mockReturnValue(false);
  await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });
  expect(fetchJob).toHaveBeenCalledTimes(1);
});
