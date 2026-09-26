# AutoBOM Interaction Specification

Companion to `AutoBOM_Final_UI_Design_Spec.md` (visual design, approved — unchanged) and `Claude_Code_UI_Implementation_Handoff.md` (reuse/extract/retire matrix). This document defines the exact behavior of every interactive control so Claude Code can wire the real Streamlit implementation with no ambiguity. It specifies behavior only — no new prototype code is produced.

---

## 1. Search

**Field:** single text input (`search_event_input`), debounced value + one-shot Enter trigger.

- **Typing, PartsBox selected:** each keystroke resets a 350ms debounce timer. After the pause, the draft value updates and PartsBox rows re-filter locally against the already-loaded snapshot (`record_filter.search_and_filter` over `mpn/manufacturer/description`). No PartsBox API call per keystroke. If this is the first non-blank query this session and the snapshot isn't loaded yet, trigger the load (see §4 loading state) before filtering.
- **Typing, PartsBox not selected:** draft value updates the same way; nothing re-filters until Enter (no supplier calls from typing, ever).
- **Pressing Enter:** clears any pending debounce, commits the draft immediately, and — only if Mouser and/or DigiKey are selected — fires one supplier lookup (`search_components`) using the committed text and the currently-selected supplier sources. If neither supplier is selected, Enter has no supplier effect (PartsBox already live-filters).
- **Draft changes after a committed Enter query, before the next Enter:** supplier results **remain visible but are marked stale** — a small "Results are for 'old query' — press Enter to update" caption appears under the Supplier Results header. Do not clear or grey out the table; the operator may still want the last search's data while typing a refinement.
- **Clearing the field (✕):** resets the draft to empty. PartsBox reverts to whatever the blank-query state is (browse-if-warm, lazy-if-cold — see §9). Supplier results clear entirely (a blank query has no supplier meaning) and the panel returns to its idle "press Enter" state.
- **Loading state:** the very first PartsBox load shows the inline "Loading PartsBox inventory snapshot…" row + skeleton table (already in the mockup's `loading` state) inside the PartsBox card only; it never blocks the rest of the page. A supplier Enter search shows its own independent loading skeleton inside the Supplier card only — the two loading states are never coupled.
- **No-results:** each card shows its own empty state independently (PartsBox can be empty while suppliers have hits, and vice versa).
- **Error:** a failed PartsBox snapshot load shows `st.error` inside the PartsBox card body (card stays sized, no page-level crash). A failed supplier source (e.g. DigiKey token expired) shows inline in the Supplier card header strip while the other supplier's rows still render — partial failure never blocks the succeeding supplier.
- **Selected-row lifecycle on result changes:** a selection persists across page changes and quantity edits (never causes a rerender/reset). A selection is **cleared** when the identity of the result set changes in a way that could remove the selected record: submitting a new Enter query, unchecking the source that produced the selection, or the draft text going blank. It is **not** cleared by adjusting an unrelated filter that still includes the record, or by an unrelated PartsBox snapshot refresh that still contains that part_id.

## 2. Source selectors (PartsBox / Mouser / DigiKey)

Three checkboxes, default all on. They are the single authoritative set for:

- Live PartsBox filtering and Enter-triggered supplier search (this section).
- Which suppliers Upload's automatic sourcing calls (§3).
- Which suppliers `Add to BOM` re-sources against (§7).
- Which suppliers `Retry Exact` calls (§13).
- Which suppliers a fresh `Find Replacement` search defaults to (§13) — the operator can still narrow further inside that panel.

**Toggling a checkbox off:**
- Does not retroactively clear already-fetched results from that source; it only prevents new calls to it from this point on.
- Immediately updates the results layout (see below).
- If it was the source that produced the current selection, clear the selection.

**Resulting layout (updates instantly on toggle, no confirmation):**
- PartsBox only → PartsBox Results card full width; Supplier card hidden entirely.
- Mouser and/or DigiKey only (PartsBox off) → Supplier Results card full width; PartsBox card hidden entirely.
- Both families on → ~50/50 side by side (down to the 1366 stacking breakpoint, §18).
- All three off → neither results card renders; a single warning replaces them: "Select at least one source (PartsBox, Mouser, or DigiKey)."

## 3. Upload

**Control:** one compact drop-zone/button (`st.file_uploader`, visually compacted), accepting `.csv`/`.xlsx`, no separate "Process Upload" step.

- **Selecting/dropping a file:** processing starts automatically. The button area is replaced by a processing chip: filename, a spinner, and a line count once known ("Sourcing 42 lines"), with a thin indeterminate-to-determinate progress bar.
- **On completion (success):** the chip switches to a green "done" state: a checkmark, the filename, and one line of outcome text ("Merged 42 lines into Working Parts List" or, if this is the first BOM this session, "Created working BOM — 42 lines"), plus "PartsBox project updated" appended only if the write toggle was on. An "Upload another" link resets the drop-zone for a new file.
- **On completion (warnings):** same done state, plus the workspace-level dismissible amber banner (already in the mockup) summarizing warning count and the top 1–2 reasons; full list in an expander.
- **On failure:** the chip turns into an inline `st.error` with the failure reason; the drop-zone remains available to retry immediately (no separate reset needed).
- **Duplicate-file guard:** re-selecting the same file object (same `file_id`) on an unrelated rerun does nothing and shows the caption "'<name>' already processed into the working BOM below." Selecting a **new** file (even same filename, re-picked) always processes.
- **Merge behavior:** if a Working Parts List already exists (from Search or a prior Upload), the new file's cleaned/sourced rows are appended to it, never replacing it. If none exists yet, this upload becomes the working BOM.
- **Sourcing during upload:** uses the same authoritative source selection as Search (§2); if a supplier is unchecked, uploaded rows are not sourced against it.
- **Configuration dependency:** reads the *current* values of Build Quantity, Project Name, Project Description, and Update PartsBox Project (§11) at the moment of processing — not a separate per-upload copy of those fields.

## 4. PartsBox Results card

- **Row click (select):** populates Selected Part Details (§7) with that row's full record (including every current location). Visually highlights the row (blue background, filled selection ring).
- **Row click again on the already-selected row:** no special "deselect" gesture is defined — selection changes only by picking a different row, submitting a new query/filter that excludes it, or clearing the query. (Matches `st.dataframe` single-select semantics: clicking the selected row again is a no-op.)
- **Page change (Prev/Next/page number):** shows that page's slice of the *already-filtered* result set; does not reset filters, query, or the current selection (selection persists even if the selected row isn't on the newly-shown page).
- **Filter change (rail or popover):** re-filters immediately, resets to page 1, clears the selection **only if** the previously-selected row no longer matches the new filter set.
- **Query change:** same as filter change — re-filters, resets to page 1, conditionally clears selection.
- **Browse Inventory click (only shown when the query is blank and results aren't already showing "everything"):** loads/reuses the full warm snapshot and shows all 3,448 parts, 20/page, with the status line switching to "Browsing · read-only." This never mutates data. Clicking it does not require a query — it is the explicit lazy-load gesture described in the audit.
- **Refresh (status-strip link, shown once a snapshot is loaded):** requests a forced snapshot refresh. Shows a brief inline spinner in the status strip ("Loading PartsBox snapshot…"), then updates the "N parts · M locations · just now" timestamp and re-renders whatever PartsBox rows are currently in view (same query/filter/page state — refresh never resets the operator's place). If refresh fails, the old snapshot and timestamp remain, with an inline error appended to the status strip.

## 5. Supplier Results card

- **Row click (select):** populates Selected Part Details (§7) with source-appropriate fields (Source, MPN, Manufacturer, Description, Supplier P/N, Stock, Unit Price, Category/Lifecycle when returned).
- **Page/filter changes:** same rules as PartsBox (§4) — never triggers a new supplier API call; the current result set (from the last Enter) is what gets paged/filtered locally.
- **Partial source failure:** if DigiKey fails but Mouser succeeds, Mouser rows still render and remain selectable; the DigiKey failure shows as inline text in the card header strip, with a "Retry (Enter)" link that re-fires the same committed query.

## 6. Filters (rail at desktop, popover below ~1400px main width)

All filter state is shared between the two placements — collapsing/expanding the rail into a popover never resets selections.

| Filter | Control type | Behavior |
|---|---|---|
| Stock | Single-select (radio-style: All / In Stock / Out of Stock / Unknown) | Applies to whichever result card(s) are visible; a record with no confirmed stock is "Unknown," never treated as 0. |
| Manufacturer | Checkbox list with a "search manufacturers…" text filter above it; "Show N more" expands the rest | Multi-select; checking a value adds it to the membership filter; the search box only filters the *visible option list*, it does not itself filter results. |
| Storage Space / Location / Project (PartsBox only) | Multi-select checkbox/searchable list, generated only from spaces/locations/projects actually present in current results | Membership filter — a part matches if any of its locations match any checked value. Hidden entirely when suppliers-only layout is active. |
| Category, Package, Mounting, Dielectric, Lifecycle | Same categorical pattern as Manufacturer | **Rendered only when the current result set has at least one non-empty value for that field** (never a permanent empty control). |
| Resistance, Capacitance, Voltage, Tolerance, Power, Unit Price, etc. | Min/max text pair, parsed via engineering-unit syntax (e.g. "10k", "25V") | Same data-driven visibility rule; an unparsable value shows an inline warning and is not applied; a value outside the parsed range excludes the record. |
| Clear all | Link, top of the panel | Resets every filter (not the search query or source selection) to its default and re-filters immediately, resetting to page 1. |

- Every filter change re-filters the affected card(s) locally (no network/API call except the PartsBox snapshot load already covered) and resets that card's page to 1.
- The active-filter chip strip under the intake card shows one removable chip per non-default filter; clicking a chip's ✕ clears just that filter.
- At ≤1366px, opening the Filters popover shows the identical panel; closing it does not discard changes — filters remain applied whether the popover is open or closed.

## 7. Selected Part Details

Rendered only when a row is selected; otherwise the section is entirely absent (no reserved blank height).

- **Quantity − / +:** decrements/increments by 1; minimum 1; does not itself do anything besides update the number shown next to Add to BOM.
- **Direct quantity edit:** the number is also directly editable (numeric input); typing a value clamps to ≥1 on blur/Enter.
- **Add to BOM:** appends one new row to the canonical Working Parts List with the selected candidate's identity and the chosen quantity, then runs it through the same sourcing/replacement decision Find Replacement uses (so a PartsBox-selected part that also matches Mouser can still resolve to whichever supplier the sourcing engine prefers). Immediately shows an inline "✓ Added ×N as line M" confirmation in the card header (no page navigation, no full-page reload) and the Working Parts List below updates in the same render pass. Any purchasing artifacts already generated become stale as a result of this canonical mutation.
- **Selection persists** through a quantity change (§4/§5 rules).
- PartsBox selections show the grouped, multi-location Inventory Locations panel (§ design spec F); supplier selections show the Supplier Availability panel. Only fields the source actually returned are shown — no invented Category/Package for a PartsBox part that lacks them.

## 8. Configuration card

All four fields are live operator inputs, not display labels, and apply to whichever intake method (Search or Upload) is used — one shared configuration, not per-method copies.

- **Build quantity:** numeric stepper (− / value / +), minimum 1. Changing it does **not** retroactively touch existing BOM lines by itself. An "Apply to uploaded lines" link (shown once a BOM exists) explicitly recomputes `required_qty`/`build_quantity`/`status`/`notes` for every row that has a `qty_per_board` (i.e., came from an upload) using the same quantity-math function upload itself uses; manually Search-added rows (no per-board quantity) are never touched by this, since their required quantity was entered directly at Add time.
- **Project name / Project description:** free-text inputs, always editable, persist in session/run state; read by Upload at process time and stored on the run/output artifacts. Editing them after a BOM exists does not retroactively rename an already-created PartsBox project — only the next Update PartsBox Project write picks up the new name.
- **Customer Reference field:** shows the currently-applied reference (or "Set once parts are added" before a BOM exists) plus a validity chip and an "Edit ▾" affordance that opens the Customer Reference popover (§9). Disabled/hinted, not clickable, until a BOM exists.
- **Update PartsBox Project:** see §10.

## 9. Customer Reference editing

Opened via the Configuration card's "Edit ▾" (or the field itself once a value exists). A popover, not a page navigation — closing it (✕ or clicking outside) discards nothing already saved; unsaved builder state (a half-picked project/PCB) is simply dropped.

- **Type selector:** three-way segmented control — Project / PCB, Inventory, R&D. Switching types swaps the fields below; it does not clear a reference already applied to the BOM, only changes what the *next* Apply will produce.
- **Project / PCB:** "Project" is a searchable single-select sourced from the approved registry (`config/customer_reference_registry.json`); "PCB Code(s)" is a multi-select, same registry. Both required before a preview appears.
- **R&D:** "Project" single-select from the same registry; "Owner" is free text (not a registry concept — staff change over time). Both required before a preview appears.
- **Inventory:** evaluated **per BOM line**, not one global value. "Get recommendations for N lines" runs the location recommender once per row and lists, per line: the recommended location, a confidence label (Exact Part / Strong Similarity / Similar Family / Low Confidence / Manual Selection Required), the reason, and an editable location dropdown (pre-filled with the recommendation, but any known storage name is selectable). Each row has its own Save — recommendations are advisory and every one can be overridden before saving.
- **Live preview (Project/PCB and R&D):** shows the constructed reference string, its length vs. the 30-character max, and a validity indicator with specific error text when invalid (disallowed characters, too long, etc.).
- **Apply to all N lines:** writes the previewed value to every current BOM row's `customer_reference` field in one action; disabled while the preview is invalid.
- **Per-line overrides (expander, all types):** a plain text field per row, defaulting to that row's current value; typing and clicking that row's Save validates and writes just that row, independent of whatever bulk value was last applied.
- **+ Add approved project or PCB code:** an inline mini-form (type radio, code, description) that appends to the registry file and immediately makes the new code selectable in the dropdowns above — it does not itself set any BOM row's reference.
- Any successful reference write (bulk or per-line) marks purchasing artifacts stale, since Customer Reference feeds the Mouser/DigiKey export contents.

## 10. Update PartsBox Project (write toggle)

- **Visually and functionally distinct** from the PartsBox source checkbox next to Search — that one only ever reads; this one, when on, performs a write the *next time Upload processes a file* (it has no independent "run now" action of its own; it arms the write for the upload step).
- **OFF:** Upload sources parts as usual but never touches PartsBox project/storage state.
- **ON:** the next Upload creates or reuses a PartsBox project + same-name storage (tagged `production`) and adds the matched BOM entries into it. The helper text states this plainly ("Creates/reuses the PartsBox project… and adds matched BOM entries") and the control keeps its amber "WRITES TO PARTSBOX" treatment whenever it's on, regardless of scroll position or which card is focused.
- A successful write invalidates the shared PartsBox snapshot so the next PartsBox read (search, browse, or a recommendation) reflects the change rather than serving stale cached data.

## 11. Working Parts List

- **Row click:** no destructive action; used only to indicate which line a downstream action (e.g. jumping into Needs Review) refers to, where applicable. Rows are not individually deletable from this view in this design (no delete action was specified in the source app; do not add one silently).
- **Search working list:** free-text filter across MPN/manufacturer/description/designators/customer reference (`RESULTS_SEARCH_FIELDS`), applied live as typed, no Enter required (this is a local canonical-BOM filter, not a supplier call).
- **Source filter / Status filter:** single-select dropdowns, populated from the values actually present in the current BOM (never a fixed list); "All" clears the filter.
- **Customer Reference cell:** the one editable column; clicking it opens inline edit (pencil affordance already shown); saving validates the format and writes that row's `customer_reference`, marking purchasing stale.
- **Every other column is display-only** — reflects canonical `ActiveBomState` fields; no direct editing of MPN, quantity, source, or status from this table (those change only through Add/Upload/Retry/Replacement).
- Rows added via Search and rows merged via Upload appear in this same list with no visual distinction other than their actual `source`/`status` values — there is no "how it got here" column, by design.
- Pagination/scrolling: the list scrolls internally past its visible row count (a fixed max-height with internal `overflow-y`), rather than paginating, since it is the canonical list an operator scans as a whole.

## 12. Needs Review

Rendered only when the review count is greater than zero; otherwise entirely absent from the page.

- **Queue (left pane):** one entry per line needing review, each clickable; clicking loads that line into the detail pane on the right and clears any open replacement search from a previously-selected line.
- **Retry Exact:** re-runs the exact-match sourcing decision for this line against the currently-selected supplier sources; on completion the line's `result_status`/`source` update in place (in the Working Parts List and, if resolved, this line drops out of the Needs Review queue) and purchasing goes stale.
- **Find Replacement:** opens the replacement panel in Mouser/DigiKey mode, pre-populated with a query built from the row's known MPN/description; two quick-swap chips ("Use MPN: …" / "Use description instead: …") let the operator retarget the query without retyping. Clicking Search fires one supplier lookup (same lookup Search's Enter path uses).
- **Check PartsBox:** opens the same replacement panel in PartsBox mode instead — filters the already-shared snapshot locally (a read, not a new API call) and additionally shows a "Covers required qty?" column comparing each candidate's stock to the line's required quantity.
- **Selecting a replacement candidate:** highlights that row and enables "Use Selected Replacement"; does not itself change the BOM.
- **Use Selected Replacement:** re-sources this line to the selected candidate through the same `apply_replacement` path Add-to-BOM uses, closes the replacement panel, clears its per-row search state, and — if this resolves the line — removes it from the Needs Review queue. Purchasing goes stale.
- Replacement search state (query text, results, selection) is scoped per row_id, so switching between two review lines never loses either one's in-progress search.

## 13. Purchasing Handoff

Rendered only once a BOM exists.

**States and what's clickable in each:**

| State | Regenerate button | Downloads |
|---|---|---|
| Blocked by Needs Review | Disabled, with caption "Resolve remaining Needs Review items before regenerating purchasing." | Whatever was generated from a prior state remains downloadable if not stale |
| Stale — BOM changed | Enabled | Disabled, labeled "(stale — regenerate to update)" |
| Ready / Current | Enabled | Enabled |
| Generating | Disabled (shows a spinner + "Regenerating…" label); the whole card's action area is locked | Whatever was current before regeneration started remains downloadable until the new outputs land |
| Generation failed (full or partial) | Enabled (to retry) | Whichever specific outputs actually failed are disabled; outputs that succeeded (e.g. Mouser export when only DigiKey failed) stay enabled |

- **Regenerate Purchasing:** the *only* action anywhere in the app that creates purchasing artifacts (exports + a DigiKey MyList). Rebuilds every export from the current canonical BOM; on completion updates each artifact's status independently (Mouser export can be current while DigiKey failed, or vice versa) and shows any returned error text inline.
- **Download Mouser Export:** downloads the CSV as-is; the caption explicitly states this is for manual upload to Mouser — AutoBOM never creates a Mouser cart.
- **DigiKey MyList result:** displays only identifiers actually returned by the API (List ID; a Share identifier only if the API provided one — otherwise "Not provided by the DigiKey MyLists API," never fabricated).
- **Other output downloads** (cleaned workbook, cleaned CSV, sourcing report, DigiKey list CSV, PartsBox import/unmatched CSVs, run summary): each independently enabled/disabled based on its own artifact status, same stale/failed labeling pattern as the two primary cards.
- Nowhere in this section does any control check out, pay, or submit an order — every action either downloads a file or (Regenerate only) prepares/refreshes artifacts for a human to hand off manually.

## 14. Ownership marks, header, banners

- Arro/Yank marks are static images, non-interactive.
- The workspace warning/error banner (e.g. post-upload warnings) has a dismiss (✕) that hides it for the remainder of the session for that specific message; it does not undo whatever it was warning about.

## 15. Responsive interaction behavior

The 1920×1080 visual design and all interactions above are unchanged at every width — only *placement and stacking* change:

- **1440×900:** identical behavior; rail and Configuration narrow (see design spec §B); result tables gain horizontal scroll inside their cards when content exceeds the narrower width; no control is removed or hidden.
- **1366×768:** the filter rail collapses into a "Filters (n)" popover button beside the source selectors — clicking it opens the exact same filter panel described in §6, with the same live state; closing it does not lose filter state. If both result cards no longer fit side-by-side at the narrowed main-content width, they stack vertically (PartsBox above Supplier) rather than compressing below a usable column width. All other sections (Configuration, Selected Part, Working Parts List, Needs Review, Purchasing) keep the same interactions, just at reduced card widths with internal horizontal scroll on wide tables.
- No breakpoint changes what an action *does* — only how much horizontal space its container has.
