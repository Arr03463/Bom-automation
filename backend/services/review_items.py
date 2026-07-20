REVIEW_STATUSES = {
    "missing_mpn",
    "missing_manufacturer",
    "qty_mismatch",
    "manual_review",
}

SUPPLIER_REVIEW_STATUSES = {
    "error",
    "no_offer",
    "shortage",
    "skipped",
}

SOURCING_REVIEW_STATUSES = {
    "check_wall_inventory",
    "manual_review",
}


def build_review_items(clean_bom):
    review_mask = clean_bom["status"].isin(REVIEW_STATUSES)

    if "supplier_match_status" in clean_bom.columns:
        review_mask = review_mask | clean_bom["supplier_match_status"].isin(
            SUPPLIER_REVIEW_STATUSES
        )

    if "sourcing_status" in clean_bom.columns:
        review_mask = review_mask | clean_bom["sourcing_status"].isin(
            SOURCING_REVIEW_STATUSES
        )

    return clean_bom[review_mask].copy()
