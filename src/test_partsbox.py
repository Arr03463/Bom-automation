from partsbox_client import PartsBoxClient


def main():
    client = PartsBoxClient()

    print("Testing PartsBox API connection...")

    projects = client.list_projects()
    storage_locations = client.list_storage_locations()

    project_count = len(projects.get("data", []))
    storage_count = len(storage_locations.get("data", []))

    print(f"Connected to PartsBox.")
    print(f"Projects found: {project_count}")
    print(f"Storage locations found: {storage_count}")


if __name__ == "__main__":
    main()