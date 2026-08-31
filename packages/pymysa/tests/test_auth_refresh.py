"""Session renewal over plain HTTP.

The app client rejects USER_PASSWORD_AUTH but accepts REFRESH_TOKEN_AUTH, so a restored
session renews without pycognito or any AWS SDK.
"""

from __future__ import annotations

import json

import pytest

from pymysa.auth import MysaAuth, Tokens, tokens_from_auth_result
from pymysa.const import AMZ_JSON, COGNITO_CLIENT_ID, INITIATE_AUTH_TARGET
from pymysa.exceptions import AuthenticationError

RESULT = {"IdToken": "id-2", "AccessToken": "access-2", "ExpiresIn": 3600}


class FakeResponse:
    def __init__(self, status: int, payload: dict) -> None:
        self.status = status
        self._payload = payload

    async def json(self, content_type=None):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class FakeSession:
    def __init__(self, status: int, payload: dict) -> None:
        self.status = status
        self.payload = payload
        self.calls: list[tuple[str, dict, dict]] = []

    def post(self, url, data=None, headers=None):
        self.calls.append((url, json.loads(data), headers))
        return FakeResponse(self.status, self.payload)


def _restored(session: FakeSession) -> MysaAuth:
    auth = MysaAuth("someone@example.com", session=session)
    auth.restore(Tokens("id-1", "access-1", "refresh-1", expires_at=0.0))
    return auth


async def test_a_stale_session_renews_over_http():
    session = FakeSession(200, {"AuthenticationResult": RESULT})
    auth = _restored(session)

    assert await auth.id_token() == "id-2"


async def test_the_request_uses_the_refresh_flow_and_amz_framing():
    session = FakeSession(200, {"AuthenticationResult": RESULT})
    await _restored(session).id_token()

    (_, body, headers) = session.calls[0]
    assert body["AuthFlow"] == "REFRESH_TOKEN_AUTH"
    assert body["ClientId"] == COGNITO_CLIENT_ID
    assert body["AuthParameters"] == {"REFRESH_TOKEN": "refresh-1"}
    assert headers["X-Amz-Target"] == INITIATE_AUTH_TARGET
    assert headers["Content-Type"] == AMZ_JSON


async def test_the_existing_refresh_token_survives_a_renewal():
    """Cognito returns no RefreshToken on a refresh; losing it would force a re-login."""
    session = FakeSession(200, {"AuthenticationResult": RESULT})
    auth = _restored(session)

    await auth.id_token()

    assert auth.tokens is not None
    assert auth.tokens.refresh_token == "refresh-1"


async def test_a_rejected_refresh_reports_the_cognito_error():
    session = FakeSession(
        400, {"__type": "NotAuthorizedException", "message": "Invalid Refresh Token"}
    )

    with pytest.raises(AuthenticationError, match="Invalid Refresh Token"):
        await _restored(session).id_token()


async def test_a_fresh_session_is_not_renewed():
    session = FakeSession(200, {"AuthenticationResult": RESULT})
    auth = MysaAuth("someone@example.com", session=session)
    auth.restore(Tokens("id-1", "access-1", "refresh-1", expires_at=2**31))

    assert await auth.id_token() == "id-1"
    assert session.calls == []


def test_a_returned_refresh_token_replaces_the_old_one():
    tokens = tokens_from_auth_result({**RESULT, "RefreshToken": "refresh-2"}, "refresh-1")
    assert tokens.refresh_token == "refresh-2"


async def test_a_borrowed_session_is_not_closed():
    session = FakeSession(200, {"AuthenticationResult": RESULT})
    auth = MysaAuth("someone@example.com", session=session)

    await auth.aclose()

    assert auth._session is session
