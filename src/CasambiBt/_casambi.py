import asyncio
import logging
from binascii import b2a_hex as b2a
from collections.abc import Callable, Mapping
from copy import copy
from pathlib import Path
from typing import Any, Final, cast

from bleak.backends.device import BLEDevice
from httpx import AsyncClient, RequestError

from CasambiBt._constants import IncomingPacketType
from CasambiBt._switch import SwitchEvent

from ._backup import createBackup, restoreBackup
from ._cache import Cache
from ._client import (
    CasambiClient,
    CasambiClientClassic,
    CasambiClientEvolution,
    ConnectionState,
)
from ._constants import isClassicNetwork, normalizeAddress
from ._network import Network
from ._operation import (
    OpCode,
    OperationsContext,
    OperationsContextClassic,
    OperationsContextEvolution,
)
from ._unit import Group, Scene, Unit, UnitControl, UnitControlType, UnitState
from .errors import BluetoothError, CloudUnavailableError, ConnectionStateError

# Upper bound for the reconnect a command attempts on a broken connection.
SEND_RECONNECT_TIMEOUT: Final = 30


class Casambi:
    """Class to manage one Casambi network.

    This is the central point of interaction and should be preferred to dealing with the internal components,
    e.g. ``Network`` or ``CasambiClient``, directly.
    """

    def __init__(
        self,
        httpClient: AsyncClient | None = None,
        cachePath: Path | None = None,
    ) -> None:
        self._casaClient: CasambiClient | None = None
        self._casaNetwork: Network | None = None

        self._unitChangedCallbacks: list[Callable[[Unit], None]] = []
        self._switchEventCallbacks: list[Callable[[SwitchEvent], None]] = []
        self._disconnectCallbacks: list[Callable[[], None]] = []
        self._connectionLock = asyncio.Lock()

        self._logger = logging.getLogger(__name__)
        self._opContext: OperationsContext
        self._ownHttpClient = httpClient is None
        self._httpClient = httpClient

        self._cache = Cache(cachePath)
        self._bleDeviceCallback: Callable[[], BLEDevice | None] | None = None

    def _checkNetwork(self) -> None:
        if not self._casaNetwork or not self._casaNetwork._networkRevision:
            raise ConnectionStateError(
                ConnectionState.AUTHENTICATED,
                ConnectionState.NONE,
                "Network information missing.",
            )

    @property
    def networkName(self) -> str:
        self._checkNetwork()
        return self._casaNetwork._networkName  # type: ignore

    @property
    def networkId(self) -> str:
        self._checkNetwork()
        return self._casaNetwork._id  # type: ignore

    @property
    def units(self) -> list[Unit]:
        """Get the units in the network if connected.

        :return: A list of all units in the network.
        :raises ConnectionStateError: There is no connection to the network.
        """
        self._checkNetwork()
        return self._casaNetwork.units  # type: ignore

    @property
    def groups(self) -> list[Group]:
        """Get the groups in the network if connected.

        :return: A list of all groups in the network.
        :raises ConnectionStateError: There is no connection to the network.
        """
        self._checkNetwork()
        return self._casaNetwork.groups  # type: ignore

    @property
    def scenes(self) -> list[Scene]:
        """Get the scenes of the network if connected.

        :return: A list of all scenes in the network.
        :raises ConnectionStateError: There is no connection to the network.
        """
        self._checkNetwork()
        return self._casaNetwork.scenes  # type: ignore

    @property
    def connected(self) -> bool:
        """Check whether there is an active connection to the network."""
        return (
            self._casaClient is not None
            and self._casaClient._connectionState == ConnectionState.AUTHENTICATED
        )

    async def connect(
        self,
        addr_or_device: str | BLEDevice,
        password: str,
        forceOffline: bool = False,
        preferCache: bool = False,
        bleDeviceCallback: Callable[[], BLEDevice | None] | None = None,
    ) -> None:
        """Connect and authenticate to a network.

        :param addr_or_device: The MAC address of the network or a BLEDevice. Use `discover` to find the address of a network.
        :param password: The password for the network.
        :param forceOffline: Whether to avoid contacting the casambi servers.
        :param preferCache: Use the cached network configuration without
            contacting the casambi servers if one exists. Use `refreshNetwork`
            to check for a newer configuration afterwards.
        :param bleDeviceCallback: Returns the current BLEDevice of the network,
            used by the connection retries (e.g. when a proxy changed).
        :raises AuthenticationError: The supplied password is invalid.
        :raises ProtocolError: The network did not follow the expected protocol.
        :raises NetworkNotFoundError: No network was found under the supplied address.
        :raises NetworkOnlineUpdateNeededError: An offline update isn't possible in the current state.
        :raises NetworkUpdateError: The network configuration is malformed.
        :raises BluetoothError: An error occurred in the bluetooth stack.
        :raises BluetoothDeviceNotFoundError: The bluetooth device belonging to the network can't be found.
        """

        if isinstance(addr_or_device, BLEDevice):
            addr = addr_or_device.address
        else:
            addr = normalizeAddress(addr_or_device)
            addr_or_device = addr

        self._logger.info("Trying to connect to casambi network %s...", addr)

        async with self._connectionLock:
            if self._casaClient is not None:
                # Never leak the connection of a previous connect.
                await self._casaClient.disconnect()
                self._casaClient = None

            if not self._httpClient:
                self._httpClient = AsyncClient()

            # Retrieve network information
            uuid = addr.replace(":", "").lower()
            await self._cache.setUuid(uuid)
            self._casaNetwork = Network(uuid, self._httpClient, self._cache)
            await self._casaNetwork.load()

            if preferCache and not forceOffline and await self._casaNetwork.hasCache():
                self._logger.info("Using the cached network configuration.")
                forceOffline = True
                await self._casaNetwork.getNetworkId(forceOffline=True)
            else:
                try:
                    await self._casaNetwork.logIn(password, forceOffline)
                except (CloudUnavailableError, RequestError) as err:
                    self._logger.warning(
                        "Casambi cloud can't be used (%s). Trying to continue offline.",
                        err,
                    )
                    forceOffline = True

            await self._casaNetwork.update(forceOffline)
            self._bleDeviceCallback = bleDeviceCallback
            await self._connectClient(addr_or_device)

    async def refreshNetwork(self, password: str) -> bool:
        """Check the cloud for a newer network configuration.

        A newer configuration is stored in the cache and used by the next
        connect; the units, groups and scenes in use are not changed.

        :param password: The password for the network.
        :return: True if a newer configuration was downloaded.
        :raises AuthenticationError: The supplied password is invalid.
        :raises CloudUnavailableError: The cloud can't be used at the moment.
        :raises ConnectionStateError: There is no network loaded.
        """
        self._checkNetwork()
        network = cast(Network, self._casaNetwork)
        await network.logIn(password)
        return await network.fetchUpdate()

    @property
    def networkRevision(self) -> int:
        """Get the revision of the network configuration in use."""
        self._checkNetwork()
        return cast(int, self._casaNetwork.revision)  # type: ignore[union-attr]

    async def exportOfflineBackup(self) -> dict[str, Any]:
        """Export everything needed to use the network without the cloud.

        The backup contains the network configuration including the keys of
        the network. Treat it like a password.

        :raises ConnectionStateError: There is no network loaded.
        """
        self._checkNetwork()
        return await createBackup(cast(Network, self._casaNetwork))

    async def importOfflineBackup(self, backup: Mapping[str, Any]) -> str:
        """Restore an offline backup into the cache.

        A following connect uses the restored configuration and doesn't need
        the cloud.

        :param backup: A backup created by `exportOfflineBackup`.
        :return: The bluetooth address of the network in the backup.
        :raises OfflineBackupError: The backup is invalid.
        """
        return await restoreBackup(self._cache, backup)

    async def reconnect(self, addr_or_device: str | BLEDevice) -> None:
        """Reestablish the bluetooth connection. Only works after initial connection attempt and before disconnect has been called.

        :param addr: The MAC address of the network or a BLEDevice. Use `discover` to find the address of a network.
        :param password: The password for the network.
        :raises ProtocolError: The network did not follow the expected protocol.
        :raises BluetoothError: An error occurred in the bluetooth stack.
        :raises BluetoothDeviceNotFoundError: The bluetooth device belonging to the network can't be found.
        """

        self._checkNetwork()
        async with self._connectionLock:
            if self._casaClient is None:
                raise ConnectionStateError(
                    ConnectionState.CONNECTED,
                    ConnectionState.NONE,
                    "Reconnect only possible after initial connection and before disconnect.",
                )
            if self.connected:
                return
            await self._casaClient.disconnect()
            await self._connectClient(addr_or_device)

    async def _connectClient(self, addr_or_device: str | BLEDevice) -> None:
        """Initiate the bluetooth connection."""
        self._casaNetwork = cast(Network, self._casaNetwork)

        if isClassicNetwork(self._casaNetwork.protocolVersion):
            self._casaClient = CasambiClientClassic(
                addr_or_device,
                self._dataCallback,
                self._disconnectCallback,
                self._casaNetwork,
                self._bleDeviceCallback,
            )
            self._opContext = OperationsContextClassic()
        else:
            self._casaClient = CasambiClientEvolution(
                addr_or_device,
                self._dataCallback,
                self._disconnectCallback,
                self._casaNetwork,
                self._bleDeviceCallback,
            )
            self._opContext = OperationsContextEvolution()
        try:
            await self._casaClient.connect()
            await self._casaClient.exchangeKey()
            await self._casaClient.authenticate()
        except BaseException:
            await self._casaClient.disconnect()
            raise

    async def setUnitState(self, target: Unit, state: UnitState) -> None:
        """Set the state of one unit directly.

        :param target: The targeted unit.
        :param state: The desired state.
        :return: Nothing is returned by this function. To get the new state register a change handler.
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """
        if isClassicNetwork(self._casaNetwork.protocolVersion):  # type: ignore
            for c in target.unitType.controls:
                if c.type == UnitControlType.DIMMER and state.dimmer is not None:
                    await self.setLevel(target, state.dimmer)
                elif (
                    c.type == UnitControlType.TEMPERATURE
                    and state.temperature is not None
                ):
                    await self.setTemperature(target, state.temperature)
                elif c.type == UnitControlType.VERTICAL and state.vertical is not None:
                    await self.setVertical(target, state.vertical)
                elif c.type == UnitControlType.WHITE and state.white is not None:
                    await self.setWhite(target, state.white)
                elif c.type == UnitControlType.RGB and state.rgb is not None:
                    await self.setColor(target, state.rgb)
        else:
            stateBytes = target.getStateAsBytes(state)
            await self._send(target, stateBytes, OpCode.SetState)

    async def setControlValue(
        self, unit: Unit, control: UnitControl, value: int
    ) -> None:
        """Set a single control's value and send the updated state.

        The state is built from the unit's current raw state bytes with only
        the bits described by ``control`` overwritten.  All other controls —
        including UNKNOWN ones — remain unchanged.

        :param unit: The target unit.
        :param control: A :class:`UnitControl` from ``unit.unitType.controls``.
        :param value: Raw integer value to write into the control's bit field.
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """
        if unit.state is not None and unit.state.raw_state is not None:
            raw = bytearray(unit.state.raw_state)
        else:
            raw = bytearray(unit.unitType.stateLength)

        # Clear the target bits then write the new value (little-endian bytes).
        byte_start = control.offset // 8
        bit_start = control.offset % 8
        n_bytes = (control.length + bit_start + 7) // 8

        current = int.from_bytes(
            raw[byte_start : byte_start + n_bytes], byteorder="little"
        )
        mask = ((1 << control.length) - 1) << bit_start
        current = (current & ~mask) | (
            (value & ((1 << control.length) - 1)) << bit_start
        )
        raw[byte_start : byte_start + n_bytes] = current.to_bytes(
            n_bytes, byteorder="little"
        )

        state_bytes = bytes(raw)
        await self._send(unit, state_bytes, OpCode.SetState)
        unit.setStateFromBytes(state_bytes)

    async def setWhiteColorBalance(self, unit: Unit, value: int) -> None:
        """Set the white/color balance for a unit with a WHITECOLORBALANCE control.

        ``value`` is the raw 6-bit cross-fade level in the range [0, 63].
        0 = pure white channel, 63 = pure color channel.

        The balance is written via :meth:`setControlValue` which manipulates the
        raw state bytes in-place and sends a ``SetState`` opcode, so all other
        controls (brightness, colour, temperature) are preserved.

        :param unit: The target unit.  Must have a ``WHITECOLORBALANCE`` control.
        :param value: Raw balance level in range [0, 63].
        :raises ValueError: The unit does not support ``WHITECOLORBALANCE``, or value out of range.
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """
        if value < 0 or value > 63:
            raise ValueError(
                f"White/color balance value {value} is not in range [0, 63]."
            )
        control = unit.unitType.get_control(UnitControlType.WHITECOLORBALANCE)
        if control is None:
            raise ValueError("The unit does not support WHITECOLORBALANCE.")
        await self.setControlValue(unit, control, value)

    async def setLevel(self, target: Unit | Group | None, level: int) -> None:
        """Set the level (brightness) for one or multiple units.

        If ``target`` is of type ``Unit`` only this unit is affected.
        If ``target`` is of type ``Group`` the whole group is affected.
        if ``target`` is of type ``None`` all units in the network are affected.

        :param target: One or multiple targeted units.
        :param level: The desired level in range [0, 255]. If 0 the unit is turned off.
        :return: Nothing is returned by this function. To get the new state register a change handler.
        :raises ValueError: The supplied level isn't in range
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """
        if level < 0 or level > 255:
            raise ValueError()

        payload = level.to_bytes(1, byteorder="big", signed=False)
        await self._send(target, payload, OpCode.SetLevel)

    async def setVertical(self, target: Unit | Group | None, vertical: int) -> None:
        """Set the vertical (balance between top and bottom LED) for one or multiple units.

        If ``target`` is of type ``Unit`` only this unit is affected.
        If ``target`` is of type ``Group`` the whole group is affected.
        if ``target`` is of type ``None`` all units in the network are affected.

        :param target: One or multiple targeted units.
        :param vertical: The desired vertical balance in range [0, 255]. If 0 the unit is turned off.
        :return: Nothing is returned by this function. To get the new state register a change handler.
        :raises ValueError: The supplied level isn't in range
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """
        if vertical < 0 or vertical > 255:
            raise ValueError()

        payload = vertical.to_bytes(1, byteorder="big", signed=False)
        await self._send(target, payload, OpCode.SetVertical)

    async def setSlider(self, target: Unit | Group | None, value: int) -> None:
        """Set the slider for one or multiple units.

        If ``target`` is of type ``Unit`` only this unit is affected.
        If ``target`` is of type ``Group`` the whole group is affected.
        if ``target`` is of type ``None`` all units in the network are affected.

        :param target: One or multiple targeted units.
        :param value: The desired value in range [0, 255].
        :return: Nothing is returned by this function. To get the new state register a change handler.
        :raises ValueError: The supplied level isn't in range
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """
        if value < 0 or value > 255:
            raise ValueError()

        payload = value.to_bytes(1, byteorder="big", signed=False)
        await self._send(target, payload, OpCode.SetSlider)

    async def setWhite(self, target: Unit | Group | None, level: int) -> None:
        """Set the white level for one or multiple units.

        If ``target`` is of type ``Unit`` only this unit is affected.
        If ``target`` is of type ``Group`` the whole group is affected.
        if ``target`` is of type ``None`` all units in the network are affected.

        :param target: One or multiple targeted units.
        :param level: The desired level in range [0, 255].
        :return: Nothing is returned by this function. To get the new state register a change handler.
        :raises ValueError: The supplied level isn't in range
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """
        if level < 0 or level > 255:
            raise ValueError()

        payload = level.to_bytes(1, byteorder="big", signed=False)
        await self._send(target, payload, OpCode.SetWhite)

    async def setColor(
        self, target: Unit | Group | None, rgbColor: tuple[int, int, int]
    ) -> None:
        """Set the rgb color for one or multiple units.

        If ``target`` is of type ``Unit`` only this unit is affected.
        If ``target`` is of type ``Group`` the whole group is affected.
        if ``target`` is of type ``None`` all units in the network are affected.

        :param target: One or multiple targeted units.
        :param rgbColor: The desired color as a tuple of three ints in range [0, 255].
        :return: Nothing is returned by this function. To get the new state register a change handler.
        :raises ValueError: The supplied rgbColor isn't in range
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """

        if isClassicNetwork(self._casaNetwork.protocolVersion):  # type: ignore
            payload = UnitState.payload_from_rgb(rgbColor)
        else:
            state = UnitState()
            state.rgb = rgbColor
            hs: tuple[float, float] = state.hs  # type: ignore[assignment]
            payload = UnitState.payload_from_hs(hs)
        await self._send(target, payload, OpCode.SetColor)

    async def setTemperature(
        self, target: Unit | Group | None, temperature: int
    ) -> None:
        """Set the temperature for one or multiple units.

        If ``target`` is of type ``Unit`` only this unit is affected.
        If ``target`` is of type ``Group`` the whole group is affected.
        if ``target`` is of type ``None`` all units in the network are affected.

        :param target: One or multiple targeted units.
        :param temperature: The desired temperature in degrees Kelvin.
        :return: Nothing is returned by this function. To get the new state register a change handler.
        :raises ValueError: The supplied temperature isn't in range
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """

        payload = UnitState.payload_from_temperature(temperature)
        await self._send(target, payload, OpCode.SetTemperature)

    async def setColorXY(
        self, target: Unit | Group | None, xyColor: tuple[float, float]
    ) -> None:
        """Set the xy color for one or multiple units.

        If ``target`` is of type ``Unit`` only this unit is affected.
        If ``target`` is of type ``Group`` the whole group is affected.
        if ``target`` is of type ``None`` all units in the network are affected.

        :param target: One or multiple targeted units.
        :param xyColor: The desired color as a pair of floats in the range [0.0, 1.0].
        :return: Nothing is returned by this function. To get the new state register a change handler.
        :raises ValueError: The supplied XYColor isn't in range or not supported by the supplied unit.
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """

        if xyColor[0] < 0.0 or xyColor[0] > 1.0 or xyColor[1] < 0.0 or xyColor[1] > 1.0:
            raise ValueError("Color out of range.")

        # We assume a default length of 22 bits, so 11 bits per coordinate. Is this sane?
        length = 22
        if target is not None and isinstance(target, Unit):
            control = target.unitType.get_control(UnitControlType.XY)
            if control is None:
                raise ValueError("The control isn't supported by this unit.")
            length = control.length

        payload = UnitState.payload_from_xy(xyColor, length)
        await self._send(target, payload, OpCode.SetColorXY)

    async def turnOn(self, target: Unit | Group | None) -> None:
        """Turn one or multiple units on to their last level.

        If ``target`` is of type ``Unit`` only this unit is affected.
        If ``target`` is of type ``Group`` the whole group is affected.
        if ``target`` is of type ``None`` all units in the network are affected.

        :param target: One or multiple targeted units.
        :return: Nothing is returned by this function. To get the new state register a change handler.
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """
        self._checkNetwork()

        if isClassicNetwork(self._casaNetwork.protocolVersion):  # type: ignore
            await self._send(target, b"\xff\x01\x00\x00\x01", OpCode.SetLevel)
        else:
            # Use -1 to indicate special packet format
            # Use RestoreLastLevel flag (1) and UseFullTimeFlag (4).
            # Not sure what UseFullTime does but this is what the app uses.
            await self._send(target, b"\xff\x05", OpCode.SetLevel)

    async def turnOff(self, target: Unit | Group | None) -> None:
        """Turn one or multiple units off.

        If ``target`` is of type ``Unit`` only this unit is affected.
        If ``target`` is of type ``Group`` the whole group is affected.
        if ``target`` is of type ``None`` all units in the network are affected.

        :param target: One or multiple targeted units.
        :return: Nothing is returned by this function. To get the new state register a change handler.
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """
        self._checkNetwork()

        if (
            isinstance(target, Unit)
            and target.unitType.get_control(UnitControlType.ONOFF) is not None
            and not isClassicNetwork(self._casaNetwork.protocolVersion)  # type: ignore
        ):
            state = copy(target.state) if target.state is not None else UnitState()
            state.onoff = False
            stateBytes = target.getStateAsBytes(state)
            await self._send(target, stateBytes, OpCode.SetState)
        else:
            await self.setLevel(target, 0)

    async def switchToScene(self, target: Scene, level: int = 0xFF) -> None:
        """Switch the network to a predefined scene.

        :param target: The scene to switch to.
        :param level: An optional relative brightness for all units in the scene.
        :return: Nothing is returned by this function. To get the new state register a change handler.
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """
        await self.setLevel(target, level)  # type: ignore[arg-type]

    async def _send(
        self, target: Unit | Group | Scene | None, state: bytes, opcode: OpCode
    ) -> None:
        if self._casaClient is None:
            raise ConnectionStateError(
                ConnectionState.AUTHENTICATED,
                ConnectionState.NONE,
            )

        if self._logger.isEnabledFor(logging.DEBUG):
            self._logger.debug(
                "Sending operation %s with payload %s.", opcode.name, b2a(state)
            )

        opPkt = self._opContext.prepareOperation(opcode, target, state)

        try:
            await self._casaClient.send(opPkt)
        except ConnectionStateError as exc:
            if exc.got != ConnectionState.NONE:
                raise
            # Reconnect once, but never let a command hang for the whole
            # retry policy of the bluetooth stack.
            self._logger.info("Trying to reconnect broken connection once.")
            try:
                async with asyncio.timeout(SEND_RECONNECT_TIMEOUT):
                    await self.reconnect(self._casaClient._address_or_devive)
            except TimeoutError as err:
                raise BluetoothError("Reconnect for sending timed out.") from err
            await self._casaClient.send(opPkt)

    def _dataCallback(
        self, packetType: IncomingPacketType, data: dict[str, Any] | SwitchEvent
    ) -> None:
        if packetType == IncomingPacketType.UnitState:
            unitData = cast(dict[str, Any], data)
            if self._logger.isEnabledFor(logging.DEBUG):
                self._logger.debug(
                    "Handling changed state %s for unit %s",
                    b2a(unitData["state"]),
                    unitData["id"],
                )

            found = False
            for u in self._casaNetwork.units:  # type: ignore[union-attr]
                if u.deviceId != unitData["id"]:
                    continue
                found = True
                try:
                    u.setStateFromBytes(unitData["state"])
                except Exception:
                    # Keep the previous state, but still report on/online.
                    self._logger.error(
                        "Failed to parse the state of unit %s.",
                        u.deviceId,
                        exc_info=True,
                    )
                u._on = unitData["on"]
                u._online = unitData["online"]

                # Notify listeners
                for h in list(self._unitChangedCallbacks):
                    try:
                        h(u)
                    except Exception:
                        self._logger.error(
                            "Exception occurred in unitChangedCallback %s.",
                            h,
                            exc_info=True,
                        )

            if not found:
                self._logger.warning(
                    "Changed state notification for unknown unit %s", unitData["id"]
                )
        elif packetType == IncomingPacketType.SwitchEvent:
            switchData = cast(SwitchEvent, data)
            self._logger.debug(
                "Handling switch event: unit_id=%s, button=%s, event=%s",
                switchData.unit_id,
                switchData.button,
                switchData.event,
            )

            # Notify listeners
            for switch_handler in list(self._switchEventCallbacks):
                try:
                    switch_handler(switchData)
                except Exception:
                    self._logger.error(
                        "Exception occurred in switchEventCallback %s.",
                        switch_handler,
                        exc_info=True,
                    )
        else:
            self._logger.warning("Handler for type %s not implemented!", packetType)

    def registerUnitChangedHandler(self, handler: Callable[[Unit], None]) -> None:
        """Register a new handler for unit state changed.

        This handler is called whenever a new state for a unit is received.
        The handler is supplied by the unit for which the state changed
        and the state property of the unit is set to the new state.

        :param handler: The method to call when a new unit state is received.
        """
        self._unitChangedCallbacks.append(handler)
        self._logger.debug("Registered unit changed handler %s", handler)

    def unregisterUnitChangedHandler(self, handler: Callable[[Unit], None]) -> None:
        """Unregister an existing unit state change handler.

        :param handler: The handler to unregister.
        :raises ValueError: If the handler isn't registered.
        """
        self._unitChangedCallbacks.remove(handler)
        self._logger.debug("Removed unit changed handler %s", handler)

    def registerSwitchEventHandler(
        self, handler: Callable[[SwitchEvent], None]
    ) -> None:
        """Register a new handler for switch events.

        This handler is called whenever a switch event is received.
        The handler is supplied with a SwitchEvent containing:
        - unit_id: The ID of the switch unit
        - button: The button number (1-based, = button_event_index + 1)
        - button_event_index: 0-based index from the protocol
        - event: A ButtonEventType (PRESS, RELEASE, HOLD, RELEASE_AFTER_HOLD)
        - flags: Frame flags
        - extra_data: Any additional payload bytes

        :param handler: The method to call when a switch event is received.
        """
        self._switchEventCallbacks.append(handler)
        self._logger.debug("Registered switch event handler %s", handler)

    def unregisterSwitchEventHandler(
        self, handler: Callable[[SwitchEvent], None]
    ) -> None:
        """Unregister an existing switch event handler.

        :param handler: The handler to unregister.
        :raises ValueError: If the handler isn't registered.
        """
        self._switchEventCallbacks.remove(handler)
        self._logger.debug("Removed switch event handler %s", handler)

    def registerDisconnectCallback(self, callback: Callable[[], None]) -> None:
        """Register a disconnect callback.

        The callback is called whenever the Bluetooth stack reports that
        the Bluetooth connection to the network was disconnected.

        :params callback: The callback to register.
        """
        self._disconnectCallbacks.append(callback)
        self._logger.debug("Registered disconnect callback %s", callback)

    def unregisterDisconnectCallback(self, callback: Callable[[], None]) -> None:
        """Unregister an existing disconnect callback.

        :param callback: The callback to unregister.
        :raises ValueError: If the callback isn't registered.
        """
        self._disconnectCallbacks.remove(callback)
        self._logger.debug("Removed disconnect callback %s", callback)

    async def invalidateCache(self, uuid: str) -> None:
        """Invalidates the cache for a network.

        :param uuid: The address of the network.
        """

        # We can't use our own cache here since the invalidation happens
        # before the first connection attempt.
        tempCache = Cache(self._cache._cachePath)
        await tempCache.setUuid(uuid)
        await tempCache.invalidateCache()

    def _disconnectCallback(self) -> None:
        # Mark all units as offline on disconnect.
        units = self._casaNetwork.units if self._casaNetwork else []
        for u in units:
            u._online = False
            for h in list(self._unitChangedCallbacks):
                try:
                    h(u)
                except Exception:
                    self._logger.error(
                        "Exception occurred in unitChangedHandler %s.",
                        h,
                        exc_info=True,
                    )

        for d in list(self._disconnectCallbacks):
            try:
                d()
            except Exception:
                self._logger.error(
                    "Exception occurred in disconnectCallback %s.",
                    d,
                    exc_info=True,
                )

    async def disconnect(self) -> None:
        """Disconnect from the network."""
        if self._casaClient:
            try:
                await asyncio.shield(self._casaClient.disconnect())
            except Exception:
                self._logger.error("Failed to disconnect from client.", exc_info=True)
        if self._casaNetwork:
            try:
                await asyncio.shield(self._casaNetwork.disconnect())
            except Exception:
                self._logger.error("Failed to disconnect from network.", exc_info=True)
            self._casaNetwork = None
        if self._ownHttpClient and self._httpClient is not None:
            try:
                await asyncio.shield(self._httpClient.aclose())
            except Exception:
                self._logger.error("Failed to close http client.", exc_info=True)
