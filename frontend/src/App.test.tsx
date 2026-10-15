import { describe, expect, it, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./auth";
import { api } from "./api";

vi.mock("./api", () => ({
  ApiError: class ApiError extends Error { status = 500; },
  api: {
    companies: vi.fn().mockResolvedValue([{ id: 3, name: "Acme", website_url: "https://acme.com" }]),
    company: vi.fn().mockResolvedValue({ id: 3, name: "Acme", website_url: "https://acme.com" }),
    crawlJobs: vi.fn().mockResolvedValue([]),
    createCompany: vi.fn(), createCrawl: vi.fn(), crawlJob: vi.fn(), cancelCrawl: vi.fn(), chat: vi.fn(), login: vi.fn(), register: vi.fn(),
  },
}));

describe("authenticated product shell", () => {
  beforeEach(() => sessionStorage.setItem("fieldnote_token", "test-token"));
  it("loads the company list and shows an open company", async () => {
    render(<AuthProvider><MemoryRouter initialEntries={["/"]}><App /></MemoryRouter></AuthProvider>);
    expect(await screen.findByText("Acme")).toBeInTheDocument();
    expect(screen.getByText("Add company")).toBeInTheDocument();
  });

  it("shows a company empty state when there is no crawl history", async () => {
    render(<AuthProvider><MemoryRouter initialEntries={["/companies/3"]}><App /></MemoryRouter></AuthProvider>);
    await waitFor(() => expect(screen.getByText("Not crawled yet")).toBeInTheDocument());
    expect(screen.getByText("Start crawl")).toBeInTheDocument();
    expect(screen.getByText("Company chat")).toBeInTheDocument();
  });

  it("polls an active crawl and stops when it reaches a terminal status", async () => {
    const user = userEvent.setup();
    const job = { job_id: 8, company_id: 3, status: "QUEUED", max_pages: 5, max_depth: 1, pages_discovered: 2, pages_crawled: 1, pages_indexed: 1, pages_failed: 0, pages_new: 1, pages_changed: 0, pages_unchanged: 0, pages_deactivated: 0, attempt_count: 1, error: null, created_at: "2026-01-01T12:00:00Z", started_at: null, completed_at: null, duration_seconds: null };
    vi.mocked(api.crawlJobs).mockResolvedValueOnce([job]);
    vi.mocked(api.crawlJob).mockResolvedValueOnce(job).mockResolvedValueOnce({ ...job, status: "COMPLETED", completed_at: "2026-01-01T12:00:03Z", duration_seconds: 3 });
    render(<AuthProvider><MemoryRouter initialEntries={["/companies/3"]}><App /></MemoryRouter></AuthProvider>);
    await screen.findByText("Queued");
    await screen.findByText("Open crawl details");
    await user.click(await screen.findByText("Open crawl details"));
    expect(await screen.findByRole("heading", { name: "Completed" })).toBeInTheDocument();
    expect(api.crawlJob).toHaveBeenCalledWith(3, 8, expect.any(AbortSignal));
  });
});

describe("account creation", () => {
  it("registers and signs the user in", async () => {
    const user = userEvent.setup();
    sessionStorage.clear();
    vi.mocked(api.register).mockResolvedValue({ message: "If this email is new, an account was created. Try signing in." });
    vi.mocked(api.login).mockResolvedValue({ access_token: "new-token" });
    render(<AuthProvider><MemoryRouter initialEntries={["/login"]}><App /></MemoryRouter></AuthProvider>);
    await user.click(screen.getByRole("link", { name: "Create one" }));
    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.type(screen.getByLabelText("Confirm password"), "password123");
    await user.click(screen.getByRole("button", { name: /create account/i }));
    await waitFor(() => expect(api.register).toHaveBeenCalledWith("new@example.com", "password123"));
    expect(api.login).toHaveBeenCalledWith("new@example.com", "password123");
  });
});
