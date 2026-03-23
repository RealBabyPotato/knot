from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from api import create_app
from models import NoteMatch, ProcessResult


class FakeProcessor:
    def __init__(self, base_dir: Path) -> None:
        self.settings = SimpleNamespace(
            base_dir=base_dir,
            inbox_dir=base_dir / "Inbox",
            vault_dir=base_dir / "Vault",
            chroma_dir=base_dir / "data" / "chroma",
            provider="openai",
            collection_name="knot-notes",
            chat_model="gpt-4o-mini",
            embedding_model="text-embedding-3-small",
            detail_mode="minimal",
            output_mode="single_note",
            update_distance_threshold=0.35,
        )
        self.settings.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.settings.vault_dir.mkdir(parents=True, exist_ok=True)
        self.settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.process_calls: list[dict[str, object]] = []

    def relative_note_path(self, note_path: Path) -> str:
        return str(note_path.resolve().relative_to(self.settings.base_dir))

    def infer_note_title(self, raw_text: str, *, fallback: str) -> str:
        for line in raw_text.splitlines():
            if line.startswith("# "):
                return line.removeprefix("# ").strip() or fallback
        return fallback

    def list_notes(
        self,
        *,
        include_vault: bool = True,
        include_inbox: bool = True,
    ) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        roots = []
        if include_vault:
            roots.append(("vault", self.settings.vault_dir))
        if include_inbox:
            roots.append(("inbox", self.settings.inbox_dir))

        for scope, root in roots:
            for note_path in root.rglob("*.md"):
                content = note_path.read_text(encoding="utf-8")
                records.append(
                    {
                        "path": self.relative_note_path(note_path),
                        "title": self.infer_note_title(content, fallback=note_path.stem),
                        "scope": scope,
                        "modified_at": note_path.stat().st_mtime,
                        "size_bytes": note_path.stat().st_size,
                    }
                )

        records.sort(key=lambda item: item["path"])
        return records

    def save_note(
        self,
        path: Path,
        note_text: str,
        *,
        source_path: Path | None = None,
    ) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(note_text, encoding="utf-8")
        return path

    def delete_note(self, path: Path) -> None:
        if path.exists():
            path.unlink()

    def process_raw_text(
        self,
        raw_text: str,
        *,
        source_path: Path | None = None,
        target_path: Path | None = None,
        note_title: str | None = None,
        output_mode: str | None = None,
        status_callback=None,
    ) -> ProcessResult:
        self.process_calls.append(
            {
                "raw_text": raw_text,
                "source_path": source_path,
                "target_path": target_path,
                "note_title": note_title,
                "output_mode": output_mode,
            }
        )
        if output_mode == "linked_tree":
            if target_path is None:
                target_path = self.settings.vault_dir / "processed" / "index.md"
            target_path.parent.mkdir(parents=True, exist_ok=True)
            child_path = target_path.parent / "Topic One.md"
            child_path.write_text("# Topic One\n\nChild content\n", encoding="utf-8")
            final_note = f"# {note_title or target_path.parent.name}\n\nOverview\n"
            target_path.write_text(final_note, encoding="utf-8")
            return ProcessResult(
                mode="tree",
                source_path=source_path or target_path,
                note_path=target_path,
                root_note_path=target_path,
                artifacts=[target_path, child_path],
                tree_summary={"created": 2, "updated": 0, "unchanged": 0},
            )
        if target_path is None:
            target_path = self.settings.vault_dir / "processed.md"
        target_path.parent.mkdir(parents=True, exist_ok=True)
        title = note_title or self.infer_note_title(raw_text, fallback=target_path.stem)
        final_note = f"# {title}\n\n{raw_text.strip()}\n"
        existing = target_path.exists()
        target_path.write_text(final_note, encoding="utf-8")
        return ProcessResult(
            mode="update" if existing else "create",
            source_path=source_path or target_path,
            note_path=target_path,
            related_links=["Related Note"],
            matched_note=(
                NoteMatch(
                    note_path=target_path,
                    title=title,
                    score=0.0,
                    excerpt="",
                )
                if existing
                else None
            ),
        )


class BackendApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.tmpdir.name)
        self.processor = FakeProcessor(self.base_dir)
        self.client = TestClient(create_app(processor=self.processor))

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_health_and_settings(self) -> None:
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")

        settings = self.client.get("/settings")
        self.assertEqual(settings.status_code, 200)
        self.assertEqual(settings.json()["vault_dir"], str(self.base_dir / "Vault"))

    def test_note_crud_and_listing(self) -> None:
        created = self.client.post(
            "/notes",
            json={
                "path": "Vault/notes/day-one.md",
                "title": "Day One",
                "content": "# Day One\n\nhello world",
            },
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["path"], "Vault/notes/day-one.md")

        notes = self.client.get("/notes")
        self.assertEqual(notes.status_code, 200)
        self.assertTrue(any(item["path"] == "Vault/notes/day-one.md" for item in notes.json()))

        content = self.client.get("/notes/content", params={"path": "Vault/notes/day-one.md"})
        self.assertEqual(content.status_code, 200)
        self.assertIn("hello world", content.json()["content"])

        updated = self.client.put(
            "/notes/content",
            json={
                "path": "Vault/notes/day-one.md",
                "content": "# Day One\n\nupdated content",
            },
        )
        self.assertEqual(updated.status_code, 200)
        self.assertIn("updated content", updated.json()["content"])

        moved = self.client.post(
            "/notes/move",
            json={
                "source_path": "Vault/notes/day-one.md",
                "destination_path": "Vault/archive/day-one-renamed.md",
            },
        )
        self.assertEqual(moved.status_code, 200)
        self.assertEqual(moved.json()["path"], "Vault/archive/day-one-renamed.md")

        deleted = self.client.delete("/notes/content", params={"path": "Vault/archive/day-one-renamed.md"})
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.json()["deleted"])

    def test_rename_alias_accepts_title_payload(self) -> None:
        created = self.client.post(
            "/notes",
            json={
                "path": "Vault/notes/day-one.md",
                "title": "Day One",
                "content": "# Day One\n\nhello world",
            },
        )
        self.assertEqual(created.status_code, 200)

        renamed = self.client.patch(
            "/notes/rename",
            json={
                "path": "Vault/notes/day-one.md",
                "title": "day-one-renamed",
            },
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()["path"], "Vault/notes/day-one-renamed.md")
        self.assertFalse((self.base_dir / "Vault" / "notes" / "day-one.md").exists())
        self.assertTrue((self.base_dir / "Vault" / "notes" / "day-one-renamed.md").exists())

    def test_manual_knot_process_can_write_to_target_path(self) -> None:
        response = self.client.post(
            "/knot/process",
            json={
                "content": "# Raw Note\n\nfirst line",
                "output_path": "Vault/processed.md",
                "title": "Processed Note",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "create")
        self.assertEqual(payload["note_path"], "Vault/processed.md")
        self.assertIn("first line", payload["content"])
        self.assertEqual(len(self.processor.process_calls), 1)
        self.assertEqual(
            self.processor.process_calls[0]["target_path"],
            self.base_dir / "Vault" / "processed.md",
        )

    def test_knot_process_defaults_to_named_output_folder(self) -> None:
        response = self.client.post(
            "/knot/process",
            json={
                "path": "Vault/source-note.md",
                "content": "# Source Note\n\nfirst line",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["note_path"], "Vault/knot-source-note/source-note.md")
        self.assertEqual(payload["output_folder"], "Vault/knot-source-note")
        self.assertEqual(
            self.processor.process_calls[0]["target_path"],
            self.base_dir / "Vault" / "knot-source-note" / "source-note.md",
        )

    def test_knot_process_can_create_linked_tree_output(self) -> None:
        response = self.client.post(
            "/knot/process",
            json={
                "path": "Vault/math-lectures.md",
                "content": "# Math Lectures\n\nintegrals and derivatives",
                "output_folder": "math-lectures",
                "output_mode": "linked_tree",
                "title": "MathLectures",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "tree")
        self.assertEqual(payload["root_note_path"], "Vault/math-lectures/index.md")
        self.assertIn("Vault/math-lectures/Topic One.md", payload["artifacts"])
        self.assertEqual(payload["tree_summary"]["created"], 2)
        self.assertEqual(
            self.processor.process_calls[0]["target_path"],
            self.base_dir / "Vault" / "math-lectures" / "index.md",
        )
        self.assertEqual(self.processor.process_calls[0]["output_mode"], "linked_tree")


if __name__ == "__main__":
    unittest.main()
