import { useQuery } from "@tanstack/react-query";
import type { DocumentRecord } from "./types";

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, options);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      body?.error?.message || `Request failed (${response.status}).`,
    );
  }
  return response.status === 204
    ? (undefined as T)
    : (response.json() as Promise<T>);
}
export function useDocuments() {
  return useQuery({
    queryKey: ["documents"],
    queryFn: () => api<DocumentRecord[]>("/documents"),
    refetchInterval: (query) =>
      query.state.data?.some((r) =>
        ["queued", "processing"].includes(r.document.status),
      )
        ? 2000
        : false,
  });
}
export function upload(file: File, retry = false) {
  const body = new FormData();
  body.append("file", file);
  body.append("retry_failed", String(retry));
  return api<DocumentRecord>("/documents", { method: "POST", body });
}
