import asyncio
import logging
import struct
from binascii import b2a_hex as b2a
from collections.abc import Callable
from enum import IntEnum, unique
from hashlib import sha256
from typing import Any, Final

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.client import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakNotFoundError,
    close_stale_connections,
    establish_connection,
    get_device,
)
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ec

from ._constants import CASA_AUTH_CHAR_UUID, ConnectionState
from ._encryption import Encryptor
from ._network import Network

# We need to move these imports here to prevent a cycle.
from .errors import (  # noqa: E402
    BluetoothError,
    ConnectionStateError,
    NetworkNotFoundError,
    ProtocolError,
    UnsupportedProtocolVersion,
)


@unique
class IncommingPacketType(IntEnum):
    UnitState = 6
    SwitchEvent = 7
    NetworkConfig = 9


MIN_VERSION: Final[int] = 10
MAX_VERSION: Final[int] = 10


class CasambiClient:
    def __init__(
        self,
        address_or_device: str | BLEDevice,
        dataCallback: Callable[[IncommingPacketType, dict[str, Any]], None],
        disonnectedCallback: Callable[[], None],
        network: Network,
    ) -> None:
        self._gattClient: BleakClient = None  # type: ignore[assignment]
        self._notifySignal = asyncio.Event()
        self._network = network

        self._mtu: int
        self._unitId: int
        self._flags: int
        self._nonce: bytes
        self._key: bytearray

        self._encryptor: Encryptor

        self._outPacketCount = 0
        self._inPacketCount = 0

        self._callbackQueue: asyncio.Queue[tuple[BleakGATTCharacteristic, bytes]]
        self._callbackTask: asyncio.Task[None] | None = None

        self._address_or_devive = address_or_device
        self.address = (
            address_or_device.address
            if isinstance(address_or_device, BLEDevice)
            else address_or_device
        )
        self._logger = logging.getLogger(__name__)
        self._connectionState: ConnectionState = ConnectionState.NONE
        self._dataCallback = dataCallback
        self._disconnectedCallback = disonnectedCallback
        self._activityLock = asyncio.Lock()

        self._checkProtocolVersion(network.protocolVersion)

    def _checkProtocolVersion(self, version: int) -> None:
        if version < MIN_VERSION:
            raise UnsupportedProtocolVersion(
                f"Legacy version aren't supported currently. Your network version is {version}. Minimum version is {MIN_VERSION}."
            )
        if version > MAX_VERSION:
            self._logger.warning(
                "Version too new. Your network version is %i. Highest supported version is %i. Continue at your own risk.",
                version,
                MAX_VERSION,
            )

    def _checkState(self, desired: ConnectionState) -> None:
        if self._connectionState != desired:
            raise ConnectionStateError(desired, self._connectionState)

    async def connect(self) -> None:
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

        if not device:
            self._logger.error("Failed to discover client.")
            raise NetworkNotFoundError

        try:
            # If we are already connected to the device the key exchange will fail.
            await close_stale_connections(device)
            # TODO: Should we try to get access to the network name here?
            self._gattClient = await establish_connection(
                BleakClient, device, "Casambi Network", self._on_disconnect
            )
        except BleakNotFoundError as e:
            # Guess that this is the error reason since ther are no better error types
            self._logger.error("Failed to find client.", exc_info=True)
            raise NetworkNotFoundError from e
        except BleakError as e:
            self._logger.error("Failed to connect.", exc_info=True)
            raise BluetoothError(e.args) from e
        except Exception as e:
            self._logger.error("Unkown connection failure.", exc_info=True)
            raise BluetoothError from e

        self._logger.info(f"Connected to {self.address}")
        self._connectionState = ConnectionState.CONNECTED

    def _on_disconnect(self, client: BleakClient) -> None:
        if self._connectionState != ConnectionState.NONE:
            self._logger.info(f"Received disconnect callback from {self.address}")
        if self._connectionState == ConnectionState.AUTHENTICATED:
            self._logger.debug("Executing disconnect callback.")
            self._disconnectedCallback()
        self._connectionState = ConnectionState.NONE

    async def exchangeKey(self) -> None:
        self._checkState(ConnectionState.CONNECTED)

        self._logger.info("Starting key exchange...")

        await self._activityLock.acquire()
        try:
            # Initiate communication with device
            firstResp = await self._gattClient.read_gatt_char(CASA_AUTH_CHAR_UUID)
            self._logger.debug(f"Got {b2a(firstResp)}")

            # Check type and protocol version
            if not (
                firstResp[0] == 0x1 and firstResp[1] == self._network.protocolVersion
            ):
                self._logger.error(
                    "Unexpected answer from device! Wrong device or protocol version? Trying to continue."
                )

            # Parse device info
            self._mtu, self._unit, self._flags, self._nonce = struct.unpack_from(
                ">BHH16s", firstResp, 2
            )
            self._logger.debug(
                f"Parsed mtu {self._mtu}, unit {self._unit}, flags {self._flags}, nonce {b2a(self._nonce)}"
            )

            # Device will initiate key exchange, so listen for that
            self._logger.debug("Starting notify")
            await self._gattClient.start_notify(
                CASA_AUTH_CHAR_UUID, self._queueCallback
            )
        finally:
            self._activityLock.release()

        # Wait for key exchange, will get notified by _exchNotifyCallback
        await self._notifySignal.wait()
        await self._activityLock.acquire()
        try:
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
        finally:
            self._activityLock.release()

        # Wait for success response from _exchNotifyCallback
        await self._notifySignal.wait()
        await self._activityLock.acquire()
        try:
            self._notifySignal.clear()
            if self._connectionState == ConnectionState.ERROR:  # type: ignore[comparison-overlap]
                raise ProtocolError("Failed to negotiate key!")
            else:
                self._logger.info("Key exchange sucessful")
                self._encryptor = Encryptor(self._transportKey)

                # Skip auth if the network doesn't use a key.
                if self._network.keyStore.getKey():
                    self._connectionState = ConnectionState.KEY_EXCHANGED
                else:
                    self._connectionState = ConnectionState.AUTHENTICATED
        finally:
            self._activityLock.release()

    def _queueCallback(self, handle: BleakGATTCharacteristic, data: bytes) -> None:
        self._callbackQueue.put_nowait((handle, data))

    async def _processCallbacks(self) -> None:
        while True:
            handle, data = await self._callbackQueue.get()

            # Try to loose any races here.
            # Otherwise a state change caused by the last packet might not have been handled yet
            await asyncio.sleep(0.001)
            await self._activityLock.acquire()
            try:
                self._callbackMulitplexer(handle, data)
            finally:
                self._callbackQueue.task_done()
                self._activityLock.release()

    def _callbackMulitplexer(
        self, handle: BleakGATTCharacteristic, data: bytes
    ) -> None:
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

    def _exchNofityCallback(self, handle: BleakGATTCharacteristic, data: bytes) -> None:
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

    async def authenticate(self) -> None:
        self._checkState(ConnectionState.KEY_EXCHANGED)

        self._logger.info("Authenicating channel...")
        key = self._network.keyStore.getKey()  # Session key

        if not key:
            self._logger.info("No key in keystore. Skipping auth.")
            # The channel already has to be set to authenticated by exchangeKey.
            # This needs to be done there a non-handshake packet could be sent right after acking the key exch
            # and we don't want that packet to end up in _authNofityCallback.
            return

        await self._activityLock.acquire()
        try:
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
        finally:
            self._activityLock.release()

        # Wait for auth response
        await self._notifySignal.wait()

        await self._activityLock.acquire()
        try:
            self._notifySignal.clear()
            if self._connectionState == ConnectionState.ERROR:
                raise ProtocolError("Failed to verify authentication response.")
            else:
                self._connectionState = ConnectionState.AUTHENTICATED
                self._logger.info("Authentication successful")
        finally:
            self._activityLock.release()

    def _authNofityCallback(self, handle: BleakGATTCharacteristic, data: bytes) -> None:
        self._logger.info("Processing authentication response...")

        # TODO: Verify counter
        self._inPacketCount += 1

        try:
            self._encryptor.decryptAndVerify(data, data[:4] + self._nonce[4:])
        except InvalidSignature:
            self._logger.fatal("Invalid signature for auth response!")
            self._connectionState = ConnectionState.ERROR
            return

        # TODO: Verify Digest 2 (to compare with response from device); SHA256(key.key||self pubKey point||self._transportKey)

        self._notifySignal.set()

    async def _writeEncPacket(
        self, packet: bytes, id: int, char: str | BleakGATTCharacteristic
    ) -> None:
        encPacket = self._encryptor.encryptThenMac(packet, self._getNonce(id))
        try:
            await self._gattClient.write_gatt_char(char, encPacket)
        except BleakError as e:
            if e.args[0] == "Not connected":
                self._connectionState = ConnectionState.NONE
            else:
                raise e

    def _getNonce(self, id: int | bytes) -> bytes:
        if isinstance(id, int):
            id = id.to_bytes(4, "little")
        return self._nonce[:4] + id + self._nonce[8:]

    async def send(self, packet: bytes) -> None:
        self._checkState(ConnectionState.AUTHENTICATED)

        await self._activityLock.acquire()
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
            self._activityLock.release()

    def _establishedNofityCallback(
        self, handle: BleakGATTCharacteristic, data: bytes
    ) -> None:
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
        elif packetType == IncommingPacketType.SwitchEvent:
            self._parseSwitchEvent(data[1:])
        elif packetType == IncommingPacketType.NetworkConfig:
            # We don't care about the config the network thinks it has.
            # We assume that cloud config and local config match.
            # If there is a mismatch the user can solve it using the app.
            # In the future we might want to parse the revision and issue a warning if there is a mismatch.
            pass
        else:
            self._logger.info(f"Packet type {packetType} not implemented. Ignoring!")

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

    def _parseSwitchEvent(self, data: bytes) -> None:
        """Parse switch event packet which contains multiple message types"""
        self._logger.info(f"Parsing incoming switch event packet... Data: {b2a(data)}")

        pos = 0
        oldPos = 0
        try:
            while pos <= len(data) - 3:
                oldPos = pos
                
                # Parse message header
                message_type = data[pos]
                flags = data[pos + 1]
                length = ((data[pos + 2] >> 4) & 15) + 1
                parameter = data[pos + 2] & 15
                pos += 3

                # Check if we have enough data for the payload
                if pos + length > len(data):
                    self._logger.debug(
                        f"Incomplete message at position {oldPos}. "
                        f"Type: 0x{message_type:02x}, declared length: {length}, available: {len(data) - pos}"
                    )
                    break

                # Extract the payload
                payload = data[pos : pos + length]
                pos += length

                # Process based on message type
                if message_type == 0x08 or message_type == 0x10:  # Switch/button events
                    self._processSwitchMessage(message_type, flags, parameter, payload, data, oldPos)
                else:
                    # Log other message types for now
                    self._logger.debug(
                        f"Message type 0x{message_type:02x}: flags=0x{flags:02x}, "
                        f"param={parameter}, payload={b2a(payload)}"
                    )

                oldPos = pos

        except IndexError:
            self._logger.error(
                f"Ran out of data while parsing switch event packet! "
                f"Remaining data {b2a(data[oldPos:])} in {b2a(data)}."
            )

    def _processSwitchMessage(self, message_type: int, flags: int, button: int, payload: bytes, full_data: bytes, start_pos: int) -> None:
        """Process a switch/button message (types 0x08 or 0x10)"""
        if not payload:
            self._logger.error("Switch message has empty payload")
            return

        unit_id = payload[0]

        action = None
        if len(payload) > 1:
            action = payload[1]

        extra_data = b''
        if len(payload) > 2:
            extra_data = payload[2:]

        event_string = "unknown"
        
        # Different interpretation based on message type
        if message_type == 0x08:
            # Type 0x08: Use bit 1 of action for press/release
            if action is not None:
                is_release = (action >> 1) & 1
                event_string = "button_release" if is_release else "button_press"
        elif message_type == 0x10:
            # Type 0x10: Must check the additional state byte after the message
            # The action value is a counter that increments with each state change
            additional_data_pos = start_pos + 3 + len(payload)
            if additional_data_pos + 2 < len(full_data):
                state_byte = full_data[additional_data_pos + 1]
                if state_byte == 0x01:
                    event_string = "button_press"
                elif state_byte == 0x02:
                    event_string = "button_release"
                else:
                    self._logger.warning(f"Unknown state byte: 0x{state_byte:02x}")
            else:
                self._logger.warning("Type 0x10 message missing state byte information")

        action_display = f"{action:#04x}" if action is not None else "N/A"

        self._logger.info(
            f"Switch event (type 0x{message_type:02x}): button={button}, unit_id={unit_id}, "
            f"action={action_display} ({event_string}), flags=0x{flags:02x}"
        )

        self._dataCallback(
            IncommingPacketType.SwitchEvent,
            {
                "message_type": message_type,
                "button": button,
                "unit_id": unit_id,
                "action": action,
                "event": event_string,
                "flags": flags,
                "extra_data": extra_data,
            },
        )

    async def disconnect(self) -> None:
        self._logger.info("Disconnecting...")

        if self._callbackTask is not None:
            self._callbackTask.cancel()
            self._callbackTask = None

        if self._gattClient is not None and self._gattClient.is_connected:
            try:
                await self._gattClient.disconnect()
            except Exception:
                self._logger.error("Failed to disconnect BleakClient.", exc_info=True)

        self._connectionState = ConnectionState.NONE
        self._logger.info("Disconnected.")
