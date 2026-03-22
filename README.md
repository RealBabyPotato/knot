# knot

Knot is a local-first Markdown note toolchain. It now ships as both:

- a Python CLI for batch processing raw notes
- a Tauri desktop app for manual note editing, saving, previewing, and on-demand Knot formatting

The processing core stays local: notes live on disk, Chroma persists locally, and the formatter preserves the author's voice instead of flattening it into generic AI copy.

Knot supports both OpenAI and Gemini through LangChain. If `.env` sets `KNOT_PROVIDER=google` or a Google API key is present without an OpenAI key, Knot resolves to Google automatically.

## Project Layout

```text
.
├── Inbox/               # raw note drop zone
├── Vault/               # cleaned, linked notes
├── desktop/             # Tauri + React desktop app
├── data/
│   └── chroma/          # local Chroma persistence
├── tests/
├── api.py               # FastAPI backend for the desktop app
├── core.py              # processing + Chroma orchestration
├── models.py            # shared agent/data contracts
├── librarian.py         # deterministic section-aware merge engine
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
cd desktop && npm install
```

For Gemini, set `GOOGLE_API_KEY` in `.env`.

## Desktop App

Run the Tauri app from the desktop workspace:

```bash
cd desktop
npm run tauri:dev
```

That starts the Vite frontend and the Tauri shell. The shell launches the local FastAPI backend automatically and points it at the same project `Vault/`, `Inbox/`, and `data/chroma/`.

The desktop app is intentionally manual:

- notes are plain `.md` files in `Vault/`
- you save explicitly
- you run Knot explicitly
- there is no watch mode

If you want to run the backend without Tauri during UI work:

```bash
source .venv/bin/activate
python -m uvicorn api:app --host 127.0.0.1 --port 7768 --reload
cd desktop
VITE_KNOT_API_URL=http://127.0.0.1:7768 npm run dev
```

## CLI

Drop a raw Markdown file into `Inbox/`, then run:

```bash
knot lecture-01.md
```

If you want to force Gemini from the CLI instead of `.env`:

```bash
knot lecture-01.md --provider google
```

If you want a simple beautify-only pass:

```bash
knot lecture-01.md --detail minimal
```

If you want Knot to add a bit of explanatory context:

```bash
knot lecture-01.md --detail enriched
```

If you want the formatted note written somewhere other than `Vault/`:

```bash
knot lecture-01.md --output-dir NotesOut
```

The current scaffold does this:

- reads the raw note from `Inbox/`
- writes the formatted markdown into `Vault/` by default, or another folder passed with `--output-dir`
- checks the output folder for an exact filename match first, then falls back to Chroma similarity search
- supports `minimal` detail for pure beautification and `enriched` detail for light explanatory expansion
- preserves the raw note's own H1 title when present instead of forcing the filename into the note body
- chunks update input and merges it back into matching sections instead of only appending a freeform block
- adds related `[[WikiLinks]]` only in `enriched` mode
- writes or updates the target note in the configured output folder
- shows a live CLI spinner during slow model/vector phases
- upserts the finalized note back into local Chroma

## Notes

- The update path is intentionally append-only. New content becomes an `## Update ...` block instead of rewriting old sections.
- Related note links are inserted before the newest raw archive so the unedited source text still stays at the bottom of the newest write.
- Tune `KNOT_UPDATE_DISTANCE_THRESHOLD` once you have a real note corpus and can inspect match quality.
- The desktop app uses the same local-first note store and processing core as the CLI; it just adds a manual editor, preview, CRUD, and on-demand formatting layer.
