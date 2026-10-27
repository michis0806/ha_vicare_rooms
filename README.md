# ViCare Rooms (`vicare_rooms`)

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=michis0806&repository=ha_vicare_rooms&category=integration)
[![Open your Home Assistant instance and start setting up this integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=vicare_rooms)

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

- Home Assistant **2026.10.0 or newer**.
- A Viessmann account and API client for **ViCare Rooms** (see below).
- The official ViCare integration is optional. ViCare Rooms authenticates independently.
- A Viessmann gateway with a **Smart RoomControl** device.

## Installation

### HACS (custom repository)

Click the HACS badge above, or manually:

1. HACS → Integrations → ⋮ → *Custom repositories*
2. Add `https://github.com/michis0806/ha_vicare_rooms` (category: Integration)
3. Install **ViCare Rooms** and restart Home Assistant.

### Manual

Copy `custom_components/vicare_rooms/` into your `config/custom_components/` folder
and restart Home Assistant.

## Authentication

ViCare Rooms uses its **own OAuth authorization** with PKCE. It never reads tokens
or credentials from the official ViCare integration. Home Assistant stores and
refreshes the tokens for ViCare Rooms automatically; your Viessmann password is
entered only on the Viessmann sign-in page.

1. Sign in to the [Viessmann developer portal](https://app.developer.viessmann-climatesolutions.com/)
   with the account used by your ViCare app.
2. Create an API client, for example named **ViCare Rooms**, with Google reCAPTCHA
   **disabled** and this redirect URI: `https://my.home-assistant.io/redirect/oauth`.
3. Copy the **Client ID**. New clients may take up to an hour to become active.
4. Add **ViCare Rooms** in Home Assistant and enter the Client ID in the
   integration's own setup dialog. No client secret is requested. The client is
   stored automatically in Home Assistant Application Credentials.
5. Follow the redirect to Viessmann and authorize access, then select your gateway
   if more than one Smart RoomControl is found.

If you do not use the My Home Assistant integration, register your instance's
`<Home Assistant URL>/auth/external/callback` as the redirect URI instead.

### Invalid redirection URI

If Viessmann reports `Invalid redirection URI`, open the API client matching the
Client ID you entered and add exactly `https://my.home-assistant.io/redirect/oauth`
to its allowed redirect URIs, without a trailing slash. Save the client, then
restart the sign-in flow in Home Assistant. Changing the client secret cannot fix
this error. If My Home Assistant is disabled, use the instance callback described
above instead.

### Updating from 1.x

After updating and restarting, the existing entry asks you to **re-authenticate**.
Complete the steps above through that prompt, using the account that contains the
existing gateway. **Do not delete the integration or add a replacement entry.**
The existing config entry, gateway and sensor unique IDs, entity IDs, known rooms
and custom room names are preserved. Each configured gateway requires its own
sign-in. No credentials or tokens are copied from the official ViCare integration.

The legacy `vicare_rooms:` YAML key no longer creates a configured entry, because
OAuth requires an interactive login. Remove the key from `configuration.yaml`;
existing entries continue through the re-authentication prompt.

## Setup

Settings → Devices & services → *Add integration* → **ViCare Rooms**.
Installation, gateway and RoomControl are discovered automatically; if you have
several gateways with room control you can pick one (one config entry per gateway).

Configuration is performed in the UI; YAML cannot complete the OAuth login.

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
Authorization failures immediately request a new sign-in instead of being hidden
by this grace period. A separate OAuth login does not guarantee a separate API
quota: account for the combined requests if the official integration is also used.

## Icon

The integration ships its own brand icon (`brand/` folder inside the integration);
Home Assistant 2026.3 or newer picks it up automatically.

## Disclaimer

This project is not affiliated with Viessmann. Use at your own risk.

---

## Deutsch

Home-Assistant-Integration, die die **Raumtemperaturen und -luftfeuchten** eines
Viessmann **Smart RoomControl** als Sensoren bereitstellt — ein Gerät pro Raum.
Die offizielle ViCare-Integration bietet diese Werte nicht an.

- Benötigt **Home Assistant 2026.10.0 oder neuer** und eine **eigene OAuth-Anmeldung**
  bei Viessmann. Die offizielle ViCare-Integration ist optional.
- Im [Viessmann-Entwicklerportal](https://app.developer.viessmann-climatesolutions.com/)
  einen API-Client für ViCare Rooms anlegen: Google reCAPTCHA deaktivieren und
  `https://my.home-assistant.io/redirect/oauth` als Redirect-URI eintragen.
  Bei der Einrichtung wird nur die Client-ID abgefragt, kein Client-Secret.
  Neue Clients benötigen ggf. bis zu einer Stunde.
- Installation über HACS (Custom Repository) oder manuell nach
  `config/custom_components/`, danach Neustart.
- Einrichtung über *Integration hinzufügen* → **ViCare Rooms**, anschließend bei
  Viessmann anmelden. Das Gateway wird danach automatisch erkannt bzw. ausgewählt.
- **Update von 1.x:** Die vorhandene Integration fordert zur erneuten Anmeldung auf.
  Diese mit dem bisherigen Viessmann-Konto abschließen, ohne die Integration zu
  löschen. Sensor-IDs, Geräte und Raumnamen bleiben erhalten. Pro Gateway ist
  eine Anmeldung nötig. Den bisherigen YAML-Eintrag `vicare_rooms:` entfernen.
- Tokens werden von Home Assistant automatisch erneuert; bei widerrufener Freigabe
  erscheint eine Aufforderung zur erneuten Anmeldung. Die API-Limits weiterhin
  gemeinsam mit den Abfragen anderer ViCare-Integrationen berücksichtigen.
- **Raumnamen:** Der Namens-Endpunkt der Viessmann-API ist kostenpflichtig
  (HTTP 402 ohne gebuchtes Paket). Namen lassen sich stattdessen im
  **Konfigurieren**-Dialog der Integration je Raum-Index vergeben.
- Bei API-Störungen werden die letzten Werte bis zu 30 Minuten weitergereicht.

Die Werte sind die vom RoomControl gebildeten **Raum-Aggregate** (gewichteter
Mittelwert der zugeordneten Klimasensoren). Einzelwerte der Klimasensoren gibt die
öffentliche Viessmann-API nicht her.

## Development checks

Use Python 3.14 and an isolated virtual environment:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-test.txt
python -m pytest --asyncio-mode=auto tests
```

Tests use a temporary Home Assistant configuration and a local HTTP server;
no real Viessmann account or production Home Assistant instance is accessed.
GitHub Actions also runs hassfest and the HACS validator.
