from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Sequence

from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from prompts import (
    NEW_NOTE_USER_PROMPT,
    NOTE_PROCESSING_SYSTEM_PROMPT,
    UPDATE_NOTE_USER_PROMPT,
)

RAW_ARCHIVE_RE = re.compile(
    r"\n?<details>\s*\n<summary>Original Raw Notes</summary>\s*\n\n.*?\n</details>\s*$",
    re.DOTALL,
)
ALL_RAW_ARCHIVES_RE = re.compile(
    r"\n?<details>\s*\n<summary>Original Raw Notes</summary>\s*\n\n.*?\n</details>\s*",
    re.DOTALL,
)
RELATED_NOTES_RE = re.compile(
    r"\n## Related Notes\n(?:- \[\[[^\n]+\]\]\n)+\n*",
    re.MULTILINE,
)


@dataclass(slots=True)
class KnotSettings:
    base_dir: Path
    inbox_dir: Path
    vault_dir: Path
    chroma_dir: Path
    collection_name: str = "knot-notes"
    chat_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    update_distance_threshold: float = 0.35
    chunk_size: int = 1200
    chunk_overlap: int = 150

    @classmethod
    def from_base_dir(
        cls,
        base_dir: Path,
        *,
        chat_model: str | None = None,
        update_distance_threshold: float | None = None,
    ) -> "KnotSettings":
        base_dir = base_dir.resolve()
        chroma_dir = Path(os.getenv("KNOT_CHROMA_DIR", "data/chroma"))
        if not chroma_dir.is_absolute():
            chroma_dir = base_dir / chroma_dir

        return cls(
            base_dir=base_dir,
            inbox_dir=base_dir / "Inbox",
            vault_dir=base_dir / "Vault",
            chroma_dir=chroma_dir,
            collection_name=os.getenv("KNOT_COLLECTION_NAME", "knot-notes"),
            chat_model=chat_model or os.getenv("KNOT_MODEL", "gpt-4o-mini"),
            embedding_model=os.getenv(
                "KNOT_EMBEDDING_MODEL",
                "text-embedding-3-small",
            ),
            update_distance_threshold=update_distance_threshold
            if update_distance_threshold is not None
            else float(os.getenv("KNOT_UPDATE_DISTANCE_THRESHOLD", "0.35")),
        )


@dataclass(slots=True)
class NoteMatch:
    note_path: Path
    title: str
    score: float
    excerpt: str = ""


@dataclass(slots=True)
class ProcessResult:
    mode: str
    source_path: Path
    note_path: Path
    related_links: list[str] = field(default_factory=list)
    matched_note: NoteMatch | None = None


class KnotProcessor:
    def __init__(self, settings: KnotSettings) -> None:
        self.settings = settings
        self.settings.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.settings.vault_dir.mkdir(parents=True, exist_ok=True)
        self.settings.chroma_dir.mkdir(parents=True, exist_ok=True)

        self._llm: ChatOpenAI | None = None
        self._embeddings: OpenAIEmbeddings | None = None
        self._vector_store: Chroma | None = None
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.settings.chunk_size,
            chunk_overlap=self.settings.chunk_overlap,
        )

    def process(self, filename: str) -> ProcessResult:
        self._assert_api_key()

        source_path = self.resolve_inbox_path(filename)
        raw_text = source_path.read_text(encoding="utf-8").strip()
        if not raw_text:
            raise ValueError(f"Inbox note is empty: {source_path}")

        default_note_path = self.settings.vault_dir / source_path.name
        exact_match = (
            NoteMatch(
                note_path=default_note_path,
                title=default_note_path.stem,
                score=0.0,
            )
            if default_note_path.exists()
            else None
        )
        semantic_match = None if exact_match else self.find_existing_note(raw_text)
        matched_note = exact_match or semantic_match

        should_update = bool(
            exact_match
            or (
                semantic_match
                and semantic_match.score <= self.settings.update_distance_threshold
            )
        )
        target_path = matched_note.note_path if should_update and matched_note else default_note_path

        if should_update and matched_note:
            existing_note = target_path.read_text(encoding="utf-8")
            update_block = self.render_update_block(existing_note, raw_text)
            body_for_matching = self.strip_related_notes(existing_note)
            related_links = self.related_note_titles(
                f"{body_for_matching}\n\n{self.strip_raw_archives(update_block)}",
                exclude_path=target_path,
            )
            final_note = self.merge_update(existing_note, update_block, related_links)
            mode = "update"
        else:
            note_title = target_path.stem
            draft_note = self.render_new_note(note_title, raw_text)
            related_links = self.related_note_titles(
                self.strip_raw_archives(draft_note),
                exclude_path=target_path,
            )
            final_note = self.insert_related_notes_before_raw_archive(
                draft_note,
                related_links,
            )
            mode = "create"

        target_path.write_text(final_note.rstrip() + "\n", encoding="utf-8")
        self.upsert_note(target_path, final_note, source_path=source_path)

        return ProcessResult(
            mode=mode,
            source_path=source_path,
            note_path=target_path,
            related_links=related_links,
            matched_note=matched_note if should_update else None,
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

    def find_existing_note(self, query_text: str, *, limit: int = 5) -> NoteMatch | None:
        results = self.vector_store.similarity_search_with_score(query_text, k=limit)
        seen_paths: set[str] = set()

        for document, score in results:
            note_path = document.metadata.get("note_path")
            if not note_path or note_path in seen_paths:
                continue

            seen_paths.add(note_path)
            resolved_path = self.settings.base_dir / note_path
            return NoteMatch(
                note_path=resolved_path,
                title=document.metadata.get("note_title", resolved_path.stem),
                score=float(score),
                excerpt=self.compact_excerpt(document.page_content),
            )

        return None

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
        titles: list[str] = []
        seen_paths: set[str] = set()
        excluded = self.relative_note_path(exclude_path) if exclude_path else None

        for document, _score in results:
            note_path = document.metadata.get("note_path")
            if not note_path or note_path == excluded or note_path in seen_paths:
                continue

            seen_paths.add(note_path)
            titles.append(document.metadata.get("note_title", Path(note_path).stem))
            if len(titles) == limit:
                break

        return titles

    def render_new_note(self, note_title: str, raw_text: str) -> str:
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", NOTE_PROCESSING_SYSTEM_PROMPT),
                ("human", NEW_NOTE_USER_PROMPT),
            ]
        )
        chain = prompt | self.llm | StrOutputParser()
        response = chain.invoke(
            {
                "note_title": note_title,
                "raw_text": raw_text,
            }
        )
        return self.clean_model_output(response)

    def render_update_block(self, existing_note: str, raw_text: str) -> str:
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", NOTE_PROCESSING_SYSTEM_PROMPT),
                ("human", UPDATE_NOTE_USER_PROMPT),
            ]
        )
        chain = prompt | self.llm | StrOutputParser()
        response = chain.invoke(
            {
                "existing_note": existing_note,
                "raw_text": raw_text,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
        )
        return self.clean_model_output(response)

    def merge_update(
        self,
        existing_note: str,
        update_block: str,
        related_links: Sequence[str],
    ) -> str:
        base = self.strip_related_notes(existing_note).rstrip()
        addition = update_block.strip()

        if not related_links:
            return f"{base}\n\n{addition}\n"

        related_section = self.format_related_notes(related_links).strip()
        return f"{base}\n\n{related_section}\n\n{addition}\n"

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
        return f"## Related Notes\n{lines}\n"

    def strip_related_notes(self, note_text: str) -> str:
        return RELATED_NOTES_RE.sub("\n", note_text).strip() + "\n"

    def strip_raw_archives(self, note_text: str) -> str:
        stripped = ALL_RAW_ARCHIVES_RE.sub("\n", note_text)
        return stripped.strip()

    def clean_model_output(self, text: str) -> str:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```markdown").removeprefix("```")
            cleaned = cleaned.removesuffix("```").strip()
        return cleaned

    def upsert_note(self, note_path: Path, note_text: str, *, source_path: Path) -> None:
        embedding_text = self.strip_raw_archives(self.strip_related_notes(note_text))
        if not embedding_text:
            embedding_text = note_text

        metadata = {
            "note_path": self.relative_note_path(note_path),
            "note_title": note_path.stem,
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

    def _assert_api_key(self) -> None:
        if os.getenv("OPENAI_API_KEY"):
            return
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to .env before running `knot process`."
        )

    @property
    def llm(self) -> ChatOpenAI:
        if self._llm is None:
            self._llm = ChatOpenAI(
                model=self.settings.chat_model,
                temperature=0,
            )
        return self._llm

    @property
    def embeddings(self) -> OpenAIEmbeddings:
        if self._embeddings is None:
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
