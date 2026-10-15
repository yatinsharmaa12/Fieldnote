import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./api";

describe("API contract", () => {
  afterEach(() => vi.useRealTimers());
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("logs in, sends bearer auth, and creates a company", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "token-1" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 4, name: "Acme", website_url: "https://acme.com" }), { status: 200 }));

    const login = await api.login("person@acme.com", "secret");
    sessionStorage.setItem("fieldnote_token", login.access_token);
    await api.createCompany({ name: "Acme", website_url: "https://acme.com" });

    expect(JSON.parse(fetchMock.mock.calls[0][1]?.body as string)).toEqual({ email: "person@acme.com", password: "secret" });
    expect(new Headers(fetchMock.mock.calls[1][1]?.headers).get("Authorization")).toBe("Bearer token-1");
  });

  it("maps crawl, cancellation, statistics, and chat to existing routes", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ job_id: 8, company_id: 3, status: "QUEUED" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ message: "Job cancelled" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ answer: "Yes", sources: [{ title: "About", url: "https://acme.com/about" }] }), { status: 200 }));
    sessionStorage.setItem("fieldnote_token", "token-1");

    expect(await api.createCrawl(3, { max_pages: 10, max_depth: 2 })).toMatchObject({ job_id: 8 });
    expect(await api.cancelCrawl(3, 8)).toEqual({ message: "Job cancelled" });
    expect(await api.chat(3, "What do you do?")).toMatchObject({ answer: "Yes" });
  });

  it("surfaces authentication and API errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: "Invalid email or password" }), { status: 401 }));
    await expect(api.login("bad@example.com", "bad")).rejects.toEqual(expect.objectContaining({ status: 401, message: "Invalid email or password" } satisfies Partial<ApiError>));
  });

  it("turns an unreachable backend into a useful connection error", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(api.login("person@acme.com", "secret")).rejects.toEqual(expect.objectContaining({ status: 503, message: expect.stringContaining("backend") }));
  });

  it("shares identical in-flight reads without caching stale results", async () => {
    let finish!: (response: Response) => void;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const first = api.companies();
    const second = api.companies();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    finish(new Response("[]"));
    await Promise.all([first, second]);
    fetchMock.mockResolvedValueOnce(new Response("[]"));
    await api.companies();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("keeps the chat timeout active while reading the response body", async () => {
    vi.useFakeTimers();
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, options) => ({
      ok: true,
      json: () => new Promise((_resolve, reject) => options?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")))),
    } as Response));
    const outcome = api.chat(3, "Question").catch(error => error);
    await vi.advanceTimersByTimeAsync(35000);
    expect(vi.getTimerCount()).toBe(1);
    await vi.advanceTimersByTimeAsync(10000);
    expect(await outcome).toMatchObject({ status: 408 });
    expect(vi.getTimerCount()).toBe(0);
  });

  it("preserves caller cancellation instead of reporting a server error", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((_url, options) => new Promise((_resolve, reject) => options?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")))));
    const controller = new AbortController();
    const outcome = api.chat(3, "Question", controller.signal).catch(error => error);
    controller.abort();
    expect(await outcome).toMatchObject({ name: "AbortError" });
  });

  it("expires the current session and flattens validation errors", async () => {
    sessionStorage.setItem("fieldnote_token", "expired");
    const expired = vi.fn();
    window.addEventListener("fieldnote:session-expired", expired, { once: true });
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response('{"detail":"Expired"}', { status: 401 }))
      .mockResolvedValueOnce(new Response('{"detail":[{"msg":"Invalid URL"}]}', { status: 422 }));
    await expect(api.company(3)).rejects.toMatchObject({ status: 401 });
    expect(sessionStorage.getItem("fieldnote_token")).toBeNull();
    expect(expired).toHaveBeenCalledOnce();
    await expect(api.createCompany({ name: "Acme", website_url: "invalid" })).rejects.toMatchObject({ message: "Invalid URL" });
  });
});
