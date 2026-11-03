"""Sensoren: Temperatur, Luftfeuchtigkeit und Soll-Temperaturen je ViCare-Raum."""
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
from .const import CONF_GATEWAY_SERIAL, CONF_KNOWN_ROOMS, DOMAIN, SETPOINT_LEVELS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ViCareRoomsCoordinator = entry.runtime_data
    gateway_serial = entry.data[CONF_GATEWAY_SERIAL]
    data = coordinator.data or {}
    rooms = sorted(set(entry.data.get(CONF_KNOWN_ROOMS) or []) | set(data))
    entities: list[ViCareRoomSensor] = []
    for idx in rooms:
        entities.append(ViCareRoomSensor(coordinator, gateway_serial, idx, "t"))
        entities.append(ViCareRoomSensor(coordinator, gateway_serial, idx, "h"))
        # Soll-Temperaturen nur für Räume, für die die API ein Niveau liefert
        # (Räume ohne Regelung, z. B. reine Klimasensoren, haben keine).
        for level in SETPOINT_LEVELS:
            if level in data.get(idx, {}):
                entities.append(
                    ViCareRoomSensor(coordinator, gateway_serial, idx, level)
                )
    async_add_entities(entities)


class ViCareRoomSensor(CoordinatorEntity[ViCareRoomsCoordinator], SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    # has_entity_name ohne eigenen Namen + device_class -> HA benennt die Entity
    # lokalisiert ("Temperatur"/"Temperature"/...) in jeder Frontend-Sprache.
    # Die Soll-Temperaturen bekommen ihren Namen über translation_key.
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ViCareRoomsCoordinator,
        gateway_serial: str,
        idx: int,
        kind: str,
    ) -> None:
        super().__init__(coordinator)
        self._idx = idx
        self._kind = kind
        if kind == "t":
            self._attr_unique_id = f"{gateway_serial}-room-{idx}-temperature"
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        elif kind == "h":
            self._attr_unique_id = f"{gateway_serial}-room-{idx}-humidity"
            self._attr_device_class = SensorDeviceClass.HUMIDITY
            self._attr_native_unit_of_measurement = PERCENTAGE
        else:
            # kind = Heizniveau ("normal"/"reduced")
            self._attr_unique_id = f"{gateway_serial}-room-{idx}-setpoint-{kind}"
            self._attr_translation_key = f"setpoint_{kind}"
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        # Das Raum-Gerät legt __init__.py an, hier genügt die Zuordnung.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{gateway_serial}-room-{idx}")}
        )

    @property
    def native_value(self) -> float | None:
        return (self.coordinator.data or {}).get(self._idx, {}).get(self._kind)

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None
