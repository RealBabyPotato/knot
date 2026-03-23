from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal


AgentMode = Literal["create", "update"]
SegmentKind = Literal[
    "heading",
    "bullet",
    "paragraph",
    "aside",
    "todo",
    "note",
    "reminder",
    "unknown",
]
LockReason = Literal[
    "slang",
    "profanity",
    "abbrev",
    "casing",
    "emphasis",
    "quoted_phrase",
]
DiffOperation = Literal[
    "group_under_heading",
    "wrap_list",
    "move_segment",
    "lift_action_item",
    "verbatim_copy",
]
NovelTokenClass = Literal["markdown_syntax", "section_label", "timestamp"]
MergeDisposition = Literal["merged", "appended"]
DetailMode = Literal["minimal", "enriched"]
OutputMode = Literal["single_note", "linked_tree"]


@dataclass(slots=True)
class KnotSettings:
    base_dir: Path
    inbox_dir: Path
    vault_dir: Path
    chroma_dir: Path
    provider: str = "openai"
    collection_name: str = "knot-notes"
    chat_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    update_distance_threshold: float = 0.35
    chunk_size: int = 1200
    chunk_overlap: int = 150
    detail_mode: DetailMode = "minimal"
    output_mode: OutputMode = "single_note"

    @classmethod
    def from_base_dir(
        cls,
        base_dir: Path,
        *,
        provider: str | None = None,
        chat_model: str | None = None,
        update_distance_threshold: float | None = None,
        output_dir: Path | None = None,
        detail_mode: str | None = None,
        output_mode: str | None = None,
    ) -> "KnotSettings":
        base_dir = base_dir.resolve()
        configured_provider = cls.configured_env("KNOT_PROVIDER")
        requested_provider = cls.normalize_config_value(provider)
        provider_hint = (
            configured_provider
            if requested_provider in {None, "auto"}
            else requested_provider
        )
        resolved_provider = cls.normalize_provider(provider_hint)
        chroma_dir = Path(os.getenv("KNOT_CHROMA_DIR", "data/chroma"))
        if not chroma_dir.is_absolute():
            chroma_dir = base_dir / chroma_dir
        resolved_output_dir = output_dir or Path(os.getenv("KNOT_OUTPUT_DIR", "Vault"))
        if not resolved_output_dir.is_absolute():
            resolved_output_dir = base_dir / resolved_output_dir
        resolved_detail_mode = cls.normalize_detail_mode(
            detail_mode or os.getenv("KNOT_DETAIL_MODE")
        )
        resolved_output_mode = cls.normalize_output_mode(
            output_mode or os.getenv("KNOT_OUTPUT_MODE")
        )

        return cls(
            base_dir=base_dir,
            inbox_dir=base_dir / "Inbox",
            vault_dir=resolved_output_dir,
            chroma_dir=chroma_dir,
            provider=resolved_provider,
            collection_name=os.getenv("KNOT_COLLECTION_NAME", "knot-notes"),
            chat_model=chat_model
            or os.getenv("KNOT_MODEL")
            or cls.default_chat_model(resolved_provider),
            embedding_model=os.getenv(
                "KNOT_EMBEDDING_MODEL",
                cls.default_embedding_model(resolved_provider),
            ),
            update_distance_threshold=update_distance_threshold
            if update_distance_threshold is not None
            else float(os.getenv("KNOT_UPDATE_DISTANCE_THRESHOLD", "0.35")),
            detail_mode=resolved_detail_mode,
            output_mode=resolved_output_mode,
        )

    @staticmethod
    def normalize_provider(provider: str | None) -> str:
        normalized = KnotSettings.normalize_config_value(provider)
        if normalized is None or normalized == "auto":
            if KnotSettings.google_api_key() and not KnotSettings.configured_env(
                "OPENAI_API_KEY"
            ):
                return "google"
            return "openai"

        if normalized in {"google", "gemini"}:
            return "google"
        if normalized == "openai":
            return "openai"
        raise ValueError("Unsupported provider. Use one of: auto, openai, google, gemini.")

    @staticmethod
    def google_api_key() -> str | None:
        return KnotSettings.configured_env("GOOGLE_API_KEY")

    @staticmethod
    def configured_env(name: str) -> str | None:
        return KnotSettings.normalize_config_value(os.getenv(name))

    @staticmethod
    def normalize_config_value(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def default_chat_model(provider: str) -> str:
        if provider == "google":
            return "gemini-2.5-flash"
        return "gpt-4o-mini"

    @staticmethod
    def default_embedding_model(provider: str) -> str:
        if provider == "google":
            return "models/gemini-embedding-001"
        return "text-embedding-3-small"

    @staticmethod
    def normalize_detail_mode(detail_mode: str | None) -> DetailMode:
        if detail_mode is None:
            return "minimal"

        normalized = detail_mode.strip().lower()
        if normalized in {"none", "minimal", "clean"}:
            return "minimal"
        if normalized in {"medium", "enriched", "contextual", "study"}:
            return "enriched"
        raise ValueError(
            "Unsupported detail mode. Use one of: minimal, enriched, none, medium."
        )

    @staticmethod
    def normalize_output_mode(output_mode: str | None) -> OutputMode:
        if output_mode is None:
            return "single_note"

        normalized = output_mode.strip().lower().replace("-", "_")
        if normalized in {"single", "single_note", "singlefile", "single_file"}:
            return "single_note"
        if normalized in {"tree", "linked_tree", "linked_folder", "folder"}:
            return "linked_tree"
        raise ValueError(
            "Unsupported output mode. Use one of: single_note, linked_tree."
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
    root_note_path: Path | None = None
    artifacts: list[Path] = field(default_factory=list)
    tree_summary: dict[str, int] | None = None


@dataclass(slots=True)
class SourceSegment:
    segment_id: str
    char_start: int
    char_end: int
    kind: SegmentKind
    text: str
    voice_locked: bool = False
    lock_reason: LockReason | None = None


@dataclass(slots=True)
class BeautificationConstraints:
    ban_jargon: bool = True
    ban_register_shift: bool = True
    locked_phrases: list[str] = field(default_factory=list)
    forbidden_substitutions: list[str] = field(default_factory=list)
    allowed_novel_token_classes: list[NovelTokenClass] = field(
        default_factory=lambda: ["markdown_syntax", "section_label", "timestamp"]
    )


@dataclass(slots=True)
class OutputBlock:
    block_id: str
    markdown: str
    derived_from_segment_ids: list[str] = field(default_factory=list)
    novel_token_classes: list[NovelTokenClass] = field(default_factory=list)


@dataclass(slots=True)
class DiffOp:
    op: DiffOperation
    source_segment_ids: list[str] = field(default_factory=list)
    target_block_id: str = ""
    introduced_text: str = ""
    introduced_text_class: NovelTokenClass | None = None


@dataclass(slots=True)
class NoteSection:
    heading: str
    content: str


@dataclass(slots=True)
class WikiLinkCandidate:
    title: str
    note_path: str
    score: float
    source: Literal["vector", "fallback"]


@dataclass(slots=True)
class MergeAction:
    heading: str
    disposition: MergeDisposition


@dataclass(slots=True)
class MergeReport:
    actions: list[MergeAction] = field(default_factory=list)
    raw_archives_preserved: int = 0
    raw_archives_added: int = 0
    wikilinks_selected: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AgentEnvelope:
    contract_version: str
    mode: AgentMode
    note_title: str
    source_path: str
    raw_text: str
    raw_sha256: str
    segments: list[SourceSegment] = field(default_factory=list)
    constraints: BeautificationConstraints = field(
        default_factory=BeautificationConstraints
    )
    output_blocks: list[OutputBlock] = field(default_factory=list)
    diff_ops: list[DiffOp] = field(default_factory=list)


@dataclass(slots=True)
class TreeNodePlan:
    node_key: str
    title: str
    parent_key: str | None = None
    summary: str = ""
    raw_basis: str = ""
    cross_links: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TreeManifest:
    tree_title: str
    root_summary: str
    nodes: list[TreeNodePlan] = field(default_factory=list)
    related_links: list[WikiLinkCandidate] = field(default_factory=list)
    merge_report: MergeReport | None = None
    raw_archive_text: str = ""

    def as_dict(self) -> dict[str, object]:
        return asdict(self)
