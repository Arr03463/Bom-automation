# AutoBOM Operator Guide

Audience: a teammate using AutoBOM day-to-day, not the developer.

## Navigation

The sidebar has exactly two top-level destinations:

- **AutoBOM** -- one continuous workspace, not a set of separate
  pages/tabs. Add parts at the top (via Search or Upload -- see below),
  then scroll down through BOM Configuration (with Customer Reference),
  the working BOM/results, and Purchasing Handoff -- all on the same
  page, all reading/writing the same BOM. You never navigate away and
  lose your place.
- **PartsBox Inventory** -- a separate area for browsing/searching the
  full PartsBox catalog independent of any specific BOM run (see below).

## Add Parts

Two ways to add parts to your working BOM -- use either one, or both,
in any order:

- **Search** (the default/primary way) -- reuses the same search engine
  used everywhere else in AutoBOM. PartsBox is searched by default;
  enable Mouser/DigiKey for live supplier results. Enter a quantity next
  to a result and click **Add to BOM** to add that one line. Nothing is
  added automatically just by searching. If you haven't uploaded
  anything yet, adding your first part this way starts your working BOM.
- **Upload** (the secondary option, beside Search) -- upload a BOM as
  CSV or XLSX. Open **Upload settings** to set the build quantity,
  PartsBox project name/description, and which suppliers to source
  against, then click **Process Upload**.
  - If you haven't added anything yet, this becomes your working BOM
    (same behavior as before).
  - If you already have a working BOM (from Search, or an earlier
    upload), this **merges** the new file's lines into it instead of
    replacing what's already there -- nothing you've already added or
    configured is discarded.

Both methods feed the exact same working BOM: quantity handling,
PartsBox matching, supplier sourcing, Customer Reference, Needs Review,
and purchasing all treat a part the same way regardless of whether it
was searched-and-added or came from an uploaded file.

Adding parts here never creates a Mouser cart or DigiKey MyList -- see
Purchasing Handoff below for that.

## BOM Configuration

Once your working BOM has at least one part, this section appears with
settings for it:

- **Build quantity** -- edit and click **Apply Build Quantity** to
  recompute required quantities for every line that came from an
  uploaded file (quantity × build quantity). Lines added manually via
  Search have their required quantity set directly when added, so this
  does not change them.
- **PartsBox project** -- shown for reference; it's set from Upload's
  settings when a BOM file is processed. Parts added via Search alone
  are not synced to PartsBox.
- **Customer Reference** -- see below. It's part of configuring the BOM,
  not a separate purchasing-only step.

### Customer Reference

Sets the Customer Reference / Customer Part Number that flows into the
Mouser cart, DigiKey MyList, and export files for every BOM line. Three
ways to generate one, all from Yank's approved naming convention:

- **Project / PCB** -- pick an approved Project code and one or more PCB
  codes (e.g. `PRJ-ATH-DAB`).
- **Inventory** -- for stock/inventory builds. Click **Get Recommendations
  for All Parts** to see a suggested storage location for every BOM line
  at once (PartsBox exact-part match first, similar-part fallback), shown
  as a table you can accept or override per line before saving.
- **R&D** -- project code plus a free-text owner (e.g. `RND-ARM-AARON`).

**Apply to All BOM Lines** sets the generated reference on every row;
individual lines can still be overridden below. Assigning or changing a
reference never itself calls Mouser/DigiKey/PartsBox -- it only updates
the BOM's canonical data (and marks purchasing artifacts stale if
they'd already been generated under the old reference).

## Results / Needs Review

Below BOM Configuration:

- Summary metrics (Total Parts / PartsBox / Mouser / DigiKey / Needs
  Review).
- The working BOM table, including each line's **Customer Reference**,
  source, and status.
- **All Results** / **Needs Review**: search and filter the processed
  BOM; Needs Review isolates parts that couldn't be automatically
  sourced.

For each item needing review:

1. **Retry Exact Part** -- re-attempts the same MPN/manufacturer lookup.
   Use this first if you suspect a transient API issue.
2. **Find Replacement** -- opens the same shared search engine Add Parts'
   Search uses, prefilled with what AutoBOM already knows about the
   part, right there inline under that BOM line. Search Mouser/DigiKey,
   review candidates, and select one. AutoBOM updates the BOM row and
   re-runs sourcing for it automatically.
3. **Check PartsBox** -- last-resort fallback lookup against PartsBox
   inventory, for when no purchasable replacement is available.

Approving a replacement is always your decision -- AutoBOM will not
silently substitute a part.

## Purchasing Handoff

1. Purchasing status reflects the **current** BOM state, derived per
   supplier:
   - **Ready for Handoff**: every supplier that actually has items to buy
     has a current cart/MyList.
   - **Stale — BOM Changed**: a Needs Review action changed the BOM since
     purchasing artifacts were generated -- regenerate before handing off.
   - **Needs Review**: resolve remaining Needs Review items first.
   - **Partial — Generation Failed** / **Generation Failed**: one or both
     suppliers' cart/MyList creation failed -- see the error(s) shown, and
     retry. A supplier that already succeeded will NOT be recreated by a
     retry; only the failed one is retried.
   - **Not Required**: a supplier with zero sourced items for it never
     blocks readiness.
2. Click **Regenerate Purchasing** to (re)create what's needed from the
   current BOM. This is the ONLY action that can create a live Mouser
   cart or DigiKey MyList -- uploading, configuring, searching, changing
   Customer Reference, filtering, or just leaving the page open never
   does.
3. **Mouser**: cart creation is automatic; CartKey is shown in a copyable
   code block. Sharing with purchasing is a manual step for now -- open
   Mouser yourself, use its Share action, and hand the resulting Access ID
   directly to purchasing. Nothing needs to be pasted back into AutoBOM.
   Confirmed with Mouser: the Access ID is derived internally from the
   CartKey, but that derivation isn't currently exposed through any
   supported public/Automation Services API -- this is the current
   supported workflow, with a clean extension point for a future
   supported Mouser sharing API/integration. AutoBOM's role ends at
   handoff: checkout, payment, and order submission always happen
   manually, outside AutoBOM.
4. **DigiKey**: MyList creation is automatic; the List ID is shown in a
   copyable code block -- hand it to purchasing so they can locate it in
   DigiKey. Confirmed (2026-09-25, live): the MyLists API does not
   provide a separate share identifier/link -- the List ID is the
   identifier there is. If a share identifier is ever returned by the
   API, it will appear the same way, in its own copyable code block --
   AutoBOM never invents one.

## Downloads (Purchasing Handoff)

Each output file (cleaned CSV, cleaned workbook, sourcing report, DigiKey
list CSV, PartsBox import/unmatched CSVs, run summary) tracks its own
freshness. A file is disabled for download when it's stale (the BOM
changed since it was generated) or when its last generation attempt
failed -- **other files being current does not re-enable it**. Two files
(the multi-sheet cleaned workbook and the PartsBox unmatched CSV) are
never automatically regenerated after a BOM change; upload the BOM again
(as a fresh working BOM, or merged into the current one) if you need a
current copy of either.

## PartsBox Inventory

A separate top-level page for browsing/searching the full accessible
PartsBox catalog (PartsBox remains the system of record) -- not limited
to parts referenced by the current or any BOM run. Search, or click
**Browse All** with an empty query to see everything. Storage Locations
shows which storage locations carry the `production` tag.

This page itself is read-only by design: opening it, searching, or
filtering never writes anything to PartsBox. That's a property of this
*page*, not a limitation of AutoBOM's PartsBox integration as a whole --
AutoBOM does perform real PartsBox writes elsewhere, as part of
processing an uploaded BOM file (creating/reusing the project and
storage location, and syncing BOM entries into it -- see Add Parts
above). Those writes only happen from an explicit **Process Upload**
click, never from viewing this page, and never from adding parts via
Search alone.

## What NOT to do

- Don't click **Regenerate Purchasing** repeatedly "just in case" --
  it's a no-op for anything already current, but each attempt for a
  failed/stale supplier does make a live vendor call.
- Don't treat a disabled download as a bug -- it means that specific file
  doesn't match the current BOM; regenerate or re-run instead.
- Don't manually edit files under `runs/` -- they're per-run scratch
  space and may be cleaned up automatically (see the deployment guide's
  retention policy).
- Don't paste a Mouser or DigiKey secret/token into any AutoBOM field --
  none of AutoBOM's own UI ever asks for one.
- Parts added via Search alone aren't synced to a PartsBox project --
  there's no "sync to PartsBox now" action for a Search-only working
  BOM yet. If you need PartsBox entries for those parts, include them in
  an uploaded file (even a small one) so Upload's PartsBox step covers
  them.
