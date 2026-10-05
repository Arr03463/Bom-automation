"""
Pure, deterministic DigiKey FastAdd cart-link builder. No vendor API
call, no DigiKey MyLists OAuth/refresh token -- this is a plain URL a
recipient opens directly in a browser to load a DigiKey cart, replacing
the normal-flow DigiKey MyList creation (see
Documentation/AutoBOM_Direct_Cart_Handoff_Change_Risk_Audit.md and
Documentation/AutoBOM_Claude_Code_Direct_Cart_Handoff_Implementation_Prompt.md).

URL format confirmed 2026-09-28 against DigiKey's own TechForum post
"DigiKey FastAdd -- Bulk add parts into a DigiKey cart via third party
tooling and URLs"
(https://forum.digikey.com/t/digikey-fastadd-bulk-add-parts-into-a-digikey-cart-via-third-party-tooling-and-urls/61356),
which gives this example URL verbatim:

    https://www.digikey.com/classic/ordering/fastadd.aspx?part1=1050-ABX00052-ND&qty1=1&cref1=cpn123&part2=1050-ABX00162-ND&qty2=1&cref2=bobs-board&utm_source=bomalizer.ai&utm_content=7za42ddr

-- 1-indexed partN/qtyN/crefN query parameters, newcart=true|false
(defaults to false/adds-to-current-cart when omitted; AutoBOM always
sends an explicit value so a recipient's existing cart is never silently
merged into), and utm_source/utm_content as the only approved tracking
fields. The same post states "the max safe character count of the URL is
around 1700 characters, more characters will cause errors" for the FINAL
encoded URL -- not the raw/unencoded field values. This is a community
TechForum post, not DigiKey's own formal API reference documentation;
treated as the best available primary source, consistent with the audit
this module implements, but not independently confirmed via a real
FastAdd request from this environment (no DigiKey account/cart access
here). Verify against a real cart load before high-volume production use
if that matters for your deployment.
"""

import urllib.parse
from dataclasses import dataclass, field

FASTADD_BASE_URL = "https://www.digikey.com/classic/ordering/fastadd.aspx"

# Named, documented safe-length constant for the FINAL percent-encoded
# URL (see module docstring for the source). A shorter constant here is
# always safe to lower further; this is the ceiling, not a target.
FASTADD_SAFE_LENGTH_CHARS = 1700

# AutoBOM's own external-tool identifier for DigiKey's utm_source field
# -- distinct per deployment if that's ever useful, but a fixed value is
# fine for now (this is operational/analytics data, not a credential).
FASTADD_UTM_SOURCE = "AutoBOM"


@dataclass(frozen=True)
class FastAddLinkResult:
    """
    Structured output for the digikey_cart_link artifact (see
    workflow_runner.py's artifact-status model). `status` is one of:
      - "current": `url` is a usable, within-limit FastAdd link.
      - "not_required": no DigiKey purchasing lines were provided.
      - "csv_fallback": the encoded URL exceeded FASTADD_SAFE_LENGTH_CHARS;
        `url` is deliberately left empty -- never expose an oversized or
        truncated link (see the change-risk audit's H6: "never truncate
        a URL or omit lines to fit the limit").
    A generation-time failure (an unexpected exception) is the caller's
    concern (see workflow_runner.regenerate_purchasing()), not a status
    this pure function returns itself.
    """

    status: str
    url: str = ""
    encoded_length: int = 0
    item_count: int = 0
    fallback_reason: str = ""
    source_row_ids: tuple = field(default_factory=tuple)


def build_digikey_fastadd_url(lines, new_cart=True, utm_content=""):
    """
    `lines` must already be validated PurchasingLine objects for
    supplier "digikey" (see purchasing_lines.build_purchasing_lines()) --
    this function does not re-validate part numbers/quantities, and by
    construction (build_purchasing_lines() rejects a blank supplier part
    number as an error, never an omission) never falls back to a
    manufacturer part number.
    """
    if not lines:
        return FastAddLinkResult(status="not_required", item_count=0)

    params = []
    source_row_ids = []
    for index, line in enumerate(lines, start=1):
        params.append((f"part{index}", line.supplier_part_number))
        params.append((f"qty{index}", str(line.quantity)))
        if line.customer_reference:
            params.append((f"cref{index}", line.customer_reference))
        source_row_ids.extend(line.source_row_ids)

    params.append(("newcart", "true" if new_cart else "false"))
    params.append(("utm_source", FASTADD_UTM_SOURCE))
    if utm_content:
        params.append(("utm_content", utm_content))

    # quote (not quote_plus): spaces become %20 rather than "+", so a
    # literal "+" in a customer reference/part number round-trips
    # unambiguously as %2B. Non-ASCII characters are percent-encoded as
    # UTF-8 bytes (urllib.parse.quote's documented default policy).
    query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    url = f"{FASTADD_BASE_URL}?{query_string}"
    encoded_length = len(url)
    item_count = len(lines)

    if encoded_length > FASTADD_SAFE_LENGTH_CHARS:
        return FastAddLinkResult(
            status="csv_fallback",
            encoded_length=encoded_length,
            item_count=item_count,
            fallback_reason=(
                f"Encoded FastAdd URL is {encoded_length} characters, over the "
                f"{FASTADD_SAFE_LENGTH_CHARS}-character safe limit for a reliable "
                "GET request. Use the DigiKey CSV instead."
            ),
            source_row_ids=tuple(source_row_ids),
        )

    return FastAddLinkResult(
        status="current",
        url=url,
        encoded_length=encoded_length,
        item_count=item_count,
        source_row_ids=tuple(source_row_ids),
    )
