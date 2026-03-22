import { useEffect, useRef, useState } from "react";
import {
    createNote,
    deleteNote,
    getHealth,
    getNote,
    getSettings,
    listNotes,
    moveNote,
    runKnot,
    saveNote,
} from "./api";
import { HybridMarkdownEditor } from "./hybrid-editor";
import type { KnotDetailMode, KnotStatus, NoteDocument, NoteSummary, WorkspaceSettings } from "./types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import {
    ChevronLeft,
    ChevronRight,
    FileText,
    FolderClosed,
    FolderOpen,
    FolderPlus,
    Plus,
    Save,
    Search,
    Sparkles,
    Trash2,
    X,
} from "lucide-react";

type SortMode = "recent" | "title" | "path";

type FolderRecord = {
    path: string;
    name: string;
    depth: number;
    noteCount: number;
};

type KnotFormState = {
    outputFolder: string;
    noteName: string;
    title: string;
    detailMode: KnotDetailMode;
};

const TREE_INDENTS = [
    "pl-[0px]",
    "pl-[12px]",
    "pl-[24px]",
    "pl-[36px]",
    "pl-[48px]",
    "pl-[60px]",
    "pl-[72px]",
    "pl-[84px]",
    "pl-[96px]",
] as const;

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

const SORT_OPTIONS = [
    { value: "recent", label: "Recent" },
    { value: "title", label: "Title" },
    { value: "path", label: "Path" },
] as const;

const DETAIL_MODE_OPTIONS = [
    { value: "minimal", label: "Minimal" },
    { value: "enriched", label: "Enriched" },
] as const;

function treeIndentClass(depth: number): string {
    return TREE_INDENTS[Math.min(depth, TREE_INDENTS.length - 1)];
}

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

function normalizeDetailMode(value?: string): KnotDetailMode {
    return value === "enriched" ? "enriched" : "minimal";
}

function defaultKnotFolder(path: string): string {
    return `knot-${stemFromPath(normalizePath(path)) || "Untitled"}`;
}

function defaultKnotForm(note: NoteDocument, detailMode: KnotDetailMode): KnotFormState {
    const normalizedPath = normalizePath(note.path);
    return {
        outputFolder: defaultKnotFolder(normalizedPath),
        noteName: stemFromPath(normalizedPath) || "Untitled",
        title: summarizeTitle({ ...note, path: normalizedPath }),
        detailMode,
    };
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

        const leftKey = sortMode === "path" ? left.path.toLowerCase() : summarizeTitle(left).toLowerCase();
        const rightKey = sortMode === "path" ? right.path.toLowerCase() : summarizeTitle(right).toLowerCase();
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
    const [workspaceSettings, setWorkspaceSettings] = useState<WorkspaceSettings | null>(null);
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
    const [knotModalOpen, setKnotModalOpen] = useState(false);
    const [knotForm, setKnotForm] = useState<KnotFormState>(() => defaultKnotForm(EMPTY_NOTE, "minimal"));
    const [isRenamingTitle, setIsRenamingTitle] = useState(false);
    const [pendingTitle, setPendingTitle] = useState("");
    const titleInputRef = useRef<HTMLInputElement | null>(null);

    const query = search.trim().toLowerCase();
    const isDirty = draft.content !== originalContent || normalizePath(draft.path) !== selectedPath;
    const orderedNotes = sortNotes(notes, sortMode);
    const folderRecords = buildFolderRecords(notes, virtualFolders);
    const filteredNotes = orderedNotes.filter((note) => {
        if (!query) {
            return true;
        }

        return [summarizeTitle(note), note.path, note.preview ?? ""].some((value) =>
            value.toLowerCase().includes(query),
        );
    });
    const updatedLabel = formatTimestamp(draft.updatedAt);
    const connectionDotClass = health.healthy
        ? "bg-emerald-400 shadow-[0_0_0_4px_rgba(74,222,128,0.14)]"
        : "bg-rose-400 shadow-[0_0_0_4px_rgba(251,113,133,0.14)]";

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

    useEffect(() => {
        if (!isRenamingTitle) {
            return;
        }

        titleInputRef.current?.focus();
        titleInputRef.current?.select();
    }, [isRenamingTitle]);

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

    function beginTitleRename() {
        setPendingTitle(stemFromPath(draft.path));
        setIsRenamingTitle(true);
    }

    function commitTitleRename() {
        const trimmed = pendingTitle.trim();
        setIsRenamingTitle(false);

        if (!trimmed) {
            setPendingTitle(stemFromPath(draft.path));
            return;
        }

        const currentFolder = folderFromPath(draft.path);
        const nextPath = currentFolder ? `${currentFolder}/${trimmed}.md` : `${trimmed}.md`;
        updateDraftPath(nextPath);
        setPendingTitle(trimmed);
    }

    function cancelTitleRename() {
        setPendingTitle(stemFromPath(draft.path));
        setIsRenamingTitle(false);
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
            await persistDraft();
            setStatusMessage("Saved");
            await refreshNotes();
        } catch (error) {
            setStatusMessage(error instanceof Error ? error.message : "Failed to save.");
        } finally {
            setSaving(false);
        }
    }

    async function persistDraft(): Promise<NoteDocument> {
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
        return saved;
    }

    function openKnotModal() {
        setKnotForm(defaultKnotForm(draft, normalizeDetailMode(workspaceSettings?.detailMode)));
        setKnotModalOpen(true);
    }

    async function handleConfirmKnot() {
        setProcessing(true);
        try {
            let sourceDocument = draft;
            const normalizedPath = normalizePath(draft.path);
            if (!selectedPath || isDirty || normalizedPath !== selectedPath) {
                sourceDocument = await persistDraft();
            }

            const payload = {
                path: normalizePath(sourceDocument.path),
                title: knotForm.title.trim() || summarizeTitle(sourceDocument),
                content: sourceDocument.content,
                outputFolder: normalizeFolderPath(knotForm.outputFolder || defaultKnotFolder(sourceDocument.path)),
                noteName: knotForm.noteName.trim() || stemFromPath(sourceDocument.path) || "Untitled",
                detailMode: knotForm.detailMode,
            };
            const response = await runKnot(payload);
            const nextPath = normalizePath(response.notePath ?? response.path ?? payload.path);
            const nextContent = response.content ?? sourceDocument.content;
            setDraft({
                path: nextPath,
                title: response.title ?? summarizeTitle({ ...sourceDocument, path: nextPath }),
                content: nextContent,
                updatedAt: response.updatedAt,
            });
            setOriginalContent(nextContent);
            setSelectedPath(nextPath);
            setSelectedFolder(folderFromPath(nextPath));
            ensureFolderExpanded(folderFromPath(nextPath));
            setStatusMessage(response.status ?? "Processed");
            setKnotModalOpen(false);
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
            try {
                setWorkspaceSettings(await getSettings());
            } catch {
                setWorkspaceSettings(null);
            }
            const items = await refreshNotes();
            if (items.length > 0) {
                await openNote(items[0].path, { skipDirtyCheck: true });
            }
        })();
    }, []);

    function treeButtonClass(active: boolean) {
        return cn(
            "group flex w-full items-center gap-3 rounded-xl border border-transparent px-3 py-2.5 text-left text-sm text-stone-300 transition-all duration-150 hover:border-stone-800 hover:bg-stone-900/70 hover:text-stone-100",
            active && "border-amber-300/15 bg-stone-900 text-stone-50 shadow-[0_0_0_1px_rgba(245,158,11,0.12)]",
        );
    }

    const renderNoteTree = () => {
        const rootNotes = directNotes(filteredNotes, "", sortMode);

        return (
            <div className="space-y-1">
                {rootNotes.map((note) => (
                    <button
                        key={note.path}
                        type="button"
                        className={treeButtonClass(selectedPath === note.path)}
                        onClick={() => void openNote(note.path)}
                    >
                        <FileText className="size-4 shrink-0 text-stone-500 transition-colors group-hover:text-amber-300" />
                        <span className="min-w-0 flex-1 truncate">{summarizeTitle(note)}</span>
                    </button>
                ))}

                {folderRecords.map((folder) => {
                    const parentPath = folder.path.split("/").slice(0, -1).join("/");
                    const isExpanded = expandedFolders.includes(folder.path);
                    const showAllForSearch = Boolean(query);
                    const isVisible = showAllForSearch || folder.depth === 0 || expandedFolders.includes(parentPath);

                    if (!isVisible) {
                        return null;
                    }

                    const folderNotes = directNotes(filteredNotes, folder.path, sortMode);
                    const visibleCount = showAllForSearch ? folderNotes.length : folder.noteCount;

                    return (
                        <div key={folder.path} className={cn("space-y-1", treeIndentClass(folder.depth))}>
                            <button
                                type="button"
                                className={treeButtonClass(selectedFolder === folder.path)}
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
                                    <FolderOpen className="size-4 shrink-0 text-amber-300" />
                                ) : (
                                    <FolderClosed className="size-4 shrink-0 text-stone-500 transition-colors group-hover:text-amber-300" />
                                )}
                                <span className="min-w-0 flex-1 truncate">{folder.name}</span>
                                <span className="rounded-full border border-stone-700/80 bg-stone-900/90 px-2 py-0.5 text-[11px] text-stone-400">
                                    {visibleCount}
                                </span>
                            </button>

                            {(isExpanded || showAllForSearch) && (
                                <div className="space-y-1 pl-3">
                                    {folderNotes.map((note) => (
                                        <button
                                            key={note.path}
                                            type="button"
                                            className={treeButtonClass(selectedPath === note.path)}
                                            onClick={() => void openNote(note.path)}
                                        >
                                            <FileText className="size-4 shrink-0 text-stone-500 transition-colors group-hover:text-amber-300" />
                                            <span className="min-w-0 flex-1 truncate">{summarizeTitle(note)}</span>
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    );
                })}

                {filteredNotes.length === 0 && !loadingNotes && (
                    <div className="rounded-2xl border border-dashed border-stone-800 bg-stone-950/50 px-4 py-8 text-center">
                        <p className="text-sm text-stone-500">{query ? "No notes match your search" : "No notes yet"}</p>
                    </div>
                )}
            </div>
        );
    };

    return (
        <div className="flex min-h-screen flex-col md:flex-row">
            <aside
                className={cn(
                    "flex w-full shrink-0 flex-col border-b border-stone-800/80 bg-stone-950/75 backdrop-blur-xl md:min-h-screen md:border-b-0 md:border-r",
                    sidebarCollapsed ? "md:w-[4.75rem]" : "md:w-80",
                )}
            >
                <div className="flex items-center justify-between border-b border-stone-800/80 px-4 py-4">
                    {!sidebarCollapsed && (
                        <div>
                            <span className="block text-sm font-semibold tracking-[-0.02em] text-stone-50">Knot</span>
                            <span className="block text-xs uppercase tracking-[0.18em] text-stone-500">Notes Workspace</span>
                        </div>
                    )}
                    <button
                        type="button"
                        className="inline-flex size-9 items-center justify-center rounded-xl border border-stone-800 bg-stone-950/80 text-stone-400 transition-colors hover:bg-stone-900 hover:text-stone-100"
                        onClick={() => setSidebarCollapsed((current) => !current)}
                        aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
                    >
                        {sidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
                    </button>
                </div>

                {!sidebarCollapsed && (
                    <>
                        <div className="space-y-2 border-b border-stone-800/80 px-4 py-4">
                            <Button size="sm" className="w-full justify-center" onClick={() => void beginFreshNote()}>
                                <Plus size={14} />
                                New Note
                            </Button>
                            <Button variant="outline" size="sm" className="w-full justify-center" onClick={handleCreateFolder}>
                                <FolderPlus size={14} />
                                New Folder
                            </Button>
                        </div>

                        <div className="border-b border-stone-800/80 px-4 py-4">
                            <div className="relative">
                                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-stone-500" />
                                <Input
                                    type="text"
                                    className="pl-9"
                                    placeholder="Search notes..."
                                    value={search}
                                    onChange={(event) => setSearch(event.target.value)}
                                />
                            </div>
                        </div>

                        <ScrollArea className="min-h-0 flex-1 px-3 py-3">
                            <div className="space-y-3">
                                <div className="flex items-center justify-between px-2 pt-1 text-[11px] font-medium uppercase tracking-[0.18em] text-stone-500">
                                    <span>Notes</span>
                                    <Select
                                        value={sortMode}
                                        onValueChange={(nextValue) => setSortMode(nextValue as SortMode)}
                                        options={[...SORT_OPTIONS]}
                                        uiSize="sm"
                                        className="w-auto min-w-[6.25rem] border-stone-800/90 bg-stone-950/85 text-stone-300"
                                    />
                                </div>
                                {renderNoteTree()}
                            </div>
                        </ScrollArea>

                        <div className="flex items-center gap-3 border-t border-stone-800/80 px-4 py-3 text-xs text-stone-500">
                            <span className={cn("size-2 rounded-full", connectionDotClass)} />
                            <span>{health.healthy ? "Connected" : "Disconnected"}</span>
                        </div>
                    </>
                )}
            </aside>

            <main className="flex min-h-0 flex-1 flex-col">
                <div className="flex min-h-0 flex-1 flex-col">
                    <div className="border-b border-stone-800/80 bg-stone-950/55 px-4 py-4 backdrop-blur-xl md:px-8">
                        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
                            <div className="space-y-2">
                                {isRenamingTitle ? (
                                    <Input
                                        ref={titleInputRef}
                                        value={pendingTitle}
                                        onChange={(event) => setPendingTitle(event.target.value)}
                                        onBlur={commitTitleRename}
                                        onKeyDown={(event) => {
                                            if (event.key === "Enter") {
                                                event.preventDefault();
                                                commitTitleRename();
                                            }

                                            if (event.key === "Escape") {
                                                event.preventDefault();
                                                cancelTitleRename();
                                            }
                                        }}
                                        className="h-auto border-stone-700/70 bg-transparent px-0 py-0 text-2xl font-semibold tracking-[-0.03em] text-stone-50 shadow-none placeholder:text-stone-500 focus:border-transparent focus:ring-0 md:text-3xl"
                                        aria-label="Rename note"
                                    />
                                ) : (
                                    <button
                                        type="button"
                                        className="inline-flex max-w-full items-center rounded-lg hover:cursor-text text-left text-2xl font-semibold tracking-[-0.03em] text-stone-50 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/60 focus-visible:ring-offset-2 focus-visible:ring-offset-stone-950 md:text-3xl"
                                        onClick={beginTitleRename}
                                    >
                                        <span className="truncate">{summarizeTitle(draft)}</span>
                                    </button>
                                )}
                                <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs uppercase tracking-[0.14em] text-stone-500">
                                    <span>{selectedFolder || "Root"}</span>
                                    <span>{wordCount(draft.content)} words</span>
                                    {updatedLabel && <span>{updatedLabel}</span>}
                                    {isDirty && <span className="text-amber-300">Unsaved</span>}
                                </div>
                            </div>

                            <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end lg:justify-end">
                                <Button variant="outline" size="sm" onClick={() => void handleSave()} disabled={saving || loadingNote}>
                                    <Save size={14} />
                                    {saving ? "Saving..." : "Save"}
                                </Button>

                                <Button size="sm" onClick={openKnotModal} disabled={processing || loadingNote}>
                                    <Sparkles size={14} />
                                    {processing ? "Processing..." : "Knot"}
                                </Button>

                                {selectedPath && (
                                    <>
                                        <Button variant="outline" size="sm" onClick={() => void handleDelete(selectedPath)}>
                                            <Trash2 size={14} />
                                            Delete
                                        </Button>
                                    </>
                                )}
                            </div>
                        </div>
                    </div>

                    <div className="flex-1 overflow-y-auto px-4 pb-24 pt-6 md:px-8 md:pt-10">
                        <div className="mx-auto w-full max-w-4xl">
                            <HybridMarkdownEditor
                                value={draft.content}
                                onChange={(nextValue) => {
                                    setDraft((current) => ({ ...current, content: nextValue }));
                                }}
                            />
                        </div>
                    </div>
                </div>

                <div className="flex flex-col gap-2 border-t border-stone-800/80 bg-stone-950/55 px-4 py-3 text-xs text-stone-500 backdrop-blur md:flex-row md:items-center md:justify-between md:px-8">
                    <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
                        <span className="inline-flex items-center gap-2">
                            <span className={cn("size-2 rounded-full", connectionDotClass)} />
                            {health.healthy ? "Ready" : "Offline"}
                        </span>
                        {statusMessage && <span>{statusMessage}</span>}
                    </div>
                    <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
                        <span>{loadingNote ? "Loading..." : isDirty ? "Edited" : "Saved"}</span>
                        <span className="truncate">{selectedPath || "New note"}</span>
                    </div>
                </div>
            </main>

            {knotModalOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-stone-950/80 px-4 backdrop-blur-sm">
                    <div className="w-full max-w-xl rounded-[28px] border border-stone-800/80 bg-stone-950 p-6 shadow-[0_30px_120px_rgba(0,0,0,0.55)]">
                        <div className="flex items-start justify-between gap-4">
                            <div className="space-y-2">
                                <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-stone-500">Knot Output</p>
                                <h2 className="text-2xl font-semibold tracking-[-0.03em] text-stone-50">Configure this knot run</h2>
                                <p className="text-sm leading-6 text-stone-400">
                                    The raw note stays intact. Knot writes formatted output into a dedicated folder in your vault.
                                </p>
                            </div>
                            <button
                                type="button"
                                className="inline-flex size-9 items-center justify-center rounded-xl border border-stone-800 bg-stone-950/80 text-stone-400 transition-colors hover:bg-stone-900 hover:text-stone-100"
                                onClick={() => setKnotModalOpen(false)}
                                aria-label="Close knot modal"
                            >
                                <X size={16} />
                            </button>
                        </div>

                        <div className="mt-6 grid gap-4 sm:grid-cols-2">
                            <div className="space-y-1.5 sm:col-span-2">
                                <label className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone-500">Output Folder</label>
                                <Input
                                    value={knotForm.outputFolder}
                                    onChange={(event) =>
                                        setKnotForm((current) => ({
                                            ...current,
                                            outputFolder: event.target.value,
                                        }))
                                    }
                                    placeholder={defaultKnotFolder(draft.path)}
                                />
                            </div>

                            <div className="space-y-1.5">
                                <label className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone-500">File Name</label>
                                <Input
                                    value={knotForm.noteName}
                                    onChange={(event) =>
                                        setKnotForm((current) => ({
                                            ...current,
                                            noteName: event.target.value,
                                        }))
                                    }
                                    placeholder={stemFromPath(draft.path)}
                                />
                            </div>

                            <div className="space-y-1.5">
                                <label className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone-500">Enrichment</label>
                                <Select
                                    value={knotForm.detailMode}
                                    onValueChange={(nextValue) =>
                                        setKnotForm((current) => ({
                                            ...current,
                                            detailMode: normalizeDetailMode(nextValue),
                                        }))
                                    }
                                    options={[...DETAIL_MODE_OPTIONS]}
                                />
                            </div>

                            <div className="space-y-1.5 sm:col-span-2">
                                <label className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone-500">Title</label>
                                <Input
                                    value={knotForm.title}
                                    onChange={(event) =>
                                        setKnotForm((current) => ({
                                            ...current,
                                            title: event.target.value,
                                        }))
                                    }
                                    placeholder={summarizeTitle(draft)}
                                />
                            </div>
                        </div>

                        <div className="mt-5 rounded-2xl border border-stone-800 bg-stone-900/60 px-4 py-3">
                            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone-500">Output Preview</p>
                            <p className="mt-2 text-sm text-stone-200">
                                {normalizeFolderPath(knotForm.outputFolder || defaultKnotFolder(draft.path))}/
                                {(knotForm.noteName.trim() || stemFromPath(draft.path) || "Untitled").replace(/\.md$/i, "")}.md
                            </p>
                        </div>

                        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
                            <Button variant="outline" onClick={() => setKnotModalOpen(false)} disabled={processing}>
                                Cancel
                            </Button>
                            <Button onClick={() => void handleConfirmKnot()} disabled={processing || loadingNote}>
                                <Sparkles size={14} />
                                {processing ? "Knitting..." : "Run Knot"}
                            </Button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
