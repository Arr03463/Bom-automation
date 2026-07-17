# AutoBOM — Project Standards (v4)

**Source of truth:** the v1.5.1 baseline plus the four v4 module packages.

- PRD: `uploads/AutoBOM_PRD_v1.5.1.docx`
- Master Design Contract: `uploads/AutoBOM_Claude_Design_Package_v1.5.1.docx`
- Permissions Matrix: `uploads/AutoBOM_Permissions_Matrix_v1.5.docx`
- Module packages: Purchasing v4.1, Inventory Activation v3.1, Designer Workspace Alignment v1.1.1, Production Workspace Alignment v1.1.1

**Ordering rule:** the PRD is *integrative* — it wins on cross-workflow, roles, data model, and integration topics. Module packages remain authoritative within their own scope. Earlier v1.1 / v1.3 / v1.4 / v1.5 texts are superseded but kept for history — do NOT treat them as current.

**Main build:** `autobom/AutoBOM Platform.html`.

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

## CPN (Customer Part Number) — sigil format

**Format:** `#` for project-bound, `~` for wall-bound. Initials removed (v1.3 residue).

Project-bound example: `#TVCA-B052-001` (project code `TVCA`, source bucket `B052`, line 001 zero-padded).

Wall-bound example: `~A-3-7-001` (PartsBox wall location `A-3-7`, line 001 zero-padded). Wall CPN pulls the location name dynamically from PartsBox — AutoBOM never hard-codes wall bin structure.

**CPN travels with the cart line item** to Mouser/DigiKey via the customer reference field at cart-build time. Prints on packing slip / QR label. Read at receiving. Routes physical bag via lookup against CPN issuance table.

**CPN is NOT written to Josh's Daily Purchasing List.** Josh's sheet has no CPN column. Per-CPN traceability lives inside AutoBOM's internal state and on the supplier cart line — never on the sheet.

**Display in monospace.** Read-only everywhere except the initial generation moment.

**Admin can configure CPN format string** within grammar validation (Bounded Admin Authority).

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

## Purchasing v4 — bucket model

**Purchasing is a shared bucket, not a workflow role.** Every Request from every workflow pools into one embedded view accessible from Designer, Production, and Admin sidebars.

### Bucket streams
Two streams (Critical and Main), each with Admin-configurable batch interval (defaults 180 min Critical, 360 min Main). Timers never overlap. Batches are atomic.

### Critical toggle on Request submission
Boolean, default off. On → Critical stream. Off → Main stream. Cannot be edited after submission. On Josh's sheet: `Next Day` (Critical) or `2-Day` (Main).

### Full / Filtered toggle
- **Full** — every in-flight Request. Admin default.
- **Filtered** — requester = current user only. Designer / Production default.

### Batch flush pipeline (Pattern A — mirrors POC)
Timer fires → group entries by supplier → build Mouser cart via Cart API → build DigiKey list via MyLists API → write to Josh's sheet (one row per supplier per batch, 12 columns fixed) → batch state = WRITTEN.

Atomic: all steps succeed or batch stays Pending.

**CPN written into each cart line via customer reference field.** NOT written to sheet.

### Josh's sheet — 12 columns, per-supplier-per-batch rows

| Column | AutoBOM writes | Post-write |
|---|---|---|
| Date | Batch timestamp | Josh's business |
| Project | **Blank** | Manual |
| Vendor | Supplier name | Josh's business |
| Item | Category label | Josh's business |
| Need | Free-text (or blank) | Josh's business |
| Unit Price | **Blank** | Josh's business |
| Quantity | **1** | Josh may override |
| Total Cost | cart_total at Qty=1 | Josh may override |
| Link to Product | Cart URL | Josh clicks |
| Urgency | `Next Day` or `2-Day` | Josh's business |
| Requestor | **Blank** | Manual |
| Status | Blank | Josh manages |

**No new columns. No CPN column. 12-column absolute.**

**Sheet-write one-way.** AutoBOM writes at flush; does not read back.

### Bucket state values
`QUEUED_MAIN` · `QUEUED_CRITICAL` · `WRITTEN` · `PURCHASED` / `PROCESSED`. No `approved`, no `partially-ordered`, no `ordered`, no `shipped`.

### v4 rejection criteria
- Any Required By / Urgency dropdown on the Request form
- Per-line urgency on sheet
- Immediate per-submission sheet writes
- Half-writes / interleaved batches
- Hard-coded timer intervals
- Order Execution / cart-submission UI
- New sheet columns
- CPN column on sheet
- `approveRequest` / `rejectRequest` flow
- Order lifecycle objects (POs, Shipments) as first-class state

---

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
