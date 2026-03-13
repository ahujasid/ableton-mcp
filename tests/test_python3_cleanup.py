"""Tests verifying Python 2 compatibility code removal and Python 3.11 idiom adoption.

These tests grep the actual source files on disk to confirm that:
- All Python 2 compatibility code has been removed
- Python 3.11 idioms (super(), f-strings, direct queue import) are used
- No bare except: blocks exist anywhere
"""

import re


def test_no_future_imports(remote_script_source: str) -> None:
    """Verify no 'from __future__' imports remain in the Remote Script."""
    assert "from __future__" not in remote_script_source, (
        "Found 'from __future__' import -- Python 2 compatibility code should be removed"
    )


def test_no_queue_compat_hack(remote_script_source: str) -> None:
    """Verify the try/except Queue import hack is gone and direct 'import queue' is used."""
    assert "import Queue" not in remote_script_source, (
        "Found 'import Queue' -- Python 2 queue compatibility hack should be removed"
    )
    assert "import queue" in remote_script_source, (
        "Missing 'import queue' -- direct Python 3 queue import should be present"
    )


def test_no_attribute_error_decode_branches(remote_script_source: str) -> None:
    """Verify no AttributeError try/except blocks for encode/decode remain.

    The Remote Script had three try/except AttributeError blocks that were
    Python 2 compatibility shims for string encode/decode. In Python 3,
    socket.recv() always returns bytes, so these are dead code.
    """
    # Find except AttributeError blocks that are part of encode/decode patterns
    # Look for "except AttributeError" near "Python 2" comments
    lines = remote_script_source.splitlines()
    for i, line in enumerate(lines):
        if "except AttributeError" in line:
            # Check surrounding lines (2 lines after) for Python 2 comments
            context = "\n".join(lines[max(0, i - 2):i + 3])
            if "Python 2" in context or "decode" in context or "encode" in context:
                raise AssertionError(
                    f"Found AttributeError except block for encode/decode compatibility "
                    f"at line {i + 1}:\n{context}"
                )


def test_super_calls_used(remote_script_source: str) -> None:
    """Verify old-style ControlSurface.__init__/disconnect calls are replaced with super()."""
    assert "ControlSurface.__init__" not in remote_script_source, (
        "Found 'ControlSurface.__init__' -- should use super().__init__() instead"
    )
    assert "ControlSurface.disconnect(self)" not in remote_script_source, (
        "Found 'ControlSurface.disconnect(self)' -- should use super().disconnect() instead"
    )
    assert "super().__init__" in remote_script_source, (
        "Missing 'super().__init__' -- Python 3 super() should be used for __init__"
    )
    assert "super().disconnect()" in remote_script_source, (
        "Missing 'super().disconnect()' -- Python 3 super() should be used for disconnect"
    )


def test_no_bare_excepts(remote_script_source: str, server_source: str) -> None:
    """Verify no bare 'except:' blocks exist in either source file.

    Bare except blocks catch SystemExit and KeyboardInterrupt, which is almost
    never desired. Every except should catch a specific exception type.
    """
    bare_except_pattern = re.compile(r"except\s*:")

    remote_matches = bare_except_pattern.findall(remote_script_source)
    assert len(remote_matches) == 0, (
        f"Found {len(remote_matches)} bare 'except:' block(s) in Remote Script -- "
        f"each should catch a specific exception type"
    )

    server_matches = bare_except_pattern.findall(server_source)
    assert len(server_matches) == 0, (
        f"Found {len(server_matches)} bare 'except:' block(s) in MCP Server -- "
        f"each should catch a specific exception type"
    )


def test_f_strings_used(remote_script_source: str) -> None:
    """Verify f-strings are used and .format() calls are minimal.

    The Remote Script should use f-strings throughout instead of
    string concatenation with + or .format() calls.
    """
    format_count = remote_script_source.count('".format(') + remote_script_source.count("'.format(")
    assert format_count <= 2, (
        f"Found {format_count} .format() calls -- should use f-strings instead "
        f"(up to 2 allowed for edge cases)"
    )

    # Count f-string usage
    f_string_pattern = re.compile(r'''f["']''')
    f_string_count = len(f_string_pattern.findall(remote_script_source))
    assert f_string_count > 10, (
        f"Only found {f_string_count} f-strings -- expected more than 10 after conversion"
    )
