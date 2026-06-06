import asyncio
import logging
import struct
from abc import ABC, abstractmethod
from binascii import b2a_hex as b2a
from collections.abc import Callable
from hashlib import sha256
from typing import Any

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

from CasambiBt._switch import SwitchEventDecoder

from ._constants import (
    CASA_AUTH_CHAR_UUID,
    CLASSIC_AUTH_LEVEL_MANAGER,
    CLASSIC_AUTH_LEVEL_VISITOR,
    FIRST_EVO_VERSION,
    MAX_EVO_VERSION,
    MIN_EVO_VERSION,
    MIN_SUPPORTED_CLASSIC_VERSION,
    ConnectionState,
    IncomingPacketType,
)
from ._encryption import ClassicEncryptor, Encryptor
from ._network import Network

# We need to move these imports here to prevent a cycle.
from .errors import (  # noqa: E402
    BluetoothDeviceNotFoundError,
    BluetoothError,
    ConnectionStateError,
    ProtocolError,
    UnsupportedProtocolVersion,
)


class CasambiClient(ABC):
    def __init__(
        self,
        address_or_device: str | BLEDevice,
        dataCallback: Callable[[IncomingPacketType, Any], None],
        disonnectedCallback: Callable[[], None],
        network: Network,
    ) -> None:
        self._gattClient: BleakClient = None  # type: ignore[assignment]
        self._network = network

        self._mtu: int
        self._unitId: int
        self._flags: int

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
        self._switch_decoder = SwitchEventDecoder()
        self._connectionState: ConnectionState = ConnectionState.NONE
        self._dataCallback = dataCallback
        self._disconnectedCallback = disonnectedCallback
        self._activityLock = asyncio.Lock()

        self._logger.info(
            f"Initializing client for {self.address} with network version {network.protocolVersion}."
        )

        self._checkProtocolVersion(network.protocolVersion)

    @abstractmethod
    def _checkProtocolVersion(self, version: int) -> None:
        pass

    def _checkState(self, desired: ConnectionState) -> None:
        if self._connectionState != desired:
            raise ConnectionStateError(desired, self._connectionState)

    async def connect(self) -> None:
        self._checkState(ConnectionState.NONE)

        self._logger.info(f"Connection to {self.address}")

        # Reset packet counters
        self._outPacketCount = 1
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
            self._logger.error("Failed to discover unit.")
            raise BluetoothDeviceNotFoundError

        try:
            # If we are already connected to the device the key exchange will fail.
            await close_stale_connections(device)
            # TODO: Should we try to get access to the network name here?
            self._gattClient = await establish_connection(
                BleakClient, device, "Casambi Network", self._on_disconnect
            )
        except BleakNotFoundError as e:
            # Guess that this is the error reason since there are no better error types
            self._logger.error("Failed to find unit.", exc_info=True)
            raise BluetoothDeviceNotFoundError from e
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

    def _queueCallback(self, handle: BleakGATTCharacteristic, data: bytes) -> None:
        self._callbackQueue.put_nowait((handle, data))

    async def _processCallbacks(self) -> None:
        try:
            while True:
                handle, data = await self._callbackQueue.get()

                # Try to loose any races here.
                # Otherwise a state change caused by the last packet might not have been handled yet
                await asyncio.sleep(0.001)
                await self._activityLock.acquire()
                try:
                    self._callbackMulitplexer(handle, data)
                except Exception:
                    self._logger.error("Failed to process callback.", exc_info=True)
                finally:
                    self._callbackQueue.task_done()
                    self._activityLock.release()
        except TimeoutError:
            self._logger.info("Callback processing task cancelled.")

    def _callbackMulitplexer(
        self, handle: BleakGATTCharacteristic, data: bytes
    ) -> None:
        self._logger.debug(
            f"[CASAMBI_RAW_PACKET] Callback on handle {handle} in state {self._connectionState}: {b2a(data)}"
        )

        if self._connectionState == ConnectionState.CONNECTED:
            self._exchNotifyCallback(handle, data)
        elif self._connectionState == ConnectionState.KEY_EXCHANGED:
            self._authNotifyCallback(handle, data)
        elif self._connectionState == ConnectionState.AUTHENTICATED:
            self._inPacketCount += 1
            self._establishedNotifyCallback(handle, data)
        else:
            self._logger.warning(
                f"Unhandled notify in state {self._connectionState}: {b2a(data)}"
            )

    @abstractmethod
    async def exchangeKey(self, retries: int = 2) -> None:
        pass

    @abstractmethod
    def _exchNotifyCallback(self, handle: BleakGATTCharacteristic, data: bytes) -> None:
        pass

    @abstractmethod
    async def authenticate(self) -> None:
        pass

    @abstractmethod
    def _authNotifyCallback(self, handle: BleakGATTCharacteristic, data: bytes) -> None:
        pass

    @abstractmethod
    def _establishedNotifyCallback(
        self, handle: BleakGATTCharacteristic, data: bytes
    ) -> None:
        pass

    async def send(self, packet: bytes, retries: int = 2) -> None:
        self._checkState(ConnectionState.AUTHENTICATED)

        await self._activityLock.acquire()
        try:
            self._logger.debug(
                f"Sending packet {b2a(packet)} with counter {self._outPacketCount}"
            )
            retry = 0
            while True:
                try:
                    await self._sendInternal(packet)
                    break
                except BluetoothError:
                    retry += 1
                    if retry > retries:
                        raise
                    await asyncio.sleep(0.5)

            self._outPacketCount += 1
        finally:
            self._activityLock.release()

    @abstractmethod
    async def _sendInternal(self, packet: bytes) -> None:
        pass

    async def disconnect(self) -> None:
        self._logger.info("Disconnecting...")

        if self._callbackTask is not None:
            self._callbackTask.cancel()
            self._callbackTask = None

        if self._gattClient is not None and self._gattClient.is_connected:
            try:
                await self._gattClient.disconnect()
            except BleakError:
                self._logger.debug("Failed to disconnect BleakClient.", exc_info=True)

        self._connectionState = ConnectionState.NONE
        self._switch_decoder.reset()
        self._logger.info("Disconnected.")


class CasambiClientEvolution(CasambiClient):
    def __init__(
        self,
        address_or_device: str | BLEDevice,
        dataCallback: Callable[[IncomingPacketType, Any], None],
        disonnectedCallback: Callable[[], None],
        network: Network,
    ) -> None:
        self._nonce: bytes
        self._encryptor: Encryptor
        self._key: bytearray

        self._notifySignal = asyncio.Event()

        super().__init__(address_or_device, dataCallback, disonnectedCallback, network)

    def _checkProtocolVersion(self, version: int) -> None:
        if version < MIN_EVO_VERSION:
            raise UnsupportedProtocolVersion(
                f"Classic version aren't supported by this class. Your network version is {version}. Minimum version is {MIN_EVO_VERSION}."
            )
        if version > MAX_EVO_VERSION:
            self._logger.warning(
                "Version too new. Your network version is %i. Highest supported version is %i. This version is untested.",
                version,
                MAX_EVO_VERSION,
            )

    async def _wait_timeout(self, evt: asyncio.Event, timeout: int = 15) -> None:
        try:
            await asyncio.wait_for(evt.wait(), timeout)
        except TimeoutError as e:
            raise BluetoothError("Timed out while waiting for a response.") from e

    async def exchangeKey(self, retries: int = 2) -> None:
        self._checkState(ConnectionState.CONNECTED)

        self._logger.info("Starting key exchange...")

        await self._activityLock.acquire()
        try:
            # Initiate communication with device.  The initial GATT read can fail
            # transiently (e.g. ATT error 0x0e) if the device is not yet ready for
            # GATT operations immediately after connection.  Retry with the same
            # policy used by send().
            retry = 0
            while True:
                try:
                    firstResp = await self._gattClient.read_gatt_char(
                        CASA_AUTH_CHAR_UUID
                    )
                    break
                except BleakError as exc:
                    retry += 1
                    if retry > retries:
                        raise BluetoothError("Failed to initiate GATT read.") from exc
                    self._logger.debug(
                        "Transient error reading auth characteristic, retrying..."
                    )
                    await asyncio.sleep(0.5)
            self._logger.debug(f"Got {b2a(firstResp)}")

            # Check type and protocol version
            if not (
                firstResp[0] == 0x1 and firstResp[1] == self._network.protocolVersion
            ):
                if (
                    firstResp[0] == 0x1
                    and firstResp[1] == 0x2B
                    and self._network.protocolVersion == 11
                ):
                    # This is what happens for protocol version 11 so skip the error.
                    # TODO: Implement proper handling after understanding this behavior.
                    pass
                else:
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
            try:
                await self._gattClient.start_notify(
                    CASA_AUTH_CHAR_UUID,
                    self._queueCallback,
                    bluez={"use_start_notify": True},
                )
            except BleakError as exc:
                raise BluetoothError("Failed to initiate GATT notify.") from exc
        finally:
            self._activityLock.release()

        # Wait for key exchange, will get notified by _exchNotifyCallback
        await self._wait_timeout(self._notifySignal)
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
        except BleakError as exc:
            raise BluetoothError("GATT write failed during key exchange.") from exc
        finally:
            self._activityLock.release()

        # Wait for success response from _exchNotifyCallback
        await self._wait_timeout(self._notifySignal)
        await self._activityLock.acquire()
        try:
            self._notifySignal.clear()
            if self._connectionState == ConnectionState.ERROR:  # type: ignore[comparison-overlap]
                raise ProtocolError("Failed to negotiate key!")
            else:
                self._logger.info("Key exchange sucessful")
                self._encryptor = Encryptor(self._key)

                # Skip auth if the network doesn't use a key.
                if self._network.keyStore.getKey():
                    self._connectionState = ConnectionState.KEY_EXCHANGED
                else:
                    self._connectionState = ConnectionState.AUTHENTICATED
        finally:
            self._activityLock.release()

    def _exchNotifyCallback(self, handle: BleakGATTCharacteristic, data: bytes) -> None:
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
            self._key = bytearray()
            for i in range(16):
                self._key.append(digestedSecret[i] ^ digestedSecret[16 + i])

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

        self._logger.info("Authenticating channel...")
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
            hashFcnt.update(self._key)
            authDig = hashFcnt.digest()
            self._logger.debug(f"Auth digest: {b2a(authDig)}")

            # Send auth packet
            authPacket = int.to_bytes(1, 4, "little")
            authPacket += b"\x04"
            authPacket += key.id.to_bytes(1, "little")
            authPacket += authDig
            await self._writeEncPacket(authPacket, 1, CASA_AUTH_CHAR_UUID)
            self._outPacketCount += 1
        finally:
            self._activityLock.release()

        # Wait for auth response
        await self._wait_timeout(self._notifySignal)

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

    def _authNotifyCallback(self, handle: BleakGATTCharacteristic, data: bytes) -> None:
        self._logger.info("Processing authentication response...")

        # TODO: Verify counter
        self._inPacketCount += 1

        try:
            self._encryptor.decryptAndVerify(data, data[:4] + self._nonce[4:])
        except InvalidSignature:
            self._logger.fatal("Invalid signature for auth response!")
            self._connectionState = ConnectionState.ERROR
            return

        # TODO: Verify Digest 2 (to compare with response from device); SHA256(key.key||self pubKey point||self._key)

        self._notifySignal.set()

    def _establishedNotifyCallback(
        self, handle: BleakGATTCharacteristic, data: bytes
    ) -> None:
        # TODO: Check incoming counter and direction flag

        try:
            packetContents = self._encryptor.decryptAndVerify(
                data, data[:4] + self._nonce[4:]
            )
        except InvalidSignature:
            # We only drop packets with invalid signature here instead of going into an error state
            self._logger.error(f"Invalid signature for packet {b2a(data)}!")
            return

        packetType = packetContents[0]
        self._logger.debug(f"Incoming data of type {packetType}: {b2a(packetContents)}")

        # Log decrypted packet with special marker
        self._logger.debug(
            f"[CASAMBI_DECRYPTED] Type={packetType} #{self._inPacketCount}: {b2a(packetContents)}"
        )

        if packetType == IncomingPacketType.UnitState:
            self._parseUnitStates(packetContents[1:])
        elif packetType == IncomingPacketType.SwitchEvent:
            for s in self._switch_decoder.decode(
                packetContents[1:], self._inPacketCount
            ):
                self._dataCallback(IncomingPacketType.SwitchEvent, s)
        elif packetType == IncomingPacketType.NetworkConfig:
            # We don't care about the config the network thinks it has.
            # We assume that cloud config and local config match.
            # If there is a mismatch the user can solve it using the app.
            # In the future we might want to parse the revision and issue a warning if there is a mismatch.
            pass
        else:
            self._logger.debug(f"Packet type {packetType} not implemented. Ignoring!")

    def _parseUnitStates(self, data: bytes) -> None:
        self._logger.debug("Parsing incoming unit states...")
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
                    IncomingPacketType.UnitState,
                    {"id": id, "online": online, "on": on, "state": state},
                )

                oldPos = pos
        except IndexError:
            self._logger.error(
                f"Ran out of data while parsing unit state! Remaining data {b2a(data[oldPos:])} in {b2a(data)}."
            )

    async def _sendInternal(self, packet: bytes) -> None:
        counter = int.to_bytes(self._outPacketCount, 4, "little")
        headerPaket = counter + b"\x07" + packet

        self._logger.debug(f"Packet with header: {b2a(headerPaket)}")

        await self._writeEncPacket(
            headerPaket, self._outPacketCount, CASA_AUTH_CHAR_UUID
        )

    async def _writeEncPacket(
        self, packet: bytes, id: int, char: str | BleakGATTCharacteristic
    ) -> None:
        encPacket = self._encryptor.encryptThenMac(packet, self._getNonce(id))
        try:
            await self._gattClient.write_gatt_char(char, encPacket)
        except BleakError as e:
            if e.args[0] == "Not connected":
                self._logger.debug(
                    "Unexpected write while disconnected.", exc_info=True
                )
                self._connectionState = ConnectionState.NONE
            else:
                raise BluetoothError from e

    def _getNonce(self, id: int | bytes) -> bytes:
        if isinstance(id, int):
            id = id.to_bytes(4, "little")
        return self._nonce[:4] + id + self._nonce[8:]


class CasambiClientClassic(CasambiClient):
    """This is a client implementation for conformant classic networks."""

    def __init__(
        self,
        address_or_device: str | BLEDevice,
        dataCallback: Callable[[IncomingPacketType, Any], None],
        disonnectedCallback: Callable[[], None],
        network: Network,
    ) -> None:
        super().__init__(address_or_device, dataCallback, disonnectedCallback, network)
        self._connhash: bytes

        visitorKey = network.keyStore.getLegacyKey(CLASSIC_AUTH_LEVEL_VISITOR)
        if not visitorKey:
            raise ProtocolError("Can't continue without visitor key.")
        self._visitorEncryptor = ClassicEncryptor(visitorKey.key, 4)

        self._managerEncryptor: ClassicEncryptor | None
        managerKey = network.keyStore.getLegacyKey(CLASSIC_AUTH_LEVEL_MANAGER)
        if managerKey:
            self._managerEncryptor = ClassicEncryptor(managerKey.key, 16)
        else:
            self._managerEncryptor = None
            self._logger.warning(
                "No manager key in keystore. Manager level packets won't be handled correctly."
            )

    def _checkProtocolVersion(self, version: int) -> None:
        if version >= FIRST_EVO_VERSION:
            raise UnsupportedProtocolVersion(
                "Evolution networks aren't supported by this class."
            )

        if version < MIN_SUPPORTED_CLASSIC_VERSION:
            raise UnsupportedProtocolVersion(
                f"Network version {version} is too old. Nonconformant classic networks currently not supported."
                f"Minimum supported version is {MIN_SUPPORTED_CLASSIC_VERSION}."
            )

    async def exchangeKey(self, retries: int = 2) -> None:
        self._checkState(ConnectionState.CONNECTED)

        self._logger.info("Starting key exchange...")

        await self._activityLock.acquire()
        try:
            # Initiate communication with device.  The initial GATT read can fail
            # transiently (e.g. ATT error 0x0e) if the device is not yet ready for
            # GATT operations immediately after connection.  Retry with the same
            # policy used by send().
            retry = 0
            while True:
                try:
                    firstResp = await self._gattClient.read_gatt_char(
                        CASA_AUTH_CHAR_UUID
                    )
                    break
                except BleakError as exc:
                    retry += 1
                    if retry > retries:
                        raise BluetoothError("Failed to initiate GATT read.") from exc
                    self._logger.debug(
                        "Transient error reading auth characteristic, retrying..."
                    )
                    await asyncio.sleep(0.5)
            self._logger.debug(f"Got {b2a(firstResp)}")

            # Parse device info
            (
                self._connhash,
                self._unit,
                flags_lo,
                self._mtu,
                protocolVersion,
                flags_high,
            ) = struct.unpack_from(">8sBBBBB", firstResp)
            self._flags = flags_lo | (flags_high << 8)

            if protocolVersion != self._network.protocolVersion:
                self._logger.warning(
                    "Device reported unexpected version. Was %i, expected %i.",
                    protocolVersion,
                    self._network.protocolVersion,
                )

            self._logger.debug(
                f"Parsed mtu {self._mtu}, unit {self._unit}, flags {self._flags}, connhash {b2a(self._connhash)}"
            )

            self._logger.debug("Starting notify")
            try:
                await self._gattClient.start_notify(
                    CASA_AUTH_CHAR_UUID,
                    self._queueCallback,
                    bluez={"use_start_notify": True},
                )
            except BleakError as exc:
                raise BluetoothError("Failed to initiate GATT notify.") from exc
            self._connectionState = ConnectionState.KEY_EXCHANGED
        finally:
            self._activityLock.release()

    def _exchNotifyCallback(self, handle: BleakGATTCharacteristic, data: bytes) -> None:
        raise ProtocolError(
            "Refusing to handle callback at this time for classic network."
        )

    async def authenticate(self) -> None:
        self._checkState(ConnectionState.KEY_EXCHANGED)

        await self._activityLock.acquire()
        try:
            # We only send the version for now and not the time.
            self._logger.info("Sending version.")
            await self._sendInternal(b"\x00\x01\x0b")
            # Manually increment since we have to bypass send due to locking.
            self._outPacketCount += 1

            self._connectionState = ConnectionState.AUTHENTICATED
        finally:
            self._activityLock.release()

    def _authNotifyCallback(self, handle: BleakGATTCharacteristic, data: bytes) -> None:
        raise ProtocolError(
            "Refusing to handle callback at this time for classic network."
        )

    def _establishedNotifyCallback(
        self, handle: BleakGATTCharacteristic, data: bytes
    ) -> None:
        self._logger.debug(f"Incoming data: {b2a(data)}")

        unitId = data[0]
        if unitId == 0x00:
            # Network config. Skipping.
            pass
        elif unitId == 0xFF:
            # Log marker. Skipping.
            pass
        elif unitId == 0xF0:
            # Response
            pass
        else:
            pos = 0
            while pos < len(data):
                if pos + 2 > len(data):
                    self._logger.error(f"Failed to find header at {pos}. Abort.")
                    break

                flags = data[pos + 1]

                stateLen = flags & 0x0F
                prio = flags & 0x10 != 0
                extra1 = flags & 0x20 != 0
                extra2 = flags & 0x40 != 0
                online = flags & 0x80 != 0

                statePos = pos + 2
                extra1Val = -1
                extra2Val = -1

                if extra1:
                    extra1Val = data[statePos]
                    statePos += 1
                if extra2:
                    extra2Val = data[statePos]
                    statePos += 1

                if statePos + stateLen > len(data):
                    self._logger.error(
                        f"Failed to find message of length {stateLen + (statePos - pos)} at pos {pos}. Abort."
                    )
                    break

                unitId = data[pos]
                state = data[statePos : statePos + stateLen]

                self._logger.debug(
                    f"Parsed state: Len {stateLen}, id {unitId}, prio {prio}, online {online}, extra1 {extra1Val}, extra2 {extra2Val}, state {b2a(state)}."
                )

                # It's ok to pass anything as on. The value will only be used if no appropriate controls are available.
                self._dataCallback(
                    IncomingPacketType.UnitState,
                    {"id": unitId, "online": online, "on": True, "state": state},
                )

                pos = statePos + stateLen

    async def _sendInternal(self, packet: bytes) -> None:
        sequence = int.to_bytes(self._outPacketCount & 0xFFFF, 2, "big")
        if sequence == b"\0":
            sequence = b"\x01"
            self._outPacketCount += 1

        outPacket = sequence + packet
        if self._managerEncryptor:
            outPacket = b"\x03" + self._managerEncryptor.digest(
                outPacket, self._connhash
            )
        else:
            outPacket = b"\x02" + self._visitorEncryptor.digest(
                outPacket, self._connhash
            )

        self._logger.debug(f"Packet with header: {b2a(outPacket)}")

        try:
            await self._gattClient.write_gatt_char(CASA_AUTH_CHAR_UUID, outPacket)
        except BleakError as e:
            if e.args[0] == "Not connected":
                self._logger.debug(
                    "Unexpected write while disconnected.", exc_info=True
                )
                self._connectionState = ConnectionState.NONE
            else:
                raise BluetoothError from e
