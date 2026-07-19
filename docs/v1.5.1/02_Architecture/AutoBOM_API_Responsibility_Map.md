# AutoBOM API Responsibility Map

**Purpose:** Concrete per-API responsibilities. Which external system owns which questions. Which endpoints to use for which flows. Anti-patterns that violate the API leverage principle.

**Companion documents:**
- `AutoBOM_Platform_Architecture.md` — where these APIs plug in
- `AutoBOM_Data_Flow_and_Sequencing.md` — when in the flow each API gets called
- `AutoBOM_Code_to_Service_Connections.md` — which code files consume each API

**Audience:** Claude Code (integration reference), Claude Architect (cross-wiring audit).

---

## 1. The API leverage principle (recap)

> AutoBOM orchestrates; APIs do the domain-heavy work.

Every capability decision defaults to leveraging existing API capability before building it inside AutoBOM. Each API is called for questions **inside its domain**.

**Do not cross-wire APIs to answer questions their system doesn't own.**

- DigiKey's Barcode Search API does NOT validate a receiving scan (PartsBox does).
- Mouser's Search API does NOT look up a part in your inventory (PartsBox does).
- PartsBox's part records do NOT provide supplier stock or pricing (Mouser/DigiKey do).

This document exists to make the correct-vs-wrong choice explicit at every integration point.

---

## 2. PartsBox

**Owns:** Physical inventory reality. Storage locations. Part attachments. Build records. Native barcode scanning.

**Auth:** API key in header. Single key per Anthropic instance (Aaron's commercial plan).

**Base URL:** PartsBox API v2 endpoints (per Aaron's plan documentation).

**Not owned by PartsBox:** catalog details beyond what's stored on the part record, supplier pricing, supplier stock at Mouser/DigiKey, order fulfillment lifecycle.

### 2.1 Endpoints AutoBOM uses

#### Search and read

| Endpoint | Purpose | Called by |
|---|---|---|
| `POST /api/1/part/all` | Full-part-list search — MPN, keyword, filter | search_available_stock mode (app-wide search bar) |
| `POST /api/1/part/get` | Detail on a specific part | Part detail lookups |
| `POST /api/1/storage/all` | Storage location list — full inventory of storage | Inventory tab of embedded surface, storage location search results |
| `POST /api/1/storage/get` | Detail on a specific storage location | Storage location detail surface |
| `POST /api/1/storage/parts` | Parts within a specific storage location | Storage location detail parts list |
| `POST /api/1/stock/get` | Per-part per-location stock levels | Two on-hand qtys on BOM lines (In project box + On wall) |

#### Write

| Endpoint | Purpose | Called by |
|---|---|---|
| `POST /api/1/part/create` | Create new part | B2-Guarded flow (auto-create validated MPN OR local-part) |
| `POST /api/1/part/attachments` | Attach file to part | Datasheet lifecycle (with `attachment/type = "datasheet"`) |
| `POST /api/1/storage/create` | Create storage location | Project box creation at Project creation time |
| `POST /api/1/stock/add` | Add stock to a location | Receiving flow (Case A, B1, C, D, E resolutions) |
| `POST /api/1/stock/remove` | Remove stock (build consumption) | Build execution — deducted PER LINE per overlay state |
| `POST /api/1/build/create` | Create build record | Build execution — logs the build in PartsBox |

#### QR / identification

| Endpoint | Purpose | Called by |
|---|---|---|
| PartsBox ID Anything™ QR image endpoint | Generate QR image for a build | Build result screen (renders QR inline) |

**Response format:** Image with image Content-Type. AutoBOM renders inline, does not decode or process the image content.

### 2.2 Native barcode scanning

PartsBox's native scanning UI can be embedded via iframe OR AutoBOM can implement the scan input and pass the raw barcode to PartsBox's parsing endpoint.

**AutoBOM currently uses:** PartsBox scan handled by their native browser scanning UI, embedded in the receiving flow. Response returns `{ mpn, manufacturer, quantity, distributorSku, cpn }`.

**Not called by AutoBOM ever:** Mouser Barcode Search API. DigiKey Barcode Search API. These would cross-wire.

### 2.3 Cache behavior for PartsBox

All PartsBox READ calls flow through Cache Layer with configurable TTL (default 60s, Admin range 10-3600s).

Cache invalidation on any PartsBox WRITE call — cache entries touching affected part or storage location invalidate immediately.

Rate limit: PartsBox's rate limit is respected. Cache queue backs off with exponential delay if rate-limited.

### 2.4 PartsBox anti-patterns

- ❌ Building AutoBOM's own storage location detail screen that fetches from PartsBox and re-renders — **acceptable if adding annotations**. Just PASSING THROUGH to PartsBox UI (link out) is fine too. But re-implementing storage-detail behavior redundantly is wrong.
- ❌ Storing PartsBox part records in AutoBOM's DB as source of truth — always fetch via API.
- ❌ Implementing QR generation in AutoBOM — call ID Anything™.
- ❌ Building AutoBOM's own barcode parser — use PartsBox native scanning.
- ❌ Duplicating PartsBox part attachments in AutoBOM — attach to PartsBox via `part/attachments`.
- ❌ Managing storage-kind semantics separately from PartsBox tags — read `development` / `production` / `autobom-managed` tags from PartsBox; AutoBOM adds annotations but does not override PartsBox's tag data.

---

## 3. Mouser

**Owns:** Catalog details (MPN, manufacturer, description, characteristics, pricing, stock at Mouser). Cart building.

**Auth:** Two separate API keys — Search API key and Cart/Order API key. Per Mouser's documentation, these are managed independently.

**Base URL:** Mouser API endpoints per their v2 documentation.

**Not owned by Mouser:** DigiKey's catalog, actual inventory at your facility, order placement (Mouser's own UI owns this).

### 3.1 Endpoints AutoBOM uses

#### Search / catalog

| Endpoint | Purpose | Called by |
|---|---|---|
| `POST /api/v2/search/partnumber` | MPN lookup — exact or partial | Sourcing Engine `validateMpn(mpn)`, characteristic search fallback |
| `POST /api/v2/search/keyword` | Keyword-based search | Characteristic search fallback (Mouser's parametric is weaker than DigiKey's) |
| `POST /api/v2/search/manufacturerlist` | Get manufacturers matching a query | Bidirectional Manufacturer typeahead in Push-Back resolution |

**Return values include:** Part details, stock quantity, unit price, price breaks, datasheet URL (when non-null), datasheet name, product URL, manufacturer, packaging, RoHS status.

#### Cart

| Endpoint | Purpose | Called by |
|---|---|---|
| `POST /api/v1/cart/add_items_to_cart` | Add multiple items to a cart | Batch flush pipeline (Step 2 for Mouser group) |
| `POST /api/v1/cart/create` (if needed) | Create new cart | Same |

**Cart line customer reference:** Cart line items support a customer reference field (typically labeled `CustomerPartNumber` or `Reference` in Mouser's API). This is where CPN gets written at cart-build.

**Cart URL:** Returned by cart creation/modification response — real Mouser cart URL Josh clicks in the sheet.

### 3.2 Mouser parametric filtering caveat

Mouser's Search API supports keyword search well but has **weaker parametric filtering** than DigiKey. The Sourcing Engine handles this by:

1. Attempting characteristic query via keyword + spec-related hints in the query string
2. Fetching a larger result set than needed
3. Applying client-side filtering to narrow to actual characteristic matches
4. Ranking and returning

This is intentional — DigiKey is primary for parametric queries; Mouser is primary for MPN-based lookups where its response format is clean.

### 3.3 Mouser cache behavior

Search results cached with default 5-minute TTL. Cart operations NOT cached (transactional).

### 3.4 Mouser anti-patterns

- ❌ Calling Mouser Cart API's cart-submit endpoint — violates No autonomous purchases tenet.
- ❌ Calling Mouser Barcode Search for receiving — cross-wires with PartsBox scanning domain.
- ❌ Using Mouser Search response as the source of truth for what's in AutoBOM inventory — that's PartsBox's job.
- ❌ Storing full Mouser catalog in AutoBOM DB — always fetch on demand with cache.
- ❌ Building custom parametric UI that mirrors Mouser's without leveraging their Search API — extract what their API provides, don't rebuild.

---

## 4. DigiKey

**Owns:** Catalog details, native parametric filters, pricing, stock at DigiKey. MyLists (analogous to Mouser Cart). Product Change Notifications (future).

**Auth:** OAuth 2.0 client credentials flow. Client ID + Client Secret. Bearer token with expiration; refresh required. AuthService manages token lifecycle.

**Base URL:** DigiKey Product Information V4 (current) + MyLists endpoints.

**Not owned by DigiKey:** Mouser's catalog, actual inventory at your facility, order placement (DigiKey's own UI owns this).

### 4.1 Endpoints AutoBOM uses

#### Product Information V4 — Search

| Endpoint | Purpose | Called by |
|---|---|---|
| `POST /products/v4/search/productsearch` | Full parametric + keyword search | Sourcing Engine characteristic search (search_suppliers mode) |
| `POST /products/v4/search/keywordsearch` | Keyword-based search | MPN lookup, general search |
| `GET /products/v4/search/productdetails/{productNumber}` | Detail on specific product | Individual part detail |
| `GET /products/v4/search/{productNumber}/pricing` | Price breaks + stock | Pricing display |

#### FilterOptions and ParametricFilters (KEY unlock)

**DigiKey exposes parametric filters natively via the ProductSearch response.** The response includes `FilterOptions.ParametricFilters[]` — a first-class list of parametric filter dimensions applicable to that category.

AutoBOM's Sourcing Engine:
1. Translates AutoBOM characteristic query → DigiKey `ParametricFilters` in the request
2. Receives structured `FilterOptions` in response
3. Renders result cards using the parametric filter values directly

**This eliminates client-side parametric matching for DigiKey queries.** DigiKey does the parametric work; AutoBOM presents the results.

Filter dimensions example (for a specific category like Chip Resistors):
- Resistance
- Tolerance
- Power (Watts)
- Composition
- Temperature Coefficient
- Package / Case
- Operating Temperature

Each filter dimension has enumerable value ranges — AutoBOM constructs the request accordingly.

#### MyLists

| Endpoint | Purpose | Called by |
|---|---|---|
| `POST /mylists/v1/lists` (`create_list`) | Create new list | Batch flush pipeline (Step 2 for DigiKey group) |
| `POST /mylists/v1/lists/{listId}/parts` (`add_parts_to_list`) | Add parts to list | Same |
| `GET /mylists/v1/lists/{listId}` | Retrieve list | Cart URL reconstruction if needed |

**List URL:** Returned by list creation response — real DigiKey list URL Josh clicks in the sheet. List URL is stable while the list exists.

**List line reference:** DigiKey supports a per-line reference / CustomerPartNumber field. This is where CPN gets written.

#### Product Change Notifications (deferred, future scope)

| Endpoint | Purpose | Called by |
|---|---|---|
| PCN API | Product Change Notifications for EOL / obsolescence alerts | FUTURE: proactive Push-Back suggestions before EOL hits |

Not called in v1.5 MVP.

### 4.2 DigiKey Barcode API

Exists. **NOT called by AutoBOM** — PartsBox owns scanning. Cross-wiring here would violate the API leverage principle.

### 4.3 DigiKey cache behavior

Product Information calls cached with default 5-minute TTL. MyLists operations NOT cached.

ParametricFilters response cached with same TTL — response structure changes rarely for a given category.

### 4.4 DigiKey OAuth handling

- Token expiration handled by AuthService — refresh flow runs before token expiry
- Token expiration during a batch flush → flush pauses waiting for refresh
- Refresh failure → Admin notified (Refresh inline action on Dashboard)

### 4.5 DigiKey anti-patterns

- ❌ Calling DigiKey MyLists submit-order endpoint — violates No autonomous purchases tenet.
- ❌ Calling DigiKey Barcode API for receiving — cross-wires with PartsBox scanning.
- ❌ Building client-side parametric filter matching for DigiKey results — **use their ParametricFilters directly**.
- ❌ Storing DigiKey list content in AutoBOM DB as source of truth — the list URL is the URL. AutoBOM stores the URL, not the content.
- ❌ Duplicating pricing/stock in AutoBOM DB — always fetch on demand.

---

## 5. Microsoft Graph (OneDrive)

**Owns:** Josh's Daily Purchasing List (Excel workbook stored in OneDrive).

**Auth:** OAuth 2.0 with delegated permissions to Josh's OneDrive scope, or application permissions if AutoBOM authenticates as a service account.

**Base URL:** Microsoft Graph v1.0 endpoints.

**Not owned by Graph:** anything that isn't OneDrive (Teams, SharePoint outside OneDrive drive, etc.).

### 5.1 Endpoints AutoBOM uses

| Endpoint | Purpose | Called by |
|---|---|---|
| `PATCH /me/drive/items/{item-id}/workbook/worksheets/{sheet}/tables/{table}/rows/add` OR `POST /me/drive/items/{item-id}/workbook/worksheets/{sheet}/range(address='...')` | Append rows to Josh's Daily Purchasing List | Batch flush pipeline (Step 3) |
| `GET /me/drive/items/{item-id}/workbook/worksheets/{sheet}/tables/{table}/rows` | Read rows | **NEVER CALLED. Sheet-write is one-way.** |

### 5.2 Sheet write mechanics

Each row-write operation:
- Target workbook + worksheet identified by config (Admin can update the target)
- Row data as an ordered array of 12 values matching the 12-column commitment
- Column ordering per PRD v1.5 Section 11.4 and Purchasing v4.1 Section 4.2

### 5.3 Sheet-write failure handling

- Graph API rate limits respected
- Auth token refresh handled automatically
- Concurrent writes serialized within AutoBOM (queue) to avoid conflicts (Excel workbook is single-writer at row level)
- Failure → batch stays Pending (Section 3.3 of Data Flow doc)

### 5.4 Graph anti-patterns

- ❌ Reading Josh's sheet to reconcile state — sheet-write is one-way; internal state is truth.
- ❌ Adding columns to Josh's sheet — 12-column commitment absolute.
- ❌ Writing to any workbook other than the configured target — one workbook, one target.
- ❌ Writing CPN to any column — CPN lives elsewhere.

---

## 6. AutoBOM's own database

**Owns:** All cross-workflow state that no single external API owns.

**Not covered by external APIs:**
- Bucket state and batch state (Purchasing pipeline)
- CPN issuance records with format versioning
- Push-Back objects with structured fields
- Program object and Program-Project relationship (specifically our workflow's use)
- Master BOM state machine (draft → validated → sourcing → results → normalised → submitted → exceptions)
- Build overlay state per line (used/skipped/deferred/rework)
- User roles and multi-role state
- Configuration (Admin Bounded Authority values)
- Audit log
- Force-Waivers log
- Notification records with routing metadata

### 6.1 Database is source of truth for these things

Even where an external system might have a mirror (e.g., PartsBox has a project BOM that mirrors AutoBOM's master BOM), AutoBOM's DB is the source of truth for AutoBOM-side workflow state. The PartsBox mirror is downstream — updates flow AutoBOM DB → PartsBox on state transitions (like Push-Back resolution).

### 6.2 Database is NOT source of truth for

- Physical inventory (PartsBox is)
- Storage location existence and structure (PartsBox is)
- Datasheets (PartsBox is, once attached)
- Supplier catalog (Mouser + DigiKey are)
- Josh's sheet content (we write; we don't re-read)

---

## 7. Cross-wiring warnings (summary)

Consolidated list of every anti-pattern from Sections 2-5:

**Never do:**
- Call Mouser Barcode Search or DigiKey Barcode API during receiving. PartsBox owns scanning.
- Call any supplier's order-submit endpoint. Violates No autonomous purchases tenet.
- Build QR generation in AutoBOM. Call PartsBox ID Anything™.
- Build barcode parser in AutoBOM. Use PartsBox native scanning.
- Build client-side parametric filtering for DigiKey. Use their ParametricFilters natively.
- Store supplier catalog in AutoBOM DB as source of truth. Fetch on demand with cache.
- Store PartsBox part records in AutoBOM DB as source of truth. Fetch on demand.
- Read Josh's sheet. Sheet-write is one-way.
- Add columns to Josh's sheet. 12-column commitment absolute.
- Write CPN to Josh's sheet. CPN lives in cart line customer reference field + internal state.
- Duplicate datasheets in AutoBOM. Attach to PartsBox.
- Duplicate PartsBox tags with different semantics. Read PartsBox tags as truth.

---

## 8. Configuration values for external APIs (Bounded Admin)

Admin can configure the following API integration values via Configuration → Suppliers or → System Settings tabs. Each has bounds.

| Setting | Type | Bounds | Notes |
|---|---|---|---|
| PartsBox API key | Secure string | Non-empty | Not displayed in UI after entry; rotated via key regeneration flow |
| Mouser Search API key | Secure string | Non-empty | Same |
| Mouser Cart API key | Secure string | Non-empty | Separate key per Mouser's design |
| DigiKey Client ID | String | Non-empty | OAuth client id |
| DigiKey Client Secret | Secure string | Non-empty | OAuth client secret |
| DigiKey OAuth environment | Enum | Sandbox / Production | Determines base URL |
| Microsoft Graph OAuth config | Secure string / OAuth flow | Follows Graph auth flow | Delegated permissions to Josh's OneDrive |
| PartsBox cache TTL | Integer seconds | 10 - 3600 | Default 60 |
| Supplier catalog cache TTL | Integer seconds | 60 - 3600 | Default 300 |
| Datasheet URL cache TTL | Integer hours | 1 - 168 | Default 24 |
| Batch flush timer — Critical | Integer minutes | 15 - 1440 | Default 180 |
| Batch flush timer — Main | Integer minutes | 15 - 1440 | Default 360 |
| Batch flush retry count | Integer | 1 - 10 | Default 3 |
| Push-Back escalation window | Integer hours | 1 - 168 | Default 24 |
| Distributor priority | Radio | Mouser first / DigiKey first | Affects sourcing engine result ordering |
| Freshness threshold (sourcing) | Enum | 1h / 4h / 12h / 24h / 48h / 7d | Default 24h |
| Alternate-part policy | Toggle | Auto-suggest / Require sign-off | Default Auto-suggest |

Every configuration change:
- Validated against schema
- Written to audit log with before/after
- Applies immediately after save (no restart required)
- Admin can dry-run before applying (see runtime observability in Platform Architecture doc)

---

## 9. What to reach for in each common flow

Quick lookup for Claude Code — when building each flow, which APIs matter:

### 9.1 App-wide search bar keystroke

1. Cache Layer check for query
2. If miss → PartsBox `part/all` + `storage/all` (parallel) via Sourcing Engine `search_available_stock`
3. If Include suppliers toggle → also Mouser Search + DigiKey ProductSearch (parallel) via Sourcing Engine

### 9.2 Push-Back resolution characteristic search

1. Sourcing Engine `search_suppliers` with characteristic filters
2. Primary: DigiKey ProductSearch with translated ParametricFilters (native filtering)
3. Fallback: Mouser Search with keyword + spec hints + client-side filter
4. If Include wall toggle → PartsBox `part/all` in parallel
5. Datasheet URLs harvested from response for display

### 9.3 Attach replacement (datasheet auto-attach)

1. Check PartsBox part for existing `attachment/type = datasheet`
2. If none → fetch datasheet URL (from cached supplier response or re-query)
3. Download PDF (background job)
4. `part/attachments` POST with `attachment/type = "datasheet"`

### 9.4 Bucket flush pipeline

1. Group bucket entries by supplier
2. For Mouser group → `add_items_to_cart` (with CPN in customer reference)
3. For DigiKey group → `create_list` + `add_parts_to_list` (with CPN in reference)
4. Retrieve URLs
5. Microsoft Graph → write rows to Josh's sheet (one per supplier per batch)
6. Update batch state → WRITTEN atomically

### 9.5 Receiving scan

1. PartsBox native scanning → parse scan result
2. AutoBOM CPN issuance table lookup
3. Decision Engine `selectReceivingCase(scanResult, cpnRecord)` → A/B1/B2/C/D/E
4. Case handler executes:
   - Case A: `stock/add` to expected location
   - Case B1: prompt → update location assignment → `stock/add`
   - Case B2: Sourcing Engine `validateMpn` → `part/create` (if valid) → `stock/add`
   - Case C: prompt → `stock/add` to selected location
   - Case D: prompt → identify → `stock/add`
   - Case E: `stock/add` + Over flag
5. Cache Layer invalidate for affected part + location
6. Update fulfillment pill in Purchasing archive (DB write)

### 9.6 Run Build

1. Decision Engine `gateRunBuild(build)` → allowed / blocked with reasons
2. If allowed → PartsBox `build/create` with consumption plan
3. `stock/remove` per line per overlay state (batched or per-line depending on PartsBox API surface)
4. On success → PartsBox ID Anything™ QR endpoint → render inline
5. Update Build state → complete

---

## 10. Future API integrations (roadmap)

Reserved but not implemented in v1.5 MVP:

- **DigiKey Product Change Notifications API** — proactive EOL alerts feeding Push-Back suggestions
- **Additional suppliers (Newark, etc.)** — Sourcing Engine already abstracts supplier clients; add as new modules
- **Microsoft Teams API** — Push notifications to Teams channels (currently just in-app notifications)
- **Email API** — Send email notifications (currently in-app only)
- **ERP APIs** — outbound events for ERP integration
- **Analytics APIs** — data warehouse dumps for reporting

None of these are called in v1.5. Architecture reserves capacity via the abstract Sourcing Engine + NotificationService interfaces.
