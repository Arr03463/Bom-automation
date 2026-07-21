# AutoBOM startup cheat sheet

Run commands from the repository root unless a step says otherwise.

## First-time setup

You need Python 3.11+, Node.js 20+, npm, and Git. PostgreSQL 15+ is needed only when you want database-backed features.

### Windows PowerShell

```powershell
py -3.12 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
Set-Location frontend
npm install
Set-Location ..
Copy-Item .env.example .env   # Skip this if .env already exists
```

### macOS, Linux, or Git Bash

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
cd frontend && npm install && cd ..
cp .env.example .env          # Skip this if .env already exists
```

Never commit `.env` or paste its secret values into logs or issues.

## Configure the environment

Edit `.env` in the repository root. For the simplest local mode, use:

```dotenv
ENV=development
BACKEND_URL=http://localhost:8000
FRONTEND_URL=http://localhost:3000
SESSION_SECRET=replace-with-a-long-random-string
```

The other settings are optional by capability:

| Feature | Variables to configure | If omitted or left as placeholders |
|---|---|---|
| PostgreSQL | `DATABASE_URL` | Database is reported as not configured |
| PartsBox | `PARTSBOX_API_KEY` | PartsBox calls are disabled |
| Mouser search/cart | `MOUSER_SEARCH_API_KEY`, `MOUSER_CART_API_KEY` | Corresponding calls are disabled |
| DigiKey | `DIGIKEY_CLIENT_ID`, `DIGIKEY_CLIENT_SECRET` | DigiKey calls are disabled |
| Microsoft login | `AZURE_TENANT_ID`, `AZURE_AD_CLIENT_ID`, `AZURE_AD_CLIENT_SECRET` | Local seed-user login is used |
| Purchasing sheet | Microsoft Graph variables plus `ONEDRIVE_PURCHASING_SHEET_ID` | Writes are logged to the console |

Use `.env.local` for personal overrides; its values take precedence over `.env`. The complete variable list and comments are in `.env.example`.

Keep `FLUSH_MODE=dry_run` (the default) while configuring integrations. Change it to `live` only when you intentionally want bucket flushes to modify external systems.

## Start the program

### Windows PowerShell

```powershell
pwsh scripts/dev.ps1
```

This opens the backend and frontend in separate PowerShell windows. Stop them with `Ctrl+C` in each window, or close both windows.

### macOS, Linux, or Git Bash

```bash
bash scripts/dev.sh
```

Stop both servers with `Ctrl+C`.

Then open:

- App: http://localhost:3000
- Backend health: http://localhost:8000/api/health

In local mode, choose a seed user on the login screen. Examples:

- `aaron.jones@yanktech.com` — Designer
- `maria.chen@yanktech.com` — Production
- `grace.hill@yanktech.com` — Admin

## Optional PostgreSQL setup

After PostgreSQL is installed and running, create the databases, then migrate and seed the development database:

```powershell
createdb autobom_local
createdb autobom_test
Set-Location backend
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m db.seed
Set-Location ..
```

Make sure `DATABASE_URL` in `.env` matches your PostgreSQL host, port, database, username, and password.

## Quick troubleshooting

- Backend will not start: confirm `backend/.venv` exists and dependencies were installed.
- Frontend will not start: run `npm install` inside `frontend`.
- Vite reports an esbuild binary error: run `node node_modules/esbuild/install.js` inside `frontend`.
- Port already in use: stop the process using port 3000 or 8000, then launch again.
- Check active modes without exposing secrets: open `http://localhost:8000/api/health`.
- Run backend tests: `Set-Location backend; .venv/Scripts/python.exe -m pytest tests`.
