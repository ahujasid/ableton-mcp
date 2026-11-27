# Integration safety and compatibility

The Remote Script enforces safety for direct TCP callers as well as MCP tools.
It reads `ABLETON_MCP_SAFETY_CONFIG`, or `~/.config/ableton-mcp/safety.json`, on each command. There is no tool that changes this policy.

Configuration accepts only `read_only` (a JSON boolean), `allow` and `saved_set_allow` (objects mapping delete/playback/mixer/routing/structure/edit/undo to JSON booleans), and `deny_commands`/`allow_commands` (lists of known command names). Unknown fields, strings instead of booleans, and strings instead of lists are errors. A malformed configuration or missing explicitly configured file refuses every mutation. Read commands remain available for diagnosis. Denials and disabled categories always win; an allow_commands entry never overrides false.

Without a configuration file, deletion is disabled, other categories are enabled, and deletion in saved or unknown sets is disabled. Enabling deletion requires `allow.delete: true`; saved-set deletion additionally requires `saved_set_allow.delete: true`. Existing public signatures are retained; destructive commands now honor this policy.

New guarded writes use opaque IDs from `get_target_identity` or feature read responses. IDs are local to one script instance, bounded to 4096 retained objects and invalidated on script shutdown. Re-read after an identity mismatch or eviction. Names and indices alone are insufficient for these writes. Live proxy equality is used rather than Python wrapper identity.

Batched setters preflight every field and snapshot before writing, use tolerance for numeric readback, and report rollback failures explicitly. Live does not guarantee transactional property writes; an error with `rollback_complete: false` requires inspecting the set before further edits. Automation replacement, warp/loop writes and render/resampling remain deferred.

Modern MIDI additions validate at most 10000 notes before mutation, accept velocity 0..127, and preserve supported extended values. New notes receive new host IDs; existing note IDs are not reused by additive writes. Legacy writes report unsupported fields. Clip-type support is detected at runtime. Offline compatibility tests are not a claim of verification on any particular Live version.
