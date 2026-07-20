"""Shared HTTP retry/backoff (guide §6.2) + DigiKey normalization casing."""

import responses

from services.supplier_base import http_request
from services.digikey_client import _digikey_product_to_result

URL = "https://api.example.com/thing"
_noop_sleep = lambda _s: None


@responses.activate
def test_retries_on_429_then_succeeds():
    responses.add(responses.GET, URL, status=429, headers={"Retry-After": "0"})
    responses.add(responses.GET, URL, json={"ok": True}, status=200)
    resp = http_request("GET", URL, supplier="test", sleep=_noop_sleep)
    assert resp.status_code == 200
    assert len(responses.calls) == 2


@responses.activate
def test_retries_on_500_then_succeeds():
    responses.add(responses.GET, URL, status=503)
    responses.add(responses.GET, URL, status=500)
    responses.add(responses.GET, URL, json={"ok": True}, status=200)
    resp = http_request("GET", URL, supplier="test", sleep=_noop_sleep)
    assert resp.status_code == 200
    assert len(responses.calls) == 3


@responses.activate
def test_no_retry_on_400():
    responses.add(responses.GET, URL, status=400)
    resp = http_request("GET", URL, supplier="test", sleep=_noop_sleep)
    assert resp.status_code == 400
    assert len(responses.calls) == 1        # 400 is not retried


@responses.activate
def test_no_retry_on_404():
    responses.add(responses.GET, URL, status=404)
    resp = http_request("GET", URL, supplier="test", sleep=_noop_sleep)
    assert resp.status_code == 404
    assert len(responses.calls) == 1


def test_digikey_normalization_casing_and_widening():
    product = {
        "Manufacturer": {"Name": "Samsung Electro-Mechanics"},
        "ManufacturerProductNumber": "CL05B104KO5NNNC",
        "QuantityAvailable": 500000,
        "ProductStatus": {"Status": "Active"},
        "Description": {"ProductDescription": "CAP CER 0.1UF 16V X7R 0402"},
        "DatasheetUrl": "https://digikey/ds.pdf",           # DigiKey casing (no 'S')
        "ProductUrl": "https://digikey/p",
        "ProductVariations": [{
            "DigiKeyProductNumber": "1276-1000-1-ND", "MinimumOrderQuantity": 1,
            "StandardPricing": [{"BreakQuantity": 1, "UnitPrice": 0.10}],
        }],
    }
    res = _digikey_product_to_result(product)
    assert res.supplier == "DigiKey"
    assert res.manufacturer == "Samsung Electro-Mechanics"
    assert res.stock == 500000
    assert res.datasheet_url == "https://digikey/ds.pdf"
    assert res.description.startswith("CAP CER")
    assert res.lifecycle_status == "Active"
    assert res.moq == 1
    assert res.supplier_part_number == "1276-1000-1-ND"
    assert res.price_breaks and res.price_breaks[0]["price"] == "0.1"
