"""Cognito authentication.

The app client accepts SRP for login and REFRESH_TOKEN_AUTH for renewal. Login therefore
goes through pycognito, imported only at that moment and never on the running path;
renewal is a plain HTTP call, so a restored session needs no SDK at all.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import (
    AMZ_JSON,
    AWS_REGION,
    COGNITO_CLIENT_ID,
    COGNITO_IDP_URL,
    COGNITO_USER_POOL_ID,
    INITIATE_AUTH_TARGET,
)
from .exceptions import AuthenticationError

REFRESH_MARGIN_SECONDS = 300
DEFAULT_EXPIRES_IN = 3600


@dataclass(slots=True)
class Tokens:
    id_token: str
    access_token: str
    refresh_token: str
    expires_at: float

    @property
    def stale(self) -> bool:
        return time.time() >= self.expires_at - REFRESH_MARGIN_SECONDS


def tokens_from_auth_result(result: dict[str, Any], refresh_token: str) -> Tokens:
    """Build tokens from a Cognito AuthenticationResult."""
    return Tokens(
        id_token=result["IdToken"],
        access_token=result["AccessToken"],
        # Absent on a refresh; the caller's existing token stays valid.
        refresh_token=result.get("RefreshToken") or refresh_token,
        expires_at=time.time() + float(result.get("ExpiresIn", DEFAULT_EXPIRES_IN)),
    )


class MysaAuth:
    """Owns the Cognito session and the AWS credentials derived from it."""

    def __init__(
        self,
        username: str,
        password: str | None = None,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._username = username
        self._password = password
        self._tokens: Tokens | None = None
        self._lock = asyncio.Lock()
        self._session = session
        self._owns_session = session is None

    async def aclose(self) -> None:
        """Close the HTTP session, if this object created it."""
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    def _http(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    @property
    def username(self) -> str:
        return self._username

    @property
    def tokens(self) -> Tokens | None:
        """Current tokens, for callers that persist a session."""
        return self._tokens

    async def login(self) -> Tokens:
        if self._password is None:
            raise AuthenticationError("No password available for initial login")
        self._tokens = await asyncio.to_thread(self._login_blocking, self._password)
        return self._tokens

    async def id_token(self) -> str:
        async with self._lock:
            if self._tokens is None:
                await self.login()
            elif self._tokens.stale:
                self._tokens = await self._refresh(self._tokens.refresh_token)
            assert self._tokens is not None
            return self._tokens.id_token

    @classmethod
    def from_refresh_token(
        cls,
        username: str,
        refresh_token: str,
        session: aiohttp.ClientSession | None = None,
    ) -> MysaAuth:
        """Auth for a caller that kept the refresh token rather than the password.

        The tokens start expired, so the first request renews the session. Nothing about
        the SRP login is needed again and pycognito is never imported.
        """
        auth = cls(username, session=session)
        auth.restore(
            Tokens(id_token="", access_token="", refresh_token=refresh_token, expires_at=0.0)
        )
        return auth

    def restore(self, tokens: Tokens) -> None:
        """Adopt tokens persisted by a caller, avoiding a password round trip."""
        self._tokens = tokens

    async def _refresh(self, refresh_token: str) -> Tokens:
        """Renew the session over plain HTTP.

        A refresh response carries no new refresh token, so the existing one is kept.
        """
        body = {
            "AuthFlow": "REFRESH_TOKEN_AUTH",
            "ClientId": COGNITO_CLIENT_ID,
            "AuthParameters": {"REFRESH_TOKEN": refresh_token},
        }
        try:
            async with self._http().post(
                COGNITO_IDP_URL,
                data=json.dumps(body),
                headers={"Content-Type": AMZ_JSON, "X-Amz-Target": INITIATE_AUTH_TARGET},
            ) as response:
                payload = await response.json(content_type=None)
                if response.status != 200:
                    raise AuthenticationError(
                        f"Session refresh failed: "
                        f"{payload.get('__type', response.status)}: "
                        f"{payload.get('message', '')}".strip()
                    )
        except aiohttp.ClientError as err:
            raise AuthenticationError(f"Session refresh failed: {err}") from err

        return tokens_from_auth_result(payload["AuthenticationResult"], refresh_token)

    # -- blocking sections, always called through asyncio.to_thread ------------

    def _cognito(self) -> Any:
        from pycognito import Cognito

        return Cognito(
            COGNITO_USER_POOL_ID,
            COGNITO_CLIENT_ID,
            user_pool_region=AWS_REGION,
            username=self._username,
        )

    def _login_blocking(self, password: str) -> Tokens:
        from botocore.exceptions import ClientError

        user = self._cognito()
        try:
            user.authenticate(password=password)
        except ClientError as err:
            raise AuthenticationError(str(err)) from err
        return self._tokens_from(user)

    @staticmethod
    def _tokens_from(user: Any) -> Tokens:
        expires_in = getattr(user, "expires_in", None) or DEFAULT_EXPIRES_IN
        return Tokens(
            id_token=user.id_token,
            access_token=user.access_token,
            refresh_token=user.refresh_token,
            expires_at=time.time() + float(expires_in),
        )
