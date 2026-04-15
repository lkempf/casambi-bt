"""Tests for the Network module."""

import json
import pathlib
import pickle
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from CasambiBt._cache import Cache
from CasambiBt._network import (
    SESSION_CACHE_FILE,
    TYPES_CACHE_FILE,
    TYPES_CACHE_VERSION,
    Network,
    _NetworkSession,
)
from CasambiBt._unit import UnitType
from CasambiBt.errors import (
    AuthenticationError,
    NetworkNotFoundError,
    NetworkOnlineUpdateNeededError,
    NetworkUpdateError,
)


@pytest.fixture
async def cache(tmp_path: pathlib.Path) -> AsyncGenerator[Cache, None]:
    """Provide a cache instance mapped to a temporary directory."""
    c = Cache(tmp_path)
    await c.setUuid("test-uuid")
    await c.invalidateCache()
    yield c


@pytest.fixture
def mock_client() -> AsyncMock:
    """Provide a mock AsyncClient."""
    return AsyncMock(spec=httpx.AsyncClient)


@pytest.fixture
def network(mock_client: AsyncMock, cache: Cache) -> Network:
    """Provide a Network instance initialized with mock dependencies."""
    return Network("test-uuid", mock_client, cache)


def test_session_expired():
    """Test session expiration logic."""
    session = _NetworkSession(
        session="token",
        network="network-id",
        manager=True,
        keyID=1,
        expires=datetime.now(UTC) - timedelta(minutes=1),
    )
    assert session.expired() is True

    session.expires = datetime.now(UTC) + timedelta(minutes=1)
    assert session.expired() is False


async def test_network_init(network: Network):
    """Test the initialization state of a Network instance."""
    assert network._uuid == "test-uuid"
    assert network._session is None
    assert network.authenticated() is False
    assert network.protocolVersion == -1


async def test_get_network_id_from_cache(
    network: Network, cache: Cache, mock_client: AsyncMock
):
    """Test that the network ID is retrieved correctly when cached."""
    async with cache as cache_path:
        await (cache_path / "networkid").write_text("cached-id")

    mock_client.get.return_value = httpx.Response(200, json={"id": "cached-id"})

    await network.getNetworkId()
    assert network._id == "cached-id"


async def test_get_network_id_from_api(network: Network, mock_client: AsyncMock):
    """Test that the network ID is fetched from the API when not cached."""
    mock_client.get.return_value = httpx.Response(200, json={"id": "api-id"})

    await network.getNetworkId()

    assert network._id == "api-id"
    mock_client.get.assert_called_once_with(
        "https://api.casambi.com/network/uuid/test-uuid"
    )


async def test_get_network_id_api_not_found(network: Network, mock_client: AsyncMock):
    """Test handling of 404 response when fetching the network ID."""
    mock_client.get.return_value = httpx.Response(404)
    with pytest.raises(NetworkNotFoundError):
        await network.getNetworkId()


async def test_get_network_id_api_request_error_with_cache(
    network: Network, mock_client: AsyncMock, cache: Cache
):
    """Test fallback to cached network ID when API request fails."""
    async with cache as cache_path:
        await (cache_path / "networkid").write_text("cached-id")

    mock_client.get.side_effect = httpx.RequestError("Error")
    await network.getNetworkId()
    assert network._id == "cached-id"


async def test_get_network_id_api_request_error_no_cache(
    network: Network, mock_client: AsyncMock
):
    """Test handling of API request error when no cache is available."""
    mock_client.get.side_effect = httpx.RequestError("Error")
    with pytest.raises(NetworkOnlineUpdateNeededError):
        await network.getNetworkId()


async def test_get_network_id_force_offline_with_cache(network: Network, cache: Cache):
    """Test that forceOffline works correctly when cache is present."""
    async with cache as cache_path:
        await (cache_path / "networkid").write_text("cached-id")

    await network.getNetworkId(forceOffline=True)
    assert network._id == "cached-id"


async def test_get_network_id_force_offline_no_cache(network: Network):
    """Test that forceOffline raises an error when cache is missing."""
    with pytest.raises(NetworkOnlineUpdateNeededError):
        await network.getNetworkId(forceOffline=True)


async def test_login_success(network: Network, mock_client: AsyncMock):
    """Test successful login and session caching."""
    mock_client.get.return_value = httpx.Response(200, json={"id": "api-id"})

    session_data = {
        "session": "test-session",
        "network": "api-id",
        "manager": True,
        "keyID": 1,
        "expires": (datetime.now().timestamp() + 3600) * 1000,
        "role": 3,
    }
    mock_client.post.return_value = httpx.Response(200, json=session_data)

    await network.logIn("password")

    assert network.authenticated() is True
    assert network._session is not None
    assert network._session.session == "test-session"
    mock_client.post.assert_called_once()

    # Check if session was cached
    async with network._cache as cache_path:
        assert await (cache_path / SESSION_CACHE_FILE).exists()


async def test_login_failure(network: Network, mock_client: AsyncMock):
    """Test handling of a failed login attempt."""
    mock_client.get.return_value = httpx.Response(200, json={"id": "api-id"})
    mock_client.post.return_value = httpx.Response(401, text="Unauthorized")

    with pytest.raises(AuthenticationError):
        await network.logIn("wrong-password")


async def test_update_not_authenticated(network: Network):
    """Test that updating an unauthenticated network raises an error."""
    with pytest.raises(AuthenticationError):
        await network.update()


async def test_update_success(network: Network, mock_client: AsyncMock):
    """Test successful network data update via API."""
    network._session = _NetworkSession(
        "sess", "net", True, 1, datetime.now(UTC) + timedelta(days=1)
    )
    network._id = "test-net"

    network_data = {
        "status": "UPDATED",
        "network": {
            "revision": 2,
            "name": "My Network",
            "protocolVersion": 1,
            "units": [],
            "grid": {"cells": []},
            "scenes": [],
        },
    }
    mock_client.put.return_value = httpx.Response(
        200, json=network_data, content=json.dumps(network_data).encode()
    )

    await network.update()

    assert network._networkRevision == 2
    assert network._networkName == "My Network"
    assert network._protocolVersion == 1
    assert network.units == []
    assert network.groups == []
    assert network.scenes == []

    # Check if network data was cached
    async with network._cache as cache_path:
        assert await (cache_path / f"{network._id}.json").exists()


async def test_update_force_offline_with_cache(network: Network):
    """Test offline network update using cached data."""
    network._id = "test-net"
    network_data = {
        "status": "UPTODATE",
        "network": {
            "revision": 3,
            "name": "Cached Network",
            "protocolVersion": 2,
            "units": [],
            "grid": {"cells": []},
            "scenes": [],
        },
    }
    async with network._cache as cache_path:
        await (cache_path / f"{network._id}.json").write_bytes(
            json.dumps(network_data).encode()
        )

    await network.update(forceOffline=True)
    assert network._networkRevision == 3
    assert network._networkName == "Cached Network"


async def test_update_force_offline_no_cache(network: Network):
    """Test offline update raises an error when no cache is present."""
    network._id = "test-net"
    with pytest.raises(NetworkOnlineUpdateNeededError):
        await network.update(forceOffline=True)


async def test_update_api_gone_invalidates_cache(
    network: Network, mock_client: AsyncMock, cache: Cache
):
    """Test that a 410 GONE response during update invalidates the cache."""
    network._session = _NetworkSession(
        "sess", "net", True, 1, datetime.now(UTC) + timedelta(days=1)
    )
    network._id = "test-net"

    mock_client.put.return_value = httpx.Response(410)  # GONE

    with patch.object(
        cache, "invalidateCache", new_callable=AsyncMock
    ) as mock_invalidate:
        with pytest.raises(NetworkUpdateError):
            await network.update()

        mock_invalidate.assert_called_once()


async def test_load_session_and_types(network: Network, cache: Cache):
    """Test loading session and unit type information from cache."""
    session = _NetworkSession(
        session="token",
        network="network-id",
        manager=True,
        keyID=1,
        expires=datetime.now(UTC) + timedelta(days=1),
    )
    unit_types: dict[int, tuple[UnitType | None, datetime]] = {
        1: (None, datetime.now(UTC))
    }

    async with cache as cache_path:
        await (cache_path / SESSION_CACHE_FILE).write_bytes(pickle.dumps(session))
        await (cache_path / TYPES_CACHE_FILE).write_bytes(
            pickle.dumps((TYPES_CACHE_VERSION, unit_types))
        )

    await network._loadSession()
    await network._loadTypeCache()

    assert network._session is not None
    assert network._session.session == "token"
    assert network._unitTypes == unit_types


async def test_load_type_cache_correct_version(network: Network, cache: Cache):
    """Test that a correctly versioned cache is accepted."""
    unit_types: dict[int, tuple[UnitType | None, datetime]] = {
        42: (None, datetime.now(UTC))
    }
    async with cache as cache_path:
        await (cache_path / TYPES_CACHE_FILE).write_bytes(
            pickle.dumps((TYPES_CACHE_VERSION, unit_types))
        )

    await network._loadTypeCache()
    assert network._unitTypes == unit_types


async def test_load_type_cache_outdated_version(network: Network, cache: Cache):
    """Test that an outdated cache version is discarded."""
    unit_types: dict[int, tuple[UnitType | None, datetime]] = {
        99: (None, datetime.now(UTC))
    }
    async with cache as cache_path:
        await (cache_path / TYPES_CACHE_FILE).write_bytes(
            pickle.dumps((TYPES_CACHE_VERSION - 1, unit_types))
        )

    await network._loadTypeCache()
    assert network._unitTypes == {}


async def test_load_type_cache_legacy_unversioned(network: Network, cache: Cache):
    """Test that a legacy plain-dict cache (no version tuple) is discarded."""
    unit_types: dict[int, tuple[UnitType | None, datetime]] = {
        7: (None, datetime.now(UTC))
    }
    async with cache as cache_path:
        # Write a legacy payload — plain dict, no version wrapper
        await (cache_path / TYPES_CACHE_FILE).write_bytes(pickle.dumps(unit_types))

    await network._loadTypeCache()
    assert network._unitTypes == {}


async def test_save_and_reload_type_cache(network: Network, cache: Cache):
    """Test that the type cache save/reload roundtrip preserves data."""
    unit_types: dict[int, tuple[UnitType | None, datetime]] = {
        5: (None, datetime.now(UTC))
    }
    network._unitTypes = unit_types

    await network._saveTypeCache()
    network._unitTypes = {}
    await network._loadTypeCache()

    assert network._unitTypes == unit_types


async def test_update_parse_units(network: Network, mock_client: AsyncMock):
    """Test parsing of units during network update."""
    network._session = _NetworkSession(
        "sess", "net", True, 1, datetime.now(UTC) + timedelta(days=1)
    )
    network._id = "test-net"

    network_data = {
        "status": "UPDATED",
        "network": {
            "revision": 2,
            "name": "My Network",
            "protocolVersion": 10,
            "units": [
                {
                    "type": 10,
                    "deviceID": 1,
                    "uuid": "unit-uuid",
                    "address": "00:11:22:33:44:55",
                    "name": "My Unit",
                    "firmware": "1.0",
                }
            ],
            "grid": {"cells": []},
            "scenes": [],
        },
    }
    mock_client.put.return_value = httpx.Response(
        200, json=network_data, content=json.dumps(network_data).encode()
    )
    mock_client.get.return_value = httpx.Response(
        200,
        json={
            "id": 10,
            "model": "Test Model",
            "vendor": "Test Vendor",
            "mode": "Test Mode",
            "stateLength": 4,
            "controls": [],
        },
    )

    await network.update()

    assert len(network.units) == 1
    unit = network.units[0]
    assert unit.deviceId == 1
    assert unit.uuid == "unit-uuid"
    assert unit.address == "00:11:22:33:44:55"
    assert unit.name == "My Unit"
    assert unit.firmwareVersion == "1.0"
    assert unit.unitType.id == 10
    assert unit._isClassic is False


async def test_update_parse_groups(network: Network, mock_client: AsyncMock):
    """Test parsing of groups (cells) during network update."""
    network._session = _NetworkSession(
        "sess", "net", True, 1, datetime.now(UTC) + timedelta(days=1)
    )
    network._id = "test-net"

    network_data = {
        "status": "UPDATED",
        "network": {
            "revision": 2,
            "name": "My Network",
            "protocolVersion": 10,
            "units": [
                {
                    "type": 10,
                    "deviceID": 1,
                    "uuid": "unit-uuid",
                    "address": "00:11:22:33:44:55",
                    "name": "My Unit",
                    "firmware": "1.0",
                }
            ],
            "grid": {
                "cells": [
                    {
                        "type": 2,
                        "groupID": 100,
                        "name": "My Group",
                        "cells": [{"type": 1, "unit": 1}],
                    }
                ]
            },
            "scenes": [],
        },
    }
    mock_client.put.return_value = httpx.Response(
        200, json=network_data, content=json.dumps(network_data).encode()
    )
    mock_client.get.return_value = httpx.Response(
        200,
        json={
            "id": 10,
            "model": "Test Model",
            "vendor": "Test Vendor",
            "mode": "Test Mode",
            "stateLength": 4,
            "controls": [],
        },
    )

    await network.update()

    assert len(network.groups) == 1
    group = network.groups[0]
    assert group.groudId == 100
    assert group.name == "My Group"
    assert len(group.units) == 1
    assert group.units[0].deviceId == 1


async def test_update_parse_scenes(network: Network, mock_client: AsyncMock):
    """Test parsing of scenes during network update."""
    network._session = _NetworkSession(
        "sess", "net", True, 1, datetime.now(UTC) + timedelta(days=1)
    )
    network._id = "test-net"

    network_data = {
        "status": "UPDATED",
        "network": {
            "revision": 2,
            "name": "My Network",
            "protocolVersion": 10,
            "units": [],
            "grid": {"cells": []},
            "scenes": [{"sceneID": 200, "name": "My Scene"}],
        },
    }
    mock_client.put.return_value = httpx.Response(
        200, json=network_data, content=json.dumps(network_data).encode()
    )

    await network.update()

    assert len(network.scenes) == 1
    scene = network.scenes[0]
    assert scene.sceneId == 200
    assert scene.name == "My Scene"


async def test_update_classic_network(network: Network, mock_client: AsyncMock):
    """Test successful network data update via API for a classic network."""
    network._session = _NetworkSession(
        "sess", "net", True, 1, datetime.now(UTC) + timedelta(days=1)
    )
    network._id = "test-net"

    network_data = {
        "status": "UPDATED",
        "network": {
            "revision": 2,
            "name": "Classic Network",
            "protocolVersion": 5,
            "units": [
                {
                    "type": 10,
                    "deviceID": 1,
                    "uuid": "unit-uuid",
                    "address": "00:11:22:33:44:55",
                    "name": "My Unit",
                    "firmware": "1.0",
                }
            ],
            "grid": {"cells": []},
            "scenes": [],
        },
    }
    mock_client.put.return_value = httpx.Response(
        200, json=network_data, content=json.dumps(network_data).encode()
    )
    mock_client.get.return_value = httpx.Response(
        200,
        json={
            "id": 10,
            "model": "Test Model",
            "vendor": "Test Vendor",
            "mode": "Test Mode",
            "stateLength": 4,
            "controls": [],
        },
    )

    await network.update()

    assert network.protocolVersion == 5
    assert len(network.units) == 1
    assert network.units[0]._isClassic is True
