# Batch Commands and Skills Plugin Design

**Date:** 2026-01-01
**Status:** Approved

## Problem

MCP round-trips are expensive. Each operation (create track, set name, load instrument) requires a full round-trip through the MCP server and TCP socket to Ableton. Building a 4-track template means 12+ sequential calls, which is slow and consumes context window.

## Solution

Two complementary improvements:

1. **`execute_batch` MCP tool** — Execute multiple commands in a single call
2. **Skills plugin** — Pre-built patterns that guide Claude to use batching effectively

---

## Part 1: Batch Command

### Architecture

A single new MCP tool that accepts an array of commands and executes them sequentially within Ableton.

**Request format:**
```json
{
  "commands": [
    {"type": "create_midi_track", "params": {"index": -1}},
    {"type": "set_track_name", "params": {"track_index": 0, "name": "Kick"}},
    {"type": "load_instrument", "params": {"track_index": 0, "uri": "..."}}
  ]
}
```

**Execution flow:**
1. MCP Server receives the batch
2. Validates all commands upfront (correct types, required params)
3. Sends entire batch to Ableton Remote Script via TCP
4. Remote Script executes commands sequentially, stopping on first error
5. Returns indexed results for each executed command

**Why execute in Ableton, not MCP Server:**
By sending the entire batch to Ableton and executing there, we pay the TCP latency once instead of N times.

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Error handling | Fail-fast | Stop at first error, return partial results. Ableton's undo stack provides safety. |
| Validation | Upfront | Validate schema/syntax before executing anything. Runtime errors (invalid track index) caught during execution. |
| Response format | Indexed results | Array matching input order, each with status/result or error. |
| Batchable commands | All commands | Any command that works individually can be batched, including destructive ones. |

### Response Format

**Full success:**
```json
{
  "status": "success",
  "results": [
    {"index": 0, "status": "success", "result": {"track_index": 0}},
    {"index": 1, "status": "success", "result": {}},
    {"index": 2, "status": "success", "result": {}}
  ]
}
```

**Partial failure:**
```json
{
  "status": "partial",
  "results": [
    {"index": 0, "status": "success", "result": {"track_index": 5}},
    {"index": 1, "status": "success", "result": {}},
    {"index": 2, "status": "error", "error": "Track index 99 does not exist"}
  ]
}
```

**Validation error:**
```json
{
  "status": "validation_error",
  "error": "Command at index 2: missing required param 'track_index'"
}
```

### Implementation

**MCP Server (`server.py`):**
```python
@mcp.tool()
async def execute_batch(commands: list[dict]) -> dict:
    """Execute multiple commands in a single batch."""
    # 1. Validate all commands upfront
    for i, cmd in enumerate(commands):
        validate_command(cmd, index=i)  # Raises on invalid

    # 2. Send batch to Ableton
    response = send_command("execute_batch", {"commands": commands})
    return response
```

**Remote Script (`__init__.py`):**
```python
def handle_execute_batch(self, params):
    commands = params.get("commands", [])
    results = []

    for i, cmd in enumerate(commands):
        try:
            handler = self.command_handlers.get(cmd["type"])
            result = handler(cmd.get("params", {}))
            results.append({"index": i, "status": "success", "result": result})
        except Exception as e:
            results.append({"index": i, "status": "error", "error": str(e)})
            return {"status": "partial", "results": results}

    return {"status": "success", "results": results}
```

### Testing

**Unit tests (validation):**
- Valid batch passes validation
- Missing command type → rejected
- Missing required param → rejected with index
- Invalid param type → rejected with details

**Integration tests (with mock):**
- Batch creates multiple tracks in single call
- Batch stops on error, returns partial results
- Empty batch handled appropriately

**Manual testing checklist:**
- Create 4-track template in one batch
- Batch with intentional error mid-way
- Large batch (10+ commands)

---

## Part 2: Skills Plugin

### Directory Structure

```
ableton-mcp/
  .claude-plugin/
    plugin.json
    marketplace.json
  skills/
    create-track-template/
      SKILL.md
    build-drum-pattern/
      SKILL.md
    setup-mixing/
      SKILL.md
```

### Plugin Metadata

**.claude-plugin/plugin.json:**
```json
{
  "name": "ableton-mcp",
  "description": "AI-assisted music production skills for Ableton Live",
  "version": "1.0.0",
  "author": {
    "name": "Josh Delsman"
  },
  "homepage": "https://github.com/voxxit/ableton-mcp",
  "repository": "https://github.com/voxxit/ableton-mcp",
  "license": "MIT",
  "keywords": ["ableton", "music-production", "daw", "midi", "audio"]
}
```

**.claude-plugin/marketplace.json:**
```json
{
  "name": "ableton-mcp-marketplace",
  "description": "Skills for AI-assisted music production in Ableton Live",
  "owner": {
    "name": "Josh Delsman"
  },
  "plugins": [
    {
      "name": "ableton-mcp",
      "description": "AI-assisted music production skills for Ableton Live",
      "version": "1.0.0",
      "source": "./"
    }
  ]
}
```

### Core Skills

**1. create-track-template**

Guide Claude to create multi-track setups efficiently using batching.

```markdown
---
name: create-track-template
description: "Use when creating multiple tracks at once for a project template."
---

When the user asks for a track template:
1. Clarify what tracks they need
2. Build a single execute_batch call
3. Execute once, not individual calls
4. Report results
```

**2. build-drum-pattern**

Guide Claude to add drum hits across multiple clips efficiently.

**3. setup-mixing**

Batch volume, panning, and mute/solo operations.

---

## Part 3: CLAUDE.md Updates

Add to CLAUDE.md:

```markdown
## MCP Design Principles

When designing new MCP tools or working with Ableton:

- **Batch by default** — MCP round-trips are expensive. Use `execute_batch`
  for any operation involving 2+ commands.
- **Minimize context usage** — Each tool call consumes context window.
  One batch call beats many individual calls.
- **Skills guide usage** — Check the `skills/` directory for pre-built
  patterns like track templates and drum programming.
- **Test reliability** — All batched operations must have integration tests
  covering success, partial failure, and validation errors.

## Plugin Structure

This repository includes a Claude Code plugin with Ableton-specific skills:

- `create-track-template` — Multi-track setup with batching
- `build-drum-pattern` — Efficient MIDI note placement
- `setup-mixing` — Batch volume/pan/mute operations

Install via: `claude plugins add github:voxxit/ableton-mcp`
```

---

## Implementation Order

1. Add `execute_batch` to MCP server with validation
2. Add `execute_batch` handler to Remote Script
3. Write tests (unit + integration)
4. Create `.claude-plugin/` directory with metadata
5. Create initial skills (`create-track-template`)
6. Update CLAUDE.md with design principles
7. Test end-to-end with real Ableton

## Batch Size Recommendation

Soft limit of ~50 commands per batch. Not enforced, but recommended to avoid TCP timeout issues.
