"""
Launch AutoBOM locally with production-LIKE configuration: separate
runs/cache/token directories outside the repo checkout, DIGIKEY_TOKEN_STORE
=file, and the production Streamlit config -- everything §17 asks for,
runnable on a developer machine right now, without touching whatever real
production directories eventually exist on the Yank PC (this defaults to
a location under the user's local temp/AppData, never a path resembling
the documented production layout).

This does NOT touch:
  - the developer's real .env / real DigiKey token store
  - runs/.cache inside the repo checkout
  - any real production directory

Usage:
    python deploy/run_local_production_like.py [--data-dir PATH] [--port 8501]

Then use deploy/local_restart_simulation.py (or just Ctrl-C and re-run
this script) to rehearse a restart against the same --data-dir.
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = Path(tempfile.gettempdir()) / "autobom-local-production-like"


def build_env(data_dir: Path, port: int) -> dict:
    env = dict(os.environ)
    runs_root = data_dir / "runs"
    cache_root = data_dir / "cache"
    token_dir = data_dir / "tokens"
    for path in (runs_root, cache_root, token_dir):
        path.mkdir(parents=True, exist_ok=True)

    env["AUTOBOM_RUNS_ROOT"] = str(runs_root)
    env["AUTOBOM_CACHE_ROOT"] = str(cache_root)
    env["DIGIKEY_TOKEN_STORE"] = "file"
    env["DIGIKEY_TOKEN_STORE_PATH"] = str(token_dir)
    env["STREAMLIT_SERVER_HEADLESS"] = "true"
    env["STREAMLIT_SERVER_PORT"] = str(port)
    env["STREAMLIT_SERVER_ADDRESS"] = "127.0.0.1"
    env["STREAMLIT_SERVER_ENABLE_CORS"] = "true"
    env["STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION"] = "true"
    # Deliberately do NOT set DIGIKEY_MYLISTS_ENABLED/MOUSER_CART_ENABLED
    # here -- this script controls WHERE state lives, not whether live
    # vendor calls happen. Those flags and real credentials still come
    # from whatever .env/environment this process already has (dry-run
    # by default unless the developer's real .env overrides it).
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip the preflight check (not recommended).",
    )
    args = parser.parse_args()

    print(f"Production-like data directory: {args.data_dir}")
    env = build_env(args.data_dir, args.port)

    if not args.skip_preflight:
        print("Running deployment preflight against this configuration...")
        preflight_result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "src" / "deployment_preflight.py")],
            cwd=str(PROJECT_ROOT),
            env=env,
        )
        if preflight_result.returncode != 0:
            print("Preflight reported FAIL. Not starting AutoBOM.", file=sys.stderr)
            sys.exit(preflight_result.returncode)

    print(f"Starting AutoBOM on http://127.0.0.1:{args.port} (production-like config)...")
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", "app.py"],
        cwd=str(PROJECT_ROOT),
        env=env,
    )


if __name__ == "__main__":
    main()
