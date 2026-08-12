"""ViCare Raumwerte — Raumtemperaturen/-feuchten vom Viessmann Smart RoomControl.

Ergänzt die offizielle vicare-Integration: nutzt deren OAuth-Token und liest
die rooms.*-Features des RoomControl-Geräts direkt von der Viessmann-API.
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_GATEWAY_SERIAL,
    CONF_INSTALLATION_ID,
    CONF_KNOWN_ROOMS,
    CONF_ROOMCONTROL_ID,
    DOMAIN,
    GRACE_SECONDS,
    INSTALLATIONS_URL,
    REQUEST_TIMEOUT,
    UPDATE_INTERVAL,
    features_url,
    rooms_map_url,
)

_LOGGER = logging.getLogger(__name__)

# Der yaml-Schlüssel `vicare_rooms:` dient nur als Anstoß, den Config-Eintrag
# beim ersten Start automatisch anzulegen (Import-Flow). Optional.
CONFIG_SCHEMA = vol.Schema({vol.Optional(DOMAIN): vol.Schema({})}, extra=vol.ALLOW_EXTRA)

PLATFORMS = ["sensor"]


def get_vicare_token(hass: HomeAssistant) -> str | None:
    """Access-Token der offiziellen vicare-Integration holen."""
    for entry in hass.config_entries.async_entries("vicare"):
        token = (entry.data.get("token") or {}).get("access_token")
        if token:
            return token
    return None


async def api_get(hass: HomeAssistant, url: str, token: str) -> dict:
    session = async_get_clientsession(hass)
    resp = await session.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
    )
    resp.raise_for_status()
    return await resp.json()


async def async_discover_roomcontrols(
    hass: HomeAssistant, token: str
) -> list[dict[str, Any]]:
    """Alle Gateways mit RoomControl-Gerät im ViCare-Konto finden."""
    payload = await api_get(hass, INSTALLATIONS_URL, token)
    found: list[dict[str, Any]] = []
    for inst in payload.get("data", []):
        for gw in inst.get("gateways") or []:
            for dev in gw.get("devices") or []:
                if dev.get("deviceType") == "roomControl":
                    found.append(
                        {
                            CONF_INSTALLATION_ID: inst["id"],
                            CONF_GATEWAY_SERIAL: gw["serial"],
                            CONF_ROOMCONTROL_ID: dev["id"],
                            "title": inst.get("description") or str(inst["id"]),
                        }
                    )
    return found


async def async_fetch_room_names(
    hass: HomeAssistant, token: str, installation_id
) -> dict[int, str]:
    """Raumnamen abrufen. Der Endpunkt ist monetarisiert und antwortet ohne
    gebuchtes API-Paket mit HTTP 402 — dann leeres Mapping zurückgeben."""
    try:
        payload = await api_get(hass, rooms_map_url(installation_id), token)
    except Exception as err:
        _LOGGER.debug("Raumnamen nicht verfügbar: %s", err)
        return {}
    raw = payload.get("data", payload)
    if isinstance(raw, dict):
        raw = raw.get("rooms", [])
    names: dict[int, str] = {}
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        idx = item.get("id", item.get("roomId"))
        name = item.get("name") or item.get("title")
        if isinstance(idx, int) and name:
            names[idx] = str(name)
    return names


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    if DOMAIN in config and not hass.config_entries.async_entries(DOMAIN):
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data={}
            )
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    token = get_vicare_token(hass)
    if not token:
        raise ConfigEntryNotReady(
            "Offizielle vicare-Integration nicht eingerichtet (liefert den OAuth-Token)"
        )

    # Alt-Einträge (v1.0.x) oder Import ohne Daten: einmalig nachdiscovern
    data = dict(entry.data)
    if CONF_GATEWAY_SERIAL not in data:
        try:
            found = await async_discover_roomcontrols(hass, token)
        except Exception as err:
            raise ConfigEntryNotReady(f"Discovery fehlgeschlagen: {err}") from err
        if not found:
            raise ConfigEntryNotReady("Kein Smart RoomControl im ViCare-Konto gefunden")
        found[0].pop("title", None)
        data.update(found[0])
        hass.config_entries.async_update_entry(entry, data=data)

    coordinator = ViCareRoomsCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    coordinator.api_room_names = await async_fetch_room_names(
        hass, token, data[CONF_INSTALLATION_ID]
    )

    # Einmal gesehene Räume merken, damit ihre Entities bei Sensor-Ausfall
    # nicht verschwinden, sondern nur unavailable werden.
    known = set(data.get(CONF_KNOWN_ROOMS) or []) | set(coordinator.data)
    if set(data.get(CONF_KNOWN_ROOMS) or []) != known:
        data[CONF_KNOWN_ROOMS] = sorted(known)
        hass.config_entries.async_update_entry(entry, data=data)

    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, data[CONF_GATEWAY_SERIAL])},
        name="ViCare RoomControl",
        manufacturer="Viessmann",
        model="Smart RoomControl",
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

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
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
        except Exception as err:
            # kurze Störungen überbrücken statt sofort unavailable zu werden
            if self.data is not None and time.monotonic() - self._last_ok < GRACE_SECONDS:
                _LOGGER.warning(
                    "ViCare-API-Abruf fehlgeschlagen, nutze letzte Werte: %s", err
                )
                return self.data
            raise UpdateFailed(f"ViCare-API nicht erreichbar: {err}") from err
        self._last_ok = time.monotonic()
        return data

    async def _fetch(self) -> dict[int, dict[str, float]]:
        token = get_vicare_token(self.hass)
        if not token:
            raise UpdateFailed("Kein Access-Token der vicare-Integration gefunden")
        payload = await api_get(self.hass, self._url, token)

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
                if (
                    (props.get("status") or {}).get("value") == "connected"
                    and value is not None
                ):
                    key = "t" if parts[3] == "temperature" else "h"
                    rooms.setdefault(int(parts[1]), {})[key] = value
        if not rooms:
            raise UpdateFailed("Antwort der ViCare-API enthielt keine Raumwerte")
        return rooms
