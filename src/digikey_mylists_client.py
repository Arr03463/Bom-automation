import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv

from digikey_client import DigiKeyClient
from http_error_utils import describe_error_response
from http_error_utils import raise_for_status as _raise_for_status

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=True)


class DigiKeyMyListsClient:
    def __init__(self):
        load_dotenv(PROJECT_ROOT / ".env", override=True)

        self.base_url = os.getenv("DIGIKEY_BASE_URL", "https://api.digikey.com").strip()
        self.client_id = os.getenv("DIGIKEY_CLIENT_ID", "").strip()
        self.account_id = os.getenv("DIGIKEY_ACCOUNT_ID", "").strip()
        self.enabled = os.getenv("DIGIKEY_MYLISTS_ENABLED", "false").lower() == "true"
        self.dry_run = os.getenv("SUPPLIER_DRY_RUN", "true").lower() == "true"

        self.auth_client = DigiKeyClient()

    def validate_config(self):
        if not self.enabled:
            raise ValueError("DIGIKEY_MYLISTS_ENABLED is not true in .env")

        if not self.client_id:
            raise ValueError("Missing DIGIKEY_CLIENT_ID in .env")

    def headers(self):
        token = self.auth_client.get_user_access_token()

        headers = {
            "Authorization": f"Bearer {token}",
            "X-DIGIKEY-Client-Id": self.client_id,
            "Content-Type": "application/json",
        }

        if self.account_id:
            headers["X-DIGIKEY-Account-Id"] = self.account_id

        return headers

    def is_list_name_available(self, list_name):
        self.validate_config()

        if self.dry_run:
            return True

        encoded_name = quote(list_name, safe="")
        url = f"{self.base_url}/mylists/v1/lists/validate/{encoded_name}"

        response = requests.get(
            url,
            headers=self.headers(),
            timeout=30,
        )

        if response.status_code >= 400:
            print("DigiKey IsValidListName response:", describe_error_response(response))

        _raise_for_status(response, "DigiKey MyLists name validation failed")
        result = response.json()

        if isinstance(result, bool):
            return result

        return str(result).strip().lower() == "true"

    def get_valid_list_name(self, list_name):
        self.validate_config()

        if self.dry_run:
            return list_name

        encoded_name = quote(list_name, safe="")
        url = f"{self.base_url}/mylists/v1/lists/validate/name/{encoded_name}"

        response = requests.get(
            url,
            headers=self.headers(),
            timeout=30,
        )

        if response.status_code >= 400:
            print("DigiKey ValidListName response:", describe_error_response(response))

        _raise_for_status(response, "DigiKey MyLists valid-name request failed")
        result = response.json()

        if isinstance(result, str) and result.strip():
            return result.strip()

        return list_name

    def resolve_create_list_name(self, list_name):
        self.validate_config()

        if self.dry_run or self.is_list_name_available(list_name):
            return list_name, False

        timestamped_name = build_timestamped_list_name(list_name)
        safe_name = self.get_valid_list_name(timestamped_name)
        return safe_name, True

    def create_list(self, list_name, description="Created by BOM automation tool"):
        self.validate_config()

        payload = {
            "ListName": list_name,
            "CreatedBy": description,
            "Source": "external",
        }

        if self.dry_run:
            print("\n[DIGIKEY MYLISTS DRY RUN] Would create list")
            print("Payload:", payload)
            return {
                "dry_run": True,
                "ListId": "dry-run-list-id",
                "ListName": list_name,
            }

        url = f"{self.base_url}/mylists/v1/lists"

        response = requests.post(
            url,
            json=payload,
            headers=self.headers(),
            timeout=30,
        )

        if response.status_code >= 400:
            print("DigiKey CreateList response:", describe_error_response(response))

        _raise_for_status(response, "DigiKey MyLists create-list request failed")
        return response.json()

    def add_parts_to_list(self, list_id, parts):
        # Confirmed live (2026-09-25): the real response is a plain list
        # of string item IDs (e.g. ["N7S19MYZ7F"]), not a list of dicts
        # with per-part fields -- and no share identifier/link field
        # exists anywhere in this or create_list()'s response. share_id
        # staying None in _build_digikey_purchasing() is a confirmed
        # absence, not an open question.
        self.validate_config()

        if self.dry_run:
            print("\n[DIGIKEY MYLISTS DRY RUN] Would add parts to list")
            print("List ID:", list_id)
            print("Payload:", parts)
            return {
                "dry_run": True,
                "ListId": list_id,
                "parts_added": len(parts),
            }

        url = f"{self.base_url}/mylists/v1/lists/{list_id}/parts"

        response = requests.post(
            url,
            json=parts,
            headers=self.headers(),
            timeout=30,
        )

        if response.status_code >= 400:
            print("DigiKey AddParts response:", describe_error_response(response))

        _raise_for_status(response, "DigiKey MyLists add-parts request failed")
        return response.json()


def build_timestamped_list_name(list_name):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{list_name} {timestamp}"


def build_digikey_mylists_parts(clean_bom):
    parts = []

    for _, row in clean_bom.iterrows():
        selected_supplier = str(row.get("selected_supplier", "")).strip().lower()
        sourcing_status = str(row.get("sourcing_status", "")).strip().lower()

        if selected_supplier != "digikey" or sourcing_status != "sourced_digikey":
            continue

        supplier_part_number = str(row.get("supplier_part_number", "")).strip()
        mpn = str(row.get("mpn", "")).strip()
        qty = str(row.get("supplier_order_qty", "")).strip()

        part_number = supplier_part_number or mpn

        if not part_number or not qty:
            continue

        parts.append(
            {
                "RequestedPartNumber": part_number,
                "OriginalPartNumber": mpn,
                "ManufacturerName": str(row.get("manufacturer", "")).strip(),
                "SelectedQuantityIndex": 0,
                "Quantities": [
                    {
                        "Quantity": int(float(qty)),
                    }
                ],
            }
        )

    return parts


def create_digikey_mylist_from_bom(clean_bom, list_name):
    client = DigiKeyMyListsClient()
    parts = build_digikey_mylists_parts(clean_bom)

    if not parts:
        return {
            "created": False,
            "message": "No DigiKey-sourced parts found.",
            "parts_count": 0,
            "token_store_error": None,
        }

    resolved_list_name, name_changed = client.resolve_create_list_name(list_name)

    # Confirmed live (2026-09-25, three real disposable test MyLists):
    # create_list()'s actual response IS a bare string -- the list ID
    # itself (e.g. "02UFKJOWAE") -- not a dict. This branch is
    # load-bearing in practice, not unexercised defensive code.
    create_result = client.create_list(resolved_list_name)
    if isinstance(create_result, str):
        list_id = create_result
    else:
        list_id = (
            create_result.get("ListId")
            or create_result.get("listId")
            or create_result.get("Id")
            or create_result.get("id")
        )

    # Codex F2: a rotated refresh token that failed to persist durably is
    # a degraded outcome even when the MyList call(s) above succeeded --
    # the durable store still holds the OLD token DigiKey has already
    # invalidated, so the NEXT refresh attempt (this process or another,
    # especially after a restart) will fail until re-persisted. Read
    # unconditionally so this is never lost regardless of which branch
    # below returns.
    token_store_error = getattr(client.auth_client, "token_store_error", None)

    if not list_id:
        return {
            "created": False,
            "message": "DigiKey list created but no list ID was found in response.",
            "requested_list_name": list_name,
            "list_name": resolved_list_name,
            "name_changed": name_changed,
            "parts_count": len(parts),
            "create_result": create_result,
            "token_store_error": token_store_error,
        }

    add_result = client.add_parts_to_list(list_id, parts)
    token_store_error = getattr(client.auth_client, "token_store_error", None)

    return {
        "created": True,
        "list_id": list_id,
        "requested_list_name": list_name,
        "list_name": resolved_list_name,
        "name_changed": name_changed,
        "parts_count": len(parts),
        "create_result": create_result,
        "add_result": add_result,
        "token_store_error": token_store_error,
    }


