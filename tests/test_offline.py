"""Offline operation of the connect path with a fake Casambi cloud.

Only the http transport and the bluetooth connection are replaced, so the
cache, session and update logic run as in production.
"""

import json
import pathlib
import pickle
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from bleak.backends.device import BLEDevice

from CasambiBt import (
    CACHE_VERSION,
    AuthenticationError,
    Casambi,
    CloudUnavailableError,
    NetworkOnlineUpdateNeededError,
    UnitControl,
    UnitControlType,
    UnitType,
)
from CasambiBt._network import _NetworkSession

UUID = "aabbccddeeff"
ADDRESS = "AA:BB:CC:DD:EE:FF"
NID = "net-1"
KEY = {"id": 1, "type": 1, "role": 3, "name": "k", "key": "00" * 16}
UNIT_TYPE = UnitType(
    42, "m", "v", "mode", 1, [UnitControl(UnitControlType.DIMMER, 0, 8, 0, False)]
)
FIXTURE = {
    "id": 42,
    "model": "m",
    "vendor": "v",
    "mode": "mode",
    "stateLength": 1,
    "controls": [
        {"type": "dimmer", "offset": 0, "length": 8, "default": 0, "readonly": False}
    ],
}


def network_json(revision: int = 5, units: int = 1) -> dict[str, Any]:
    return {
        "status": "OK",
        "network": {
            "name": "Home",
            "revision": revision,
            "protocolVersion": 10,
            "keyStore": {"keys": [KEY]},
            "units": [
                {
                    "type": 42,
                    "deviceID": i + 1,
                    "uuid": f"u{i + 1}",
                    "address": "a",
                    "name": f"Lamp {i + 1}",
                    "firmware": 1,
                }
                for i in range(units)
            ],
            "grid": {"cells": []},
            "scenes": [],
        },
    }


def make_cache(
    root: pathlib.Path, *, type_age_days: int = 0, session_valid: bool = True
) -> pathlib.Path:
    """Create the cache a previous online connect leaves behind."""
    entry = root / UUID
    entry.mkdir(parents=True)
    (root / ".cachever").write_text(str(CACHE_VERSION))
    (entry / "networkid").write_text(NID)
    (entry / f"{NID}.json").write_text(json.dumps(network_json()))
    expiry = datetime.now(UTC) + timedelta(days=28 - type_age_days)
    (entry / "types.pck").write_bytes(pickle.dumps({42: (UNIT_TYPE, expiry)}))
    session = _NetworkSession(
        "s",
        NID,
        True,
        1,
        datetime.now(UTC) + timedelta(days=1 if session_valid else -1),
    )
    (entry / "session.pck").write_bytes(pickle.dumps(session))
    return root


class FakeCloud:
    """A configurable fake of the Casambi cloud API."""

    def __init__(self) -> None:
        self.offline = False
        self.network_id_status = 200
        self.session_status = 200
        self.update_status = 200
        self.fixture_status = 200
        self.network = network_json()
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.offline:
            raise httpx.ConnectError("offline", request=request)
        path = request.url.path
        if path.startswith("/network/uuid/"):
            return httpx.Response(self.network_id_status, json={"id": NID})
        if path.endswith("/session"):
            expires = (datetime.now(UTC) + timedelta(days=7)).timestamp() * 1000
            return httpx.Response(
                self.session_status,
                json={
                    "session": "new",
                    "network": NID,
                    "manager": True,
                    "keyID": 1,
                    "expires": expires,
                },
            )
        if path.startswith("/fixture/"):
            return httpx.Response(self.fixture_status, json=FIXTURE)
        if path == f"/network/{NID}/":
            revision = json.loads(request.content)["revision"]
            if revision == self.network["network"]["revision"]:
                return httpx.Response(self.update_status, json={"status": "UPTODATE"})
            return httpx.Response(self.update_status, json=self.network)
        return httpx.Response(404)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))


@pytest.fixture
def cloud() -> FakeCloud:
    return FakeCloud()


@pytest.fixture(autouse=True)
def no_bluetooth():
    """Replace the bluetooth connection, the network data path is tested."""
    with patch.object(Casambi, "_connectClient", AsyncMock()) as connect:
        yield connect


async def connect(cloud: FakeCloud, cache: pathlib.Path, **kwargs: Any) -> Casambi:
    casa = Casambi(cloud.client(), cache)
    await casa.connect(BLEDevice(ADDRESS, "C", None), "pw", **kwargs)
    return casa


@pytest.mark.parametrize("session_valid", [True, False])
async def test_offline_with_cache(
    cloud: FakeCloud, tmp_path: pathlib.Path, session_valid: bool
) -> None:
    cloud.offline = True
    casa = await connect(cloud, make_cache(tmp_path, session_valid=session_valid))
    assert [u.name for u in casa.units] == ["Lamp 1"]
    assert casa.units[0].unitType == UNIT_TYPE


async def test_offline_with_expired_types(
    cloud: FakeCloud, tmp_path: pathlib.Path
) -> None:
    """Expired unit types are still used while the cloud is unreachable."""
    cloud.offline = True
    casa = await connect(cloud, make_cache(tmp_path, type_age_days=60))
    assert casa.units[0].unitType == UNIT_TYPE


@pytest.mark.parametrize(
    "configure",
    [
        lambda c: setattr(c, "network_id_status", 503),
        lambda c: setattr(c, "network_id_status", 403),
        lambda c: setattr(c, "session_status", 503),
        lambda c: setattr(c, "session_status", 429),
        lambda c: setattr(c, "update_status", 503),
        lambda c: setattr(c, "fixture_status", 500),
    ],
    ids=[
        "network-id-503",
        "network-id-403",
        "login-503",
        "login-429",
        "update-503",
        "fixture-500",
    ],
)
async def test_cloud_errors_fall_back_to_cache(
    cloud: FakeCloud, tmp_path: pathlib.Path, configure: Callable[[FakeCloud], None]
) -> None:
    """A cloud that answers with errors must not stop a cached network."""
    configure(cloud)
    casa = await connect(
        cloud, make_cache(tmp_path, type_age_days=60, session_valid=False)
    )
    assert [u.name for u in casa.units] == ["Lamp 1"]
    assert casa.units[0].unitType == UNIT_TYPE


async def test_wrong_password_is_reported(
    cloud: FakeCloud, tmp_path: pathlib.Path
) -> None:
    cloud.session_status = 401
    with pytest.raises(AuthenticationError) as err:
        await connect(cloud, make_cache(tmp_path, session_valid=False))
    assert err.value.status_code == 401


async def test_first_connect_needs_the_cloud(
    cloud: FakeCloud, tmp_path: pathlib.Path
) -> None:
    cloud.offline = True
    with pytest.raises(NetworkOnlineUpdateNeededError):
        await connect(cloud, tmp_path)


async def test_first_connect_cloud_error(
    cloud: FakeCloud, tmp_path: pathlib.Path
) -> None:
    cloud.session_status = 503
    with pytest.raises(NetworkOnlineUpdateNeededError):
        await connect(cloud, tmp_path)


async def test_unknown_unit_type_keeps_unit(
    cloud: FakeCloud, tmp_path: pathlib.Path
) -> None:
    """A unit whose type can't be fetched stays in the network."""
    cloud.fixture_status = 500
    casa = await connect(cloud, tmp_path)
    assert [u.name for u in casa.units] == ["Lamp 1"]
    assert casa.units[0].unitType.controls == []

    # Failures are not cached: the next connect fetches the type.
    cloud.fixture_status = 200
    casa = await connect(cloud, tmp_path)
    assert casa.units[0].unitType == UNIT_TYPE


async def test_prefer_cache_skips_the_cloud(
    cloud: FakeCloud, tmp_path: pathlib.Path
) -> None:
    casa = await connect(cloud, make_cache(tmp_path), preferCache=True)
    assert [u.name for u in casa.units] == ["Lamp 1"]
    assert cloud.requests == []


async def test_prefer_cache_without_cache_uses_the_cloud(
    cloud: FakeCloud, tmp_path: pathlib.Path
) -> None:
    casa = await connect(cloud, tmp_path, preferCache=True)
    assert [u.name for u in casa.units] == ["Lamp 1"]
    assert cloud.requests


async def test_refresh_network(cloud: FakeCloud, tmp_path: pathlib.Path) -> None:
    """A newer configuration is cached but the live units stay untouched."""
    cache = make_cache(tmp_path)
    casa = await connect(cloud, cache, preferCache=True)
    units = casa.units

    assert await casa.refreshNetwork("pw") is False

    cloud.network = network_json(revision=6, units=2)
    assert await casa.refreshNetwork("pw") is True
    assert casa.units is units
    assert casa.networkRevision == 5

    # The next connect uses the new configuration, even offline.
    cloud.offline = True
    casa = await connect(cloud, cache, preferCache=True)
    assert [u.name for u in casa.units] == ["Lamp 1", "Lamp 2"]
    assert casa.networkRevision == 6


async def test_refresh_network_errors(cloud: FakeCloud, tmp_path: pathlib.Path) -> None:
    casa = await connect(
        cloud, make_cache(tmp_path, session_valid=False), preferCache=True
    )

    cloud.session_status = 503
    with pytest.raises(CloudUnavailableError) as err:
        await casa.refreshNetwork("pw")
    assert err.value.status_code == 503

    cloud.session_status = 401
    with pytest.raises(AuthenticationError):
        await casa.refreshNetwork("pw")

    cloud.offline = True
    with pytest.raises(CloudUnavailableError):
        await casa.refreshNetwork("pw")


async def test_rotated_keys_replace_cached_keys(
    cloud: FakeCloud, tmp_path: pathlib.Path
) -> None:
    """Keys that changed in the cloud replace the cached ones."""
    cache = make_cache(tmp_path)
    casa = await connect(cloud, cache)
    assert casa._casaNetwork.keyStore.getKey().key == bytes(16)  # type: ignore[union-attr]

    new_key = {**KEY, "key": "11" * 16}
    cloud.network = network_json(revision=6)
    cloud.network["network"]["keyStore"]["keys"] = [new_key]
    casa = await connect(cloud, cache)
    assert casa._casaNetwork.keyStore.getKey().key == b"\x11" * 16  # type: ignore[union-attr]


async def test_connect_with_string_address(
    cloud: FakeCloud, tmp_path: pathlib.Path
) -> None:
    """An address without colons used to crash with UnboundLocalError."""
    cloud.offline = True
    casa = Casambi(cloud.client(), make_cache(tmp_path))
    await casa.connect("aabbccddeeff", "pw")
    assert [u.name for u in casa.units] == ["Lamp 1"]


async def test_connect_with_invalid_address(tmp_path: pathlib.Path) -> None:
    casa = Casambi(None, tmp_path)
    with pytest.raises(ValueError):
        await casa.connect("not-a-mac", "pw")
