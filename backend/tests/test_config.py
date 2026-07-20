"""Config loader — graceful-fallback detection."""

from config.settings import Settings, is_real


def test_is_real_detects_placeholders_and_empty():
    assert is_real("real-value-1234")
    assert not is_real(None)
    assert not is_real("")
    assert not is_real("   ")
    assert not is_real("<paste-client-id-here>")
    assert not is_real("<from-poc-env>")
    assert not is_real("<same-as-AZURE_TENANT_ID>")


def test_local_mode_flags(monkeypatch):
    # No Azure / Graph creds -> local mode.
    for k in ("AZURE_AD_CLIENT_ID", "AZURE_AD_CLIENT_SECRET", "AZURE_TENANT_ID",
              "MICROSOFT_GRAPH_TENANT_ID", "MICROSOFT_GRAPH_CLIENT_ID",
              "MICROSOFT_GRAPH_CLIENT_SECRET", "ONEDRIVE_PURCHASING_SHEET_ID"):
        monkeypatch.delenv(k, raising=False)
    s = Settings()
    assert s.azure_enabled is False
    assert s.graph_configured is False
    assert s.graph_enabled is False
    assert s.status()["auth"] == "seed-users"
    assert s.status()["graph_sheet_writer"] == "console-fallback"


def test_azure_mode_flags(monkeypatch):
    for k in ("AZURE_AD_CLIENT_ID", "AZURE_AD_CLIENT_SECRET", "AZURE_TENANT_ID",
              "MICROSOFT_GRAPH_TENANT_ID", "MICROSOFT_GRAPH_CLIENT_ID", "MICROSOFT_GRAPH_CLIENT_SECRET"):
        monkeypatch.setenv(k, "real-value-abcd")
    s = Settings()
    assert s.azure_enabled is True
    assert s.graph_configured is True
    # graph_enabled still needs the sheet id
    assert s.graph_enabled is False
    monkeypatch.setenv("ONEDRIVE_PURCHASING_SHEET_ID", "real-sheet-id")
    assert Settings().graph_enabled is True


def test_group_role_map_only_valid_roles():
    from db.models import VALID_ROLES
    for role in Settings().azure_group_role_map.values():
        assert role in VALID_ROLES
