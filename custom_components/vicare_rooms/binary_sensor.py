"""Binärsensoren: Fenster-offen-Erkennung je ViCare-Raum."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ViCareRoomsCoordinator
from .const import CONF_GATEWAY_SERIAL, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ViCareRoomsCoordinator = entry.runtime_data
    gateway_serial = entry.data[CONF_GATEWAY_SERIAL]
    async_add_entities(
        ViCareRoomOpenWindow(coordinator, gateway_serial, idx)
        for idx, values in sorted((coordinator.data or {}).items())
        if "window" in values
    )


class ViCareRoomOpenWindow(
    CoordinatorEntity[ViCareRoomsCoordinator], BinarySensorEntity
):
    """Fenster offen laut Raumsteuerung (rooms.N.sensors.openWindow)."""

    _attr_device_class = BinarySensorDeviceClass.WINDOW
    _attr_has_entity_name = True
    _attr_translation_key = "open_window"

    def __init__(
        self, coordinator: ViCareRoomsCoordinator, gateway_serial: str, idx: int
    ) -> None:
        super().__init__(coordinator)
        self._idx = idx
        self._attr_unique_id = f"{gateway_serial}-room-{idx}-open-window"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{gateway_serial}-room-{idx}")}
        )

    @property
    def is_on(self) -> bool | None:
        return (self.coordinator.data or {}).get(self._idx, {}).get("window")

    @property
    def available(self) -> bool:
        return super().available and self.is_on is not None
