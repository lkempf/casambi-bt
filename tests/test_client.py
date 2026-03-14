import asyncio
import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.backends.client import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import BleakNotFoundError
from cryptography.hazmat.primitives.asymmetric import ec

from CasambiBt._client import CasambiClientEvolution
from CasambiBt._constants import (
    CASA_AUTH_CHAR_UUID,
    MIN_EVO_VERSION,
    ConnectionState,
    IncomingPacketType,
)
from CasambiBt._network import Network
from CasambiBt.errors import (
    BluetoothDeviceNotFoundError,
    BluetoothError,
    ConnectionStateError,
    UnsupportedProtocolVersion,
)


@pytest.fixture
def mock_network() -> MagicMock:
    network = MagicMock(spec=Network)
    network.protocolVersion = 10
    network.keyStore = MagicMock()
    network.keyStore.getKey.return_value = None
    return network


@pytest.fixture
def data_callback() -> MagicMock:
    return MagicMock()


@pytest.fixture
def disconnected_callback() -> MagicMock:
    return MagicMock()


@pytest.fixture
def client(
    mock_network: MagicMock, data_callback: MagicMock, disconnected_callback: MagicMock
) -> CasambiClientEvolution:
    return CasambiClientEvolution(
        "00:11:22:33:44:55", data_callback, disconnected_callback, mock_network
    )


def test_init_valid(mock_network, data_callback, disconnected_callback):
    client = CasambiClientEvolution(
        "00:11:22:33:44:55", data_callback, disconnected_callback, mock_network
    )
    assert client.address == "00:11:22:33:44:55"
    assert client._connectionState == ConnectionState.NONE


def test_init_unsupported_version(mock_network, data_callback, disconnected_callback):
    mock_network.protocolVersion = MIN_EVO_VERSION - 1
    with pytest.raises(UnsupportedProtocolVersion):
        CasambiClientEvolution(
            "00:11:22:33:44:55", data_callback, disconnected_callback, mock_network
        )


async def test_connect_wrong_state(client):
    client._connectionState = ConnectionState.CONNECTED
    with pytest.raises(ConnectionStateError):
        await client.connect()


@patch("CasambiBt._client.get_device")
@patch("CasambiBt._client.establish_connection")
@patch("CasambiBt._client.close_stale_connections")
async def test_connect_success(mock_close, mock_establish, mock_get_device, client):
    mock_device = MagicMock(spec=BLEDevice)
    mock_get_device.return_value = mock_device
    mock_establish.return_value = AsyncMock()

    await client.connect()

    mock_get_device.assert_called_once_with("00:11:22:33:44:55")
    mock_close.assert_called_once_with(mock_device)
    mock_establish.assert_called_once()
    assert client._connectionState == ConnectionState.CONNECTED
    assert client._callbackTask is not None


@patch("CasambiBt._client.get_device")
async def test_connect_device_not_found(mock_get_device, client):
    mock_get_device.return_value = None

    with pytest.raises(BluetoothDeviceNotFoundError):
        await client.connect()


@patch("CasambiBt._client.get_device")
@patch("CasambiBt._client.establish_connection")
@patch("CasambiBt._client.close_stale_connections")
async def test_connect_bleak_not_found(
    mock_close, mock_establish, mock_get_device, client
):
    mock_device = MagicMock(spec=BLEDevice)
    mock_get_device.return_value = mock_device
    mock_establish.side_effect = BleakNotFoundError()

    with pytest.raises(BluetoothDeviceNotFoundError):
        await client.connect()


@patch("CasambiBt._client.get_device")
@patch("CasambiBt._client.establish_connection")
@patch("CasambiBt._client.close_stale_connections")
async def test_connect_bleak_error(mock_close, mock_establish, mock_get_device, client):
    mock_device = MagicMock(spec=BLEDevice)
    mock_get_device.return_value = mock_device
    mock_establish.side_effect = BleakError("error")

    with pytest.raises(BluetoothError):
        await client.connect()


async def test_disconnect(client):
    client._connectionState = ConnectionState.CONNECTED
    client._gattClient = AsyncMock()
    client._gattClient.is_connected = True
    client._callbackTask = asyncio.create_task(asyncio.sleep(1))

    await client.disconnect()

    client._gattClient.disconnect.assert_called_once()
    assert client._connectionState == ConnectionState.NONE
    assert client._callbackTask is None


def test_on_disconnect(client, disconnected_callback):
    client._connectionState = ConnectionState.AUTHENTICATED
    client._on_disconnect(MagicMock())
    disconnected_callback.assert_called_once()
    assert client._connectionState == ConnectionState.NONE


async def test_exchange_key_success(client):
    client._connectionState = ConnectionState.CONNECTED
    client._gattClient = AsyncMock()

    mock_nonce = b"1234567890123456"
    first_resp = struct.pack(">BBBHH16s", 0x1, 10, 23, 1, 0, mock_nonce)
    client._gattClient.read_gatt_char.return_value = first_resp

    device_priv = ec.generate_private_key(ec.SECP256R1())
    device_pub = device_priv.public_key().public_numbers()

    callback_data_1 = struct.pack(
        "<B32s32s",
        0x2,
        device_pub.x.to_bytes(32, byteorder="little", signed=False),
        device_pub.y.to_bytes(32, byteorder="little", signed=False),
    )

    callback_data_2 = struct.pack(">B", 0x3)

    async def mock_start_notify(*args, **kwargs):
        async def send_callbacks():
            await asyncio.sleep(0)
            client._exchNotifyCallback(None, callback_data_1)
            await asyncio.sleep(0.05)
            client._exchNotifyCallback(None, callback_data_2)

        asyncio.create_task(send_callbacks())  # noqa: RUF006

    client._gattClient.start_notify.side_effect = mock_start_notify

    await client.exchangeKey()

    client._gattClient.read_gatt_char.assert_called_once_with(CASA_AUTH_CHAR_UUID)
    client._gattClient.start_notify.assert_called_once()
    assert client._connectionState == ConnectionState.AUTHENTICATED
    assert hasattr(client, "_encryptor")


async def test_authenticate_success(client, mock_network):
    mock_key = MagicMock()
    mock_key.key = b"1234567890123456"
    mock_key.id = 1
    mock_network.keyStore.getKey.return_value = mock_key

    client._connectionState = ConnectionState.KEY_EXCHANGED
    client._gattClient = AsyncMock()
    client._nonce = b"1234567890123456"
    client._key = b"1234567890123456"
    client._encryptor = MagicMock()
    client._encryptor.encryptThenMac.return_value = b"encrypted_packet"

    async def mock_write(*args, **kwargs):
        async def send_callbacks():
            await asyncio.sleep(0)
            client._notifySignal.set()

        asyncio.create_task(send_callbacks())  # noqa: RUF006

    client._gattClient.write_gatt_char.side_effect = mock_write

    await client.authenticate()

    client._gattClient.write_gatt_char.assert_called_once()
    assert client._connectionState == ConnectionState.AUTHENTICATED


def test_parse_unit_states(client, data_callback):
    client._connectionState = ConnectionState.AUTHENTICATED
    data = b"\x02\x03\x01\x42"
    client._parseUnitStates(data)

    data_callback.assert_called_once_with(
        IncomingPacketType.UnitState,
        {"id": 2, "online": True, "on": True, "state": b"\x42"},
    )


async def test_authenticate_skip_no_key(client, mock_network):
    mock_network.keyStore.getKey.return_value = None
    client._connectionState = ConnectionState.KEY_EXCHANGED
    client._gattClient = AsyncMock()

    await client.authenticate()

    client._gattClient.write_gatt_char.assert_not_called()
    assert client._connectionState == ConnectionState.KEY_EXCHANGED


async def test_send_success(client):
    client._connectionState = ConnectionState.AUTHENTICATED
    client._gattClient = AsyncMock()
    client._nonce = b"1234567890123456"
    client._encryptor = MagicMock()
    client._encryptor.encryptThenMac.return_value = b"encrypted_payload"
    client._outPacketCount = 1

    packet_to_send = b"\x01\x02\x03"

    await client.send(packet_to_send)

    assert client._outPacketCount == 2
    client._encryptor.encryptThenMac.assert_called_once()
    client._gattClient.write_gatt_char.assert_called_once_with(
        CASA_AUTH_CHAR_UUID, b"encrypted_payload"
    )


async def test_send_wrong_state(client):
    client._connectionState = ConnectionState.CONNECTED
    with pytest.raises(ConnectionStateError):
        await client.send(b"\x01\x02")


def test_auth_notify_callback_invalid_sig(client):
    from cryptography.exceptions import InvalidSignature

    client._connectionState = ConnectionState.KEY_EXCHANGED
    client._nonce = b"1234567890123456"
    client._encryptor = MagicMock()
    client._encryptor.decryptAndVerify.side_effect = InvalidSignature()

    client._authNotifyCallback(None, b"1234" + b"invalid_data_that_fails_verification")

    assert client._connectionState == ConnectionState.ERROR


@pytest.mark.anyio
async def test_exchange_key_retries_on_transient_error(client):
    """read_gatt_char failing once then succeeding should not raise."""
    client._connectionState = ConnectionState.CONNECTED
    client._gattClient = AsyncMock()

    mock_nonce = b"1234567890123456"
    first_resp = struct.pack(">BBBHH16s", 0x1, 10, 23, 1, 0, mock_nonce)

    client._gattClient.read_gatt_char.side_effect = [
        BleakError("transient"),
        first_resp,
    ]

    device_priv = ec.generate_private_key(ec.SECP256R1())
    device_pub = device_priv.public_key().public_numbers()

    callback_data_1 = struct.pack(
        "<B32s32s",
        0x2,
        device_pub.x.to_bytes(32, byteorder="little", signed=False),
        device_pub.y.to_bytes(32, byteorder="little", signed=False),
    )
    callback_data_2 = struct.pack(">B", 0x3)

    async def mock_start_notify(*args, **kwargs):
        async def send_callbacks():
            await asyncio.sleep(0)
            client._exchNotifyCallback(None, callback_data_1)
            await asyncio.sleep(0.05)
            client._exchNotifyCallback(None, callback_data_2)

        asyncio.create_task(send_callbacks())  # noqa: RUF006

    client._gattClient.start_notify.side_effect = mock_start_notify

    await client.exchangeKey()

    assert client._gattClient.read_gatt_char.call_count == 2
    assert client._connectionState == ConnectionState.AUTHENTICATED


@pytest.mark.anyio
async def test_exchange_key_fails_after_max_retries(client):
    """read_gatt_char always failing should raise BluetoothError after 4 attempts (retries=2)."""
    from CasambiBt.errors import BluetoothError

    client._connectionState = ConnectionState.CONNECTED
    client._gattClient = AsyncMock()
    client._gattClient.read_gatt_char.side_effect = BleakError("persistent error")

    with pytest.raises(BluetoothError):
        await client.exchangeKey(retries=2)

    # initial attempt + 3 retries = 4 total (consistent with send() convention)
    assert client._gattClient.read_gatt_char.call_count == 4
