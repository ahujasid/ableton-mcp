# Production control MVP

This fork keeps the existing TCP bridge and Remote Script as the owners of Live
mutations. It adds only the controls required to inspect production state,
compare Session variants, and update a Live 12 set with fail-closed identity
checks.

## Reproducible installation

Use a reviewed commit from `feat/production-control-mvp`; do not install from an
unversioned package index:

```bash
git fetch origin
git checkout <validated-commit>
uv venv --python 3.13 .venv
uv sync --locked --no-install-project
uv pip install --python .venv/bin/python --no-deps .
.venv/bin/python -c "import importlib.metadata as m; assert m.version('mcp') == '1.4.0'"
```

`pyproject.toml` and `uv.lock` pin `mcp[cli]==1.4.0`. The generated executable
must start with the checkout-local Python path:

```bash
head -n 1 .venv/bin/ableton-mcp
```

Deploy the Remote Script from this checkout, then compare hashes:

```bash
cp AbletonMCP_Remote_Script/__init__.py \
  "$HOME/Music/Ableton/User Library/Remote Scripts/AbletonMCP/__init__.py"
shasum -a 256 AbletonMCP_Remote_Script/__init__.py \
  "$HOME/Music/Ableton/User Library/Remote Scripts/AbletonMCP/__init__.py"
```

Reload the `AbletonMCP` control surface after deployment. Save a valuable set
before a reload and never use production clips as test fixtures.

## Safety contract

Mutations resolve their target again inside Live's main thread. Track, clip,
device, chain, parameter, and Arrangement selectors pair positional indices with
expected names or class names. An identity mismatch, stale current value, or
ambiguous Arrangement match returns a structured error without modifying Live.

Use `dry_run=true` for preflight. `overwrite` is false by default. Batch mixer,
device, and scene duplication operations validate every target before applying
any change. Mutation responses include the resolved target, previous/requested/
applied state, and Live's parameter metadata where it is available.

## Command matrix

| Area | Read | Guarded mutation |
| --- | --- | --- |
| Runtime | `get_capabilities` | — |
| Mixer | `get_mixer_parameters` | `set_mixer_parameter`, `set_mixer_parameters` |
| Devices and racks | `get_device_parameters` | `set_device_parameter`, `set_device_parameters` |
| MIDI clips | `get_clip_notes`, `get_clip_properties` | `replace_clip_notes`, `clear_clip_notes`, `set_clip_loop`, `delete_session_clip` |
| Session variants | existing `get_track_info` | `duplicate_session_clip`, `duplicate_session_scene_clips`, `fire_scene`, `stop_all_clips`, `back_to_arrangement` |
| Arrangement | reinforced `get_arrangement_clips` | reinforced `duplicate_session_clip_to_arrangement`, `delete_arrangement_clip` |
| Levels | `get_output_meter_levels` | — |

Minimal guarded parameter update:

```json
{
  "track_index": 1,
  "expected_track_name": "Bass",
  "device_path": [
    {"index": 0, "expected_name": "Instrument", "expected_class_name": "InstrumentDevice"}
  ],
  "parameter_index": 3,
  "expected_parameter_name": "Filter Freq",
  "expected_current_value": 0.5,
  "value": 0.51,
  "tolerance": 0.000001,
  "dry_run": true
}
```

## Deliberately unsupported

- Arrangement replace and trim are not exposed: Live 12.2.1 does not provide a
  recoverable transaction for delete-first replacement or reliable trimming.
- Occupied Session destinations are not overwritten. Live's duplicate operation
  has no recoverable overwrite transaction; choose an empty destination.
- Clip envelopes are not included. Their safe replacement contract would expand
  this MVP beyond the validated production controls.
- Export, save dialogs, plugin UIs, licensing, auditory evaluation, and generic
  macOS/UI automation remain manual.

## Telemetry

Telemetry remains enabled, matching ableton-mcp 1.2.0. The source checkout now
contains an environment-backed `MCP_Server.config`; upstream omitted this file
and its source collector silently fails to initialize. Configure
`ABLETON_MCP_TELEMETRY_SUPABASE_URL` and
`ABLETON_MCP_TELEMETRY_SUPABASE_ANON_KEY` only in the local MCP environment.
The fork never stores the third-party endpoint credential.

All commands added by this MVP use `telemetry_tool`, not rich telemetry. With
the existing consent default they send the anonymous customer/session IDs,
event/tool name, prompt, success, duration, error text, package/platform fields,
and empty metadata. They do not send target indices, names, parameter values,
device paths, or MIDI notes. Existing rich tools are unchanged; notably
`add_notes_to_clip` still captures MIDI note content.

## Rollback

Before deployment, copy the current Codex config, generated executable, venv
metadata, and deployed Remote Script to a private rollback directory. To roll
back, restore the prior Remote Script and Codex config, then reload the Ableton
control surface. Do not treat `site-packages` or the User Library copy as source.

The Python SDK tag `mcp==1.4.0` contains a client-side stdio mismatch: its
`ClientSession` consumes `MessageFrame`, while its `stdio_client` emits a bare
`JSONRPCMessage`. This does not affect the FastMCP server transport. Validate
the server with a conforming MCP client or raw JSON-RPC framing rather than
patching generated or installed SDK files.
