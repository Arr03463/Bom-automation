import json
import os
import uuid
from pathlib import Path


def atomic_write_json(path, data):
    """
    Shared atomic JSON write: write to a uniquely-named temp file in the
    same directory, then os.replace() it into place. os.replace() is
    atomic on both Windows and POSIX, so a reader never observes a
    partially-written file, and a crash mid-write leaves the original
    file (if any) untouched.

    Originally written for SupplierLookupCache; also used by
    customer_reference_registry.py for the approved project/PCB registry
    -- both are "one JSON file, occasionally rewritten whole" cases.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")

    tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    try:
        os.replace(str(tmp_path), str(path))
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise
