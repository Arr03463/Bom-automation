from nexar_client import NexarClient


MATCH_COLUMNS = [
    "matched_manufacturer",
    "matched_mpn",
    "matched_supplier",
    "matched_inventory",
    "matched_price_qty",
    "matched_unit_price",
    "matched_currency",
    "supplier_match_status",
    "supplier_match_notes",
]


def extract_offers_from_result(result):
    offers = []

    results = (
        result.get("data", {})
        .get("supSearchMpn", {})
        .get("results", [])
    )

    for item in results:
        part = item.get("part", {})
        mpn = part.get("mpn", "")
        manufacturer = part.get("manufacturer", {}).get("name", "")

        for seller in part.get("sellers", []):
            seller_name = seller.get("company", {}).get("name", "")
            for offer in seller.get("offers", []):
                offers.append(
                    {
                        "manufacturer": manufacturer,
                        "mpn": mpn,
                        "seller": seller_name,
                        "inventory_level": offer.get("inventoryLevel"),
                        "prices": offer.get("prices", []),
                    }
                )

    return offers


def search_supplier_offers(mpn, client=None):
    client = client or NexarClient()
    result = client.search_part_by_mpn(mpn)
    return extract_offers_from_result(result)


def choose_best_offer(offers, required_qty=None):
    required_qty = _parse_number(required_qty)
    candidates = []

    for offer in offers:
        inventory = _parse_number(offer.get("inventory_level"))
        price_break = _best_price_break(offer.get("prices", []), required_qty)
        unit_price = _parse_number(price_break.get("price"))

        if inventory is None and unit_price is None:
            continue

        has_enough_inventory = (
            required_qty is not None
            and inventory is not None
            and inventory >= required_qty
        )

        candidates.append(
            {
                "offer": offer,
                "inventory": inventory,
                "price_break": price_break,
                "unit_price": unit_price,
                "has_enough_inventory": has_enough_inventory,
            }
        )

    if not candidates:
        return None

    if required_qty is not None:
        in_stock = [candidate for candidate in candidates if candidate["has_enough_inventory"]]
        if in_stock:
            return min(in_stock, key=_priced_offer_sort_key)

    return max(candidates, key=lambda candidate: candidate["inventory"] or 0)


def enrich_bom_with_supplier_offers(clean_bom, client=None):
    updated_bom = clean_bom.copy().astype(object)

    for column in MATCH_COLUMNS:
        if column not in updated_bom.columns:
            updated_bom[column] = ""

    client = client or NexarClient()
    offer_cache = {}

    for index, row in updated_bom.iterrows():
        mpn = _clean_text(row.get("mpn", ""))
        required_qty = row.get("required_qty", "")

        if not mpn:
            updated_bom.at[index, "supplier_match_status"] = "skipped"
            updated_bom.at[index, "supplier_match_notes"] = "skipped: missing mpn"
            continue

        try:
            if mpn not in offer_cache:
                offer_cache[mpn] = search_supplier_offers(mpn, client=client)
            offers = offer_cache[mpn]
        except Exception as exc:
            updated_bom.at[index, "supplier_match_status"] = "error"
            updated_bom.at[index, "supplier_match_notes"] = f"Nexar lookup failed: {exc}"
            continue

        best = choose_best_offer(offers, required_qty=required_qty)
        if not best:
            updated_bom.at[index, "supplier_match_status"] = "no_offer"
            updated_bom.at[index, "supplier_match_notes"] = "no supplier offer found"
            continue

        offer = best["offer"]
        price_break = best["price_break"]
        inventory = best["inventory"]
        parsed_required_qty = _parse_number(required_qty)

        updated_bom.at[index, "matched_manufacturer"] = offer.get("manufacturer", "")
        updated_bom.at[index, "matched_mpn"] = offer.get("mpn", "")
        updated_bom.at[index, "matched_supplier"] = offer.get("seller", "")
        updated_bom.at[index, "matched_inventory"] = _format_number(inventory)
        updated_bom.at[index, "matched_price_qty"] = price_break.get("quantity", "")
        updated_bom.at[index, "matched_unit_price"] = price_break.get("price", "")
        updated_bom.at[index, "matched_currency"] = price_break.get("currency", "")

        if parsed_required_qty is not None and inventory is not None and inventory < parsed_required_qty:
            updated_bom.at[index, "supplier_match_status"] = "shortage"
            updated_bom.at[index, "supplier_match_notes"] = (
                f"best offer inventory {inventory} is below required qty {parsed_required_qty}"
            )
        else:
            updated_bom.at[index, "supplier_match_status"] = "matched"
            updated_bom.at[index, "supplier_match_notes"] = "matched by mpn"

    return updated_bom


def _best_price_break(prices, required_qty=None):
    if not prices:
        return {}

    parsed_prices = []
    for price in prices:
        quantity = _parse_number(price.get("quantity"))
        unit_price = _parse_number(price.get("price"))
        if quantity is None or unit_price is None:
            continue
        parsed_prices.append((quantity, unit_price, price))

    if not parsed_prices:
        return {}

    if required_qty is not None:
        usable_breaks = [item for item in parsed_prices if item[0] <= required_qty]
        if usable_breaks:
            return max(usable_breaks, key=lambda item: item[0])[2]

    return min(parsed_prices, key=lambda item: item[0])[2]


def _priced_offer_sort_key(candidate):
    unit_price = candidate["unit_price"]
    inventory = candidate["inventory"]
    if unit_price is None:
        unit_price = float("inf")
    if inventory is None:
        inventory = 0
    return unit_price, -inventory


def _parse_number(value):
    text = _clean_text(value)
    if not text:
        return None

    try:
        number = float(text.replace(",", ""))
    except ValueError:
        return None

    return int(number) if number.is_integer() else number


def _format_number(value):
    if value is None:
        return ""
    return str(int(value)) if float(value).is_integer() else str(value)


def _clean_text(value):
    if value is None:
        return ""
    return str(value).strip()
