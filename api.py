from __future__ import annotations

from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from core import KnotProcessor
from models import KnotSettings


def resolve_base_dir(base_dir: Path) -> Path:
    candidate = base_dir.resolve()
    markers = (".env", "Inbox", "pyproject.toml")

    for current in (candidate, *candidate.parents):
        if any((current / marker).exists() for marker in markers):
            return current

    return candidate


class NotePayload(BaseModel):
    path: str | None = Field(default=None, min_length=1)
    output_path: str | None = Field(default=None, min_length=1)
    output_folder: str | None = Field(default=None, min_length=1)
    detail_mode: str | None = None
    output_mode: str | None = None
    title: str | None = None
    content: str = ""

    def resolved_path(self) -> str:
        candidate = self.path or self.output_path
        if not candidate:
            raise HTTPException(status_code=400, detail="A note path is required.")
        return candidate

    def source_reference(self) -> str:
        return self.path or self.output_path or "Untitled.md"


class MovePayload(BaseModel):
    source_path: str | None = Field(default=None, min_length=1)
    destination_path: str | None = Field(default=None, min_length=1)
    path: str | None = Field(default=None, min_length=1)
    new_path: str | None = Field(default=None, min_length=1)
    target_path: str | None = Field(default=None, min_length=1)
    new_name: str | None = Field(default=None, min_length=1)
    title: str | None = Field(default=None, min_length=1)

    def resolved_source_path(self) -> str:
        candidate = self.source_path or self.path
        if not candidate:
            raise HTTPException(status_code=400, detail="A source note path is required.")
        return candidate

    def resolved_destination_path(self) -> str:
        candidate = self.destination_path or self.new_path or self.target_path
        if candidate:
            return candidate

        name = self.new_name or self.title
        if not name:
            raise HTTPException(status_code=400, detail="A destination note path is required.")

        source = Path(self.resolved_source_path().strip().replace("\\", "/"))
        if source.suffix.lower() == ".md":
            source = source.with_suffix("")
        return str(source.parent / f"{note_stem(name)}.md")


class ProcessResponse(BaseModel):
    mode: str
    path: str
    title: str
    content: str
    related_links: list[str] = Field(default_factory=list)
    status: str
    output_folder: str
    root_note_path: str | None = None
    artifacts: list[str] = Field(default_factory=list)
    tree_summary: dict[str, int] | None = None


def note_stem(value: str | None, fallback: str = "Untitled") -> str:
    if not value:
        return fallback

    normalized = value.strip().replace("\\", "/").rstrip("/")
    candidate = Path(normalized).name
    if candidate.lower().endswith(".md"):
        candidate = candidate[:-3]
    return candidate or fallback


def build_default_output_path(payload: NotePayload) -> str:
    source_stem = note_stem(payload.source_reference())
    folder_name = payload.output_folder.strip() if payload.output_folder else f"knot-{source_stem}"
    title = note_stem(payload.title, fallback=source_stem)
    return str(Path(folder_name) / f"{title}.md")


def build_default_output_folder(payload: NotePayload) -> str:
    source_stem = note_stem(payload.source_reference())
    folder_name = payload.output_folder.strip() if payload.output_folder else f"knot-{source_stem}"
    return str(Path(folder_name))


def build_tree_root_path(payload: NotePayload) -> str:
    if payload.output_path:
        raw_path = Path(payload.output_path.strip())
        folder = raw_path.parent if raw_path.suffix.lower() == ".md" else raw_path
        return str(folder / "index.md")
    return str(Path(build_default_output_folder(payload)) / "index.md")


class KnotWorkspace:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = resolve_base_dir(base_dir or Path.cwd())
        load_dotenv(self.base_dir / ".env", override=False)

    def settings(self) -> KnotSettings:
        return KnotSettings.from_base_dir(self.base_dir, provider="auto")

    def processor(
        self,
        *,
        detail_mode: str | None = None,
        output_mode: str | None = None,
    ) -> KnotProcessor:
        settings = KnotSettings.from_base_dir(
            self.base_dir,
            provider="auto",
            detail_mode=detail_mode,
            output_mode=output_mode,
        )
        return KnotProcessor(settings)

    def vault_dir(self) -> Path:
        return self.settings().vault_dir

    def prune_empty_dirs(self, start: Path) -> None:
        vault_dir = self.vault_dir().resolve()
        current = start.resolve()

        while current != vault_dir and vault_dir in current.parents:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent

    def resolve_note_path(self, relative_path: str) -> Path:
        raw_path = Path(relative_path.strip())
        if raw_path.is_absolute():
            raise HTTPException(status_code=400, detail="Note path must be relative.")

        if raw_path.parts and raw_path.parts[0] == self.vault_dir().name:
            raw_path = Path(*raw_path.parts[1:])

        if raw_path.suffix.lower() != ".md":
            raw_path = raw_path.with_suffix(".md")

        candidate = (self.vault_dir() / raw_path).resolve()
        vault_dir = self.vault_dir().resolve()
        if candidate != vault_dir and vault_dir not in candidate.parents:
            raise HTTPException(status_code=400, detail="Note path escapes the vault.")
        return candidate

    def synthetic_source_path(self, relative_path: str) -> Path:
        raw_path = Path(relative_path.strip())
        if raw_path.parts and raw_path.parts[0] == self.vault_dir().name:
            raw_path = Path(*raw_path.parts[1:])
        if raw_path.suffix.lower() != ".md":
            raw_path = raw_path.with_suffix(".md")
        return (self.base_dir / "Inbox" / raw_path).resolve()

    def resolve_folder_path(self, relative_path: str) -> Path:
        raw_path = Path(relative_path.strip())
        if raw_path.is_absolute():
            raise HTTPException(status_code=400, detail="Folder path must be relative.")

        if raw_path.parts and raw_path.parts[0] == self.vault_dir().name:
            raw_path = Path(*raw_path.parts[1:])

        candidate = (self.vault_dir() / raw_path).resolve()
        vault_dir = self.vault_dir().resolve()
        if candidate != vault_dir and vault_dir not in candidate.parents:
            raise HTTPException(status_code=400, detail="Folder path escapes the vault.")
        return candidate

    def list_notes(self) -> list[dict[str, Any]]:
        processor = self.processor()
        items: list[dict[str, Any]] = []

        for note_path in sorted(
            self.vault_dir().rglob("*.md"),
            key=lambda item: (item.stat().st_mtime, str(item).lower()),
            reverse=True,
        ):
            content = note_path.read_text(encoding="utf-8")
            cleaned = processor.clean_indexable_text(content).strip()
            preview = ""
            for line in cleaned.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("# "):
                    continue
                preview = stripped
                break

            items.append(
                {
                    "path": str(note_path.relative_to(self.vault_dir())),
                    "title": note_path.stem,
                    "preview": processor.compact_excerpt(preview) if preview else "",
                    "updated_at": int(note_path.stat().st_mtime),
                }
            )

        return items

    def read_note(self, relative_path: str) -> dict[str, Any]:
        note_path = self.resolve_note_path(relative_path)
        if not note_path.exists():
            raise HTTPException(status_code=404, detail=f"Note not found: {relative_path}")

        return {
            "path": str(note_path.relative_to(self.vault_dir())),
            "title": note_path.stem,
            "content": note_path.read_text(encoding="utf-8"),
            "updated_at": int(note_path.stat().st_mtime),
        }

    def save_note(self, payload: NotePayload, *, must_not_exist: bool) -> dict[str, Any]:
        note_path = self.resolve_note_path(payload.resolved_path())
        note_path.parent.mkdir(parents=True, exist_ok=True)

        if must_not_exist and note_path.exists():
            raise HTTPException(
                status_code=409,
                detail=f"Note already exists: {payload.resolved_path()}",
            )

        content = payload.content.rstrip() + "\n" if payload.content.strip() else ""
        note_path.write_text(content, encoding="utf-8")

        return {
            "path": str(note_path.relative_to(self.vault_dir())),
            "title": note_path.stem,
            "content": content,
            "updated_at": int(note_path.stat().st_mtime),
        }

    def delete_note(self, relative_path: str) -> dict[str, Any]:
        note_path = self.resolve_note_path(relative_path)
        if not note_path.exists():
            raise HTTPException(status_code=404, detail=f"Note not found: {relative_path}")

        note_path.unlink()
        self.prune_empty_dirs(note_path.parent)
        return {"deleted": True, "path": str(note_path.relative_to(self.vault_dir()))}

    def move_note(self, payload: MovePayload) -> dict[str, Any]:
        source_reference = payload.resolved_source_path()
        destination_reference = payload.resolved_destination_path()
        source_path = self.resolve_note_path(source_reference)
        destination_path = self.resolve_note_path(destination_reference)

        if not source_path.exists():
            raise HTTPException(status_code=404, detail=f"Note not found: {source_reference}")

        if source_path == destination_path:
            return self.read_note(str(source_path.relative_to(self.vault_dir())))

        if destination_path.exists():
            raise HTTPException(status_code=409, detail=f"Note already exists: {destination_reference}")

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.rename(destination_path)
        self.prune_empty_dirs(source_path.parent)

        return self.read_note(str(destination_path.relative_to(self.vault_dir())))

    def process_note(self, payload: NotePayload) -> ProcessResponse:
        processor = self.processor(
            detail_mode=payload.detail_mode,
            output_mode=payload.output_mode,
        )
        processor._assert_provider_credentials()

        raw_text = payload.content.strip()
        if not raw_text:
            raise HTTPException(status_code=400, detail="Cannot process an empty note.")

        source_path = self.synthetic_source_path(payload.source_reference())
        output_mode = KnotSettings.normalize_output_mode(payload.output_mode)

        if output_mode == "linked_tree":
            target_path = self.resolve_note_path(build_tree_root_path(payload))
            note_title = note_stem(payload.title, fallback=note_stem(payload.source_reference()))
        else:
            target_relative_path = payload.output_path or build_default_output_path(payload)
            target_path = self.resolve_note_path(target_relative_path)
            note_title = target_path.stem
            target_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            result = processor.process_raw_text(
                raw_text,
                source_path=source_path,
                target_path=target_path,
                note_title=note_title,
                output_mode=output_mode,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        final_note = result.note_path.read_text(encoding="utf-8")
        output_folder = result.root_note_path.parent if result.root_note_path else result.note_path.parent
        status = (
            f"Created linked folder {output_folder.name}."
            if output_mode == "linked_tree"
            else f"Processed {result.note_path.name}."
        )
        return ProcessResponse(
            mode=result.mode,
            path=str(result.note_path.relative_to(self.vault_dir())),
            title=result.note_path.stem,
            content=final_note,
            related_links=result.related_links,
            status=status,
            output_folder=str(output_folder.relative_to(self.vault_dir())),
            root_note_path=(
                str(result.root_note_path.relative_to(self.vault_dir()))
                if result.root_note_path is not None
                else None
            ),
            artifacts=[
                str(path.relative_to(self.vault_dir()))
                for path in result.artifacts
            ],
            tree_summary=result.tree_summary,
        )


class ProcessorWorkspace:
    def __init__(self, processor: Any) -> None:
        self._processor = processor
        self.base_dir = Path(processor.settings.base_dir)

    def settings(self) -> Any:
        return self._processor.settings

    def relative_note_path(self, path: Path) -> str:
        return str(path.relative_to(self.base_dir))

    def prune_empty_dirs(self, start: Path) -> None:
        vault_dir = (self.base_dir / "Vault").resolve()
        current = start.resolve()

        while current != vault_dir and vault_dir in current.parents:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent

    def resolve_note_path(self, relative_path: str) -> Path:
        raw_path = Path(relative_path.strip())
        if raw_path.is_absolute():
            raise HTTPException(status_code=400, detail="Note path must be relative.")

        if raw_path.parts and raw_path.parts[0] not in {"Vault", "Inbox"}:
            raw_path = Path("Vault") / raw_path

        if raw_path.suffix.lower() != ".md":
            raw_path = raw_path.with_suffix(".md")

        candidate = self.base_dir / raw_path
        candidate_resolved = candidate.resolve()
        base_resolved = self.base_dir.resolve()
        if candidate_resolved != base_resolved and base_resolved not in candidate_resolved.parents:
            raise HTTPException(status_code=400, detail="Note path escapes the workspace.")
        return candidate

    def synthetic_source_path(self, relative_path: str) -> Path:
        raw_path = Path(relative_path.strip())
        if raw_path.parts and raw_path.parts[0] == "Vault":
            raw_path = Path("Inbox", *raw_path.parts[1:])
        elif raw_path.parts and raw_path.parts[0] != "Inbox":
            raw_path = Path("Inbox") / raw_path
        if raw_path.suffix.lower() != ".md":
            raw_path = raw_path.with_suffix(".md")
        return self.base_dir / raw_path

    def resolve_folder_path(self, relative_path: str) -> Path:
        raw_path = Path(relative_path.strip())
        if raw_path.is_absolute():
            raise HTTPException(status_code=400, detail="Folder path must be relative.")

        if raw_path.parts and raw_path.parts[0] not in {"Vault", "Inbox"}:
            raw_path = Path("Vault") / raw_path

        candidate = self.base_dir / raw_path
        candidate_resolved = candidate.resolve()
        base_resolved = self.base_dir.resolve()
        if candidate_resolved != base_resolved and base_resolved not in candidate_resolved.parents:
            raise HTTPException(status_code=400, detail="Folder path escapes the workspace.")
        return candidate

    def list_notes(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        vault_dir = self.base_dir / "Vault"
        for note_path in sorted(vault_dir.rglob("*.md")):
            content = note_path.read_text(encoding="utf-8")
            items.append(
                {
                    "path": self.relative_note_path(note_path),
                    "title": note_path.stem,
                    "scope": "vault",
                    "modified_at": note_path.stat().st_mtime,
                    "size_bytes": note_path.stat().st_size,
                }
            )
        return items

    def read_note(self, relative_path: str) -> dict[str, Any]:
        note_path = self.resolve_note_path(relative_path)
        if not note_path.exists():
            raise HTTPException(status_code=404, detail=f"Note not found: {relative_path}")
        return {
            "path": self.relative_note_path(note_path),
            "title": note_path.stem,
            "content": note_path.read_text(encoding="utf-8"),
            "updated_at": int(note_path.stat().st_mtime),
        }

    def save_note(self, payload: NotePayload, *, must_not_exist: bool) -> dict[str, Any]:
        note_path = self.resolve_note_path(payload.resolved_path())
        if must_not_exist and note_path.exists():
            raise HTTPException(
                status_code=409,
                detail=f"Note already exists: {payload.resolved_path()}",
            )
        content = payload.content.rstrip() + "\n" if payload.content.strip() else ""
        self._processor.save_note(note_path, content, source_path=self.synthetic_source_path(payload.resolved_path()))
        return {
            "path": self.relative_note_path(note_path),
            "title": note_path.stem,
            "content": content,
            "updated_at": int(note_path.stat().st_mtime),
        }

    def delete_note(self, relative_path: str) -> dict[str, Any]:
        note_path = self.resolve_note_path(relative_path)
        self._processor.delete_note(note_path)
        self.prune_empty_dirs(note_path.parent)
        return {"deleted": True, "path": self.relative_note_path(note_path)}

    def move_note(self, payload: MovePayload) -> dict[str, Any]:
        source_reference = payload.resolved_source_path()
        destination_reference = payload.resolved_destination_path()
        source_path = self.resolve_note_path(source_reference)
        destination_path = self.resolve_note_path(destination_reference)

        if not source_path.exists():
            raise HTTPException(status_code=404, detail=f"Note not found: {source_reference}")

        if source_path == destination_path:
            return self.read_note(self.relative_note_path(source_path))

        if destination_path.exists():
            raise HTTPException(status_code=409, detail=f"Note already exists: {destination_reference}")

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.rename(destination_path)
        self.prune_empty_dirs(source_path.parent)

        return self.read_note(self.relative_note_path(destination_path))

    def process_note(self, payload: NotePayload) -> dict[str, Any]:
        output_mode = KnotSettings.normalize_output_mode(payload.output_mode)
        if output_mode == "linked_tree":
            target_path = self.resolve_note_path(build_tree_root_path(payload))
            note_title = note_stem(payload.title, fallback=note_stem(payload.source_reference()))
        else:
            target_relative_path = payload.output_path or build_default_output_path(payload)
            target_path = self.resolve_note_path(target_relative_path)
            note_title = target_path.stem

        result = self._processor.process_raw_text(
            payload.content,
            source_path=self.synthetic_source_path(payload.source_reference()),
            target_path=target_path,
            note_title=note_title,
            output_mode=output_mode,
        )
        content = result.note_path.read_text(encoding="utf-8")
        output_folder = result.root_note_path.parent if result.root_note_path else result.note_path.parent
        return {
            "mode": result.mode,
            "path": self.relative_note_path(result.note_path),
            "note_path": self.relative_note_path(result.note_path),
            "title": result.note_path.stem,
            "content": content,
            "related_links": result.related_links,
            "status": (
                f"Created linked folder {output_folder.name}."
                if output_mode == "linked_tree"
                else f"Processed {result.note_path.name}."
            ),
            "output_folder": self.relative_note_path(output_folder),
            "root_note_path": (
                self.relative_note_path(result.root_note_path)
                if result.root_note_path is not None
                else None
            ),
            "artifacts": [self.relative_note_path(path) for path in result.artifacts],
            "tree_summary": result.tree_summary,
        }


def create_app(
    *,
    workspace: KnotWorkspace | ProcessorWorkspace | None = None,
    processor: Any | None = None,
) -> FastAPI:
    backend = workspace or (ProcessorWorkspace(processor) if processor is not None else KnotWorkspace())
    app = FastAPI(title="Knot API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:1420",
            "http://localhost:1420",
            "http://tauri.localhost",
            "tauri://localhost",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        current = backend.settings()
        provider = getattr(current, "provider", "unknown")
        healthy = True
        message = f"Provider: {provider}."

        if isinstance(current, KnotSettings):
            if provider == "openai" and not KnotSettings.configured_env("OPENAI_API_KEY"):
                healthy = False
                message = f"{message} Missing OPENAI_API_KEY."
            elif provider == "google" and not KnotSettings.google_api_key():
                healthy = False
                message = f"{message} Missing GOOGLE_API_KEY."
            else:
                vault_dir = current.vault_dir
                vault_label = (
                    vault_dir.relative_to(backend.base_dir)
                    if vault_dir.is_relative_to(backend.base_dir)
                    else vault_dir
                )
                message = f"{message} Vault: {vault_label}."

        return {
            "status": "ok" if healthy else "error",
            "healthy": healthy,
            "message": message,
        }

    @app.get("/settings")
    def settings() -> dict[str, Any]:
        current = backend.settings()
        return {
            "base_dir": str(backend.base_dir),
            "vault_dir": str(getattr(current, "vault_dir", backend.base_dir / "Vault")),
            "inbox_dir": str(getattr(current, "inbox_dir", backend.base_dir / "Inbox")),
            "provider": getattr(current, "provider", "unknown"),
            "detail_mode": getattr(current, "detail_mode", "minimal"),
            "output_mode": getattr(current, "output_mode", "single_note"),
        }

    @app.get("/notes")
    def list_notes() -> list[dict[str, Any]]:
        return backend.list_notes()

    @app.get("/notes/content")
    def get_note_content(path: str = Query(..., min_length=1)) -> dict[str, Any]:
        return backend.read_note(path)

    @app.put("/notes/content")
    def put_note_content(payload: NotePayload) -> dict[str, Any]:
        return backend.save_note(payload, must_not_exist=False)

    @app.delete("/notes/content")
    def delete_note_content(path: str = Query(..., min_length=1)) -> dict[str, Any]:
        return backend.delete_note(path)

    @app.post("/notes/move")
    def move_note(payload: MovePayload) -> dict[str, Any]:
        return backend.move_note(payload)

    @app.post("/notes/rename")
    @app.patch("/notes/rename")
    @app.post("/notes/content/rename")
    @app.patch("/notes/content/rename")
    def rename_note(payload: MovePayload) -> dict[str, Any]:
        return backend.move_note(payload)

    @app.post("/notes")
    def post_note(payload: NotePayload) -> dict[str, Any]:
        return backend.save_note(payload, must_not_exist=True)

    @app.post("/knot/process")
    def process_note(payload: NotePayload) -> Any:
        return backend.process_note(payload)

    return app


app = create_app()
