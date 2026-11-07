"""Set a device parameter the way Live shows it: "1.80 s", "830 Hz", "-18 dB", "Ping Pong".

Live stores most parameters as a raw value (often 0..1) and only shows the unit
through ``str_for_value``. Finding the raw value for a shown value is a search;
doing it here, inside Live, costs one call instead of dozens of round trips.
No Live imports, so it is testable on its own.
"""

from __future__ import absolute_import, print_function, unicode_literals

import re

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def display_number(text):
    """A shown value as one comparable number: kHz → Hz, s → ms, "-inf dB" → -1e9.
    Returns None when the text has no number (an on/off or list label)."""
    t = text.strip().lower().replace(",", ".")
    if "inf" in t:
        return -1e9 if "-" in t else 1e9
    m = _NUMBER.search(t)
    if not m:
        return None
    v = float(m.group(0))
    if "khz" in t:
        v *= 1000.0
    elif re.search(r"\d\s*s$", t):  # "1.80 s", not "ms"
        v *= 1000.0
    return v


def resolve_value(param, value, iterations=40):
    """The raw value that makes ``param`` show ``value``.

    A number is taken as raw. A string matches a list item (case-insensitive)
    for switches and menus, else is searched for by bisection over the
    parameter's range on its shown number.
    """
    if not isinstance(value, str):
        v = float(value)
        if not param.min <= v <= param.max:
            raise ValueError("%s: %s is outside %s..%s (raw); pass the shown value as a string, e.g. \"%s\""
                             % (param.name, v, param.min, param.max, param.str_for_value(param.value)))
        return v
    if param.is_quantized:
        items = [str(i) for i in param.value_items]
        lowered = [i.lower() for i in items]
        want = value.strip().lower()
        if want in lowered:
            return float(param.min) + lowered.index(want)
        raise ValueError("%s: '%s' is not one of %s" % (param.name, value, items))
    target = display_number(value)
    if target is None:
        raise ValueError("%s: no number in '%s'" % (param.name, value))

    def shown(raw):
        n = display_number(param.str_for_value(raw))
        if n is None:
            raise ValueError("%s shows no number ('%s'); pass a raw value" % (param.name, param.str_for_value(raw)))
        return n

    lo, hi = float(param.min), float(param.max)
    at_lo, at_hi = shown(lo), shown(hi)
    rising = at_hi >= at_lo
    if (target < min(at_lo, at_hi)) or (target > max(at_lo, at_hi)):
        raise ValueError("%s: '%s' is outside %s..%s" % (param.name, value, param.str_for_value(lo), param.str_for_value(hi)))
    a, b = lo, hi
    for _ in range(iterations):
        mid = (a + b) / 2.0
        if (shown(mid) < target) == rising:
            a = mid
        else:
            b = mid
    return b


def find_parameter(device, name):
    """A device's parameter by its exact name, case-insensitive as a fallback."""
    params = list(device.parameters)
    for p in params:
        if p.name == name:
            return p
    for p in params:
        if p.name.lower() == name.lower():
            return p
    raise ValueError("No parameter '%s' on %s; it has: %s" % (name, device.name, [p.name for p in params]))
