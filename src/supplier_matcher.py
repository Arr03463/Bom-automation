from nexar_client import NexarClient


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


def search_supplier_offers(mpn):
    client = NexarClient()
    result = client.search_part_by_mpn(mpn)
    return extract_offers_from_result(result)