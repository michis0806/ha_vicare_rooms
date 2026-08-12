# ViCare Raumwerte (`vicare_rooms`)

Home Assistant custom integration that exposes **per-room temperature and humidity**
from a Viessmann **Smart RoomControl** (ViCare room control) as proper sensor
entities — one device per room.

[Deutsche Beschreibung weiter unten.](#deutsch)

## What it does

The official [ViCare integration](https://www.home-assistant.io/integrations/vicare/)
does not expose the room values of a Smart RoomControl. This integration fills that
gap: it reads the `rooms.*.sensors.temperature` / `rooms.*.sensors.humidity` features
of the RoomControl device directly from the Viessmann API and creates:

- one **device per room** (linked to a "ViCare RoomControl" hub device),
- a **temperature** and a **humidity** sensor per room (localized entity names via
  device classes — works in every Home Assistant language).

Values are the room aggregates computed by the RoomControl (weighted average of the
climate sensors assigned to a room). Individual climate-sensor readings are **not
available** through the public Viessmann API.

## Requirements

- The **official ViCare integration must be set up and working** — this integration
  re-uses its OAuth token and does not do its own authentication.
- A Viessmann gateway with a **Smart RoomControl** device.

## Installation

### HACS (custom repository)

1. HACS → Integrations → ⋮ → *Custom repositories*
2. Add `https://github.com/michis0806/ha_vicare_rooms` (category: Integration)
3. Install **ViCare Raumwerte** and restart Home Assistant.

### Manual

Copy `custom_components/vicare_rooms/` into your `config/custom_components/` folder
and restart Home Assistant.

## Setup

Settings → Devices & services → *Add integration* → **ViCare Raumwerte**.
Installation, gateway and RoomControl are discovered automatically; if you have
several gateways with room control you can pick one (one config entry per gateway).

Alternatively add `vicare_rooms:` to `configuration.yaml` — the config entry is then
created automatically on startup.

## Room names

The Viessmann endpoint that returns room names
(`/iot/v2/equipment/installations/{id}/rooms/map`) is **monetized** and answers
`402 PACKAGE_NOT_PAID_FOR` for regular API access. The integration tries it anyway —
if your API package includes it, real room names are used automatically.

Otherwise rooms are called "Room N" / "Raum N". Use the integration's **Configure**
dialog to assign your own name per room index (`room_0`, `room_1`, …); the room
indices match the order of the rooms in the ViCare app.

## Behavior on API outages

Values are polled every 5 minutes. If the Viessmann API fails temporarily, the last
known values are kept for up to 30 minutes before entities become `unavailable`.

## Disclaimer

This project is not affiliated with Viessmann. Use at your own risk.

---

## Deutsch

Home-Assistant-Integration, die die **Raumtemperaturen und -luftfeuchten** eines
Viessmann **Smart RoomControl** als Sensoren bereitstellt — ein Gerät pro Raum.
Die offizielle ViCare-Integration bietet diese Werte nicht an.

- Benötigt die eingerichtete **offizielle ViCare-Integration** (liefert den
  OAuth-Token, keine eigene Anmeldung nötig).
- Installation über HACS (Custom Repository) oder manuell nach
  `config/custom_components/`, danach Neustart.
- Einrichtung über *Integration hinzufügen* → **ViCare Raumwerte** (automatische
  Erkennung) oder per `vicare_rooms:` in der `configuration.yaml`.
- **Raumnamen:** Der Namens-Endpunkt der Viessmann-API ist kostenpflichtig
  (HTTP 402 ohne gebuchtes Paket). Namen lassen sich stattdessen im
  **Konfigurieren**-Dialog der Integration je Raum-Index vergeben.
- Bei API-Störungen werden die letzten Werte bis zu 30 Minuten weitergereicht.

Die Werte sind die vom RoomControl gebildeten **Raum-Aggregate** (gewichteter
Mittelwert der zugeordneten Klimasensoren). Einzelwerte der Klimasensoren gibt die
öffentliche Viessmann-API nicht her.
