# Tests

Server-side unit tests for the MCP tools. They mock the Ableton socket
connection, so they run anywhere — no Ableton, no network, deterministic.

## Run

From the repo root:

```bash
# quickest — pytest pulled in just for this run, no pyproject change:
uv run --with pytest pytest -v

# or if you've added pytest as a dev dependency (see below):
uv run pytest -v

# or in any venv that already has the server's deps + pytest:
python -m pytest -v
```

## What's covered

`tests/test_get_notes_from_clip.py` exercises the real
`MCP_Server.server` tool functions with a `FakeConnection` substituted for the
live Ableton link:

- `get_notes_from_clip` sends the correct command and params
- output header (clip name / note count / length) and JSON body are correct
- empty clip returns zero notes, not an error
- a connection exception is caught and reported, not raised
- a response missing metadata (older Remote Script) degrades gracefully
- **round-trip:** read output feeds straight into `add_notes_to_clip`, and a
  read -> transpose -> write cycle yields the expected pitches
- `add_notes_to_clip` regression: still forwards track/clip/notes

## What these tests do NOT cover

The actual Live Object Model calls (`get_notes_extended`, `clip.is_midi_clip`,
`set_notes`) only run inside Ableton's embedded Python. These tests stop at the
socket boundary. The Live-side behaviour is verified with the manual
integration checklist (run once against a real Set).

## Adding pytest as a dev dependency (optional, for CI)

In `pyproject.toml`:

```toml
[dependency-groups]
dev = ["pytest>=8"]
```

Then `uv sync --group dev` and `uv run pytest -v`.
