# BOM Automation Tool

Internal BOM automation tool for cleaning designer BOMs, creating PartsBox project setup, sourcing parts through Mouser/DigiKey, and preparing supplier carts/lists.

## Current Capabilities

- Clean messy CSV/XLSX BOM files
- Normalize columns such as manufacturer, MPN, designators, and quantity
- Calculate build quantity requirements
- Create/reuse PartsBox project and storage location
- Add BOM entries into PartsBox project
- Search Mouser first, then DigiKey fallback
- Create Mouser cart items when enabled
- Create DigiKey MyList when enabled
- Export cleaned BOM, sourcing report, review items, and run summary

## Safety Controls

This tool does not place orders or complete checkout.

Safety toggles are controlled in `.env`:

- `PARTSBOX_DRY_RUN`
- `SUPPLIER_DRY_RUN`
- `MOUSER_CART_DRY_RUN`
- `MOUSER_CART_ENABLED`
- `DIGIKEY_MYLISTS_ENABLED`

## Setup

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt