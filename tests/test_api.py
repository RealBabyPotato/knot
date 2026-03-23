from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from api import KnotWorkspace, MovePayload, NotePayload, build_default_output_folder
from models import KnotSettings


class ApiWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_env = os.environ.copy()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._original_env)

    def test_save_read_and_list_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            (base_dir / "Inbox").mkdir()
            (base_dir / "Vault").mkdir()
            (base_dir / "data" / "chroma").mkdir(parents=True)

            workspace = KnotWorkspace(base_dir)
            saved = workspace.save_note(
                NotePayload(
                    path="folder/test-note.md",
                    title="Test Note",
                    content="# Test Note\n\nHello from Knot.\n",
                ),
                must_not_exist=True,
            )

            self.assertEqual(saved["path"], "folder/test-note.md")

            read_back = workspace.read_note("folder/test-note.md")
            self.assertIn("Hello from Knot.", read_back["content"])

            notes = workspace.list_notes()
            self.assertEqual(len(notes), 1)
            self.assertEqual(notes[0]["path"], "folder/test-note.md")
            self.assertEqual(notes[0]["title"], "Test Note")

    def test_move_note_updates_path_and_prunes_old_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            (base_dir / "Inbox").mkdir()
            (base_dir / "Vault").mkdir()
            (base_dir / "data" / "chroma").mkdir(parents=True)

            workspace = KnotWorkspace(base_dir)
            workspace.save_note(
                NotePayload(
                    path="folder/test-note.md",
                    title="Test Note",
                    content="# Test Note\n\nHello from Knot.\n",
                ),
                must_not_exist=True,
            )

            moved = workspace.move_note(
                MovePayload(
                    source_path="folder/test-note.md",
                    destination_path="archive/renamed-note.md",
                )
            )

            self.assertEqual(moved["path"], "archive/renamed-note.md")
            self.assertFalse((base_dir / "Vault" / "folder").exists())
            self.assertTrue((base_dir / "Vault" / "archive" / "renamed-note.md").exists())

    def test_move_note_accepts_rename_payload_and_reuses_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            (base_dir / "Inbox").mkdir()
            (base_dir / "Vault").mkdir()
            (base_dir / "data" / "chroma").mkdir(parents=True)

            workspace = KnotWorkspace(base_dir)
            workspace.save_note(
                NotePayload(
                    path="folder/test-note.md",
                    title="Test Note",
                    content="# Test Note\n\nHello from Knot.\n",
                ),
                must_not_exist=True,
            )

            moved = workspace.move_note(
                MovePayload(
                    path="folder/test-note.md",
                    title="renamed-note",
                )
            )

            self.assertEqual(moved["path"], "folder/renamed-note.md")
            self.assertFalse((base_dir / "Vault" / "folder" / "test-note.md").exists())
            self.assertTrue((base_dir / "Vault" / "folder" / "renamed-note.md").exists())

    def test_rejects_paths_outside_vault(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            (base_dir / "Inbox").mkdir()
            (base_dir / "Vault").mkdir()
            (base_dir / "data" / "chroma").mkdir(parents=True)

            workspace = KnotWorkspace(base_dir)

            with self.assertRaises(HTTPException):
                workspace.resolve_note_path("../escape.md")

    def test_build_default_output_folder_uses_named_folder(self) -> None:
        payload = NotePayload(
            path="MathLectures.md",
            content="# Math Lectures",
            output_mode="linked_tree",
        )

        self.assertEqual(build_default_output_folder(payload), "knot-MathLectures")

    def test_output_mode_normalization_accepts_linked_tree_alias(self) -> None:
        self.assertEqual(KnotSettings.normalize_output_mode("linked-tree"), "linked_tree")


if __name__ == "__main__":
    unittest.main()
