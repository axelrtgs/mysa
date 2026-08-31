"""Config and options flows. See docs/specs/06-ha-entities.md."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pymysa import AuthenticationError, Home, MysaAccount, MysaAuth, MysaError

from .const import (
    CONF_HOMES,
    CONF_REFRESH_TOKEN,
    CONF_STORE_PASSWORD,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .coordinator import MysaConfigEntry

_LOGGER = logging.getLogger(__name__)

CREDENTIALS = vol.Schema(
    {
        vol.Required(CONF_USERNAME): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)
        ),
        vol.Required(CONF_PASSWORD): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_STORE_PASSWORD, default=False): bool,
    }
)


def _interval_field() -> Any:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=MIN_SCAN_INTERVAL,
            max=MAX_SCAN_INTERVAL,
            step=1,
            unit_of_measurement="s",
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _homes_field(homes: Mapping[str, Home]) -> Any:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            multiple=True,
            options=[
                selector.SelectOptionDict(value=home.id, label=home.name or home.id)
                for home in homes.values()
            ],
        )
    )


class MysaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Log in once, then ask which homes to set up."""

    VERSION = 1

    def __init__(self) -> None:
        self._credentials: dict[str, Any] = {}
        self._homes: dict[str, Home] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_USERNAME].casefold())
            self._abort_if_unique_id_configured()
            errors = await self._authenticate(user_input)
            if not errors:
                return await self._continue()
        return self.async_show_form(
            step_id="user", data_schema=CREDENTIALS, errors=errors
        )

    async def async_step_homes(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Which homes to set up. An excluded device is never discovered (spec 09)."""
        if user_input is not None:
            return self._entry(user_input[CONF_HOMES])
        return self.async_show_form(
            step_id="homes",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOMES, default=list(self._homes)): _homes_field(
                        self._homes
                    )
                }
            ),
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """A session that could not be renewed.

        Where the user asked for the password to be stored, this is silent; otherwise
        it asks for it again.
        """
        password = entry_data.get(CONF_PASSWORD)
        if password is not None:
            # Storing it again: the user asked for that once and has not changed it.
            errors = await self._authenticate(
                {
                    CONF_USERNAME: entry_data[CONF_USERNAME],
                    CONF_PASSWORD: password,
                    CONF_STORE_PASSWORD: True,
                }
            )
            if not errors:
                return self._update()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._authenticate(
                {CONF_USERNAME: entry.data[CONF_USERNAME], **user_input}
            )
            if not errors:
                return self._update()
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                    vol.Optional(CONF_STORE_PASSWORD, default=False): bool,
                }
            ),
            errors=errors,
            description_placeholders={CONF_USERNAME: entry.data[CONF_USERNAME]},
        )

    async def _authenticate(self, user_input: dict[str, Any]) -> dict[str, str]:
        """Log in by SRP, keep the refresh token, and read the account's homes.

        `list_homes()` is one request and discovers nothing (spec 09), so the homes are
        known before anything has been paid for.
        """
        session = async_get_clientsession(self.hass)
        auth = MysaAuth(
            user_input[CONF_USERNAME], user_input[CONF_PASSWORD], session=session
        )
        try:
            tokens = await auth.login()
            self._homes = dict(await MysaAccount(auth, session).list_homes())
        except AuthenticationError:
            return {"base": "invalid_auth"}
        except MysaError as err:
            _LOGGER.debug("could not reach the account: %s", err)
            return {"base": "cannot_connect"}

        self._credentials = {
            CONF_USERNAME: user_input[CONF_USERNAME],
            CONF_REFRESH_TOKEN: tokens.refresh_token,
        }
        if user_input.get(CONF_STORE_PASSWORD):
            self._credentials[CONF_PASSWORD] = user_input[CONF_PASSWORD]
        return {}

    async def _continue(self) -> ConfigFlowResult:
        """One home needs no question."""
        if len(self._homes) > 1:
            return await self.async_step_homes()
        return self._entry(list(self._homes))

    def _entry(self, homes: list[str]) -> ConfigFlowResult:
        return self.async_create_entry(
            title=self._credentials[CONF_USERNAME],
            data=self._credentials,
            options={CONF_HOMES: homes, CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL},
        )

    def _update(self) -> ConfigFlowResult:
        """A fresh token for an entry that already exists.

        The stored password is replaced or removed by what was asked for this time, so
        clearing the box is how a user stops storing it.
        """
        entry = self._get_reauth_entry()
        data = {
            key: value
            for key, value in entry.data.items()
            if key not in (CONF_PASSWORD, CONF_REFRESH_TOKEN)
        }
        return self.async_update_reload_and_abort(
            entry, data={**data, **self._credentials}
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: MysaConfigEntry) -> MysaOptionsFlow:
        return MysaOptionsFlow()


class MysaOptionsFlow(OptionsFlow):
    """The homes to include, and how often to poll."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_HOMES: user_input[CONF_HOMES],
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                }
            )

        options = self.config_entry.options
        chosen = list(options.get(CONF_HOMES) or [])
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOMES, default=chosen): _homes_field(
                        self._known_homes(chosen)
                    ),
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): _interval_field(),
                }
            ),
        )

    def _known_homes(self, chosen: list[str]) -> dict[str, Home]:
        """The homes discovery read, or the stored ids where the entry is not loaded."""
        entry: MysaConfigEntry = self.config_entry
        coordinator = getattr(entry, "runtime_data", None)
        if coordinator is not None and coordinator.account.homes:
            return dict(coordinator.account.homes)
        return {home_id: Home(home_id, home_id, None, {}) for home_id in chosen}
