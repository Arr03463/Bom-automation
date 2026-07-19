import os
import secrets
import sys
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"

load_dotenv(ENV_PATH, override=True)


def main():
    if len(sys.argv) > 1 and sys.argv[1].strip().lower() in {"--check", "check"}:
        check_existing_refresh_token()
        return

    client_id = os.getenv("DIGIKEY_CLIENT_ID", "").strip()
    client_secret = os.getenv("DIGIKEY_CLIENT_SECRET", "").strip()
    token_url = os.getenv("DIGIKEY_TOKEN_URL", "https://api.digikey.com/v1/oauth2/token").strip()
    redirect_uri = os.getenv("DIGIKEY_REDIRECT_URI", "https://localhost").strip()

    if not client_id or not client_secret:
        raise ValueError("Missing DIGIKEY_CLIENT_ID or DIGIKEY_CLIENT_SECRET in .env")

    state = secrets.token_urlsafe(16)
    authorize_url = "https://api.digikey.com/v1/oauth2/authorize?" + urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
        }
    )

    if len(sys.argv) > 1:
        redirected_url = sys.argv[1].strip()
    else:
        print("Opening DigiKey authorization page...")
        print("After approving access, Chrome may show 'localhost refused to connect'.")
        print("That is expected. Copy the full URL from the address bar and paste it here.")
        print()
        print(authorize_url)
        print()

        webbrowser.open(authorize_url)
        redirected_url = input("Paste redirected URL: ").strip()
    query = parse_qs(urlparse(redirected_url).query)

    returned_state = _first(query, "state")
    if returned_state and returned_state != state:
        raise ValueError("OAuth state did not match. Try again from a fresh authorization URL.")

    error = _first(query, "error")
    if error:
        raise ValueError(f"DigiKey authorization failed: {error}")

    code = _first(query, "code")
    if not code:
        raise ValueError("No authorization code found in pasted URL.")

    response = requests.post(
        token_url,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    if response.status_code >= 400:
        print("DigiKey token exchange failed.")
        print(response.text)

    response.raise_for_status()

    token_data = response.json()
    refresh_token = token_data.get("refresh_token", "").strip()
    access_token = token_data.get("access_token", "").strip()

    if not refresh_token:
        raise ValueError("DigiKey did not return a refresh token.")

    _set_env_value("DIGIKEY_REDIRECT_URI", redirect_uri)
    _set_env_value("DIGIKEY_REFRESH_TOKEN", refresh_token)
    _set_env_value("DIGIKEY_MYLISTS_ENABLED", "true")

    print()
    print("DigiKey OAuth setup complete.")
    print("Saved DIGIKEY_REFRESH_TOKEN in .env.")
    if access_token:
        print("Received access token too, but only the refresh token was saved.")


def _first(query, name):
    values = query.get(name) or []
    return values[0] if values else ""


def _set_env_value(name, value):
    env_path = ENV_PATH
    lines = env_path.read_text().splitlines() if env_path.exists() else []

    for index, line in enumerate(lines):
        if line.strip().startswith("#") or "=" not in line:
            continue

        key, _ = line.split("=", 1)
        if key.strip() == name:
            lines[index] = f"{name}={value}"
            env_path.write_text("\n".join(lines) + "\n")
            return

    lines.append(f"{name}={value}")
    env_path.write_text("\n".join(lines) + "\n")


def check_existing_refresh_token():
    client_id = os.getenv("DIGIKEY_CLIENT_ID", "").strip()
    client_secret = os.getenv("DIGIKEY_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("DIGIKEY_REFRESH_TOKEN", "").strip()
    token_url = os.getenv("DIGIKEY_TOKEN_URL", "https://api.digikey.com/v1/oauth2/token").strip()

    if not client_id or not client_secret:
        raise ValueError("Missing DIGIKEY_CLIENT_ID or DIGIKEY_CLIENT_SECRET in .env")

    if not refresh_token:
        raise ValueError("Missing DIGIKEY_REFRESH_TOKEN in .env")

    response = requests.post(
        token_url,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )

    if response.status_code >= 400:
        print("DigiKey refresh token check failed.")
        print(response.text)
        response.raise_for_status()

    token_data = response.json()
    new_refresh_token = token_data.get("refresh_token", "").strip()
    access_token = token_data.get("access_token", "").strip()

    if new_refresh_token and new_refresh_token != refresh_token:
        _set_env_value("DIGIKEY_REFRESH_TOKEN", new_refresh_token)
        print("DigiKey refresh token is valid. Saved rotated refresh token in .env.")
    else:
        print("DigiKey refresh token is valid.")

    if access_token:
        print("Received a user access token.")


if __name__ == "__main__":
    main()
