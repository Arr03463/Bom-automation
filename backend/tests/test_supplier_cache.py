"""Supplier lookup cache — the TTL added on port (guide §6.3)."""

from services.supplier_lookup_cache import SupplierLookupCache


def test_hit_within_ttl(monkeypatch, tmp_path):
    monkeypatch.setenv("SUPPLIER_LOOKUP_CACHE_ENABLED", "true")
    monkeypatch.setenv("SUPPLIER_LOOKUP_CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setenv("SUPPLIER_LOOKUP_CACHE_TTL_SECONDS", "100000")
    cache = SupplierLookupCache()
    cache.set("k", {"supplier": "Mouser", "mpn": "X"})
    assert cache.get("k") == {"supplier": "Mouser", "mpn": "X"}


def test_miss_after_ttl(monkeypatch, tmp_path):
    path = str(tmp_path / "cache.json")
    monkeypatch.setenv("SUPPLIER_LOOKUP_CACHE_ENABLED", "true")
    monkeypatch.setenv("SUPPLIER_LOOKUP_CACHE_PATH", path)
    monkeypatch.setenv("SUPPLIER_LOOKUP_CACHE_TTL_SECONDS", "100000")
    SupplierLookupCache().__class__  # ensure import
    c1 = SupplierLookupCache()
    c1.set("k", {"supplier": "Mouser"})
    c1.save()

    # Re-open with a negative TTL -> every entry is immediately stale.
    monkeypatch.setenv("SUPPLIER_LOOKUP_CACHE_TTL_SECONDS", "-1")
    c2 = SupplierLookupCache()
    assert c2.get("k") is None
