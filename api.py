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
    note_name: str | None = Field(default=None, min_length=1)
    detail_mode: str | None = None
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
    source_path: str = Field(min_length=1)
    destination_path: str = Field(min_length=1)


class ProcessResponse(BaseModel):
    mode: str
    path: str
    title: str
    content: str
    related_links: list[str] = Field(default_factory=list)
    status: str
    output_folder: str


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
    note_name = note_stem(payload.note_name, fallback=source_stem)
    return str(Path(folder_name) / f"{note_name}.md")


class KnotWorkspace:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = resolve_base_dir(base_dir or Path.cwd())
        load_dotenv(self.base_dir / ".env", override=False)

    def settings(self) -> KnotSettings:
        return KnotSettings.from_base_dir(self.base_dir, provider="auto")

    def processor(self, *, detail_mode: str | None = None) -> KnotProcessor:
        settings = KnotSettings.from_base_dir(
            self.base_dir,
            provider="auto",
            detail_mode=detail_mode,
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

    def list_notes(self) -> list[dict[str, Any]]:
        processor = self.processor()
        items: list[dict[str, Any]] = []

        for note_path in sorted(
            self.vault_dir().rglob("*.md"),
            key=lambda item: (item.stat().st_mtime, str(item).lower()),
            reverse=True,
        ):
            content = note_path.read_text(encoding="utf-8")
            cleaned = processor.strip_raw_archives(processor.strip_related_notes(content)).strip()
            title = processor.infer_note_title(content, fallback=note_path.stem)
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
                    "title": title,
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
            "title": payload.title or note_path.stem,
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
        source_path = self.resolve_note_path(payload.source_path)
        destination_path = self.resolve_note_path(payload.destination_path)

        if not source_path.exists():
            raise HTTPException(status_code=404, detail=f"Note not found: {payload.source_path}")

        if source_path == destination_path:
            return self.read_note(str(source_path.relative_to(self.vault_dir())))

        if destination_path.exists():
            raise HTTPException(status_code=409, detail=f"Note already exists: {payload.destination_path}")

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.rename(destination_path)
        self.prune_empty_dirs(source_path.parent)

        return self.read_note(str(destination_path.relative_to(self.vault_dir())))

    def process_note(self, payload: NotePayload) -> ProcessResponse:
        processor = self.processor(detail_mode=payload.detail_mode)
        processor._assert_provider_credentials()

        raw_text = payload.content.strip()
        if not raw_text:
            raise HTTPException(status_code=400, detail="Cannot process an empty note.")

        target_relative_path = payload.output_path or build_default_output_path(payload)
        target_path = self.resolve_note_path(target_relative_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        previous_note = target_path.read_text(encoding="utf-8") if target_path.exists() else None
        note_title = processor.infer_note_title(raw_text, fallback=target_path.stem)
        if payload.title:
            note_title = payload.title
        source_path = self.synthetic_source_path(payload.source_reference())

        try:
            if previous_note is not None and previous_note.strip() != raw_text:
                update_fragments = processor.render_update_fragments(previous_note, raw_text)
                body_for_matching = processor.strip_related_notes(previous_note)
                fragment_text = processor.strip_raw_archives("\n\n".join(update_fragments))
                related_links = processor.related_links_for(
                    f"{body_for_matching}\n\n{fragment_text}",
                    exclude_path=target_path,
                )
                final_note, _merge_report = processor._merge_engine.merge(
                    previous_note,
                    update_fragments,
                    related_links,
                    raw_text,
                    related_heading=processor.related_heading_label(),
                )
                mode = "update"
                status = f"Merged new raw content into {target_path.name}."
            else:
                draft_note = processor.render_new_note(note_title, raw_text)
                related_links = processor.related_links_for(
                    processor.strip_raw_archives(draft_note),
                    exclude_path=target_path,
                )
                final_note = processor.insert_related_notes_before_raw_archive(
                    draft_note,
                    related_links,
                )
                mode = "create" if previous_note is None else "format"
                status = (
                    f"Created {target_path.name} from raw Markdown."
                    if previous_note is None
                    else f"Formatted {target_path.name} in place."
                )

            final_note = final_note.rstrip() + "\n"
            processor.write_note_atomically(target_path, final_note)
            try:
                processor.upsert_note(target_path, final_note, source_path=source_path)
            except Exception:
                processor.rollback_note_write(target_path, previous_note)
                raise
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        return ProcessResponse(
            mode=mode,
            path=str(target_path.relative_to(self.vault_dir())),
            title=note_title,
            content=final_note,
            related_links=related_links,
            status=status,
            output_folder=str(target_path.parent.relative_to(self.vault_dir())),
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

    def list_notes(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        vault_dir = self.base_dir / "Vault"
        for note_path in sorted(vault_dir.rglob("*.md")):
            content = note_path.read_text(encoding="utf-8")
            items.append(
                {
                    "path": self.relative_note_path(note_path),
                    "title": self._processor.infer_note_title(content, fallback=note_path.stem),
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
            "title": self._processor.infer_note_title(
                note_path.read_text(encoding="utf-8"),
                fallback=note_path.stem,
            ),
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
            "title": payload.title or note_path.stem,
            "content": content,
            "updated_at": int(note_path.stat().st_mtime),
        }

    def delete_note(self, relative_path: str) -> dict[str, Any]:
        note_path = self.resolve_note_path(relative_path)
        self._processor.delete_note(note_path)
        self.prune_empty_dirs(note_path.parent)
        return {"deleted": True, "path": self.relative_note_path(note_path)}

    def move_note(self, payload: MovePayload) -> dict[str, Any]:
        source_path = self.resolve_note_path(payload.source_path)
        destination_path = self.resolve_note_path(payload.destination_path)

        if not source_path.exists():
            raise HTTPException(status_code=404, detail=f"Note not found: {payload.source_path}")

        if source_path == destination_path:
            return self.read_note(self.relative_note_path(source_path))

        if destination_path.exists():
            raise HTTPException(status_code=409, detail=f"Note already exists: {payload.destination_path}")

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.rename(destination_path)
        self.prune_empty_dirs(source_path.parent)

        return self.read_note(self.relative_note_path(destination_path))

    def process_note(self, payload: NotePayload) -> dict[str, Any]:
        target_relative_path = payload.output_path or build_default_output_path(payload)
        target_path = self.resolve_note_path(target_relative_path)
        result = self._processor.process_raw_text(
            payload.content,
            source_path=self.synthetic_source_path(payload.source_reference()),
            target_path=target_path,
            note_title=payload.title or payload.note_name,
        )
        content = target_path.read_text(encoding="utf-8")
        return {
            "mode": result.mode,
            "path": self.relative_note_path(result.note_path),
            "note_path": self.relative_note_path(result.note_path),
            "title": payload.title or payload.note_name or target_path.stem,
            "content": content,
            "related_links": result.related_links,
            "status": f"Processed {target_path.name}.",
            "output_folder": self.relative_note_path(target_path.parent),
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

    @app.post("/notes")
    def post_note(payload: NotePayload) -> dict[str, Any]:
        return backend.save_note(payload, must_not_exist=True)

    @app.post("/knot/process")
    def process_note(payload: NotePayload) -> Any:
        return backend.process_note(payload)

    return app


app = create_app()
