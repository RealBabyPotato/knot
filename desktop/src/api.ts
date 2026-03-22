import type {
  KnotProcessRequest,
  KnotStatus,
  NoteDocument,
  NoteSummary,
  ProcessResponse,
  WorkspaceSettings,
} from "./types";

const DEFAULT_API_URL = "http://127.0.0.1:7768";

function getApiBaseUrl(): string {
  return (import.meta.env.VITE_KNOT_API_URL ?? DEFAULT_API_URL).replace(/\/$/, "");
}

function titleFromPath(path: string): string {
  const stem = path.split("/").pop()?.replace(/\.md$/, "").trim();
  return stem && stem.length > 0 ? stem : "Untitled";
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }

  const text = await response.text();
  return text as T;
}

function normalizeSummary(value: any): NoteSummary {
  const path = String(value.path ?? value.note_path ?? value.filePath ?? "");
  return {
    path,
    title: String(value.title ?? value.note_title ?? value.name ?? titleFromPath(path)),
    preview: value.preview ?? value.excerpt ?? value.content_preview,
    updatedAt: value.updatedAt ?? value.updated_at ?? value.modified_at,
  };
}

function normalizeDocument(value: any, fallbackPath = ""): NoteDocument {
  if (typeof value === "string") {
    return {
      path: fallbackPath,
      title: fallbackPath ? fallbackPath.split("/").pop()?.replace(/\.md$/, "") ?? fallbackPath : "Untitled",
      content: value,
    };
  }

  const path = String(value.path ?? value.note_path ?? fallbackPath);
  return {
    path,
    title: String(value.title ?? value.note_title ?? titleFromPath(path)),
    content: String(value.content ?? value.markdown ?? value.body ?? ""),
    updatedAt: value.updatedAt ?? value.updated_at ?? value.modified_at,
  };
}

function normalizeStatus(value: any): KnotStatus {
  if (typeof value === "string") {
    return { healthy: true, message: value };
  }

  return {
    healthy: Boolean(value.healthy ?? value.ok ?? value.status === "ok"),
    message: String(value.message ?? value.detail ?? value.status ?? "OK"),
  };
}

function normalizeProcessResponse(value: any): ProcessResponse {
  return {
    mode: value.mode,
    path: value.path ?? value.note_path,
    notePath: value.note_path ?? value.path,
    title: value.title,
    content: value.content,
    updatedAt: value.updatedAt ?? value.updated_at ?? value.modified_at,
    status: value.status,
    relatedLinks: Array.isArray(value.related_links) ? value.related_links : [],
    outputFolder: value.output_folder ?? value.outputFolder,
  };
}

export async function getHealth(): Promise<KnotStatus> {
  try {
    const response = await requestJson<unknown>("/health");
    return normalizeStatus(response);
  } catch (error) {
    return {
      healthy: false,
      message: error instanceof Error ? error.message : "Backend unreachable",
    };
  }
}

export async function listNotes(): Promise<NoteSummary[]> {
  const response = await requestJson<any>("/notes");
  const notes = Array.isArray(response) ? response : response.notes ?? response.items ?? [];
  return notes.map(normalizeSummary).filter((note: NoteSummary) => note.path);
}

export async function getSettings(): Promise<WorkspaceSettings> {
  const response = await requestJson<any>("/settings");
  return {
    baseDir: String(response.base_dir ?? response.baseDir ?? ""),
    vaultDir: String(response.vault_dir ?? response.vaultDir ?? ""),
    inboxDir: String(response.inbox_dir ?? response.inboxDir ?? ""),
    provider: String(response.provider ?? "unknown"),
    detailMode: String(response.detail_mode ?? response.detailMode ?? "minimal"),
  };
}

export async function getNote(path: string): Promise<NoteDocument> {
  const response = await requestJson<any>(`/notes/content?path=${encodeURIComponent(path)}`);
  return normalizeDocument(response, path);
}

export async function saveNote(document: Pick<NoteDocument, "path" | "title" | "content">): Promise<NoteDocument> {
  const response = await requestJson<any>("/notes/content", {
    method: "PUT",
    body: JSON.stringify(document),
  });

  return normalizeDocument(response, document.path);
}

export async function createNote(document: Pick<NoteDocument, "path" | "title" | "content">): Promise<NoteDocument> {
  const response = await requestJson<any>("/notes", {
    method: "POST",
    body: JSON.stringify(document),
  });

  return normalizeDocument(response, document.path);
}

export async function deleteNote(path: string): Promise<{ deleted: boolean; path: string }> {
  return requestJson<{ deleted: boolean; path: string }>(`/notes/content?path=${encodeURIComponent(path)}`, {
    method: "DELETE",
  });
}

export async function moveNote(sourcePath: string, destinationPath: string): Promise<NoteDocument> {
  const response = await requestJson<any>("/notes/move", {
    method: "POST",
    body: JSON.stringify({
      source_path: sourcePath,
      destination_path: destinationPath,
    }),
  });

  return normalizeDocument(response, destinationPath);
}

export async function runKnot(request: KnotProcessRequest): Promise<ProcessResponse> {
  const response = await requestJson<any>("/knot/process", {
    method: "POST",
    body: JSON.stringify({
      path: request.path,
      title: request.title,
      content: request.content,
      output_path: request.outputPath,
      output_folder: request.outputFolder,
      note_name: request.noteName,
      detail_mode: request.detailMode,
    }),
  });

  return normalizeProcessResponse(response);
}
