import { request } from "./client";
export async function login(email: string, password: string) {
  const result = await request<{ access_token: string }>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
  await chrome.storage.local.set({ fieldnote_token: result.access_token }); return result;
}
export async function logout() {
  const token = await chrome.storage.local.get("fieldnote_token");
  await chrome.storage.local.remove("fieldnote_token");
  try {
    if (token.fieldnote_token) await request<{ message: string }>("/auth/logout", { method: "POST", headers: { Authorization: "Bearer " + token.fieldnote_token } });
  } catch {
    // Best-effort revocation; always clear local state.
  }
}
