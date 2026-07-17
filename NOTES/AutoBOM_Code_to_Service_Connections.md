# AutoBOM Code-to-Service Connections (v1.5.1)

**Purpose:** How the frontend prototype code maps to backend services and external APIs. Which files need real backend wiring, which are pure UI state, and where the integration surfaces live.

**Companion documents:**
- `AutoBOM_Data_Flow_and_Sequencing.md` — data movement
- `AutoBOM_Platform_Architecture.md` — service topology
- `AutoBOM_API_Responsibility_Map.md` — external API detail

**Audience:** Claude Code (primary — integration handoff).

**Reference frontend:** The prototype in `AutoBoM.zip` (as of Coordination Notes 1 + 2 landing). Not every file listed here exists yet — some will after Note 1 (Housekeeping) and Note 2 (Forward Layer) execute.

---

## 1. Frontend files — role and integration status

Each frontend file below is categorized by its **integration status**:
- 🟢 **Pure UI** — no backend integration; state is derived, decorative, or session-local
- 🟡 **Local state, needs wiring** — currently mocks the backend; Claude Code replaces mock with real API calls
- 🔴 **Integration surface** — significant new backend integration required

### 1.1 App shell and routing

| File | Status | Backend/API touchpoints |
|---|---|---|
| `app.jsx` | 🟡 | Auth session, active user, active role, notification subscription. Replace in-memory user with `/api/session` fetch. |
| `shell.jsx` | 🟡 | Notification badge count from real notification subscription. Role switcher persists active role via `/api/session/role`. |
| `nav.jsx` | 🟢 | Pure routing table. No backend touch. |
| `permissions.jsx` | 🟡 | Currently client-side capability list. Backend validates every action anyway; frontend permissions are for UI enablement only. Backend NEVER trusts client-side permissions. |

### 1.2 State store

| File | Status | Backend/API touchpoints |
|---|---|---|
| `store.jsx` | 🔴 | Currently mutates in-memory state directly. Every action becomes a backend call. See Section 3 for action-by-action mapping. |
| `data.jsx` | 🟡 | Seed data. Replaced by fetch-on-session-boot: `/api/programs`, `/api/projects`, `/api/boms`, etc. Seeds move into DB migrations. |

### 1.3 Domain services (surface files)

| File | Status | Backend/API touchpoints |
|---|---|---|
| `screen_dashboard.jsx` | 🟡 | Needs Attention items fetched from `/api/needs-attention?role={activeRole}`. Real-time updates via SSE/websocket. Includes the new "Replacements recommended" card on Production. |
| `needs_attention.jsx` | 🟡 | Card derivation logic stays client-side; data source is backend Needs Attention endpoint. |
| `screen_collections.jsx` + `screen_collection_detail.jsx` | 🟡 | CRUD via `/api/collections`. Add Part drawer calls Sourcing Engine. |
| `screen_admin.jsx` (post-restructure) | 🔴 | User CRUD, Configuration CRUD (with dry-run), Force-Waivers log, Audit Log — all backed by real services. Also per-Program `notifyOnEquivalentSwap` toggle. |
| `screen_embedded.jsx` (Purchasing + Inventory) | 🔴 | Purchasing part reads bucket state via `/api/bucket`, archive via `/api/batches`. Inventory part reads via PartsBox proxy endpoints. |
| `screen_production.jsx` + `screen_production_pipeline.jsx` + `screen_production_results.jsx` | 🔴 | BOM lifecycle CRUD. Sourcing invocation. **NEW: inline-edit affordance with characteristic-match check on structural fields.** Model B re-upload button + ceremony. |
| `screen_bom_overview.jsx` | 🟡 | Cross-Project BOM listing. |

### 1.4 Search and characteristic query

| File | Status | Backend/API touchpoints |
|---|---|---|
| `search.jsx` | 🔴 | Currently static CATALOG. Replace with Sourcing Engine `search_available_stock` calls. Include suppliers toggle → routes through same engine with `includeSuppliers: true`. |
| `inline_part_verify.jsx` | 🟢 | Retired for Push-Back resolution. Kept for other contexts (Dev Collection candidate entry — deferred behind flag). No new backend wiring. |
| New: `pushback_replace_line.jsx` (per Coordination Note 2 Action 11) | 🔴 | Unified characteristic search interface for Push-Back resolution. Calls Sourcing Engine `search_suppliers` mode. **Attaches recommendation to pushback.recommendation, does NOT mutate BOM directly.** |
| New: `pushback_add_component.jsx` (Coordination Note 2 Action 11a) | 🔴 | Missing-component branch of Push-Back resolution. Same search UI, but seeded from Production's addedComponentRequest. Attaches recommendation to pushback.recommendation.addedLine. |
| New: `apply_pushback_card.jsx` (Coordination Note 2 Action 13) | 🔴 | Production Dashboard "Replacements recommended" card. Apply action commits recommendations to master BOM. |
| New: `inline_edit_with_match_check.jsx` (Coordination Note 2 Action 19) | 🔴 | Production BOM screen inline-edit affordance. Silent swap on characteristic-match success. Soft flag on mismatch. |
| New: `storage_location_detail.jsx` (per Coordination Note 2 Action 5) | 🔴 | Storage location detail surface. Backed by PartsBox `storage/get` + `storage/parts`. Move parts / Add stock actions. |

### 1.5 Retired files (to delete per Housekeeping Note 1)

| File | Fate |
|---|---|
| `screen_purchasing.jsx` | DELETE. Old standalone Purchasing screen. Absorbed into embedded surface. |
| `MyOrdersScreen` in `app.jsx` | DELETE. Redundant with embedded Purchasing Filtered mode. |

### 1.6 Retired code paths (deprecated in v1.5.1)

| Path | Fate |
|---|---|
| Variant declaration UI in Build creation | DELETE. Build creation directly sets overlay against master. |
| Variant CSV upload handler | DELETE. |
| Different-new component propagation logic | DELETE. Different-new scenarios go through Push-Back with `missing-component` reason. |
| Designer's Push-Back resolution direct-write to BOM | DELETE. Designer writes to pushback.recommendation; Production applies. |

---

## 2. Backend service layer — file/module organization (guidance for Claude Code)

Unchanged from v1.5, with two additions:

- **characteristic-match-service.js** — new. Compares two parts' characteristics against match criteria (package, nominal, tolerance ≥, voltage ≥, temp ≥). Returns match/mismatch with delta. Called by BOMService on inline-edit; called by Sourcing Engine during Push-Back resolution result ranking.

- Existing PushbackService gets a new sub-object (`pushback.recommendation`) with two states: `open` (recommendations being built by Designer) and `sent` (Designer submitted; awaiting Production application).

```
/backend
  /engines
    decision-engine.js       # rule-based orchestration
    sourcing-engine.js       # supplier-facing queries
    characteristic-match-service.js   # NEW: characteristic comparison
  /services
    program-service.js       # Programs CRUD + notifyOnEquivalentSwap toggle
    project-service.js       # Projects CRUD + program_id linkage
    bom-service.js           # Master BOM per Project + Model B re-upload + inline edit
    build-service.js         # Builds with overlay (no variant)
    collection-service.js    # Collections + Collection→Program
    request-service.js       # Requests + bucketState
    bucket-service.js        # bucket streams + timer
    batch-service.js         # batch flush pipeline
    cpn-issuance-service.js  # CPN generation + format versioning
    pushback-service.js      # Push-Back with recommendation sub-object
    storage-location-metadata-service.js
    notification-service.js  # notification generation + delivery
    user-service.js          # User CRUD + role assignment
    configuration-service.js # Bounded Admin config (including characteristic-match rules)
    audit-service.js         # audit log writes/queries
    force-waiver-service.js  # Force-Waivers log
  /clients
    partsbox-client.js
    mouser-client.js
    digikey-client.js
    graph-client.js
  /cache
    cache-layer.js
  /jobs
    batch-flush-job.js
    sourcing-job.js
    datasheet-attach-job.js
    escalation-job.js
    reupload-invalidation-job.js   # NEW: cascade invalidation on Model B re-upload
  /controllers (or routes/)
    programs-controller.js
    projects-controller.js
    boms-controller.js       # Includes reupload ceremony + inline edit
    builds-controller.js     # Includes overlay setting; no variant handler
    collections-controller.js
    requests-controller.js
    bucket-controller.js
    batches-controller.js
    pushback-controller.js   # Includes recommendation, application
    inventory-controller.js
    storage-locations-controller.js
    receiving-controller.js
    admin-controller.js
    session-controller.js
    notifications-controller.js
  /middleware
    auth-middleware.js
    role-permission-middleware.js
    audit-middleware.js
    error-middleware.js
  /db
    /migrations
    /models
```

---

## 3. Store action → backend service mapping

Every action in `store.jsx` (post-Housekeeping cleanup + Coordination Note 2 additions) maps to a backend endpoint.

### 3.1 Existing actions

| Store action | HTTP method + endpoint | Backend service |
|---|---|---|
| `createProgram({name, code, ...})` | POST /api/programs | ProgramService |
| `editProgram(id, patch)` | PATCH /api/programs/:id | ProgramService |
| `archiveProgram(id)` | POST /api/programs/:id/archive | ProgramService |
| `setProgramNotifyOnEquivalentSwap(id, enabled)` | PATCH /api/programs/:id | ProgramService (Admin only) |
| `createProject({name, program_id?, ...})` | POST /api/projects | ProjectService |
| `linkProjectToProgram(projectId, programId)` | PATCH /api/projects/:id | ProjectService |
| `createCollection({name, program_id, ...})` | POST /api/collections | CollectionService |
| `addPartToCollection(collectionId, part)` | POST /api/collections/:id/items | CollectionService |
| `submitCollectionAsRequest(collectionId, {critical, note})` | POST /api/requests | RequestService |
| `uploadBom(projectId, file)` | POST /api/projects/:id/bom (multipart) | BOMService (initial upload) |
| `validateBom(bomId)` | POST /api/boms/:id/validate | BOMService |
| `runBomSourcing(bomId)` | POST /api/boms/:id/source | BOMService |
| `cancelSourcing(bomId)` | POST /api/boms/:id/source/cancel | BOMService |
| `submitBomToPurchasing(bomId)` | POST /api/boms/:id/submit-request | BOMService → RequestService |

### 3.2 NEW / MODIFIED actions in v1.5.1

| Store action | HTTP method + endpoint | Backend service |
|---|---|---|
| `reuploadBom(projectId, file, reason)` | POST /api/projects/:id/bom/reupload (multipart + reason) | BOMService (Model B ceremony — cascades invalidation) |
| `inlineEditBomLine(bomId, lineNo, patch)` | PATCH /api/boms/:id/lines/:lineNo | BOMService (checks: metadata vs structural; if structural + MPN/mfr change, invokes CharacteristicMatchService) |
| `inlineEditWithMatchCheck(bomId, lineNo, newMpn, newMfr)` | POST /api/boms/:id/lines/:lineNo/characteristic-check | BOMService + CharacteristicMatchService (returns match/mismatch + delta) |
| `commitEquivalentSwap(bomId, lineNo, newMpn, newMfr)` | POST /api/boms/:id/lines/:lineNo/commit-equivalent | BOMService (auto-audit, no reason required, FYI notification if applicable) |
| `commitOverride(bomId, lineNo, newMpn, newMfr, reason)` | POST /api/boms/:id/lines/:lineNo/commit-override | BOMService (audit with reason, always-fire notification) |
| `sendPushback(bomId, {reason, urgency, flaggedLines, addedComponentRequest, note})` | POST /api/boms/:id/pushback | PushBackService (renamed from `sendException`; supports missing-component branch) |
| `resolvePushback(pushbackId, recommendations)` | POST /api/pushbacks/:id/recommendations | PushBackService (Designer resolves; produces recommendation object; does NOT mutate BOM) |
| `applyPushbackRecommendation(pushbackId)` | POST /api/pushbacks/:id/apply | PushBackService + BOMService (Production applies; commits recommendation to master BOM; version increments; state transitions) |
| `rejectPushbackRecommendation(pushbackId, {lineNo, reason})` | POST /api/pushbacks/:id/reject | PushBackService (Production rejects specific recommendation; back to Designer) |
| `cancelPushback(pushbackId, reason)` | POST /api/pushbacks/:id/cancel | PushBackService (Production withdraws entire Push-Back; no state change on BOM) |
| `deferPushback(pushbackId, reason)` | POST /api/pushbacks/:id/defer | PushBackService |
| `reassignPushback(pushbackId, newAssignee)` | POST /api/pushbacks/:id/reassign | PushBackService |
| `createBuild(projectId, {name, buildQty, overlayLines})` | POST /api/projects/:id/builds | BuildService (NEW: no `variant` param; overlayLines is the per-line overlay array) |
| `runBuild(buildId)` | POST /api/builds/:id/run | BuildService |
| `flushBucket(stream, {reason})` | POST /api/bucket/flush?stream={critical,main} | BucketService |
| `scanReceiving({barcode})` | POST /api/receiving/scan | Receiving controller |
| `addComment(entityId, body)` | POST /api/comments | Multi-service |
| `markNotificationRead(notifId)` | PATCH /api/notifications/:id/read | NotificationService |
| `adminOverride({action, reason, target})` | POST /api/admin/override | Multi-service dispatch |
| `setConfig(key, value)` | PATCH /api/admin/config | ConfigurationService |
| `setCharacteristicMatchRules(programId?, rules)` | PATCH /api/admin/characteristic-match-rules | ConfigurationService (global or per-Program) |
| `dryRunDecision(scenario)` | POST /api/admin/dry-run | DecisionEngine |
| `setUserRoles(userId, roles)` | PATCH /api/users/:id/roles | UserService |
| `inviteUser({email, roles})` | POST /api/users | UserService |

**Retired actions (from Housekeeping Note 1) — MUST NOT exist in backend:**
- `approveRequest`, `placeOrder`, `createShipment`, `setShipmentStatus`, `setOrderStep`, `_rollupRequest`

**Retired actions (from v1.5.1 revision) — MUST NOT exist in backend:**
- Variant-related action bodies (variant CSV upload endpoint, variant diff endpoint, propagation endpoint)
- Any endpoint that lets Designer write directly to BOM lines outside of pushback.recommendation

---

## 4. Which store slice is backed by which service

Post-Housekeeping + Coordination Note 2 state shape:

```javascript
STATE = {
    // From backend / DB — primary state
    user,                    // /api/session, UserService
    activeRole,              // session state, UserService
    programs,                // /api/programs, ProgramService
    projects,                // /api/projects, ProjectService
    boms,                    // /api/boms, BOMService (each BOM includes pushback with recommendation sub-object)
    builds,                  // /api/builds (nested under Projects), BuildService
    collections,             // /api/collections, CollectionService
    requests,                // /api/requests, RequestService
    batches,                 // /api/batches, BatchService
    pushbacks,               // Attached to BOMs, PushBackService; includes recommendation sub-object
    notifications,           // /api/notifications, NotificationService (with SSE for updates)
    audit,                   // /api/audit (Admin only), AuditService
    forceWaivers,            // /api/admin/force-waivers, ForceWaiverService
    users,                   // /api/users (Admin only), UserService
    config,                  // /api/admin/config, ConfigurationService (includes characteristic-match rules)

    // From backend via PartsBox proxy
    inventory: {
        parts: [],
        storageLocations: [],
        cacheAge: {},
    },

    // Ephemeral / client-side
    comments,                // Fetched per-entity on demand
    // Removed under Housekeeping: orders, shipments, taskResolutions
    // Removed under v1.5.1: variant-related state (never should have been client-side anyway)
};
```

### 4.1 Push-Back object shape (v1.5.1)

```javascript
pushback: {
    id, bomId, projectId,
    by, when, resolvedBy, resolvedWhen, appliedBy, appliedWhen,
    reason,   // enum
    urgency,  // enum
    state,    // 'open' | 'recommendations_sent' | 'applied' | 'deferred' | 'withdrawn' | 'cancelled_by_reupload'
    note,
    flaggedLines: [
        { lineNo, exReason, comments, intendedReplacement? }
    ],
    addedComponentRequest: null OR {
        mpn?, characteristics, description, quantityPerBoard, designator?
    },
    recommendation: null OR {
        state: 'open' | 'sent',    // Designer builds recommendations (open); submits (sent)
        perLine: [
            { lineNo, recommendedMpn, recommendedMfr, source, characteristics }
        ],
        addedLine: null OR {
            mpn, mfr, source, characteristics, quantityPerBoard, suggestedDesignator
        },
        resolutionSummary
    },
    comments: [],
    routing: {
        assignedTo, escalatedAt?, escalatedTo?
    }
}
```

---

## 5. Real-time / live updates

Updated for v1.5.1:

| UI surface | Live update needed | Backend event source |
|---|---|---|
| Dashboard Needs Attention | New Push-Back arrives, new recommendations arrive, notification arrives | NotificationService event bus |
| Purchasing embedded — bucket display | New Request enters bucket, batch flushes | BucketService state changes |
| Purchasing embedded — archive fulfillment pills | Receiving scan updates fulfillment | Receiving controller emits event |
| BOM sourcing progress | Long-running sourcing job progress | SourcingJob emits events |
| Batch flush progress | Long-running flush pipeline | BatchFlushJob emits events |
| Inventory tab | Another user writes to PartsBox via AutoBOM | CacheLayer emits invalidation event |
| **Push-Back recommendation state** | Designer sends recommendations; Production applies | PushBackService state changes |
| **Model B re-upload cascade** | Re-upload cancels Push-Backs / flags bucket entries | ReuploadInvalidationJob emits events |
| **Production inline-edit swap** | Silent match commits ripple to Program-linked Designer | BOMService emits FYI |

Non-live updates use standard REST + client-side polling on user demand.

---

## 6. Cache Layer usage in code

Unchanged from v1.5. Every backend service that reads external data routes through Cache Layer.

---

## 7. Auth handling in code

Unchanged from v1.5.

---

## 8. Configuration values consumed by code

Unchanged from v1.5, with additions:

- `pushback.escalation.window` (integer hours, 1-168)
- `characteristic-match.rules.global` (JSON object with match criteria)
- `characteristic-match.rules.per-program.<program_id>` (per-Program override — Bounded Admin can tune)
- `notify-on-equivalent-swap.default` (boolean, default true; applies to new Programs)

---

## 9. Notification flow through code

Updated for v1.5.1. Same base flow with three new notification types:

- **REPLACEMENTS RECOMMENDED** — targetRole: production, on Push-Back resolution
- **RECOMMENDATIONS APPLIED** — targetRole: designer (resolver), FYI on Production application
- **EQUIVALENT SWAP FYI** — targetRole: designer (Program owner), on Production silent match swap (gated by Program.notifyOnEquivalentSwap)
- **OVERRIDE COMMIT** — targetRole: designer (Program owner), on Production override commit (always)
- **RE-UPLOAD CANCELLATION** — targetRole: designer (Push-Back resolver, if applicable), on Model B ceremony

Each generated via NotificationService.emit() with structured routes + verbs.

---

## 10. What Claude Code should NOT do

Same list as v1.5, plus these v1.5.1 additions:

- ❌ Add a variant CSV upload endpoint. Retired.
- ❌ Add a variant diff endpoint. Retired.
- ❌ Add "different-new" propagation logic. Retired — flows through Push-Back with `missing-component` reason.
- ❌ Add an endpoint that lets Designer write directly to master BOM lines. Designer writes to pushback.recommendation only.
- ❌ Auto-apply Push-Back recommendations. Production must click Apply.
- ❌ Skip the characteristic-match check on inline MPN/manufacturer edits. Always run it.
- ❌ Silently commit an override without audit reason. Reason is mandatory.
- ❌ Skip FYI notification on override commits regardless of Program config. Override always notifies.
- ❌ Hard-block Production on characteristic mismatch. Always soft flag with three options.
- ❌ Silently commit on Model B re-upload with downstream state. Confirmation modal + audit reason mandatory.

---

## 11. Integration handoff checklist for Claude Code

Same as v1.5. When picking up an implementation ticket:

1. **Read `CLAUDE.md`** — operating context.
2. **Read the relevant module package** (Purchasing v4.1, Inventory v3.1, Designer Alignment v1.1.1, Production Alignment v1.1.1) — detailed spec.
3. **Read this file** — code-to-service map.
4. **Check the drift report + coordination notes** — housekeeping and forward-layer targets.
5. **Identify** which files change (frontend + backend).
6. **Identify** which external APIs are touched — cross-reference against API Responsibility Map.
7. **Identify** which cache keys need invalidation on write.
8. **Identify** which notifications need to be generated.
9. **Identify** which audit events need to be written.
10. **Identify** which configuration values are read.
11. Only THEN begin implementation.

---

## 12. Prototype → production migration path

Unchanged from v1.5.

### 12.1 Phase 1 — clean baseline (Coordination Note 1)

Housekeeping. Same as v1.5.

### 12.2 Phase 2 — forward-looking layer (Coordination Note 2, v1.5.1)

- App-wide search PartsBox integration
- Push-Back resolution characteristic search with **Designer-proposes/Production-applies model**
- Push-Back with **`missing-component` reason category** and addedComponentRequest
- Storage location detail
- **Production inline-edit with characteristic-match check + soft flag**

At this phase, Claude Code implements:
- PartsBox client
- Sourcing Engine with `search_available_stock` + `search_suppliers`
- **CharacteristicMatchService**
- Cache Layer
- Frontend integration for the new search surfaces + inline-edit + apply-recommendation flows
- Push-Back service with recommendation sub-object

### 12.3 Phase 3 — full state persistence

Same as v1.5.

### 12.4 Phase 4 — Purchasing pipeline

Same as v1.5.

### 12.5 Phase 5 — Production BOM screen rebuild

- Master BOM per Project + Build overlay model (NO variant declaration — retired)
- Run Build → PartsBox `build/create` + QR delivery
- Receiving flow with Cases A-E
- **Model B re-upload ceremony UI on Production BOM screen** (the affordance itself; the backend already exists from Phase 2)

### 12.6 Phase 6 — Admin surfaces

- Bounded Admin Configuration
- Force-Waivers log
- Decision traces
- Dry-run UI
- **Per-Program `notifyOnEquivalentSwap` toggle**
- **Characteristic-match rules editor (global + per-Program)**

Each phase depends on prior phases. Order matters.
