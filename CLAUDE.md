# AutoBOM — Project Standards (v4)

**Source of truth:** the v1.5.1 baseline plus the four v4 module packages.

- PRD: `docs/v1.5.1/00_Core_Spec/AutoBOM_PRD_v1.5.1.docx`
- Master Design Contract: `docs/v1.5.1/00_Core_Spec/AutoBOM_Claude_Design_Package_v1.5.1.docx`
- Permissions Matrix: `docs/v1.5.1/00_Core_Spec/AutoBOM_Permissions_Matrix_v1.5.docx`
- Module packages: Purchasing **v4.2**, Inventory Activation v3.1, Designer Workspace Alignment v1.1.1, Production Workspace Alignment v1.1.1 — all in `docs/v1.5.1/01_Module_Packages/`. The **Purchasing v4.2** package (`AutoBOM_Purchasing_v4.2_Claude_Design_Package.docx`) is the authoritative full Purchasing spec (supersedes v4 / v4.1); the Purchasing section in this file is its operating summary.
- Deployment plan: `docs/v1.5.1/04_Infrastructure/AutoBOM_Deployment_Readiness.md`
- Supplier API integration guide: `docs/v1.5.1/04_Infrastructure/AutoBOM_Supplier_API_Integration_Guide.md` (DigiKey · Mouser · PartsBox implementation rules — read before touching any supplier client)

**Ordering rule:** the PRD is *integrative* — it wins on cross-workflow, roles, data model, and integration topics. Module packages remain authoritative within their own scope. Earlier v1.1 / v1.3 / v1.4 / v1.5 texts are superseded but kept for history in `docs/archive/` — do NOT treat them as current.

**Main build:** current working prototype lives in `docs/v1.5.1/06_Prototype/` (standalone HTML for viewing, ZIP for editing). Production code will live in `frontend/` (React + Vite) and `backend/` (Python + FastAPI). Existing POC code lives in `poc/`.

---

## Claude Code's mandate — activate the prototype, wire it to real systems

**The prototype in `docs/v1.5.1/06_Prototype/` is the working source of truth for the product.** Every screen, sidebar, dashboard, button, table row, inline action, Push-Back handshake, bucket/flush flow, receiving scan, Build creation, notification, and role view already works as an interactive prototype on mock/seed data. This is what AutoBOM *is*.

**Claude Code's job is to turn that prototype on — not to rebuild or redesign it.** Take the prototype's exact screens, components, workflows, and interactions and connect them to real systems so they go live:

- **Backend + database** — FastAPI + Postgres for real persistence, state, versioning, audit (Programs, Projects, BOMs, Builds, Requests, Push-Backs, CPN issuance, buckets, notifications).
- **Sourcing engine + supplier clients** — the proven `poc/` code (sourcing engine, BOM cleaner, Mouser / DigiKey / PartsBox clients) refactored into `backend/services/`, per the Supplier API Integration Guide.
- **Microsoft Graph** — Daily Purchasing List writes at bucket flush (Purchasing v4.2).
- **Auth** — seed users locally, Azure AD when credentials arrive (graceful fallback).

**"Activate" means:** every interactive element the prototype demonstrates becomes real. Buttons fire real actions; rows load and mutate real records; Push-Backs move real state across Designer ↔ Production; bucket flushes call the real cart APIs and append the real sheet; receiving scans hit PartsBox; Builds call `build/create`; characteristic-match, coverage, and CPN routing run on live data. Replace mock data and stubbed handlers with live integrations.

**Preserve the prototype faithfully.** Port its layout, flows, navigation, and behavior as-is. Do not re-architect the UI, rename flows, restructure screens, or "improve" the UX. Speed and usability over aesthetics — this is an internal tool, and the prototype already encodes the intended workflow. When a wiring decision would change prototype behavior, flag it rather than silently diverging.

**Reuse and expand the POC — never rebuild blindly.** The `poc/` code is a proven proof-of-concept that already works at smaller scale (sourcing engine, BOM cleaner, Mouser / DigiKey / PartsBox clients, cart / list building). It is the reference for *how the real logic behaves*. We are not inventing something new from a blank page — we are **scaling up a thing that already works**: port the POC's functions into `backend/services/`, expand their abilities to full scale, and refactor where necessary to fit the new architecture and connect to the prototype UI.

**The POC is read-only and permanent — do NOT edit it.** Never modify, refactor-in-place, move, or delete anything under `poc/`. It stays exactly as-is, indefinitely, as a living reference you can always open to see what worked and why. All new work happens in `frontend/` and `backend/`; the POC is *copied-from and learned-from*, never changed. The new system is built **on top of / based on** the POC, not by mutating it.

All of this stays inside the operating tenets below (leverage APIs, human approval, no autonomous purchases, trace ripples).

---

## Workspace layout

The repository (`BOM-AUTOMATION/`) is organized as:

```
BOM-AUTOMATION/
├── CLAUDE.md                    # This file — operating context for Claude sessions
├── .env                         # Local development credentials (gitignored)
├── .gitignore
├── .agents/                     # Agent configuration
├── .codex/                      # Codex / agent workspace
├── .venv/                       # Python virtualenv (gitignored)
├── __pycache__/                 # Python bytecode cache (not source)
├── backend/                     # Python + FastAPI backend (Claude Code builds this)
├── frontend/                    # React + Vite frontend (Claude Code builds this)
├── poc/                         # Proven Python POC — READ-ONLY reference, never edited; port from it
├── output/                      # Runtime outputs (not source)
└── docs/
    ├── README.md                # Index of all documentation
    ├── archive/                 # Historical versions (v1.0 - v1.4). Not current.
    ├── decisions/               # Architecture decision records
    ├── reference/               # External reference docs
    └── v1.5.1/                  # Current baseline. Everything here is authoritative.
        ├── 00_Core_Spec/        # PRD, Permissions Matrix, Master Design Contract
        ├── 01_Module_Packages/  # Purchasing v4.2, Inventory Activation, Designer, Production
        ├── 02_Architecture/     # Platform arch, data flow, API map, code-to-service
        ├── 03_Coordination_Notes/  # Notes 1-4 + Note 4 Rollback
        ├── 04_Infrastructure/   # Deployment + supplier API rules
        │   ├── AutoBOM_Deployment_Readiness.md
        │   ├── AutoBOM_Supplier_API_Integration_Guide.md / .docx
        │   └── partsbox api rules.pdf   # (corrupted export — re-export needed)
        ├── 05_Reference/        # AutoBOM_Product_Discovery_Report.md
        └── 06_Prototype/        # Standalone HTML + working ZIP
```

**Superseded documents:**
- `AutoBOM_Azure_Requirements_Checklist.md` (in `04_Infrastructure/`) — replaced by `AutoBOM_Deployment_Readiness.md`. Move to `docs/archive/` when convenient.

---

## Operating tenets (non-negotiable, apply to every decision)

These take precedence over any specific spec detail. If a spec detail conflicts with a tenet, the tenet wins and Claude Architect gets flagged.

### Bounded Admin Authority
Admin has broad configurability, but every surface is bounded by input validation, type constraints, and blast-radius limits. No single Admin action can produce invalid state or catastrophically break the platform. Destructive actions require confirmation and audit reason (≥10 chars). Configurability is real — CPN format is free-form within grammar validation, cache TTL is integer seconds within a validated range, bucket timers are integer minutes within a validated range — but the system is safe against Admin error, Admin turnover, and adversarial Admin. Admin also has runtime observability: dry-run mode against real inputs (no side effects) and structured decision traces on every decision engine invocation.

### No autonomous purchases
AutoBOM does **not** execute financial transactions against any supplier API. In scope: cart building, retrieving pricing, populating purchasing lists, generating purchasing packages. **Out of scope: placing orders, submitting carts programmatically, moving money.** Every purchasing action ends at a human clicking "Place Order" in an external system — currently Josh reviewing the Daily Purchasing List and executing orders in Mouser/DigiKey's own UI. Cart-building APIs are called; order-submission APIs are never called.

### API leverage principle
AutoBOM orchestrates; APIs do the domain-heavy work. Each API is called for questions *inside its domain*:
- **PartsBox** — inventory, storage locations, part attachments (including datasheets), builds, scanning.
- **Mouser + DigiKey** — catalog search, parametric filters, pricing, cart-building.
- **OneDrive / Microsoft Graph** — Josh's Daily Purchasing List writes.
- **AutoBOM's own database** — cross-workflow state that no single API knows about (buckets, CPNs, Push-Backs, Programs, workflow routing rules).

**Do not cross-wire APIs to answer questions their system doesn't own.** DigiKey's Barcode Search does *not* validate a receiving scan (PartsBox does); Mouser's search does *not* look up a part in your inventory (PartsBox does). This is the single most common architecture mistake and it's out of bounds.

### Human approval
Automation assists decisions; automation does not replace responsibility. Critical actions require human review. Recommended replacements are shown, not applied. Sourcing decisions require Designer or Production sign-off. **When Designer resolves a Push-Back, the resolution is a *recommendation* — Production is the one who applies it to the master BOM.** The system does not silently mutate the master BOM based on Designer's picks alone.

### Nothing is an isolated system
Every architectural decision intertwines with others. When Claude Design lands one change, they check the ripples: Does this touch Push-Back arrival? Does it touch the CPN issuance table? Does it change what Josh sees on the sheet? Cross-boundary effects must be traced explicitly. Isolated fixes that ignore ripples become sources of drift.

---

## Supplier & Inventory API integration rules (DigiKey · Mouser · PartsBox)

**Authoritative implementation reference:** `docs/v1.5.1/04_Infrastructure/AutoBOM_Supplier_API_Integration_Guide.md` (`.docx` mirror alongside it). Claude Code MUST read that guide before writing or modifying any supplier-client code (`backend/services/digikey_client.py`, `mouser_client.py`, `mouser_cart_client.py`, `partsbox_client.py`, and the POC equivalents in `poc/`). The rules below are the non-negotiable summary; the guide holds exact request/response envelopes, headers, error codes, and Python examples.

This section sits **under** the Operating tenets above — nothing here overrides *No autonomous purchases*, *API leverage principle*, or *Human approval*. It makes those tenets concrete at the HTTP layer.

### Credentials (from `.env` — never hardcode, never log)
`DIGIKEY_CLIENT_ID`, `DIGIKEY_CLIENT_SECRET`, `MOUSER_API_KEY`, `PARTSBOX_API_KEY`. Empty/placeholder values follow the deployment doc's graceful-fallback pattern. Mask secrets to last 4 chars in any log line.

### DigiKey — OAuth 2.0 (Product Information V4 is the sourcing API)
- **2-legged (client credentials)** for automated sourcing; 3-legged only when acting for a specific signed-in DigiKey user. Access token lives **10 minutes** — cache it, refresh proactively (~9 min) or reactively on a `401`. Never fetch a token per call.
- Every V4 call needs **all** of: `Authorization: Bearer {token}`, `X-DIGIKEY-Client-Id`, and the three locale headers `X-DIGIKEY-Locale-Site` / `-Language` / `-Currency`, plus `Content-Type`/`Accept: application/json`. Omitting the locale headers is a top cause of silent `400`s.
- Base path `{host}/products/v4`. Keyword search `POST /products/v4/search/keyword` (Limit ≤ 50, page with Offset); single MPN → `GET /products/v4/search/{urlencoded_pn}/productdetails`. Pricing/qty live under `ProductVariations[]`, keyed by `DigiKeyProductNumber` — one MPN can have several variations (Cut Tape / T&R / DigiReel).
- Limits: Product Information **120/min, 1000/day**. Read `X-RateLimit-*` headers and back off on `429`.

### Mouser — API key in the query string (no OAuth)
- Key is passed as `?apiKey={key}`, **never** a header. Search and Order use **separate keys** in principle; the current POC `.env` uses a single `MOUSER_API_KEY` — confirm before wiring the Order API.
- **Every request body is wrapped in a named root object** (`{"SearchByKeywordRequest": {…}}`, `{"SearchByPartRequest": {…}}`, `{"Order": {…}}`, etc.). Sending the inner object alone errors. Responses wrap in `{ "Errors": [...], "SearchResults": {...} }` — **check `Errors` first**; a `200` with non-empty `Errors` is a failure.
- Batch up to **10 part numbers** per `search/partnumber` call, pipe-separated (`|`), 3–40 chars each. Enums: `searchOptions` = None|Rohs|InStock|RohsAndInStock; `partSearchOptions` = None|Exact.
- Cart building is allowed (Cart API); **`Order.SubmitOrder` stays `false`** so the call returns a preview only. `true` places a real order and is out of scope (see gate below).
- ~**1000 calls/day** ceiling — cache aggressively via `supplier_lookup_cache.py`.

### PartsBox — inventory source of truth (see "Inventory and Receiving via PartsBox")
- AutoBOM orchestrates; PartsBox owns inventory, storage, scanning, builds, and attachments. Use `stock/add` for receiving, `part/attachments` (`attachment/type = "datasheet"`) for datasheet lifecycle, `build/create` for consumption, and the **ID Anything™ QR image endpoint** for build QR delivery — do not build a QR generator in AutoBOM.
- **Do not cross-wire APIs** (API leverage principle): PartsBox validates receiving scans; Mouser/DigiKey do catalog + cart only. Distributor barcode APIs are **not** called during receiving.
- Exact PartsBox auth/endpoint/body formats: see `docs/v1.5.1/04_Infrastructure/partsbox api rules.pdf`. ⚠️ **The committed PDF is corrupted** (truncated tiled-image export, no text layer, no trailer — unreadable). Re-export a clean copy (prefer a text-based PDF or Markdown) before relying on it; until then, PartsBox usage rules in this file plus the POC `partsbox_client.py` are the working reference.

### Cross-cutting (both distributors)
- **Retry** only `429`/`5xx`/timeouts with exponential backoff (honor `X-RateLimit-Reset`); on `401` refresh the DigiKey token once then retry; never blind-retry `400`/`404`.
- **Cache** part lookups keyed by `(supplier, part_number, options)` with sensible TTL — the single biggest lever for staying under the ~1000/day caps and keeping the platform fast.
- **Normalize** DigiKey and Mouser fields into one internal schema (mapping table in the guide, §6.7) so the rest of AutoBOM stays supplier-agnostic. Casing trap: datasheet URL is `DatasheetUrl` on DigiKey V4 vs `DataSheetUrl` on Mouser.
- **Traceability:** log supplier, endpoint, status, rate-limit-remaining, and latency for every outbound call so any sourced price traces back to its source call.

### Human-approval gate (reinforces *No autonomous purchases*)
Automation may source, compare, recommend, build carts, and generate order **previews/packages**. Automation MUST NOT submit an order, approve a purchase, or move money. Concretely: keep Mouser `SubmitOrder=false`; do not call DigiKey Ordering submit; every purchasing action ends at a human clicking "Place Order" in the distributor's own UI (Josh on the Daily Purchasing List). Order-submission APIs are never called.

---

## v4 role model — three login roles

**Active login roles: Designer · Production · Admin.**

- **Designer** (engineering intent) — creates Programs, curates Collections, resolves Push-Backs by *proposing* replacements Production applies.
- **Production** (sourcing readiness + assembly) — owns Projects, uploads master BOM, runs Builds, does Receiving. Applies Designer's Push-Back recommendations to the master BOM. Can inline-edit master BOM for equivalent-part swaps with characteristic-match check (see below).
- **Admin** (system config + oversight) — Bounded Admin Authority per tenet above.

**Purchasing is NOT a login role.** It is an *embedded surface* inside Designer and Production workspaces (and Admin, with Full-mode default). Reached via a sidebar item labelled "Purchasing" that opens the same embedded view.

**Inventory is NOT a login role.** It is an embedded surface (same pattern as Purchasing).

**Development role is deferred.** Fully removed from active MVP surfaces. Behind `DEV_ROLE_ENABLED = false` in `permissions.jsx`. Reactivation is a one-line flip.

**"purchasing" and "development" strings should not appear in `ALL_ROLES` arrays** used to render UI. Those arrays are Designer, Production, Admin.

---

## Workspace sidebars (v4, from Chapter B)

### Designer
- Dashboard
- Programs
- Collections
- Purchasing (embedded, Filtered default)
- Inventory (embedded)
- Notifications (shared / general)

**Removed from Designer:** Projects (Projects are Production's), My Orders.

Designer needs a **Create Program flow** with sigil validation on Program code.

### Production
- Dashboard
- BOMs
- Projects
- Purchasing (embedded, Filtered default)
- Inventory (embedded)
- Notifications (shared / general)

**BOMs and Builds are nested inside Project detail.** A Project detail page shows the master BOM at the top, Builds history below, coverage indicators, "Run Build" primary action, Push-Back state.

**Receiving is NOT a top-level nav item.** Reached from within embedded Inventory via "Start receiving" primary action.

### Admin
- Dashboard
- Configuration (tabbed to workflow, suppliers, system settings, decision traces)
- Programs
- Users
- Purchasing (embedded, Full default)
- Inventory (embedded)
- Force-Waivers log
- Audit Log

---

## Data model — Program → Project → BOM → Builds

- **Program** — top-level R&D/product organization. Owned by Designer. Fields: id, name, code, owner, status (Active/Paused/Complete/Archived), description, customer, dates, tags. Contains zero or more Collections (Designer's) and zero or more Projects (soft downward reference; read-only cards linking out to Production's Project detail).
- **Project** — a specific PCB being assembled. Owned by Production. Has nullable `program_id` FK. Structure ≠ control — Production has full operational control regardless of Program link. Designer NEVER edits, tracks, or works Projects.
- **Master BOM** — **exactly one master BOM per Project.** Versioned at Project level. **PartsBox sees exactly one BOM per Project.** Master BOM cannot be forked into multiple BOMs under the same PartsBox project. Structural changes to the master flow through Push-Back resolution (Designer proposes, Production applies) or Production inline-edit for characteristic-matched equivalents. Full-file re-upload is allowed under Model B ceremony (see below).
- **Build** — physical assembly of the PCB. A Project has many Builds over time. Each Build references the master BOM with per-line overlay:
  - `used` — line populated normally → PartsBox consumes from project box on `build/create`
  - `skipped` — line omitted for this Build → no PartsBox consumption
  - `deferred` — line not populated this Build pass, intent to add later via rework → no PartsBox consumption now; future rework fires its own consumption
  - `rework` — line populated with a different component (realtime substitution or post-hoc swap) → PartsBox consumes the actual substitute, NOT the master's stated component

The `rework` state carries: substitute component (MPN, manufacturer, quantity), `rework_type` (`realtime` / `post_hoc`), optional Development wall ticket ID, actor, timestamp, note.

**Rework state is per-Build, not master-BOM.** It's Production recording what actually happened on THIS assembly, not the master changing.

**QR delivery on Build result:** After `build/create` succeeds, AutoBOM calls PartsBox ID Anything™ QR image endpoint and renders inline. Fallback: "Open Build in PartsBox" link. Do not build a QR generator in AutoBOM.

### Master BOM immutability + three change paths (locked)

The master BOM's *structure* (which parts are on the board, MPN + manufacturer + quantity + designator) is not casually mutable after upload. There are only three paths to change it:

**Path 1 — Production inline-edit with characteristic-match check (Option 2).** Production can edit any line's MPN or manufacturer. The platform runs a characteristic-match check against the original:
- **Match** — silent swap. Master BOM version increments. Auto-recorded audit entry: "characteristic-match equivalent swap" with the delta. No manual reason required (low-stakes). Designer FYI notification fires on Program-linked Projects (Admin-configurable per Program).
- **Mismatch on any critical characteristic** — Production sees soft flag: "This differs from the original in [X, Y]. Send to Designer, or continue as override?" If "Send to Designer" → auto-generates a Push-Back with the flagged line + Production's intended replacement as context. If "Continue as override" → requires manual audit reason, master BOM version increments, Designer notified via FYI.

Characteristics that must match for silent swap:
- Package / footprint (physical fit)
- Nominal value (capacitance, resistance, voltage rating — primary spec)
- Tolerance (equal or tighter is fine; wider triggers flag)
- Voltage rating (equal or higher is fine)
- Temperature range (equal or wider is fine)

Non-structural metadata (line notes, description, designator text) is freely editable inline by Production without characteristic check.

**Path 2 — Push-Back to Designer.** When Production can't resolve (needs engineering judgment on a truly different part, or needs to add a component the master doesn't have), Push-Back to Designer. Designer resolves via unified characteristic search, picks a replacement or new component, sends back as a *recommendation*. Production sees the recommendation on their Dashboard, clicks Apply, master BOM version increments. **Designer never edits the master directly** — the resolution surface produces a recommendation object; Production is the one who commits it to the master.

**Path 3 — Model B re-upload (ceremonial, for mistake recovery).** Full-file re-upload is always allowed at any BOM state, BUT once the BOM has been touched downstream, re-upload becomes a ceremonial action:
- Confirmation modal enumerates what will be invalidated (open Push-Backs, in-flight sourcing runs, uncommitted Builds, Requests in the bucket)
- Mandatory audit reason (≥10 chars)
- Master BOM version increments
- Notifications fire to affected parties:
  - Designer notified if there was an open Push-Back → Push-Back cancelled with reason
  - Purchasing (embedded surface) flagged if Request was in the bucket → bucket entry flagged for review
  - Production notified if a Build was in draft → Build coverage recomputes against new master
- Audit entry with before/after state

**Retired:** Variant declaration diff-and-propagate. Different-new propagation. Variant CSV upload. Manual variant click-through as a separate flow from Build creation.

---

## CPN (Component Part Number)

CPNs use a **continuous-identifier chain**, NOT sigils. Any sigil format
(#project-bound / ~wall-bound, e.g. #TVCA-B052-001 / ~A-3-7-001) is RETIRED
per Coordination Note 3 and must not appear anywhere in code, seed data, or UI.

### Format
The CPN is a continuous identifier derived by walking the succession chain:

    Program.identifier → Project.identifier → BOM line sequence

Example: `TVCA-R2-042`
  - `TVCA`  — Program identifier
  - `R2`    — Project identifier
  - `042`   — line sequence, incrementing onto the end as parts are added

The next part appends the next number in the chain (…-042 → …-043). This mirrors
the prototype's `cpnFor` derivation in data.jsx.

### Scope
Scope (project-bound vs wall-bound) is NOT encoded as a sigil in the string.
It is surfaced separately via `cpnScope()` and rendered in the UI as
**Project / Wall pills**. The CPN string itself carries no scope character.

### Configurability
The format is configurable, not hard-coded. It is stored as `cpn_format` in the
`configuration` table (Bounded-Admin value). Changing the naming nomenclature is a
config update — NOT a code change or system rehaul. The `cpn_issuance` table is
format-agnostic: it stores the resulting string + `format_version` + `scope`, so
history remains valid across format changes.

### Generation (single source of truth)
CPN generation is ONE service, in ONE place (Phase 4). It walks the chain,
increments, and applies the configurable `cpn_format`. No other component ever
constructs, increments, or formats a CPN. In particular, supplier cart/list writers
(Mouser `CustomerPartNumber`, DigiKey MyLists `CustomerReference`) are pure
passthroughs — they receive an already-generated CPN string and place it in the
supplier field, nothing more.

### Program-code validation
Program codes are validated as continuous-identifier segments (alphanumeric chain
components), NOT against any sigil scheme. Remove any "sigil validation on Program
code" rule.

---

## Push-Back — cross-boundary structured handshake

A Push-Back is a completed transaction across a boundary: Production submits a problem → Designer resolves with a recommendation → Production applies the recommendation.

### Structure
Every Push-Back carries:
- **Reason category** — enum: `obsolete` / `eol` / `unsourceable` / `zero-stock` / **`missing-component`** / `other`
- **Urgency** — enum: Blocking / Standard
- **Per-flagged-line detail** with own comment sub-thread
- **Overall comment thread**
- **Actor + timestamp** on every state change

**`missing-component`** is the reason when Production discovers they need a part the master BOM doesn't have. The Push-Back doesn't flag an existing line — instead the submission carries the *added component request* (MPN if Production knows it, or characteristics/description if they don't).

### Two entry points, one destination

Push-Backs originate from two triggers, both flowing to the same Designer resolution surface:

1. **Production's judgment.** Production hits a problem line — obsolete, EOL, unsourceable, complex substitution beyond their scope — and sends a structured Push-Back from the BOM screen.
2. **Platform's characteristic-match failure.** Production tries an inline edit; characteristic-match check fails; Production picks "Send to Designer" from the soft flag. Platform auto-generates a Push-Back with Production's intended replacement pre-populated as context.

### Arrival (Designer side)
Push-Backs appear on the Designer Dashboard's **Needs Attention** section as "BOM EXCEPTION" cards. Card shows: BOM name/version/ID, Program → Project breadcrumb, reason/urgency badges, Production's message, part count needing action. Primary action opens the resolution surface **inline on the dashboard** — never leaves the dashboard, never a modal.

### Resolution flow — Designer proposes, Production applies

Designer clicks the primary action → resolution surface expands inline → each flagged line shows a sub-card with a **unified search interface**:
- MPN input field (free-text, smart-matching)
- Manufacturer field as bidirectional-constrained typeahead
- Characteristic filters pre-loaded from the flagged part, refinable
- MPN + characteristic filters AND-combined
- `missing-component` Push-Back: same surface, but starting query is "add from scratch" mode — no source part to compare against, characteristics from Production's description

The unified search runs in **`search_suppliers` mode**. Designer picks a candidate → attaches as **recommendation** (not commit) → the whole batch submits back via **"Send recommendations to Production"** as the batch-primary action.

**The recommendation lands on Production's Dashboard as a "Replacements recommended" Needs Attention card.** Production reviews Designer's picks → clicks Apply → master BOM version increments with the recommended replacements applied. Only at Apply does the master BOM change.

Designer NEVER directly edits the master BOM. The resolution surface produces a recommendation object; Production commits it.

### Routing
**Uniform across Program-linked and standalone Projects.** Production surfaces problems; Designer resolves them with a recommendation. Production does NOT self-resolve engineering-judgment Push-Backs — that's a hard rule.

- **Program-linked Project:** Push-Back routes to Program owner Designer first. If no response within Admin-configurable window (default 24h), escalates to unassigned pool.
- **Standalone Project:** Push-Back routes directly to unassigned pool.

### Run Build is gated
While any Push-Back is unresolved on the parent Project's master BOM, that Project's "Run Build" action is blocked. Admin `force-waive` overrides, with required reason logged to Force-Waivers log.

### Secondary paths on resolution surface
- **Comment** — write to Push-Back overall thread or per-line sub-thread. Optionally notifies Production.
- **Defer** — mark Push-Back as deferred with reason. Persists on Needs Attention.
- **Reassign** — hand to another Designer with note.

---

## Characteristic search — two modes

The sourcing engine exposes two named search modes. Same underlying logic, opposite default polarity, same UI toggle pattern for the inverted overlay.

### `search_available_stock` — PartsBox primary, suppliers overlay
Powers the app-wide search bar. Default result surface has two sections:
- **In inventory** (PartsBox parts + storage locations)
- **Available from suppliers** (Mouser + DigiKey — shown only when "Include suppliers" toggle is on)

### `search_suppliers` — Mouser/DigiKey primary, PartsBox overlay
Powers the Push-Back resolution flow AND the characteristic-match check on Production inline-edit. Default result surface has one section (supplier results). Adds a second section (PartsBox / wall) when "Include wall" toggle is on.

### Rules that apply to both modes
- **Both sections shown, never deduped.**
- **DigiKey Product Information V4 `ParametricFilters`** used natively for characteristic queries.
- **Mouser's parametric filtering is less first-class.** Fall back to keyword-with-spec-hints and client-side filter.
- **Result cards show characteristic comparison** against the source part (matches / differs / improves) when a source exists.

---

## Datasheet lifecycle

- Supplier search results **display datasheet URL inline** when Mouser or DigiKey APIs return one.
- **On user-action** (add to Collection, submit Request, attach as Push-Back recommendation, B2-Guarded creation, Production inline-edit apply): AutoBOM downloads the PDF and attaches to PartsBox via `part/attachments` with `attachment/type = "datasheet"`.
- **Skip if already attached.**
- **Over time PartsBox becomes the persistent source of truth** for datasheets.

---

## Inventory and Receiving via PartsBox

**PartsBox is the source of truth for inventory.** AutoBOM works on top via API.

### Storage kinds
- **Project Boxes** — AutoBOM-created, tagged `production`. One per Project.
- **Development locations (wall bins)** — pre-existing PartsBox infrastructure, tagged `development`. Discovered via development tag. AutoBOM reads structure opaquely.

### Universal read + write for all roles
With confirm-on-destructive prompts. Cache-with-TTL: 60s default, Admin-configurable, refresh-on-write, rate-limited from day one.

### Receiving flow
- User scans distributor barcode/QR
- PartsBox handles scan natively
- AutoBOM cross-references against bucket entries, CPN issuance, sheet batch archive, storage assignments
- PartsBox executes `stock/add`
- AutoBOM updates fulfillment state
- Case B mismatch on wall scans → auto-update PartsBox location with audit reason
- Multi-location wall parts → dropdown with default (highest-stock location)

**Mouser and DigiKey barcode APIs are NOT called during receiving.** PartsBox owns scanning; distributor APIs own catalog+cart-building. Do not cross-wire.

### Wall as exception, not default
Wall parts appear in Designer sourcing ONLY when both suppliers fail. In Production BOM build coverage, "on wall" quantities are informational — they don't drive readiness green/amber/red (which is driven by "in project box" quantities).

### B2-Guarded part creation
- Scanned or referenced MPN doesn't exist in PartsBox: sourcing engine validates against real suppliers.
- Validated → auto-create in PartsBox.
- Not validated → prompt user for local-part / MPN-wrong / handle-in-PartsBox choice.
- Local parts tagged `local-part`, no distributor SKUs.

---

## Purchasing v4.2 — bucket model

> **Authoritative spec:** the full Purchasing design lives in `docs/v1.5.1/01_Module_Packages/AutoBOM_Purchasing_v4.2_Claude_Design_Package.docx` (bucket model, request submission, flush pipeline, CPN traceability, embedded Purchasing UI, failure modes, full rejection criteria). This section is the **operating summary** — the 14-column sheet contract, write defaults, and append-only rule below are current and supersede any older 12-column text in earlier package revisions. If this summary and the v4.2 package ever diverge, flag it.

**Purchasing is a shared bucket, not a workflow role.** Every Request from every workflow pools into one embedded view accessible from Designer, Production, and Admin sidebars.

### Bucket streams
Two streams (Critical and Main), each with Admin-configurable batch interval (defaults 180 min Critical, 360 min Main). Timers never overlap. Batches are atomic.

### Critical toggle on Request submission
Boolean, default off. On → Critical stream. Off → Main stream. Cannot be edited after submission. On Josh's sheet: `Next Day` (Critical) or `2-Day` (Main).

### Full / Filtered toggle
- **Full** — every in-flight Request. Admin default.
- **Filtered** — requester = current user only. Designer / Production default.

### Batch flush pipeline (Pattern A — mirrors POC)
Timer fires → group entries by supplier → build Mouser cart via Cart API → build DigiKey list via MyLists API → write to Josh's sheet via Microsoft Graph (one row per supplier per batch, 14-column schema fixed) → batch state = WRITTEN.

Atomic: all steps succeed or batch stays Pending.

**CPN written into each cart line via customer reference field.** NOT written to sheet.

### Josh's sheet — 14 columns, per-supplier-per-batch rows

The live Daily Purchasing List has **14 columns** (it is a shared sheet — humans also add manual, non-electronic purchase rows to it). AutoBOM writes **only** its defined columns below for the Mouser/DigiKey electronic-component batches, and leaves the human-managed columns blank. AutoBOM never adds, reorders, or renames columns.

| # | Column | AutoBOM writes | Post-write |
|---|---|---|---|
| 1 | Date | Date/time the row is written to the sheet (write timestamp) | Buyer-managed |
| 2 | Project | `Other` (fixed default) | Buyer may override |
| 3 | Vendor | Supplier name (`Mouser` / `DigiKey`) | Buyer-managed |
| 4 | Item | Category label | Buyer-managed |
| 5 | Need | `Component Purchasing` (fixed default) | Buyer may override |
| 6 | Unit Price | Cart total (cost of the cart) | Buyer may override |
| 7 | Quantity | **1** | Buyer may override |
| 8 | Total Cost | Unit Price × Quantity | Buyer may override |
| 9 | Link to Product | Mouser/DigiKey cart **share link** (the cart's share key/URL) | Buyer clicks to purchase |
| 10 | Urgency | `Next Day` (Critical) or `2-Day` (Main) — set by the AutoBOM user's Critical toggle | Fixed at submission |
| 11 | Requestor | `Aaron Jones` (default for now) | Buyer may override |
| 12 | Status | **Blank** | Buyer-managed (`Purchased` / `Processed`) |
| 13 | Purchase Date | **Blank** | Filled when the order is placed |
| 14 | Long Link (alternative) | **Blank** | Buyer-managed (backup / full URL) |

**AutoBOM adds no new columns and no CPN column. The schema is a fixed 14 columns.**

> **Fixed write defaults (current):** `Project = Other`, `Need = Component Purchasing`, `Requestor = Aaron Jones` (temporary default until real requester routing is wired). `Date` = write timestamp; `Unit Price` = cart total; `Quantity = 1`; `Total Cost = Unit Price × Quantity`; `Link to Product` = the Mouser/DigiKey cart **share link**. The sheet's add-item form marks Date, Project, Vendor, Need, Unit Price, Quantity, Link to Product, Urgency, and Requestor as **required** — these defaults guarantee every required field is populated on each Graph write so the append never fails validation. (`Total Cost`, `Status`, `Purchase Date`, and `Long Link` are not required.)

> **Urgency scope:** AutoBOM only ever writes `Next Day` (Critical stream) or `2-Day` (Main stream). Other values seen on the live sheet (`Amazon Prime`, `Ground`, etc.) are entered by humans for manual non-distributor purchases and are outside AutoBOM's scope — AutoBOM is electronic-components-only (Mouser + DigiKey).

**Sheet-write one-way.** AutoBOM writes at flush; does not read back.

### Append-only, write-once (hard rule — program this in)
AutoBOM's **only** sheet operation is appending a new row. It MUST NOT edit, overwrite, reorder, clear, or delete any existing row or cell — including rows AutoBOM wrote in earlier batches and rows people added by hand. Use only the Graph row-append call; never a delete, clear, or update call.

- **Write-once.** Each bucket entry is written to the sheet exactly one time. Guard on `bucketState` — an entry already `WRITTEN` is never re-written, updated, or re-flushed, and no duplicate row is ever created for the same entry.
- **No empty rows.** Never append a row for a cart that has no items / no content. Skip empty carts entirely — do not create blank or placeholder rows. A row is written only when it carries real data (a real cart with a share link and a cost).

### Sheet integration — Microsoft Graph API (SharePoint / OneDrive in Teams)

The Daily Purchasing List is an Excel workbook living in the SharePoint / OneDrive document library behind a Microsoft Teams team. AutoBOM writes to it **through the Microsoft Graph API** — there is no other integration path. Build the writer so that when credentials arrive it plugs in with no code change (graceful-fallback pattern from `AutoBOM_Deployment_Readiness.md`).

- **Credentials (`.env`, never hardcode/log):** `MICROSOFT_GRAPH_TENANT_ID`, `MICROSOFT_GRAPH_CLIENT_ID`, `MICROSOFT_GRAPH_CLIENT_SECRET`, `ONEDRIVE_PURCHASING_SHEET_ID` (the workbook's drive-item id). Same Azure AD app registration as SSO.
- **Auth (app-only / client credentials):** `POST https://login.microsoftonline.com/{MICROSOFT_GRAPH_TENANT_ID}/oauth2/v2.0/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, `scope=https://graph.microsoft.com/.default`. Token ~60 min — cache and refresh like the DigiKey token. The app registration needs application permission `Sites.ReadWrite.All` (or `Files.ReadWrite.All`) with admin consent.
- **Locate the workbook:** by drive-item id — `/drives/{driveId}/items/{ONEDRIVE_PURCHASING_SHEET_ID}` (or `/sites/{siteId}/drive/items/{itemId}`). The workbook should contain a formatted Table over the 14-column header row (e.g. named `PurchasingList`).
- **Append rows:** `POST /drives/{driveId}/items/{itemId}/workbook/tables/{tableName}/rows/add` with body `{ "values": [ [ <14 cells in column order> ], ... ] }` — one inner array per per-supplier-per-batch row, empty string for human-managed columns. If the sheet has no Table, fall back to a range write: `PATCH .../workbook/worksheets('{sheet}')/range(address='A{row}:N{row}')` — targeting the **next empty row only, never an existing row**.
- **Atomic batch write:** open a workbook session — `POST .../workbook/createSession {"persistChanges": true}` → send the returned id as the `workbook-session-id` header on every write in the batch → `POST .../workbook/closeSession`. This holds the batch's rows to the Pattern-A all-or-nothing boundary.
- **Column order is fixed** exactly as the 14-column table above. Write cells in that order; never reorder or rename.
- **Graceful fallback:** if the `MICROSOFT_GRAPH_*` / `ONEDRIVE_PURCHASING_SHEET_ID` values are empty or placeholders (local dev), the writer **logs the batch rows to console** instead of calling Graph — Aaron can develop the whole purchasing pipeline without touching Josh's real sheet. When the values are real (Azure mode), writes go to the live workbook. Same code path, gated on whether the env vars hold real values. Implement in `backend/integrations/microsoft_graph.py` + `backend/services/purchasing_sheet_writer.py`.
- **One-way:** AutoBOM only writes at flush; it never reads the sheet back. Josh owns everything post-write.

### Bucket state values
`QUEUED_MAIN` · `QUEUED_CRITICAL` · `WRITTEN` · `PURCHASED` / `PROCESSED`. No `approved`, no `partially-ordered`, no `ordered`, no `shipped`.

### v4 rejection criteria
- Any Required By / Urgency dropdown on the Request form
- Per-line urgency on sheet
- Immediate per-submission sheet writes
- Half-writes / interleaved batches
- Hard-coded timer intervals
- Order Execution / cart-submission UI
- AutoBOM adding new sheet columns
- CPN column on sheet
- `approveRequest` / `rejectRequest` flow
- Order lifecycle objects (POs, Shipments) as first-class state
- Editing, overwriting, reordering, or deleting existing sheet rows or cells (append-only)
- Empty or placeholder rows written to the sheet
- Duplicate / repeat writes of an already-`WRITTEN` entry

## Notification routing

- **Notifications are task handoffs, not links.** Route the clicker to the screen where THEY can resolve it inside THEIR workspace.
- Record shape: `routes: { designer?, production?, admin? }` + `actionLabel`, `verb`, `sourceRole`, `targetRole`.
- **Notification click → Dashboard**: ACTION notifications route to clicker's OWN dashboard with the matching Needs Attention card scrolled + amber-flashed.
- **Multi-role users**: auto-switch with banner ("Switched to Production context — task assigned to Production").
- **Purchasing role gets no notifications** — Purchasing is not a role.
- **Batch failure notifications → Admin.**

### New notification types under the revised model
- **Push-Back recommendations received** — Designer resolves a Push-Back → Production Dashboard gets a "Replacements recommended" card → primary action: Apply (which commits recommendations to master BOM and version-increments).
- **Production self-serve equivalent swap** (FYI to Program owner Designer, if any) — Admin-configurable per Program. Format: "Production swapped [MPN] → [MPN] on [Project.master BOM], both spec-matched."
- **Production self-serve mismatch override** (audit + notification to Program owner Designer, if any) — always fires. Format: "Production overrode characteristic-match on [MPN] → [MPN], reason: [X]."
- **Model B re-upload notifications** — fired to Designer (if open Push-Back), Purchasing/Production (if Request in bucket or Build in draft) with what was invalidated.

---

## Dashboard is the operational inbox

- **Task Center does not exist** — no nav, no route, no state machine. Dashboard IS the inbox AND work surface.
- **Needs Attention** — top section of every Dashboard. Only items requiring current user's action. Empty → "All caught up" green state. Sidebar Dashboard badged `[N]`.
- **Every item is interactive** — card title navigates to detail; action button completes the common action inline.
- **Inline expansion grows the card WITHIN page flow** — never modal, overlay, or takeover.

### Per-role Needs Attention cards

**Designer:**
- BOM exception (Push-Back received — opens resolution inline)
- Stale sourcing (Re-check inline)
- Unassigned Push-Back pool (Take ownership)

**Production:**
- BOM awaiting sourcing (Run sourcing inline)
- **Replacements recommended** (Designer resolved a Push-Back — Apply inline commits to master BOM)
- BOM awaiting validation (Review → navigates)
- Push-Back pending Designer (informational)
- Build coverage red / amber (Review inline)
- Receiving batch complete FYI (View archive)

**Admin:**
- Failed job (Retry inline)
- Stuck workflow >48h (Reassign inline)
- DigiKey token expiring (Refresh inline)
- Batch flush failure (Diagnose inline)
- Force-waives past 24h (Review log)
- System Status health rows

### v4 rejection criteria (additive)
- Task Center in any form
- Display-only Dashboard items
- Actions that force navigation for the common response
- Modal/overlay for inline expansion
- Push-Back arrival at a dedicated `/d/exception/:id` screen
- **Push-Back resolution via manual MPN typing** (retired — use unified characteristic search)
- **Designer's Push-Back resolution silently mutating the master BOM** (retired — Designer produces recommendations Production applies)
- **Variant declaration UI as a separate step from Build creation** (retired — Build creation is master + overlay only)
- **File re-upload as everyday-edit affordance** (retired — Model B ceremony required for mistake recovery)

---

## Scrolling & layout

- Sidebar **fixed**, never scrolls. Everything else is **one unified scrollable page** using native scroll and native scrollbar.
- No inner scroll boxes inside content sections, tables, or panels.
- Sticky: top rail, table column headers, action bar.
- Design assuming hundreds of line items. Compression that hides info = design failure.
- Desktop-first. Mobile is read-only for order status only.

---

## Navigation & persistence

- URL-routed hash routing. Browser Back/Forward work. Deep links work.
- Breadcrumbs below top rail on every page, fully clickable.
- Tabs reflected in URL (`?tab=`); switching never reloads.
- Workspace persistence via `useListState(key, defaults)` (sessionStorage): filters, sort, scroll restored on return.
- Related-object links on every detail view. No dead ends.

---

## Search

- Primary search is a contextual overlay, not a page navigation. Top rail bar → dropdown; **⌘K / Ctrl+K** → centered command palette.
- Live results on every keystroke. Categorised: Components · Storage locations · Collections · BOMs · Projects · Requests.
- **App-wide search runs in `search_available_stock` mode** — PartsBox primary. "Include suppliers" toggle adds Mouser + DigiKey.
- **Push-Back resolution search runs in `search_suppliers` mode** — Mouser/DigiKey primary. "Include wall" toggle adds PartsBox.
- **Production inline-edit characteristic-match check runs in `search_suppliers` mode** — checks the intended replacement's characteristics against the source line's; renders match/differs/improves comparison silently in the background, surfaces soft flag if mismatch.
- Both sections shown, never deduped.
- **Storage locations** as first-class result cards. Click opens location detail INSIDE AutoBOM.

---

## Input principle

Wherever a value has a known set of valid answers, user **selects** (dropdown/segmented/picker) — never types from scratch. Free typing reserved for genuinely open content (notes, comments, descriptions, audit reasons). Apply opportunistically.

---

## Comments

- Every commentable object has a thread. `<CommentThread entityId>`.
- Chronological, oldest→newest.
- **Push-Back has TWO thread levels**: overall thread + per-flagged-line sub-thread.
- Required on: Collections, BOMs, Push-Backs, Requests, resolution surfaces.
- Comments cannot be deleted (audit weight).

---

## Collections

- **Only Designer Collections in MVP** — violet, role=designer. Development Collections deferred.
- **Collection→Program required** — dropdown at creation. Program is required.
- Inline-editable on detail (active/draft only): name, description, program.
- Per-row controls: edit qty, edit per-item note, remove-with-confirm, refresh sourcing.
- **Add part NEVER navigates.** Inline drawer using `search_available_stock` mode.
- **New Collection modal** — required: name, program, description, category, owner.
- **Stale data gate at Request to Order.**

---

## Production BOM screen (updated for v4)

- Header: name, version, state, buildQty (default build count for coverage), overage
- Items table with two on-hand qtys per line ("In project box" + "On wall")
- Coverage indicators driven by "In project box" only
- **Every line editable inline for non-structural fields** (note, description, designator text) — Production writes freely
- **Line MPN/manufacturer editable inline for characteristic-matched swaps** — silent commit on match, soft-flag prompt on mismatch (Send to Designer / Continue as override)
- Row-level actions: edit, remove-with-confirm, refresh sourcing per line, flag for Push-Back
- Collection-level: Run sourcing, Send Push-Back (structured), Create Build, **Re-upload master BOM** (Model B ceremony)
- **Re-upload button always visible; behavior depends on state:**
  - BOM in draft state → straightforward replace with audit entry
  - BOM in sourcing/results state → confirmation with what invalidates + audit reason
  - BOM in exceptions state → confirmation flags open Push-Backs will be cancelled + audit reason + affected-party notifications
  - Any Build against BOM → confirmation flags Build coverage will recompute + audit reason + Production notification

---

## Production exception handling

- **Cancel sourcing preserves partial results.** Completed lines stay; BOM returns to normalised. Partial-results banner offers `[Re-run sourcing on unsourced lines]`.
- **PartsBox failure non-blocking.** Submission still proceeds; procurement package view shows error with `[Retry]`.
- **Push-Back submission is structured** (see Push-Back section).

---

## Admin — Bounded Authority in practice

- **User CRUD** — destructive actions require confirmation + audit reason (≥10 chars).
- **Role assignment** — Admin assigns Designer / Production / Admin only.
- **Distributor priority** — dropdown (Mouser first / DigiKey first).
- **Freshness threshold** — dropdown.
- **Alternate-part policy** — toggle.
- **CPN format string** — free-form within grammar validation.
- **Bucket timers** — integer minutes within range.
- **Cache TTL** — integer seconds within range.
- **Push-Back escalation window** — integer hours within range.
- **Characteristic-match rules** — Admin can adjust which characteristics gate silent swap (Bounded Admin — cannot disable check entirely, but can tune per-Program).
- **Per-Program FYI notification policy** — Admin toggles whether Program owner Designer gets FYI on Production self-serve equivalent swaps for that Program.
- **Force-Waivers** — logged with actor, target, reason, timestamp. Individual force-waives require confirmation + reason.
- **Runtime observability** — dry-run mode, decision traces, execute-as-user.
- **Batch flush escape hatch** — `flushBucket(stream)` manual flush, audit-logged.

---

## Retired concepts (v1.3–v1.5 residue — do NOT reintroduce)

- Purchasing as a login role
- Purchasing dashboard (`b.dashboard`)
- Standalone Purchasing screen (`b.purchasing`)
- Bucket view route (`b.requests`)
- Order Execution route (`b.orderExec`)
- Order Placement route (`b.orderPlace`)
- Purchase Orders route (`b.orders`)
- Shipments route (`b.shipments`)
- Request Review as standalone screen (`b.requestReview` — absorbed into embedded Purchasing)
- `approveRequest` store action
- `placeOrder` store action
- `createShipment`, `setShipmentStatus`, `setOrderStep`, `_rollupRequest` store actions
- ORDERS seed array
- SHIPMENTS seed array
- Request state values `approved`, `partially-ordered`, `ordered`, `shipped` — replaced by `bucketState`
- Old CPN format `<bucket>-<sourceId>-<initials>-<line>` — replaced by sigil format
- `cpnFor(sourceObj, line)` old helper in `data.jsx`
- Designer sidebar item "My Orders" (`d.orders`)
- Designer Dashboard "My Orders" panel
- Standalone Designer search page (`d.search`)
- Production sidebar item "Receiving" as top-level (moves inline to embedded Inventory)
- Admin sidebar split (Roles & Permissions + Workflow Config + Suppliers + System Settings) — consolidated into Configuration tabbed screen
- Old `NAV_BY_ROLE.purchasing`, `.manager`, `.executive`, `.readonly` entries
- Task Center in any form
- `Required By` dropdown on any form
- `Urgency` word on any AutoBOM-facing form (only Josh's sheet uses Urgency column)
- Push-Back navigation to `/d/exception/:id` (dashboard-inline only)
- Push-Back resolution via manual MPN typing (unified characteristic search only)
- **Designer directly mutating the master BOM from resolution** (Designer produces recommendation; Production applies)
- **Variant declaration diff-and-propagate** (retired — Build creation uses master + overlay only)
- **Variant CSV upload as a separate flow** (retired)
- **Manual variant click-through as a pre-Build step** (retired — Build creation directly sets per-line overlay against master)
- **"Different-new" propagation logic** (retired — new lines flow through Push-Back with `missing-component` reason)
- **One-time-only BOM upload** (retired — Model B allows re-upload for mistake recovery with ceremony)

---

## Future expansion (deferred)

- Development role + Investigations + Improvement Recommendations + Rework Packages + Firmware Releases + Development Collections (behind DEV_ROLE_ENABLED).
- Review & Share workflows.
- Proactive PCN alerts from DigiKey Product Change Notifications API.
- Email / Microsoft Teams notification channels.
- Additional suppliers beyond Mouser and DigiKey.
- Analytics and reporting.
- Cloud deployment.
- Mobile access (currently read-only for order status).
- ERP integrations.

---

## Working discipline for Claude Design

1. **Read this file first, every session.** Supersedes anything in module packages when conflicts arise.
2. **When in doubt, ask Claude Architect via elicitation before building.** One question at a time.
3. **Trace ripples on every change.** Nothing is an isolated system.
4. **Prefer leveraging APIs.** If a capability exists at PartsBox / Mouser / DigiKey, use it. If you find yourself building parametric matching in JavaScript, stop and ask.
5. **Do not reintroduce retired concepts.** If a legacy pattern needs to touch retired territory, flag it.
6. **Speed and usability matter more than aesthetics.** AutoBOM is an internal business tool.
7. **Preserve the Designer-recommends / Production-applies separation** on Push-Back resolution. This is a fundamental workflow constraint.
8. **Characteristic-match check is silent when it succeeds** — Production sees no friction on equivalent swaps. Only mismatches surface UI (soft flag).
9. **Model B re-upload ceremony scales with downstream impact** — no ceremony on draft state; heavy ceremony on active/exception states.
