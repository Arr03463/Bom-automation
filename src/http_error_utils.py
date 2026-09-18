SAFE_MESSAGE_FIELDS = (
    "error",
    "error_description",
    "message",
    "Message",
    "ErrorMessage",
    "ErrorDetails",
    "detail",
)

SAFE_REQUEST_ID_FIELDS = (
    "RequestId",
    "requestId",
    "request_id",
    "correlationId",
    "correlation_id",
)


def describe_error_response(response, max_length=300):
    """
    A short, safe-to-print description of an HTTP error response: the
    status code plus known-safe fields pulled from a JSON body (an
    allow-list of error/message/request-id style keys only).

    Deliberately never includes the raw response body. Several of this
    codebase's clients pass API keys as URL query parameters (e.g. Mouser's
    Cart API); some vendor error responses echo back request details, so
    printing response.text verbatim on failure can leak a secret to the
    console/logs. Printing only allow-listed fields avoids that without
    guessing at redaction patterns in free-form text.
    """
    status = getattr(response, "status_code", "unknown")
    details = []

    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        for key in SAFE_MESSAGE_FIELDS:
            value = payload.get(key)
            if value:
                details.append(str(value))
                break

        for key in SAFE_REQUEST_ID_FIELDS:
            value = payload.get(key)
            if value:
                details.append(f"request id: {value}")
                break

    if not details:
        details.append("no structured error details in response")

    text = " | ".join(details)
    if len(text) > max_length:
        text = text[: max_length - 3] + "..."

    return f"HTTP {status}: {text}"
