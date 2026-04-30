import os
import requests
from dotenv import load_dotenv

from digikey_client import DigiKeyClient

load_dotenv()


class DigiKeyMyListsClient:
    def __init__(self):
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
            headers["X-DIGIKEY-Account-ID"] = self.account_id

        return headers

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
            print("DigiKey CreateList response:", response.text)

        response.raise_for_status()
        return response.json()

    def add_parts_to_list(self, list_id, parts):
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
            print("DigiKey AddParts response:", response.text)

        response.raise_for_status()
        return response.json()


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
        }

    create_result = client.create_list(list_name)
    if isinstance(create_result, str):
        list_id = create_result
    else:
        list_id = (
            create_result.get("ListId")
            or create_result.get("listId")
            or create_result.get("Id")
            or create_result.get("id")
        )

    if not list_id:
        return {
            "created": False,
            "message": "DigiKey list created but no list ID was found in response.",
            "parts_count": len(parts),
            "create_result": create_result,
        }

    add_result = client.add_parts_to_list(list_id, parts)

    return {
        "created": True,
        "list_id": list_id,
        "parts_count": len(parts),
        "create_result": create_result,
        "add_result": add_result,
    }
