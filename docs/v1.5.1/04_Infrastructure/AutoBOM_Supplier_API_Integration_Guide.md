# AutoBOM Supplier API Integration Guide

**Implementation reference for DigiKey and Mouser APIs**
Project: Yank-Auto / AutoBOM · Captured: July 18, 2026

---

## 0. How to use this document

This is an **implementation-grade** reference intended to be read by an engineer or by Claude Code before writing or modifying any supplier-client code (`digikey_client.py`, `mouser_client.py`, `mouser_cart_client.py`, `nexar_client.py`, etc.). It specifies exactly how each API is authenticated, called, throttled, and parsed so that integrations do not fail at runtime.

Conventions used below:

- **`{curly}`** = a value you substitute at runtime.
- **CONFIRMED** = verified against the live spec / official docs on 2026-07-18.
- **VERIFY-IN-SANDBOX** = the shape is well-established but exact optional fields should be validated against the sandbox response before relying on them, because suppliers add fields over time.
- All request/response bodies are JSON unless stated. Send `Content-Type: application/json` and `Accept: application/json` on every JSON request.
- Property casing matters. DigiKey uses `PascalCase` for most body fields; Mouser wraps request bodies in a **named root object** and returns `PascalCase` fields. Do not lowercase them.

**Golden rules that prevent most "random errors":**

1. Never hardcode secrets. Load `DIGIKEY_CLIENT_ID`, `DIGIKEY_CLIENT_SECRET`, `MOUSER_SEARCH_API_KEY`, `MOUSER_ORDER_API_KEY` from environment / `.env`.
2. DigiKey access tokens expire in **10 minutes** (2-legged). Cache the token and refresh on expiry or on a `401`. Do not request a new token per call.
3. Mouser passes the key as a **query-string parameter** (`?apiKey=...`), never as a header.
4. Every Mouser request body is wrapped in a **root object** (e.g. `{"SearchByKeywordRequest": {...}}`). Sending the inner object alone returns an error.
5. Respect rate limits and implement exponential backoff on `429`.
6. Per AutoBOM principles, **never auto-submit an order**. Order/cart calls that commit money require an explicit human approval gate (see §6.5). Mouser's order submit is gated by `SubmitOrder=false` — keep it `false` until a human approves.

---

## 1. Credentials and environment setup

Recommended `.env` layout (matches the project's `config.py` pattern):

```dotenv
# DigiKey
DIGIKEY_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxx
DIGIKEY_CLIENT_SECRET=xxxxxxxxxxxxxxxx
DIGIKEY_ENV=production            # or: sandbox
DIGIKEY_LOCALE_SITE=US
DIGIKEY_LOCALE_LANGUAGE=en
DIGIKEY_LOCALE_CURRENCY=USD

# Mouser (Search API and Order API use SEPARATE keys)
MOUSER_SEARCH_API_KEY=00000000-0000-0000-0000-000000000000
MOUSER_ORDER_API_KEY=00000000-0000-0000-0000-000000000000
```

Base hosts:

| Provider | Environment | Base host |
|---|---|---|
| DigiKey | Production | `https://api.digikey.com` |
| DigiKey | Sandbox | `https://sandbox-api.digikey.com` |
| Mouser | Production only | `https://api.mouser.com` |

> DigiKey Sandbox returns valid response **structures** but incomplete / non-matching **data** — good for wiring up parsing, useless for real pricing. Mouser has no separate sandbox host; test against production with low call volume.

---

## 2. DigiKey — Authentication (OAuth 2.0)

DigiKey requires **OAuth 2.0 over TLSv1.2** on every call. Two flows exist. For automated BOM sourcing you almost always want **2-legged (client credentials)**. Use 3-legged only when acting on behalf of a specific signed-in DigiKey user (e.g. reading *their* orders or lists).

### 2.1 Endpoints (CONFIRMED)

| Purpose | Production URL | Sandbox URL |
|---|---|---|
| Token | `https://api.digikey.com/v1/oauth2/token` | `https://sandbox-api.digikey.com/v1/oauth2/token` |
| Authorize (3-legged) | `https://api.digikey.com/v1/oauth2/authorize` | `https://sandbox-api.digikey.com/v1/oauth2/authorize` |

### 2.2 Two-legged (Client Credentials) — CONFIRMED

`POST {base}/v1/oauth2/token` with `Content-Type: application/x-www-form-urlencoded` and body:

```
grant_type=client_credentials
client_id={DIGIKEY_CLIENT_ID}
client_secret={DIGIKEY_CLIENT_SECRET}
```

Response:

```json
{
  "access_token": "xxxxxxxx",
  "token_type": "Bearer",
  "expires_in": 599
}
```

- **Access token lifetime: 10 minutes.** Cache it; refresh proactively at ~9 minutes or reactively on a `401`.

### 2.3 Three-legged (Authorization Code) — CONFIRMED

1. Redirect the user to `GET {base}/v1/oauth2/authorize?response_type=code&client_id={id}&redirect_uri={uri}`.
2. User signs in → DigiKey redirects to `{uri}?code={authcode}`. **Authorization code expires in 1 minute.**
3. Exchange it: `POST {base}/v1/oauth2/token` with `grant_type=authorization_code`, `code={authcode}`, `client_id`, `client_secret`, `redirect_uri`.
4. Response includes `access_token` (**30-minute** lifetime) and `refresh_token` (**does not expire**). Use the refresh token with `grant_type=refresh_token` to get new access tokens.

### 2.4 Token lifetimes (quick table)

| Token | Flow | Lifetime |
|---|---|---|
| Access token | Client Credentials (2-legged) | 10 min |
| Authorization code | Authorization Code (3-legged) | 1 min |
| Access token | Authorization Code (3-legged) | 30 min |
| Refresh token | Authorization Code (3-legged) | Does not expire |

### 2.5 Python — token manager with caching

```python
import os, time, threading, requests

class DigiKeyAuth:
    """Thread-safe 2-legged token cache for DigiKey."""
    def __init__(self):
        env = os.getenv("DIGIKEY_ENV", "production")
        self.base = ("https://sandbox-api.digikey.com"
                     if env == "sandbox" else "https://api.digikey.com")
        self.client_id = os.environ["DIGIKEY_CLIENT_ID"]
        self.client_secret = os.environ["DIGIKEY_CLIENT_SECRET"]
        self._token = None
        self._expires_at = 0.0
        self._lock = threading.Lock()

    def token(self) -> str:
        with self._lock:
            # refresh 30s before actual expiry
            if self._token and time.time() < self._expires_at - 30:
                return self._token
            resp = requests.post(
                f"{self.base}/v1/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data["access_token"]
            self._expires_at = time.time() + int(data.get("expires_in", 600))
            return self._token
```

---

## 3. DigiKey — Required headers, rate limits, errors

### 3.1 Required request headers for all Product Information V4 calls (CONFIRMED)

Even endpoints that the portal shows without a visible "lock" icon **still require** the Authorization token. Send all of these:

| Header | Value | Required |
|---|---|---|
| `Authorization` | `Bearer {access_token}` | Yes |
| `X-DIGIKEY-Client-Id` | `{DIGIKEY_CLIENT_ID}` | Yes |
| `X-DIGIKEY-Locale-Site` | Two-letter country, e.g. `US`, `CA`, `DE`, `UK`, `JP` | Yes |
| `X-DIGIKEY-Locale-Language` | Two-letter language, e.g. `en`, `de`, `fr`, `ja` | Yes |
| `X-DIGIKEY-Locale-Currency` | Three-letter currency, e.g. `USD`, `EUR`, `GBP` | Yes |
| `X-DIGIKEY-Customer-Id` | Regional customer id | Optional |
| `Content-Type` | `application/json` | Yes (POST) |
| `Accept` | `application/json` | Yes |

> Common failure: sending only `Authorization` and `X-DIGIKEY-Client-Id` and omitting the locale headers → `400`/localization errors. Always send the three locale headers.

### 3.2 Rate limits (CONFIRMED)

| API Product | Per minute | Per day |
|---|---|---|
| Barcode | 120 | 1,000 |
| Create BOM | 10 | — |
| Order Support | 120 | 1,000 |
| Ordering | 10 | — |
| Product Information | 120 | 1,000 |
| Quoting | 10 | — |

Every response carries limit headers — read them and back off before you hit the wall:

- `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `X-RateLimit-ResetTime`
- Burst: `X-BurstLimit-Limit`, `X-BurstLimit-Remaining`, `X-BurstLimit-Reset`, `X-BurstLimit-ResetTime`

### 3.3 HTTP status codes (CONFIRMED)

| Code | Meaning | Action |
|---|---|---|
| 200 | OK | Parse body |
| 400 | Bad Request | Fix payload/headers; do not retry unchanged |
| 401 | Unauthorized | Token expired/invalid → refresh token once and retry |
| 404 | Not Found | Part/resource does not exist |
| 429 | Too Many Requests | Back off using `X-RateLimit-Reset`, then retry |
| 500 | Server Error | Retry with exponential backoff |
| 503 | Service Unavailable | Retry with exponential backoff |

---

## 4. DigiKey — Product Information V4 (the core sourcing API)

Base path: `{base}/products/v4`. This is the API AutoBOM uses for component lookup, specs, pricing, availability, substitutions, and lifecycle.

### 4.1 Endpoint map (CONFIRMED endpoint set; paths VERIFY-IN-SANDBOX for exact casing)

| Operation | Method | Path | Use |
|---|---|---|---|
| KeywordSearch | POST | `/products/v4/search/keyword` | Search catalog by keyword / MPN / description |
| ProductDetails | GET | `/products/v4/search/{productNumber}/productdetails` | Full detail for one part |
| ProductPricing | GET | `/products/v4/search/{productNumber}/pricing` | Price/qty breaks |
| DigiReelPricing | GET | `/products/v4/search/{productNumber}/digireelpricing` | DigiReel pricing |
| Media | GET | `/products/v4/search/{productNumber}/media` | Datasheets, images |
| Associations | GET | `/products/v4/search/{productNumber}/associations` | Kits / related |
| Substitutions | GET | `/products/v4/search/{productNumber}/substitutions` | Substitute parts |
| RecommendedProducts | GET | `/products/v4/search/{productNumber}/recommendedproducts` | Recommendations |
| PackageTypeByQuantity | GET | `/products/v4/search/packagetypebyquantity/{productNumber}` | Packaging by qty |
| Categories | GET | `/products/v4/search/categories` | All categories |
| CategoryById | GET | `/products/v4/search/categories/{categoryId}` | One category |
| Manufacturers | GET | `/products/v4/search/manufacturers` | All manufacturers |

> `{productNumber}` must be URL-encoded (part numbers contain `/`, `,`, spaces). Use `urllib.parse.quote(pn, safe="")`.

### 4.2 KeywordSearch — request body

Minimum valid body is just `Keywords`. Full body for controlled searches (VERIFY-IN-SANDBOX for the full filter grammar):

```json
{
  "Keywords": "0.1uF 0402 X7R",
  "Limit": 10,
  "Offset": 0,
  "FilterOptionsRequest": {
    "ManufacturerFilter": [],
    "CategoryFilter": [],
    "StatusFilter": [],
    "ParameterFilterRequest": { "CategoryFilter": null, "ParameterFilters": [] },
    "SearchOptions": ["InStock"]
  },
  "SortOptions": { "Field": "None", "SortOrder": "Ascending" }
}
```

- `Limit` max is 50 per call; page with `Offset`.
- `SearchOptions` values include e.g. `InStock`, `RohsCompliant`, `Has3DModel`, `HasDatasheet`, `NewProductsOnly`, `NonRohsCompliant` (validate the ones you need in sandbox).

### 4.3 KeywordSearch — response (key fields, VERIFY-IN-SANDBOX)

```json
{
  "ProductsCount": 1234,
  "ExactMatches": [ ... ],
  "Products": [
    {
      "ManufacturerProductNumber": "CL05B104KO5NNNC",
      "Manufacturer": { "Name": "Samsung Electro-Mechanics" },
      "Description": { "ProductDescription": "CAP CER 0.1UF 16V X7R 0402", "DetailedDescription": "..." },
      "ProductVariations": [
        {
          "DigiKeyProductNumber": "1276-1000-1-ND",
          "PackageType": { "Name": "Cut Tape (CT)" },
          "MinimumOrderQuantity": 1,
          "StandardPricing": [ { "BreakQuantity": 1, "UnitPrice": 0.10, "TotalPrice": 0.10 } ]
        }
      ],
      "QuantityAvailable": 500000,
      "ProductStatus": { "Id": 0, "Status": "Active" },
      "DatasheetUrl": "https://...",
      "PhotoUrl": "https://...",
      "ProductUrl": "https://..."
    }
  ]
}
```

> Note the V4 shift: pricing/qty live under `ProductVariations[]`, keyed by `DigiKeyProductNumber`. A single manufacturer part can have several variations (Cut Tape, Tape & Reel, Digi-Reel), each with its own DigiKey PN, MOQ, and price breaks. Do not assume one price list per part.

### 4.4 Python — KeywordSearch and ProductDetails

```python
import os, time, urllib.parse, requests

class DigiKeyClient:
    def __init__(self, auth: "DigiKeyAuth"):
        self.auth = auth
        self.base = auth.base

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.auth.token()}",
            "X-DIGIKEY-Client-Id": self.auth.client_id,
            "X-DIGIKEY-Locale-Site": os.getenv("DIGIKEY_LOCALE_SITE", "US"),
            "X-DIGIKEY-Locale-Language": os.getenv("DIGIKEY_LOCALE_LANGUAGE", "en"),
            "X-DIGIKEY-Locale-Currency": os.getenv("DIGIKEY_LOCALE_CURRENCY", "USD"),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(self, method, path, **kwargs):
        url = f"{self.base}{path}"
        for attempt in range(4):
            resp = requests.request(method, url, headers=self._headers(),
                                    timeout=20, **kwargs)
            if resp.status_code == 401 and attempt == 0:
                self.auth._token = None          # force refresh, retry once
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                reset = int(resp.headers.get("X-RateLimit-Reset", 2 ** attempt))
                time.sleep(min(reset, 30))
                continue
            resp.raise_for_status()
            return resp.json()
        resp.raise_for_status()

    def keyword_search(self, keywords, limit=10, offset=0, search_options=None):
        body = {"Keywords": keywords, "Limit": limit, "Offset": offset}
        if search_options:
            body["FilterOptionsRequest"] = {"SearchOptions": search_options}
        return self._request("POST", "/products/v4/search/keyword", json=body)

    def product_details(self, product_number):
        pn = urllib.parse.quote(product_number, safe="")
        return self._request("GET", f"/products/v4/search/{pn}/productdetails")
```


---

## 5. Mouser API

Mouser is simpler than DigiKey: **no OAuth**. Authentication is a single API key passed as a **query-string parameter** on every request. Search and ordering use **separate keys** issued from your Mouser account.

### 5.1 Authentication (CONFIRMED)

- Pass `?apiKey={key}` on the URL. The key is a **UUID** (`00000000-0000-0000-0000-000000000000` format).
- Do **not** send it as a header or in the body.
- `MOUSER_SEARCH_API_KEY` → Search API. `MOUSER_ORDER_API_KEY` → Cart/Order/Order-History APIs. Mixing them up returns `401/403`.
- Send `Content-Type: application/json` and `Accept: application/json`. The API also supports XML, but use JSON.

### 5.2 Versions and base paths (CONFIRMED)

| Version | Base path | Contents |
|---|---|---|
| V1 | `https://api.mouser.com/api/v1` | Full API: Search (`keyword`, `partnumber`), Cart, Order, Order History. The manufacturer-specific search variants in V1 are **deprecated**. |
| V2 | `https://api.mouser.com/api/v2` | Newer Search endpoints with manufacturer filtering: `keywordandmanufacturer`, `partnumberandmanufacturer`, `manufacturerlist`. |

> Practical guidance for AutoBOM: use **V1 `search/partnumber`** and **V1 `search/keyword`** for general sourcing; use **V2 `search/partnumberandmanufacturer`** when you already know the manufacturer and want to disambiguate. Use **V1 Cart + Order** for the "generate order cart" workflow.

### 5.3 Rate limits (CONFIRMED behavior; exact numbers account-dependent)

- Mouser Search API is capped at roughly **1,000 calls per day** per key (matches DigiKey's Product Information daily cap). Treat 1,000/day as the working ceiling and cache results.
- There is no published fixed per-minute number; throttle to a few requests/second and back off on `429`.
- **Batch to save calls:** `search/partnumber` accepts **up to 10 part numbers** in one request, pipe-separated (`|`), each 3–40 characters. Always batch BOM lookups in groups of 10.

### 5.4 Search request envelopes (CONFIRMED — exact wrappers)

Every Mouser request body is wrapped in a **named root object**. These are the exact shapes:

**V1 keyword search** — `POST /api/v1/search/keyword?apiKey={key}`
```json
{
  "SearchByKeywordRequest": {
    "keyword": "resistor",
    "records": 50,
    "startingRecord": 0,
    "searchOptions": "None",
    "searchWithYourSignUpLanguage": "false",
    "mouserPaysCustomsAndDuties": false
  }
}
```

**V1 part-number search** — `POST /api/v1/search/partnumber?apiKey={key}`
```json
{
  "SearchByPartRequest": {
    "mouserPartNumber": "494-JANTX2N2222A|610-2N2222-TL",
    "partSearchOptions": "None",
    "mouserPaysCustomsAndDuties": false
  }
}
```

**V2 keyword + manufacturer** — `POST /api/v2/search/keywordandmanufacturer?apiKey={key}`
```json
{
  "SearchByKeywordMfrNameRequest": {
    "keyword": "0.1uF 0402",
    "manufacturerName": "Samsung Electro-Mechanics",
    "records": 50,
    "pageNumber": 0,
    "searchOptions": "None",
    "searchWithYourSignUpLanguage": "false",
    "mouserPaysCustomsAndDuties": false
  }
}
```

**V2 part-number + manufacturer** — `POST /api/v2/search/partnumberandmanufacturer?apiKey={key}`
```json
{
  "SearchByPartMfrNameRequest": {
    "mouserPartNumber": "CL05B104KO5NNNC",
    "manufacturerName": "Samsung Electro-Mechanics",
    "partSearchOptions": "None",
    "mouserPaysCustomsAndDuties": false
  }
}
```

**V2 manufacturer list** — `GET /api/v2/search/manufacturerlist?apiKey={key}` (no body).

Enum values (CONFIRMED):

- `searchOptions`: `None` | `Rohs` | `InStock` | `RohsAndInStock`
- `partSearchOptions`: `None` | `Exact`

### 5.5 Search response envelope (CONFIRMED)

All search endpoints return the same envelope: a top-level `Errors` array and a `SearchResults` object.

```json
{
  "Errors": [],
  "SearchResults": {
    "NumberOfResult": 50,
    "Parts": [
      {
        "MouserPartNumber": "594-MFR123",
        "ManufacturerPartNumber": "MFR123",
        "Manufacturer": "Vishay",
        "Description": "Resistor example",
        "Category": "Resistors",
        "Availability": "In Stock",
        "FactoryStock": "1000",
        "LeadTime": "0 weeks",
        "LifecycleStatus": "Active",
        "Min": "1",
        "Mult": "1",
        "DataSheetUrl": "https://...",
        "ImagePath": "https://...",
        "ProductDetailUrl": "https://...",
        "Reeling": false,
        "ROHSStatus": "RoHS Compliant",
        "IsDiscontinued": "false",
        "PriceBreaks": [ { "Quantity": 1, "Price": "0.25", "Currency": "USD" } ],
        "ProductAttributes": [ { "AttributeName": "Resistance", "AttributeValue": "10k", "AttributeCost": "" } ],
        "AlternatePackagings": []
      }
    ]
  }
}
```

**Critical parsing rule:** check `Errors` first. A `200` with a non-empty `Errors` array means the request was rejected (bad key, malformed body). `SearchResults.Parts` may be empty even on success.

### 5.6 Python — Mouser search client

```python
import os, requests

class MouserSearchClient:
    BASE = "https://api.mouser.com/api"

    def __init__(self):
        self.key = os.environ["MOUSER_SEARCH_API_KEY"]

    def _post(self, path, payload):
        resp = requests.post(
            f"{self.BASE}{path}",
            params={"apiKey": self.key},                # key goes in the QUERY STRING
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("Errors"):
            raise RuntimeError(f"Mouser error: {data['Errors']}")
        return data.get("SearchResults", {})

    def search_keyword(self, keyword, records=50, starting_record=0,
                       search_options="None"):
        return self._post("/v1/search/keyword", {
            "SearchByKeywordRequest": {
                "keyword": keyword,
                "records": records,
                "startingRecord": starting_record,
                "searchOptions": search_options,
                "searchWithYourSignUpLanguage": "false",
            }
        })

    def search_partnumbers(self, part_numbers, exact=True):
        """part_numbers: list of up to 10 strings."""
        joined = "|".join(part_numbers[:10])
        return self._post("/v1/search/partnumber", {
            "SearchByPartRequest": {
                "mouserPartNumber": joined,
                "partSearchOptions": "Exact" if exact else "None",
            }
        })

    def search_part_with_mfr(self, part_number, manufacturer, exact=True):
        return self._post("/v2/search/partnumberandmanufacturer", {
            "SearchByPartMfrNameRequest": {
                "mouserPartNumber": part_number,
                "manufacturerName": manufacturer,
                "partSearchOptions": "Exact" if exact else "None",
            }
        })
```

### 5.7 Cart API (V1) — for the "generate order cart" workflow

All cart endpoints use `MOUSER_ORDER_API_KEY` as `?apiKey=`. A cart is identified by a `CartKey` (UUID). Passing an all-zero `CartKey` creates a new cart; the response returns the real key to reuse.

| Operation | Method | Path |
|---|---|---|
| Get cart | GET | `/api/v1/cart?apiKey={key}&cartKey={cartKey}` |
| Replace whole cart | POST | `/api/v1/cart?apiKey={key}` |
| Insert items | POST | `/api/v1/cart/items/insert?apiKey={key}` |
| Update items | POST | `/api/v1/cart/items/update?apiKey={key}` |
| Remove item | POST | `/api/v1/cart/item/remove?apiKey={key}` |
| Insert schedule | POST | `/api/v1/cart/insert/schedule?apiKey={key}` |
| Update schedule | POST | `/api/v1/cart/update/schedule?apiKey={key}` |
| Delete all schedules | POST | `/api/v1/cart/deleteall/schedule?apiKey={key}` |

> "Replace whole cart" (`POST /cart`) **deletes any part numbers not included in the request**. Prefer `items/insert` / `items/update` for incremental changes.

Insert items request (CONFIRMED shape):
```json
{
  "CartKey": "00000000-0000-0000-0000-000000000000",
  "MouserPaysCustomsAndDuties": false,
  "CartItems": [
    { "MouserPartNumber": "594-MFR123", "Quantity": 100,
      "CustomerPartNumber": "R-10K-0402", "PackagingChoice": "None" }
  ]
}
```

- `PackagingChoice` enum: `None` | `Cut_Tape` | `MouseReel` | `FullReel`.
- `MouserPartNumber` max 80 chars; `CustomerPartNumber` max 21 chars.

Cart response (CONFIRMED shape): `CartKey`, `CurrencyCode`, `CartItems[]` (OrderLine objects with `MouserPartNumber`, `MfrPartNumber`, `Quantity`, `UnitPrice`, `ExtendedPrice`, `Manufacturer`, `Description`, `LifeCycle`, `ScheduledReleases[]`, `additionalFees[]`), `TotalItemCount`, `MerchandiseTotal`, `additionalFeesTotal`, `Errors[]`.

### 5.8 Order API (V1) — HUMAN-APPROVAL GATED

| Operation | Method | Path |
|---|---|---|
| Order options (shipping/payment/tax) | POST | `/api/v1/order/options/query?apiKey={key}` |
| Currencies | GET | `/api/v1/order/currencies?apiKey={key}` |
| Countries | GET | `/api/v1/order/countries?apiKey={key}` |
| Submit / preview order | POST | `/api/v1/order?apiKey={key}` |
| Create order from old order | POST | `/api/v1/order/CreateFromOrder?apiKey={key}` |
| Get order by number | GET | `/api/v1/order/{orderNumber}?apiKey={key}` |
| Create cart from order | POST | `/api/v1/order/item/CreateCartFromOrder?apiKey={key}` |

Submit order request (CONFIRMED shape):
```json
{
  "Order": {
    "ShippingAddress": { "CountryCode": "US", "FirstName": "…", "LastName": "…",
                          "AddressOne": "…", "City": "…", "PhoneNumber": "…" },
    "OrderType": "Unspecified",
    "PrimaryShipping": { "Code": 0 },
    "Payment": { "Method": 0 },
    "CurrencyCode": "USD",
    "CartKey": "{cartKey}",
    "SubmitOrder": false
  }
}
```

> **`SubmitOrder`**: `false` → returns an **order summary / preview** (safe, no money moves). `true` → **places the order**. Per AutoBOM's human-approval principle, AutoBOM code must keep `SubmitOrder=false` and surface the preview for explicit human approval. Only a deliberate, human-triggered action should ever send `true`. Placing a Mouser order requires a valid Mouser account with payment set up.

### 5.9 Order History (V1)

| Operation | Method | Path |
|---|---|---|
| By date filter | GET | `/api/v1/orderhistory/ByDateFilter?apiKey={key}&...` |
| By date range | GET | `/api/v1/orderhistory/ByDateRange?apiKey={key}&...` |
| By sales order # | GET | `/api/v1/orderhistory/salesOrderNumber?apiKey={key}&...` |
| By web order # | GET | `/api/v1/orderhistory/webOrderNumber?apiKey={key}&...` |

Order-history summary object fields: `DateCreated`, `SalesOrderNumber`, `WebOrderNumber`, `PoNumber`, `BuyerName`, `OrderStatusDisplay`.


---

## 6. Cross-cutting implementation rules (apply to both suppliers)

### 6.1 Secrets
Load every credential from environment variables (`.env` via `python-dotenv`). Never commit keys. Keep the `.env` in `.gitignore` (the project already does).

### 6.2 Retry & backoff
Retry only on `429`, `500`, `502`, `503` and network timeouts. Do **not** retry `400`/`401`/`404` blindly. On `401`, refresh the DigiKey token exactly once and retry; if it fails again, surface the error. Use exponential backoff (`2 ** attempt`, capped) and honor `X-RateLimit-Reset` when present.

```python
import time, requests

RETRYABLE = {429, 500, 502, 503}

def with_retries(fn, max_attempts=4):
    for attempt in range(max_attempts):
        try:
            resp = fn()
        except requests.Timeout:
            time.sleep(2 ** attempt); continue
        if resp.status_code in RETRYABLE:
            wait = int(resp.headers.get("X-RateLimit-Reset", 2 ** attempt))
            time.sleep(min(wait, 30)); continue
        return resp
    return resp
```

### 6.3 Caching
Both suppliers cap you near **1,000 lookups/day**. Cache successful part lookups (the project already has `supplier_lookup_cache.py`) keyed by `(supplier, part_number, options)` with a sensible TTL (e.g. pricing/stock ~1–6 h, static specs ~days). This is the single biggest lever for staying under limits and keeping the platform fast.

### 6.4 Batching
- Mouser: batch up to 10 part numbers per `search/partnumber` call.
- DigiKey V4: `KeywordSearch` returns up to 50 per page; page with `Offset` only when needed. For a single known MPN use `ProductDetails`, not a keyword search.

### 6.5 Human-approval gate (AutoBOM principle #4)
Automation may **source, compare, recommend, and build carts/order previews**. Automation must **never** auto-submit a supplier order, auto-approve a purchase, or move money. Concretely:
- Mouser: keep `Order.SubmitOrder = false`; expose the preview; require an explicit human action to ever set it `true`.
- DigiKey: the Ordering API requires an active DigiKey Credit account and is likewise gated — generate the cart/order package, then stop for approval.

### 6.6 Traceability & logging (AutoBOM principle #2)
Log every outbound request with: supplier, endpoint, request id / correlation id, status code, rate-limit-remaining, and latency. Never log full API keys or tokens (mask to last 4). Persist which supplier/endpoint produced each sourced price so any component can be traced back to its source call.

### 6.7 Normalization
DigiKey and Mouser return different field names for the same concept. Normalize into one internal schema so the rest of AutoBOM is supplier-agnostic:

| Internal field | DigiKey V4 source | Mouser source |
|---|---|---|
| `supplier_part_number` | `ProductVariations[].DigiKeyProductNumber` | `MouserPartNumber` |
| `manufacturer_part_number` | `ManufacturerProductNumber` | `ManufacturerPartNumber` |
| `manufacturer` | `Manufacturer.Name` | `Manufacturer` |
| `description` | `Description.ProductDescription` | `Description` |
| `quantity_available` | `QuantityAvailable` | `Availability` / `FactoryStock` |
| `unit_price` (qty 1) | `ProductVariations[].StandardPricing[].UnitPrice` | `PriceBreaks[].Price` |
| `price_breaks` | `ProductVariations[].StandardPricing[]` | `PriceBreaks[]` |
| `lifecycle_status` | `ProductStatus.Status` | `LifecycleStatus` |
| `datasheet_url` | `DatasheetUrl` | `DataSheetUrl` |
| `moq` | `ProductVariations[].MinimumOrderQuantity` | `Min` |
| `rohs` | (parameter / status) | `ROHSStatus` |

> Casing trap: the datasheet field is `DatasheetUrl` (lowercase "s") on DigiKey V4 but `DataSheetUrl` (capital "S") on Mouser. They are not interchangeable — pin each key exactly as the live response returns it.

---

## 7. Field reference

### 7.1 Mouser `MouserPart` (CONFIRMED fields)

`MouserPartNumber`, `ManufacturerPartNumber`, `Manufacturer`, `Description`, `Category`, `Availability`, `FactoryStock`, `LeadTime`, `LifecycleStatus`, `Min`, `Mult`, `DataSheetUrl`, `ImagePath`, `ProductDetailUrl`, `Reeling` (bool), `ROHSStatus`, `IsDiscontinued`, `RTM`, `SuggestedReplacement`, `PriceBreaks[]` (`Quantity` int, `Price` str, `Currency` str), `ProductAttributes[]` (`AttributeName`, `AttributeValue`, `AttributeCost`), `AlternatePackagings[]`, `AvailabilityOnOrder[]`, `SurchargeMessages[]`, `TradeCompliance[]`.

### 7.2 Mouser error object (CONFIRMED)

`Id` (int), `Code`, `Message`, `ResourceKey`, `ResourceFormatString`, `ResourceFormatString2`, `PropertyName`.

### 7.3 DigiKey V4 Product (key fields, VERIFY-IN-SANDBOX)

`ManufacturerProductNumber`, `Manufacturer.Name`, `Description.ProductDescription`, `Description.DetailedDescription`, `ProductVariations[]` (`DigiKeyProductNumber`, `PackageType.Name`, `MinimumOrderQuantity`, `StandardPricing[]` with `BreakQuantity`/`UnitPrice`/`TotalPrice`), `QuantityAvailable`, `ProductStatus.Status`, `DatasheetUrl`, `PhotoUrl`, `ProductUrl`, `Parameters[]` (name/value spec pairs).

---

## 8. Quick reference cheat sheet

```
DIGIKEY
  Auth:    POST {base}/v1/oauth2/token  (form-urlencoded, client_credentials)  -> token 10 min
  Base:    {base}/products/v4
  Headers: Authorization: Bearer <t> | X-DIGIKEY-Client-Id | X-DIGIKEY-Locale-Site/Language/Currency | Content-Type/Accept: application/json
  Search:  POST /products/v4/search/keyword            body {"Keywords":"...","Limit":<=50,"Offset":n}
  Detail:  GET  /products/v4/search/{urlencoded_pn}/productdetails
  Limits:  Product Information 120/min, 1000/day. Watch X-RateLimit-* headers.

MOUSER  (key in QUERY STRING, not header)
  Search key: MOUSER_SEARCH_API_KEY | Order key: MOUSER_ORDER_API_KEY
  KW:      POST /api/v1/search/keyword?apiKey=K      {"SearchByKeywordRequest": {...}}
  PN:      POST /api/v1/search/partnumber?apiKey=K   {"SearchByPartRequest": {"mouserPartNumber":"a|b|... (<=10)"}}
  PN+Mfr:  POST /api/v2/search/partnumberandmanufacturer?apiKey=K {"SearchByPartMfrNameRequest": {...}}
  Resp:    { "Errors":[], "SearchResults": { "NumberOfResult":n, "Parts":[...] } }  <- check Errors first
  Cart:    POST /api/v1/cart/items/insert?apiKey=K    (CartKey 000...0 = new cart)
  Order:   POST /api/v1/order?apiKey=K   SubmitOrder=false => PREVIEW (keep false; human approves)
  Limits:  ~1000 calls/day. Batch 10 PNs per call. Cache aggressively.

NEVER: auto-submit orders, move money, or approve purchases without a human. Cache lookups. Mask secrets in logs.
```

---

*Sources: DigiKey developer portal (developer.digikey.com — documentation, products, Product Information V4 pages) and Mouser API Swagger specs (api.mouser.com/api/docs/V1 and /V2), retrieved 2026-07-18. Fields marked VERIFY-IN-SANDBOX should be confirmed against a live sandbox/production response before release, as suppliers extend schemas over time.*
