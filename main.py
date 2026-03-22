from __future__ import annotations

import sys
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import KnotProcessor
from models import KnotSettings, ProcessResult

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Knot turns rough markdown notes into cleaned, linked vault notes.",
)
console = Console()


def resolve_base_dir(base_dir: Path) -> Path:
    candidate = base_dir.resolve()
    markers = (".env", "Inbox", "pyproject.toml")

    for current in (candidate, *candidate.parents):
        if any((current / marker).exists() for marker in markers):
            return current

    return candidate


def build_processor(
    *,
    base_dir: Path,
    provider: str,
    model: str | None,
    update_threshold: float,
    output_dir: Path | None,
    detail_mode: str,
) -> KnotProcessor:
    base_dir = resolve_base_dir(base_dir)
    load_dotenv(base_dir / ".env", override=False)
    settings = KnotSettings.from_base_dir(
        base_dir,
        provider=provider,
        chat_model=model,
        update_distance_threshold=update_threshold,
        output_dir=output_dir,
        detail_mode=detail_mode,
    )
    return KnotProcessor(settings)


def process_with_feedback(
    processor: KnotProcessor,
    filename: str,
    *,
    show_spinner: bool,
) -> tuple[ProcessResult, str | None]:
    current_status = "Starting"

    def on_status(message: str) -> None:
        nonlocal current_status
        current_status = message

    if show_spinner and console.is_terminal:
        with console.status(f"[bold cyan]{current_status}[/bold cyan]", spinner="dots12") as status:
            def update_and_render(message: str) -> None:
                on_status(message)
                status.update(f"[bold cyan]{message}[/bold cyan]")

            result = processor.process(filename, status_callback=update_and_render)
        return result, current_status

    result = processor.process(filename, status_callback=on_status)
    return result, current_status


def print_result(result: ProcessResult, *, base_dir: Path) -> None:
    relative_note_path = result.note_path.relative_to(base_dir)
    console.print(f"[green]{result.mode.upper()}[/green] {relative_note_path}")
    console.print(f"Output folder: {result.note_path.parent.relative_to(base_dir)}")

    if result.matched_note is not None and result.mode == "update":
        console.print(
            "Matched existing note "
            f"({result.matched_note.score:.3f}): "
            f"{result.matched_note.note_path.relative_to(base_dir)}"
        )

    if result.related_links:
        console.print("Related: " + ", ".join(f"[[{title}]]" for title in result.related_links))


@app.command()
def process(
    filename: str = typer.Argument(..., help="Markdown note inside Inbox/ to process."),
    base_dir: Path = typer.Option(
        Path.cwd(),
        "--base-dir",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Project root containing Inbox/, an output folder, and data/chroma/.",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Folder where formatted markdown files are written. Defaults to Vault/.",
    ),
    provider: str = typer.Option(
        "auto",
        "--provider",
        help="Model provider: auto, openai, google, or gemini.",
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        help="Chat model used for the note-cleanup pass. Defaults depend on provider.",
    ),
    update_threshold: float = typer.Option(
        0.35,
        "--update-threshold",
        min=0.0,
        help="Maximum Chroma distance for treating a semantic match as an update.",
    ),
    detail: str = typer.Option(
        "minimal",
        "--detail",
        help="Formatting depth: minimal or enriched. `none` and `medium` are also accepted.",
    ),
    no_spinner: bool = typer.Option(
        False,
        "--no-spinner",
        help="Disable the CLI loading spinner.",
    ),
) -> None:
    """Process a raw note from Inbox/ into the configured output folder."""
    processor = build_processor(
        base_dir=base_dir,
        provider=provider,
        model=model,
        update_threshold=update_threshold,
        output_dir=output_dir,
        detail_mode=detail,
    )

    try:
        result, _status = process_with_feedback(
            processor,
            filename,
            show_spinner=not no_spinner,
        )
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    print_result(result, base_dir=base_dir)


if __name__ == "__main__":
    app()
