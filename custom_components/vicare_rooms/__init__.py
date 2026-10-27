"""ViCare Raumwerte — Raumtemperaturen/-feuchten vom Viessmann Smart RoomControl.

Liest die rooms.*-Features mit einer eigenen OAuth-Anmeldung bei Viessmann.
"""

from __future__ import annotations

import logging
import time
from datetime import timedelta

import voluptuous as vol
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    ImplementationUnavailableError,
    UnknownImplementationError,
)
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ViCareRoomsApi
from .const import (
    CONF_GATEWAY_SERIAL,
    CONF_INSTALLATION_ID,
    CONF_KNOWN_ROOMS,
    CONF_ROOMCONTROL_ID,
    DOMAIN,
    GRACE_SECONDS,
    UPDATE_INTERVAL,
    features_url,
)

_LOGGER = logging.getLogger(__name__)

# Accept legacy YAML, but interactive OAuth setup must happen in the UI.
CONFIG_SCHEMA = vol.Schema(
    {vol.Optional(DOMAIN): vol.Schema({})}, extra=vol.ALLOW_EXTRA
)

PLATFORMS = ["sensor"]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    if DOMAIN in config and not hass.config_entries.async_entries(DOMAIN):
        _LOGGER.warning(
            "Set up ViCare Rooms in Settings > Devices & services and remove "
            "vicare_rooms: from configuration.yaml; OAuth requires an interactive login"
        )
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data={}
            )
        )
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Retain legacy gateway and entity IDs; setup will request an own login."""
    if entry.version > 2:
        return False
    if entry.version == 1:
        hass.config_entries.async_update_entry(entry, version=2, minor_version=1)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not entry.data.get("token") or not entry.data.get("auth_implementation"):
        raise ConfigEntryAuthFailed("ViCare Rooms now requires its own OAuth sign-in")
    try:
        implementation = (
            await config_entry_oauth2_flow.async_get_config_entry_implementation(
                hass, entry
            )
        )
    except UnknownImplementationError as err:
        raise ConfigEntryAuthFailed(
            "Please configure ViCare Rooms application credentials"
        ) from err
    except ImplementationUnavailableError as err:
        raise ConfigEntryNotReady("OAuth provider temporarily unavailable") from err

    oauth = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)
    api = ViCareRoomsApi(oauth.async_request)
    if CONF_GATEWAY_SERIAL not in entry.data:
        raise ConfigEntryAuthFailed("Please select a Smart RoomControl during sign-in")

    coordinator = ViCareRoomsCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    coordinator.api_room_names = await api.async_fetch_room_names(
        entry.data[CONF_INSTALLATION_ID]
    )
    # Refreshing OAuth can update entry.data. Always use the latest token data.
    data = dict(entry.data)

    # Einmal gesehene Räume merken, damit ihre Entities bei Sensor-Ausfall
    # nicht verschwinden, sondern nur unavailable werden.
    known = set(data.get(CONF_KNOWN_ROOMS) or []) | set(coordinator.data)
    if set(data.get(CONF_KNOWN_ROOMS) or []) != known:
        data[CONF_KNOWN_ROOMS] = sorted(known)
        hass.config_entries.async_update_entry(entry, data=data)

    registry = dr.async_get(hass)
    hub = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, data[CONF_GATEWAY_SERIAL])},
        name="ViCare RoomControl",
        manufacturer="Viessmann",
        model="Smart RoomControl",
    )
    # Die Raum-Geräte hier anlegen statt über DeviceInfo(via_device=...) in den
    # Sensoren: via_device ist deprecated (Entfernung 2027.8), via_device_id
    # braucht die id des bereits angelegten Gateway-Geräts.
    for idx in sorted(known):
        registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"{data[CONF_GATEWAY_SERIAL]}-room-{idx}")},
            name=coordinator.room_display_name(idx),
            manufacturer="Viessmann",
            model="Smart RoomControl",
            via_device_id=hub.id,
        )

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


class ViCareRoomsCoordinator(DataUpdateCoordinator[dict[int, dict[str, float]]]):
    """Pollt die Raum-Features und puffert kurze API-Störungen ab."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, api: ViCareRoomsApi
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self._api = api
        self._url = features_url(
            entry.data[CONF_INSTALLATION_ID],
            entry.data[CONF_GATEWAY_SERIAL],
            entry.data[CONF_ROOMCONTROL_ID],
        )
        self._last_ok = 0.0
        self.api_room_names: dict[int, str] = {}

    def room_display_name(self, idx: int) -> str:
        """Anzeigename: Options-Eintrag > API-Name > generischer Name."""
        fallback = (
            "Raum" if (self.hass.config.language or "").startswith("de") else "Room"
        )
        return (
            self.config_entry.options.get(f"room_{idx}")
            or self.api_room_names.get(idx)
            or f"{fallback} {idx}"
        )

    async def _async_update_data(self) -> dict[int, dict[str, float]]:
        try:
            data = await self._fetch()
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            # kurze Störungen überbrücken statt sofort unavailable zu werden
            if (
                self.data is not None
                and time.monotonic() - self._last_ok < GRACE_SECONDS
            ):
                _LOGGER.warning(
                    "ViCare-API-Abruf fehlgeschlagen, nutze letzte Werte: %s", err
                )
                return self.data
            raise UpdateFailed(f"ViCare-API nicht erreichbar: {err}") from err
        self._last_ok = time.monotonic()
        return data

    async def _fetch(self) -> dict[int, dict[str, float]]:
        payload = await self._api.async_get(self._url)

        rooms: dict[int, dict[str, float]] = {}
        for feat in payload.get("data", []):
            parts = feat.get("feature", "").split(".")
            if (
                len(parts) == 4
                and parts[0] == "rooms"
                and parts[1].isdigit()
                and parts[2] == "sensors"
                and parts[3] in ("temperature", "humidity")
            ):
                props = feat.get("properties") or {}
                value = (props.get("value") or {}).get("value")
                if (props.get("status") or {}).get(
                    "value"
                ) == "connected" and value is not None:
                    key = "t" if parts[3] == "temperature" else "h"
                    rooms.setdefault(int(parts[1]), {})[key] = value
        if not rooms:
            raise UpdateFailed("Antwort der ViCare-API enthielt keine Raumwerte")
        return rooms
