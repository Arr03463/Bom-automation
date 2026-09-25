"""
Production deployment preflight -- validates the running environment
without creating any vendor side effects (no cart, no MyList) and without
ever printing secret/token values. Runnable now against a local/simulated
production environment, and later against the real Yank PC deployment
with no code change (see Documentation/AutoBOM_Deployment_Guide.md).

Usage: `python src/deployment_preflight.py`
"""

import importlib.metadata
import os
import platform
import sys
from pathlib import Path

from dotenv import load_dotenv

from config_validation import (
    digikey_mylists_config_status,
    mouser_cart_config_status,
    partsbox_config_status,
)
from run_workspace import PROJECT_ROOT, resolve_runs_root
from supplier_lookup_cache import default_cache_path
from token_store import FileTokenStore, MemoryTokenStore, build_token_store

# Every vendor client module in this codebase loads .env at import time
# (see digikey_client.py, mouser_client.py, partsbox_client.py); this
# module has no such import, so it must do the same explicitly -- run
# standalone (`python src/deployment_preflight.py`), .env would otherwise
# never be loaded and every check would silently see an empty environment.
load_dotenv(PROJECT_ROOT / ".env", override=True)

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

_SEVERITY_ORDER = {PASS: 0, WARN: 1, FAIL: 2}

MINIMUM_PYTHON_VERSION = (3, 12)


def _check(name, status, detail):
    return {"name": name, "status": status, "detail": detail}


def _worst(statuses):
    return max(statuses, key=lambda status: _SEVERITY_ORDER[status]) if statuses else PASS


def _is_inside(path, ancestor):
    try:
        resolved_path = Path(path).resolve()
        resolved_ancestor = Path(ancestor).resolve()
    except OSError:
        return False
    return resolved_path == resolved_ancestor or resolved_ancestor in resolved_path.parents


def check_python_version():
    current = sys.version_info[:2]
    if current >= MINIMUM_PYTHON_VERSION:
        return _check("Python version", PASS, f"Running {platform.python_version()}")
    return _check(
        "Python version",
        WARN,
        f"Running {platform.python_version()}; tested/production target is "
        f"{'.'.join(map(str, MINIMUM_PYTHON_VERSION))}+.",
    )


def check_dependency_versions(lock_path=None):
    lock_path = Path(lock_path) if lock_path else PROJECT_ROOT / "requirements-lock.txt"
    if not lock_path.exists():
        return [_check("Dependency lock file", WARN, f"{lock_path} not found.")]

    checks = []
    for line in lock_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue

        name, _, expected_version = line.partition("==")
        name = name.strip()
        expected_version = expected_version.strip()
        try:
            installed_version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            checks.append(_check(f"Dependency: {name}", FAIL, f"expected {expected_version}, not installed"))
            continue

        if installed_version == expected_version:
            checks.append(_check(f"Dependency: {name}", PASS, installed_version))
        else:
            checks.append(
                _check(
                    f"Dependency: {name}",
                    WARN,
                    f"installed {installed_version}, lock expects {expected_version}",
                )
            )

    return checks


def check_writable_directory(name, directory):
    directory = Path(directory)
    probe_path = directory / f".preflight-{os.getpid()}.tmp"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe_path.write_text("preflight", encoding="utf-8")
        content = probe_path.read_text(encoding="utf-8")
        probe_path.unlink()
        if content != "preflight":
            return _check(name, FAIL, f"{directory}: read-back mismatch after write.")
        return _check(name, PASS, f"{directory}: writable.")
    except OSError as exc:
        return _check(name, FAIL, f"{directory}: not writable ({exc}).")
    finally:
        try:
            probe_path.unlink(missing_ok=True)
        except OSError:
            pass


def check_runs_root():
    return check_writable_directory("Runs directory", resolve_runs_root())


def check_cache_root():
    return check_writable_directory("Cache directory", default_cache_path().parent)


def check_logs_directory(logs_dir):
    """
    Only checked when AUTOBOM_LOGS_DIR is actually configured -- this
    codebase does not itself write log files (see the deployment guide's
    "Inspecting logs" section: stdout/stderr, captured by the host/service
    wrapper), so there is no default logs directory to assume.
    """
    if not logs_dir:
        return _check(
            "Logs directory",
            WARN,
            "AUTOBOM_LOGS_DIR is not set -- confirm the service wrapper "
            "captures stdout/stderr to a file with rotation instead.",
        )
    return check_writable_directory("Logs directory", logs_dir)


def check_file_token_store(directory):
    """
    Exercises the exact read/write/atomic-replace/lock mechanics
    FileTokenStore and its lock use, against a real directory. Never
    prints token contents -- only a fixed preflight probe value this
    function writes itself.
    """
    checks = []
    directory = Path(directory)

    try:
        directory.mkdir(parents=True, exist_ok=True)
        checks.append(_check("Token directory exists/creatable", PASS, str(directory)))
    except OSError as exc:
        checks.append(_check("Token directory exists/creatable", FAIL, f"{directory}: {exc}"))
        return checks

    store = FileTokenStore(directory)
    probe_key = f"_preflight_probe_{os.getpid()}"
    try:
        store.set(probe_key, "preflight-value")
        round_tripped = store.get(probe_key) == "preflight-value"
        checks.append(
            _check(
                "Token store read/write/atomic replace",
                PASS if round_tripped else FAIL,
                "round-trip succeeded" if round_tripped else "round-trip value mismatch",
            )
        )
    except OSError as exc:
        checks.append(_check("Token store read/write/atomic replace", FAIL, str(exc)))
    finally:
        try:
            (directory / probe_key).unlink(missing_ok=True)
        except OSError:
            pass

    lock = store.lock(timeout=5)
    try:
        acquired_inside = False
        with lock:
            acquired_inside = lock.acquired
        checks.append(
            _check(
                "Token store lock acquire/release",
                PASS if acquired_inside else FAIL,
                "acquired and released cleanly" if acquired_inside else "lock reported not acquired",
            )
        )
    except Exception as exc:  # noqa: BLE001 - preflight must report, not crash
        checks.append(_check("Token store lock acquire/release", FAIL, str(exc)))

    if _is_inside(directory, PROJECT_ROOT):
        checks.append(
            _check(
                "Token directory location",
                WARN,
                f"{directory} is inside the source checkout ({PROJECT_ROOT}) -- a "
                "release-folder replacement or `git clean` could remove it. Prefer "
                "a dedicated location outside the checkout for production (e.g. "
                "C:\\ProgramData\\AutoBOM\\tokens).",
            )
        )
    else:
        checks.append(
            _check("Token directory location", PASS, f"{directory} is outside the source checkout.")
        )

    return checks


def check_digikey_token_store_resolution():
    """
    Confirms the CONFIGURED backend actually resolves to what was
    requested -- build_token_store() silently falls back to
    MemoryTokenStore if DIGIKEY_TOKEN_STORE=file/http is set without its
    required path/URL, which would otherwise only be discovered after a
    restart drops the token.
    """
    requested = os.getenv("DIGIKEY_TOKEN_STORE", "").strip().lower()
    store = build_token_store()
    resolved_name = type(store).__name__

    if requested == "file" and isinstance(store, MemoryTokenStore):
        return _check(
            "DigiKey token store resolution",
            FAIL,
            "DIGIKEY_TOKEN_STORE=file but DIGIKEY_TOKEN_STORE_PATH is not set -- "
            "silently resolved to MemoryTokenStore (non-durable).",
        )
    if requested == "http" and isinstance(store, MemoryTokenStore):
        return _check(
            "DigiKey token store resolution",
            FAIL,
            "DIGIKEY_TOKEN_STORE=http but DIGIKEY_TOKEN_STORE_URL is not set -- "
            "silently resolved to MemoryTokenStore (non-durable).",
        )
    mylists_enabled = os.getenv("DIGIKEY_MYLISTS_ENABLED", "false").strip().lower() == "true"
    if mylists_enabled and isinstance(store, MemoryTokenStore):
        # Whatever combination of settings got here (explicit "memory",
        # nothing set, or an unrecognized backend name), the RESULT is
        # what matters: MemoryTokenStore is never durable across a
        # restart. EnvFileTokenStore/FileTokenStore are fine here even
        # though they weren't "explicitly requested" -- see
        # build_token_store()'s auto-selection.
        return _check(
            "DigiKey token store resolution",
            WARN,
            f"Resolved to {resolved_name} with DigiKey MyLists enabled -- not "
            "durable across a restart. See "
            "Documentation/AutoBOM_DigiKey_Durable_Token_Strategy.md.",
        )
    return _check("DigiKey token store resolution", PASS, f"Resolved to {resolved_name}.")


def check_production_development_separation():
    """
    Heuristic, not a guarantee: warns when this process's runs/cache/token
    locations all still point at defaults inside the checkout, which is
    correct for local development but is exactly the "developer checkout
    accidentally used for production" mistake §8 asks to guard against.
    Does not fail -- a genuinely small/simple deployment may legitimately
    accept this -- just makes the choice visible.
    """
    runs_root = resolve_runs_root()
    cache_root = default_cache_path().parent
    token_backend = os.getenv("DIGIKEY_TOKEN_STORE", "").strip().lower()

    all_in_checkout = _is_inside(runs_root, PROJECT_ROOT) and _is_inside(cache_root, PROJECT_ROOT)
    if all_in_checkout and token_backend in ("", "env_file"):
        return _check(
            "Production/development separation",
            WARN,
            "Runs, cache, and token store all resolve to locations inside/relative "
            "to this checkout -- appropriate for development, but a production "
            "deployment should set AUTOBOM_RUNS_ROOT, AUTOBOM_CACHE_ROOT, and "
            "DIGIKEY_TOKEN_STORE=file with a dedicated path outside the checkout.",
        )
    return _check(
        "Production/development separation",
        PASS,
        f"runs={runs_root}, cache={cache_root}, token_backend={token_backend or 'auto'}",
    )


def check_streamlit_production_settings():
    """
    Informational only: reports the Streamlit server settings that would
    actually be in effect (env vars take priority over any config file),
    so a production launch can be visually confirmed as NOT reusing the
    Dev Container's relaxed CORS/XSRF settings.
    """
    cors = os.getenv("STREAMLIT_SERVER_ENABLE_CORS", "").strip()
    xsrf = os.getenv("STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION", "").strip()
    headless = os.getenv("STREAMLIT_SERVER_HEADLESS", "").strip()
    port = os.getenv("STREAMLIT_SERVER_PORT", "").strip()
    address = os.getenv("STREAMLIT_SERVER_ADDRESS", "").strip()

    if cors.lower() == "false" or xsrf.lower() == "false":
        return _check(
            "Streamlit CORS/XSRF settings",
            WARN,
            f"STREAMLIT_SERVER_ENABLE_CORS={cors or 'unset'}, "
            f"STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION={xsrf or 'unset'} -- these "
            "should stay enabled (the default) in production; the Dev Container "
            "disables them for local preview convenience only.",
        )

    return _check(
        "Streamlit server settings",
        PASS,
        f"headless={headless or 'default'}, port={port or 'default'}, "
        f"address={address or 'default'}, CORS/XSRF left at secure defaults.",
    )


def run_preflight():
    """
    Runs every check that can be evaluated from this process/environment
    alone -- no vendor cart/MyList is created, no secret value is ever
    included in a check's detail string.
    """
    checks = []
    checks.append(check_python_version())
    checks.extend(check_dependency_versions())
    checks.append(check_runs_root())
    checks.append(check_cache_root())
    checks.append(check_logs_directory(os.getenv("AUTOBOM_LOGS_DIR", "").strip()))

    token_backend = os.getenv("DIGIKEY_TOKEN_STORE", "").strip().lower()
    if token_backend == "file":
        directory = os.getenv("DIGIKEY_TOKEN_STORE_PATH", "").strip()
        if directory:
            checks.extend(check_file_token_store(directory))
        else:
            checks.append(
                _check(
                    "Token directory",
                    FAIL,
                    "DIGIKEY_TOKEN_STORE=file but DIGIKEY_TOKEN_STORE_PATH is not set.",
                )
            )
    checks.append(check_digikey_token_store_resolution())
    checks.append(check_production_development_separation())
    checks.append(check_streamlit_production_settings())

    for status in (
        digikey_mylists_config_status(),
        mouser_cart_config_status(),
        partsbox_config_status(),
    ):
        if status.get("warning"):
            checks.append(_check("Vendor integration configuration", WARN, status["warning"]))

    overall = _worst([entry["status"] for entry in checks])
    return {"overall": overall, "checks": checks}


def format_report(result):
    lines = [f"AutoBOM deployment preflight: {result['overall']}", ""]
    for entry in result["checks"]:
        lines.append(f"[{entry['status']}] {entry['name']}: {entry['detail']}")
    return "\n".join(lines)


if __name__ == "__main__":
    report = run_preflight()
    print(format_report(report))
    sys.exit(1 if report["overall"] == FAIL else 0)
