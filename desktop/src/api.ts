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
  const normalized = path.replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
  const parts = normalized.split("/");
  const filename = parts[parts.length - 1]?.trim() ?? "";
  if (filename.toLowerCase() === "index.md" && parts.length > 1) {
    return parts[parts.length - 2] ?? "Untitled";
  }
  const stem = filename.replace(/\.md$/, "").trim();
  return stem && stem.length > 0 ? stem : "Untitled";
}

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function extractErrorMessage(raw: string, status: number): string {
  const text = raw.trim();
  if (!text) {
    return `Request failed with status ${status}`;
  }

  try {
    const value = JSON.parse(text);
    if (typeof value?.detail === "string" && value.detail.trim()) {
      return value.detail;
    }
    if (typeof value?.message === "string" && value.message.trim()) {
      return value.message;
    }
  } catch {
    // FastAPI often returns JSON, but plain text is still a valid error body.
  }

  return text;
}

type RenameAttempt = {
  path: string;
  method: "POST" | "PATCH";
};

type RenameStrategy = RenameAttempt | "crud";

const RENAME_ATTEMPTS: RenameAttempt[] = [
  { path: "/notes/move", method: "POST" },
  { path: "/notes/rename", method: "POST" },
  { path: "/notes/rename", method: "PATCH" },
  { path: "/notes/content/rename", method: "POST" },
  { path: "/notes/content/rename", method: "PATCH" },
];

let renameStrategyPromise: Promise<RenameStrategy | null> | null = null;

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
    throw new ApiError(extractErrorMessage(text, response.status), response.status);
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

function sameRenameAttempt(left: RenameAttempt, right: RenameAttempt): boolean {
  return left.path === right.path && left.method === right.method;
}

function isRenameAttempt(value: RenameStrategy | null): value is RenameAttempt {
  return Boolean(value && value !== "crud");
}

async function detectRenameStrategy(): Promise<RenameStrategy | null> {
  try {
    const openapi = await requestJson<any>("/openapi.json");
    const paths = openapi?.paths ?? {};

    for (const attempt of RENAME_ATTEMPTS) {
      const method = attempt.method.toLowerCase();
      if (paths?.[attempt.path]?.[method]) {
        return attempt;
      }
    }

    return "crud";
  } catch {
    return null;
  }
}

async function getRenameStrategy(): Promise<RenameStrategy | null> {
  if (!renameStrategyPromise) {
    renameStrategyPromise = detectRenameStrategy();
  }
  return renameStrategyPromise;
}

function resetRenameStrategy(): void {
  renameStrategyPromise = null;
}

function normalizeSummary(value: any): NoteSummary {
  const path = String(value.path ?? value.note_path ?? value.filePath ?? "");
  return {
    path,
    title: titleFromPath(path),
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
    title: titleFromPath(path),
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
  const path = String(value.path ?? value.note_path ?? "");
  return {
    mode: value.mode,
    path,
    notePath: path,
    title: titleFromPath(path),
    content: value.content,
    updatedAt: value.updatedAt ?? value.updated_at ?? value.modified_at,
    status: value.status,
    relatedLinks: Array.isArray(value.related_links) ? value.related_links : [],
    outputFolder: value.output_folder ?? value.outputFolder,
    rootNotePath: value.root_note_path ?? value.rootNotePath,
    artifacts: Array.isArray(value.artifacts) ? value.artifacts : [],
    treeSummary: value.tree_summary ?? value.treeSummary,
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
    outputMode: String(response.output_mode ?? response.outputMode ?? "single_note"),
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

async function requestRename(attempt: RenameAttempt, body: string, destinationPath: string): Promise<NoteDocument> {
  const response = await requestJson<any>(attempt.path, {
    method: attempt.method,
    body,
  });
  return normalizeDocument(response, destinationPath);
}

async function moveNoteViaCrud(sourcePath: string, destinationPath: string): Promise<NoteDocument> {
  const source = await getNote(sourcePath);
  const created = await createNote({
    path: destinationPath,
    title: titleFromPath(destinationPath),
    content: source.content,
  });

  try {
    await deleteNote(sourcePath);
  } catch (error) {
    try {
      await deleteNote(destinationPath);
    } catch {
      // Best-effort rollback if the source delete fails after the new note is created.
    }
    throw error;
  }

  return created;
}

export async function moveNote(sourcePath: string, destinationPath: string): Promise<NoteDocument> {
  const body = JSON.stringify({
    source_path: sourcePath,
    destination_path: destinationPath,
    path: sourcePath,
    new_path: destinationPath,
  });

  const preferredStrategy = await getRenameStrategy();
  if (preferredStrategy === "crud") {
    return moveNoteViaCrud(sourcePath, destinationPath);
  }

  const attempts = isRenameAttempt(preferredStrategy)
    ? [preferredStrategy, ...RENAME_ATTEMPTS.filter((attempt) => !sameRenameAttempt(attempt, preferredStrategy))]
    : RENAME_ATTEMPTS;

  let lastError: unknown;
  for (const attempt of attempts) {
    try {
      return await requestRename(attempt, body, destinationPath);
    } catch (error) {
      lastError = error;
      if (!(error instanceof ApiError) || ![404, 405].includes(error.status)) {
        throw error;
      }
    }
  }

  resetRenameStrategy();

  try {
    return await moveNoteViaCrud(sourcePath, destinationPath);
  } catch (fallbackError) {
    throw fallbackError instanceof Error
      ? fallbackError
      : lastError instanceof Error
        ? lastError
        : new Error("Rename endpoint not found.");
  }
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
      detail_mode: request.detailMode,
      output_mode: request.outputMode,
    }),
  });

  return normalizeProcessResponse(response);
}
