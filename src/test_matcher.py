from supplier_matcher import search_supplier_offers


def main():
    mpn = input("Enter MPN to search: ").strip()
    offers = search_supplier_offers(mpn)

    print(f"\nFound {len(offers)} offers\n")
    for offer in offers[:10]:
        print(offer)


if __name__ == "__main__":
    main()