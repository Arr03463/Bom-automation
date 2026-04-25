from nexar_client import NexarClient


def main():
    client = NexarClient()

    test_mpn = input("Enter a test MPN: ").strip()
    result = client.search_part_by_mpn(test_mpn)

    print("\nRaw Nexar result:")
    print(result)


if __name__ == "__main__":
    main()