"""Setting a parameter by the value Live shows, without Live."""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "AbletonMCP_Remote_Script", "handlers"))
import params  # noqa: E402


class Param:
    """A fake DeviceParameter: raw 0..1 mapped to a display by `show`."""

    def __init__(self, name, show, quantized=False, items=(), lo=0.0, hi=1.0):
        self.name, self.show, self.is_quantized, self.value_items = name, show, quantized, list(items)
        self.min, self.max, self.value = lo, hi, lo

    def str_for_value(self, v):
        return self.show(v)


def hz(v):  # 20 Hz .. 20 kHz, exponential like Live's filters
    f = 20 * 1000 ** v
    return "%.2f kHz" % (f / 1000) if f >= 1000 else "%.0f Hz" % f


@pytest.mark.parametrize("text, n", [("1.80 s", 1800), ("600 ms", 600), ("4.50 kHz", 4500), ("830 Hz", 830),
                                      ("-18.0 dB", -18), ("-inf dB", -1e9), ("40 %", 40), ("5.85 ", 5.85), ("On", None)])
def test_display_number(text, n):
    assert params.display_number(text) == n


def test_shown_value_is_found_by_search():
    p = Param("Freq", hz)
    raw = params.resolve_value(p, "830 Hz")
    assert math.isclose(20 * 1000 ** raw, 830, rel_tol=0.01)
    raw = params.resolve_value(p, "4.50 kHz")
    assert math.isclose(20 * 1000 ** raw, 4500, rel_tol=0.01)


def test_falling_display_and_list_items():
    falling = Param("Atten", lambda v: "%.1f dB" % (-60 * v))
    assert math.isclose(params.resolve_value(falling, "-18 dB"), 0.3, abs_tol=0.01)
    menu = Param("Channel Mode", None, quantized=True, items=["Stereo", "Ping Pong", "Mid/Side"], hi=2.0)
    assert params.resolve_value(menu, "ping pong") == 1.0


def test_errors_name_the_problem():
    with pytest.raises(ValueError, match="outside"):
        params.resolve_value(Param("Freq", hz), "50 kHz")
    with pytest.raises(ValueError, match="raw"):
        params.resolve_value(Param("Freq", hz), 5.85)
    with pytest.raises(ValueError, match="not one of"):
        params.resolve_value(Param("Mode", None, quantized=True, items=["A", "B"], hi=1.0), "C")
