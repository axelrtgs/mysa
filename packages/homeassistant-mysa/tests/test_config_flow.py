"""Setting the account up, signing in again, and changing what is included."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pymysa import AuthenticationError, Home, TransportError
from pymysa.auth import Tokens

from custom_components.mysa.const import (
    CONF_HOMES,
    CONF_REFRESH_TOKEN,
    CONF_STORE_PASSWORD,
    DOMAIN,
)

from .conftest import BB_V1, HOME_ID, SECOND_HOME, entry_for, load, setup_account

CREDENTIALS = {CONF_USERNAME: "jamie@example.com", CONF_PASSWORD: "hunter2"}
TOKENS = Tokens("id-token", "access-token", "refresh-token", 9_999_999_999.0)

ONE_HOME = {HOME_ID: Home(HOME_ID, "Home", 0.0616, {})}
TWO_HOMES = {**ONE_HOME, SECOND_HOME: Home(SECOND_HOME, "The Cabin", None, {})}


@contextmanager
def signed_in(
    homes: dict[str, Home] | None = None, failure: Exception | None = None
) -> Iterator[MagicMock]:
    """The SRP login and the one request that lists homes (spec 09)."""
    auth = MagicMock()
    auth.login = AsyncMock(return_value=TOKENS, side_effect=failure)
    account = MagicMock()
    account.list_homes = AsyncMock(return_value=homes if homes is not None else ONE_HOME)
    with (
        patch("custom_components.mysa.config_flow.MysaAuth", return_value=auth),
        patch("custom_components.mysa.config_flow.MysaAccount", return_value=account),
        patch("custom_components.mysa.async_setup_entry", return_value=True),
    ):
        yield auth


async def _start(hass: HomeAssistant, **extra: Any) -> dict[str, Any]:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CREDENTIALS, **extra}
    )


async def test_one_home_is_not_a_question(hass: HomeAssistant) -> None:
    with signed_in():
        result = await _start(hass)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "jamie@example.com"
    assert result["data"] == {
        CONF_USERNAME: "jamie@example.com",
        CONF_REFRESH_TOKEN: "refresh-token",
    }
    assert result["options"] == {CONF_HOMES: [HOME_ID], CONF_SCAN_INTERVAL: 60}


async def test_the_password_is_kept_only_when_it_is_asked_for(
    hass: HomeAssistant,
) -> None:
    with signed_in():
        kept = await _start(hass, **{CONF_STORE_PASSWORD: True})

    assert kept["data"][CONF_PASSWORD] == "hunter2"


async def test_more_than_one_home_is_asked_about_before_anything_is_discovered(
    hass: HomeAssistant,
) -> None:
    with signed_in(TWO_HOMES):
        asked = await _start(hass)
        assert asked["type"] is FlowResultType.FORM
        assert asked["step_id"] == "homes"

        result = await hass.config_entries.flow.async_configure(
            asked["flow_id"], {CONF_HOMES: [SECOND_HOME]}
        )

    assert result["options"][CONF_HOMES] == [SECOND_HOME]


async def test_a_rejected_password_can_be_corrected(hass: HomeAssistant) -> None:
    with signed_in(failure=AuthenticationError("Incorrect username or password")):
        rejected = await _start(hass)
    assert rejected["type"] is FlowResultType.FORM
    assert rejected["errors"] == {"base": "invalid_auth"}

    with signed_in():
        result = await hass.config_entries.flow.async_configure(
            rejected["flow_id"], CREDENTIALS
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_an_unreachable_backend_is_not_a_rejected_password(
    hass: HomeAssistant,
) -> None:
    with signed_in(failure=TransportError("/homes request failed")):
        result = await _start(hass)

    assert result["errors"] == {"base": "cannot_connect"}


async def test_an_account_cannot_be_set_up_twice(hass: HomeAssistant) -> None:
    entry_for().add_to_hass(hass)

    with signed_in():
        result = await _start(hass)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_a_stored_password_signs_in_again_without_asking(
    hass: HomeAssistant,
) -> None:
    entry = entry_for(password="hunter2")
    entry.add_to_hass(hass)

    with signed_in() as auth:
        result = await entry.start_reauth_flow(hass)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert auth.login.await_count == 1
    assert entry.data[CONF_REFRESH_TOKEN] == "refresh-token"
    assert entry.data[CONF_PASSWORD] == "hunter2"


async def test_without_a_stored_password_reauthentication_asks_for_one(
    hass: HomeAssistant,
) -> None:
    entry = entry_for()
    entry.add_to_hass(hass)

    with signed_in():
        asked = await entry.start_reauth_flow(hass)
        assert asked["step_id"] == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(
            asked["flow_id"], {CONF_PASSWORD: "hunter2"}
        )

    assert result["reason"] == "reauth_successful"
    assert CONF_PASSWORD not in entry.data


async def test_changing_the_homes_rediscovers(hass: HomeAssistant) -> None:
    """Devices in a home that is no longer chosen go away (spec 06)."""
    setup = await setup_account(hass, [load(BB_V1)])

    result = await hass.config_entries.options.async_init(setup.entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_HOMES: [SECOND_HOME], CONF_SCAN_INTERVAL: 120}
    )
    await hass.async_block_till_done()

    assert setup.entry.options == {CONF_HOMES: [SECOND_HOME], CONF_SCAN_INTERVAL: 120}
    assert setup.account.devices == {}
    assert not hass.states.async_entity_ids("climate")


async def test_the_polling_interval_is_what_the_options_say(hass: HomeAssistant) -> None:
    setup = await setup_account(hass, [load(BB_V1)])

    result = await hass.config_entries.options.async_init(setup.entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_HOMES: [HOME_ID], CONF_SCAN_INTERVAL: 300}
    )
    await hass.async_block_till_done()

    assert setup.entry.runtime_data.update_interval.total_seconds() == 300
