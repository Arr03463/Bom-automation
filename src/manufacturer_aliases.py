import re


MANUFACTURER_ALIASES = {
    # AVX / Kyocera
    "avx": "kyocera avx",
    "kyocera avx": "kyocera avx",
    "kyocera avx components": "kyocera avx",

    # STMicroelectronics
    "st": "stmicroelectronics",
    "stmicroelectronics": "stmicroelectronics",
    "st microelectronics": "stmicroelectronics",
    "stmicro": "stmicroelectronics",

    # Texas Instruments
    "ti": "texas instruments",
    "texas instruments": "texas instruments",
    "texas instruments inc": "texas instruments",
    "texas instruments incorporated": "texas instruments",

    # Murata
    "murata": "murata",
    "murata electronics": "murata",
    "murata electronics north america": "murata",

    # Yageo
    "yageo": "yageo",
    "yageo group": "yageo",

    # Analog Devices
    "adi": "analog devices",
    "analog devices": "analog devices",
    "analog devices inc": "analog devices",
    "analog devices incorporated": "analog devices",

    # Microchip
    "microchip": "microchip technology",
    "microchip tech": "microchip technology",
    "microchip technology": "microchip technology",
    "microchip technology inc": "microchip technology",
    "atmel": "microchip technology",

    # NXP
    "nxp": "nxp semiconductors",
    "nxp semiconductors": "nxp semiconductors",
    "nxp usa": "nxp semiconductors",
    "freescale": "nxp semiconductors",
    "freescale semiconductor": "nxp semiconductors",

    # Infineon
    "infineon": "infineon technologies",
    "infineon technologies": "infineon technologies",
    "infineon technologies ag": "infineon technologies",
    "cypress": "infineon technologies",
    "cypress semiconductor": "infineon technologies",

    # ON Semiconductor
    "onsemi": "on semiconductor",
    "on semiconductor": "on semiconductor",
    "on semiconductor corp": "on semiconductor",
    "fairchild": "on semiconductor",
    "fairchild semiconductor": "on semiconductor",

    # Vishay
    "vishay": "vishay intertechnology",
    "vishay intertechnology": "vishay intertechnology",
    "vishay intertechnology inc": "vishay intertechnology",

    # Kemet
    "kemet": "kemet",
    "kemet electronics": "kemet",
    "kemet corporation": "kemet",

    # Samsung
    "samsung": "samsung electro-mechanics",
    "samsung electro-mechanics": "samsung electro-mechanics",
    "semco": "samsung electro-mechanics",

    # TDK
    "tdk": "tdk",
    "tdk corporation": "tdk",
    "epcos": "tdk",

    # Panasonic
    "panasonic": "panasonic",
    "panasonic electronic components": "panasonic",
    "panasonic industry": "panasonic",

    # TE Connectivity
    "te": "te connectivity",
    "te connectivity": "te connectivity",
    "tyco": "te connectivity",
    "tyco electronics": "te connectivity",

    # Molex
    "molex": "molex",
    "molex llc": "molex",

    # Samtec
    "samtec": "samtec",
    "samtec inc": "samtec",

    # Amphenol
    "amphenol": "amphenol",
    "amphenol corporation": "amphenol",

    # Hirose
    "hirose": "hirose electric",
    "hirose electric": "hirose electric",
    "hrs": "hirose electric",

    # JST
    "jst": "jst",
    "j.s.t.": "jst",
    "jst sales america": "jst",

    # Wurth
    "wurth": "wurth elektronik",
    "würth": "wurth elektronik",
    "wurth elektronik": "wurth elektronik",
    "we": "wurth elektronik",

    # Renesas
    "renesas": "renesas electronics",
    "renesas electronics": "renesas electronics",
    "intersil": "renesas electronics",

    # Maxim
    "maxim": "analog devices",
    "maxim integrated": "analog devices",
    "maxim integrated products": "analog devices",

    # Linear Technology
    "linear": "analog devices",
    "linear technology": "analog devices",
    "ltc": "analog devices",

    # Rohm
    "rohm": "rohm semiconductor",
    "rohm semiconductor": "rohm semiconductor",

    # Broadcom
    "broadcom": "broadcom",
    "broadcom inc": "broadcom",
    "avago": "broadcom",
    "avago technologies": "broadcom",

    # Littelfuse
    "littelfuse": "littelfuse",
    "littelfuse inc": "littelfuse",

    # Bourns
    "bourns": "bourns",
    "bourns inc": "bourns",

    # Omron
    "omron": "omron",
    "omron electronics": "omron",

    # Mean Well
    "meanwell": "mean well",
    "mean well": "mean well",
    "mean well enterprises": "mean well",

    # Silicon Labs
    "silabs": "silicon laboratories",
    "silicon labs": "silicon laboratories",
    "silicon laboratories": "silicon laboratories",

    # Espressif
    "espressif": "espressif systems",
    "espressif systems": "espressif systems",

    # Raspberry Pi
    "raspberry pi": "raspberry pi",
    "raspberry pi trading": "raspberry pi",

    # OmniVision
    "omnivision": "omnivision technologies",
    "omnivision technologies": "omnivision technologies",

    # Coilcraft
    "coilcraft": "coilcraft",
    "coilcraft inc": "coilcraft",

    # Eaton
    "eaton": "eaton electronics",
    "eaton electronics": "eaton electronics",

    # Bel Fuse
    "bel": "bel fuse",
    "bel fuse": "bel fuse",
    "bel fuse inc": "bel fuse",

    # Schaffner
    "schaffner": "schaffner",
    "schaffner emc": "schaffner",

    # Qualcomm
    "qualcomm": "qualcomm",
    "qualcomm technologies": "qualcomm",

    # Intel / Altera
    "intel": "intel",
    "altera": "intel",

    # Xilinx / AMD
    "xilinx": "amd",
    "advanced micro devices": "amd",
    "amd": "amd",

    # Lattice
    "lattice": "lattice semiconductor",
    "lattice semiconductor": "lattice semiconductor",
}


def normalize_part_number(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def normalize_manufacturer(value):
    text = str(value or "").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|llc)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = " ".join(text.split())
    return MANUFACTURER_ALIASES.get(text, text)


def manufacturers_equivalent(expected, actual):
    expected = normalize_manufacturer(expected)
    actual = normalize_manufacturer(actual)

    if not expected:
        return True

    return expected == actual or expected in actual or actual in expected
