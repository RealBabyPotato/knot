from __future__ import annotations

import json
import os
import re
import sys
from hashlib import sha1
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

from models import KnotSettings, NoteMatch, ProcessResult, TreeManifest, TreeNodePlan
from prompts import (
    NEW_NOTE_USER_PROMPT,
    TREE_INDEX_USER_PROMPT,
    TREE_MANIFEST_SYSTEM_PROMPT,
    TREE_MANIFEST_USER_PROMPT,
    TREE_NOTE_USER_PROMPT,
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
AUTO_LINKS_RE = re.compile(
    r"\n?<!-- knot:auto-links:start -->.*?<!-- knot:auto-links:end -->\s*",
    re.DOTALL,
)
KNOT_TREE_META_RE = re.compile(r"<!--\s*knot:tree\s+({.*?})\s*-->")
MAX_TREE_NOTES = 20
MAX_TREE_DEPTH = 3


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
        output_mode: str | None = None,
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

        resolved_output_mode = KnotSettings.normalize_output_mode(
            output_mode or self.settings.output_mode
        )
        if resolved_output_mode == "linked_tree":
            target_folder = self.resolve_tree_target_folder(
                source_path=resolved_source_path,
                target_path=target_path,
                note_title=note_title,
            )
            return self.process_raw_tree(
                raw_text,
                source_path=resolved_source_path,
                target_folder=target_folder,
                note_title=note_title,
                status_callback=status_callback,
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

    def resolve_tree_target_folder(
        self,
        *,
        source_path: Path,
        target_path: Path | None,
        note_title: str | None,
    ) -> Path:
        if target_path is not None:
            resolved_target = self.resolve_note_path(target_path, default_dir=self.settings.vault_dir)
            return resolved_target.parent

        title = note_title or source_path.stem
        folder_name = self.slugify_title(title) or source_path.stem
        return self.resolve_folder_path(folder_name, default_dir=self.settings.vault_dir)

    def process_raw_tree(
        self,
        raw_text: str,
        *,
        source_path: Path,
        target_folder: Path,
        note_title: str | None = None,
        status_callback: Callable[[str], None] | None = None,
    ) -> ProcessResult:
        def report(message: str) -> None:
            if status_callback is not None:
                status_callback(message)

        root_title = note_title or self.infer_note_title(raw_text, fallback=source_path.stem)
        target_folder = self.resolve_folder_path(target_folder, default_dir=self.settings.vault_dir)
        target_folder.mkdir(parents=True, exist_ok=True)

        report("Planning linked note tree")
        manifest = self.plan_tree_manifest(raw_text, tree_title=root_title)
        existing_tree = self.inspect_existing_tree(target_folder)
        if existing_tree["has_unmanaged_markdown"]:
            raise ValueError(
                f"Output folder already contains unmanaged markdown: {target_folder.relative_to(self.settings.base_dir)}"
            )

        report("Rendering linked notes")
        artifacts: list[Path] = []
        created = 0
        updated = 0
        unchanged = 0
        previous_contents: dict[Path, str | None] = {}

        try:
            root_note_path = target_folder / "index.md"
            root_content = self.render_tree_index_note(
                manifest,
                raw_text=raw_text,
                root_note_path=root_note_path,
                source_path=source_path,
            )
            previous_root = root_note_path.read_text(encoding="utf-8") if root_note_path.exists() else None
            previous_contents[root_note_path] = previous_root
            if previous_root != root_content:
                self.write_note_atomically(root_note_path, root_content)
                self.upsert_note(
                    root_note_path,
                    root_content,
                    source_path=source_path,
                    extra_metadata={
                        "tree_id": self.tree_id_for(target_folder),
                        "tree_root": self.relative_note_path(root_note_path),
                        "tree_node_key": "__root__",
                    },
                )
            artifacts.append(root_note_path)
            if previous_root is None:
                created += 1
            elif previous_root != root_content:
                updated += 1
            else:
                unchanged += 1

            node_paths = self.plan_tree_paths(target_folder, manifest)
            for node in manifest.nodes:
                note_path = node_paths[node.node_key]
                existing_record = existing_tree["nodes"].get(node.node_key)
                if existing_record is not None and existing_record["path"] != note_path and existing_record["path"].exists():
                    note_path.parent.mkdir(parents=True, exist_ok=True)
                    existing_record["path"].rename(note_path)
                    existing_tree["nodes"][node.node_key]["path"] = note_path

                existing_note = note_path.read_text(encoding="utf-8") if note_path.exists() else None
                previous_contents[note_path] = existing_note
                rendered = self.render_tree_node_note(
                    node,
                    manifest=manifest,
                    note_path=note_path,
                    root_folder=target_folder,
                    source_path=source_path,
                    existing_note=existing_note,
                )
                if existing_note == rendered:
                    unchanged += 1
                else:
                    note_path.parent.mkdir(parents=True, exist_ok=True)
                    self.write_note_atomically(note_path, rendered)
                    self.upsert_note(
                        note_path,
                        rendered,
                        source_path=source_path,
                        extra_metadata={
                            "tree_id": self.tree_id_for(target_folder),
                            "tree_root": self.relative_note_path(root_note_path),
                            "tree_node_key": node.node_key,
                        },
                    )
                    if existing_note is None:
                        created += 1
                    else:
                        updated += 1
                artifacts.append(note_path)
        except Exception:
            for path, previous in previous_contents.items():
                self.rollback_note_write(path, previous)
            raise

        return ProcessResult(
            mode="tree",
            source_path=source_path,
            note_path=root_note_path,
            root_note_path=root_note_path,
            artifacts=artifacts,
            tree_summary={
                "created": created,
                "updated": updated,
                "unchanged": unchanged,
            },
        )

    def plan_tree_manifest(self, raw_text: str, *, tree_title: str) -> TreeManifest:
        planned = self.render_tree_manifest(raw_text, tree_title=tree_title)
        if planned is None:
            planned = self.heuristic_tree_manifest(raw_text, tree_title=tree_title)
        return self.validate_tree_manifest(planned, raw_text=raw_text, tree_title=tree_title)

    def render_tree_manifest(self, raw_text: str, *, tree_title: str) -> TreeManifest | None:
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", TREE_MANIFEST_SYSTEM_PROMPT),
                ("human", TREE_MANIFEST_USER_PROMPT),
            ]
        )
        chain = prompt | self.llm | StrOutputParser()
        response = chain.invoke(
            {
                "tree_title": tree_title,
                "detail_mode": self.settings.detail_mode,
                "raw_text": raw_text,
            }
        )
        cleaned = self.clean_model_output(response)
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            return None

        nodes: list[TreeNodePlan] = []
        raw_nodes = payload.get("nodes") if isinstance(payload, dict) else None
        if not isinstance(raw_nodes, list):
            return None

        for item in raw_nodes:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            parent_title = str(item.get("parent_title") or "").strip() or None
            raw_cross_links = item.get("cross_links", [])
            if not isinstance(raw_cross_links, list):
                raw_cross_links = []
            nodes.append(
                TreeNodePlan(
                    node_key="",
                    title=title,
                    parent_key=parent_title,
                    summary=str(item.get("summary") or "").strip(),
                    raw_basis=str(item.get("raw_basis") or "").strip(),
                    cross_links=[
                        str(value).strip()
                        for value in raw_cross_links
                        if str(value).strip()
                    ],
                )
            )

        if not nodes:
            return None

        return TreeManifest(
            tree_title=str(payload.get("tree_title") or tree_title).strip() or tree_title,
            root_summary=str(payload.get("root_summary") or "").strip(),
            nodes=nodes,
        )

    def heuristic_tree_manifest(self, raw_text: str, *, tree_title: str) -> TreeManifest:
        heading_matches = list(re.finditer(r"^(#{1,3})\s+(.+?)\s*$", raw_text, re.MULTILINE))
        nodes: list[TreeNodePlan] = []

        if heading_matches:
            for index, match in enumerate(heading_matches[:MAX_TREE_NOTES]):
                start = match.end()
                end = heading_matches[index + 1].start() if index + 1 < len(heading_matches) else len(raw_text)
                basis = raw_text[start:end].strip()
                title = match.group(2).strip()
                if not title:
                    continue
                parent_key = nodes[-1].title if match.group(1) == "###" and nodes else None
                nodes.append(
                    TreeNodePlan(
                        node_key="",
                        title=title,
                        parent_key=parent_key,
                        summary=self.compact_excerpt(basis or title, max_length=220),
                        raw_basis=basis or title,
                    )
                )

        if not nodes:
            chunks = [chunk.strip() for chunk in self._splitter.split_text(raw_text) if chunk.strip()]
            for index, chunk in enumerate(chunks[: min(3, MAX_TREE_NOTES)]):
                nodes.append(
                    TreeNodePlan(
                        node_key="",
                        title=f"{tree_title} Part {index + 1}" if len(chunks) > 1 else tree_title,
                        summary=self.compact_excerpt(chunk, max_length=220),
                        raw_basis=chunk,
                    )
                )

        return TreeManifest(
            tree_title=tree_title,
            root_summary=self.compact_excerpt(raw_text, max_length=260),
            nodes=nodes[:MAX_TREE_NOTES],
        )

    def validate_tree_manifest(
        self,
        manifest: TreeManifest,
        *,
        raw_text: str,
        tree_title: str,
    ) -> TreeManifest:
        nodes: list[TreeNodePlan] = []
        seen_keys: dict[str, int] = {}
        title_to_key: dict[str, str] = {}

        for raw_node in manifest.nodes[:MAX_TREE_NOTES]:
            title = raw_node.title.strip()
            if not title:
                continue

            base_key = self.slugify_title(title) or f"node-{len(nodes) + 1}"
            suffix = seen_keys.get(base_key, 0)
            seen_keys[base_key] = suffix + 1
            node_key = base_key if suffix == 0 else f"{base_key}-{suffix + 1}"
            title_to_key[title] = node_key

            nodes.append(
                TreeNodePlan(
                    node_key=node_key,
                    title=title,
                    parent_key=raw_node.parent_key.strip() if raw_node.parent_key else None,
                    summary=raw_node.summary.strip() or self.compact_excerpt(raw_node.raw_basis or title, max_length=220),
                    raw_basis=raw_node.raw_basis.strip() or title,
                    cross_links=[link.strip() for link in raw_node.cross_links if link.strip()],
                )
            )

        if not nodes:
            nodes.append(
                TreeNodePlan(
                    node_key=self.slugify_title(tree_title) or "overview",
                    title=tree_title,
                    summary=self.compact_excerpt(raw_text, max_length=220),
                    raw_basis=raw_text,
                )
            )

        for node in nodes:
            if node.parent_key:
                node.parent_key = title_to_key.get(node.parent_key, self.slugify_title(node.parent_key))
                if node.parent_key == node.node_key:
                    node.parent_key = None
            node.cross_links = [
                title_to_key.get(link, self.slugify_title(link))
                for link in node.cross_links
                if title_to_key.get(link, self.slugify_title(link)) and link.strip()
            ]

        node_keys = {node.node_key for node in nodes}
        for node in nodes:
            if node.parent_key not in node_keys:
                node.parent_key = None
            node.cross_links = [
                key for key in self._dedupe(node.cross_links) if key in node_keys and key != node.node_key
            ]

        depths: dict[str, int] = {}

        def depth_for(node: TreeNodePlan) -> int:
            if node.node_key in depths:
                return depths[node.node_key]
            if not node.parent_key:
                depths[node.node_key] = 1
                return 1
            parent = next((item for item in nodes if item.node_key == node.parent_key), None)
            if parent is None:
                depths[node.node_key] = 1
                node.parent_key = None
                return 1
            parent_depth = depth_for(parent)
            if parent_depth >= MAX_TREE_DEPTH:
                node.parent_key = None
                depths[node.node_key] = 1
                return 1
            depths[node.node_key] = parent_depth + 1
            return depths[node.node_key]

        for node in nodes:
            depth_for(node)

        root_summary = manifest.root_summary.strip() or self.compact_excerpt(raw_text, max_length=260)
        return TreeManifest(
            tree_title=manifest.tree_title.strip() or tree_title,
            root_summary=root_summary,
            nodes=nodes,
        )

    def inspect_existing_tree(self, target_folder: Path) -> dict[str, Any]:
        managed_nodes: dict[str, dict[str, Any]] = {}
        has_unmanaged_markdown = False

        if not target_folder.exists():
            return {"nodes": managed_nodes, "has_unmanaged_markdown": False}

        for candidate in target_folder.rglob("*.md"):
            metadata = self.extract_tree_metadata(candidate.read_text(encoding="utf-8"))
            if metadata is None:
                has_unmanaged_markdown = True
                continue
            managed_nodes[str(metadata.get("node_key") or "")] = {
                "path": candidate,
                "metadata": metadata,
            }

        return {
            "nodes": managed_nodes,
            "has_unmanaged_markdown": has_unmanaged_markdown and bool(managed_nodes or list(target_folder.rglob("*.md"))),
        }

    def plan_tree_paths(self, target_folder: Path, manifest: TreeManifest) -> dict[str, Path]:
        nodes_by_key = {node.node_key: node for node in manifest.nodes}
        paths: dict[str, Path] = {}
        for node in manifest.nodes:
            branch_parts: list[str] = []
            cursor = node.parent_key
            hops = 0
            while cursor and hops < MAX_TREE_DEPTH:
                parent = nodes_by_key.get(cursor)
                if parent is None:
                    break
                branch_parts.insert(0, self.safe_note_name(parent.title))
                cursor = parent.parent_key
                hops += 1
            paths[node.node_key] = target_folder.joinpath(*branch_parts, f"{self.safe_note_name(node.title)}.md")

        return paths

    def render_tree_index_note(
        self,
        manifest: TreeManifest,
        *,
        raw_text: str,
        root_note_path: Path,
        source_path: Path,
    ) -> str:
        node_paths = self.plan_tree_paths(root_note_path.parent, manifest)
        child_nodes = [node for node in manifest.nodes if node.parent_key is None]
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", note_processing_system_prompt(self.settings.detail_mode)),
                ("human", TREE_INDEX_USER_PROMPT),
            ]
        )
        chain = prompt | self.llm | StrOutputParser()
        response = chain.invoke(
            {
                "detail_mode": self.settings.detail_mode,
                "note_title": manifest.tree_title,
                "root_summary": manifest.root_summary,
                "child_titles": ", ".join(node.title for node in child_nodes) or manifest.tree_title,
            }
        )
        content = self.strip_raw_archives(self.clean_model_output(response))
        content = self.ensure_title(content, manifest.tree_title)
        content = self.upsert_auto_links(
            content,
            child_links=[self.path_wikilink(node_paths[node.node_key]) for node in child_nodes],
            see_also_links=[],
        )
        content = self.inject_tree_metadata(
            content,
            tree_id=self.tree_id_for(root_note_path.parent),
            node_key="__root__",
            source_path=source_path,
        )
        raw_archive = self._merge_engine.render_raw_archive(raw_text)
        return f"{content.rstrip()}\n\n{raw_archive}\n"

    def render_tree_node_note(
        self,
        node: TreeNodePlan,
        *,
        manifest: TreeManifest,
        note_path: Path,
        root_folder: Path,
        source_path: Path,
        existing_note: str | None,
    ) -> str:
        nodes_by_key = {item.node_key: item for item in manifest.nodes}
        child_nodes = [item for item in manifest.nodes if item.parent_key == node.node_key]
        cross_nodes = [nodes_by_key[key] for key in node.cross_links if key in nodes_by_key]
        parent_title = nodes_by_key[node.parent_key].title if node.parent_key in nodes_by_key else "Root"

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", note_processing_system_prompt(self.settings.detail_mode)),
                ("human", TREE_NOTE_USER_PROMPT),
            ]
        )
        chain = prompt | self.llm | StrOutputParser()
        response = chain.invoke(
            {
                "detail_mode": self.settings.detail_mode,
                "note_title": node.title,
                "parent_title": parent_title,
                "child_titles": ", ".join(item.title for item in child_nodes) or "None",
                "cross_link_titles": ", ".join(item.title for item in cross_nodes) or "None",
                "summary": node.summary,
                "raw_basis": node.raw_basis,
            }
        )
        draft = self.ensure_title(self.strip_raw_archives(self.clean_model_output(response)), node.title)

        if existing_note is not None:
            cleaned_existing = self.strip_tree_system_sections(existing_note)
            update_fragments = self.render_update_fragments(cleaned_existing, node.raw_basis)
            draft, _report = self._merge_engine.merge(
                cleaned_existing,
                update_fragments,
                [],
                node.raw_basis,
                related_heading=self.related_heading_label(),
            )
            draft = self.ensure_title(self.strip_raw_archives(draft), node.title)

        child_links = self.internal_wikilinks_for_nodes(
            child_nodes,
            manifest=manifest,
            root_folder=root_folder,
        )
        see_also_links = self.internal_wikilinks_for_nodes(
            cross_nodes,
            manifest=manifest,
            root_folder=root_folder,
        )
        content = self.upsert_auto_links(draft, child_links=child_links, see_also_links=see_also_links)
        return self.inject_tree_metadata(
            content,
            tree_id=self.tree_id_for(root_folder),
            node_key=node.node_key,
            source_path=source_path,
        ).rstrip() + "\n"

    def tree_id_for(self, target_folder: Path) -> str:
        relative = self.relative_note_path(target_folder)
        return sha1(relative.encode("utf-8")).hexdigest()[:12]

    def extract_tree_metadata(self, note_text: str) -> dict[str, Any] | None:
        match = KNOT_TREE_META_RE.search(note_text)
        if match is None:
            return None
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def inject_tree_metadata(
        self,
        note_text: str,
        *,
        tree_id: str,
        node_key: str,
        source_path: Path,
    ) -> str:
        cleaned = KNOT_TREE_META_RE.sub("", note_text).strip()
        metadata = json.dumps(
            {
                "tree_id": tree_id,
                "node_key": node_key,
                "source_path": str(source_path.relative_to(self.settings.base_dir)),
                "version": 1,
            },
            separators=(",", ":"),
        )
        first_line, separator, rest = cleaned.partition("\n")
        if first_line.startswith("# "):
            body = f"{first_line}\n<!-- knot:tree {metadata} -->"
            if rest.strip():
                body += f"\n{rest.lstrip()}"
            return body
        return f"<!-- knot:tree {metadata} -->\n{cleaned}"

    def upsert_auto_links(
        self,
        note_text: str,
        *,
        child_links: Sequence[str],
        see_also_links: Sequence[str],
    ) -> str:
        cleaned = AUTO_LINKS_RE.sub("\n", note_text).strip()
        sections: list[str] = []
        if child_links:
            sections.append("## Subtopics\n" + "\n".join(f"- {link}" for link in child_links))
        if see_also_links:
            sections.append("## See Also\n" + "\n".join(f"- {link}" for link in see_also_links))
        if not sections:
            return cleaned + "\n"
        auto_block = (
            "<!-- knot:auto-links:start -->\n"
            + "\n\n".join(sections).strip()
            + "\n<!-- knot:auto-links:end -->"
        )
        return f"{cleaned}\n\n{auto_block}\n"

    def strip_tree_system_sections(self, note_text: str) -> str:
        stripped = self.strip_raw_archives(note_text)
        stripped = self.strip_related_notes(stripped)
        stripped = AUTO_LINKS_RE.sub("\n", stripped)
        stripped = KNOT_TREE_META_RE.sub("", stripped)
        return stripped.strip() + "\n"

    def clean_indexable_text(self, note_text: str) -> str:
        return self.strip_tree_system_sections(note_text).strip()

    def ensure_title(self, note_text: str, title: str) -> str:
        cleaned = note_text.strip()
        if cleaned.startswith("# "):
            return cleaned
        return f"# {title}\n\n{cleaned}".strip()

    def safe_note_name(self, title: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "", title).strip().rstrip(".")
        return cleaned or "Untitled"

    def slugify_title(self, title: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")

    def internal_wikilinks_for_nodes(
        self,
        nodes: Sequence[TreeNodePlan],
        *,
        manifest: TreeManifest,
        root_folder: Path,
    ) -> list[str]:
        paths = self.plan_tree_paths(root_folder, manifest)
        links: list[str] = []
        for node in nodes:
            path = paths.get(node.node_key)
            if path is None:
                continue
            links.append(self.path_wikilink(path))
        return self._dedupe(links)

    def path_wikilink(self, note_path: Path) -> str:
        relative = note_path.relative_to(self.settings.vault_dir)
        without_suffix = str(relative.with_suffix("")).replace("\\", "/")
        return f"[[{without_suffix}]]"

    def _dedupe(self, values: Sequence[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        return deduped

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

    def resolve_folder_path(
        self,
        path: str | Path,
        *,
        default_dir: Path | None = None,
    ) -> Path:
        candidate = Path(path)

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
                    self.clean_indexable_text(candidate_text).lower(),
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

    def upsert_note(
        self,
        note_path: Path,
        note_text: str,
        *,
        source_path: Path,
        extra_metadata: dict[str, Any] | None = None,
    ) -> None:
        embedding_text = self.clean_indexable_text(note_text)
        if not embedding_text:
            embedding_text = note_text

        metadata = {
            "note_path": self.relative_note_path(note_path),
            "note_title": self.infer_note_title(note_text, fallback=note_path.stem),
            "source_path": str(source_path.relative_to(self.settings.base_dir)),
        }
        if extra_metadata:
            metadata.update(extra_metadata)

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
