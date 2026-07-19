"""AutoBOM backend entry point.

Run locally from the backend/ directory:

    cd backend
    python main.py            # http://localhost:8000  (auto-reload)

This adds backend/ to sys.path so `config`, `api`, and `app` import as
top-level packages regardless of the caller's working directory.
"""

import sys
from pathlib import Path

# Make backend/ the import root (so `cd backend && python main.py` works, and
# so it also works when invoked from the repo root).
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import logging

import uvicorn

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main() -> None:
    # Pass the import string (not the app object) so --reload can re-import.
    uvicorn.run(
        "app.factory:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=[str(BACKEND_DIR)],
    )


if __name__ == "__main__":
    main()
