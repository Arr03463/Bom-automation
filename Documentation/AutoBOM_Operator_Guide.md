# AutoBOM Operator Guide

Audience: a teammate using AutoBOM day-to-day, not the developer.

## Navigation

The sidebar has exactly two top-level destinations:

- **AutoBOM** -- one continuous parts sourcer, not a set of separate
  pages/tabs and not "Search mode" vs. "Upload mode". Add parts at the
  top (via Search or Upload -- see below), then scroll down through
  Configuration (with Customer Reference), the working BOM/results, and
  Purchasing Handoff -- all on the same page, all reading/writing the
  same working BOM. You never navigate away and lose your place.
- **PartsBox Inventory** -- a separate area for browsing/searching the
  full PartsBox catalog independent of any specific BOM run (see below).

## Add Parts

Search and Upload are not two different workflows -- they're two ways
to put parts into the same working BOM. Use either one, or both, in any
order:

- **Search** (the default/primary way) -- reuses the same search engine
  used everywhere else in AutoBOM. Enter a quantity next to a result and
  click **Add to BOM** to add that one line. Nothing is added
  automatically just by searching. If you haven't uploaded anything
  yet, adding your first part this way starts your working BOM.
- **Upload** (the secondary option, beside Search) -- upload a BOM as
  CSV or XLSX and click **Process Upload**. Build quantity, project
  name/description, and PartsBox behavior all come from the shared
  **Configuration** section below, not from Upload itself.
  - If you haven't added anything yet, this becomes your working BOM.
  - If you already have a working BOM (from Search, or an earlier
    upload), this **merges** the new file's lines into it instead of
    replacing what's already there -- nothing you've already added or
    configured is discarded.

**Sources** (next to Search: PartsBox / Mouser / DigiKey) determine
which databases/suppliers AutoBOM consults -- for that search, *and*
for sourcing the whole working BOM, uploaded parts included. All three
are on by default so an upload gets fully sourced without an extra
step; uncheck Mouser/DigiKey here first if you just want a quick
PartsBox-only search.

Both intake methods feed the exact same working BOM: quantity handling,
PartsBox matching, supplier sourcing, Customer Reference, Needs Review,
and purchasing all treat a part the same way regardless of whether it
was searched-and-added or came from an uploaded file.

Adding parts here never creates a live vendor cart or list at Mouser or
DigiKey -- see Purchasing Handoff below for the DigiKey cart link and
supplier CSVs, which are the only outputs of this normal flow.

## Configuration

Always visible below Add Parts -- one shared configuration for the
whole parts-sourcing job, not separate Upload settings:

- **Build quantity** -- used when processing a new upload. Once you have
  a working BOM, click **Apply Build Quantity to Uploaded Lines** to
  recompute required quantities for lines that came from an uploaded
  file (quantity × build quantity). Lines added manually via Search have
  their required quantity set directly when added, so this never
  changes them.
- **Project Name** / **Project Description** -- used for the PartsBox
  project when Upload processes a file.
- **Update PartsBox Project** -- creates/reuses the PartsBox project and
  same-name storage (tagged `production`) and adds matched BOM entries
  when you process an upload. This is distinct from the PartsBox
  checkbox under Sources, which only *searches* PartsBox and never
  writes -- parts added via Search alone are not synced to PartsBox (see
  "What NOT to do" below).
- **Customer Reference** -- see below. It's part of configuring the BOM,
  not a separate purchasing-only step.

### Customer Reference

Sets the Customer Reference / Customer Part Number that flows into the
Mouser CSV, the DigiKey cart link and CSV, and export files for every
BOM line. Three ways to generate one, all from Yank's approved naming
convention:

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

Below Configuration:

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

AutoBOM never creates a live Mouser cart or DigiKey MyList as part of
this normal flow. Instead: DigiKey gets a direct cart-loading link you
(or purchasing) open in a browser, plus a supplier-import CSV as a
fallback; Mouser gets a supplier-import CSV. Nothing here requires you
to leave AutoBOM, generate a key/token, and come back to paste it in.

1. Purchasing status reflects the **current** BOM state:
   - **Ready for Handoff**: every supplier that actually has items (a
     supplier with zero items is skipped entirely) has its required
     artifact current -- DigiKey needs its CSV current AND its cart link
     either current or validly falling back to CSV-only (see the
     CSV Fallback note below); Mouser needs its CSV current. Nothing
     needs review.
   - **Stale — BOM Changed**: a Needs Review action (or build quantity/
     Customer Reference/DNP change) affected purchasing data since
     artifacts were generated -- regenerate before handing off.
   - **Needs Review**: resolve remaining Needs Review items first.
   - **Generation Failed** / **Partial — Generation Failed**: a required
     supplier CSV or the DigiKey cart link could not be generated --
     often because a sourced row is missing its supplier part number or
     has an invalid quantity. See the error(s) shown; fix the
     underlying row (Retry Exact / Find Replacement) and regenerate.
2. Click **Regenerate Purchasing** to (re)create everything from the
   current BOM. This makes **zero** live vendor calls -- both supplier
   CSVs and the DigiKey cart link are a local file write and a plain URL
   calculation respectively. Uploading, configuring, searching, changing
   Customer Reference, filtering, or just leaving the page open never
   triggers it either way; it only ever runs on this explicit click.
3. **Mouser**: click **Download Mouser CSV** and upload that file to
   Mouser's BOM Tool to source/order the Mouser-selected parts. AutoBOM
   does not create a Mouser cart as part of this normal flow.
4. **DigiKey**:
   - **Open DigiKey Cart** loads a DigiKey shopping cart directly,
     pre-filled with the DigiKey-sourced parts, quantities, and Customer
     References -- no DigiKey account action or sign-in from AutoBOM.
     The same link is also shown as plain text you can copy and send to
     someone else.
   - **CSV Fallback**: when the cart link would be too long to load
     reliably (a very large DigiKey line count), AutoBOM shows an
     explanation and only offers **Download DigiKey CSV** instead -- no
     Open/Copy control in that state. This is expected behavior for a
     large BOM, not an error.
   - **Download DigiKey CSV** is always available alongside the link
     too, as a fallback or for uploading via DigiKey's own bulk-order
     tooling.

AutoBOM's role ends at handoff either way: checkout, payment, and order
submission always happen manually, outside AutoBOM.

## Downloads (Purchasing Handoff)

Each output file (cleaned CSV, cleaned workbook, sourcing report, DigiKey
CSV, Mouser CSV, PartsBox import/unmatched CSVs, run summary) tracks its
own freshness. A file is disabled for download when it's stale (the BOM
changed since it was generated) or when its last generation attempt
failed -- **other files being current does not re-enable it**. The
cleaned workbook regenerates along with everything else on Regenerate
Purchasing, though its Column Mapping/Warnings sheets come back empty
after any edit (they describe the original upload's raw-to-clean
transformation, which no longer applies once the BOM has changed). The
PartsBox unmatched CSV is the one file never automatically regenerated
after a BOM change; upload the BOM again (as a fresh working BOM, or
merged into the current one) if you need a current copy of it.

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
processing an uploaded BOM file with **Update PartsBox Project** checked
(creating/reusing the project and storage location, and syncing BOM
entries into it -- see Configuration above). Those writes only happen
from an explicit **Process Upload** click, never from viewing this
page, and never from adding parts via Search alone.

## What NOT to do

- Don't treat a disabled download as a bug -- it means that specific file
  doesn't match the current BOM; regenerate or re-run instead.
- Don't manually edit files under `runs/` -- they're per-run scratch
  space and may be cleaned up automatically (see the deployment guide's
  retention policy).
- Don't paste a Mouser or DigiKey secret/token into any AutoBOM field --
  none of AutoBOM's own UI ever asks for one.
- Don't assume a very long DigiKey cart link means something went wrong
  if it falls back to CSV-only -- that's the documented, deliberate
  behavior for a BOM with a large DigiKey line count.
- Parts added via Search alone aren't synced to a PartsBox project --
  there's no "sync to PartsBox now" action for a Search-only working
  BOM yet. If you need PartsBox entries for those parts, include them in
  an uploaded file (even a small one) so Upload's PartsBox step covers
  them.
