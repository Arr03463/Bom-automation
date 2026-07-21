import logging
import os

import requests

_log = logging.getLogger("autobom.partsbox")


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
            "build/create",   # DECREMENTS REAL STOCK - must honor the dry-run gate
            "stock/add",      # receiving; same reason
        ]

        if self.dry_run and operation in write_operations:
            # Echo the operation + payload back so callers can render an honest
            # preview of exactly what the live call would do.
            _log.info("[PARTSBOX DRY RUN] would call %s payload=%s", operation, payload)
            return {"dry_run": True, "operation": operation, "payload": payload}

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
            # logger, not print: honors the app's logging config and level, and
            # goes through the same scrubbing/formatting as every other trace.
            _log.warning("PartsBox %s -> %s: %s", operation, response.status_code,
                         (response.text or "")[:500])

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

    # ---- Builds (Phase 4) --------------------------------------------------
    # NOTE: build/create DECREMENTS REAL STOCK. It is registered as a write
    # operation so PARTSBOX_DRY_RUN gates it exactly like the other writes.
    def create_build(self, project_id, build_qty, entries, notes=""):
        """Consume stock for one physical assembly.

        `entries` come from services.build_service.consumption_plan()['consume']
        - already filtered to the lines that actually consume ('used' + the
        substitutes from 'rework'); 'skipped' and 'deferred' never reach here.
        """
        payload = {
            "project/id": project_id,
            "build/quantity": int(build_qty or 1),
            "build/entries": [
                {"part/mpn": e["mpn"], "part/manufacturer": e.get("mfr") or "",
                 "build/quantity": int(e["qty"])}
                for e in entries
            ],
        }
        if notes:
            payload["build/notes"] = notes
        return self.call("build/create", payload)

    def build_qr_image_url(self, build_id):
        """PartsBox ID Anything(TM) QR image URL for a build.

        Per the API-leverage tenet, AutoBOM never generates QR codes - it asks
        PartsBox for the image and renders it. The caller falls back to the
        'Open Build in PartsBox' link when this is unavailable.

        UNVERIFIED: the exact ID-Anything path could not be confirmed - the
        committed `partsbox api rules.pdf` is a corrupted export with no text
        layer (flagged in CLAUDE.md). The template is therefore configurable via
        PARTSBOX_QR_URL_TEMPLATE so it can be corrected without a code change.
        """
        if not build_id:
            return None
        template = os.getenv(
            "PARTSBOX_QR_URL_TEMPLATE",
            "https://api.partsbox.com/api/1/id-anything/qr/{id}",
        ).strip()
        return template.replace("{id}", str(build_id))

    def build_web_url(self, build_id):
        """Human fallback: open the build in the PartsBox web app."""
        if not build_id:
            return None
        base = os.getenv("PARTSBOX_WEB_URL", "https://partsbox.com").strip().rstrip("/")
        return f"{base}/builds/{build_id}"
