"""Exercise own OAuth, legacy reauth and API errors against real HA helpers."""

import time
from unittest.mock import AsyncMock, PropertyMock, patch

import aiohttp
import pytest
from conftest import make_entry
from custom_components.vicare_rooms import (
    ViCareRoomsCoordinator,
    async_migrate_entry,
    async_setup_entry,
)
from custom_components.vicare_rooms.api import ViCareRoomsApi
from custom_components.vicare_rooms.application_credentials import (
    async_get_auth_implementation,
)
from custom_components.vicare_rooms.config_flow import ViCareRoomsConfigFlow
from custom_components.vicare_rooms.const import (
    INSTALLATIONS_URL,
    TOKEN_URL,
    features_url,
    rooms_map_url,
)
from homeassistant.components.application_credentials import ClientCredential
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.config_entry_oauth2_flow import OAuth2Session

pytestmark = pytest.mark.asyncio

CANDIDATE = {
    "installation_id": 123,
    "gateway_serial": "gateway-1",
    "roomcontrol_id": "roomcontrol-1",
    "title": "Home",
}
DISCOVERY = {
    "data": [
        {
            "id": 123,
            "gateways": [
                {
                    "serial": "gateway-1",
                    "devices": [{"id": "roomcontrol-1", "deviceType": "roomControl"}],
                }
            ],
        }
    ]
}
FEATURES = {
    "data": [
        {
            "feature": "rooms.0.sensors.temperature",
            "properties": {"status": {"value": "connected"}, "value": {"value": 21.5}},
        }
    ]
}


def token(access="own-access", *, expired=False):
    return {
        "access_token": access,
        "refresh_token": "own-refresh",
        "expires_at": time.time() + (-10 if expired else 3600),
        "expires_in": 3600,
    }


def flow_for(hass, entry=None):
    flow = ViCareRoomsConfigFlow()
    flow.hass = hass
    flow.handler = "vicare_rooms"
    flow.flow_id = "test-flow"
    flow.context = (
        {"source": "user"}
        if entry is None
        else {"source": "reauth", "entry_id": entry.entry_id}
    )
    return flow


async def implementation(hass):
    return await async_get_auth_implementation(
        hass, "own-client", ClientCredential("client-id", "ignored-secret")
    )


async def test_pkce_authorization_code_exchange(hass, http_mock):
    """The real HA flow sends PKCE/scopes and owns the returned tokens."""
    impl = await implementation(hass)
    flow = flow_for(hass)
    flow.flow_impl = impl
    with patch.object(
        type(impl),
        "redirect_uri",
        new_callable=PropertyMock,
        return_value="https://my.home-assistant.io/redirect/oauth",
    ):
        auth = await flow.async_step_auth()
    from yarl import URL

    query = URL(auth["url"]).query
    assert query["code_challenge_method"] == "S256"
    assert query["scope"] == "IoT offline_access"
    assert "client_secret" not in query
    await flow.async_step_auth(
        {"code": "authorization-code", "state": {"redirect_uri": query["redirect_uri"]}}
    )
    with http_mock as mocked:
        mocked.post(
            TOKEN_URL,
            payload={
                "access_token": "own-access",
                "refresh_token": "own-refresh",
                "expires_in": 3600,
            },
        )
        mocked.get(INSTALLATIONS_URL, payload=DISCOVERY)
        result = await flow.async_step_creation()
        post = next(
            calls[0]
            for (method, _), calls in mocked.requests.items()
            if method == "POST"
        )
        assert post.kwargs["data"]["code_verifier"] == impl.code_verifier
        assert "client_secret" not in post.kwargs["data"]
    assert result["type"] == "create_entry"
    assert result["data"]["token"]["access_token"] == "own-access"
    assert result["data"]["auth_implementation"] == "own-client"
    assert result["data"]["gateway_serial"] == "gateway-1"


async def test_expired_token_refresh_is_persisted(hass, http_mock):
    entry = make_entry(
        hass,
        data={
            **CANDIDATE,
            "token": token(expired=True),
            "auth_implementation": "own-client",
        },
    )
    session = OAuth2Session(hass, entry, await implementation(hass))
    with http_mock as mocked:
        mocked.post(
            TOKEN_URL,
            payload={
                "access_token": "renewed",
                "refresh_token": "rotated",
                "expires_in": 3600,
            },
        )
        mocked.get(INSTALLATIONS_URL, payload=DISCOVERY)
        result = await ViCareRoomsApi(
            session.async_request
        ).async_discover_roomcontrols()
        get = next(
            calls[0]
            for (method, _), calls in mocked.requests.items()
            if method == "GET"
        )
        assert get.kwargs["headers"]["Authorization"] == "Bearer renewed"
    assert result[0]["gateway_serial"] == "gateway-1"
    assert entry.data["token"]["refresh_token"] == "rotated"


async def test_migrate_and_reauth_preserves_existing_entry(hass, http_mock):
    old = {**CANDIDATE, "known_rooms": [0, 1]}
    entry = make_entry(hass, version=1, data=old, options={"room_0": "Wohnzimmer"})
    assert await async_migrate_entry(hass, entry)
    assert entry.version == 2
    with pytest.raises(ConfigEntryAuthFailed):
        await async_setup_entry(hass, entry)
    flow = flow_for(hass, entry)
    assert (await flow.async_step_reauth(entry.data))["step_id"] == "reauth_confirm"
    with (
        http_mock as mocked,
        patch.object(hass.config_entries, "async_reload", new=AsyncMock()),
    ):
        mocked.get(INSTALLATIONS_URL, payload=DISCOVERY)
        result = await flow.async_oauth_create_entry(
            {"token": token(), "auth_implementation": "own-client"}
        )
        await hass.async_block_till_done()
    assert result["reason"] == "reauth_successful"
    assert entry.unique_id == "gateway-1"
    assert entry.options == {"room_0": "Wohnzimmer"}
    assert entry.data["known_rooms"] == [0, 1]
    assert entry.data["token"]["access_token"] == "own-access"
    assert len(hass.config_entries.async_entries("vicare_rooms")) == 1


async def test_reauth_wrong_account_does_not_replace_existing_data(hass, http_mock):
    entry = make_entry(hass, data=CANDIDATE)
    flow = flow_for(hass, entry)
    with http_mock as mocked:
        mocked.get(INSTALLATIONS_URL, payload={"data": []})
        result = await flow.async_oauth_create_entry(
            {"token": token(), "auth_implementation": "own-client"}
        )
    assert result["reason"] == "wrong_account"
    assert "token" not in entry.data


async def test_multiple_gateways_and_duplicate(hass, http_mock):
    other = {**CANDIDATE, "gateway_serial": "gateway-2"}
    flow = flow_for(hass)
    flow._oauth_data = {"token": token(), "auth_implementation": "own-client"}
    flow._candidates = [CANDIDATE, other]
    assert (await flow.async_step_gateway())["step_id"] == "gateway"
    result = await flow.async_step_gateway({"gateway": "gateway-2"})
    assert result["data"]["gateway_serial"] == "gateway-2"
    make_entry(hass, data=CANDIDATE)
    from homeassistant.data_entry_flow import AbortFlow

    with pytest.raises(AbortFlow, match="already_configured"):
        await flow._create(CANDIDATE)


@pytest.mark.parametrize("status", [401, 402, 403, 429, 503])
async def test_room_name_failure_and_authorization(hass, http_mock, status):
    entry = make_entry(hass, data={"token": token()})
    api = ViCareRoomsApi(
        OAuth2Session(hass, entry, await implementation(hass)).async_request
    )
    with http_mock as mocked:
        mocked.get(rooms_map_url(123), status=status)
        if status == 401:
            with pytest.raises(ConfigEntryAuthFailed):
                await api.async_fetch_room_names(123)
        else:
            assert await api.async_fetch_room_names(123) == {}


async def test_auth_failure_bypasses_cached_values(hass, http_mock):
    entry = make_entry(hass, data=CANDIDATE)
    api = AsyncMock()
    coordinator = ViCareRoomsCoordinator(hass, entry, api)
    coordinator.data = {0: {"t": 21.5}}
    coordinator._last_ok = time.monotonic()
    api.async_get.side_effect = aiohttp.ClientConnectionError("offline")
    assert await coordinator._async_update_data() == coordinator.data
    api.async_get.side_effect = ConfigEntryAuthFailed("revoked")
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_refresh_rejection_requests_reauth(hass, http_mock):
    entry = make_entry(
        hass,
        data={
            **CANDIDATE,
            "token": token(expired=True),
            "auth_implementation": "own-client",
        },
    )
    api = ViCareRoomsApi(
        OAuth2Session(hass, entry, await implementation(hass)).async_request
    )
    with (
        http_mock as mocked,
        patch.object(type(entry), "async_start_reauth_if_available") as reauth,
    ):
        mocked.post(TOKEN_URL, status=400, payload={"error": "invalid_grant"})
        with pytest.raises(ConfigEntryAuthFailed):
            await api.async_get(INSTALLATIONS_URL)
        reauth.assert_called_once_with(hass)


async def test_legacy_yaml_requires_ui(hass, http_mock):
    assert (await flow_for(hass).async_step_import({}))["reason"] == "setup_required"


async def test_setup_keeps_refreshed_token_and_sensor_ids(hass, http_mock):
    """Discovering rooms during setup must not overwrite a rotated token."""
    from custom_components.vicare_rooms.sensor import ViCareRoomSensor
    from homeassistant.helpers import device_registry as dr

    dr.async_setup(hass)
    await dr.async_load(hass)
    entry = make_entry(
        hass,
        data={
            **CANDIDATE,
            "token": token(expired=True),
            "auth_implementation": "own-client",
        },
        options={"room_0": "Wohnzimmer"},
    )
    entry._async_set_state(hass, ConfigEntryState.SETUP_IN_PROGRESS, None)
    impl = await implementation(hass)
    with (
        http_mock as mocked,
        patch(
            "custom_components.vicare_rooms.config_entry_oauth2_flow.async_get_config_entry_implementation",
            new=AsyncMock(return_value=impl),
        ),
        patch.object(
            hass.config_entries, "async_forward_entry_setups", new=AsyncMock()
        ),
    ):
        mocked.post(
            TOKEN_URL,
            payload={
                "access_token": "renewed",
                "refresh_token": "rotated",
                "expires_in": 3600,
            },
        )
        mocked.get(features_url(123, "gateway-1", "roomcontrol-1"), payload=FEATURES)
        mocked.get(rooms_map_url(123), status=402)
        assert await async_setup_entry(hass, entry)
    assert entry.data["token"]["refresh_token"] == "rotated"
    assert entry.data["known_rooms"] == [0]
    sensor = ViCareRoomSensor(entry.runtime_data, "gateway-1", 0, "t")
    assert sensor.unique_id == "gateway-1-room-0-temperature"
    assert sensor.native_value == 21.5
    assert entry.runtime_data.room_display_name(0) == "Wohnzimmer"
    await entry.runtime_data.async_shutdown()


async def test_client_id_only_form_and_credential_registration(hass, http_mock):
    """Use real Application Credentials storage without asking for a secret."""
    from homeassistant.components import application_credentials
    from homeassistant.helpers import config_entry_oauth2_flow

    hass.config.components.add("my")
    assert await application_credentials.async_setup(hass, {})
    flow = flow_for(hass)
    result = await flow.async_step_user()
    assert result["step_id"] == "user"
    assert {str(field) for field in result["data_schema"].schema} == {"client_id"}
    assert (
        result["description_placeholders"]["redirect_uri"]
        == "https://my.home-assistant.io/redirect/oauth"
    )
    invalid = await flow.async_step_user({"client_id": "  "})
    assert invalid["errors"] == {"client_id": "invalid_client_id"}
    with patch(
        "custom_components.vicare_rooms.config_flow.ViCareRoomsConfigFlow.async_step_auth",
        new=AsyncMock(return_value={"type": "external"}),
    ):
        assert (await flow.async_step_user({"client_id": "  public-client-1  "}))[
            "type"
        ] == "external"
    credentials = hass.data[
        application_credentials.DATA_COMPONENT
    ].async_client_credentials("vicare_rooms")
    assert len(credentials) == 1
    credential = next(iter(credentials.values()))
    assert credential.client_id == "public-client-1"
    assert credential.client_secret == ""
    assert flow.flow_impl.client_secret == ""
    implementations = await config_entry_oauth2_flow.async_get_implementations(
        hass, "vicare_rooms"
    )
    assert flow.flow_impl.domain in implementations


async def test_multiple_public_clients_do_not_overwrite_each_other(hass, http_mock):
    from homeassistant.components import application_credentials
    from homeassistant.helpers import config_entry_oauth2_flow

    hass.config.components.add("my")
    await application_credentials.async_setup(hass, {})
    with patch(
        "custom_components.vicare_rooms.config_flow.ViCareRoomsConfigFlow.async_step_auth",
        new=AsyncMock(return_value={"type": "external"}),
    ):
        first = flow_for(hass)
        await first.async_step_user({"client_id": "first-client"})
        second = flow_for(hass)
        await second.async_step_user({"client_id": "second-client"})
    assert first.flow_impl.domain != second.flow_impl.domain
    assert (
        len(
            await config_entry_oauth2_flow.async_get_implementations(
                hass, "vicare_rooms"
            )
        )
        == 2
    )
    entry = make_entry(
        hass, data={**CANDIDATE, "auth_implementation": first.flow_impl.domain}
    )
    reauth = flow_for(hass, entry)
    result = await reauth.async_step_reauth_confirm({})
    assert result["step_id"] == "user"
    field = next(iter(result["data_schema"].schema))
    assert field.description["suggested_value"] == "first-client"
