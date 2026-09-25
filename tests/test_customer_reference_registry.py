import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from customer_reference_registry import (
    RegistryError,
    add_pcb_code,
    add_project,
    get_pcb_codes,
    get_projects,
    is_approved_pcb_code,
    is_approved_project,
    load_registry,
)


class RegistryTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="autobom_registry_test_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.registry_path = self.temp_dir / "registry.json"

    def write_registry(self, projects=None, pcb_codes=None):
        self.registry_path.write_text(
            json.dumps({"projects": projects or {}, "pcb_codes": pcb_codes or {}}),
            encoding="utf-8",
        )


class LoadRegistryTests(RegistryTestCase):
    def test_loads_projects_and_pcb_codes(self):
        self.write_registry(projects={"ARM": "NASA P3 (Armstrong)"}, pcb_codes={"DAB": "Dual Active Bridge"})

        registry = load_registry(self.registry_path)

        self.assertEqual(registry["projects"], {"ARM": "NASA P3 (Armstrong)"})
        self.assertEqual(registry["pcb_codes"], {"DAB": "Dual Active Bridge"})

    def test_missing_file_raises(self):
        with self.assertRaises(RegistryError):
            load_registry(self.temp_dir / "does-not-exist.json")

    def test_corrupt_json_raises_not_silently_empty(self):
        self.registry_path.write_text("{not valid json", encoding="utf-8")

        with self.assertRaises(RegistryError):
            load_registry(self.registry_path)

    def test_non_object_root_raises(self):
        self.registry_path.write_text("[1, 2, 3]", encoding="utf-8")

        with self.assertRaises(RegistryError):
            load_registry(self.registry_path)

    def test_lowercase_code_raises(self):
        self.write_registry(projects={"arm": "lowercase code"})

        with self.assertRaises(RegistryError):
            load_registry(self.registry_path)

    def test_empty_description_raises(self):
        self.write_registry(projects={"ARM": ""})

        with self.assertRaises(RegistryError):
            load_registry(self.registry_path)

    def test_default_repo_registry_loads_and_includes_dab_and_buzz(self):
        # Exercises the actual shipped config/customer_reference_registry.json.
        pcb_codes = get_pcb_codes()
        self.assertIn("DAB", pcb_codes)
        self.assertIn("BUZZ", pcb_codes)
        self.assertEqual(pcb_codes["DAB"], "Dual Active Bridge")
        self.assertEqual(pcb_codes["BUZZ"], "Bus Bar")

    def test_default_repo_registry_preserves_existing_approved_pcb_codes(self):
        pcb_codes = get_pcb_codes()
        for expected in ("BOOST", "AMP", "TXCTR", "MINI", "TXTER", "RXTER", "REC", "BUCK", "PDU", "RXCTR", "MISC"):
            self.assertIn(expected, pcb_codes)

    def test_default_repo_registry_has_expected_projects(self):
        projects = get_projects()
        for expected in ("ARM", "ALD", "COL", "SPAR", "ATH", "TBCA", "SNAP", "MOM"):
            self.assertIn(expected, projects)


class IsApprovedTests(RegistryTestCase):
    def test_is_approved_project_case_insensitive(self):
        self.write_registry(projects={"ARM": "desc"})
        self.assertTrue(is_approved_project("arm", self.registry_path))
        self.assertFalse(is_approved_project("xyz", self.registry_path))

    def test_is_approved_pcb_code(self):
        self.write_registry(pcb_codes={"DAB": "desc"})
        self.assertTrue(is_approved_pcb_code("DAB", self.registry_path))
        self.assertFalse(is_approved_pcb_code("NEWCODE", self.registry_path))


class AddCodeTests(RegistryTestCase):
    def test_add_project_persists_and_is_readable(self):
        self.write_registry(projects={"ARM": "existing"})

        add_project("NEWPROJ", "A brand new project", self.registry_path)

        self.assertTrue(is_approved_project("NEWPROJ", self.registry_path))
        self.assertEqual(get_projects(self.registry_path)["NEWPROJ"], "A brand new project")
        # Existing entries are preserved, not wiped.
        self.assertTrue(is_approved_project("ARM", self.registry_path))

    def test_add_pcb_code_persists(self):
        self.write_registry(pcb_codes={"DAB": "existing"})

        add_pcb_code("NEWPCB", "A brand new PCB", self.registry_path)

        self.assertTrue(is_approved_pcb_code("NEWPCB", self.registry_path))

    def test_add_project_creates_registry_if_missing(self):
        # No write_registry() call -- the file doesn't exist yet.
        add_project("FIRSTPROJ", "First ever project", self.registry_path)

        self.assertTrue(self.registry_path.exists())
        self.assertTrue(is_approved_project("FIRSTPROJ", self.registry_path))

    def test_add_project_rejects_duplicate_code(self):
        self.write_registry(projects={"ARM": "existing"})

        with self.assertRaises(RegistryError):
            add_project("ARM", "duplicate", self.registry_path)

    def test_add_project_rejects_invalid_code_characters(self):
        self.write_registry()

        with self.assertRaises(RegistryError):
            add_project("bad-code!", "invalid", self.registry_path)

    def test_add_project_rejects_empty_description(self):
        self.write_registry()

        with self.assertRaises(RegistryError):
            add_project("VALIDCODE", "", self.registry_path)

    def test_add_project_normalizes_code_to_uppercase(self):
        self.write_registry()

        add_project("lowercase", "desc", self.registry_path)

        self.assertTrue(is_approved_project("LOWERCASE", self.registry_path))

    def test_new_project_does_not_require_generator_changes(self):
        """
        The whole point of the registry: adding a code here must not
        require touching customer_reference.py's generator. Prove a
        never-before-seen project code round-trips through the
        generator with zero special-casing.
        """
        from customer_reference import build_project_reference

        self.write_registry()
        add_project("BRANDNEWCODE", "Some future project", self.registry_path)

        self.assertTrue(is_approved_project("BRANDNEWCODE", self.registry_path))
        self.assertEqual(
            build_project_reference("BRANDNEWCODE", ["MISC"]), "PRJ-BRANDNEWCODE-MISC"
        )


if __name__ == "__main__":
    unittest.main()
