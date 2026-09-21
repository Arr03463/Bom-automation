"""
Minimal engineering-value parsing shared by record_filter.py's range
filters. Not a full electronics ontology or dimensional-analysis system --
it converts a string like "10uF", "4.7k", "25 V", or "10%" into a plain
float in base units (SI prefix applied, unit suffix stripped), so range
comparisons ("voltage >= 25") work without each page writing its own
ad hoc numeric parsing. Callers are responsible for only comparing values
that are actually the same kind of quantity; this module does not know
what a volt is, only how to strip one.
"""

import re

SI_PREFIX_MULTIPLIERS = {
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "µ": 1e-6,
    "m": 1e-3,
    "k": 1e3,
    "K": 1e3,
    "M": 1e6,
    "G": 1e9,
}

# Longest-first so "Hz" is stripped before a bare "H" match could apply.
_KNOWN_UNIT_SUFFIXES = sorted(
    ["ohm", "Ohm", "Hz", "V", "A", "W", "F", "H", "%", "s"],
    key=len,
    reverse=True,
)

_NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?$")


def parse_engineering_value(value):
    """
    Returns a float in base units, or None if `value` cannot be
    interpreted as a number (missing, blank, or genuinely non-numeric
    text). Handles a leading +/-, an optional "±"/"+/-" tolerance marker,
    a known unit suffix, and a single-character SI prefix immediately
    before that suffix (or at the end of the string if there is no
    recognized unit suffix).
    """
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    text = text.replace("±", "").replace("+/-", "").strip()
    if not text:
        return None

    for unit in _KNOWN_UNIT_SUFFIXES:
        if text.endswith(unit) and len(text) > len(unit):
            text = text[: -len(unit)]
            break

    text = text.strip()
    if not text:
        return None

    if _NUMBER_RE.match(text):
        return float(text)

    prefix = text[-1]
    if prefix in SI_PREFIX_MULTIPLIERS:
        number_text = text[:-1]
        if _NUMBER_RE.match(number_text):
            return float(number_text) * SI_PREFIX_MULTIPLIERS[prefix]

    return None


def value_in_range(value, minimum=None, maximum=None):
    """
    True if `value` (already a parsed float) falls within
    [minimum, maximum] where either bound may be None (unbounded on that
    side). A value of None (unparseable/missing) never matches a bounded
    range -- an unknown quantity is not "within" any real range.
    """
    if value is None:
        return False
    if minimum is not None and value < minimum:
        return False
    if maximum is not None and value > maximum:
        return False
    return True
