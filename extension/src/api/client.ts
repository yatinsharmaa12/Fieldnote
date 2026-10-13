export const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const REQUEST_TIMEOUT_MS = 35000;

export class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }

export async function request<T>(path: string, options: RequestInit = {}) {
  const token = await chrome.storage.local.get("fieldnote_token");
  const headers = new Headers(options.headers); headers.set("Content-Type", "application/json");
  if (token.fieldnote_token) headers.set("Authorization", `Bearer ${token.fieldnote_token}`);
  let response: Response;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try { response = await fetch(`${API_BASE}${path}`, { ...options, headers, signal: controller.signal }); }
  catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw new ApiError(408, "The server took too long to respond. Please try again.");
    throw new ApiError(503, "Unable to reach Fieldnote. Check that the backend is running.");
  } finally { window.clearTimeout(timeout); }
  if (!response.ok) {
    let message = "Something went wrong. Please try again.";
    try { message = (await response.json()).detail ?? message; } catch { /* non-JSON response */ }
    throw new ApiError(response.status, message);
  }
  return response.json() as Promise<T>;
}
