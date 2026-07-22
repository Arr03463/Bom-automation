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


def test_an_elapsed_timer_rolls_forward_instead_of_parking_at_zero(db):
    """The reported bug: with no scheduler consuming the boundary, an elapsed
    anchor sat at 0s / "batch due" forever, which looks exactly like a timer
    that was never connected to a clock."""
    _set(db, "critical", intervalMin=180,
         nextRunAt=(datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat())
    t = bt.get_timers(db)["critical"]
    assert t["secondsRemaining"] > 0, "timer is stuck at zero"
    assert t["due"] is False
    assert t["missedRuns"] == 1
    assert t["secondsRemaining"] <= 180 * 60


def test_roll_forward_stays_on_the_original_cadence(db):
    """Advance by WHOLE intervals, so a long gap doesn't drift the schedule."""
    interval = 60
    anchor = datetime.now(timezone.utc) - timedelta(minutes=200)   # 3 windows + 20m ago
    _set(db, "main", intervalMin=interval, nextRunAt=anchor.isoformat())
    t = bt.get_timers(db)["main"]
    assert t["missedRuns"] == 4
    delta = (datetime.fromisoformat(t["nextRunAt"]) - anchor).total_seconds() / 60
    assert delta % interval == 0, "next run drifted off the original cadence"
    assert 0 < t["secondsRemaining"] <= interval * 60


def test_a_very_old_anchor_still_lands_in_the_future(db):
    """Overnight/weekend gap must not need N iterations or produce a past time."""
    _set(db, "main", intervalMin=360,
         nextRunAt=(datetime.now(timezone.utc) - timedelta(days=30)).isoformat())
    t = bt.get_timers(db)["main"]
    assert t["secondsRemaining"] > 0 and t["missedRuns"] > 100


def test_roll_forward_is_persisted(db):
    _set(db, "critical", intervalMin=30,
         nextRunAt=(datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat())
    first = bt.get_timers(db)["critical"]["nextRunAt"]
    assert bt.get_timers(db)["critical"]["nextRunAt"] == first, "roll-forward not saved"
    assert bt.get_timers(db)["critical"]["missedRuns"] == 0, "already rolled; nothing missed now"


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
    """A flush re-anchors from NOW (not from the rolled cadence boundary), and
    stamps lastRunAt so the UI can show when the batch actually went out."""
    _set(db, "critical", intervalMin=30,
         nextRunAt=(datetime.now(timezone.utc) + timedelta(minutes=4)).isoformat())
    assert bt.get_timers(db)["critical"]["lastRunAt"] is None
    bt.mark_flushed(db, "critical")
    t = bt.get_timers(db)["critical"]
    assert t["lastRunAt"] is not None
    assert t["due"] is False
    assert 29 * 60 <= t["secondsRemaining"] <= 30 * 60, "did not restart a full interval"


def test_corrupt_stored_interval_falls_back_to_the_default(db):
    """Bad data must not break the whole Purchasing screen."""
    _set(db, "main", intervalMin="not-a-number")
    assert bt.get_timers(db)["main"]["intervalMin"] == 360
