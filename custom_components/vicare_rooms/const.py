"""Konstanten für ViCare Raumwerte."""

DOMAIN = "vicare_rooms"

API_BASE = "https://api.viessmann-climatesolutions.com/iot/v2"
INSTALLATIONS_URL = f"{API_BASE}/equipment/installations?includeGateways=true"

CONF_INSTALLATION_ID = "installation_id"
CONF_GATEWAY_SERIAL = "gateway_serial"
CONF_ROOMCONTROL_ID = "roomcontrol_id"
CONF_KNOWN_ROOMS = "known_rooms"

UPDATE_INTERVAL = 300   # Sekunden
GRACE_SECONDS = 1800    # bei API-Störung alte Werte max. 30 Min weiterreichen
REQUEST_TIMEOUT = 15


def features_url(installation_id, gateway_serial: str, roomcontrol_id: str) -> str:
    return (
        f"{API_BASE}/features/installations/{installation_id}"
        f"/gateways/{gateway_serial}/devices/{roomcontrol_id}/features"
    )


def rooms_map_url(installation_id) -> str:
    return f"{API_BASE}/equipment/installations/{installation_id}/rooms/map"
