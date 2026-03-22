from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from librarian import SemanticMergeEngine
from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import (
    ChatGoogleGenerativeAI,
    GoogleGenerativeAIEmbeddings,
)
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from models import KnotSettings, NoteMatch, ProcessResult
from prompts import (
    NEW_NOTE_USER_PROMPT,
    UPDATE_NOTE_FRAGMENT_USER_PROMPT,
    note_processing_system_prompt,
)

RAW_ARCHIVE_RE = re.compile(
    r"\n?<details>\s*\n<summary>(?:Original Raw Notes|Raw Archive)</summary>\s*\n\n.*?\n</details>\s*$",
    re.DOTALL,
)
ALL_RAW_ARCHIVES_RE = re.compile(
    r"\n?<details>\s*\n<summary>(?:Original Raw Notes|Raw Archive)</summary>\s*\n\n.*?\n</details>\s*",
    re.DOTALL,
)
RELATED_NOTES_RE = re.compile(
    r"\n(?:## Related Notes|### Connections)\n(?:- \[\[[^\n]+\]\]\n)+\n*",
    re.MULTILINE,
)


def normalize_provider(provider: str | None) -> str:
    return KnotSettings.normalize_provider(provider)


def google_api_key() -> str | None:
    return KnotSettings.google_api_key()


def default_chat_model(provider: str) -> str:
    return KnotSettings.default_chat_model(provider)


def default_embedding_model(provider: str) -> str:
    return KnotSettings.default_embedding_model(provider)


class KnotProcessor:
    def __init__(self, settings: KnotSettings) -> None:
        self.settings = settings
        self.settings.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.settings.vault_dir.mkdir(parents=True, exist_ok=True)
        self.settings.chroma_dir.mkdir(parents=True, exist_ok=True)

        self._llm: Any | None = None
        self._embeddings: Any | None = None
        self._vector_store: Chroma | None = None
        self._merge_engine = SemanticMergeEngine()
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.settings.chunk_size,
            chunk_overlap=self.settings.chunk_overlap,
        )

    def process(
        self,
        filename: str,
        *,
        status_callback: Callable[[str], None] | None = None,
    ) -> ProcessResult:
        source_path = self.resolve_inbox_path(filename)
        raw_text = source_path.read_text(encoding="utf-8").strip()
        return self.process_raw_text(
            raw_text,
            source_path=source_path,
            status_callback=status_callback,
        )

    def process_raw_text(
        self,
        raw_text: str,
        *,
        source_path: Path | None = None,
        target_path: Path | None = None,
        note_title: str | None = None,
        status_callback: Callable[[str], None] | None = None,
    ) -> ProcessResult:
        def report(message: str) -> None:
            if status_callback is not None:
                status_callback(message)

        report("Checking model credentials")
        self._assert_provider_credentials()

        raw_text = raw_text.strip()
        if not raw_text:
            raise ValueError("Raw note is empty.")

        resolved_source_path = source_path
        if resolved_source_path is None:
            resolved_source_path = self.settings.inbox_dir / "manual.md"
        resolved_source_path = self.resolve_note_path(
            resolved_source_path,
            default_dir=self.settings.inbox_dir,
        )

        matched_note: NoteMatch | None = None
        if target_path is not None:
            target_path = self.resolve_note_path(target_path, default_dir=self.settings.vault_dir)
            matched_note = (
                NoteMatch(
                    note_path=target_path,
                    title=target_path.stem,
                    score=0.0,
                )
                if target_path.exists()
                else None
            )
            if matched_note is not None:
                report("Chunking update for merge")
                existing_note = target_path.read_text(encoding="utf-8")
                update_fragments = self.render_update_fragments(existing_note, raw_text)
                body_for_matching = self.strip_related_notes(existing_note)
                fragment_text = self.strip_raw_archives("\n\n".join(update_fragments))
                related_links = self.related_links_for(
                    f"{body_for_matching}\n\n{fragment_text}",
                    exclude_path=target_path,
                )
                report("Merging into existing note")
                final_note, _merge_report = self._merge_engine.merge(
                    existing_note,
                    update_fragments,
                    related_links,
                    raw_text,
                    related_heading=self.related_heading_label(),
                )
                mode = "update"
            else:
                resolved_title = note_title or self.infer_note_title(
                    raw_text,
                    fallback=target_path.stem,
                )
                report(
                    f"Formatting note with {self.settings.chat_model} "
                    f"({self.settings.detail_mode})"
                )
                draft_note = self.render_new_note(resolved_title, raw_text)
                related_links = self.related_links_for(
                    self.strip_raw_archives(draft_note),
                    exclude_path=target_path,
                )
                final_note = self.insert_related_notes_before_raw_archive(
                    draft_note,
                    related_links,
                )
                mode = "create"
        else:
            default_note_path = self.settings.vault_dir / resolved_source_path.name
            exact_match = (
                NoteMatch(
                    note_path=default_note_path,
                    title=default_note_path.stem,
                    score=0.0,
                )
                if default_note_path.exists()
                else None
            )
            report("Searching semantic memory")
            semantic_match = None if exact_match else self.find_existing_note(raw_text)
            matched_note = exact_match or semantic_match

            should_update = bool(
                exact_match
                or (
                    semantic_match
                    and semantic_match.score <= self.settings.update_distance_threshold
                )
            )
            target_path = (
                matched_note.note_path if should_update and matched_note else default_note_path
            )

            if should_update and matched_note:
                existing_note = target_path.read_text(encoding="utf-8")
                report("Chunking update for merge")
                update_fragments = self.render_update_fragments(existing_note, raw_text)
                body_for_matching = self.strip_related_notes(existing_note)
                fragment_text = self.strip_raw_archives("\n\n".join(update_fragments))
                related_links = self.related_links_for(
                    f"{body_for_matching}\n\n{fragment_text}",
                    exclude_path=target_path,
                )
                report("Merging into existing note")
                final_note, _merge_report = self._merge_engine.merge(
                    existing_note,
                    update_fragments,
                    related_links,
                    raw_text,
                    related_heading=self.related_heading_label(),
                )
                mode = "update"
            else:
                resolved_title = note_title or self.infer_note_title(
                    raw_text,
                    fallback=target_path.stem,
                )
                report(
                    f"Formatting note with {self.settings.chat_model} "
                    f"({self.settings.detail_mode})"
                )
                draft_note = self.render_new_note(resolved_title, raw_text)
                related_links = self.related_links_for(
                    self.strip_raw_archives(draft_note),
                    exclude_path=target_path,
                )
                final_note = self.insert_related_notes_before_raw_archive(
                    draft_note,
                    related_links,
                )
                mode = "create"

        final_note = final_note.rstrip() + "\n"
        report("Saving note and semantic memory")
        previous_note = (
            target_path.read_text(encoding="utf-8") if target_path.exists() else None
        )
        self.write_note_atomically(target_path, final_note)
        try:
            self.upsert_note(target_path, final_note, source_path=resolved_source_path)
        except Exception:
            self.rollback_note_write(target_path, previous_note)
            raise

        return ProcessResult(
            mode=mode,
            source_path=resolved_source_path,
            note_path=target_path,
            related_links=related_links,
            matched_note=matched_note,
        )

    def resolve_inbox_path(self, filename: str) -> Path:
        candidate = Path(filename)
        if not candidate.suffix:
            candidate = candidate.with_suffix(".md")

        if candidate.is_absolute():
            resolved = candidate
        elif candidate.parts and candidate.parts[0] == self.settings.inbox_dir.name:
            resolved = (self.settings.base_dir / candidate).resolve()
        else:
            resolved = (self.settings.inbox_dir / candidate).resolve()

        if not resolved.exists():
            raise FileNotFoundError(f"Raw note not found: {resolved}")
        return resolved

    def resolve_note_path(
        self,
        path: str | Path,
        *,
        default_dir: Path | None = None,
    ) -> Path:
        candidate = Path(path)
        if not candidate.suffix:
            candidate = candidate.with_suffix(".md")

        if candidate.is_absolute():
            resolved = candidate.resolve()
        elif candidate.parts and candidate.parts[0] == self.settings.base_dir.name:
            resolved = (self.settings.base_dir / candidate).resolve()
        elif candidate.parts and candidate.parts[0] == self.settings.vault_dir.name:
            resolved = (self.settings.base_dir / candidate).resolve()
        elif candidate.parts and candidate.parts[0] == self.settings.inbox_dir.name:
            resolved = (self.settings.base_dir / candidate).resolve()
        else:
            root = default_dir or self.settings.vault_dir
            resolved = (root / candidate).resolve()

        try:
            resolved.relative_to(self.settings.base_dir)
        except ValueError as exc:
            raise ValueError(
                f"Path must stay within the workspace rooted at {self.settings.base_dir}"
            ) from exc

        return resolved

    def list_notes(self, *, include_vault: bool = True, include_inbox: bool = True) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        roots: list[tuple[str, Path]] = []
        if include_vault:
            roots.append(("vault", self.settings.vault_dir))
        if include_inbox:
            roots.append(("inbox", self.settings.inbox_dir))

        for scope, root in roots:
            if not root.exists():
                continue
            for note_path in root.rglob("*.md"):
                if note_path.name.startswith("."):
                    continue
                try:
                    text = note_path.read_text(encoding="utf-8")
                except OSError:
                    continue

                stat = note_path.stat()
                records.append(
                    {
                        "path": self.relative_note_path(note_path),
                        "title": self.infer_note_title(text, fallback=note_path.stem),
                        "scope": scope,
                        "modified_at": stat.st_mtime,
                        "size_bytes": stat.st_size,
                    }
                )

        records.sort(key=lambda item: (item["title"].lower(), item["path"]))
        return records

    def read_note(self, path: str | Path) -> str:
        resolved = self.resolve_note_path(path)
        return resolved.read_text(encoding="utf-8")

    def save_note(
        self,
        path: str | Path,
        note_text: str,
        *,
        source_path: Path | None = None,
    ) -> Path:
        resolved = self.resolve_note_path(path)
        note_text = note_text.rstrip() + "\n"
        previous_note = resolved.read_text(encoding="utf-8") if resolved.exists() else None
        self.write_note_atomically(resolved, note_text)
        try:
            self.upsert_note(resolved, note_text, source_path=source_path or resolved)
        except Exception:
            self.rollback_note_write(resolved, previous_note)
            raise
        return resolved

    def delete_note(self, path: str | Path) -> None:
        resolved = self.resolve_note_path(path)
        if resolved.exists():
            resolved.unlink()
        self.vector_store.delete(where={"note_path": self.relative_note_path(resolved)})

    def find_existing_note(self, query_text: str, *, limit: int = 5) -> NoteMatch | None:
        results = self.vector_store.similarity_search_with_score(query_text, k=limit)
        seen_paths: set[str] = set()
        stale_paths: set[str] = set()

        for document, score in results:
            note_path = document.metadata.get("note_path")
            if not note_path or note_path in seen_paths:
                continue

            seen_paths.add(note_path)
            resolved_path = self.settings.base_dir / note_path
            if not resolved_path.exists():
                stale_paths.add(note_path)
                continue

            return NoteMatch(
                note_path=resolved_path,
                title=document.metadata.get("note_title", resolved_path.stem),
                score=float(score),
                excerpt=self.compact_excerpt(document.page_content),
            )

        for stale_path in stale_paths:
            self.vector_store.delete(where={"note_path": stale_path})

        return None

    def render_new_note(self, note_title: str, raw_text: str) -> str:
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", note_processing_system_prompt(self.settings.detail_mode)),
                ("human", NEW_NOTE_USER_PROMPT),
            ]
        )
        chain = prompt | self.llm | StrOutputParser()
        response = chain.invoke(
            {
                "detail_mode": self.settings.detail_mode,
                "note_title": note_title,
                "raw_text": raw_text,
            }
        )
        return self.clean_model_output(response)

    def render_update_fragments(self, existing_note: str, raw_text: str) -> list[str]:
        chunks = [chunk.strip() for chunk in self._splitter.split_text(raw_text) if chunk.strip()]
        if not chunks:
            chunks = [raw_text]

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", note_processing_system_prompt(self.settings.detail_mode)),
                ("human", UPDATE_NOTE_FRAGMENT_USER_PROMPT),
            ]
        )
        chain = prompt | self.llm | StrOutputParser()
        rendered: list[str] = []

        for chunk in chunks:
            response = chain.invoke(
                {
                    "detail_mode": self.settings.detail_mode,
                    "existing_note": existing_note,
                    "raw_text": chunk,
                }
            )
            cleaned = self.clean_model_output(response)
            if cleaned:
                rendered.append(cleaned)

        return rendered

    def insert_related_notes_before_raw_archive(
        self,
        note_text: str,
        related_links: Sequence[str],
    ) -> str:
        body = note_text.strip()
        if not related_links:
            return body + "\n"

        match = RAW_ARCHIVE_RE.search(body)
        related_section = self.format_related_notes(related_links).strip()

        if not match:
            return f"{body}\n\n{related_section}\n"

        before_archive = body[: match.start()].rstrip()
        raw_archive = body[match.start() :].lstrip()
        return f"{before_archive}\n\n{related_section}\n\n{raw_archive}\n"

    def format_related_notes(self, related_links: Sequence[str]) -> str:
        lines = "\n".join(f"- [[{title}]]" for title in related_links)
        return f"{self.related_heading_label()}\n{lines}\n"

    def strip_related_notes(self, note_text: str) -> str:
        return RELATED_NOTES_RE.sub("\n", note_text).strip() + "\n"

    def strip_raw_archives(self, note_text: str) -> str:
        stripped = ALL_RAW_ARCHIVES_RE.sub("\n", note_text)
        return stripped.strip()

    def infer_note_title(self, raw_text: str, *, fallback: str) -> str:
        for line in raw_text.splitlines():
            if line.startswith("# "):
                return line.removeprefix("# ").strip() or fallback
            if line.strip():
                break
        return fallback

    def clean_model_output(self, text: str) -> str:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```markdown").removeprefix("```")
            cleaned = cleaned.removesuffix("```").strip()
        return cleaned

    def write_note_atomically(self, note_path: Path, note_text: str) -> None:
        temp_path = note_path.with_name(f".{note_path.name}.tmp")
        temp_path.write_text(note_text, encoding="utf-8")
        temp_path.replace(note_path)

    def rollback_note_write(self, note_path: Path, previous_note: str | None) -> None:
        if previous_note is None:
            if note_path.exists():
                note_path.unlink()
            return
        self.write_note_atomically(note_path, previous_note)

    def lexical_related_titles(
        self,
        query_text: str,
        *,
        exclude_path: Path | None = None,
        limit: int = 3,
    ) -> list[str]:
        excluded = exclude_path.resolve() if exclude_path else None
        query_terms = set(re.findall(r"[a-z0-9]+", query_text.lower()))
        scored: list[tuple[float, str]] = []

        for candidate in self.settings.vault_dir.rglob("*.md"):
            if excluded and candidate.resolve() == excluded:
                continue

            candidate_text = candidate.read_text(encoding="utf-8")
            candidate_terms = set(
                re.findall(
                    r"[a-z0-9]+",
                    self.strip_raw_archives(self.strip_related_notes(candidate_text)).lower(),
                )
            )
            if not candidate_terms:
                continue

            overlap = len(query_terms & candidate_terms)
            union = len(query_terms | candidate_terms) or 1
            score = overlap / union
            scored.append((score, candidate.stem))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [title for _score, title in scored[:limit]]

    def upsert_note(self, note_path: Path, note_text: str, *, source_path: Path) -> None:
        embedding_text = self.strip_raw_archives(self.strip_related_notes(note_text))
        if not embedding_text:
            embedding_text = note_text

        metadata = {
            "note_path": self.relative_note_path(note_path),
            "note_title": self.infer_note_title(note_text, fallback=note_path.stem),
            "source_path": str(source_path.relative_to(self.settings.base_dir)),
        }

        documents = self._splitter.create_documents(
            [embedding_text],
            metadatas=[metadata],
        )
        ids = [
            f"{metadata['note_path']}::chunk::{index}"
            for index, _document in enumerate(documents)
        ]

        self.vector_store.delete(where={"note_path": metadata["note_path"]})
        self.vector_store.add_documents(documents=documents, ids=ids)

    def relative_note_path(self, note_path: Path) -> str:
        return str(note_path.resolve().relative_to(self.settings.base_dir))

    def compact_excerpt(self, text: str, *, max_length: int = 160) -> str:
        collapsed = " ".join(text.split())
        if len(collapsed) <= max_length:
            return collapsed
        return collapsed[: max_length - 3].rstrip() + "..."

    def related_links_for(
        self,
        query_text: str,
        *,
        exclude_path: Path | None = None,
    ) -> list[str]:
        if self.settings.detail_mode == "minimal":
            return []
        return self.related_note_titles(query_text, exclude_path=exclude_path)

    def related_heading_label(self) -> str:
        if self.settings.detail_mode == "enriched":
            return "### Connections"
        return "## Related Notes"

    def related_note_titles(
        self,
        query_text: str,
        *,
        exclude_path: Path | None = None,
        limit: int = 3,
    ) -> list[str]:
        results = self.vector_store.similarity_search_with_score(
            query_text,
            k=max(limit * 4, 8),
        )
        semantic_titles: list[str] = []
        seen_paths: set[str] = set()
        excluded = self.relative_note_path(exclude_path) if exclude_path else None

        for document, _score in results:
            note_path = document.metadata.get("note_path")
            if not note_path or note_path == excluded or note_path in seen_paths:
                continue

            resolved_path = self.settings.base_dir / note_path
            if not resolved_path.exists():
                self.vector_store.delete(where={"note_path": note_path})
                continue

            seen_paths.add(note_path)
            semantic_titles.append(document.metadata.get("note_title", Path(note_path).stem))
            if len(semantic_titles) >= limit:
                break

        fallback_titles = self.lexical_related_titles(
            query_text,
            exclude_path=exclude_path,
            limit=max(limit * 2, 6),
        )
        return self._merge_engine.ensure_exact_wikilinks(
            semantic_titles,
            fallback_titles,
            limit=limit,
        )

    def _assert_provider_credentials(self) -> None:
        if self.settings.provider == "openai":
            if KnotSettings.configured_env("OPENAI_API_KEY"):
                return
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add it to .env or switch to "
                "`KNOT_PROVIDER=google` before running `knot process`."
            )

        if google_api_key():
            return

        raise RuntimeError(
            "GOOGLE_API_KEY is not set. Add it to .env before running `knot process` "
            "with Gemini."
        )

    @property
    def llm(self) -> ChatOpenAI | ChatGoogleGenerativeAI:
        if self._llm is None:
            if self.settings.provider == "google":
                self._llm = ChatGoogleGenerativeAI(
                    model=self.settings.chat_model,
                    temperature=0,
                    google_api_key=google_api_key(),
                )
            else:
                self._llm = ChatOpenAI(
                    model=self.settings.chat_model,
                    temperature=0,
                )
        return self._llm

    @property
    def embeddings(self) -> OpenAIEmbeddings | GoogleGenerativeAIEmbeddings:
        if self._embeddings is None:
            if self.settings.provider == "google":
                self._embeddings = GoogleGenerativeAIEmbeddings(
                    model=self.settings.embedding_model,
                    google_api_key=google_api_key(),
                )
            else:
                self._embeddings = OpenAIEmbeddings(
                    model=self.settings.embedding_model,
                )
        return self._embeddings

    @property
    def vector_store(self) -> Chroma:
        if self._vector_store is None:
            self._vector_store = Chroma(
                collection_name=self.settings.collection_name,
                persist_directory=str(self.settings.chroma_dir),
                embedding_function=self.embeddings,
            )
        return self._vector_store
