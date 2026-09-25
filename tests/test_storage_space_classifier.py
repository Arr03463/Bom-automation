import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from storage_space_classifier import (
    DEVELOPMENT,
    MECHANICAL,
    OTHER,
    PROJECT,
    classify_storage,
    load_storage_space_rules,
)

DEFAULT_RULES = {
    "default_classification": "Development",
    "mechanical_tags": [],
    "development_tags": [],
}


class ClassifyStorageTests(unittest.TestCase):
    def test_production_tag_plus_matching_project_name_is_project(self):
        storage = {"storage/name": "Army Battery", "storage/tags": ["production"]}
        result = classify_storage(storage, project_names=["Army Battery"], rules=DEFAULT_RULES)
        self.assertEqual(result, PROJECT)

    def test_production_tag_without_matching_project_name_is_not_project(self):
        storage = {"storage/name": "C1 - Resistors", "storage/tags": ["production"]}
        result = classify_storage(storage, project_names=["Army Battery"], rules=DEFAULT_RULES)
        self.assertNotEqual(result, PROJECT)

    def test_matching_name_without_production_tag_is_not_project(self):
        """
        Name alone is not enough -- the verified convention requires
        BOTH the production tag and the same-name project relationship.
        """
        storage = {"storage/name": "Army Battery", "storage/tags": []}
        result = classify_storage(storage, project_names=["Army Battery"], rules=DEFAULT_RULES)
        self.assertNotEqual(result, PROJECT)

    def test_project_name_match_is_case_and_whitespace_insensitive(self):
        storage = {"storage/name": "  ARMY BATTERY  ", "storage/tags": ["production"]}
        result = classify_storage(storage, project_names=["army battery"], rules=DEFAULT_RULES)
        self.assertEqual(result, PROJECT)

    def test_configured_mechanical_tag_classifies_mechanical(self):
        rules = {**DEFAULT_RULES, "mechanical_tags": ["mechanical"]}
        storage = {"storage/name": "Enclosure Bin", "storage/tags": ["Mechanical"]}
        result = classify_storage(storage, project_names=[], rules=rules)
        self.assertEqual(result, MECHANICAL)

    def test_configured_development_tag_classifies_development(self):
        rules = {**DEFAULT_RULES, "development_tags": ["dev"], "default_classification": "Other"}
        storage = {"storage/name": "R&D Wall", "storage/tags": ["dev"]}
        result = classify_storage(storage, project_names=[], rules=rules)
        self.assertEqual(result, DEVELOPMENT)

    def test_unclassified_storage_falls_back_to_configured_default(self):
        storage = {"storage/name": "C2 - Capacitors", "storage/tags": []}
        result = classify_storage(storage, project_names=[], rules=DEFAULT_RULES)
        self.assertEqual(result, DEVELOPMENT)

    def test_default_can_be_configured_to_other(self):
        rules = {**DEFAULT_RULES, "default_classification": "Other"}
        storage = {"storage/name": "Unlabeled Bin", "storage/tags": []}
        result = classify_storage(storage, project_names=[], rules=rules)
        self.assertEqual(result, OTHER)

    def test_mechanical_precedes_default_development(self):
        rules = {**DEFAULT_RULES, "mechanical_tags": ["mech"]}
        storage = {"storage/name": "Bin 4", "storage/tags": ["mech"]}
        result = classify_storage(storage, project_names=[], rules=rules)
        self.assertEqual(result, MECHANICAL)

    def test_project_precedes_mechanical(self):
        rules = {**DEFAULT_RULES, "mechanical_tags": ["production"]}
        storage = {"storage/name": "Army Battery", "storage/tags": ["production"]}
        result = classify_storage(storage, project_names=["Army Battery"], rules=rules)
        self.assertEqual(result, PROJECT)


class LoadStorageSpaceRulesTests(unittest.TestCase):
    def test_real_config_file_loads_and_has_required_keys(self):
        rules = load_storage_space_rules()
        self.assertIn("default_classification", rules)
        self.assertIn("mechanical_tags", rules)
        self.assertIn("development_tags", rules)
        self.assertIn(rules["default_classification"], {"Development", "Project", "Mechanical", "Other"})

    def test_real_config_mechanical_and_development_tags_start_empty(self):
        """
        Regression guard: the config's own docstring/notes explain these
        lists start empty because no tag convention is confirmed live --
        a future edit to that file should be a deliberate, documented
        choice, not an accidental one this test would silently accept.
        """
        rules = load_storage_space_rules()
        self.assertEqual(rules["mechanical_tags"], [])
        self.assertEqual(rules["development_tags"], [])


if __name__ == "__main__":
    unittest.main()
