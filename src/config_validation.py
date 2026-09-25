import os

from token_store import MemoryTokenStore, build_token_store


def digikey_mylists_config_status():
    """
    Whether DigiKey MyLists automation is actually production-ready as
    configured, not just "enabled". DIGIKEY_MYLISTS_ENABLED=true with only
    an in-process MemoryTokenStore will silently degrade to needing manual
    re-authorization after every restart/redeploy -- see
    Documentation/AutoBOM_DigiKey_Durable_Token_Strategy.md. Surface that
    clearly at startup instead of letting it fail invisibly later.
    """
    enabled = os.getenv("DIGIKEY_MYLISTS_ENABLED", "false").strip().lower() == "true"
    if not enabled:
        return {"enabled": False, "durable": None, "warning": None}

    store = build_token_store()
    durable = not isinstance(store, MemoryTokenStore)

    missing_credentials = [
        name
        for name in ("DIGIKEY_CLIENT_ID", "DIGIKEY_CLIENT_SECRET")
        if not os.getenv(name, "").strip()
    ]

    warning = None
    if missing_credentials:
        warning = (
            "DIGIKEY_MYLISTS_ENABLED is true, but required credentials are "
            f"missing: {', '.join(missing_credentials)}. DigiKey MyList "
            "creation will fail until these are set."
        )
    elif not durable:
        warning = (
            "DIGIKEY_MYLISTS_ENABLED is true, but the DigiKey refresh token "
            "store is in-process only (no DIGIKEY_TOKEN_STORE=file/http "
            "configured with a durable location). The token will be lost on "
            "the next restart/redeploy, requiring manual re-authorization. "
            "See Documentation/AutoBOM_DigiKey_Durable_Token_Strategy.md "
            "before relying on this in a hosted deployment."
        )

    return {
        "enabled": True,
        "durable": durable,
        "token_store": type(store).__name__,
        "warning": warning,
    }


def mouser_cart_config_status():
    """
    Mirrors digikey_mylists_config_status() for Mouser cart automation --
    if MOUSER_CART_ENABLED is true, purchasing reflects a clean state only
    when the credentials it depends on are actually present.

    Deliberately NOT called from collect_startup_warnings() -- the
    AutoBOM Streamlit app's normal purchasing workflow doesn't use the
    Mouser Cart API at all anymore (see src/mouser_export.py); only the
    separate src/main.py CLI tool does, so a startup warning about it in
    the app would be about a feature the app never invokes. Kept here,
    tested, and still usable directly for that CLI path.
    """
    enabled = os.getenv("MOUSER_CART_ENABLED", "false").strip().lower() == "true"
    if not enabled:
        return {"enabled": False, "warning": None}

    missing = [name for name in ("MOUSER_CART_API_KEY",) if not os.getenv(name, "").strip()]
    warning = None
    if missing:
        warning = (
            "MOUSER_CART_ENABLED is true, but required credentials are "
            f"missing: {', '.join(missing)}. Mouser cart creation will fail "
            "until these are set."
        )

    return {"enabled": True, "warning": warning}


def partsbox_config_status():
    """
    PartsBox credentials are required for every PartsBox-dependent page/
    action (project lifecycle, Inventory, Component Search's PartsBox
    source). Absent credentials should fail gracefully in those features,
    not crash -- this lets app.py show one clear banner instead.
    """
    configured = bool(os.getenv("PARTSBOX_API_KEY", "").strip())
    warning = None
    if not configured:
        warning = (
            "PARTSBOX_API_KEY is not set. PartsBox project/storage creation, "
            "PartsBox Inventory, and PartsBox search will not work until it "
            "is configured."
        )

    return {"configured": configured, "warning": warning}


def collect_startup_warnings():
    """
    One shared entry point app.py calls once per page load to surface
    configuration problems as an in-app banner, instead of a feature
    failing later with a raw exception the operator has to decode.
    """
    warnings = []

    for status in (
        digikey_mylists_config_status(),
        partsbox_config_status(),
    ):
        if status.get("warning"):
            warnings.append(status["warning"])

    return warnings
