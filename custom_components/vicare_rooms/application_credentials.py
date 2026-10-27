"""Application credentials for ViCare Rooms, independent of core ViCare."""

from __future__ import annotations

from homeassistant.components.application_credentials import ClientCredential
from homeassistant.core import HomeAssistant
from homeassistant.helpers.config_entry_oauth2_flow import (
    LocalOAuth2ImplementationWithPkce,
)

from .const import AUTHORIZE_URL, TOKEN_URL


async def async_get_description_placeholders(hass: HomeAssistant) -> dict[str, str]:
    """Link to instructions for creating a Viessmann API client."""
    return {
        "more_info_url": "https://github.com/michis0806/ha_vicare_rooms#authentication"
    }


async def async_get_auth_implementation(
    hass: HomeAssistant, auth_domain: str, credential: ClientCredential
) -> ViCareRoomsOAuth2Implementation:
    """Use PKCE with a public client; no client secret is sent."""
    return ViCareRoomsOAuth2Implementation(
        hass, auth_domain, credential.client_id, AUTHORIZE_URL, TOKEN_URL
    )


class ViCareRoomsOAuth2Implementation(LocalOAuth2ImplementationWithPkce):
    """Viessmann OAuth2 with offline access for token refresh."""

    @property
    def extra_authorize_data(self) -> dict:
        return super().extra_authorize_data | {"scope": "IoT offline_access"}
