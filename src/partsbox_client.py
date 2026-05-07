import os
import requests
from dotenv import load_dotenv

load_dotenv()


MANUFACTURER_ALIASES = {
    "murata electronics": "murata",
    "murata manufacturing": "murata",
    "st": "stmicroelectronics",
    "stmicro": "stmicroelectronics",
    "st micro": "stmicroelectronics",
    "st microelectronics": "stmicroelectronics",
    "yageo group": "yageo",
}


def normalize_manufacturer(value):
    text = str(value or "").strip().lower()
    text = text.replace("&", " and ")
    text = " ".join(text.replace("-", " ").replace("/", " ").split())

    if text in MANUFACTURER_ALIASES:
        return MANUFACTURER_ALIASES[text]

    suffixes = [
        "corporation",
        "corp",
        "incorporated",
        "inc",
        "limited",
        "ltd",
        "co",
        "company",
        "group",
    ]

    words = [word for word in text.split() if word not in suffixes]
    normalized = " ".join(words)

    return MANUFACTURER_ALIASES.get(normalized, normalized)


class PartsBoxClient:
    def __init__(self):
        self.api_key = os.getenv("PARTSBOX_API_KEY", "").strip()
        self.base_url = os.getenv(
            "PARTSBOX_API_BASE_URL",
            "https://api.partsbox.com/api/1",
        ).strip()
        self._parts_cache = None

        # 🔒 DRY RUN FLAG
        self.dry_run = os.getenv("PARTSBOX_DRY_RUN", "true").lower() == "true"
    def validate_config(self):
        if not self.api_key:
            raise ValueError("Missing PARTSBOX_API_KEY in .env")

    def call(self, operation, payload=None):
        self.validate_config()

        write_operations = [
            "project/create",
            "storage/create",
            "project/add-entries",
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

        if response.status_code >= 400:
            print("PartsBox response:", response.text)

        response.raise_for_status()
        data = response.json()

        status_category = data.get("partsbox.status/category", "").strip().lower()
        if status_category and status_category != "ok":
            message = data.get("partsbox.status/message", "Unknown PartsBox error")
            raise ValueError(f"PartsBox API error: {message}")

        return data

    def get_project_entries(self, project_id):
        return self.call("project/get-entries", {"project/id": project_id})

    def add_project_entries(self, project_id, entries):
        payload = {
            "project/id": project_id,
            "entries": entries,
        }
        return self.call("project/add-entries", payload)

    def list_parts(self):
        return self.call("part/all")

    def get_parts(self):
        if self._parts_cache is None:
            parts = self.list_parts()
            self._parts_cache = parts.get("data", parts.get("parts", []))

        return self._parts_cache

    def find_part_by_mpn_and_manufacturer(self, mpn, manufacturer=""):
        target_mpn = str(mpn or "").strip().lower()
        target_manufacturer = normalize_manufacturer(manufacturer)

        if not target_mpn:
            return None

        mpn_matches = []

        for part in self.get_parts():
            part_mpn = str(part.get("part/mpn") or part.get("part/name") or "").strip().lower()

            if part_mpn == target_mpn:
                mpn_matches.append(part)

        if not target_manufacturer:
            return mpn_matches[0] if mpn_matches else None

        for part in mpn_matches:
            part_manufacturer = normalize_manufacturer(part.get("part/manufacturer"))

            if (
                part_manufacturer == target_manufacturer
                or target_manufacturer in part_manufacturer
                or part_manufacturer in target_manufacturer
            ):
                return part

        return None

    def list_projects(self):
        return self.call("project/all")

    def list_storage_locations(self):
        return self.call("storage/all")
    
    def find_project_by_name(self, name):
        projects = self.list_projects()
        records = projects.get("data", projects.get("projects", []))

        target = str(name).strip().lower()

        for project in records:
            project_name = (
                project.get("project/name")
                or project.get("name")
                or project.get("project_name")
                or ""
            ).strip().lower()

            if project_name == target:
                return project

        return None


    def find_storage_by_name(self, name):
        storage_locations = self.list_storage_locations()
        records = storage_locations.get("data", storage_locations.get("storage", []))

        target = str(name).strip().lower()

        for storage in records:
            storage_name = (
                storage.get("storage/name")
                or storage.get("name")
                or storage.get("storage_name")
                or ""
            ).strip().lower()

            if storage_name == target:
                return storage

        return None

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

        payload["project/description"] = description or "Created by BOM automation tool."

      #  if notes:
           # payload["project/notes"] = notes

        #if tags:
         #   payload["project/tags"] = tags

        return self.call("project/create", payload)
    
    
