"""
Approved Project/PCB code registry backing the Customer Reference feature
(see Documentation/AutoBOM_Customer_Reference_Feature_Report.md and the
Yank naming-convention SOP, YT-SOP-00-01-A).

Deliberately a single, plain, human-editable JSON file, not scattered
across Python modules: adding a newly-approved project or PCB code is a
config edit, never a generator/supplier-adapter/sourcing-engine change.
Today's codes (from the SOP) are the CURRENT approved registry, not a
permanent, hardcoded universe -- see add_project()/add_pcb_code().
"""

import json
import os
import re
from pathlib import Path

from atomic_file import atomic_write_json

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "config" / "customer_reference_registry.json"

# Codes are a single hyphen-free, underscore-free field (the generator is
# what joins multiple codes with "-"/"_") -- letters and digits only,
# matching every code in the SOP (ARM, ATH, DAB, BUZZ, BOOST, ...).
_CODE_PATTERN = re.compile(r"^[A-Z0-9]+$")


class RegistryError(ValueError):
    """
    Raised for a missing, corrupt, or structurally invalid registry file.
    Deliberately NOT swallowed/defaulted to empty like the supplier
    lookup cache's lenient reader -- an approved-code registry silently
    reading as empty could make every project/PCB code look unapproved,
    or (worse) be mistaken for "nothing is restricted yet."
    """


def resolve_registry_path(path=None):
    if path:
        return Path(path)
    override = os.getenv("CUSTOMER_REFERENCE_REGISTRY_PATH", "").strip()
    return Path(override) if override else DEFAULT_REGISTRY_PATH


def _validate_code_map(value, field_name):
    if not isinstance(value, dict):
        raise RegistryError(f"Registry field {field_name!r} must be an object of code -> description.")

    for code, description in value.items():
        if not isinstance(code, str) or not _CODE_PATTERN.match(code):
            raise RegistryError(
                f"Registry field {field_name!r} has an invalid code {code!r} "
                "(codes must be uppercase letters/digits only)."
            )
        if not isinstance(description, str) or not description.strip():
            raise RegistryError(
                f"Registry field {field_name!r} code {code!r} has a missing/empty description."
            )


def load_registry(path=None):
    """
    Loads and validates the registry. Raises RegistryError on anything
    that isn't a well-formed {"projects": {...}, "pcb_codes": {...}}
    document -- fail loud, since a malformed registry must never be
    silently treated as "no approved codes" or bypassed.
    """
    registry_path = resolve_registry_path(path)

    if not registry_path.exists():
        raise RegistryError(f"Customer Reference registry not found: {registry_path}")

    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RegistryError(f"Customer Reference registry is not valid JSON: {registry_path}") from exc

    if not isinstance(data, dict):
        raise RegistryError(f"Customer Reference registry must be a JSON object: {registry_path}")

    projects = data.get("projects", {})
    pcb_codes = data.get("pcb_codes", {})
    _validate_code_map(projects, "projects")
    _validate_code_map(pcb_codes, "pcb_codes")

    return {"projects": dict(projects), "pcb_codes": dict(pcb_codes)}


def get_projects(path=None):
    """{CODE: description} for every approved project code."""
    return load_registry(path)["projects"]


def get_pcb_codes(path=None):
    """{CODE: description} for every approved PCB code."""
    return load_registry(path)["pcb_codes"]


def is_approved_project(code, path=None):
    return str(code or "").strip().upper() in get_projects(path)


def is_approved_pcb_code(code, path=None):
    return str(code or "").strip().upper() in get_pcb_codes(path)


def _add_code(field_name, code, description, path=None):
    code = str(code or "").strip().upper()
    description = str(description or "").strip()

    if not _CODE_PATTERN.match(code):
        raise RegistryError(f"Invalid code {code!r}: codes must be uppercase letters/digits only.")
    if not description:
        raise RegistryError("A description is required.")

    registry_path = resolve_registry_path(path)
    registry = load_registry(registry_path) if registry_path.exists() else {"projects": {}, "pcb_codes": {}}

    if code in registry[field_name]:
        raise RegistryError(f"{code!r} is already an approved {field_name[:-1] if field_name.endswith('s') else field_name} code.")

    registry[field_name][code] = description
    atomic_write_json(registry_path, registry)
    return registry


def add_project(code, description, path=None):
    """
    Adds a newly-approved project code. Atomic write (see atomic_file.py)
    so a crash mid-write can never corrupt the registry other callers are
    reading. Raises RegistryError on an invalid code/description or a
    duplicate -- never silently overwrites an existing entry.
    """
    return _add_code("projects", code, description, path)


def add_pcb_code(code, description, path=None):
    """Adds a newly-approved PCB code. Same guarantees as add_project()."""
    return _add_code("pcb_codes", code, description, path)
