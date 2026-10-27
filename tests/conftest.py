"""Isolated Home Assistant instance; never use the live configuration."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest_asyncio
from aiohttp import ClientSession, web
from aiohttp.resolver import ThreadedResolver
from aiohttp.test_utils import TestServer
from homeassistant.config_entries import ConfigEntries, ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from yarl import URL

from homeassistant import loader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest_asyncio.fixture
async def hass(tmp_path):
    instance = HomeAssistant(str(tmp_path))
    loader.async_setup(instance)
    instance.config_entries = ConfigEntries(instance, {})
    await instance.config_entries.async_initialize()
    await instance.async_start()
    resolver = ThreadedResolver()
    with patch(
        "homeassistant.helpers.aiohttp_client._async_get_or_create_resolver",
        return_value=resolver,
    ):
        yield instance
        await instance.async_block_till_done()
        await instance.async_stop()
    await resolver.close()


def make_entry(
    hass,
    *,
    data=None,
    version=2,
    gateway="gateway-1",
    options=None,
    state=ConfigEntryState.NOT_LOADED,
):
    entry = ConfigEntry(
        domain="vicare_rooms",
        title="ViCare Rooms",
        version=version,
        minor_version=1,
        data=data or {},
        options=options or {},
        unique_id=gateway,
        source="user",
        discovery_keys={},
        subentries_data=None,
        state=state,
    )
    # Register without setting up platforms or installing production dependencies.
    hass.config_entries._entries[entry.entry_id] = entry
    return entry


@pytest_asyncio.fixture
async def http_mock():
    """Run real HTTP requests against a local server instead of Viessmann."""
    responses = []

    async def handler(request):
        response = responses[int(request.match_info["index"])]
        return web.json_response(response["payload"], status=response["status"])

    app = web.Application()
    app.router.add_route("*", "/{index}", handler)
    server = TestServer(app)
    await server.start_server()
    original_request = ClientSession._request

    class Responses:
        def __init__(self):
            self.pending = {}
            self.requests = {}

        def post(self, url, *, payload=None, status=200):
            self.add("POST", url, payload, status)

        def get(self, url, *, payload=None, status=200):
            self.add("GET", url, payload, status)

        def add(self, method, url, payload, status):
            index = len(responses)
            responses.append({"payload": payload, "status": status})
            self.pending.setdefault((method, URL(url)), []).append(index)

        def __enter__(self):
            async def request(session, method, url, **kwargs):
                key = (method.upper(), URL(url))
                assert self.pending.get(key), f"Unexpected HTTP request: {key}"
                index = self.pending[key].pop(0)
                self.requests.setdefault(key, []).append(SimpleNamespace(kwargs=kwargs))
                return await original_request(
                    session, method, server.make_url(f"/{index}"), **kwargs
                )

            self.patch = patch.object(ClientSession, "_request", new=request)
            self.patch.start()
            return self

        def __exit__(self, *args):
            self.patch.stop()

    yield Responses()
    await server.close()
