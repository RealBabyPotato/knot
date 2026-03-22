from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from dotenv import load_dotenv

from main import resolve_base_dir
from models import KnotSettings


class ProviderResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_env = os.environ.copy()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._original_env)

    def test_env_provider_beats_default_auto(self) -> None:
        os.environ["KNOT_PROVIDER"] = "google"
        os.environ["OPENAI_API_KEY"] = "sk-openai-present"
        os.environ["GOOGLE_API_KEY"] = "google-key"

        settings = KnotSettings.from_base_dir(Path.cwd(), provider="auto")

        self.assertEqual(settings.provider, "google")

    def test_blank_openai_key_does_not_block_google_auto_detection(self) -> None:
        os.environ.pop("KNOT_PROVIDER", None)
        os.environ["OPENAI_API_KEY"] = "   "
        os.environ["GOOGLE_API_KEY"] = "google-key"

        settings = KnotSettings.from_base_dir(Path.cwd(), provider="auto")

        self.assertEqual(settings.provider, "google")

    def test_resolve_base_dir_finds_nearest_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            nested_dir = project_root / "Inbox" / "nested"
            nested_dir.mkdir(parents=True)
            (project_root / ".env").write_text("KNOT_PROVIDER=google\n", encoding="utf-8")

            resolved = resolve_base_dir(nested_dir)

            self.assertEqual(resolved, project_root.resolve())

    def test_load_dotenv_from_resolved_base_dir_drives_google_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            nested_dir = project_root / "Inbox" / "nested"
            nested_dir.mkdir(parents=True)
            (project_root / ".env").write_text(
                "KNOT_PROVIDER=google\nGOOGLE_API_KEY=google-key\n",
                encoding="utf-8",
            )

            resolved = resolve_base_dir(nested_dir)
            load_dotenv(resolved / ".env", override=False)
            settings = KnotSettings.from_base_dir(resolved, provider="auto")

            self.assertEqual(settings.provider, "google")


if __name__ == "__main__":
    unittest.main()
