---
phase: 01-foundation-repair
plan: 02
subsystem: infra
tags: [socket-protocol, length-prefix-framing, struct, threading, concurrency]

# Dependency graph
requires:
  - phase: 01-foundation-repair
    provides: "Python 3 cleaned source files, pytest infrastructure"
provides:
  - "Length-prefix framing protocol on both sides of socket (struct.pack/unpack >I)"
  - "Thread-safe connection access via threading.Lock"
  - "Ping-based liveness check replacing sendall(b'')"
  - "Timeout constants for read/write/browser/ping operations"
affects: [01-foundation-repair, 02-infrastructure-refactor]

# Tech tracking
tech-stack:
  added: [struct (stdlib)]
  patterns: [length-prefix framing, threading.Lock for global resource protection, recv_exact loop]

key-files:
  created:
    - tests/test_protocol.py
    - tests/test_connection.py
  modified:
    - AbletonMCP_Remote_Script/__init__.py
    - MCP_Server/server.py

key-decisions:
  - "Protocol functions defined as standalone module-level functions (not methods) for reuse"
  - "Timeout constants as module-level frozensets for command categorization"
  - "Ping command returns {pong: true, version: '1.0'} for future version negotiation"

patterns-established:
  - "4-byte big-endian length prefix for all socket messages (struct.pack('>I', len))"
  - "recv_exact loop pattern for guaranteed byte count reads"
  - "threading.Lock wrapping all global connection access"
  - "Command-specific timeouts: READ=10s, WRITE=15s, BROWSER=30s, PING=5s"

requirements-completed: [FNDN-03, FNDN-04]

# Metrics
duration: 4min
completed: 2026-03-13
---

# Phase 1 Plan 02: Protocol & Concurrency Summary

**Length-prefix framing with struct.pack/unpack replacing O(n^2) JSON re-parsing, threading.Lock for connection safety, and ping-based liveness replacing sendall(b'')**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-13T12:46:10Z
- **Completed:** 2026-03-13T12:50:10Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Replaced O(n^2) JSON accumulation/re-parsing with O(n) length-prefix framing on both socket endpoints
- Added threading.Lock (_connection_lock) protecting all access to _ableton_connection global
- Removed both time.sleep(0.1) calls from send_command -- 200ms artificial latency eliminated
- Replaced sendall(b'') no-op liveness test with real ping command + handler
- Added timeout constants categorized by command type (read/write/browser/ping)
- Removed receive_full_response method entirely -- replaced by recv_message

## Task Commits

Each task was committed atomically:

1. **Task 1: Create protocol and connection tests (RED phase)** - `fa75f84` (test)
2. **Task 2: Implement length-prefix framing and threading.Lock in both files** - `dbca861` (feat)

## Files Created/Modified
- `tests/test_protocol.py` - 7 protocol roundtrip tests (simple, large, empty, unicode, malformed, oversized, sequential)
- `tests/test_connection.py` - 8 grep-based source verification tests (lock, no sleep, no sendall empty, ping, struct pack/unpack, no receive_full_response, import struct)
- `AbletonMCP_Remote_Script/__init__.py` - Length-prefix framing in _handle_client, ping handler, import struct
- `MCP_Server/server.py` - Length-prefix framing in send_command, threading.Lock, timeout constants, protocol functions

## Decisions Made
- Protocol functions defined as standalone module-level functions rather than class methods -- enables reuse and keeps AbletonConnection focused on connection lifecycle
- Timeout constants organized as frozensets of command names with a _timeout_for() helper -- clean categorization, easy to extend
- Ping command returns version string for future protocol version negotiation
- Kept time.sleep(1.0) in connection retry backoff (get_ableton_connection) -- this is network retry delay, not artificial send/receive delay

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Both socket endpoints use identical length-prefix framing protocol
- Connection access is thread-safe via Lock
- Ready for Plan 03 (dispatch table refactor and reliability improvements)
- All 21 tests pass (protocol + connection + cleanup)

## Self-Check: PASSED

All files exist, all commits verified.

---
*Phase: 01-foundation-repair*
*Completed: 2026-03-13*
