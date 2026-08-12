"""Sensoren: Temperatur und Luftfeuchtigkeit je ViCare-Raum."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ViCareRoomsCoordinator
from .const import CONF_GATEWAY_SERIAL, CONF_KNOWN_ROOMS, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ViCareRoomsCoordinator = entry.runtime_data
    gateway_serial = entry.data[CONF_GATEWAY_SERIAL]
    rooms = sorted(
        set(entry.data.get(CONF_KNOWN_ROOMS) or []) | set(coordinator.data or {})
    )
    entities: list[ViCareRoomSensor] = []
    for idx in rooms:
        display = coordinator.room_display_name(idx)
        entities.append(ViCareRoomSensor(coordinator, gateway_serial, idx, display, "t"))
        entities.append(ViCareRoomSensor(coordinator, gateway_serial, idx, display, "h"))
    async_add_entities(entities)


class ViCareRoomSensor(CoordinatorEntity[ViCareRoomsCoordinator], SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    # has_entity_name ohne eigenen Namen + device_class -> HA benennt die Entity
    # lokalisiert ("Temperatur"/"Temperature"/...) in jeder Frontend-Sprache
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ViCareRoomsCoordinator,
        gateway_serial: str,
        idx: int,
        display: str,
        kind: str,
    ) -> None:
        super().__init__(coordinator)
        self._idx = idx
        self._kind = kind
        if kind == "t":
            self._attr_unique_id = f"{gateway_serial}-room-{idx}-temperature"
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        else:
            self._attr_unique_id = f"{gateway_serial}-room-{idx}-humidity"
            self._attr_device_class = SensorDeviceClass.HUMIDITY
            self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{gateway_serial}-room-{idx}")},
            name=display,
            manufacturer="Viessmann",
            model="Smart RoomControl",
            via_device=(DOMAIN, gateway_serial),
        )

    @property
    def native_value(self) -> float | None:
        return (self.coordinator.data or {}).get(self._idx, {}).get(self._kind)

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None
