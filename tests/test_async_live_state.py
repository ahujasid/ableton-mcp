"""Regression tests for commands whose Live writes land on a later tick.

Live applies ``song.current_song_time = x``, ``song.set_or_delete_cue()`` and
``browser.load_item()`` asynchronously: reading the state back in the same
main-thread tick returns the old value. That broke three commands:

* set_current_song_time reported the *previous* playhead position,
* create_locator toggled the cue at the old playhead, then found nothing at
  the target and failed (unless the playhead was already there),
* load_browser_item read the device chain before the device was inserted and
  never sent ``new_devices`` / ``devices_after``, so the server printed an
  empty list.

FakeSong models that: writes are queued and only applied on ``tick()``,
which the fake scheduler calls before running each scheduled callback.
"""

from collections import deque

import pytest

from test_remote_script_bridge import _load_script_module, make_instance


@pytest.fixture(scope="module")
def script_module():
    return _load_script_module()


class FakeCue(object):
    def __init__(self, time):
        self.time = time
        self.name = ""


class FakeParameter(object):
    def __init__(self, value):
        self.value = value


class FakeDevice(object):
    _next_ptr = 1
    DEFAULTS = (1.0, 0.0, 0.5)

    def __init__(self, name):
        self.name = name
        self.class_name = name
        self._live_ptr = FakeDevice._next_ptr
        FakeDevice._next_ptr += 1
        self.parameters = [FakeParameter(v) for v in self.DEFAULTS]


class FakeTrack(object):
    def __init__(self, name="Track"):
        self.name = name
        self.devices = []

    def insert_instrument(self, device):
        """What Live 12 was observed to do: a different instrument replaces
        the current one, but loading an identical one keeps the existing
        device and only resets its parameters to their defaults."""
        if self.devices and self.devices[0].class_name == device.class_name:
            for param, default in zip(self.devices[0].parameters,
                                      FakeDevice.DEFAULTS):
                param.value = default
        else:
            self.devices = [device]


class FakeSongView(object):
    selected_track = None


class FakeSong(object):
    """Song whose writes take effect one tick later, like Live's."""

    def __init__(self, time=0.0, cues=(), playing=False):
        self._time = time
        self._pending = []
        self.cue_points = [FakeCue(t) for t in cues]
        self.is_playing = playing
        self.tracks = [FakeTrack()]
        self.view = FakeSongView()
        self.stuck = False  # when True, playhead writes never apply

    @property
    def current_song_time(self):
        return self._time

    @current_song_time.setter
    def current_song_time(self, value):
        self._pending.append(("time", value))

    def set_or_delete_cue(self):
        self._pending.append(("cue", None))

    def tick(self):
        pending, self._pending = self._pending, []
        for kind, value in pending:
            if kind == "time" and not self.stuck:
                self._time = value
            elif kind == "cue":
                # Toggles at the *applied* playhead, as Live does.
                for cue in self.cue_points:
                    if abs(cue.time - self._time) < 1e-3:
                        self.cue_points.remove(cue)
                        break
                else:
                    self.cue_points.append(FakeCue(self._time))
            elif kind == "load":
                track, device = value
                track.insert_instrument(device)


class FakeBrowser(object):
    def __init__(self, song):
        self._song = song

    def load_item(self, item):
        self._song._pending.append(
            ("load", (self._song.view.selected_track, FakeDevice(item.name))))


class FakeApplication(object):
    def __init__(self, song):
        self.browser = FakeBrowser(song)


class FakeItem(object):
    name = "Drift"


def make_live(script_module, song):
    inst = make_instance(script_module, application=FakeApplication(song))
    inst._song = song
    scheduled = deque()

    def schedule_message(delay, callback):
        if delay == 0:
            callback()
        else:
            scheduled.append(callback)

    inst.schedule_message = schedule_message

    def run_ticks(limit=200):
        n = 0
        while scheduled and n < limit:
            song.tick()
            scheduled.popleft()()
            n += 1

    return inst, run_ticks


def run_deferred(deferred, run_ticks):
    outcome = {}
    deferred.start(lambda v: outcome.setdefault("ok", v),
                   lambda m: outcome.setdefault("err", m))
    run_ticks()
    return outcome


# ------------------------------------------------------------- playhead

def test_set_song_time_reports_the_new_position(script_module):
    song = FakeSong(time=0.0)
    inst, run_ticks = make_live(script_module, song)

    out = run_deferred(inst._set_current_song_time(16.0), run_ticks)

    assert out["ok"]["current_song_time"] == 16.0
    assert out["ok"]["settled"] is True


def test_set_song_time_says_so_when_live_never_moves(script_module):
    song = FakeSong(time=0.0)
    song.stuck = True
    inst, run_ticks = make_live(script_module, song)

    out = run_deferred(inst._set_current_song_time(16.0), run_ticks)

    assert out["ok"]["current_song_time"] == 0.0
    assert out["ok"]["settled"] is False


# ------------------------------------------------------------- locators

def test_locator_is_created_at_target_not_at_old_playhead(script_module):
    song = FakeSong(time=0.0)
    inst, run_ticks = make_live(script_module, song)

    out = run_deferred(inst._create_locator("Drop", 16.0), run_ticks)

    assert out["ok"] == {"success": True, "time": 16.0, "name": "Drop"}
    assert [(c.time, c.name) for c in song.cue_points] == [(16.0, "Drop")]
    song.tick()  # the restore is itself applied on the next tick
    assert song.current_song_time == 0.0


def test_locator_at_existing_cue_is_renamed_not_toggled(script_module):
    song = FakeSong(time=0.0, cues=[16.0])
    inst, _ = make_live(script_module, song)

    result = inst._create_locator("Chorus", 16.0)

    assert result == {"success": True, "time": 16.0, "name": "Chorus"}
    assert len(song.cue_points) == 1
    assert song._pending == []


def test_locator_refuses_while_playing(script_module):
    song = FakeSong(time=0.0, playing=True)
    inst, _ = make_live(script_module, song)

    with pytest.raises(Exception, match="Stop playback"):
        inst._create_locator("Drop", 16.0)


def test_locator_fails_cleanly_and_restores_when_playhead_never_moves(
        script_module):
    song = FakeSong(time=4.0)
    song.stuck = True
    inst, run_ticks = make_live(script_module, song)

    out = run_deferred(inst._create_locator("Drop", 16.0), run_ticks)

    assert "did not reach beat 16.0" in out["err"]
    assert song.cue_points == []


# ------------------------------------------------------------- device load

def test_load_reports_the_device_once_live_inserts_it(script_module):
    song = FakeSong()
    inst, run_ticks = make_live(script_module, song)
    inst._find_browser_item_by_uri = lambda browser, uri: FakeItem()

    out = run_deferred(
        inst._load_browser_item(0, "query:Synths#Drift"), run_ticks)

    assert out["ok"]["devices_before"] == []
    assert out["ok"]["devices_after"] == ["Drift"]
    assert out["ok"]["new_devices"] == ["Drift"]
    assert out["ok"]["settled"] is True


def test_load_detects_an_in_place_reload_by_its_parameter_reset(
        script_module):
    song = FakeSong()
    drift = FakeDevice("Drift")
    drift.parameters[0].value = 0.3  # user tweaked it
    song.tracks[0].devices.append(drift)
    inst, run_ticks = make_live(script_module, song)
    inst._find_browser_item_by_uri = lambda browser, uri: FakeItem()

    out = run_deferred(
        inst._load_browser_item(0, "query:Synths#Drift"), run_ticks)

    assert out["ok"]["in_place"] is True
    assert out["ok"]["settled"] is True
    assert out["ok"]["new_devices"] == ["Drift"]
    assert drift.parameters[0].value == 1.0


def test_in_place_reload_with_untouched_parameters_gives_up_quickly(
        script_module):
    song = FakeSong()
    song.tracks[0].devices.append(FakeDevice("Drift"))  # already defaults
    inst, _ = make_live(script_module, song)
    inst._find_browser_item_by_uri = lambda browser, uri: FakeItem()
    ticks = []

    def run_ticks():
        while inst_scheduled:
            song.tick()
            ticks.append(1)
            inst_scheduled.pop(0)()

    inst_scheduled = []
    inst.schedule_message = lambda delay, cb: inst_scheduled.append(cb)

    out = run_deferred(
        inst._load_browser_item(0, "query:Synths#Drift"), run_ticks)

    assert out["ok"]["in_place"] is True
    assert out["ok"]["settled"] is False
    assert out["ok"]["new_devices"] == []
    assert len(ticks) == script_module.SAME_KIND_RELOAD_SETTLE_TICKS


def test_load_reports_unsettled_when_live_never_inserts(script_module):
    song = FakeSong()
    inst, run_ticks = make_live(script_module, song)
    inst._find_browser_item_by_uri = lambda browser, uri: FakeItem()

    deferred = inst._load_browser_item(0, "query:Synths#Drift")
    song._pending.clear()  # the load never lands
    out = run_deferred(deferred, run_ticks)

    assert out["ok"]["settled"] is False
    assert out["ok"]["in_place"] is False
    assert out["ok"]["new_devices"] == []


# ------------------------------------------------------------- dispatcher

def test_dispatcher_waits_for_deferred_result(script_module):
    """Through _process_command, with a scheduler that ticks Live before
    running every callback (so nothing blocks on the response queue)."""
    song = FakeSong(time=0.0)
    inst, _ = make_live(script_module, song)

    def schedule_message(delay, callback):
        song.tick()
        callback()

    inst.schedule_message = schedule_message

    response = inst._process_command(
        {"type": "create_locator", "params": {"name": "Drop", "time": 8.0}})

    assert response["status"] == "success"
    assert response["result"]["time"] == 8.0
    assert response["result"]["name"] == "Drop"
