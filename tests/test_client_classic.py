import struct
from unittest.mock import AsyncMock, MagicMock

import pytest

from CasambiBt._client import CasambiClientClassic
from CasambiBt._constants import (
    CASA_AUTH_CHAR_UUID,
    CLASSIC_AUTH_LEVEL_MANAGER,
    CLASSIC_AUTH_LEVEL_VISITOR,
    FIRST_EVO_VERSION,
    MIN_SUPPORTED_CLASSIC_VERSION,
    ConnectionState,
    IncomingPacketType,
)
from CasambiBt._network import Network
from CasambiBt.errors import ProtocolError, UnsupportedProtocolVersion


@pytest.fixture
def mock_network() -> MagicMock:
    network = MagicMock(spec=Network)
    network.protocolVersion = 5
    network.keyStore = MagicMock()

    # Setup mock keys
    visitor_key = MagicMock()
    visitor_key.key = b"1234567890123456"
    manager_key = MagicMock()
    manager_key.key = b"1234567890123456"

    def getLegacyKey(level):
        if level == CLASSIC_AUTH_LEVEL_VISITOR:
            return visitor_key
        elif level == CLASSIC_AUTH_LEVEL_MANAGER:
            return manager_key
        return None

    network.keyStore.getLegacyKey.side_effect = getLegacyKey
    return network


@pytest.fixture
def mock_network_no_manager(mock_network) -> MagicMock:
    visitor_key = mock_network.keyStore.getLegacyKey(CLASSIC_AUTH_LEVEL_VISITOR)

    def getLegacyKey(level):
        if level == CLASSIC_AUTH_LEVEL_VISITOR:
            return visitor_key
        return None

    mock_network.keyStore.getLegacyKey.side_effect = getLegacyKey
    return mock_network


@pytest.fixture
def mock_network_no_visitor(mock_network) -> MagicMock:
    mock_network.keyStore.getLegacyKey.side_effect = None
    mock_network.keyStore.getLegacyKey.return_value = None
    return mock_network


@pytest.fixture
def data_callback() -> MagicMock:
    return MagicMock()


@pytest.fixture
def disconnected_callback() -> MagicMock:
    return MagicMock()


@pytest.fixture
def client(
    mock_network: MagicMock, data_callback: MagicMock, disconnected_callback: MagicMock
) -> CasambiClientClassic:
    return CasambiClientClassic(
        "00:11:22:33:44:55", data_callback, disconnected_callback, mock_network
    )


def test_init_valid(mock_network, data_callback, disconnected_callback):
    client = CasambiClientClassic(
        "00:11:22:33:44:55", data_callback, disconnected_callback, mock_network
    )
    assert client.address == "00:11:22:33:44:55"
    assert client._connectionState == ConnectionState.NONE
    assert client._visitorEncryptor is not None
    assert client._managerEncryptor is not None


def test_init_no_manager(mock_network_no_manager, data_callback, disconnected_callback):
    client = CasambiClientClassic(
        "00:11:22:33:44:55",
        data_callback,
        disconnected_callback,
        mock_network_no_manager,
    )
    assert client._visitorEncryptor is not None
    assert client._managerEncryptor is None


def test_init_no_visitor(mock_network_no_visitor, data_callback, disconnected_callback):
    with pytest.raises(ProtocolError):
        CasambiClientClassic(
            "00:11:22:33:44:55",
            data_callback,
            disconnected_callback,
            mock_network_no_visitor,
        )


def test_init_unsupported_version_too_new(
    mock_network, data_callback, disconnected_callback
):
    mock_network.protocolVersion = FIRST_EVO_VERSION
    with pytest.raises(UnsupportedProtocolVersion):
        CasambiClientClassic(
            "00:11:22:33:44:55", data_callback, disconnected_callback, mock_network
        )


def test_init_unsupported_version_too_old(
    mock_network, data_callback, disconnected_callback
):
    mock_network.protocolVersion = MIN_SUPPORTED_CLASSIC_VERSION - 1
    with pytest.raises(UnsupportedProtocolVersion):
        CasambiClientClassic(
            "00:11:22:33:44:55", data_callback, disconnected_callback, mock_network
        )


async def test_exchange_key_success(client):
    client._connectionState = ConnectionState.CONNECTED
    client._gattClient = AsyncMock()

    mock_connhash = b"12345678"
    first_resp = struct.pack(">8sBBBBB", mock_connhash, 1, 0, 23, 5, 0)
    client._gattClient.read_gatt_char.return_value = first_resp

    await client.exchangeKey()

    client._gattClient.read_gatt_char.assert_called_once_with(CASA_AUTH_CHAR_UUID)
    client._gattClient.start_notify.assert_called_once()
    assert client._connectionState == ConnectionState.KEY_EXCHANGED
    assert client._connhash == mock_connhash


def test_exchNotifyCallback(client):
    with pytest.raises(ProtocolError):
        client._exchNotifyCallback(MagicMock(), b"")


async def test_authenticate_success(client):
    client._connectionState = ConnectionState.KEY_EXCHANGED

    # Mock _sendInternal to avoid needing a full encryption setup in this test
    client._sendInternal = AsyncMock()

    await client.authenticate()

    client._sendInternal.assert_called_once_with(b"\x00\x01\x0b")
    assert client._connectionState == ConnectionState.AUTHENTICATED
    assert client._outPacketCount == 1  # Incremented from 0 (init) to 1


def test_authNotifyCallback(client):
    with pytest.raises(ProtocolError):
        client._authNotifyCallback(MagicMock(), b"")


def test_establishedNotifyCallback_unit_state(client, data_callback):
    # Construct a valid unit state packet: unitId, flags (with stateLen 1, online 1), state
    # flags = 0x81 (128 for online + 1 for stateLen)
    data = b"\x02\x81\x42"
    client._establishedNotifyCallback(None, data)

    data_callback.assert_called_once_with(
        IncomingPacketType.UnitState,
        {"id": 2, "online": True, "on": True, "state": b"\x42"},
    )


async def test_sendInternal_manager(client):
    client._connectionState = ConnectionState.AUTHENTICATED
    client._gattClient = AsyncMock()
    client._connhash = b"12345678"
    client._managerEncryptor = MagicMock()
    client._managerEncryptor.digest.return_value = b"encrypted_packet"

    await client._sendInternal(b"\x12\x34")

    client._managerEncryptor.digest.assert_called_once()
    client._gattClient.write_gatt_char.assert_called_once()
    args = client._gattClient.write_gatt_char.call_args[0]
    assert args[0] == CASA_AUTH_CHAR_UUID
    assert args[1].startswith(b"\x03")


async def test_sendInternal_visitor(
    mock_network_no_manager, data_callback, disconnected_callback
):
    client = CasambiClientClassic(
        "00:11:22:33:44:55",
        data_callback,
        disconnected_callback,
        mock_network_no_manager,
    )
    client._connectionState = ConnectionState.AUTHENTICATED
    client._gattClient = AsyncMock()
    client._connhash = b"12345678"
    client._visitorEncryptor = MagicMock()
    client._visitorEncryptor.digest.return_value = b"encrypted_packet"

    await client._sendInternal(b"\x12\x34")

    client._visitorEncryptor.digest.assert_called_once()
    client._gattClient.write_gatt_char.assert_called_once()
    args = client._gattClient.write_gatt_char.call_args[0]
    assert args[0] == CASA_AUTH_CHAR_UUID
    assert args[1].startswith(b"\x02")
