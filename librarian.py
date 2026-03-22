from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

from models import MergeAction, MergeReport, NoteSection

RAW_ARCHIVE_BLOCK_RE = re.compile(
    r"<details>\s*\n<summary>Original Raw Notes</summary>\s*\n\n.*?\n</details>",
    re.DOTALL,
)
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


@dataclass(slots=True)
class ParsedNote:
    title: str
    lead: str
    sections: list[NoteSection]


class SemanticMergeEngine:
    def merge(
        self,
        existing_note: str,
        update_fragments: Sequence[str],
        related_links: Sequence[str],
        raw_text: str,
        related_heading: str = "## Related Notes",
    ) -> tuple[str, MergeReport]:
        title, lead, sections = self.parse_existing_note(existing_note)
        report = MergeReport(
            raw_archives_preserved=len(self.extract_raw_archives(existing_note)),
            raw_archives_added=1,
            wikilinks_selected=list(related_links),
        )
        section_index = {
            self.normalize_heading(section.heading): idx
            for idx, section in enumerate(sections)
        }

        merged_lead = lead
        for fragment in update_fragments:
            parsed_fragment = self.parse_fragment(fragment)
            if parsed_fragment.lead.strip():
                merged_lead = self.merge_lines(merged_lead, parsed_fragment.lead)

            for section in parsed_fragment.sections:
                key = self.normalize_heading(section.heading)
                if key in section_index:
                    idx = section_index[key]
                    sections[idx].content = self.merge_lines(
                        sections[idx].content,
                        section.content,
                    )
                    report.actions.append(
                        MergeAction(heading=sections[idx].heading, disposition="merged")
                    )
                    continue

                section_index[key] = len(sections)
                sections.append(section)
                report.actions.append(
                    MergeAction(heading=section.heading, disposition="appended")
                )

        rendered = self.render_note(
            title=title,
            lead=merged_lead,
            sections=sections,
            related_links=related_links,
            related_heading=related_heading,
            raw_archives=[
                *self.extract_raw_archives(existing_note),
                self.render_raw_archive(raw_text),
            ],
        )
        return rendered, report

    def ensure_exact_wikilinks(
        self,
        titles: Sequence[str],
        fallback_titles: Sequence[str],
        *,
        limit: int = 3,
    ) -> list[str]:
        ordered = self._dedupe_preserve_order(titles)
        fallbacks = [title for title in self._dedupe_preserve_order(fallback_titles) if title not in ordered]

        selected = ordered[:limit]
        for title in fallbacks:
            if len(selected) == limit:
                break
            selected.append(title)

        if selected and len(selected) < limit:
            cursor = 0
            while len(selected) < limit:
                selected.append(selected[cursor % len(selected)])
                cursor += 1

        return selected

    def extract_raw_archives(self, note_text: str) -> list[str]:
        return RAW_ARCHIVE_BLOCK_RE.findall(note_text)

    def strip_raw_archives(self, note_text: str) -> str:
        return RAW_ARCHIVE_BLOCK_RE.sub("", note_text).strip()

    def strip_related_notes(self, note_text: str) -> str:
        lines = note_text.splitlines()
        kept: list[str] = []
        skip = False

        for line in lines:
            if line.startswith("## Related Notes") or line.startswith("### Connections"):
                skip = True
                continue

            if skip and (line.startswith("## ") or line.startswith("### ")):
                skip = False

            if skip:
                continue

            kept.append(line)

        return "\n".join(kept).strip()

    def parse_existing_note(self, note_text: str) -> tuple[str, str, list[NoteSection]]:
        parsed = self.parse_markdown(self.strip_raw_archives(self.strip_related_notes(note_text)))
        title = parsed.title or "Untitled"
        return title, parsed.lead, parsed.sections

    def parse_fragment(self, note_text: str) -> ParsedNote:
        return self.parse_markdown(note_text, allow_missing_title=True)

    def parse_markdown(
        self,
        note_text: str,
        *,
        allow_missing_title: bool = False,
    ) -> ParsedNote:
        cleaned = note_text.strip()
        title = ""
        if cleaned.startswith("# "):
            first_line, _, remainder = cleaned.partition("\n")
            title = first_line.removeprefix("# ").strip()
            cleaned = remainder.strip()
        elif not allow_missing_title:
            raise ValueError("Expected markdown note to start with an H1 title.")

        matches = list(HEADING_RE.finditer(cleaned))
        if not matches:
            return ParsedNote(title=title, lead=cleaned.strip(), sections=[])

        lead = cleaned[: matches[0].start()].strip()
        sections: list[NoteSection] = []

        for index, match in enumerate(matches):
            section_start = match.end()
            section_end = matches[index + 1].start() if index + 1 < len(matches) else len(cleaned)
            content = cleaned[section_start:section_end].strip()
            sections.append(NoteSection(heading=match.group(1).strip(), content=content))

        return ParsedNote(title=title, lead=lead, sections=sections)

    def render_note(
        self,
        *,
        title: str,
        lead: str,
        sections: Sequence[NoteSection],
        related_links: Sequence[str],
        related_heading: str,
        raw_archives: Sequence[str],
    ) -> str:
        parts = [f"# {title}"]
        if lead.strip():
            parts.append(lead.strip())

        for section in sections:
            content = section.content.strip()
            if not content:
                continue
            parts.append(f"## {section.heading}\n{content}")

        if related_links:
            lines = "\n".join(f"- [[{title}]]" for title in related_links)
            parts.append(f"{related_heading}\n{lines}")

        parts.extend(archive.strip() for archive in raw_archives if archive.strip())
        return "\n\n".join(parts).strip() + "\n"

    def render_raw_archive(self, raw_text: str) -> str:
        return (
            "<details>\n"
            "<summary>Original Raw Notes</summary>\n\n"
            f"{raw_text.strip()}\n\n"
            "</details>"
        )

    def merge_lines(self, existing: str, incoming: str) -> str:
        existing_lines = [line.rstrip() for line in existing.splitlines()]
        seen = {
            self.normalize_line(line)
            for line in existing_lines
            if self.normalize_line(line)
        }
        appended = list(existing_lines)

        if incoming.strip() and appended and appended[-1].strip():
            appended.append("")

        for line in incoming.splitlines():
            normalized = self.normalize_line(line)
            if normalized and normalized in seen:
                continue
            if normalized:
                seen.add(normalized)
            appended.append(line.rstrip())

        return "\n".join(self.trim_blank_edges(appended)).strip()

    def normalize_heading(self, heading: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", heading.lower()).strip()

    def normalize_line(self, line: str) -> str:
        return re.sub(r"\s+", " ", line.strip().lower())

    def trim_blank_edges(self, lines: Iterable[str]) -> list[str]:
        items = list(lines)
        while items and not items[0].strip():
            items.pop(0)
        while items and not items[-1].strip():
            items.pop()
        return items

    def _dedupe_preserve_order(self, items: Sequence[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped
