import { startTransition, useEffect, useState } from "react";
import type { CSSProperties } from "react";
import {
  createNote,
  deleteNote,
  getHealth,
  getNote,
  listNotes,
  moveNote,
  runKnot,
  saveNote,
} from "./api";
import { HybridMarkdownEditor } from "./hybrid-editor";
import type { KnotStatus, NoteDocument, NoteSummary } from "./types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  FileText,
  FolderOpen,
  FolderClosed,
  Plus,
  ChevronLeft,
  ChevronRight,
  Search,
  MoreHorizontal,
  Trash2,
  Pencil,
  Save,
  Sparkles,
} from "lucide-react";

type SortMode = "recent" | "title" | "path";

type FolderRecord = {
  path: string;
  name: string;
  depth: number;
  noteCount: number;
};

const EMPTY_NOTE: NoteDocument = {
  path: "Untitled.md",
  title: "Untitled",
  content: "# Untitled\n\nStart writing here.",
};

const STORAGE_KEYS = {
  sidebarCollapsed: "knot.sidebarCollapsed",
  sortMode: "knot.sortMode",
  expandedFolders: "knot.expandedFolders",
  virtualFolders: "knot.virtualFolders",
} as const;

function stemFromPath(path: string): string {
  return path.split("/").pop()?.replace(/\.md$/, "") ?? path;
}

function normalizePath(path: string): string {
  const trimmed = path.trim().replace(/^\/+|\/+$/g, "");
  if (!trimmed) {
    return "Untitled.md";
  }
  return trimmed.endsWith(".md") ? trimmed : `${trimmed}.md`;
}

function normalizeFolderPath(path: string): string {
  return path
    .trim()
    .replace(/^\/+|\/+$/g, "")
    .replace(/\/{2,}/g, "/");
}

function folderFromPath(path: string): string {
  const normalized = normalizePath(path);
  const parts = normalized.split("/");
  parts.pop();
  return parts.join("/");
}

function summarizeTitle(note: NoteSummary | NoteDocument): string {
  return note.title?.trim() || stemFromPath(note.path) || "Untitled";
}

function formatTimestamp(value?: string | number): string {
  if (value === undefined || value === null) {
    return "";
  }

  const date = typeof value === "number" ? new Date(value * 1000) : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }

  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function wordCount(content: string): number {
  return content.trim() ? content.trim().split(/\s+/).length : 0;
}

function newNoteForFolder(folderPath: string): NoteDocument {
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const prefix = normalizeFolderPath(folderPath);
  const path = prefix ? `${prefix}/Untitled-${stamp}.md` : `Untitled-${stamp}.md`;
  return {
    path,
    title: "Untitled",
    content: "# Untitled\n\nStart writing here.",
  };
}

function sortNotes(notes: NoteSummary[], sortMode: SortMode): NoteSummary[] {
  const sorted = [...notes];
  sorted.sort((left, right) => {
    if (sortMode === "recent") {
      const leftTime = Number(left.updatedAt ?? 0);
      const rightTime = Number(right.updatedAt ?? 0);
      if (rightTime !== leftTime) {
        return rightTime - leftTime;
      }
    }

    const leftKey =
      sortMode === "path"
        ? left.path.toLowerCase()
        : summarizeTitle(left).toLowerCase();
    const rightKey =
      sortMode === "path"
        ? right.path.toLowerCase()
        : summarizeTitle(right).toLowerCase();

    return leftKey.localeCompare(rightKey);
  });

  return sorted;
}

function parentFolders(path: string): string[] {
  const normalized = normalizeFolderPath(path);
  if (!normalized) {
    return [];
  }

  const parts = normalized.split("/");
  const folders: string[] = [];
  for (let index = 0; index < parts.length; index += 1) {
    folders.push(parts.slice(0, index + 1).join("/"));
  }
  return folders;
}

function buildFolderRecords(notes: NoteSummary[], virtualFolders: string[]): FolderRecord[] {
  const folderPaths = new Set<string>();

  for (const note of notes) {
    for (const folder of parentFolders(folderFromPath(note.path))) {
      folderPaths.add(folder);
    }
  }

  for (const folder of virtualFolders) {
    for (const parent of parentFolders(folder)) {
      folderPaths.add(parent);
    }
  }

  return [...folderPaths]
    .sort((left, right) => left.localeCompare(right))
    .map((path) => ({
      path,
      name: path.split("/").pop() ?? path,
      depth: path.split("/").length - 1,
      noteCount: notes.filter((note) => {
        const folder = folderFromPath(note.path);
        return folder === path || folder.startsWith(`${path}/`);
      }).length,
    }));
}

function directNotes(notes: NoteSummary[], folderPath: string, sortMode: SortMode): NoteSummary[] {
  return sortNotes(
    notes.filter((note) => folderFromPath(note.path) === folderPath),
    sortMode,
  );
}

function loadStoredValue<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) {
      return fallback;
    }
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function App() {
  const [notes, setNotes] = useState<NoteSummary[]>([]);
  const [selectedPath, setSelectedPath] = useState("");
  const [selectedFolder, setSelectedFolder] = useState("");
  const [draft, setDraft] = useState<NoteDocument>(EMPTY_NOTE);
  const [originalContent, setOriginalContent] = useState(EMPTY_NOTE.content);
  const [health, setHealth] = useState<KnotStatus>({ healthy: false, message: "Checking..." });
  const [loadingNotes, setLoadingNotes] = useState(false);
  const [loadingNote, setLoadingNote] = useState(false);
  const [saving, setSaving] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() =>
    loadStoredValue<boolean>(STORAGE_KEYS.sidebarCollapsed, false),
  );
  const [sortMode, setSortMode] = useState<SortMode>(() => loadStoredValue<SortMode>(STORAGE_KEYS.sortMode, "recent"));
  const [expandedFolders, setExpandedFolders] = useState<string[]>(() =>
    loadStoredValue<string[]>(STORAGE_KEYS.expandedFolders, []),
  );
  const [virtualFolders, setVirtualFolders] = useState<string[]>(() =>
    loadStoredValue<string[]>(STORAGE_KEYS.virtualFolders, []),
  );
  const [search, setSearch] = useState("");

  const isDirty = draft.content !== originalContent || normalizePath(draft.path) !== selectedPath;
  const orderedNotes = sortNotes(notes, sortMode);
  const folderRecords = buildFolderRecords(notes, virtualFolders);
  const filteredNotes = orderedNotes.filter((note) => {
    const query = search.trim().toLowerCase();
    if (!query) {
      return true;
    }

    return [summarizeTitle(note), note.path, note.preview ?? ""].some((value) =>
      value.toLowerCase().includes(query),
    );
  });

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEYS.sidebarCollapsed, JSON.stringify(sidebarCollapsed));
  }, [sidebarCollapsed]);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEYS.sortMode, JSON.stringify(sortMode));
  }, [sortMode]);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEYS.expandedFolders, JSON.stringify(expandedFolders));
  }, [expandedFolders]);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEYS.virtualFolders, JSON.stringify(virtualFolders));
  }, [virtualFolders]);

  async function refreshHealth() {
    setHealth(await getHealth());
  }

  async function refreshNotes(): Promise<NoteSummary[]> {
    setLoadingNotes(true);
    try {
      const items = await listNotes();
      setNotes(items);
      return items;
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Failed to load notes.");
      return [];
    } finally {
      setLoadingNotes(false);
    }
  }

  async function openNote(path: string, options?: { skipDirtyCheck?: boolean }) {
    if (!options?.skipDirtyCheck && isDirty && !window.confirm("Discard unsaved changes?")) {
      return;
    }

    setLoadingNote(true);
    try {
      const note = await getNote(path);
      setSelectedPath(note.path);
      setSelectedFolder(folderFromPath(note.path));
      setDraft(note);
      setOriginalContent(note.content);
      setStatusMessage("");
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Failed to open note.");
    } finally {
      setLoadingNote(false);
    }
  }

  function ensureFolderExpanded(path: string) {
    const next = new Set(expandedFolders);
    for (const folder of parentFolders(path)) {
      next.add(folder);
    }
    setExpandedFolders([...next]);
  }

  function updateDraftPath(nextPath: string) {
    const normalized = normalizePath(nextPath);
    setDraft((current) => ({
      ...current,
      path: normalized,
      title: summarizeTitle({ ...current, path: normalized }),
    }));
    setSelectedFolder(folderFromPath(normalized));
    ensureFolderExpanded(folderFromPath(normalized));
  }

  async function beginFreshNote(folderPath = selectedFolder) {
    if (isDirty && !window.confirm("Discard unsaved changes?")) {
      return;
    }

    const next = newNoteForFolder(folderPath);
    setSelectedPath("");
    setSelectedFolder(folderFromPath(next.path));
    setDraft(next);
    setOriginalContent(next.content);
    ensureFolderExpanded(folderFromPath(next.path));
    setStatusMessage("New note created");
  }

  async function persistPathIfNeeded(targetPath: string): Promise<string> {
    const normalized = normalizePath(targetPath);

    if (!selectedPath || selectedPath === normalized) {
      return normalized;
    }

    const moved = await moveNote(selectedPath, normalized);
    setSelectedPath(moved.path);
    setDraft((current) => ({
      ...current,
      path: moved.path,
      title: summarizeTitle(moved),
    }));
    setSelectedFolder(folderFromPath(moved.path));
    ensureFolderExpanded(folderFromPath(moved.path));
    return moved.path;
  }

  async function handleSave() {
    setSaving(true);
    try {
      const hadSavedPath = Boolean(selectedPath);
      const normalizedPath = normalizePath(draft.path);
      const persistedPath = hadSavedPath ? await persistPathIfNeeded(normalizedPath) : normalizedPath;
      const payload = {
        path: persistedPath,
        title: summarizeTitle({ ...draft, path: persistedPath }),
        content: draft.content,
      };
      const saved = hadSavedPath ? await saveNote(payload) : await createNote(payload);
      setDraft(saved);
      setOriginalContent(saved.content);
      setSelectedPath(saved.path);
      setSelectedFolder(folderFromPath(saved.path));
      ensureFolderExpanded(folderFromPath(saved.path));
      setStatusMessage("Saved");
      await refreshNotes();
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Failed to save.");
    } finally {
      setSaving(false);
    }
  }

  async function handleProcess() {
    setProcessing(true);
    try {
      const normalizedPath = normalizePath(draft.path);
      const persistedPath = await persistPathIfNeeded(normalizedPath);
      const payload = {
        path: persistedPath,
        title: summarizeTitle({ ...draft, path: persistedPath }),
        content: draft.content,
      };
      const response = await runKnot(payload);
      const nextPath = normalizePath(response.path ?? payload.path);
      const nextContent = response.content ?? draft.content;
      setDraft({
        path: nextPath,
        title: response.title ?? summarizeTitle({ ...draft, path: nextPath }),
        content: nextContent,
        updatedAt: response.updatedAt,
      });
      setOriginalContent(nextContent);
      setSelectedPath(nextPath);
      setSelectedFolder(folderFromPath(nextPath));
      ensureFolderExpanded(folderFromPath(nextPath));
      setStatusMessage(response.status ?? "Processed");
      await refreshNotes();
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Failed to process.");
    } finally {
      setProcessing(false);
    }
  }

  async function handleDelete(path: string) {
    if (!window.confirm(`Delete "${stemFromPath(path)}"?`)) {
      return;
    }

    try {
      await deleteNote(path);
      const remaining = await refreshNotes();
      if (selectedPath === path) {
        if (remaining.length > 0) {
          await openNote(remaining[0].path, { skipDirtyCheck: true });
        } else {
          setSelectedPath("");
          setSelectedFolder("");
          setDraft(EMPTY_NOTE);
          setOriginalContent(EMPTY_NOTE.content);
        }
      }
      setStatusMessage("Deleted");
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Failed to delete.");
    }
  }

  async function handleRename(path: string) {
    if (path === selectedPath && isDirty) {
      const shouldSave = window.confirm("Save changes before renaming?");
      if (!shouldSave) {
        return;
      }
      await handleSave();
    }

    const nextPath = window.prompt("New path", path);
    if (!nextPath) {
      return;
    }

    try {
      const moved = await moveNote(path, normalizePath(nextPath));
      if (selectedPath === path) {
        setSelectedPath(moved.path);
        setSelectedFolder(folderFromPath(moved.path));
        setDraft(moved);
        setOriginalContent(moved.content);
      }
      ensureFolderExpanded(folderFromPath(moved.path));
      setStatusMessage("Renamed");
      await refreshNotes();
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Failed to rename.");
    }
  }

  function handleCreateFolder() {
    const nextFolder = window.prompt("Folder path", selectedFolder || "notes");
    if (!nextFolder) {
      return;
    }

    const normalized = normalizeFolderPath(nextFolder);
    if (!normalized) {
      return;
    }

    setVirtualFolders((current) => [...new Set([...current, normalized])]);
    setSelectedFolder(normalized);
    ensureFolderExpanded(normalized);
  }

  useEffect(() => {
    void (async () => {
      await refreshHealth();
      const items = await refreshNotes();
      if (items.length > 0) {
        await openNote(items[0].path, { skipDirtyCheck: true });
      }
    })();
  }, []);

  const renderNoteTree = () => {
    const rootNotes = directNotes(filteredNotes, "", sortMode);

    return (
      <div className="note-tree">
        {rootNotes.map((note) => (
          <button
            key={note.path}
            type="button"
            className={`note-tree-item ${selectedPath === note.path ? "active" : ""}`}
            onClick={() => void openNote(note.path)}
          >
            <FileText className="note-tree-item-icon" />
            <span className="note-tree-item-title">{summarizeTitle(note)}</span>
          </button>
        ))}

        {folderRecords.map((folder) => {
          const isExpanded = expandedFolders.includes(folder.path);
          const isVisible = folder.depth === 0 || expandedFolders.includes(folder.path.split("/").slice(0, -1).join("/"));
          
          if (!isVisible) return null;

          const folderNotes = directNotes(filteredNotes, folder.path, sortMode);

          return (
            <div key={folder.path} className="note-tree-folder" style={{ paddingLeft: `${folder.depth * 12}px` } as CSSProperties}>
              <button
                type="button"
                className={`note-tree-folder-button ${selectedFolder === folder.path ? "active" : ""}`}
                onClick={() => {
                  setSelectedFolder(folder.path);
                  setExpandedFolders((current) =>
                    current.includes(folder.path)
                      ? current.filter((entry) => entry !== folder.path)
                      : [...current, folder.path],
                  );
                }}
              >
                {isExpanded ? (
                  <FolderOpen className="note-tree-item-icon" />
                ) : (
                  <FolderClosed className="note-tree-item-icon" />
                )}
                <span className="note-tree-item-title">{folder.name}</span>
                <span style={{ fontSize: "11px", color: "hsl(var(--muted-foreground))" }}>{folder.noteCount}</span>
              </button>

              {isExpanded && (
                <div className="note-tree-folder-children">
                  {folderNotes.map((note) => (
                    <button
                      key={note.path}
                      type="button"
                      className={`note-tree-item ${selectedPath === note.path ? "active" : ""}`}
                      onClick={() => void openNote(note.path)}
                    >
                      <FileText className="note-tree-item-icon" />
                      <span className="note-tree-item-title">{summarizeTitle(note)}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {filteredNotes.length === 0 && !loadingNotes && (
          <div className="empty-state">
            <p className="empty-state-description">
              {search ? "No notes match your search" : "No notes yet"}
            </p>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className={`app-shell dark ${sidebarCollapsed ? "collapsed" : ""}`}>
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          {!sidebarCollapsed && <span className="sidebar-brand">Knot</span>}
          <button
            type="button"
            className="sidebar-toggle"
            onClick={() => setSidebarCollapsed((c) => !c)}
            aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {sidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>
        </div>

        {!sidebarCollapsed && (
          <>
            <div className="sidebar-actions">
              <Button
                size="sm"
                className="flex-1"
                onClick={() => void beginFreshNote()}
              >
                <Plus size={14} />
                New Note
              </Button>
            </div>

            <div className="search-panel">
              <div className="search-input-wrapper">
                <Search className="search-input-icon" />
                <input
                  type="text"
                  className="search-input"
                  placeholder="Search notes..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
            </div>

            <ScrollArea className="sidebar-content">
              <div className="sidebar-section">
                <div className="sidebar-section-header">
                  <span>Notes</span>
                  <select
                    value={sortMode}
                    onChange={(e) => setSortMode(e.target.value as SortMode)}
                    style={{
                      background: "transparent",
                      border: "none",
                      color: "hsl(var(--muted-foreground))",
                      fontSize: "11px",
                      cursor: "pointer",
                    }}
                  >
                    <option value="recent">Recent</option>
                    <option value="title">Title</option>
                    <option value="path">Path</option>
                  </select>
                </div>
                {renderNoteTree()}
              </div>
            </ScrollArea>

            <div className="sidebar-footer">
              <span
                className={`status-dot ${health.healthy ? "success" : "error"}`}
              />
              <span>{health.healthy ? "Connected" : "Disconnected"}</span>
            </div>
          </>
        )}
      </aside>

      {/* Main content */}
      <main className="main-content">
        <div className="editor-container">
          <div className="editor-toolbar">
            <div className="editor-toolbar-left">
              <h1 className="editor-title">{summarizeTitle(draft)}</h1>
              <div className="editor-meta">
                <span>{selectedFolder || "Root"}</span>
                <span>{wordCount(draft.content)} words</span>
                {isDirty && <span>Unsaved</span>}
              </div>
            </div>

            <div className="editor-toolbar-right">
              <div className="path-input-wrapper">
                <label className="path-input-label">Path</label>
                <input
                  type="text"
                  className="path-input"
                  value={draft.path}
                  onChange={(e) => updateDraftPath(e.target.value)}
                  placeholder="notes/filename.md"
                />
              </div>

              <Button
                variant="outline"
                size="sm"
                onClick={() => void handleSave()}
                disabled={saving || loadingNote}
              >
                <Save size={14} />
                {saving ? "Saving..." : "Save"}
              </Button>

              <Button
                size="sm"
                onClick={() => void handleProcess()}
                disabled={processing || loadingNote}
              >
                <Sparkles size={14} />
                {processing ? "Processing..." : "Knot"}
              </Button>

              {selectedPath && (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void handleRename(selectedPath)}
                  >
                    <Pencil size={14} />
                    Rename
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void handleDelete(selectedPath)}
                  >
                    <Trash2 size={14} />
                    Delete
                  </Button>
                </>
              )}
            </div>
          </div>

          <div className="editor-body">
            <div className="editor-wrapper">
              <HybridMarkdownEditor
                value={draft.content}
                onChange={(nextValue) => {
                  setDraft((current) => ({ ...current, content: nextValue }));
                }}
              />
            </div>
          </div>
        </div>

        <div className="status-bar">
          <div className="status-bar-left">
            <span className="status-indicator">
              <span className={`status-dot ${health.healthy ? "success" : "error"}`} />
              {health.healthy ? "Ready" : "Offline"}
            </span>
            {statusMessage && <span>{statusMessage}</span>}
          </div>
          <div className="status-bar-right">
            <span>{loadingNote ? "Loading..." : isDirty ? "Edited" : "Saved"}</span>
            <span>{selectedPath || "New note"}</span>
          </div>
        </div>
      </main>
    </div>
  );
}
