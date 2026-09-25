"""
Customer Reference / Customer Part Number generation and validation, per
the Yank naming-convention SOP (YT-SOP-00-01-A):

- Inventory Restock:      INV-<LOCATION>
- Project / PCB:          PRJ-<PROJECT>-<PCB_CODE>[_<PCB_CODE>...]
- Research & Development: RND-<PROJECT>-<OWNER>

Format/rules are stable (uppercase, no spaces, hyphen-separated major
fields, underscore-joined PCB codes, 30-character maximum). The approved
Project/PCB code *values* are not stable -- see customer_reference_registry.py.
This module never encodes a fixed list of allowed codes; it only checks
shape/length, so a newly-approved registry code works here with zero
changes.
"""

from dataclasses import dataclass, field

MAX_LENGTH = 30

_ALLOWED_CHAR_MESSAGE = "may only contain uppercase letters, digits, hyphens, and underscores"


@dataclass
class ValidationResult:
    value: str
    valid: bool
    length: int
    errors: list = field(default_factory=list)


def normalize_component(value):
    """
    Uppercase + trim leading/trailing whitespace only -- never silently
    strips internal spaces or invents an abbreviation. A value with
    internal spaces or disallowed characters is caught by
    validate_customer_reference(), not quietly repaired here.
    """
    return str(value or "").strip().upper()


def build_inventory_reference(location):
    return f"INV-{normalize_component(location)}"


def build_project_reference(project_code, pcb_codes):
    """
    pcb_codes: an ordered list of one or more PCB codes. Order is
    preserved exactly as given (the caller's selection order) -- this
    function invents no ordering rule of its own, per instruction not to
    guess at an ordering convention beyond what the operator selected.
    """
    project = normalize_component(project_code)
    pcbs = "_".join(normalize_component(code) for code in pcb_codes if str(code or "").strip())
    return f"PRJ-{project}-{pcbs}"


def build_rnd_reference(project_code, owner):
    project = normalize_component(project_code)
    owner_value = normalize_component(owner)
    return f"RND-{project}-{owner_value}"


def validate_customer_reference(value):
    """
    Shape/length validation only -- never fixes the value up. A too-long
    or malformed reference is returned as invalid with an explanatory
    error, for the caller (UI) to show the operator, per the SOP's own
    instruction not to silently shorten or invent abbreviations.
    """
    value = str(value or "")
    errors = []

    if not value:
        errors.append("Customer Reference cannot be empty.")
    else:
        if value != value.strip():
            errors.append("Customer Reference has leading/trailing whitespace.")
        if " " in value:
            errors.append("Customer Reference cannot contain spaces.")
        if value != value.upper():
            errors.append("Customer Reference must be uppercase.")
        if not all(ch.isalnum() or ch in "-_" for ch in value):
            errors.append(f"Customer Reference {_ALLOWED_CHAR_MESSAGE}.")
        if not value.startswith(("INV-", "PRJ-", "RND-")):
            errors.append("Customer Reference must start with INV-, PRJ-, or RND-.")

    if len(value) > MAX_LENGTH:
        errors.append(f"Maximum length is {MAX_LENGTH} characters.")

    return ValidationResult(value=value, valid=not errors, length=len(value), errors=errors)
