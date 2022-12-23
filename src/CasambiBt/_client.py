import asyncio
import logging
import struct
from binascii import b2a_hex as b2a
from enum import IntEnum, unique
from hashlib import sha256
from typing import Any, Awaitable, Callable, Dict, Union

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.client import BLEDevice
from bleak.exc import BleakDBusError, BleakError
from bleak_retry_connector import establish_connection, get_device
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ec

from ._constants import CASA_AUTH_CHAR_UUID
from ._encryption import Encryptor
from ._keystore import KeyStore


@unique
class ConnectionState(IntEnum):
    NONE = 0
    CONNECTED = 1
    KEY_EXCHANGED = 2
    AUTHENTICATED = 3
    ERROR = 99


from .errors import (
    BluetoothError,
    BluetoothNotReadyError,
    ConnectionStateError,
    NetworkNotFoundError,
    ProtocolError,
)


@unique
class IncommingPacketType(IntEnum):
    UnitState = 6


class CasambiClient:
    _gattClient: BleakClient
    _notifySignal: asyncio.Event

    _mtu: int
    _unitId: int
    _flags: int
    _nonce: bytes
    _key: bytearray

    _encryptor: Encryptor

    _outPacketCount: int
    _inPacketCount: int

    _callbackQueue: asyncio.Queue[tuple[int, bytes]]
    _callbackTask: asyncio.Task[None] | None

    def __init__(
        self,
        address_or_device: Union[str, BLEDevice],
        dataCallback: Callable[[IncommingPacketType, Dict[str, Any]], None],
        disonnectedCallback: Callable[[], None],
    ) -> None:
        self._address_or_devive = address_or_device
        self.address = (
            address_or_device.address
            if isinstance(address_or_device, BLEDevice)
            else address_or_device
        )
        self._logger = logging.getLogger(__name__)
        self._connectionState = ConnectionState.NONE
        self._dataCallback = dataCallback
        self._disconnectedCallback = disonnectedCallback
        self._sendLock = asyncio.Lock()

    def _checkState(self, desired: ConnectionState) -> None:
        if self._connectionState != desired:
            raise ConnectionStateError(desired, self._connectionState)

    async def connect(self) -> Awaitable[None]:
        self._checkState(ConnectionState.NONE)

        self._logger.info(f"Connection to {self.address}")

        # Reset packet counters
        self._outPacketCount = 2
        self._inPacketCount = 1

        # Reset callback queue
        self._callbackQueue = asyncio.Queue()
        self._callbackTask = asyncio.create_task(self._processCallbacks())

        # To use bleak_retry_connector we need to have a BLEDevice so get one if we only have the address.
        device = (
            self._address_or_devive
            if isinstance(self._address_or_devive, BLEDevice)
            else await get_device(self.address)
        )

        try:
            # TODO: Should we try to get access to the network name here?
            self._gattClient = await establish_connection(
                BleakClient, device, "Casambi Network", self._on_disconnect
            )
        # TODO: Update expected exception types for bleak_retry_connector.
        except BleakDBusError as e:
            self._logger.error("Failed to connect.", exc_info=1)
            if e.dbus_error == "org.bluez.Error.NotReady":
                raise BluetoothNotReadyError(e.dbus_error, e.dbus_error_details)
            else:
                raise BluetoothError(e.dbus_error, e.dbus_error_details)
        except BleakError:
            # Guess that this is the error reason since ther are no better error types
            self._logger.error("Failed to find client.", exc_info=1)
            raise NetworkNotFoundError()

        self._logger.info(f"Connected to {self.address}")
        self._connectionState = ConnectionState.CONNECTED

    def _on_disconnect(self, client: BleakClient) -> None:
        self._logger.info(f"Received disconnect callback from {self.address}")
        self._connectionState = ConnectionState.NONE
        self._disconnectedCallback()

    async def exchangeKey(self) -> Awaitable[None]:
        self._checkState(ConnectionState.CONNECTED)

        self._logger.info("Starting key exchange...")

        # Initiate communication with device
        firstResp = await self._gattClient.read_gatt_char(CASA_AUTH_CHAR_UUID)
        self._logger.debug(f"Got {b2a(firstResp)}")

        # Check type and protocol version
        if not (firstResp[0] == 0x1 and firstResp[1] == 0xA):
            self._connectionState = ConnectionState.ERROR
            raise ProtocolError(
                "Unexpected answer from device! Wrong device or protocol version?"
            )

        # Parse device info
        self._mtu, self._unit, self._flags, self._nonce = struct.unpack_from(
            ">BHH16s", firstResp, 2
        )
        self._logger.debug(
            f"Parsed mtu {self._mtu}, unit {self._unit}, flags {self._flags}, nonce {b2a(self._nonce)}"
        )

        # Device will initiate key exchange, so listen for that
        self._notifySignal = asyncio.Event()
        self._logger.debug(f"Starting notify")
        await self._gattClient.start_notify(CASA_AUTH_CHAR_UUID, self._queueCallback)

        # Wait for key exchange, will get notified by _exchNotifyCallback
        await self._notifySignal.wait()
        self._notifySignal.clear()
        if self._connectionState == ConnectionState.ERROR:
            raise ProtocolError("Invalid key exchange initiation.")

        # Respond to key exchange
        pubNums = self._pubKey.public_numbers()
        keyExchResponse = struct.pack(
            ">B32s32sB",
            0x2,
            pubNums.x.to_bytes(32, byteorder="little", signed=False),
            pubNums.y.to_bytes(32, byteorder="little", signed=False),
            0x1,
        )
        await self._gattClient.write_gatt_char(CASA_AUTH_CHAR_UUID, keyExchResponse)

        # Wait for success response from _exchNotifyCallback
        await self._notifySignal.wait()
        self._notifySignal.clear()
        if self._connectionState == ConnectionState.ERROR:
            raise ProtocolError("Failed to negotiate key!")
        else:
            self._logger.info("Key exchange sucessful")
            self._connectionState = ConnectionState.KEY_EXCHANGED

    def _queueCallback(self, handle: int, data: bytes) -> None:
        self._callbackQueue.put_nowait((handle, data))

    async def _processCallbacks(self) -> None:
        while True:
            handle, data = await self._callbackQueue.get()
            try:
                self._callbackMulitplexer(handle, data)
            finally:
                self._callbackQueue.task_done()

    def _callbackMulitplexer(self, handle: int, data: bytes) -> None:
        self._logger.debug(f"Callback on handle {handle}: {b2a(data)}")

        if self._connectionState == ConnectionState.CONNECTED:
            self._exchNofityCallback(handle, data)
        elif self._connectionState == ConnectionState.KEY_EXCHANGED:
            self._authNofityCallback(handle, data)
        elif self._connectionState == ConnectionState.AUTHENTICATED:
            self._establishedNofityCallback(handle, data)
        else:
            self._logger.warning(
                f"Unhandled notify in state {self._connectionState}: {b2a(data)}"
            )

    def _exchNofityCallback(self, handle: int, data: bytes) -> None:
        if data[0] == 0x2:
            # Parse device pubkey
            x, y = struct.unpack_from("<32s32s", data, 1)
            x = int.from_bytes(x, byteorder="little")
            y = int.from_bytes(y, byteorder="little")
            self._logger.debug(f"Got public key {x}, {y}")

            self._devicePubKey = ec.EllipticCurvePublicNumbers(
                x, y, ec.SECP256R1()
            ).public_key()

            # Generate key pair for client
            self._privKey = ec.generate_private_key(ec.SECP256R1())
            self._pubKey = self._privKey.public_key()

            # Generate shared secret
            secret = bytearray(self._privKey.exchange(ec.ECDH(), self._devicePubKey))
            secret.reverse()
            hashAlgo = sha256()
            hashAlgo.update(secret)
            digestedSecret = hashAlgo.digest()

            # Compute transport key
            self._transportKey = bytearray()
            for i in range(16):
                self._transportKey.append(digestedSecret[i] ^ digestedSecret[16 + i])

            # Inform exchangeKey that packet has been parsed
            self._notifySignal.set()

        elif data[0] == 0x3:
            if len(data) == 1:
                # Key exchange is acknowledged by device
                self._notifySignal.set()
            else:
                self._logger.error(
                    f"Unexpected package length for key exchange response: {b2a(data)}"
                )
                self._connectionState = ConnectionState.ERROR
                self._notifySignal.set()
        else:
            self._logger.error(f"Unexcpedted package type in {b2a(data)}.")
            self._connectionState = ConnectionState.ERROR
            self._notifySignal.set()

    async def authenticate(self, keystore: KeyStore) -> Awaitable[None]:
        self._checkState(ConnectionState.KEY_EXCHANGED)

        self._logger.info(f"Authenicating channel...")
        key = keystore.getKey()  # Session key

        if not key:
            raise ValueError("No key in keystore")

        self._encryptor = Encryptor(self._transportKey)

        # Compute client auth digest
        hashFcnt = sha256()
        hashFcnt.update(key.key)
        hashFcnt.update(self._nonce)
        hashFcnt.update(self._transportKey)
        authDig = hashFcnt.digest()
        self._logger.debug(f"Auth digest: {b2a(authDig)}")

        # Send auth packet
        authPacket = int.to_bytes(1, 4, "little")
        authPacket += b"\x04"
        authPacket += key.id.to_bytes(1, "little")
        authPacket += authDig
        await self._writeEncPacket(authPacket, 1, CASA_AUTH_CHAR_UUID)

        # Wait for auth response
        await self._notifySignal.wait()
        self._notifySignal.clear()
        if self._connectionState == ConnectionState.ERROR:
            raise ProtocolError("Failed to verify authentication response.")
        else:
            self._connectionState = ConnectionState.AUTHENTICATED
            self._logger.info("Authentication successful")

    def _authNofityCallback(self, handle: int, data: bytes) -> None:
        self._logger.info("Processing authentication response...")

        # TODO: Verify counter
        self._inPacketCount += 1

        try:
            response = self._encryptor.decryptAndVerify(
                data, data[:4] + self._nonce[4:]
            )
        except InvalidSignature:
            self._logger.fatal("Invalid signature for auth response!")
            self._connectionState = ConnectionState.ERROR
            return

        # TODO: Verify Digest 2 (to compare with response from device); SHA256(key.key||self pubKey point||self._transportKey)

        self._notifySignal.set()

    async def _writeEncPacket(
        self, packet: bytes, id: int, char: BleakGATTCharacteristic
    ) -> Awaitable[None]:
        encPacket = self._encryptor.encryptThenMac(packet, self._getNonce(id))
        try:
            await self._gattClient.write_gatt_char(char, encPacket)
        except BleakError as e:
            if e.args == "Not connected":
                self._connectionState = ConnectionState.NONE
            else:
                raise e

    def _getNonce(self, id: Union[int, bytes]) -> bytes:
        if isinstance(id, int):
            id = id.to_bytes(4, "little")
        return self._nonce[:4] + id + self._nonce[8:]

    async def send(self, packet: bytes) -> Awaitable[None]:
        self._checkState(ConnectionState.AUTHENTICATED)

        await self._sendLock.acquire()
        try:
            self._logger.debug(
                f"Sending packet {b2a(packet)} with counter {self._outPacketCount}"
            )

            counter = int.to_bytes(self._outPacketCount, 4, "little")
            headerPaket = counter + b"\x07" + packet

            self._logger.debug(f"Packet with header: {b2a(headerPaket)}")

            await self._writeEncPacket(
                headerPaket, self._outPacketCount, CASA_AUTH_CHAR_UUID
            )
            self._outPacketCount += 1
        finally:
            self._sendLock.release()

    def _establishedNofityCallback(self, handle: int, data: bytes) -> None:
        # TODO: Check incoming counter and direction flag
        self._inPacketCount += 1

        try:
            data = self._encryptor.decryptAndVerify(data, data[:4] + self._nonce[4:])
        except InvalidSignature:
            # We only drop packets with invalid signature here instead of going into an error state
            self._logger.error(f"Invalid signature for packet {b2a(data)}!")
            return

        packetType = data[0]
        self._logger.debug(f"Incoming data of type {packetType}: {b2a(data)}")

        if packetType == IncommingPacketType.UnitState:
            self._parseUnitStates(data[1:])
        else:
            self._logger.warning(f"Packet type {packetType} not implemented. Ignoring!")

    def _parseUnitStates(self, data: bytes) -> None:
        self._logger.info("Parsing incoming unit states...")
        self._logger.debug(f"Incoming unit state: {b2a(data)}")

        pos = 0
        oldPos = 0
        try:
            while pos <= len(data) - 4:
                id = data[pos]
                flags = data[pos + 1]
                stateLen = ((data[pos + 2] >> 4) & 15) + 1
                prio = data[pos + 2] & 15
                pos += 3

                online = flags & 2 != 0
                on = flags & 1 != 0

                if flags & 4:
                    pos += 1  # TODO: con?
                if flags & 8:
                    pos += 1  # TODO: sid?
                if flags & 16:
                    pos += 1  # Unkown value

                state = data[pos : pos + stateLen]
                pos += stateLen

                pos += (flags >> 6) & 3  # Padding?

                self._logger.debug(
                    f"Parsed state: Id {id}, prio {prio}, online {online}, on {on}, state {b2a(state)}1"
                )

                self._dataCallback(
                    IncommingPacketType.UnitState,
                    {"id": id, "online": online, "on": on, "state": state},
                )

                oldPos = pos
        except IndexError:
            self._logger.error(
                f"Ran out of data while parsing unit state! Remaining data {b2a(data[oldPos:])} in {b2a(data)}."
            )

    async def disconnect(self) -> Awaitable[None]:
        self._logger.info(f"Disconnecting...")

        if self._callbackTask:
            self._callbackTask.cancel()
            self._callbackTask = None

        if self._gattClient.is_connected:
            await self._gattClient.disconnect()

        self._connectionState = ConnectionState.NONE
        self._logger.info(f"Disconnected.")
