"""A supplier API key must never reach a response body, a log line, or a sheet.

The live vector (found in the pre-demo audit): Mouser passes its key in the
QUERY STRING, and a network-level `requests` failure stringifies with the full
request URL. `_mask_url` protects the log line we format ourselves, but not the
re-raised exception - so `str(exc)` echoed into an API response would put a live
key in the browser.
"""

import requests

from services.supplier_base import scrub_secrets

REAL_KEY = "a1b2c3d4-SECRET-KEY-9876"


# --- the actual vector, reproduced with a real exception --------------------
def test_a_real_requests_exception_leaks_the_key_and_scrub_stops_it():
    """Not a synthetic string: provoke a genuine connection error and confirm
    the raw exception carries the key while the scrubbed form does not."""
    try:
        requests.get("https://api.mouser.invalid/api/v1/search/keyword",
                     params={"apiKey": REAL_KEY}, timeout=2)
        raise AssertionError("expected a connection error")
    except requests.RequestException as exc:
        raw = str(exc)
        assert REAL_KEY in raw, "precondition: the raw exception should carry the key"
        safe = scrub_secrets(exc)
        assert REAL_KEY not in safe
        assert "apiKey=****" in safe
        assert "api.mouser.invalid" in safe   # still diagnosable


def test_scrub_accepts_an_exception_object_directly():
    assert REAL_KEY not in scrub_secrets(ValueError(f"boom ?apiKey={REAL_KEY}"))


# --- credential shapes ------------------------------------------------------
def test_query_string_api_key_is_masked():
    out = scrub_secrets(f"GET /api/v1/cart?apiKey={REAL_KEY}&x=1")
    assert REAL_KEY not in out and "apiKey=****" in out and "x=1" in out


def test_bearer_token_is_masked():
    out = scrub_secrets("Authorization: Bearer eyJhbGciOi.J9payload.sig")
    assert "eyJhbGciOi" not in out and "Bearer ****" in out


def test_partsbox_apikey_header_form_is_masked():
    out = scrub_secrets(f"Authorization: APIKey {REAL_KEY}")
    assert REAL_KEY not in out


def test_client_secret_is_masked():
    out = scrub_secrets(f"grant_type=refresh_token&client_secret={REAL_KEY}")
    assert REAL_KEY not in out and "client_secret=****" in out


def test_json_style_api_key_is_masked():
    out = scrub_secrets(f'{{"api_key": "{REAL_KEY}", "ok": true}}')
    assert REAL_KEY not in out


def test_clean_text_is_returned_unchanged():
    """Scrubbing must not mangle ordinary error messages."""
    msg = "Mouser error: ['Invalid part number']"
    assert scrub_secrets(msg) == msg


def test_multiple_secrets_in_one_string_are_all_masked():
    out = scrub_secrets(f"?apiKey={REAL_KEY} then Bearer {REAL_KEY}")
    assert REAL_KEY not in out


# --- all four leak sites call it --------------------------------------------
def _code_of(mod):
    """Module source with comments stripped, so the check reads CODE not prose."""
    import inspect
    return "\n".join(line.split("#", 1)[0] for line in inspect.getsource(mod).splitlines())


def test_every_boundary_that_returns_error_text_scrubs_it():
    """Guards against a future edit reintroducing a raw str(exc) at a boundary
    that reaches a client."""
    from api import sourcing, suppliers
    from services import bucket_flush

    for mod in (suppliers, sourcing, bucket_flush):
        code = _code_of(mod)
        assert "scrub_secrets" in code, f"{mod.__name__} must scrub before returning error text"
        assert "str(exc)" not in code, (
            f"{mod.__name__} still stringifies an exception directly; use scrub_secrets(exc)"
        )


def test_the_network_error_log_line_scrubs_the_exception():
    """The 4th site (A3): http_request's own retry log. _mask_url covers the url
    it formats, but the exception re-embeds the same url - key included - and
    would write the live key into the log file in plaintext."""
    from services import supplier_base

    code = _code_of(supplier_base)
    line = next(ln for ln in code.splitlines() if "network error" in ln and "log.warning" in ln)
    block = code[code.index(line):code.index(line) + 400]
    assert "scrub_secrets(exc)" in block, (
        "the network-error log line must scrub the exception, not interpolate it raw"
    )
    assert "_mask_url(url), exc," not in block, "raw exc reintroduced into the log line"
