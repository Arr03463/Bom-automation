"""Bucket batch timers — anchored to a real clock, persisted, Admin-configurable.

Before this, the countdown was fiction on both sides: the frontend seed carried
`nextRunMin: 142` and the backend's bootstrap hard-coded the same literal, so
"next batch in 2h 22m" never moved no matter how long you watched it, and the
Admin interval control mutated client memory that was thrown away on reload.

The fix is to store an ABSOLUTE next-run instant rather than a countdown number.
A stored countdown is wrong the moment nobody is looking at it; an anchor stays
correct across reloads, restarts and multiple tabs, and every client just
subtracts `now` from it.

Persisted in `configuration` under key "batch":
    {"main":     {"intervalMin": 360, "nextRunAt": <iso>, "lastRunAt": <iso|null>},
     "critical": {"intervalMin": 180, ...}}

Bounded Admin Authority: the interval is an integer number of minutes clamped to
[MIN_INTERVAL_MIN, MAX_INTERVAL_MIN]; anything else is rejected rather than
silently coerced, so a typo cannot schedule a flush every 0 minutes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from db.models import Configuration

log = logging.getLogger("autobom.timers")

CONFIG_KEY = "batch"
CONFIG_SECTION = "purchasing"
STREAMS = ("critical", "main")

# CLAUDE.md defaults: 180 min Critical, 360 min Main.
DEFAULT_INTERVALS = {"critical": 180, "main": 360}
MIN_INTERVAL_MIN = 5        # below this the sheet would be spammed
MAX_INTERVAL_MIN = 1440     # 24h


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat() if dt else None


def _parse(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _row(db: Session) -> Configuration:
    cfg = db.get(Configuration, CONFIG_KEY)
    if cfg is None:
        cfg = Configuration(key=CONFIG_KEY, section=CONFIG_SECTION, value={})
        db.add(cfg)
    if not isinstance(cfg.value, dict):
        cfg.value = {}
    return cfg


def _save(db: Session, cfg: Configuration, value: dict) -> None:
    # Reassign (don't mutate in place): SQLAlchemy does not track mutations
    # inside a JSON column, so an in-place edit would never be written back.
    cfg.value = value
    db.add(cfg)


def validate_interval(minutes) -> int:
    try:
        m = int(minutes)
    except (TypeError, ValueError):
        raise ValueError(f"Interval must be a whole number of minutes, got {minutes!r}")
    if not MIN_INTERVAL_MIN <= m <= MAX_INTERVAL_MIN:
        raise ValueError(
            f"Interval must be between {MIN_INTERVAL_MIN} and {MAX_INTERVAL_MIN} minutes, got {m}"
        )
    return m


def get_timers(db: Session) -> dict:
    """Current timer state for both streams, computed against the real clock.

    Self-healing: a stream with no anchor (fresh install) or an anchor already in
    the past gets one now, so the countdown is always meaningful. `due` says the
    window has elapsed — whether anything acts on that is the caller's business
    (today: an Admin clicking flush; a scheduler could use the same signal).
    """
    cfg = _row(db)
    value = dict(cfg.value or {})
    now = _now()
    changed = False
    out = {}

    for stream in STREAMS:
        s = dict(value.get(stream) or {})
        try:
            interval = validate_interval(s.get("intervalMin", DEFAULT_INTERVALS[stream]))
        except ValueError:
            interval = DEFAULT_INTERVALS[stream]
        next_at = _parse(s.get("nextRunAt"))
        if next_at is None:
            next_at = now + timedelta(minutes=interval)
            changed = True
        last_at = _parse(s.get("lastRunAt"))

        remaining = (next_at - now).total_seconds()
        s.update({"intervalMin": interval, "nextRunAt": _iso(next_at), "lastRunAt": _iso(last_at)})
        value[stream] = s
        out[stream] = {
            "intervalMin": interval,
            "nextRunAt": _iso(next_at),
            "lastRunAt": _iso(last_at),
            # Seconds is what a client ticks on; minutes kept for the existing
            # UI contract (it renders `next batch in {fmtC(nextRunMin)}`).
            "secondsRemaining": max(0, int(remaining)),
            "nextRunMin": max(0, int(remaining // 60)),
            "due": remaining <= 0,
            "writing": False,
        }

    if changed:
        _save(db, cfg, value)
        db.commit()
    return out


def set_interval(db: Session, stream: str, minutes) -> dict:
    """Change a stream's cadence and RE-ANCHOR from now.

    Re-anchoring matters: leaving the old anchor in place after shortening the
    interval could leave a next-run further out than the new interval allows.
    """
    if stream not in STREAMS:
        raise ValueError(f"Unknown stream {stream!r}; expected one of {list(STREAMS)}")
    m = validate_interval(minutes)
    cfg = _row(db)
    value = dict(cfg.value or {})
    s = dict(value.get(stream) or {})
    before = s.get("intervalMin", DEFAULT_INTERVALS[stream])
    s["intervalMin"] = m
    s["nextRunAt"] = _iso(_now() + timedelta(minutes=m))
    value[stream] = s
    _save(db, cfg, value)
    db.commit()
    log.info("bucket timer %s interval %s -> %s min (re-anchored)", stream, before, m)
    return get_timers(db)[stream]


def mark_flushed(db: Session, stream: str) -> None:
    """Record a completed flush and restart the countdown."""
    if stream not in STREAMS:
        return
    cfg = _row(db)
    value = dict(cfg.value or {})
    s = dict(value.get(stream) or {})
    interval = s.get("intervalMin", DEFAULT_INTERVALS[stream])
    now = _now()
    s["lastRunAt"] = _iso(now)
    s["nextRunAt"] = _iso(now + timedelta(minutes=interval))
    value[stream] = s
    _save(db, cfg, value)
    db.commit()
