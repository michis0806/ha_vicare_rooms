"""Authenticated requests and RoomControl discovery for ViCare Rooms."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    OAuth2TokenRequestReauthError,
)

from .const import (
    CONF_GATEWAY_SERIAL,
    CONF_INSTALLATION_ID,
    CONF_ROOMCONTROL_ID,
    INSTALLATIONS_URL,
    REQUEST_TIMEOUT,
    rooms_map_url,
)

_LOGGER = logging.getLogger(__name__)


class ViCareRoomsApi:
    """Use an authenticated request function supplied by Home Assistant."""

    def __init__(
        self, request: Callable[..., Awaitable[aiohttp.ClientResponse]]
    ) -> None:
        self._request = request

    async def async_get(self, url: str) -> dict[str, Any]:
        """Fetch JSON, allowing Home Assistant to refresh the entry's token."""
        try:
            response = await self._request(
                "GET", url, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            )
            async with response:
                if response.status == 401:
                    raise ConfigEntryAuthFailed(
                        "Viessmann authorization expired or revoked"
                    )
                response.raise_for_status()
                return await response.json()
        except OAuth2TokenRequestReauthError as err:
            raise ConfigEntryAuthFailed("Please sign in to ViCare Rooms again") from err

    async def async_discover_roomcontrols(self) -> list[dict[str, Any]]:
        """Discover gateways with a RoomControl in the authorized account."""
        payload = await self.async_get(INSTALLATIONS_URL)
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
        self, installation_id: int | str
    ) -> dict[int, str]:
        """Read optional paid room names without hiding authentication failures."""
        try:
            payload = await self.async_get(rooms_map_url(installation_id))
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            _LOGGER.debug("Room names unavailable: %s", err)
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
