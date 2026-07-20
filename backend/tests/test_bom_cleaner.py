"""BOM cleaner ported from POC — exercised against the real versioned test BOMs."""

from pathlib import Path

import pytest

from services import bom_cleaner

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_BOMS = [REPO_ROOT / "poc" / "input" / "test_bom.csv",
             REPO_ROOT / "poc" / "input" / "test_bom2.csv"]


@pytest.mark.parametrize("path", TEST_BOMS, ids=lambda p: p.name)
def test_process_bom_file_produces_standard_schema(path):
    if not path.exists():
        pytest.skip(f"{path.name} not present")
    result = bom_cleaner.process_bom_file(str(path))
    df = result.clean_bom
    assert len(df) > 0
    # Standard schema columns present (from bom_cleaner.STANDARD_COLUMNS).
    for col in ("mpn", "manufacturer", "qty_per_board", "designators"):
        assert col in df.columns


def test_apply_project_quantities_sets_required_qty():
    path = TEST_BOMS[0]
    if not path.exists():
        pytest.skip("test_bom.csv not present")
    result = bom_cleaner.process_bom_file(str(path))
    df = bom_cleaner.apply_project_quantities(result.clean_bom, build_quantity=10)
    assert "required_qty" in df.columns
    assert (df["build_quantity"] == 10).all()
    # required_qty = qty_per_board * build_quantity for rows with a numeric qty.
    for _, row in df.iterrows():
        try:
            qpb = float(row["qty_per_board"])
        except (ValueError, TypeError):
            continue
        assert float(row["required_qty"]) == qpb * 10
