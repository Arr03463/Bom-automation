"""
Storage-space classification (Development / Project / Mechanical /
Other) for PartsBox storage locations -- shared by PartsBox Inventory,
enriched Main Search results, and the inventory-location recommender, so
none of them invents its own rule set.

Rules live in config/storage_space_rules.json, not in this module --
adding a Mechanical or Development tag convention later is a config
edit, not a code change (see that file's own "notes" field for why the
Project rule is the only one backed by confirmed live evidence today).
"""

import json
from pathlib import Path

from partsbox_project_builder import PRODUCTION_STORAGE_TAG, storage_has_tag

DEVELOPMENT = "Development"
PROJECT = "Project"
MECHANICAL = "Mechanical"
OTHER = "Other"

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "storage_space_rules.json"


def load_storage_space_rules(config_path=None):
    path = Path(config_path) if config_path else CONFIG_PATH
    with path.open("r", encoding="utf-8") as config_file:
        return json.load(config_file)


def classify_storage(storage_record, project_names, rules=None):
    """
    storage_record: one storage/all record.
    project_names: iterable of project names (any case/whitespace --
        normalized here) used for the verified "production tag + same
        name as an existing project" Project rule.
    rules: a pre-loaded config/storage_space_rules.json dict, to avoid
        re-reading the file once per storage record when classifying an
        entire snapshot; loaded fresh when omitted.

    Precedence: Project (the one confirmed-live rule) -> configured
    Mechanical tags -> configured Development tags -> the config's
    default_classification. Never guesses beyond what the config/tags
    actually say.
    """
    rules = rules if rules is not None else load_storage_space_rules()
    normalized_project_names = {str(name).strip().lower() for name in project_names}
    storage_name = str(storage_record.get("storage/name") or storage_record.get("name") or "").strip().lower()

    if storage_name and storage_name in normalized_project_names and storage_has_tag(
        storage_record, PRODUCTION_STORAGE_TAG
    ):
        return PROJECT

    if _has_any_tag(storage_record, rules.get("mechanical_tags", [])):
        return MECHANICAL

    if _has_any_tag(storage_record, rules.get("development_tags", [])):
        return DEVELOPMENT

    return rules.get("default_classification", OTHER)


def _has_any_tag(storage_record, tags):
    return any(storage_has_tag(storage_record, tag) for tag in tags)
