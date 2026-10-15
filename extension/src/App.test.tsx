import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { askCompany } from "./api/chat";
import { listCompanies } from "./api/companies";
import { listCrawlJobs } from "./api/crawl";
import { useCurrentTab } from "./hooks/useCurrentTab";
import type { ChatResponse, CrawlJob } from "./types";

vi.mock("./hooks/useAuth", () => ({ useAuth: () => ({ token: "test", loading: false, signOut: vi.fn() }) }));
vi.mock("./hooks/useCurrentTab", () => ({ useCurrentTab: vi.fn() }));
vi.mock("./hooks/useCrawlStatus", () => ({ useCrawlStatus: () => ({ job: null, error: "", retry: vi.fn() }) }));
vi.mock("./api/companies", () => ({ listCompanies: vi.fn(), createCompany: vi.fn() }));
vi.mock("./api/crawl", () => ({ listCrawlJobs: vi.fn(), startCrawl: vi.fn(), cancelCrawl: vi.fn() }));
vi.mock("./api/chat", () => ({ askCompany: vi.fn(), uniqueSources: (sources: ChatResponse["sources"]) => sources }));

describe("website assistant", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Element.prototype.scrollIntoView = vi.fn();
    vi.mocked(useCurrentTab).mockReturnValue({ hostname: "acme.com", url: "https://acme.com" });
    vi.mocked(listCompanies).mockResolvedValue([
      { id: 1, name: "Acme", website_url: "https://acme.com" },
      { id: 2, name: "Example", website_url: "https://example.com" },
    ]);
    vi.mocked(listCrawlJobs).mockResolvedValue([{ job_id: 1, status: "COMPLETED", pages_indexed: 2 } as CrawlJob]);
  });
  afterEach(cleanup);

  it("aborts the previous site's question and ignores its late answer after switching tabs", async () => {
    let finish!: (answer: ChatResponse) => void;
    vi.mocked(askCompany).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const view = render(<App />);
    fireEvent.change(await screen.findByLabelText("Question"), { target: { value: "What is Acme?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    const signal = vi.mocked(askCompany).mock.calls[0][2];
    expect(signal?.aborted).toBe(false);
    expect(screen.getByRole("button", { name: "Stop" })).toBeVisible();

    vi.mocked(useCurrentTab).mockReturnValue({ hostname: "example.com", url: "https://example.com" });
    view.rerender(<App />);
    await screen.findByRole("heading", { name: "Example" });
    expect(signal?.aborted).toBe(true);
    await act(async () => finish({ answer: "Old Acme answer", sources: [] }));
    expect(screen.queryByText("Old Acme answer")).not.toBeInTheDocument();
    expect(screen.queryByText("What is Acme?")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Question")).toHaveValue("");
  });

  it("shows a retry action for a timed-out crawl", async () => {
    vi.mocked(listCrawlJobs).mockResolvedValue([{ job_id: 1, status: "TIMED_OUT", pages_indexed: 0, error: null } as CrawlJob]);
    render(<App />);
    expect(await screen.findByRole("button", { name: "Try again" })).toBeEnabled();
    expect(screen.getByText(/last crawl timed out/i)).toBeVisible();
    expect(screen.queryByLabelText("Question")).not.toBeInTheDocument();
  });
});
