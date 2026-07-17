# AutoBOM Platform Architecture

**Purpose:** The service topology of AutoBOM. Which services exist, what each owns, how they communicate, what depends on what.

**Companion documents:**
- `AutoBOM_Data_Flow_and_Sequencing.md` — how data moves through these services
- `AutoBOM_API_Responsibility_Map.md` — external API responsibilities
- `AutoBOM_Code_to_Service_Connections.md` — code-level service mapping

**Audience:** Claude Code (build reference), Claude Architect (topology cross-check).

---

## 1. Service topology at a glance

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (SPA)                            │
│  React-style component tree · client-side routing · sessionStore │
└─────────────────────────────────────────────────────────────────┘
                              ↕ (fetch / websocket)
┌─────────────────────────────────────────────────────────────────┐
│                    AUTOBOM BACKEND SERVICES                      │
│                                                                  │
│   ┌────────────────────┐    ┌──────────────────────┐             │
│   │  Decision Engine   │◀──▶│   Sourcing Engine    │             │
│   │  (conductor)       │    │   (executor)         │             │
│   └─────────┬──────────┘    └──────────┬───────────┘             │
│             │                          │                         │
│   ┌─────────▼──────────────────────────▼──────────┐              │
│   │              Domain Services                   │              │
│   │  Program · Project · BOM · Build · Request     │              │
│   │  CPN Issuance · Push-Back · Batch · Bucket     │              │
│   │  Storage-Location-Metadata · Notification      │              │
│   └─────────┬──────────────────────────────────────┘              │
│             │                                                    │
│   ┌─────────▼──────────┐  ┌──────────────────┐  ┌────────────┐   │
│   │   Cache Layer      │  │   Audit Layer    │  │  Auth      │   │
│   │  (PartsBox TTL,    │  │   (immutable)    │  │  (Session/ │   │
│   │   supplier         │  │                  │  │   API-key) │   │
│   │   response cache)  │  │                  │  │            │   │
│   └─────────┬──────────┘  └──────────────────┘  └────────────┘   │
│             │                                                    │
│   ┌─────────▼──────────────────────────────────────┐             │
│   │      Database (AutoBOM primary state)          │             │
│   │  Programs, Projects, BOMs, Builds, Requests,   │             │
│   │  CPN Issuance, Push-Backs, Batches, Users,     │             │
│   │  Configuration, Audit Log, Force-Waivers Log   │             │
│   └────────────────────────────────────────────────┘             │
└─────────────────────────────────────────────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────────┐
│                    EXTERNAL SERVICES                             │
│                                                                  │
│   ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌────────────┐    │
│   │ PartsBox  │  │  Mouser   │  │  DigiKey  │  │  Microsoft │    │
│   │  API      │  │  API      │  │  API      │  │  Graph     │    │
│   │           │  │           │  │           │  │  (OneDrive)│    │
│   │ inventory │  │ catalog + │  │ catalog + │  │  Josh's    │    │
│   │ scanning  │  │ cart      │  │ cart      │  │  sheet     │    │
│   │ QR builds │  │           │  │ (parametric)│ │            │    │
│   └───────────┘  └───────────┘  └───────────┘  └────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Service inventory

### 2.1 Decision Engine (the conductor)

**Purpose:** Orchestrates cross-workflow decisions. Applies handshake rules, evaluates pathways, decides notifications. The single place workflow rules live.

**Responsibilities:**
- Push-Back routing (Program-linked → owner Designer first, standalone → pool; escalation windows)
- Bucket stream selection (Critical vs Main based on Request Critical toggle)
- Batch flush scheduling (timer expiration triggers, atomicity guarantees)
- Build gating (Run Build blocking on Push-Backs, coverage, waivers)
- Case selection at receiving (A-E)
- CPN generation dispatch (per-line at Request creation)
- Notification generation and routing

**Not responsible for:**
- Talking to external APIs directly (delegates to Sourcing Engine)
- Storing state (calls Domain Services which own storage)
- Rendering (that's frontend)

**Runtime observability (Bounded Admin Authority):**
- Dry-run mode: evaluate a decision without side effects, return what WOULD have happened
- Decision traces: every real invocation writes a structured trace (rules fired, order, result)
- Execute-as-user: run decisions as if a different user were driving, for reproduction

**Interface:**
```
decide(context) → { action, sideEffects[], notifications[], trace }

evaluateBOMStateTransition(bom, event) → nextState + effects
routeExceptionToDesigner(bom, pushback) → { targetDesigner, escalationTimer }
gateRunBuild(build) → { allowed, blockingReasons[] }
selectReceivingCase(scanResult, cpnRecord) → case ('A' | 'B1' | 'B2' | 'C' | 'D' | 'E')
```

**State:** Rule tables + configuration. Rules are versioned so old decisions remain interpretable.

---

### 2.2 Sourcing Engine (the executor)

**Purpose:** Talks to supplier APIs. Owns catalog queries, characteristic search, cart building, MPN validation, parametric filter translation. The single place supplier-facing logic lives.

**Responsibilities:**
- MPN lookup at Mouser + DigiKey (parallel by default)
- Characteristic-based part search — two modes:
  - `search_available_stock` — PartsBox primary, suppliers overlay (powers app-wide search bar)
  - `search_suppliers` — Mouser/DigiKey primary, PartsBox overlay (powers Push-Back resolution)
- Parametric filter translation — AutoBOM characteristic query → DigiKey `ParametricFilters` request
- Fallback keyword+client-filter for Mouser (weaker parametric support)
- MPN validation for B2-Guarded auto-creation (parallel query, return exists/not-exists)
- Cart building — Mouser Cart API `add_items_to_cart`, DigiKey MyLists API `create_list`+`add_parts_to_list`
- Datasheet URL retrieval (from supplier catalog response)
- Build-allocation logic (preserved from POC) — per-part order quantity factoring build multiplication, MOQs, price breaks

**Not responsible for:**
- Deciding WHICH suppliers to query (that's the caller — usually a workflow surface)
- Deciding what to DO with results (that's the Decision Engine or the caller)
- Storing results (that's Cache Layer for short-term, Database for durable)
- Order placement (out of scope — No autonomous purchases tenet)

**Interface:**
```
search_available_stock(query) → { inventory[], storageLocations[], suppliers[] }
search_suppliers(query, sourcePart?) → { suppliers[], wall[]? }
validateMpn(mpn) → { valid: boolean, sources: ['mouser'?, 'digikey'?], catalogRecord? }
buildCart(supplierGroup) → { cartUrl, cartTotal, lineCount }
translateCharacteristicsToDigiKey(characteristics) → { ParametricFilters[] }
```

**State:** Stateless. All state either transient (in-request) or delegated to Cache Layer.

**Separation from Decision Engine:** These are **two separate services**. Decision Engine decides what to do; Sourcing Engine executes supplier-facing work. Decision Engine calls Sourcing Engine; not the reverse.

---

### 2.3 Domain Services

Traditional domain services, one per object type. Each owns its persistence, queries, and validation.

| Service | Owns | Depends on |
|---|---|---|
| **ProgramService** | Programs, Program-Collection relationship | Database |
| **ProjectService** | Projects, program_id FK, Project↔Program-linked-cards | Database |
| **BOMService** | Master BOM per Project, versioning, state machine | Database, Sourcing Engine, Decision Engine |
| **BuildService** | Build objects, overlay states, variant declaration diff | Database, Decision Engine, PartsBox client |
| **CollectionService** | Collections, Collection→Program FK | Database, Sourcing Engine |
| **RequestService** | Request objects (bucket entries), bucketState | Database, CPN Service |
| **BucketService** | Two-stream bucket + Critical/Main queues | Database, Batch Service, Decision Engine (timer triggers) |
| **BatchService** | Batch objects, flush pipeline atomicity | Database, Sourcing Engine (carts), OneDrive client |
| **CPNIssuanceService** | CPN generation, format-versioned records, per-CPN fulfillment state | Database |
| **PushBackService** | Push-Back objects, structured fields, routing state | Database, Decision Engine (routing) |
| **StorageLocationMetadataService** | AutoBOM-side annotations on PartsBox storage locations (tags, ownership) | Database, PartsBox client |
| **NotificationService** | Notification generation, delivery, targetRole/verb/actionLabel structure | Database, Decision Engine |
| **UserService** | User CRUD, role assignment, multi-role state | Database |
| **ConfigurationService** | Bounded Admin config (CPN format, timers, TTL, etc.) with validation | Database |
| **AuditService** | Immutable audit log writes and queries | Database (audit table) |
| **ForceWaiverService** | Force-Waivers log entries | Database, Audit Service |

**Cross-service invariants:**
- Every write operation MUST invoke AuditService with actor + before + after state.
- Every state change of concern MUST invoke NotificationService if a party needs to know.
- Every configuration change MUST validate against ConfigurationService's schema.

---

### 2.4 Cache Layer

**Purpose:** Manage cache-with-TTL for PartsBox inventory queries and supplier catalog queries. Reduce API load; keep UI responsive.

**Cached data:**

| Cached content | Default TTL | Configurable | Refresh trigger |
|---|---|---|---|
| PartsBox part search results (by MPN, characteristics) | 60 seconds | Admin, 10–3600 seconds | On explicit user refresh; on write to any part in cache key |
| PartsBox storage location queries | 60 seconds | Same range | Same |
| Mouser catalog response for MPN | 5 minutes | Admin, 60–3600 seconds | On user refresh; on force-invalidate |
| DigiKey catalog response for MPN | 5 minutes | Same range | Same |
| DigiKey ParametricFilter response | 5 minutes | Same range | Same |
| Mouser cart operations | Not cached — cart building is transactional |
| DigiKey MyLists operations | Not cached — same reason |
| Datasheet URLs (from supplier response) | 24 hours | Admin | On explicit refresh; datasheets rarely revise for same MPN |

**Refresh-on-write:** Any write via AutoBOM (stock/add, part/create, storage assignment update) invalidates all cache entries whose keys include the affected object. Example: `stock/add(part=STM32G431)` invalidates all queries whose result set includes STM32G431 or the target storage location.

**Rate limiting:** Cache Layer respects external API rate limits. If PartsBox returns rate-limit response, cache queue backs off and retries with exponential delay. UI shows "Cache stale, refresh in Xs" during backoff.

**Interface:**
```
get(cacheKey, fallbackFn) → cachedValue OR fallbackFn() (which populates cache on return)
invalidate(cacheKey OR predicate)
refresh(cacheKey) — force fresh fetch, ignore TTL
metrics() — hit rate, miss rate, oldest entry age (Admin observability)
```

---

### 2.5 Audit Layer

**Purpose:** Immutable audit log for every state change. Traceability (Core Principle 2) enforcement.

**Every audit entry captures:**
- id
- when (timestamp)
- actor (userId, activeRole at time)
- action (semantic — 'BOM state → results', 'Request → QUEUED_CRITICAL', 'part/create in PartsBox')
- entity (id, type)
- before, after (state snapshots)
- context (optional: reason, source object, related IDs)

**Immutable:** No update, no delete. Once written, permanent.

**Query interface:**
- By entity (all events for BOM-42)
- By actor (all events by Aaron)
- By date range
- By action type
- By force-waive filter (feeds the Force-Waivers log)

**Storage:** Append-only table with partitioning by month for scale. Retention policy Admin-configurable within bounds (minimum 12 months for compliance).

---

### 2.6 Auth

**Purpose:** User session for humans + API keys for external services.

**Human auth:** Session-based. Login → session token → per-request middleware verifies role and capabilities. Multi-role users see role switcher; active role determines capability set.

**External API keys:**
- PartsBox — API key stored in secure config (never displayed in UI, redacted in logs)
- Mouser — separate Search and Cart/Order API keys (two integrations, per Mouser's documentation)
- DigiKey — OAuth 2.0 client credentials flow; refresh token managed by auth layer
- Microsoft Graph — OAuth 2.0 for OneDrive access

**Key rotation:** Admin can rotate API keys via Configuration → Suppliers tab. Rotation writes an audit event and immediately invalidates the old key.

**Token expiration handling:** DigiKey OAuth token expiration produces an ADMIN notification (Refresh inline action). Batch flushes waiting on DigiKey queue behind the refresh.

---

## 3. Frontend architecture

### 3.1 SPA structure

- **Shell** (`shell.jsx`) — role switcher, sidebar, top rail, notification panel. Fixed chrome.
- **Router** (`nav.jsx`, `app.jsx`) — hash routing, breadcrumbs, route→screen dispatch. NAV_BY_ROLE + NAV_SHARED drive sidebar rendering; ROUTE_TABLE drives dispatch.
- **Store** (`store.jsx`) — client-side state, actions, notification emission, comment/audit dispatch. Uses `useStore(selector)` pattern.
- **Screens** — per-route surfaces. One JSX file per screen or family.
- **Cross-cutting components** (`ui.jsx`) — reusable UI primitives.
- **Domain-specific components** — `needs_attention.jsx` (dashboard cards), `inline_part_verify.jsx` (retired for Push-Back, kept for other contexts), `search.jsx` (contextual overlay).

### 3.2 State management

**Client-side state layers:**

1. **Global state** — user, activeRole, notifications, current PartsBox cache subset (loaded on session). Managed by store.
2. **Per-list state** (`useListState(key, defaults)`) — filters, sort, scroll position, search terms per list surface. Persisted to sessionStorage.
3. **Per-screen state** — transient UI state (which sub-card is expanded, which flagged line has focus). Component-local.
4. **Cache-aware state** — hydrated from Cache Layer via API; automatically refetches on cache invalidation events.

### 3.3 Backend communication

- REST-style for typical CRUD (POST /programs, GET /projects/:id, PATCH /boms/:id/state)
- Server-Sent Events or WebSocket for live-update flows (batch flush progress, sourcing progress, receiving flow status)
- File uploads for BOM CSVs (multipart/form-data)

### 3.4 Frontend prototype status

Current state (`AutoBoM.zip`) is a static frontend prototype with mocked-in-memory store. Frontend files simulate what backend calls WOULD return. Claude Code's job is to replace mocks with real backend calls while preserving the UI contract.

Prototype files that need real backend wiring:
- `store.jsx` action bodies (currently mutate local state; will POST/PATCH to backend)
- `data.jsx` seed (currently the "database"; will become fetch calls on session boot)
- `search.jsx` result source (currently static CATALOG; will call Cache Layer / Sourcing Engine)
- `screen_embedded.jsx` bucket display (currently reads local state; will subscribe to bucket state updates)

---

## 4. Communication patterns

### 4.1 Frontend ↔ Backend

- **Query:** `fetch('/api/...')` → JSON response → hydrate into store
- **Command:** `fetch('/api/...', {method: 'POST' | 'PATCH'})` → apply to backend → response updates local store → optimistic UI with rollback on failure
- **Long-running:** `POST` returns a job id → subscribe via SSE/WebSocket → UI shows inline progress

### 4.2 Backend service ↔ service

- **Synchronous** — most calls are in-process function calls (single Node process or monolith initially, decomposable to microservices later)
- **Asynchronous** — long-running operations use in-process job queue with persistence (survives restart). Batch flush is a job. Sourcing runs are jobs. Receiving scan is synchronous (fast).
- **Event bus** — for cross-service invariants (audit writes, notification generation, cache invalidation). Publish-subscribe pattern within backend.

### 4.3 Backend ↔ external APIs

- **PartsBox** — REST with API key header. Cache Layer wraps read calls; write calls bypass cache and invalidate.
- **Mouser** — REST with API key. Cache Layer wraps read (Search) calls; Cart calls are transactional.
- **DigiKey** — REST with OAuth Bearer. Cache Layer wraps Product Information calls; MyLists calls are transactional.
- **Microsoft Graph** — REST with OAuth Bearer. OneDrive Excel workbook API for writing rows to Josh's sheet.

**Cross-wiring rule:** Backend services call ONE external API domain per operation. Receiving flow calls PartsBox; it does not call Mouser/DigiKey for barcode validation. Sourcing calls Mouser/DigiKey; it does not call PartsBox for catalog. Configuration writes call ConfigurationService; not directly external.

---

## 5. Two engines, two responsibilities

The Decision Engine + Sourcing Engine split is a load-bearing architectural decision. Both need to exist independently.

### 5.1 Why they're separate

- **Different concerns:** Decision Engine reasons about workflow rules and human intent. Sourcing Engine reasons about supplier catalog reality.
- **Different testability:** Decision Engine tests are rule-scenarios (given this BOM state + this event, produce this action). Sourcing Engine tests are integration tests (given this MPN, Mouser/DigiKey returns X).
- **Different failure modes:** Decision Engine failure = wrong routing or wrong gating (correctness bug). Sourcing Engine failure = supplier API down (external dependency issue).
- **Different Admin observability:** Decision traces show WHY the engine decided what it did. Sourcing engine metrics show API health, response times, cache hit rates.

### 5.2 Data flow between engines

```
Frontend calls a workflow surface (e.g., Send Push-Back to Designer)
    ↓
Backend controller invokes Decision Engine:
    decide({event: 'PUSH_BACK_SUBMITTED', bom, reason, urgency})
    ↓
Decision Engine may need supplier context:
    "Is MPN X still available at any supplier?"
    → calls Sourcing Engine.validateMpn(X)
    ↓
Sourcing Engine calls external APIs (via Cache Layer)
    Returns to Decision Engine
    ↓
Decision Engine produces: { action, sideEffects, notifications, trace }
    ↓
Controller applies side effects via Domain Services (BOMService updates state, PushBackService creates object)
    ↓
NotificationService delivers to target roles
    ↓
Response to frontend: success + updated state
```

### 5.3 What lives where — quick reference

| Decision | Which engine |
|---|---|
| Which Designer receives a Push-Back | Decision Engine (uses ProgramService for owner) |
| Whether a Build can Run | Decision Engine |
| What CPN a Request line gets | Decision Engine (dispatches to CPNIssuanceService for format-versioned generation) |
| Which supplier has a given MPN in stock | Sourcing Engine |
| What characteristics a part has | Sourcing Engine (from supplier response) |
| Whether PartsBox has the part at all | Sourcing Engine (via `validateMpn`) |
| Which case (A-E) a receiving scan is | Decision Engine (with scan result from PartsBox scan) |
| Whether a bucket timer has expired | Decision Engine (scheduler) |
| The URL of a built cart | Sourcing Engine |
| Whether to attach a datasheet | Decision Engine (per user-action trigger); Sourcing Engine fetches URL |

---

## 6. Storage architecture

### 6.1 AutoBOM primary database

Owns:
- Programs, Projects, BOMs, Builds, Collections
- Requests, Batches, CPN Issuance records
- Push-Backs (with structured fields)
- Storage location metadata annotations (tags, ownership, autobom-managed flag — NOT the physical storage state which lives in PartsBox)
- Users, sessions, roles
- Configuration (Bounded Admin values)
- Audit log (append-only)
- Force-Waivers log (view over audit log filtered to force-waive events)
- Notification records

Schema highlights:
- Nullable `program_id` on Project (FK to Program)
- `cpn_issuance` table with format version per record
- `bom.pushback` structured column (JSON) — reason, urgency, flaggedLines, comments
- `build.overlay` structured column (JSON) — per-line overlay states
- `batch.state` machine + `batch.cartUrls` (JSON per supplier)

### 6.2 PartsBox as external source of truth

Owns:
- Physical inventory state (part existence, stock levels per location)
- Storage location physical structure (name, description, tag)
- Part attachments (datasheets, images)
- Scan-parsing (native barcode handling)
- Build records with QR (via ID Anything™ endpoint)

AutoBOM's database does NOT duplicate these. AutoBOM stores metadata ABOUT PartsBox objects (annotations, our-side workflow state), but the physical inventory state is fetched via API with cache-with-TTL.

### 6.3 Microsoft OneDrive as external write target

Owns:
- Josh's Daily Purchasing List (Excel workbook)

AutoBOM only writes (Section 4 of Data Flow doc). Never reads. Sheet-write is one-way.

### 6.4 Data ownership map — summary

| Data | Owner |
|---|---|
| Program metadata | AutoBOM DB |
| Project metadata | AutoBOM DB |
| Master BOM structure | AutoBOM DB (with mirror in PartsBox for `build/create` consumption) |
| Build overlay state | AutoBOM DB |
| Physical stock levels | PartsBox (via API) |
| Storage location names + descriptions | PartsBox (AutoBOM adds annotations only) |
| Datasheets | PartsBox (via `part/attachments`) |
| QR codes for Builds | PartsBox (via ID Anything™) |
| Catalog details (specs, price, alternatives) | Mouser + DigiKey (fetched on demand, cached) |
| Cart contents + URLs | Mouser + DigiKey (built via APIs, URLs stored in AutoBOM's Batch) |
| Josh's Daily Purchasing List rows | OneDrive (written by AutoBOM at flush; not read back) |
| CPN issuance records | AutoBOM DB |
| Bucket state and batch state | AutoBOM DB |
| Push-Back objects | AutoBOM DB |
| Notifications + Audit log + Force-Waivers | AutoBOM DB |
| User sessions + role assignments | AutoBOM DB |

---

## 7. Deployment model

### 7.1 Current phase — internal deployment

- Monolithic Node.js backend (or similar) deployable to internal server
- SPA served from same origin
- PostgreSQL or similar for AutoBOM primary DB
- External APIs called with per-service credentials from server config

### 7.2 Scalability provisions

Architecture prepared for future decomposition without rewrite:

- Decision Engine + Sourcing Engine are separable — each has a clean interface, no shared state
- Domain Services are per-object type — each could become a microservice
- Cache Layer is separable (Redis-backed already viable)
- Audit Layer is append-only — easy to shard by time
- External API clients (PartsBox, Mouser, DigiKey, Graph) are already well-isolated

### 7.3 Future evolution paths

- **Cloud deployment** — deploy as containers; add HTTPS gateway, secrets manager (Vault/AWS SM), managed DB
- **Multiple concurrent Users** — session-based auth already supports this; scale horizontally
- **Additional suppliers beyond Mouser/DigiKey** — Sourcing Engine already abstracts supplier clients; add Newark client as a new module
- **ERP integration** — Domain Services expose event bus; ERP consumer subscribes to relevant events
- **Mobile access** — SPA already supports responsive; extend for mobile-first read-only surfaces
- **Analytics** — Audit Log is the source; Analytics service reads audit events

---

## 8. Non-goals of this architecture

For explicitness — what AutoBOM's architecture is NOT trying to be:

- **Not a monolithic ERP.** Domain scope is intentionally narrow: engineering + production + purchasing + inventory. Finance, HR, CRM are out of scope.
- **Not a supplier catalog.** Mouser and DigiKey own catalog. AutoBOM queries them; does not maintain its own catalog.
- **Not an inventory management app.** PartsBox does that. AutoBOM orchestrates.
- **Not a workflow builder or configurable BPM.** Workflow rules live in Decision Engine as first-class code. Admin CAN configure specific parameters (timers, TTL, format strings) but cannot redesign workflows via UI.
- **Not a real-time collaboration platform.** Comments are async; no live cursor / co-editing.
- **Not a document management system.** Datasheets attach to PartsBox parts; general document storage is out of scope.

---

## 9. Where each tenet enforcement lives

Map tenets to concrete architectural surfaces:

| Tenet | Where enforced |
|---|---|
| **Bounded Admin Authority** | ConfigurationService (validation), UserService (role assignment guardrails), Decision Engine (force-waive requires reason), AuditService (destructive → audit), Force-Waivers log |
| **No autonomous purchases** | Sourcing Engine only implements cart-building operations; order-submission endpoints are NOT wired to any external API client. Code-level absence of order.submit(). |
| **API leverage principle** | Sourcing Engine → supplier APIs. PartsBox client → PartsBox API. Decision Engine → own logic. No cross-wiring at architecture level. |
| **Human approval** | Decision Engine gating rules (Run Build blocked by unresolved Push-Backs). Frontend "attach replacement" requires user click. No auto-close Push-Back. |
| **Nothing is isolated** | Cross-service event bus for state changes. Every service that emits change publishes it. Consumers subscribe. Ripple effects traceable via event log + audit. |
