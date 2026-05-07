import pandas as pd

from mouser_client import MouserClient
from digikey_client import DigiKeyClient
from sourcing_engine import apply_sourcing_decisions


def main():
    test_bom = pd.DataFrame(
        [
            {"manufacturer": "Mock", "mpn": "ABC123", "required_qty": "80"},
            {"manufacturer": "Mock", "mpn": "XYZ789", "required_qty": "80"},
            {"manufacturer": "Mock", "mpn": "NO_STOCK", "required_qty": "10"},
        ]
    )

    mouser = MouserClient()
    digikey = DigiKeyClient()

    sourced = apply_sourcing_decisions(
        test_bom,
        mouser_lookup=mouser.find_best_match,
        digikey_lookup=digikey.find_best_match,
    )

    print(sourced)


if __name__ == "__main__":
    main()