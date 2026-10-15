export const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const REQUEST_TIMEOUT_MS = 12000;
const CHAT_TIMEOUT_MS = 45000;

export class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }
export const isAbortError = (error: unknown) => error instanceof DOMException && error.name === "AbortError";

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = await chrome.storage.local.get("fieldnote_token");
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token.fieldnote_token && !headers.has("Authorization")) headers.set("Authorization", "Bearer " + token.fieldnote_token);
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (options.signal?.aborted) throw new DOMException("Request cancelled", "AbortError");
  options.signal?.addEventListener("abort", abort, { once: true });
  const timeout = window.setTimeout(abort, path === "/chat" ? CHAT_TIMEOUT_MS : REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(API_BASE + path, { ...options, headers, signal: controller.signal });
    if (!response.ok) {
      let message = "Something went wrong. Please try again.";
      try {
        const detail: unknown = (await response.json()).detail;
        if (typeof detail === "string") message = detail;
        else if (Array.isArray(detail)) message = detail.map(item => typeof item?.msg === "string" ? item.msg : "Invalid input").join(". ");
      } catch (error) { if (isAbortError(error)) throw error; }
      if (response.status === 401 && token.fieldnote_token) {
        const current = await chrome.storage.local.get("fieldnote_token");
        if (current.fieldnote_token === token.fieldnote_token && headers.get("Authorization") === "Bearer " + current.fieldnote_token) {
          await chrome.storage.local.remove("fieldnote_token");
          window.dispatchEvent(new Event("fieldnote:session-expired"));
        }
      }
      throw new ApiError(response.status, message);
    }
    return await response.json() as T;
  } catch (error) {
    if (options.signal?.aborted) throw new DOMException("Request cancelled", "AbortError");
    if (error instanceof ApiError) throw error;
    if (isAbortError(error)) throw new ApiError(408, "This is taking longer than expected. Please try again.");
    throw new ApiError(503, "Unable to reach Fieldnote. Check that the backend is running.");
  } finally {
    window.clearTimeout(timeout);
    options.signal?.removeEventListener("abort", abort);
  }
}
