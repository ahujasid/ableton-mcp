"""Safety switches for what the MCP server may change in Live.

Every command the server sends to the Remote Script passes ``check()`` first.
Each command belongs to one category; the user's config file turns categories
on or off. The config lives at ``~/.config/ableton-mcp/safety.json`` (or the
path in ``ABLETON_MCP_SAFETY_CONFIG``) and is re-read whenever it changes, so
a switch takes effect on the next tool call without reconnecting.

    {
      "read_only": false,                 # true refuses every change
      "allow": {"delete": true, ...},     # per category, see CATEGORIES
      "saved_set_allow": {"delete": false},  # stricter rules while the open
                                          # set has been saved (a real song)
      "deny_commands": [],                # always refused, by command name
      "allow_commands": []                # allowed even if their category is off
    }

The file is for the human. There is deliberately no MCP tool that changes it;
``get_safety_config`` only reads it. Change it by hand or with the CLI:

    ableton-mcp-safety                  # show the effective switches
    ableton-mcp-safety delete off       # refuse deletes
    ableton-mcp-safety read-only on     # refuse every change
    ableton-mcp-safety saved delete on  # allow deletes in saved sets too

A config file that can't be parsed refuses every change (fail closed), and if
the server can't tell whether the open set is saved, a saved-set rule applies.
"""

import json
import os
import sys
import threading

CONFIG_ENV = "ABLETON_MCP_SAFETY_CONFIG"
DEFAULT_PATH = os.path.join(os.path.expanduser("~"), ".config", "ableton-mcp", "safety.json")

# What each category means, shown by get_safety_config and the CLI.
CATEGORY_HELP = {
    "delete": "delete tracks, return tracks, clips, devices and scenes; clear a clip's notes",
    "playback": "start/stop the transport, launch or stop clips and scenes (makes sound)",
    "mixer": "volume, pan, sends, mute, solo, arm; re-enable automation",
    "routing": "track and device (sidechain) input/output routing, monitoring",
    "structure": "create, duplicate or move tracks, scenes and devices; load instruments/effects",
    "edit": "everything else that changes the set: names, notes, clips, tempo, device parameters, colours",
    "undo": "undo and redo",
}

CATEGORIES = {
    "delete": {"delete_track", "delete_clip", "clear_notes_from_clip", "delete_device", "delete_scene"},
    "playback": {"start_playback", "stop_playback", "fire_clip", "stop_clip", "fire_scene"},
    "mixer": {"set_track_mixer", "re_enable_automation"},
    "routing": {"set_track_routing", "set_track_monitoring", "set_device_routing"},
    "structure": {"create_midi_track", "create_audio_track", "duplicate_track", "create_return_track",
                  "create_scene", "duplicate_scene", "move_device", "load_browser_item",
                  "load_instrument_or_effect", "map_rack_magnitude", "duplicate_session_clip_to_arrangement"},
    "undo": {"undo", "redo"},
}

# Commands that only read. Anything not listed here and not in a category is
# treated as "edit", so a new writing command is gated even if nobody listed it.
READ_COMMANDS = {"drain_passive_events", "inspect_rack"}

DEFAULTS = {
    "read_only": False,
    "allow": dict((c, True) for c in CATEGORY_HELP),
    "saved_set_allow": {"delete": False},
    "deny_commands": [],
    "allow_commands": [],
}


class SafetyRefused(Exception):
    """A command the safety config does not allow."""


def config_path():
    return os.environ.get(CONFIG_ENV) or DEFAULT_PATH


def category_of(command_type):
    """Return the command's category, or None for a read-only command."""
    if command_type.startswith("get_") or command_type in READ_COMMANDS:
        return None
    for cat, cmds in CATEGORIES.items():
        if command_type in cmds:
            return cat
    return "edit"


class _Loader(object):
    """Reads the config, re-reading only when the file's mtime/size changes."""

    def __init__(self):
        self._lock = threading.Lock()
        self._key = None
        self._value = None

    def load(self):
        path = config_path()
        try:
            st = os.stat(path)
            key = (path, st.st_mtime_ns, st.st_size)
        except FileNotFoundError:
            return _merge({}), path, None
        except OSError as e:
            return None, path, "cannot read %s: %s" % (path, e)
        with self._lock:
            if key == self._key:
                return self._value
            try:
                with open(path, encoding="utf-8") as f:
                    raw = json.load(f)
                if not isinstance(raw, dict):
                    raise ValueError("top level must be a JSON object")
                value = (_merge(raw), path, None)
            except Exception as e:
                value = (None, path, "cannot parse %s: %s" % (path, e))
            self._key, self._value = key, value
            return value


_loader = _Loader()


def _merge(raw):
    cfg = json.loads(json.dumps(DEFAULTS))
    for k in ("read_only",):
        if k in raw:
            cfg[k] = bool(raw[k])
    for k in ("allow", "saved_set_allow"):
        if isinstance(raw.get(k), dict):
            for cat, on in raw[k].items():
                if cat not in CATEGORY_HELP:
                    raise ValueError("unknown category %r in %s (known: %s)"
                                     % (cat, k, ", ".join(CATEGORY_HELP)))
                cfg[k][cat] = bool(on)
    for k in ("deny_commands", "allow_commands"):
        if k in raw:
            cfg[k] = [str(c) for c in raw[k]]
    return cfg


def load_config():
    """Return (config or None, path, error or None)."""
    return _loader.load()


def check(command_type, set_is_saved):
    """Raise SafetyRefused unless the config allows command_type.

    set_is_saved is a callable returning True/False, or raising if it can't
    tell; it is only called when a saved-set rule could change the answer.
    """
    cat = category_of(command_type)
    if cat is None:
        return
    cfg, path, err = load_config()
    if err:
        raise SafetyRefused("Refused %s: the safety config is broken (%s). Fix the file; until then "
                            "every change is refused." % (command_type, err))
    where = " (safety config %s)" % path
    if cfg["read_only"]:
        raise SafetyRefused("Refused %s: read_only is on%s." % (command_type, where))
    if command_type in cfg["deny_commands"]:
        raise SafetyRefused("Refused %s: it is in deny_commands%s." % (command_type, where))
    if command_type in cfg["allow_commands"]:
        return
    if not cfg["allow"].get(cat, True):
        raise SafetyRefused("Refused %s: category %r is switched off%s. Ask the user to turn it on "
                            "(ableton-mcp-safety %s on) if they want this." % (command_type, cat, where, cat))
    saved_rule = cfg["saved_set_allow"].get(cat)
    if saved_rule is False:
        try:
            saved = bool(set_is_saved())
        except Exception as e:
            raise SafetyRefused("Refused %s: category %r is off in saved sets and the server could not "
                                "tell whether this set is saved (%s)%s." % (command_type, cat, e, where))
        if saved:
            raise SafetyRefused("Refused %s: category %r is switched off while a saved set (a real song) is "
                                "open%s. Do it by hand in Live, or ask the user to run "
                                "'ableton-mcp-safety saved %s on'." % (command_type, cat, where, cat))


def describe():
    """The effective switches, for get_safety_config and the CLI."""
    cfg, path, err = load_config()
    out = {"path": path, "exists": os.path.exists(path), "error": err,
           "categories": CATEGORY_HELP,
           "commands": dict((c, sorted(v)) for c, v in CATEGORIES.items()),
           "note": "Commands not listed under a category and not get_* count as 'edit'. "
                   "Only the user changes this file; there is no tool to change it."}
    if cfg:
        out.update(cfg)
    return out


def write_config(cfg, path=None):
    path = path or config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        with open(path, "rb") as src, open(path + ".bak", "wb") as dst:
            dst.write(src.read())
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def _on_off(word):
    w = word.lower()
    if w in ("on", "true", "yes", "1", "allow"):
        return True
    if w in ("off", "false", "no", "0", "deny"):
        return False
    raise SystemExit("expected on or off, got %r" % word)


def main(argv=None):
    """ableton-mcp-safety [read-only on|off] [saved] [<category> on|off]"""
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cfg, path, err = load_config()
    if err:
        print("ERROR: " + err)
        return 1
    if args:
        saved = args[0] == "saved"
        if saved:
            args = args[1:]
        if len(args) != 2:
            raise SystemExit("usage: ableton-mcp-safety [saved] <category|read-only> on|off")
        name, on = args[0], _on_off(args[1])
        if name in ("read-only", "read_only"):
            if saved:
                raise SystemExit("read-only has no saved-set variant")
            cfg["read_only"] = on
        elif name in CATEGORY_HELP:
            cfg["saved_set_allow" if saved else "allow"][name] = on
        else:
            raise SystemExit("unknown category %r; known: read-only, %s" % (name, ", ".join(CATEGORY_HELP)))
        write_config(cfg, path)
        print("wrote %s" % path)
    cfg, path, _ = load_config()
    print("Safety config: %s%s" % (path, "" if os.path.exists(path) else " (not created yet: built-in defaults)"))
    print("  read_only: %s" % ("ON - every change refused" if cfg["read_only"] else "off"))
    for cat, help_text in CATEGORY_HELP.items():
        on = cfg["allow"].get(cat, True)
        saved = cfg["saved_set_allow"].get(cat)
        extra = "" if saved is None or not on else ("   (saved sets: %s)" % ("allowed" if saved else "REFUSED"))
        print("  %-10s %-7s %s%s" % (cat, "allowed" if on else "REFUSED", help_text, extra))
    if cfg["deny_commands"]:
        print("  deny_commands: %s" % ", ".join(cfg["deny_commands"]))
    if cfg["allow_commands"]:
        print("  allow_commands: %s" % ", ".join(cfg["allow_commands"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
