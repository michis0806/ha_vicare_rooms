# Changelog

All notable changes to this integration are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.3] - 2026-09-09

### Changed

- Room devices are now created explicitly in `async_setup_entry`, right after the
  "ViCare RoomControl" gateway device, and link to it via `via_device_id`.
  `DeviceInfo(via_device=...)` is deprecated in Home Assistant and stops working
  in 2027.8, because device identifiers are no longer guaranteed to be unique
  across config entries.
- Sensors only carry the `identifiers` of their device; the `display` argument was
  dropped from the entity constructor. Room names still come from
  `room_display_name()`, so names from the options flow and from the Viessmann API
  behave exactly as before.

Nothing changes for users — no entity IDs, unique IDs or device links are
affected. A Home Assistant restart is required, as with any custom integration
update.

## [1.1.2] - 2026-08-12

### Added

- Brand icons bundled inside the integration (`brand/`), for local brand images in
  Home Assistant 2026.3 and later.

### Changed

- Manifest keys sorted so that hassfest validation passes.

## [1.1.1] - 2026-08-12

### Added

- `strings.json` plus validation workflows (hassfest and the HACS action).
- My Home Assistant badges in the README for HACS and the config flow.

### Changed

- Renamed to "ViCare Rooms".

## [1.1.0] - 2026-08-12

Initial release. This version was never tagged.

### Added

- One device per room, each with a temperature and a humidity sensor, below a
  "ViCare RoomControl" hub device.
- Auto-discovery of the Smart RoomControl using the OAuth token of the official
  ViCare integration.
- Options flow for room names — needed because the Viessmann room-name endpoint
  requires a paid API package and otherwise answers with HTTP 402.
- English and German translations.

[1.1.3]: https://github.com/michis0806/ha_vicare_rooms/compare/v1.1.2...v1.1.3
[1.1.2]: https://github.com/michis0806/ha_vicare_rooms/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/michis0806/ha_vicare_rooms/compare/79ca584...v1.1.1
[1.1.0]: https://github.com/michis0806/ha_vicare_rooms/commit/79ca584
