import pandas as pd

from mouser_client import MouserClient
from digikey_client import DigiKeyClient
from sourcing_engine import apply_sourcing_decisions


def main():
    test_bom = pd.DataFrame(
    [
        {"manufacturer": "YAGEO", "mpn": "RC0603FR-0710KL", "required_qty": "80"},
        {"manufacturer": "Texas Instruments", "mpn": "NE555P", "required_qty": "10"},
        {"manufacturer": "Murata", "mpn": "GRM188R71C104KA01D", "required_qty": "50"},
    ]
)

    mouser = MouserClient()
    digikey = DigiKeyClient()

    sourced = apply_sourcing_decisions(
        test_bom,
        mouser_lookup=mouser.find_best_match_for_row,
        digikey_lookup=digikey.find_best_match,
    )

    print(sourced)


if __name__ == "__main__":
    main()