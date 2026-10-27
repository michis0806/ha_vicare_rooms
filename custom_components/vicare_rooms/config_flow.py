"""Own OAuth sign-in, gateway selection and room-name options."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from functools import partial
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_entry_oauth2_flow

from .api import ViCareRoomsApi
from .const import (
    CONF_GATEWAY_SERIAL,
    CONF_INSTALLATION_ID,
    CONF_KNOWN_ROOMS,
    CONF_ROOMCONTROL_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class ViCareRoomsConfigFlow(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Authenticate before discovering or selecting a gateway."""

    DOMAIN = DOMAIN
    VERSION = 2

    def __init__(self) -> None:
        super().__init__()
        self._candidates: list[dict[str, Any]] = []
        self._oauth_data: dict[str, Any] = {}

    @property
    def logger(self) -> logging.Logger:
        return _LOGGER

    async def async_oauth_create_entry(self, data: dict) -> ConfigFlowResult:
        """Verify API access after the authorization-code exchange."""
        self._oauth_data = data
        api = ViCareRoomsApi(
            partial(
                config_entry_oauth2_flow.async_oauth2_request, self.hass, data["token"]
            )
        )
        try:
            self._candidates = await api.async_discover_roomcontrols()
        except ConfigEntryAuthFailed:
            return self.async_abort(reason="invalid_auth")
        except (aiohttp.ClientError, TimeoutError, ValueError):
            return self.async_abort(reason="cannot_connect")

        if self.source == SOURCE_REAUTH:
            entry = self._get_reauth_entry()
            if gateway := entry.data.get(CONF_GATEWAY_SERIAL):
                candidate = next(
                    (c for c in self._candidates if c[CONF_GATEWAY_SERIAL] == gateway),
                    None,
                )
                if candidate is None:
                    return self.async_abort(reason="wrong_account")
                return await self._create(candidate)
        if not self._candidates:
            return self.async_abort(reason="no_roomcontrol")
        return await self.async_step_gateway()

    async def _create(self, candidate: dict[str, Any]) -> ConfigFlowResult:
        gateway = candidate[CONF_GATEWAY_SERIAL]
        data = self._oauth_data | {
            CONF_INSTALLATION_ID: candidate[CONF_INSTALLATION_ID],
            CONF_GATEWAY_SERIAL: gateway,
            CONF_ROOMCONTROL_ID: candidate[CONF_ROOMCONTROL_ID],
        }
        await self.async_set_unique_id(gateway)
        if self.source == SOURCE_REAUTH:
            entry = self._get_reauth_entry()
            return self.async_update_reload_and_abort(
                entry,
                unique_id=gateway,
                data={**entry.data, **data},
            )
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="ViCare Rooms", data=data)

    async def async_step_gateway(self, user_input=None) -> ConfigFlowResult:
        """Select a gateway after OAuth; keep gateway-based unique IDs."""
        if user_input is not None:
            candidate = next(
                c
                for c in self._candidates
                if c[CONF_GATEWAY_SERIAL] == user_input["gateway"]
            )
            return await self._create(candidate)
        if len(self._candidates) == 1:
            return await self._create(self._candidates[0])
        options = {
            c[CONF_GATEWAY_SERIAL]: f"{c['title']} ({c[CONF_GATEWAY_SERIAL]})"
            for c in self._candidates
        }
        return self.async_show_form(
            step_id="gateway",
            data_schema=vol.Schema({vol.Required("gateway"): vol.In(options)}),
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Migrate legacy entries or renew a revoked authorization in place."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        if implementation := self._get_reauth_entry().data.get("auth_implementation"):
            return await self.async_step_pick_implementation(
                {"implementation": implementation}
            )
        return await self.async_step_user()

    async def async_step_import(self, import_data) -> ConfigFlowResult:
        """An interactive OAuth login cannot be imported from YAML."""
        return self.async_abort(reason="setup_required")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> ViCareRoomsOptionsFlow:
        return ViCareRoomsOptionsFlow()


class ViCareRoomsOptionsFlow(OptionsFlow):
    """Raumnamen pflegen (die API liefert Namen nur mit bezahltem API-Paket)."""

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            names = {
                key: value.strip()
                for key, value in user_input.items()
                if isinstance(value, str) and value.strip()
            }
            return self.async_create_entry(data=names)

        entry = self.config_entry
        coordinator = getattr(entry, "runtime_data", None)
        rooms = sorted(
            set(entry.data.get(CONF_KNOWN_ROOMS) or [])
            | set((coordinator.data or {}) if coordinator else {})
        )
        schema: dict[Any, Any] = {}
        for idx in rooms:
            current = entry.options.get(f"room_{idx}", "")
            if not current and coordinator:
                current = coordinator.api_room_names.get(idx, "")
            schema[
                vol.Optional(f"room_{idx}", description={"suggested_value": current})
            ] = str
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))
