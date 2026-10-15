import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { api } from "../api";
import { ChatPanel } from "./ChatPanel";

vi.mock("../api", async importOriginal => ({ ...await importOriginal<typeof import("../api")>(), api: { chat: vi.fn() } }));
const company = { id: 3, name: "Acme", website_url: "https://acme.com" };
beforeEach(() => vi.clearAllMocks());

it("stops an answer immediately, ignores its late result, and retains the question", async () => {
  let finish!: (value: { answer: string; sources: [] }) => void;
  vi.mocked(api.chat).mockReturnValue(new Promise(resolve => { finish = resolve; }));
  render(<ChatPanel company={company} />);
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "What do you do?" } });
  fireEvent.click(screen.getByRole("button", { name: "Send question" }));
  expect(screen.getByRole("status")).toHaveTextContent("preparing");
  const signal = vi.mocked(api.chat).mock.calls[0][2];
  fireEvent.click(screen.getByRole("button", { name: "Stop" }));
  expect(signal?.aborted).toBe(true);
  expect(screen.getByLabelText("Question")).toHaveValue("What do you do?");
  await act(async () => finish({ answer: "Outdated answer", sources: [] }));
  expect(screen.queryByText("Outdated answer")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Send question" })).toBeEnabled();
});

it("cancels the previous company's chat when navigating away", () => {
  vi.mocked(api.chat).mockReturnValue(new Promise(() => {}));
  const { unmount } = render(<ChatPanel company={company} />);
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "Question" } });
  fireEvent.click(screen.getByRole("button", { name: "Send question" }));
  const signal = vi.mocked(api.chat).mock.calls[0][2];
  unmount();
  expect(signal?.aborted).toBe(true);
});

it("offers a retry without losing a failed question", async () => {
  vi.mocked(api.chat).mockRejectedValueOnce(new Error("Service unavailable")).mockResolvedValueOnce({ answer: "We build software.", sources: [] });
  render(<ChatPanel company={company} />);
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "What do you do?" } });
  fireEvent.click(screen.getByRole("button", { name: "Send question" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Service unavailable");
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("We build software.")).toBeInTheDocument();
});
