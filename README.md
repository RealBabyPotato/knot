# knot

Knot is a local-first Python CLI for turning rough Markdown notes into cleaned, linked vault notes without flattening the author's voice.

## Project Layout

```text
.
├── Inbox/               # raw note drop zone
├── Vault/               # cleaned, linked notes
├── data/
│   └── chroma/          # local Chroma persistence
├── tests/
├── core.py              # processing + Chroma + file merge skeleton
├── main.py              # Typer CLI entrypoint
├── prompts.py           # exact LLM system/user prompts
├── .env.example
├── pyproject.toml       # exposes the `knot` console script
└── requirements.txt
```

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
cp .env.example .env
```

## Usage

Drop a raw Markdown file into `Inbox/`, then run:

```bash
knot process lecture-01.md
```

The current scaffold does this:

- reads the raw note from `Inbox/`
- checks `Vault/` for an exact filename match first, then falls back to Chroma similarity search
- sends the raw note through a strict anti-hallucination prompt
- adds up to 3 related `[[WikiLinks]]`
- writes or updates the target note in `Vault/`
- upserts the finalized note back into local Chroma

## Notes

- The update path is intentionally append-only. New content becomes an `## Update ...` block instead of rewriting old sections.
- Related note links are inserted before the newest raw archive so the unedited source text still stays at the bottom of the newest write.
- Tune `KNOT_UPDATE_DISTANCE_THRESHOLD` once you have a real note corpus and can inspect match quality.
