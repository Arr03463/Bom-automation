"""
Static validation for the local one-click launcher (Start_AutoBOM.bat,
deploy/launch_local.ps1, deploy/launch_production.ps1,
Create_AutoBOM_Desktop_Shortcut.ps1). These are Windows batch/PowerShell
scripts, not Python -- this file checks their TEXT content for the
properties the launcher requirement actually cares about (self-locating,
no hardcoded user path, key safety behaviors present) and, where a
PowerShell interpreter is actually available, that they parse as valid
PowerShell. It does not execute them (that would start a real Streamlit
process / open a browser / touch the Desktop).
"""

import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

START_BAT = PROJECT_ROOT / "Start_AutoBOM.bat"
LAUNCH_LOCAL_PS1 = PROJECT_ROOT / "deploy" / "launch_local.ps1"
LAUNCH_PRODUCTION_PS1 = PROJECT_ROOT / "deploy" / "launch_production.ps1"
SHORTCUT_PS1 = PROJECT_ROOT / "Create_AutoBOM_Desktop_Shortcut.ps1"

ALL_SCRIPTS = [START_BAT, LAUNCH_LOCAL_PS1, LAUNCH_PRODUCTION_PS1, SHORTCUT_PS1]

# A hardcoded absolute Windows path would defeat "locate the repository
# based on its own location" -- this pattern would catch e.g.
# "C:\Users\AaronJones\..." appearing literally in a script.
_HARDCODED_ABSOLUTE_PATH = re.compile(r"[A-Za-z]:\\Users\\[^$\s\"']+")


class FilesExistTests(unittest.TestCase):
    def test_all_launcher_files_exist(self):
        for path in ALL_SCRIPTS:
            self.assertTrue(path.exists(), f"missing: {path}")


class NoHardcodedPathsTests(unittest.TestCase):
    def test_no_hardcoded_absolute_user_path(self):
        for path in ALL_SCRIPTS:
            content = path.read_text(encoding="utf-8")
            match = _HARDCODED_ABSOLUTE_PATH.search(content)
            self.assertIsNone(match, f"{path} appears to hardcode an absolute user path: {match}")


class BatchLauncherTests(unittest.TestCase):
    def setUp(self):
        self.content = START_BAT.read_text(encoding="utf-8")

    def test_locates_itself_via_percent_dp0(self):
        self.assertIn("%~dp0", self.content)

    def test_invokes_launch_local_powershell_script(self):
        self.assertIn("launch_local.ps1", self.content)

    def test_no_exit_flag_keeps_window_open_on_failure(self):
        self.assertIn("-NoExit", self.content)


class LaunchLocalTests(unittest.TestCase):
    def setUp(self):
        self.content = LAUNCH_LOCAL_PS1.read_text(encoding="utf-8")

    def test_repo_path_defaults_from_script_root_not_hardcoded(self):
        self.assertIn("$PSScriptRoot", self.content)

    def test_reuses_launch_production_script_rather_than_reimplementing(self):
        self.assertIn("launch_production.ps1", self.content)

    def test_forces_headless_so_streamlit_does_not_also_open_a_browser(self):
        self.assertIn("STREAMLIT_SERVER_HEADLESS", self.content)

    def test_polls_before_opening_browser(self):
        self.assertIn("Invoke-WebRequest", self.content)
        self.assertIn("Start-Process $url", self.content)
        # The poll must precede the browser-open in the script text --
        # opening the browser first and polling after would defeat the
        # "wait until actually responding" requirement.
        self.assertLess(self.content.index("Invoke-WebRequest"), self.content.index("Start-Process $url"))

    def test_keeps_window_open_on_failure_via_read_host(self):
        self.assertIn("Read-Host", self.content)

    def test_checks_for_venv_before_using_it(self):
        self.assertIn(".venv", self.content)
        self.assertIn("python.exe", self.content)

    def test_does_not_reference_purchasing_regeneration_or_vendor_cart_calls(self):
        # Starting the app must never itself create a cart/MyList or
        # regenerate purchasing artifacts -- those names should not
        # appear anywhere in the launcher at all.
        for forbidden in ("regenerate_purchasing", "create_mouser_cart_from_bom", "create_digikey_mylist_from_bom"):
            self.assertNotIn(forbidden, self.content)


class LaunchProductionReuseTests(unittest.TestCase):
    def setUp(self):
        self.content = LAUNCH_PRODUCTION_PS1.read_text(encoding="utf-8")

    def test_parameters_are_now_optional_with_computed_defaults(self):
        """
        This script must serve BOTH production (explicit paths) and
        local/operator use (defaults from its own location) -- it must
        not require -RepoPath/-VenvPath/-EnvFile to be mandatory anymore,
        or Start_AutoBOM.bat's zero-argument invocation would fail.
        """
        self.assertNotIn("Mandatory = $true", self.content)
        self.assertIn("$PSScriptRoot", self.content)

    def test_still_runs_preflight_before_starting_streamlit(self):
        self.assertIn("deployment_preflight.py", self.content)


class DesktopShortcutScriptTests(unittest.TestCase):
    def setUp(self):
        self.content = SHORTCUT_PS1.read_text(encoding="utf-8")

    def test_resolves_desktop_path_dynamically_not_hardcoded(self):
        self.assertIn('GetFolderPath("Desktop")', self.content)

    def test_points_shortcut_at_start_autobom_bat(self):
        self.assertIn("Start_AutoBOM.bat", self.content)

    def test_shortcut_name_is_autobom(self):
        self.assertIn('"AutoBOM"', self.content)


class PowerShellSyntaxTests(unittest.TestCase):
    """
    Best-effort: actually parses each .ps1 with the PowerShell language
    parser (no execution) when a PowerShell interpreter is on PATH.
    Skips cleanly on hosts without one (e.g. the Linux CI runner in
    .github/workflows/tests.yml) rather than failing the whole suite.
    """

    def _powershell_executable(self):
        for candidate in ("pwsh", "powershell", "powershell.exe"):
            found = shutil.which(candidate)
            if found:
                return found
        return None

    def test_scripts_parse_as_valid_powershell(self):
        exe = self._powershell_executable()
        if not exe:
            self.skipTest("No PowerShell interpreter on PATH in this environment.")

        for path in (LAUNCH_LOCAL_PS1, LAUNCH_PRODUCTION_PS1, SHORTCUT_PS1):
            command = (
                "$errors = $null; $tokens = $null; "
                f"[System.Management.Automation.Language.Parser]::ParseFile('{path}', [ref]$tokens, [ref]$errors) | Out-Null; "
                "if ($errors.Count -gt 0) { $errors | ForEach-Object { Write-Output $_.ToString() }; exit 1 } else { exit 0 }"
            )
            result = subprocess.run(
                [exe, "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, f"{path} failed to parse:\n{result.stdout}\n{result.stderr}")


if __name__ == "__main__":
    unittest.main()
