# BOM Automation Tool

Internal BOM automation tool for cleaning designer BOMs, creating PartsBox project setup, sourcing parts through Mouser/DigiKey, and preparing supplier carts/lists.

## Current Capabilities

- Clean messy CSV/XLSX BOM files.
- Normalize manufacturer, MPN, designators, quantity, supplier, and supplier part number fields.
- Calculate required build quantities.
- Run Mouser and/or DigiKey sourcing checks.
- Use improved sourcing fallback logic:
  - exact MPN + manufacturer lookup
  - supplier part number fallback
  - relaxed manufacturer alias matching
  - duplicate candidate ranking by MPN, manufacturer, stock, active status, and price
  - DigiKey ProductDetails fallback to keyword search
- Create/reuse PartsBox project and storage location.
- Add BOM entries into PartsBox project.
- Create Mouser cart items when enabled.
- Export DigiKey list CSV every time sourcing is run.
- Create DigiKey MyList when enabled.
- Export cleaned BOM workbook, cleaned CSV, sourcing report, PartsBox CSVs, and run summary.

## Setup

Use Python 3.9+ from the project virtual environment. On Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Do not use the system `python` if it points to Python 2.

## Web App

Start the Streamlit UI:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Then open:

```text
http://localhost:8501
```

The web app lets you:

- Upload a `.csv` or `.xlsx` BOM.
- Set build quantity.
- Enter PartsBox project name and description.
- Toggle `Run PartsBox`.
- Toggle `Run supplier sourcing`.
- Toggle `Use Mouser sourcing`.
- Toggle `Use DigiKey sourcing`.
- Toggle `Create Mouser cart`.
- Toggle `Create DigiKey MyList`.
- Download created outputs.

Important toggle behavior:

- `Use Mouser sourcing` controls Mouser lookup.
- `Create Mouser cart` only controls Mouser cart upload.
- `Use DigiKey sourcing` controls DigiKey lookup.
- `Create DigiKey MyList` only controls remote DigiKey MyList creation.
- If `Run supplier sourcing` is unchecked, supplier lookups are skipped.

## CLI

The original CLI flow is still available:

```powershell
.\.venv\Scripts\python.exe src\main.py
```

The CLI uses `SUPPLIER_MODE` from `.env`:

- `mouser_then_digikey`
- `digikey_only`

## Reusable Workflow

The web app calls `run_bom_workflow()` from `src/workflow_runner.py`.

```python
from workflow_runner import run_bom_workflow

result = run_bom_workflow(
    source_file_path="input/test_bom2.csv",
    build_quantity=1,
    project_name="Example Project",
    project_description="Optional description",
    run_partsbox=True,
    run_sourcing=True,
    run_mouser_cart=False,
    run_digikey_mylist=False,
    use_mouser_sourcing=True,
    use_digikey_sourcing=True,
)
```

The function returns a structured dictionary with:

- `success`
- `errors`
- `warnings`
- `summary`
- `outputs`
- `messages`

## Environment Variables

Store secrets in `.env`. Do not commit `.env`.

Common settings:

```env
PARTSBOX_API_KEY=
PARTSBOX_DRY_RUN=true

SUPPLIER_DRY_RUN=true
SUPPLIER_MODE=mouser_then_digikey

MOUSER_SEARCH_API_KEY=
MOUSER_CART_API_KEY=
MOUSER_CART_ENABLED=false
MOUSER_CART_DRY_RUN=true
MOUSER_BASE_URL=https://api.mouser.com
MOUSER_SEARCH_DELAY_SECONDS=2.1
MOUSER_RATE_LIMIT_RETRY_SECONDS=65
MOUSER_RATE_LIMIT_RETRIES=1

SUPPLIER_LOOKUP_CACHE_ENABLED=true
SUPPLIER_LOOKUP_CACHE_PATH=.cache/supplier_lookup_cache.json

DIGIKEY_CLIENT_ID=
DIGIKEY_CLIENT_SECRET=
DIGIKEY_BASE_URL=https://api.digikey.com
DIGIKEY_TOKEN_URL=https://api.digikey.com/v1/oauth2/token
DIGIKEY_MYLISTS_ENABLED=false
DIGIKEY_REFRESH_TOKEN=
DIGIKEY_ACCESS_TOKEN=
```

Dry-run notes:

- `SUPPLIER_DRY_RUN=true` uses mock supplier lookup data.
- `PARTSBOX_DRY_RUN=true` prevents real PartsBox writes.
- `MOUSER_CART_DRY_RUN=true` prepares cart payloads without uploading them.
- DigiKey MyLists uses `SUPPLIER_DRY_RUN` for dry-run behavior.

## DigiKey MyLists OAuth

DigiKey MyLists requires 3-legged OAuth. If MyList creation fails with `Invalid RefreshToken`, refresh the token:

```powershell
.\.venv\Scripts\python.exe src\digikey_oauth_setup.py
```

After approving access in the browser, paste the redirected URL back into the terminal.

Verify the token:

```powershell
.\.venv\Scripts\python.exe src\digikey_oauth_setup.py --check
```

If the check succeeds, restart Streamlit before running the web flow again.

## Outputs

Generated files are written to `output/`, including:

- cleaned BOM workbook
- cleaned BOM CSV
- sourcing report
- DigiKey list CSV
- PartsBox import CSV
- PartsBox unmatched CSV
- run summary JSON

`output/` is ignored by Git.

Supplier lookup cache is written to:

```text
.cache/supplier_lookup_cache.json
```

The cache stores successful Mouser/DigiKey lookup results by supplier, manufacturer, MPN, and supplier part number. Repeated parts in the same BOM are deduplicated during a run, and later runs can reuse cached successful results. `.cache/` is ignored by Git.

To disable persistent supplier cache:

```env
SUPPLIER_LOOKUP_CACHE_ENABLED=false
```

## Inputs And Git Tracking

The `input/` folder is ignored by Git except test BOM files:

```text
input/test_bom*.csv
```

This keeps local/customer BOMs out of Git while allowing test fixtures to stay versioned.

## Testing

Run sourcing accuracy tests:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_sourcing_accuracy
```

Compile-check core files:

```powershell
.\.venv\Scripts\python.exe -m py_compile app.py src\workflow_runner.py src\sourcing_engine.py src\mouser_client.py src\digikey_client.py
```

## Troubleshooting

If Mouser sourcing returns `TooManyRequests`, increase:

```env
MOUSER_SEARCH_DELAY_SECONDS=2.5
MOUSER_RATE_LIMIT_RETRY_SECONDS=65
```

If output export fails with `Permission denied`, close the output CSV/XLSX in Excel and rerun.

If web behavior does not match recent code or `.env` changes, restart Streamlit.
