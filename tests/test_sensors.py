"""Room values and setpoints are parsed from the RoomControl feature list."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from conftest import make_entry
from custom_components.vicare_rooms import ViCareRoomsCoordinator
from custom_components.vicare_rooms.sensor import ViCareRoomSensor, async_setup_entry
from homeassistant.components.sensor import SensorDeviceClass

pytestmark = pytest.mark.asyncio

ENTRY_DATA = {
    "installation_id": 123,
    "gateway_serial": "gateway-1",
    "roomcontrol_id": "roomcontrol-1",
}


def level(idx, name, mode, temperature):
    return {
        "feature": f"rooms.{idx}.temperature.levels.{name}.{mode}",
        "properties": {"temperature": {"value": temperature, "unit": "celsius"}},
    }


def sensor(idx, kind, value, status="connected"):
    props = {"status": {"value": status}}
    if value is not None:
        props["value"] = {"value": value}
    return {"feature": f"rooms.{idx}.sensors.{kind}", "properties": props}


FEATURES = {
    "data": [
        sensor(0, "temperature", 16.5),
        sensor(0, "humidity", 54.8),
        level(0, "normal", "heating", 20),
        level(0, "reduced", "heating", 16),
        level(0, "normal", "perceived", 20),
        # Kühl-Niveaus ohne Wert (Anlage ohne Kühlung) werden ignoriert
        {"feature": "rooms.0.temperature.levels.normal.cooling", "properties": {}},
        sensor(1, "temperature", 21.0),
        # Raum 4: angelegt, aber ohne Sensor und ohne Niveaus
        sensor(4, "temperature", None, status="notConnected"),
        # rooms.others.* sind keine nummerierten Räume
        level("others.0", "normal", "heating", 19),
        {"feature": "rooms.features", "properties": {}},
    ]
}


async def coordinator_for(hass, payload):
    entry = make_entry(hass, data=ENTRY_DATA)
    api = MagicMock()
    api.async_get = AsyncMock(return_value=payload)
    coordinator = ViCareRoomsCoordinator(hass, entry, api)
    coordinator.data = await coordinator._fetch()
    return entry, coordinator


async def test_setpoints_are_parsed_next_to_sensor_values(hass):
    _, coordinator = await coordinator_for(hass, FEATURES)
    assert coordinator.data == {
        0: {"t": 16.5, "h": 54.8, "normal": 20, "reduced": 16},
        1: {"t": 21.0},
    }


async def test_setpoint_entities_only_for_rooms_with_levels(hass):
    entry, coordinator = await coordinator_for(hass, FEATURES)
    entry.runtime_data = coordinator
    added = []
    await async_setup_entry(hass, entry, added.extend)
    assert sorted(e.unique_id for e in added) == [
        "gateway-1-room-0-humidity",
        "gateway-1-room-0-setpoint-normal",
        "gateway-1-room-0-setpoint-reduced",
        "gateway-1-room-0-temperature",
        "gateway-1-room-1-humidity",
        "gateway-1-room-1-temperature",
    ]
    reduced = next(e for e in added if e.unique_id.endswith("setpoint-reduced"))
    assert reduced.translation_key == "setpoint_reduced"
    assert reduced.device_class == SensorDeviceClass.TEMPERATURE
    assert reduced.native_value == 16


async def test_existing_sensor_ids_and_names_unchanged(hass):
    _, coordinator = await coordinator_for(hass, FEATURES)
    temperature = ViCareRoomSensor(coordinator, "gateway-1", 0, "t")
    assert temperature.unique_id == "gateway-1-room-0-temperature"
    assert temperature.translation_key is None
    assert temperature.native_value == 16.5


async def test_setpoint_unavailable_when_level_disappears(hass):
    _, coordinator = await coordinator_for(hass, FEATURES)
    normal = ViCareRoomSensor(coordinator, "gateway-1", 0, "normal")
    coordinator.data = {0: {"t": 16.5}}
    assert normal.native_value is None
    assert not normal.available
