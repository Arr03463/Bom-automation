import pandas as pd

from main import (
    REVIEW_STATUSES,
    SOURCING_REVIEW_STATUSES,
    SUPPLIER_REVIEW_STATUSES,
    build_review_items,
)
from record_filter import coerce_int_or_none

SOURCED_STATUSES_BY_SUPPLIER = {
    "sourced_mouser": "Mouser",
    "sourced_digikey": "DigiKey",
}


def _needs_review(row):
    """
    Same criteria build_review_items() uses to decide review membership,
    applied per-row -- one definition of "needs review," reused rather
    than re-derived, so a row's result_status here always agrees with
    whether it actually shows up in review_items().
    """
    if str(row.get("status", "")).strip() in REVIEW_STATUSES:
        return True
    if str(row.get("supplier_match_status", "")).strip() in SUPPLIER_REVIEW_STATUSES:
        return True
    if str(row.get("sourcing_status", "")).strip() in SOURCING_REVIEW_STATUSES:
        return True
    return False


def _derive_source(row):
    """
    Source is which system currently holds a usable match for this row --
    distinct from result_status, which is whether that match is actually
    usable/ready. Preference order mirrors sourcing_engine's Mouser-first
    behavior; PartsBox is reported when the row was matched there,
    independent of Mouser/DigiKey sourcing (a part can exist in PartsBox
    and also be sourced externally).
    """
    selected_supplier = str(row.get("selected_supplier", "")).strip().lower()
    if selected_supplier == "mouser":
        return "Mouser"
    if selected_supplier == "digikey":
        return "DigiKey"

    if str(row.get("partsbox_match_status", "")).strip().lower() == "matched":
        return "PartsBox"

    return "None"


def _derive_result_status(row):
    """
    The UI-facing Status, kept distinct from the raw technical `status`
    column (missing_mpn, manual_review, etc.) and from `source` -- a
    Mouser row can be Ready or Error; a PartsBox row can be Ready or need
    review. The raw columns remain untouched on the row for debugging.
    """
    if str(row.get("supplier_match_status", "")).strip().lower() == "error":
        return "Error"

    if _needs_review(row):
        return "Needs Review"

    sourcing_status = str(row.get("sourcing_status", "")).strip().lower()
    if sourcing_status in SOURCED_STATUSES_BY_SUPPLIER:
        return "Ready"

    partsbox_match_status = str(row.get("partsbox_match_status", "")).strip().lower()
    if partsbox_match_status == "matched":
        return "Ready"

    if sourcing_status or partsbox_match_status:
        # A sourcing/PartsBox step ran for this row but found no match.
        return "Not Found"

    # No sourcing or PartsBox step has run for this row at all yet.
    return "Ready" if str(row.get("status", "")).strip() == "clean" else "Needs Review"


def _derive_stock(row):
    """
    Normalized display stock: results rows never have a generic `stock`
    field (only source-specific mouser_stock/digikey_stock), so a naive
    record.get("stock") lookup always misses and the Results Stock filter
    would wrongly treat every sourced row as unknown/out-of-stock. Pick
    the figure matching the row's actual source; PartsBox and unsourced
    rows have no confirmed stock number and stay None (Unknown), never 0.
    """
    source = _derive_source(row)
    if source == "Mouser":
        return coerce_int_or_none(row.get("mouser_stock"))
    if source == "DigiKey":
        return coerce_int_or_none(row.get("digikey_stock"))
    return None


def _derive_review_reason(row):
    if not _needs_review(row):
        return ""

    reasons = []
    status = str(row.get("status", "")).strip()
    if status and status != "clean":
        reasons.append(status.replace("_", " "))

    sourcing_notes = str(row.get("sourcing_notes", "")).strip()
    if sourcing_notes:
        reasons.append(sourcing_notes)

    notes = str(row.get("notes", "")).strip()
    if notes and notes not in reasons:
        reasons.append(notes)

    return "; ".join(reasons) if reasons else "Needs review"


class ActiveBomState:
    """
    The single canonical representation of a run's processed BOM.

    This wraps the same DataFrame object produced by the cleaning/sourcing/
    PartsBox steps -- it does not copy it. Review items and results views
    must be *derived* from this object on demand, not materialized once
    into a second, independently-tracked dataset that could drift out of
    sync with it.

    The eventual replacement-selection flow (Phase 3+, not built yet) must
    go through update_row() so every derived view -- review, results,
    purchasing, exports -- reflects a change the moment it is made,
    instead of some views being refreshed and others left stale.
    """

    def __init__(self, dataframe, run_id):
        self.run_id = run_id
        # Same object, not a copy. Sourcing/PartsBox steps that already
        # hold a reference to this DataFrame keep seeing every future
        # change made through update_row().
        self.dataframe = dataframe

    def row_id_for_index(self, index):
        return f"{self.run_id}:{index}"

    def index_for_row_id(self, row_id):
        prefix = f"{self.run_id}:"
        row_id = str(row_id)
        if not row_id.startswith(prefix):
            return None

        raw_index = row_id[len(prefix):]
        try:
            return int(raw_index)
        except ValueError:
            return raw_index

    def rows(self):
        """Every canonical row, as JSON-safe dicts with a stable row_id."""
        return self.to_records(self.dataframe)

    def review_items_dataframe(self):
        """
        Rows needing review, derived fresh from the canonical DataFrame via
        the existing shared build_review_items() -- reused, not
        reimplemented, so review criteria stay in one place.
        """
        return build_review_items(self.dataframe)

    def review_items(self):
        """Rows needing review, as JSON-safe dicts sharing row_id with rows()."""
        return self.to_records(self.review_items_dataframe())

    def get_row(self, row_id):
        index = self.index_for_row_id(row_id)
        if index is None or index not in self.dataframe.index:
            return None

        return next((row for row in self.rows() if row["row_id"] == row_id), None)

    def update_row(self, row_id, updates):
        """
        The one shared operation through which a row in the canonical
        state may be changed. Every derived view (rows(), review_items(),
        and anything exported from self.dataframe) reflects the change
        immediately, because they all read from this same DataFrame --
        there is no second copy to fall out of sync.
        """
        index = self.index_for_row_id(row_id)
        if index is None or index not in self.dataframe.index:
            raise KeyError(f"Unknown row_id: {row_id}")

        for column, value in updates.items():
            self.dataframe.at[index, column] = value

        return self.get_row(row_id)

    def to_records(self, dataframe):
        """
        Shared dict-conversion used for both rows() and review_items(), so
        the two transport representations are always built the same way
        from whatever DataFrame is handed in -- never two divergent
        implementations. Also the one place source/result_status/
        review_reason are derived (see module-level _derive_* functions),
        so every caller (Results Workspace, Needs Review, summary_counts)
        sees the same values instead of recomputing them separately.
        """
        if dataframe is None or dataframe.empty:
            return []

        safe_df = dataframe.where(pd.notnull(dataframe), "")
        records = []
        for index, record in safe_df.to_dict("index").items():
            record = dict(record)
            record["row_id"] = self.row_id_for_index(index)
            record["source"] = _derive_source(record)
            record["result_status"] = _derive_result_status(record)
            record["review_reason"] = _derive_review_reason(record)
            record["stock"] = _derive_stock(record)
            # needs_review is the boolean ground truth (same criteria as
            # review_items()/build_review_items()). result_status can say
            # "Error" for a row that still needs attention -- callers
            # that want a review COUNT must use this flag, not a string
            # match against result_status, so Error rows are never
            # silently dropped from that count.
            record["needs_review"] = _needs_review(record)
            records.append(record)

        return records

    def summary_counts(self):
        """
        Total/source/needs-review counts for the Results Workspace summary
        metrics -- computed once here from rows(), so the UI never
        recalculates these counts itself. needs_review here is always
        exactly len(self.review_items()), since both derive from the same
        per-row _needs_review() check.
        """
        rows = self.rows()
        counts = {
            "total_parts": len(rows),
            "partsbox": 0,
            "mouser": 0,
            "digikey": 0,
            "needs_review": 0,
        }

        source_keys = {"PartsBox": "partsbox", "Mouser": "mouser", "DigiKey": "digikey"}

        for row in rows:
            source_key = source_keys.get(row.get("source"))
            if source_key:
                counts[source_key] += 1
            if row.get("needs_review"):
                counts["needs_review"] += 1

        return counts
