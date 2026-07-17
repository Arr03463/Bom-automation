# AutoBOM POC Baseline — Foundation Analysis

**Purpose:** What the POC does today, what rules it establishes, and how the platform builds on top of it. This document is the reality anchor — grounds every architectural decision in what actually works in production use right now.

**Reading order:** Read this BEFORE any v1.5 module package if you weren't the one who built the POC. It tells you what "foundation" means concretely.

**Companion documents:**
- `AutoBOM_Data_Flow_and_Sequencing.md` — how platform-level flows extend POC flows
- `AutoBOM_Platform_Architecture.md` — services that grow out of the POC modules
- `AutoBOM_API_Responsibility_Map.md` — same external APIs the POC already integrates with
- `AutoBOM_Code_to_Service_Connections.md` — POC modules mapped to platform services

**Audience:** All three Claude agents. Especially Claude Code (implementation is essentially "wrap and extend these POC modules") and Claude Architect (grounding for future spec decisions).

---

## 1. What the POC is

A Streamlit web app plus CLI. **Single-shot BOM processing tool.** User uploads a BOM file → sets a build quantity → chooses which supplier/PartsBox operations to run → clicks Run → gets back a folder of output artifacts (cleaned files, sourcing report, cart URLs, PartsBox project set up).

**Written in Python 3.9+.** Uses pandas for data manipulation, requests for HTTP, dotenv for config, openpyxl for XLSX, Streamlit for UI.

**Not a persistent platform.** Each run is independent. No accounts, no notifications, no cross-run state — except a persistent supplier lookup cache and PartsBox reuse-on-name behavior.

**Everything toggleable.** Every operation is a checkbox. Every external write has a dry-run mode. This is the operational philosophy the platform inherits.

---

## 2. Files and responsibilities

The POC organizes into these modules. Each module is a candidate for wrapping into a platform service.

| POC file | Lines | Responsibility | Platform service equivalent |
|---|---|---|---|
| `app.py` | 145 | Streamlit UI | Retired — replaced by SPA frontend |
| `main.py` | 316 | CLI orchestration | Retired — replaced by controller layer |
| `workflow_runner.py` | (referenced but not read) | Shared workflow entry called by both UI and CLI | Becomes the Decision Engine's `runWorkflow` orchestration |
| `bom_cleaner.py` | 1137 | Load BOM, normalize columns, standardize, consolidate duplicates | BOMService (import pipeline) |
| `sourcing_engine.py` | 242 | Mouser-first / DigiKey-fallback / wall-fallback decision logic | Sourcing Engine (extended with characteristic search modes) |
| `supplier_matcher.py` | 206 | (dormant) Nexar-based offer matching | Legacy — kept for reference; Nexar not in active platform |
| `supplier_lookup_cache.py` | 68 | Persistent JSON cache of supplier lookup results | Cache Layer (extended to TTL + refresh-on-write) |
| `manufacturer_aliases.py` | 297 | Manufacturer name normalization + MPN alias handling | ManufacturerAliasService (utility across all supplier-facing code) |
| `mouser_client.py` | 312 | Mouser Search API wrapper | MouserClient (kept as-is, extended for CPN in customer reference) |
| `mouser_cart_client.py` | 117 | Mouser Cart API wrapper | Same — extended for CPN in customer reference |
| `digikey_client.py` | 468 | DigiKey Product Information V4 wrapper | DigiKeyClient (extended to use ParametricFilters natively) |
| `digikey_mylists_client.py` | 278 | DigiKey MyLists API wrapper | Same — extended for CPN in reference field |
| `digikey_oauth_setup.py` | 168 | Interactive OAuth flow for MyLists 3-legged auth | AuthService (OAuth token lifecycle) |
| `digikey_list_export.py` | 31 | Export DigiKey list to CSV | Retired — sheet write happens at batch flush, not per-run |
| `partsbox_client.py` | 221 | PartsBox API wrapper | PartsBoxClient (kept as-is, extended for scan + build/create + QR + attachments) |
| `partsbox_project_builder.py` | 262 | Orchestrate BOM → PartsBox project + storage + entries | Split: ProjectService (BOM to master BOM) + PartsBox mirror sync |
| `sourcing_report.py` | 29 | Sourcing report export | Retired as a file export; kept as an internal audit report |
| `nexar_client.py` | 99 | Nexar aggregator API (dormant) | Not used |
| `config.py` | 6 | Constants (folders, file suffixes) | Merged into ConfigurationService |

---

## 3. The workflow the POC embodies

Ordered pipeline. Each step is optional (checkbox-toggled) but ordering matters when they run.

```
User uploads BOM (CSV or XLSX)
    ↓
User sets build quantity
    ↓
User provides project name (for PartsBox) + description
    ↓
User toggles: Run PartsBox / Run supplier sourcing / Use Mouser / Use DigiKey / Create Mouser cart / Create DigiKey MyList
    ↓
User clicks Run
    ↓
[Step 1] BOM Cleaning (always)
    - Load file (bom_cleaner.load_bom)
    - Normalize columns (alias mapping to STANDARD_COLUMNS)
    - Drop junk columns and empty rows
    - Clean text encoding noise
    - Parse combined manufacturer+MPN cells
    - Consolidate duplicate parts (same-part rows merged)
    - Compute required_qty = qty_per_board × build_quantity
    - Assign per-row status: valid | missing_mpn | missing_manufacturer | qty_mismatch | manual_review
    ↓
[Step 2] Sourcing (if toggle on)
    - For each row with MPN:
        Try Mouser lookup (unless supplier_mode = digikey_only)
        If Mouser has stock ≥ required_qty → selected_supplier = Mouser
        Else try DigiKey lookup
        If DigiKey has stock ≥ required_qty → selected_supplier = DigiKey
        Else sourcing_status = check_wall_inventory
    - Cache every successful lookup persistently (JSON)
    - Deduplicate lookups within run (run_cache)
    - Export sourcing report CSV
    ↓
[Step 3] Cart building (if sourcing ran + carts_lists toggle on)
    - Mouser cart (if MOUSER_CART_ENABLED):
        Filter rows where selected_supplier=mouser AND sourcing_status=sourced_mouser
        Group by MouserPartNumber (sum quantities)
        POST /api/v1/cart/items/insert
    - DigiKey list (always exports CSV)
    - DigiKey MyList (if DIGIKEY_MYLISTS_ENABLED):
        Filter rows where selected_supplier=digikey AND sourcing_status=sourced_digikey
        POST /mylists/v1/lists (create)
        POST /mylists/v1/lists/{id}/parts (add parts)
        Handle name conflict by appending timestamp
    ↓
[Step 4] PartsBox project setup (if partsbox toggle on)
    - Find or create Project by name (idempotent)
    - Find or create Storage Location by name (same name as project) (idempotent)
    - Build entries from BOM rows
    - For each row: find PartsBox part by MPN + normalized manufacturer
    - If match: entry has entry/part-id linked
    - If no match: entry still created with descriptive comments; row added to unmatched list
    - POST project/add-entries
    - Export PartsBox import CSV + unmatched CSV
    ↓
[Step 5] Outputs
    - Cleaned BOM workbook (.xlsx with multiple sheets)
    - Cleaned BOM CSV
    - Sourcing report CSV
    - DigiKey list CSV
    - PartsBox import CSV
    - PartsBox unmatched CSV
    - Run summary JSON
```

**This is the exact real-world workflow.** Every step corresponds to something a human would do manually: clean the BOM in Excel, look up parts on Mouser/DigiKey, build a cart, register the project in PartsBox. The POC automates each step and lets the user pick which steps to run.

---

## 4. Rules the POC establishes — locked baseline behavior

These are the business rules the POC has already validated in real-world use. **The platform inherits these as foundation.** Any change to these needs explicit justification.

### 4.1 BOM cleaning rules

- **Column names are matched via alias.** A designer's BOM can have "MFG", "Mfr", "Manufacturer 1", "Maker", "Brand" — the POC recognizes all as `manufacturer`. Same for MPN, quantity, designators, description, supplier, supplier part number, subtotal, lifecycle status. Every real-world BOM shape the team has encountered is covered.

- **Combined manufacturer+MPN cells are parsed.** When a designer puts "TDK C1005X5R0J104K" in a single cell, the POC splits it into `manufacturer=TDK` and `mpn=C1005X5R0J104K`.

- **Generic prefixes are filtered.** Values like "resistor", "capacitor", "diode" prefixed to a description don't get treated as manufacturer names.

- **Duplicate parts are consolidated.** If the same MPN appears on multiple rows (different designators, same part), the POC merges them: designators concatenated, quantities summed, per-supplier fields carried from the row with the most information.

- **Junk columns dropped.** Empty columns, whitespace-only columns, columns with no header get dropped.

- **Empty rows dropped.** Rows with no MPN AND no manufacturer AND no description get dropped.

- **Encoding noise cleaned.** Non-breaking spaces, curly quotes, zero-width characters get normalized.

- **Text stripped.** Leading/trailing whitespace on every field.

- **Standard columns after cleaning:** `source_file, source_row, designators, qty_per_board, build_quantity, required_qty, manufacturer, mpn, description, supplier, supplier_part_number, unit_price, subtotal, lifecycle_status, build_multiplier, status, notes`.

- **Row status values** after cleaning: `valid`, `missing_mpn`, `missing_manufacturer`, `qty_mismatch`, `manual_review`.

### 4.2 Sourcing rules

- **Mouser is checked first.** Default supplier mode. DigiKey is fallback. `SUPPLIER_MODE=digikey_only` reverses this for DigiKey-only mode.

- **Full-quantity coverage required.** A supplier is "selected" only if their stock ≥ required_qty. If Mouser has 8 and you need 10, Mouser is NOT selected — the platform tries DigiKey. If DigiKey also can't cover full quantity, the row falls to `check_wall_inventory`.

- **No split-supplier orders.** A single BOM line is fulfilled by ONE supplier (Mouser OR DigiKey OR wall). The POC does not split "10 from Mouser and 5 from DigiKey" for one line.

- **Wall is the third fallback.** When neither supplier can cover the required quantity, `sourcing_status = check_wall_inventory`. Matches Chapter A locked behavior (wall is exception, not default).

- **Sourcing status values:** `sourced_mouser`, `sourced_digikey`, `check_wall_inventory`, `manual_review`.

- **Required quantity** = qty_per_board × build_quantity. Computed at cleaning time (`apply_project_quantities`). Not per-line, not per-supplier — a straightforward multiply.

- **DigiKey MPN lookup uses ProductDetails endpoint first.** Falls back to keyword search if ProductDetails fails.

- **Mouser search rate-limited.** Configurable delay between searches (default 2.1 seconds). One retry with a 65-second backoff on `TooManyRequests`. Prevents throttling.

- **Persistent lookup cache.** Successful supplier lookups cached to `.cache/supplier_lookup_cache.json`. Cache key: `supplier|manufacturer|mpn|supplier_part_number` (all normalized). Later runs reuse cached results — significant speedup for BOMs with repeated parts across runs.

- **Within-run deduplication.** Same lookup query in the same run is only executed once, even if it appears on multiple rows.

### 4.3 Manufacturer normalization rules

- **Case-insensitive.** All comparisons lowercased.
- **Corporate suffix stripped.** `corporation`, `corp`, `incorporated`, `inc`, `limited`, `ltd`, `co`, `company`, `group` are removed.
- **Separators normalized.** `&`, `-`, `/` treated as spaces.
- **Whitespace collapsed.**
- **Alias table.** Known variants explicitly mapped. Examples the POC ships with:
  - "murata electronics", "murata manufacturing" → "murata"
  - "st", "stmicro", "st micro", "st microelectronics" → "stmicroelectronics"
  - "yageo group" → "yageo"
- **Substring match on lookup.** After normalization, if exact match fails, substring match is tried: "murata" in "murata electronics" → match.

### 4.4 Cart building rules

- **Mouser cart filter:** Only rows where `selected_supplier == "mouser"` AND `sourcing_status == "sourced_mouser"`. Both conditions.
- **DigiKey MyList filter:** Only rows where `selected_supplier == "digikey"` AND `sourcing_status == "sourced_digikey"`. Both conditions.
- **Deduplication in cart.** Same MouserPartNumber across multiple BOM lines gets its quantities summed. Cart has one line per distinct SKU.
- **Quantity written to cart** = supplier_order_qty (which is qty_per_board × build_quantity — already right-sized).
- **Wall / manual_review rows go into NEITHER cart.** They're deferred for human resolution.

### 4.5 PartsBox integration rules

- **Idempotent create.** Both `create_project` and `create_storage_location` first check `find_by_name` and reuse the existing record if found. Re-running the same project name doesn't create duplicates.

- **Project name = Storage location name = same clean string.** One-to-one relationship. The Storage location represents "incoming parts for this project."

- **BOM rows → PartsBox entries even without match.** Every BOM row becomes a Project entry. Rows that match an existing PartsBox part get `entry/part-id` linked. Rows without match still get an entry, with descriptive comments in `entry/comments` (Manufacturer, MPN, Description) — flagged for manual PartsBox part linking later.

- **Entry qty is qty_per_board.** NOT build-multiplied. Rationale: PartsBox project represents the board's BOM, not a specific build's consumption. Build multiplication belongs at cart-building time (supplier order qty).

- **Designators split on commas OR semicolons OR whitespace.** Then filtered for empty strings.

- **PartsBox part matching:** MPN exact match + normalized manufacturer name match. Substring fallback on manufacturer if exact fails.

- **Unmatched rows exported separately** as `_partsbox_unmatched.csv` for manual review.

### 4.6 DigiKey OAuth rules

- **3-legged OAuth** for MyLists. Not for standard product queries (those use 2-legged client credentials).
- **Refresh token flow.** Access token refreshed as needed. Refresh token persistence.
- **Interactive setup script** (`digikey_oauth_setup.py`) for initial authorization and token refresh.

### 4.7 Dry-run rules

- **Every external write has a dry-run mode.** PartsBox writes (`project/create`, `storage/create`, `project/add-entries`) check `PARTSBOX_DRY_RUN`. Mouser cart checks `MOUSER_CART_DRY_RUN`. DigiKey MyLists checks `SUPPLIER_DRY_RUN`.
- **Dry-run prints payload, returns simulated success.** No API call made, workflow continues as if it succeeded.
- **Reads are never dry-run.** Product search, project listing, storage listing all execute for real.

### 4.8 File output rules

- **Output folder** (`OUTPUT_FOLDER` config).
- **Files named after source stem.** `TVCA_bom.csv` becomes `TVCA_bom_cleaned.csv`, `TVCA_bom_sourcing_report.csv`, etc.
- **Consistent suffixes.** `_cleaned.csv`, `_cleaned.xlsx`, `_sourcing_report.csv`, `_digikey_list.csv`, `_partsbox_import.csv`, `_partsbox_unmatched.csv`.
- **Workbook has multiple sheets.** Cleaned BOM, warnings, review items, mapped columns.
- **Run summary JSON** captures totals: Mouser sourced count, DigiKey sourced count, manual review count, cart items, list items, PartsBox entries, output paths.

---

## 5. Production role — 1:1 mapping to POC (Aaron's baseline)

Production role in the platform is almost a direct translation of the POC user experience, with a few additions.

### 5.1 What Production INHERITS from POC (unchanged behavior)

- **BOM upload with cleaning.** Same file formats (CSV, XLSX). Same alias handling. Same duplicate consolidation. Same standardization pipeline. The Production UI has an "Upload BOM" affordance; behind the scenes it calls the same `process_bom_file` logic.

- **Build quantity setting.** Same numeric input. Same multiplication logic (`qty_per_board × build_quantity = required_qty`).

- **Sourcing engine invocation.** Same Mouser-first / DigiKey-fallback / wall-fallback logic. Same full-quantity coverage requirement. Same status enums. The "Run sourcing" button on the Production BOM screen kicks off the same engine.

- **Cart building.** Same Mouser Cart API and DigiKey MyLists API integration. Same filter rules. Same deduplication. The platform's bucket flush pipeline USES these clients — it doesn't reimplement them.

- **PartsBox project setup.** Same idempotent create/reuse. Same entry building. Same MPN+manufacturer matching. Same unmatched-rows handling. When Production creates a new Project in the platform, PartsBox project + storage location get created behind the scenes using the same builder.

- **Toggle-driven optionality.** Every step is optional. Production can choose to skip sourcing on a BOM if they just want to register the parts in PartsBox. Same operational flexibility.

- **Dry-run mode.** Same. Admin can toggle dry-run system-wide for testing.

- **Persistent lookup cache.** Same JSON cache file. Same cache key format. Cache stays effective across the platform's runtime and across restarts.

### 5.2 What Production ADDS on top of POC

These are the ways Production's world grows beyond what the POC's single-shot model handles:

- **Project as a persistent object.** POC creates a PartsBox project per run — the project name is the persistence handle. Platform makes Project a first-class object with metadata (owner, status, description, dates, program_id, etc.), stored in the platform database. PartsBox project sync remains — Platform's Project is authoritative, PartsBox is the mirror.

- **Master BOM as a persistent object.** POC processes a BOM per run and outputs artifacts. Platform stores the cleaned BOM as the master BOM for the Project, versioned. Re-uploads (Model B — ceremonial with confirmation + audit + notifications) trigger a version increment.

- **Builds as a separate concept.** POC has no "assembly" or "build" object — it's all one BOM per run. Platform adds Build as a first-class object referencing master BOM with per-line overlay (used / skipped / deferred / rework). Multiple Builds per Project over time.

- **Push-Back to Designer as the platform-mediated version of "walk over and ask."** POC has `manual_review` and `check_wall_inventory` statuses that flag rows for human resolution. In the POC, the human is the user of the tool — they resolve manually and re-run. Platform adds the Push-Back workflow: those flagged rows become structured Push-Backs sent to Designer, who resolves via characteristic search + attach replacement, then the platform notifies Production to re-source.

- **CPN issuance and tracking.** POC doesn't emit CPNs. Platform generates a CPN per Request line at bucket entry time. CPN travels through supplier cart customer reference field, through the physical bag label, back through receiving scan.

- **Bucket-and-batch bucket model.** POC creates a Mouser cart and DigiKey list per run. Platform introduces the bucket where every Request accumulates, then Critical/Main batch timers flush the bucket via the SAME cart-building logic on a periodic schedule.

- **Josh's Daily Purchasing List sheet write.** POC exports CSV files locally. Platform writes rows to Josh's sheet at batch flush (12 columns, per-supplier-per-batch, Cart URL populated).

- **Receiving flow with case-based routing.** POC has no receiving concept — it's an ordering tool. Platform adds the receiving flow: scan distributor barcode → PartsBox parses → AutoBOM matches CPN → routes to correct destination → PartsBox stock/add → fulfillment pill updates.

- **Multi-user awareness.** POC is single-user CLI/web tool. Platform has role-based access (Designer / Production / Admin), notification handoffs, comment threads, audit trails.

- **Persistent state across sessions.** POC is stateless between runs (except cache and PartsBox reuse). Platform maintains full state — you can close the browser, come back a day later, and see exactly where every BOM, Build, Request, and Push-Back stands.

---

## 6. Designer role — foundation from POC + new functionality

Designer role builds on POC's sourcing/matching infrastructure but adds workflows the POC doesn't have.

### 6.1 What Designer INHERITS from POC (foundation)

- **Sourcing engine.** Same Mouser + DigiKey clients. Same lookup logic. Same cache. When Designer runs sourcing on a Collection, it's the same engine Production uses on a BOM.

- **Manufacturer normalization + MPN alias handling.** Same. Designer's Collection lookups and Production's BOM lookups share the same normalization pipeline.

- **PartsBox integration foundation.** Same client. Same idempotent create pattern. Designer's world doesn't create PartsBox projects (Production does), but Designer's Collection-related search into PartsBox uses the same `find_part_by_mpn_and_manufacturer` logic.

- **Cart building affordances (indirectly).** When Designer submits a Collection as a Request into the Purchasing bucket, that Request eventually contributes to a batch flush, which builds Mouser carts and DigiKey lists using the POC's cart clients.

### 6.2 What Designer ADDS on top of POC (new functionality)

- **Program as top-level R&D/product organization.** POC has no concept of a Program (an R&D initiative, contract, or customer engagement above the project level). Platform introduces Program owned by Designer. Multiple Projects link to one Program via nullable program_id FK.

- **Collection as R&D component grouping.** POC has no Collection object. Platform adds Collection: Designer's "what parts should be used?" grouping under a Program. Feeds Requests to Purchasing bucket.

- **Push-Back resolution surface.** POC has no Designer role — no cross-role handoff exists. Platform adds the Push-Back resolution flow: Push-Back arrives on Designer Dashboard as Needs Attention card → inline expansion → per-flagged-line sub-cards with unified characteristic search → attach replacement → Send replacements to Production.

- **Characteristic search (extends POC's MPN+manufacturer match).** POC matches on MPN + manufacturer with normalized name comparison. Platform extends to characteristic-based search:
  - **`search_available_stock` mode** (PartsBox primary, suppliers overlay) — powers app-wide search bar
  - **`search_suppliers` mode** (Mouser/DigiKey primary, PartsBox overlay) — powers Push-Back resolution
  
  The characteristic-matching logic is NEW. Uses DigiKey's ParametricFilters (from Product Information V4) natively. Uses Mouser's keyword+client-filter fallback for parts DigiKey doesn't cover.

- **Datasheet lifecycle.** POC doesn't touch datasheets. Platform adds datasheet URL display in supplier result cards + on-user-action download-and-attach to PartsBox via `part/attachments` with `attachment/type=datasheet`.

- **Bidirectional MPN ↔ Manufacturer typeahead.** POC has no interactive search — it's batch processing. Platform's Push-Back resolution surface has this new UI pattern: typing an MPN filters manufacturer suggestions; selecting a manufacturer filters MPN autocomplete.

- **Program-linked Push-Back routing.** POC has no routing at all. Platform routes Push-Backs to Program owner Designer first (escalation window Admin-configurable), then to unassigned pool.

---

## 7. Behaviors — KEEP, EXTEND, or REPLACE

Concrete map of every POC behavior showing its fate in the platform.

### 7.1 KEEP (verbatim from POC, no change)

- BOM file loading (CSV / XLSX / openpyxl)
- Column alias mapping to `STANDARD_COLUMNS`
- Row status enums (`missing_mpn`, `missing_manufacturer`, `qty_mismatch`, `manual_review`, plus new)
- Combined manufacturer+MPN parsing
- Generic prefix filtering
- Duplicate part consolidation logic (`_consolidate_duplicate_parts`)
- Manufacturer normalization (case, suffix strip, alias table, separator handling, substring match)
- MPN part-number equivalence logic (`part_numbers_equivalent`)
- Mouser-first / DigiKey-fallback decision logic (`decide_no_split_supplier`)
- Full-quantity coverage requirement (stock ≥ required_qty)
- No-split-supplier rule (one line, one supplier or wall)
- Wall as third fallback (`check_wall_inventory`)
- Persistent supplier lookup cache (JSON file, cache key format)
- Within-run cache dedup (`run_cache`)
- Mouser search rate limiting + retry with backoff
- Cart filter rules (selected_supplier + sourcing_status both match)
- Cart quantity aggregation (sum duplicate parts to one line)
- Cart quantity = qty_per_board × build_quantity
- PartsBox idempotent create/reuse (`find_by_name` before `create`)
- PartsBox project name = storage location name
- BOM row → PartsBox entry conversion with `entry/part-id` when match found
- Unmatched rows still get PartsBox entries (with descriptive comments)
- Designator splitting (comma/semicolon/whitespace)
- Dry-run mode on every external write
- Toggle-driven optionality
- DigiKey OAuth 3-legged flow for MyLists
- DigiKey OAuth token refresh
- DigiKey MyLists name conflict handling (timestamp append)
- Entry quantity = qty_per_board (per-board qty, not build-multiplied)

### 7.2 EXTEND (POC behavior kept, add new capability on top)

- **Sourcing engine core logic → add characteristic search modes.** Keep Mouser-first/DigiKey-fallback for MPN-based decisions. Add `search_available_stock` and `search_suppliers` modes as new orchestration paths on top of the same lookup infrastructure.

- **Supplier lookup cache → add TTL + refresh-on-write.** Current cache has no expiration. Extend with Admin-configurable TTL (default 60s for PartsBox parts, 5min for supplier catalog, 24h for datasheet URLs). Refresh-on-write invalidation when AutoBOM writes to any object.

- **Cart building → add CPN in customer reference field.** Currently no reference field written. Extend `build_mouser_cart_items` and `build_digikey_mylists_parts` to write CPN into the appropriate customer reference field on each cart line.

- **PartsBox project entries → add per-CPN issuance link.** Currently entries are described-only. Extend so entries created from a Request tie back to the CPN issuance record for per-CPN fulfillment tracking.

- **DigiKey lookup → add ParametricFilters usage.** Currently only ProductDetails + Keyword search. Extend to use ParametricFilters in ProductSearch for characteristic-based queries (Push-Back resolution).

- **Manual_review status → route into Push-Back workflow.** Currently `manual_review` is a "look at this yourself" flag. Extend so BOM rows with `manual_review` or `check_wall_inventory` status become candidates for a structured Push-Back to Designer.

- **Wall check → make explicit in characteristic search.** Currently wall is fallback status only. Extend so wall inventory (PartsBox parts tagged `development`) is searchable directly in `search_suppliers` mode's "Include wall" toggle.

- **BOM cleaning → persist to master BOM.** Currently cleaned BOM is output artifact. Extend so cleaned BOM becomes the master BOM stored in the platform database, versioned, mirrored to PartsBox project.

- **Sourcing report → become internal audit report.** Currently exported as CSV. Extend so results are stored in platform DB, browsable through the BOM detail view, and auditable. CSV export remains available on demand.

- **PartsBox client → add scan, build/create, QR endpoints, attachments.** Current client covers project + storage + parts + entries. Extend with:
  - Native barcode scanning (receiving flow)
  - `build/create` for Build execution
  - ID Anything™ QR image endpoint
  - `part/attachments` with `attachment/type` for datasheet persistence
  - `stock/add` and `stock/remove` for inventory writes

- **Mouser + DigiKey clients → same as current, add characteristic search parameters.** Same auth, same base URLs, same rate limiting. Add search request shapes that include characteristic filters translated from AutoBOM's query.

### 7.3 REPLACE (POC behavior superseded by platform behavior)

- **CLI (`main.py`) as entry point → replaced by SPA + REST controllers.** Same workflow steps happen, but triggered by clicks in the UI, not stdin prompts.

- **Streamlit UI (`app.py`) → replaced by React SPA.** Streamlit was fine for single-user single-shot; platform needs multi-user, real-time, persistent state.

- **File outputs (`OUTPUT_FOLDER`) → replaced by database persistence + on-demand exports.** Users can still download artifacts, but the primary state lives in the DB, not the filesystem.

- **Interactive input prompts (in `main.py`) → replaced by structured form UI.**

- **Per-run PartsBox project name entry → replaced by Project object with persistent name.**

- **Local CSV exports as the sole recordkeeping → replaced by platform state as source of truth (with export-on-demand).**

- **DigiKey list CSV export as the "for Josh" delivery mechanism → replaced by direct write to Josh's Daily Purchasing List via Microsoft Graph.**

- **Sourcing report CSV as the "here's what needs review" mechanism → replaced by Dashboard Needs Attention cards on Production role.**

### 7.4 NEW (not in POC at all)

- Program object + Program CRUD
- Collection object + Collection CRUD (Collection → Program required)
- Push-Back structured object (reason, urgency, flaggedLines, comments)
- Push-Back routing logic (Program-linked → Program owner Designer; standalone → unassigned pool; escalation window)
- CPN issuance table + format-versioned records
- Bucket + Critical/Main streams + Admin-configurable timers
- Batch flush pipeline atomicity guarantees
- Batch state values (Pending, WRITTEN)
- Bucket entry state values (QUEUED_MAIN, QUEUED_CRITICAL, WRITTEN, PURCHASED, PROCESSED)
- CPN fulfillment state (Pending, Partial, Fulfilled, Over) per receiving scan-back
- Microsoft Graph / OneDrive integration for Josh's sheet writes
- Receiving flow with Case A-E routing
- Build object with per-line overlay states (used, skipped, deferred, rework)
- Notification service + role-targeted notifications
- Dashboard Needs Attention pattern
- Multi-user auth + role assignment + role switcher
- Comment threads on commentable objects
- Audit log (immutable) + Force-Waivers log
- Bounded Admin Authority configuration surfaces
- Decision Engine as service (formalizes what POC does implicitly in main.py orchestration)
- Sourcing Engine + Decision Engine two-service split
- Cache Layer with TTL + refresh-on-write
- Storage location detail surface inside AutoBOM (POC leaves this as PartsBox's UI)
- Datasheet URL display + attach-on-user-action
- QR delivery on Build result screen (calls PartsBox ID Anything™)
- Programs UI (list, detail, create)
- Collections UI (list, detail, create, add-part drawer)
- Embedded Purchasing surface with Full / Filtered toggle
- Embedded Inventory surface
- Bucket archive view with fulfillment pills
- Sigil CPN format (# project-bound, ~ wall-bound)
- Model B BOM re-upload ceremony (confirmation + audit reason + downstream notifications)
- Production-side inline BOM edit with characteristic-match check (Option 2)
- FYI notifications on Program-linked BOM edits to Designer

---

## 8. Configuration values the POC uses (Bounded Admin foundation)

The POC's `.env` values are the beginning of the ConfigurationService. Every one of them gets validated bounds and moves into `configurationService.get(key)` calls in the platform.

| POC env var | POC purpose | Platform equivalent |
|---|---|---|
| `PARTSBOX_API_KEY` | PartsBox auth | Configuration → Suppliers tab; secure field |
| `PARTSBOX_DRY_RUN` | Prevents real writes | Admin toggle for dry-run mode |
| `SUPPLIER_DRY_RUN` | Mocks supplier lookups | Admin toggle |
| `SUPPLIER_MODE` | `mouser_then_digikey` or `digikey_only` | Distributor priority radio |
| `MOUSER_SEARCH_API_KEY` | Mouser search auth | Configuration → Suppliers tab; secure field |
| `MOUSER_CART_API_KEY` | Mouser cart auth | Configuration → Suppliers tab; secure field |
| `MOUSER_CART_ENABLED` | Enables cart upload | Retired — always on if key present; feature flag |
| `MOUSER_CART_DRY_RUN` | Cart dry-run | Merged into unified dry-run flag |
| `MOUSER_BASE_URL` | Endpoint override | Configuration → Suppliers |
| `MOUSER_SEARCH_DELAY_SECONDS` | Rate limit spacing | Configurable within validated range (1-10s) |
| `MOUSER_RATE_LIMIT_RETRY_SECONDS` | Backoff on 429 | Configurable within validated range (30-300s) |
| `MOUSER_RATE_LIMIT_RETRIES` | Retry count on 429 | Configurable within validated range (0-5) |
| `SUPPLIER_LOOKUP_CACHE_ENABLED` | Cache toggle | Retired — always on; TTL configurable instead |
| `SUPPLIER_LOOKUP_CACHE_PATH` | Cache file location | Retired — DB / Redis in platform |
| `DIGIKEY_CLIENT_ID` | DigiKey OAuth | Configuration → Suppliers; secure field |
| `DIGIKEY_CLIENT_SECRET` | DigiKey OAuth | Configuration → Suppliers; secure field |
| `DIGIKEY_BASE_URL` | Endpoint override | Configuration → Suppliers |
| `DIGIKEY_TOKEN_URL` | OAuth token endpoint | Configuration → Suppliers |
| `DIGIKEY_MYLISTS_ENABLED` | MyLists feature flag | Retired — always on when OAuth is set up |
| `DIGIKEY_REFRESH_TOKEN` | 3-legged OAuth token | AuthService managed |
| `DIGIKEY_ACCESS_TOKEN` | Current OAuth access | AuthService managed |

### 8.1 New configuration values (not in POC)

- `bucket.timer.critical` (integer minutes, 15-1440)
- `bucket.timer.main` (integer minutes, 15-1440)
- `bucket.retry.count` (integer, 1-10)
- `bucket.retry.backoff` (integer seconds, 30-600)
- `partsbox.cache.ttl` (integer seconds, 10-3600)
- `supplier.cache.ttl` (integer seconds, 60-3600)
- `datasheet.cache.ttl` (integer hours, 1-168)
- `pushback.escalation.window` (integer hours, 1-168)
- `freshness.threshold` (enum: 1h / 4h / 12h / 24h / 48h / 7d)
- `alternate.part.policy` (toggle: auto-suggest / require-signoff)
- `cpn.format.string` (grammar-validated free-form)
- `distributor.priority` (radio: mouser-first / digikey-first)
- `msgraph.workbook.target` (file path config)

---

## 9. Cross-cutting patterns worth preserving

Beyond the domain rules, the POC has some cross-cutting operational patterns that are worth carrying into the platform verbatim:

### 9.1 Toggle-driven optionality

Every operation is a toggle. The user can skip any step. If sourcing fails, PartsBox setup can still run. If cart building isn't enabled yet, sourcing report + CSV export still deliver value. Same philosophy in the platform — every workflow surface has partial-success handling.

### 9.2 Dry-run everywhere

Every external write has a dry-run mode. Prevents accidental damage during testing. Platform inherits this at the service layer — every external client accepts a `dry_run` param. Admin runtime observability (dry-run mode against real inputs) is a formalization of this.

### 9.3 Continue-on-failure

`main.py` wraps each major step in try/except and continues to the next step on failure. Even if PartsBox fails, sourcing continues; even if sourcing fails, BOM cleaning outputs still get exported. This "graceful degradation" philosophy carries into platform — batch flush stays Pending on API failure, sourcing preserves partial results on cancel, cache misses are recoverable.

### 9.4 Print-heavy audit trail

POC prints extensively at every step. Progress + counts + statuses + errors + outputs — all echoed to stdout. Platform replaces prints with:
- Audit log entries (structured records)
- Notifications (user-facing surface changes)
- Decision traces (Bounded Admin observability)

Same operational insight, different medium.

### 9.5 Idempotent reuse

PartsBox project + storage are created OR reused based on name lookup. Cache lookups reuse across runs. Platform generalizes: every write operation checks "does this already exist?" first, avoiding duplicates on retry.

### 9.6 Normalization at ingest

Manufacturer names, MPNs, column headers — all normalized at read time, not at compare time. Reduces per-comparison cost, ensures consistent behavior. Platform carries this into every ingest path (BOM upload, receiving scan, catalog fetch).

### 9.7 Explicit "unknown" states

`missing_mpn`, `missing_manufacturer`, `manual_review`, `check_wall_inventory`, `no_offer`, `shortage`, `skipped`, `error` — the POC has a nuanced vocabulary for "not sourced" that goes beyond boolean success/fail. Platform preserves and extends this — status enums are first-class throughout.

---

## 10. Gaps the platform needs to fill (POC doesn't do these at all)

Direct list — no ambiguity, no coverage in POC, must be built:

1. Multi-user auth and session management
2. Role assignment and role-based permission checks
3. Persistent Program object CRUD
4. Persistent Collection object CRUD
5. Persistent master BOM with versioning
6. Persistent Build object with overlay states
7. Push-Back structured workflow (submission, routing, resolution, notifications)
8. CPN issuance table with format versioning
9. Bucket with Critical/Main streams and timers
10. Batch flush pipeline with atomicity guarantees
11. Microsoft Graph / OneDrive integration for Josh's sheet
12. Receiving flow (scan, case selection A-E, PartsBox stock/add, fulfillment update)
13. Notification service with role-targeted routing
14. Dashboard Needs Attention pattern
15. Comment threads on objects
16. Immutable audit log
17. Force-Waivers log (Admin-visible)
18. Configuration surfaces with Bounded Admin Authority
19. Runtime observability (dry-run mode, decision traces, execute-as-user)
20. Storage location detail surface inside AutoBOM
21. Datasheet attach to PartsBox on user-action
22. QR delivery via PartsBox ID Anything™
23. Programs UI (list, detail, create with sigil validation)
24. Collections UI (list, detail, create, Add Part drawer)
25. Embedded Purchasing surface (Full / Filtered toggle, bucket display, archive)
26. Embedded Inventory surface (PartsBox-backed with universal read+write)
27. Characteristic search UI with bidirectional typeahead
28. Two search modes (`search_available_stock`, `search_suppliers`)
29. Program-linked Push-Back routing with escalation
30. Model B BOM re-upload ceremony
31. Production-side inline BOM edit with characteristic-match check
32. FYI notifications on Production self-serve edits to Program-linked BOM
33. DigiKey ParametricFilters translation from characteristic query

---

## 11. Why this baseline matters

Two reasons this document is essential foundation:

**1. It tells Claude Code what NOT to rewrite.** The POC's business logic — column aliasing, manufacturer normalization, duplicate consolidation, sourcing decision — is battle-tested against real BOMs. Rebuilding it from spec would introduce regressions the POC has already worked out. Claude Code wraps and extends these modules; does not reimplement them.

**2. It tells Claude Design and Claude Architect what "intuitive" means.** Aaron's language "everything just works off of each other, works how it works in real life" refers to a workflow the POC has already validated. When we design new UI, we're building on top of a proven mental model, not inventing one. The Production role's UI is a persistent multi-Project version of the POC's single-shot experience. The Designer role's UI adds cross-role handoffs to the same foundation.

**Anti-pattern to avoid:** Treating the POC as "just a proof of concept, throw it away." That would discard hard-won business rules and force everyone to relearn the workflow. Right approach: **the POC is the foundation. Every platform capability either wraps a POC module, extends a POC behavior, or fills a gap the POC leaves.** No rewrites of already-working logic.
