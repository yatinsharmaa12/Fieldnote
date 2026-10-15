import { request } from "./client";
import type { ChatResponse } from "../types";
export const askCompany = (company_id: number, question: string, signal?: AbortSignal) => request<ChatResponse>("/chat", { method: "POST", body: JSON.stringify({ company_id, question }), signal });

export function uniqueSources(sources: ChatResponse["sources"]) {
  const seen = new Set<string>();
  return sources.filter(source => {
    if (seen.has(source.url)) return false;
    seen.add(source.url);
    return true;
  });
}
