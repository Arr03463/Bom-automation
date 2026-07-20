"""Mouser client — envelope, Errors[]-first, batching, partSearchOptions."""

import json

import pytest
import responses

from services.mouser_client import MouserClient

SEARCH_URL = "https://api.mouser.com/api/v1/search/partnumber"


def _env(monkeypatch):
    monkeypatch.setenv("SUPPLIER_DRY_RUN", "false")
    monkeypatch.setenv("MOUSER_SEARCH_API_KEY", "test-key")
    monkeypatch.setenv("MOUSER_SEARCH_DELAY_SECONDS", "0")   # no inter-call sleep in tests


@responses.activate
def test_named_envelope_and_key_in_query_string(monkeypatch):
    _env(monkeypatch)
    responses.add(responses.POST, SEARCH_URL,
                  json={"Errors": [], "SearchResults": {"Parts": []}}, status=200)
    MouserClient().search_by_mpn("ABC123")

    call = responses.calls[0]
    assert "apiKey=test-key" in call.request.url          # key in query string, not header
    body = json.loads(call.request.body)
    assert "SearchByPartRequest" in body                  # named root envelope
    assert body["SearchByPartRequest"]["partSearchOptions"] in ("None", "Exact")
    assert body["SearchByPartRequest"]["partSearchOptions"] != "string"


@responses.activate
def test_errors_array_checked_first(monkeypatch):
    _env(monkeypatch)
    # 200 OK but non-empty Errors -> must be treated as a failure.
    responses.add(responses.POST, SEARCH_URL,
                  json={"Errors": [{"Code": "InvalidApiKey", "Message": "bad key"}], "SearchResults": {}},
                  status=200)
    with pytest.raises(RuntimeError, match="Mouser error"):
        MouserClient().search_by_mpn("ABC123")


@responses.activate
def test_batches_up_to_ten_pipe_separated(monkeypatch):
    _env(monkeypatch)
    responses.add(responses.POST, SEARCH_URL, json={"Errors": [], "SearchResults": {"Parts": []}}, status=200)
    mpns = [f"PN{i}" for i in range(15)]
    MouserClient().search_by_mpns(mpns, exact=True)
    body = json.loads(responses.calls[0].request.body)
    joined = body["SearchByPartRequest"]["mouserPartNumber"]
    assert joined.count("|") == 9                          # 10 PNs -> 9 separators
    assert body["SearchByPartRequest"]["partSearchOptions"] == "Exact"


@responses.activate
def test_result_normalization_and_datasheet_casing(monkeypatch):
    _env(monkeypatch)
    part = {
        "Manufacturer": "Yageo", "ManufacturerPartNumber": "RC0603FR-0710KL",
        "Availability": "8,800 In Stock", "MouserPartNumber": "603-RC0603FR-0710KL",
        "Description": "RES 10K 1% 0603", "LifecycleStatus": "Active",
        "DataSheetUrl": "https://mouser/ds.pdf",           # Mouser casing
        "Min": "1", "ROHSStatus": "RoHS Compliant",
        "PriceBreaks": [{"Quantity": 1, "Price": "0.10"}, {"Quantity": 100, "Price": "0.05"}],
    }
    responses.add(responses.POST, SEARCH_URL,
                  json={"Errors": [], "SearchResults": {"Parts": [part]}}, status=200)
    res = MouserClient().find_best_match("RC0603FR-0710KL", "Yageo", required_qty=100)
    assert res.supplier == "Mouser"
    assert res.stock == 8800
    assert res.datasheet_url == "https://mouser/ds.pdf"
    assert res.lifecycle_status == "Active"
    assert res.moq == 1
    assert res.unit_price == "0.10"
    assert len(res.price_breaks) == 2
