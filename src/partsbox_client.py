import os
import requests
from dotenv import load_dotenv

load_dotenv()


class PartsBoxClient:
    def __init__(self):
        self.api_key = os.getenv("PARTSBOX_API_KEY", "").strip()
        self.base_url = os.getenv(
            "PARTSBOX_API_BASE_URL",
            "https://api.partsbox.com/api/1",
        ).strip()

        # 🔒 DRY RUN FLAG
        self.dry_run = os.getenv("PARTSBOX_DRY_RUN", "true").lower() == "true"
    def validate_config(self):
        if not self.api_key:
            raise ValueError("Missing PARTSBOX_API_KEY in .env")

    def call(self, operation, payload=None):
        self.validate_config()

        # DRY RUN SAFETY LAYER
        write_operations = [
            "project/create",
            "storage/create",
        ]

        if self.dry_run and operation in write_operations:
            print("\n[DRY RUN] Would call:", operation)
            print("Payload:", payload)
            return {"dry_run": True}

        url = f"{self.base_url}/{operation}"
        response = requests.post(
            url,
            json=payload or {},
            headers={
                "Content-Type": "application/json",
                "Authorization": f"APIKey {self.api_key}",
            },
            timeout=30,
        )

        response.raise_for_status()
        data = response.json()

        status_category = data.get("partsbox.status/category", "")
        if status_category and status_category != "status/ok":
            message = data.get("partsbox.status/message", "Unknown PartsBox error")
            raise ValueError(f"PartsBox API error: {message}")

        return data

    def list_parts(self):
        return self.call("part/all")

    def list_projects(self):
        return self.call("project/all")

    def list_storage_locations(self):
        return self.call("storage/all")

    def create_storage_location(self, name, description="", tags=None):
        payload = {
            "storage/name": name,
        }

        if description:
            payload["storage/description"] = description

        if tags:
            payload["storage/tags"] = tags

        return self.call("storage/create", payload)

    def create_project(self, name, description="", notes="", tags=None):
        payload = {
            "project/name": name,
        }

        if description:
            payload["project/description"] = description

        if notes:
            payload["project/notes"] = notes

        if tags:
            payload["project/tags"] = tags

        return self.call("project/create", payload)