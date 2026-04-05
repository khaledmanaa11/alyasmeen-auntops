"""Mock WhatsApp sender for local development — prints messages to console instead of calling Meta API. Used when USE_MOCK_WHATSAPP=1."""


def send_text(to: str, text: str) -> dict:
    """Print a text message to console instead of sending via Meta API (mock).

    Args:
        to:   Recipient phone number.
        text: Message body.

    Returns:
        Dict with dev=True, to, and text keys.
    """
    msg = {"dev": True, "to": to, "text": text}
    print("\nreply\n-----")
    print(msg)
    return msg

def send_document_bytes(to: str, pdf_bytes: bytes, filename: str, caption: str | None = None) -> dict:
    """Print document info to console instead of uploading and sending via Meta API (mock).

    Args:
        to:        Recipient phone number.
        pdf_bytes: Raw PDF content.
        filename:  Name of the PDF file.
        caption:   Optional message caption.

    Returns:
        Dict with dev=True, to, filename, and size_bytes keys.
    """
    print(f"\n[DEV] would send invoice PDF to {to}: {filename} ({len(pdf_bytes)} bytes)")
    payload: dict = {"dev": True, "to": to, "filename": filename, "size_bytes": len(pdf_bytes)}
    if caption:
        payload["caption"] = caption
    print(payload)
    return payload


def send_document(to: str, url: str, filename: str, caption: str | None = None) -> dict:
    """Print document link to console instead of sending via Meta API (mock).

    Args:
        to:       Recipient phone number.
        url:      Publicly accessible document URL.
        filename: Name of the document file.
        caption:  Optional message caption.

    Returns:
        Dict with dev=True, to, document_link, and filename keys.
    """
    print("\nreply\n-----")
    payload = {"dev": True, "to": to, "document_link": url, "filename": filename}
    if caption:
        payload["caption"] = caption
    print(payload)
    return payload

def send_buttons(to: str, body: str, buttons: list[dict]) -> dict:
    """Mock interactive button message — prints to console and returns dict with buttons list.

    Args:
        to:      Recipient phone number.
        body:    Message body text shown above the buttons.
        buttons: List of {"id": str, "title": str} dicts (max 3).

    Returns:
        Dict with dev=True, to, text, and buttons keys.
    """
    msg = {"dev": True, "to": to, "text": body, "buttons": buttons}
    print("\nreply (buttons)\n---------------")
    print(f"body: {body}")
    for b in buttons:
        print(f"  [{b['title']}]  id={b['id']}")
    return msg


def verify_get(params: dict) -> tuple[bool,int,str]:
    """Accept any webhook verification request in dev mode and echo the challenge.

    Args:
        params: Query parameters from the Meta webhook GET request.

    Returns:
        Tuple of (True, 200, challenge_string) for all requests.
    """
    # For dev, accept any verification and echo challenge
    return True, 200, params.get("hub.challenge", "")
