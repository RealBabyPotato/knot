from __future__ import annotations

from pathlib import Path

import typer
from dotenv import load_dotenv

from core import KnotProcessor, KnotSettings

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Knot turns rough markdown notes into cleaned, linked vault notes.",
)


@app.command()
def process(
    filename: str = typer.Argument(..., help="Markdown note inside Inbox/ to process."),
    base_dir: Path = typer.Option(
        Path.cwd(),
        "--base-dir",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Project root containing Inbox/, Vault/, and data/chroma/.",
    ),
    model: str = typer.Option(
        "gpt-4o-mini",
        "--model",
        help="Chat model used for the note-cleanup pass.",
    ),
    update_threshold: float = typer.Option(
        0.35,
        "--update-threshold",
        min=0.0,
        help="Maximum Chroma distance for treating a semantic match as an update.",
    ),
) -> None:
    """Process a raw note from Inbox/ into the Vault/."""
    load_dotenv(base_dir / ".env", override=False)

    settings = KnotSettings.from_base_dir(
        base_dir,
        chat_model=model,
        update_distance_threshold=update_threshold,
    )
    processor = KnotProcessor(settings)

    try:
        result = processor.process(filename)
    except Exception as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    relative_note_path = result.note_path.relative_to(base_dir)
    typer.secho(
        f"{result.mode.upper()}: {relative_note_path}",
        fg=typer.colors.GREEN,
    )

    if result.matched_note is not None and result.mode == "update":
        typer.echo(
            "Matched existing note "
            f"({result.matched_note.score:.3f}): "
            f"{result.matched_note.note_path.relative_to(base_dir)}"
        )

    if result.related_links:
        typer.echo("Related: " + ", ".join(f"[[{title}]]" for title in result.related_links))


if __name__ == "__main__":
    app()
