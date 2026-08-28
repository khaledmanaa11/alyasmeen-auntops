"""
test_webhook_router.py — Unit tests for app/routers/whatsapp.py's POST /webhook
handler (webhook_post), called directly rather than through TestClient so the
async function can be awaited with full control over the mocked Request.
"""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request

from app.routers.whatsapp import webhook_post


@pytest.fixture
def anyio_backend():
    # The anyio pytest plugin parametrizes @pytest.mark.anyio tests over every
    # installed backend by default (asyncio *and* trio). Only anyio itself is
    # a project dependency (via starlette/fastapi) — trio is not installed,
    # so the "trio" half of that parametrization always errors with
    # ModuleNotFoundError before the test body ever runs. Pinning the backend
    # here keeps the test to the one backend this project actually has.
    return "asyncio"


def _mock_request(payload: dict) -> Request:
    request = MagicMock(spec=Request)
    request.body = AsyncMock(return_value=json.dumps(payload).encode())
    request.json = AsyncMock(return_value=payload)
    return request


@pytest.mark.anyio
async def test_webhook_persistence(monkeypatch):
    mock_payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "972591234567",
                        "id": "wamid.HBgLOTcyNTkxMzU3Nzk5NRUCABIYFEY0OEYzQTU3NzhDN0E3RUI2RQA=",
                        "text": {"body": "hello"}
                    }]
                }
            }]
        }]
    }

    request = _mock_request(mock_payload)

    import app.routers.whatsapp as wa

    # monkeypatch (not raw attribute assignment) so pytest restores the real
    # verify_signature/execute after this test even if it fails partway —
    # a bare `wa.execute = MagicMock()` used to leak into every later test
    # in the process since nothing ever put the original back.
    monkeypatch.setattr(wa, "verify_signature", MagicMock(return_value=True))
    mock_execute = MagicMock()
    monkeypatch.setattr(wa, "execute", mock_execute)

    resp = await webhook_post(request, x_hub_signature_256="sha256=fake")

    assert resp == {"status": "received"}
    mock_execute.assert_called_once()
    args, kwargs = mock_execute.call_args
    sql = args[0]
    params = args[1]

    assert "INSERT INTO webhook_events" in sql
    assert params[0] == "972591234567"
    assert params[1] == mock_payload
    assert params[2] == "wamid.HBgLOTcyNTkxMzU3Nzk5NRUCABIYFEY0OEYzQTU3NzhDN0E3RUI2RQA="


@pytest.mark.anyio
async def test_webhook_invalid_signature_returns_403(monkeypatch):
    import app.routers.whatsapp as wa
    from fastapi import HTTPException

    monkeypatch.setattr(wa, "verify_signature", MagicMock(return_value=False))
    mock_execute = MagicMock()
    monkeypatch.setattr(wa, "execute", mock_execute)

    request = _mock_request({"entry": []})

    with pytest.raises(HTTPException) as exc_info:
        await webhook_post(request, x_hub_signature_256="sha256=bad")

    assert exc_info.value.status_code == 403
    mock_execute.assert_not_called()


@pytest.mark.anyio
async def test_malformed_payload_empty_entry_persists_raw_payload_and_returns_200(monkeypatch):
    """A payload with no entry/changes must not crash the handler — it should
    still be persisted (with a fallback phone/wamid) and answered with 200 so
    Meta doesn't treat it as a delivery failure and retry forever."""
    import app.routers.whatsapp as wa

    monkeypatch.setattr(wa, "verify_signature", MagicMock(return_value=True))
    mock_execute = MagicMock()
    monkeypatch.setattr(wa, "execute", mock_execute)

    malformed_payload = {"entry": []}
    request = _mock_request(malformed_payload)

    resp = await webhook_post(request, x_hub_signature_256="sha256=fake")

    assert resp == {"status": "received"}
    mock_execute.assert_called_once()
    args, _kwargs = mock_execute.call_args
    sql, params = args[0], args[1]
    assert "INSERT INTO webhook_events" in sql
    assert params[0] == "unknown"  # no message in the payload -> fallback phone
    assert params[1] == malformed_payload  # the raw payload is still persisted
    assert params[2] is None  # no wamid available


@pytest.mark.anyio
async def test_malformed_payload_missing_entry_key_returns_200(monkeypatch):
    """Missing 'entry' entirely (not even an empty list) must be equally safe."""
    import app.routers.whatsapp as wa

    monkeypatch.setattr(wa, "verify_signature", MagicMock(return_value=True))
    mock_execute = MagicMock()
    monkeypatch.setattr(wa, "execute", mock_execute)

    request = _mock_request({})

    resp = await webhook_post(request, x_hub_signature_256="sha256=fake")

    assert resp == {"status": "received"}
    mock_execute.assert_called_once()
    args, _kwargs = mock_execute.call_args
    assert args[1][0] == "unknown"


if __name__ == "__main__":
    import asyncio

    _mp = pytest.MonkeyPatch()
    try:
        asyncio.run(test_webhook_persistence(_mp))
    finally:
        _mp.undo()
