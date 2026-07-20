"""Microsoft Graph — shared app-only client (graceful fallback).

ONE client module for all Graph access. Phase 1 uses it to READ Azure AD group
memberships (role sourcing). Phase 2 reuses the same token/request plumbing for
the purchasing-sheet writer.

Graceful fallback: when Graph creds are absent (`settings.graph_configured` is
False), `get_client()` returns None and every caller falls back to local
behavior (seed roles, console sheet writes). Graph is NEVER called in local/dev
mode — not for sync, not for fallback.

FORWARD-COMPATIBILITY (per Phase 1 requirement): this module is the single seam
for Group management. Phase 1 ships READ methods only. The write path
(add_member / remove_member) is purely additive here later — it needs only the
Graph scope to widen (Group.Read.All -> Group.ReadWrite.All) and new methods on
this same client. No schema or auth-flow change is required to add it.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import httpx
import msal

from config import settings, mask

log = logging.getLogger("autobom.graph")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
# App-only scope. Read-only in Phase 1. Widening to Group.ReadWrite.All (with
# admin consent) is all that's needed to unlock the future write path.
GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]


class GraphClient:
    """Thin app-only (client-credentials) Graph client with a cached token."""

    def __init__(self, tenant_id: str, client_id: str, client_secret: str):
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._secret = client_secret
        self._app = msal.ConfidentialClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret,
        )
        self._token: Optional[str] = None
        self._expires_at = 0.0
        self._lock = threading.Lock()

    def _acquire_token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._expires_at - 60:
                return self._token
            result = self._app.acquire_token_for_client(scopes=GRAPH_SCOPE)
            if "access_token" not in result:
                raise RuntimeError(
                    f"Graph token error: {result.get('error')} "
                    f"{result.get('error_description', '')[:120]}"
                )
            self._token = result["access_token"]
            self._expires_at = time.time() + int(result.get("expires_in", 3600))
            log.info("Graph token acquired (client %s), expires in %ss",
                     mask(self._client_id), result.get("expires_in"))
            return self._token

    def get(self, path: str, params: dict | None = None) -> dict:
        token = self._acquire_token()
        url = path if path.startswith("http") else f"{GRAPH_BASE}{path}"
        with httpx.Client(timeout=20) as client:
            resp = client.get(url, headers={"Authorization": f"Bearer {token}"}, params=params)
            resp.raise_for_status()
            return resp.json()

    def get_all(self, path: str, params: dict | None = None) -> list[dict]:
        """GET with @odata.nextLink paging flattened into one list of `value`s."""
        items: list[dict] = []
        data = self.get(path, params)
        items.extend(data.get("value", []))
        next_link = data.get("@odata.nextLink")
        while next_link:
            data = self.get(next_link)
            items.extend(data.get("value", []))
            next_link = data.get("@odata.nextLink")
        return items

    def post(self, path: str, json: dict | None = None, headers: dict | None = None) -> dict:
        token = self._acquire_token()
        url = path if path.startswith("http") else f"{GRAPH_BASE}{path}"
        hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        if headers:
            hdrs.update(headers)
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, headers=hdrs, json=json)
            resp.raise_for_status()
            return resp.json() if resp.content else {}

    # -- Excel workbook writing (Phase 2, purchasing sheet) -------------------
    # Additive on the SAME client. Used ONLY when Graph is configured; the
    # purchasing sheet writer falls back to console logging otherwise.
    def _workbook_base(self, item_id: str, drive_id: str | None) -> str:
        if drive_id:
            return f"/drives/{drive_id}/items/{item_id}/workbook"
        return f"/me/drive/items/{item_id}/workbook"

    def excel_create_session(self, item_id: str, drive_id: str | None = None) -> str:
        data = self.post(f"{self._workbook_base(item_id, drive_id)}/createSession",
                         json={"persistChanges": True})
        return data.get("id", "")

    def excel_close_session(self, item_id: str, session_id: str, drive_id: str | None = None) -> None:
        self.post(f"{self._workbook_base(item_id, drive_id)}/closeSession",
                  headers={"workbook-session-id": session_id})

    def excel_add_table_rows(self, item_id: str, table_name: str, values: list[list],
                             session_id: str | None = None, drive_id: str | None = None) -> dict:
        """APPEND rows to a workbook table — the ONLY sheet mutation AutoBOM makes."""
        headers = {"workbook-session-id": session_id} if session_id else None
        return self.post(f"{self._workbook_base(item_id, drive_id)}/tables/{table_name}/rows/add",
                         json={"values": values}, headers=headers)

    # -- Future group write path slots in here (Phase 4), same client, additive:
    #   def add_member(self, group_id, user_object_id): ...
    #   def remove_member(self, group_id, user_object_id): ...


_client_singleton: Optional[GraphClient] = None
_singleton_lock = threading.Lock()


def get_client() -> Optional[GraphClient]:
    """Return the shared Graph client, or None when Graph isn't configured
    (local/dev mode). Callers MUST treat None as 'run local fallback'."""
    if not settings.graph_configured:
        return None
    global _client_singleton
    with _singleton_lock:
        if _client_singleton is None:
            import os
            _client_singleton = GraphClient(
                tenant_id=os.environ["MICROSOFT_GRAPH_TENANT_ID"],
                client_id=os.environ["MICROSOFT_GRAPH_CLIENT_ID"],
                client_secret=os.environ["MICROSOFT_GRAPH_CLIENT_SECRET"],
            )
    return _client_singleton
