"""Bucket batch timers: anchored to a real clock, persisted, bounded.

The countdown used to be a literal (`nextRunMin: 142`) hard-coded in BOTH the
frontend seed and the backend bootstrap, so it never moved; the Admin control
mutated client memory that was discarded on reload.
"""

from datetime import datetime, timedelta, timezone

import pytest

from db.models import Configuration
from services import bucket_timers as bt


def _set(db, stream, **fields):
    cfg = db.get(Configuration, bt.CONFIG_KEY) or Configuration(
        key=bt.CONFIG_KEY, section=bt.CONFIG_SECTION, value={})
    value = dict(cfg.value or {})
    value[stream] = {**(value.get(stream) or {}), **fields}
    cfg.value = value
    db.add(cfg)
    db.commit()


# --- anchored to a clock ----------------------------------------------------
def test_countdown_is_derived_from_an_absolute_anchor(db):
    """The core fix: store WHEN the next run is, not how many minutes are left.
    A stored countdown is stale the moment nobody is looking at it."""
    soon = datetime.now(timezone.utc) + timedelta(minutes=30)
    _set(db, "main", intervalMin=360, nextRunAt=soon.isoformat())
    t = bt.get_timers(db)["main"]
    assert 29 * 60 <= t["secondsRemaining"] <= 30 * 60
    assert t["nextRunMin"] in (29, 30)
    assert t["due"] is False


def test_countdown_actually_decreases_as_time_passes(db):
    """Guards the original bug directly: two reads must differ."""
    _set(db, "main", intervalMin=360,
         nextRunAt=(datetime.now(timezone.utc) + timedelta(seconds=90)).isoformat())
    first = bt.get_timers(db)["main"]["secondsRemaining"]
    import time as _t
    _t.sleep(1.1)
    second = bt.get_timers(db)["main"]["secondsRemaining"]
    assert second < first, "countdown is frozen — not connected to a clock"


def test_elapsed_timer_reports_due_and_never_goes_negative(db):
    _set(db, "critical", intervalMin=180,
         nextRunAt=(datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat())
    t = bt.get_timers(db)["critical"]
    assert t["due"] is True and t["secondsRemaining"] == 0 and t["nextRunMin"] == 0


def test_missing_anchor_is_self_healed(db):
    """Fresh install: no anchor yet. Must produce a real one, not a fake number."""
    t = bt.get_timers(db)
    for stream in ("main", "critical"):
        assert t[stream]["nextRunAt"], f"{stream} has no anchor"
        assert t[stream]["secondsRemaining"] > 0
    assert t["critical"]["intervalMin"] == 180     # CLAUDE.md defaults
    assert t["main"]["intervalMin"] == 360


def test_anchor_persists_across_reads(db):
    first = bt.get_timers(db)["main"]["nextRunAt"]
    assert bt.get_timers(db)["main"]["nextRunAt"] == first, "anchor must not drift per read"


# --- Bounded Admin ----------------------------------------------------------
def test_interval_persists_and_reanchors(db):
    out = bt.set_interval(db, "main", 45)
    assert out["intervalMin"] == 45
    assert bt.get_timers(db)["main"]["intervalMin"] == 45     # survived the round trip
    assert out["secondsRemaining"] <= 45 * 60                 # re-anchored, not left long


def test_shortening_the_interval_pulls_the_next_run_in(db):
    _set(db, "main", intervalMin=360,
         nextRunAt=(datetime.now(timezone.utc) + timedelta(hours=5)).isoformat())
    bt.set_interval(db, "main", 10)
    assert bt.get_timers(db)["main"]["secondsRemaining"] <= 10 * 60


@pytest.mark.parametrize("bad", [0, -5, 4, 1441, 99999, "abc", None, 3.7e9])
def test_out_of_range_intervals_are_rejected_not_coerced(db, bad):
    """A typo must not schedule a flush every 0 minutes."""
    with pytest.raises(ValueError):
        bt.set_interval(db, "main", bad)


def test_bounds_are_inclusive(db):
    assert bt.set_interval(db, "main", bt.MIN_INTERVAL_MIN)["intervalMin"] == bt.MIN_INTERVAL_MIN
    assert bt.set_interval(db, "main", bt.MAX_INTERVAL_MIN)["intervalMin"] == bt.MAX_INTERVAL_MIN


def test_unknown_stream_is_rejected(db):
    with pytest.raises(ValueError, match="Unknown stream"):
        bt.set_interval(db, "urgent", 60)


def test_float_minutes_are_truncated_to_a_whole_number(db):
    assert bt.set_interval(db, "main", 45.9)["intervalMin"] == 45


# --- flush restarts the countdown -------------------------------------------
def test_mark_flushed_records_the_run_and_restarts_the_clock(db):
    _set(db, "critical", intervalMin=30,
         nextRunAt=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())
    assert bt.get_timers(db)["critical"]["due"] is True
    bt.mark_flushed(db, "critical")
    t = bt.get_timers(db)["critical"]
    assert t["due"] is False
    assert t["lastRunAt"] is not None
    assert 29 * 60 <= t["secondsRemaining"] <= 30 * 60


def test_corrupt_stored_interval_falls_back_to_the_default(db):
    """Bad data must not break the whole Purchasing screen."""
    _set(db, "main", intervalMin="not-a-number")
    assert bt.get_timers(db)["main"]["intervalMin"] == 360
