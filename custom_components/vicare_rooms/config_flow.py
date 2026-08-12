"""Config- und Options-Flow für ViCare Raumwerte."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from . import async_discover_roomcontrols, get_vicare_token
from .const import (
    CONF_GATEWAY_SERIAL,
    CONF_INSTALLATION_ID,
    CONF_KNOWN_ROOMS,
    CONF_ROOMCONTROL_ID,
    DOMAIN,
)


class ViCareRoomsConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._candidates: list[dict[str, Any]] = []

    async def _discover(self) -> ConfigFlowResult | None:
        token = get_vicare_token(self.hass)
        if not token:
            return self.async_abort(reason="vicare_missing")
        try:
            self._candidates = await async_discover_roomcontrols(self.hass, token)
        except Exception:
            return self.async_abort(reason="cannot_connect")
        if not self._candidates:
            return self.async_abort(reason="no_roomcontrol")
        return None

    async def _create(self, candidate: dict[str, Any]) -> ConfigFlowResult:
        await self.async_set_unique_id(candidate[CONF_GATEWAY_SERIAL])
        self._abort_if_unique_id_configured()
        data = {
            CONF_INSTALLATION_ID: candidate[CONF_INSTALLATION_ID],
            CONF_GATEWAY_SERIAL: candidate[CONF_GATEWAY_SERIAL],
            CONF_ROOMCONTROL_ID: candidate[CONF_ROOMCONTROL_ID],
        }
        return self.async_create_entry(title="ViCare Rooms", data=data)

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        if not self._candidates:
            if (abort := await self._discover()) is not None:
                return abort
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
            step_id="user",
            data_schema=vol.Schema({vol.Required("gateway"): vol.In(options)}),
        )

    async def async_step_import(self, import_data) -> ConfigFlowResult:
        if (abort := await self._discover()) is not None:
            return abort
        return await self._create(self._candidates[0])

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
