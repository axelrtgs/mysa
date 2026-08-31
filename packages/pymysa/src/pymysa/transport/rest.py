"""REST client. See docs/specs/01-transport-and-auth.md."""

from __future__ import annotations

from typing import Any

import aiohttp

from ..auth import MysaAuth
from ..const import API_BASE_URL, CLIENT_HEADERS, LEGACY_BASE_URL
from ..exceptions import AuthenticationError, TransportError


class MysaRest:
    def __init__(self, auth: MysaAuth, session: aiohttp.ClientSession) -> None:
        self._auth = auth
        self._session = session

    async def get_devices(self) -> dict[str, Any]:
        return await self._get("/devices")

    async def get_device_states(self) -> dict[str, Any]:
        return await self._get("/devices/state")

    async def get_firmwares(self) -> dict[str, Any]:
        return await self._get("/devices/firmware", base=LEGACY_BASE_URL)

    async def get_homes(self) -> dict[str, Any]:
        return await self._get("/homes")

    async def get_state_batch(self, device_ids: list[str]) -> dict[str, Any]:
        """Per-device telemetry, keyed by device id.

        Carries `latestTelemetry.reading` alongside the shadow sections that hold the
        values in force.
        """
        return await self._post("/state/batch", {"deviceIds": device_ids})

    async def get_users(self) -> dict[str, Any]:
        return await self._get("/users")

    async def get_home(self, home_id: str) -> dict[str, Any]:
        """A single home. `/homes` may summarise where this does not."""
        return await self._get(f"/homes/{home_id}")

    async def get_schedules(self) -> dict[str, Any]:
        """Schedule definitions. The state document carries only whether one is held."""
        return await self._get("/schedules")

    async def get_update_available(self, device_id: str) -> dict[str, Any]:
        return await self._get(f"/devices/update_available/{device_id}")

    async def get_capabilities(self, device_id: str) -> dict[str, Any]:
        return await self._get(f"/capabilities/{device_id}")

    async def update_state(
        self, device_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Write one shadow section. See pymysa.writes for the payload shapes."""
        return await self._post(f"/state/{device_id}/update", payload)

    async def _get(self, path: str, base: str = API_BASE_URL) -> dict[str, Any]:
        return await self._request("GET", path, None, base)

    async def _post(
        self, path: str, payload: dict[str, Any], base: str = API_BASE_URL
    ) -> dict[str, Any]:
        return await self._request("POST", path, payload, base)

    async def _request(
        self, method: str, path: str, payload: dict[str, Any] | None, base: str
    ) -> dict[str, Any]:
        token = await self._auth.id_token()
        url = f"{base}{path}"
        headers = {**CLIENT_HEADERS, "authorization": token}
        try:
            async with self._session.request(
                method, url, headers=headers, json=payload
            ) as response:
                if response.status in (401, 403):
                    raise AuthenticationError(f"{path} rejected the session token")
                if response.status >= 400:
                    body = await response.text()
                    raise TransportError(f"{path} returned {response.status}: {body[:200]}")
                data: dict[str, Any] = await response.json()
                return data
        except aiohttp.ClientError as err:
            raise TransportError(f"{path} request failed: {err}") from err
