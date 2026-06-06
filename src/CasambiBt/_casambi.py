import asyncio
import logging
from binascii import b2a_hex as b2a
from collections.abc import Callable
from copy import copy
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

from bleak.backends.device import BLEDevice
from httpx import AsyncClient, RequestError

from CasambiBt._constants import IncomingPacketType
from CasambiBt._switch import SwitchEvent

from ._cache import Cache
from ._client import (
    CasambiClient,
    CasambiClientClassic,
    CasambiClientEvolution,
    ConnectionState,
)
from ._constants import isClassicNetwork
from ._network import Network
from ._operation import (
    OpCode,
    OperationsContext,
    OperationsContextClassic,
    OperationsContextEvolution,
)
from ._unit import Group, Scene, Unit, UnitControl, UnitControlType, UnitState
from .errors import ConnectionStateError


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

        self._logger = logging.getLogger(__name__)
        self._opContext: OperationsContext
        self._ownHttpClient = httpClient is None
        self._httpClient = httpClient

        self._cache = Cache(cachePath)

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
    ) -> None:
        """Connect and authenticate to a network.

        :param addr: The MAC address of the network or a BLEDevice. Use `discover` to find the address of a network.
        :param password: The password for the network.
        :param forceOffline: Whether to avoid contacting the casambi servers.
        :raises AuthenticationError: The supplied password is invalid.
        :raises ProtocolError: The network did not follow the expected protocol.
        :raises NetworkNotFoundError: No network was found under the supplied address.
        :raises NetworkOnlineUpdateNeededError: An offline update isn't possible in the current state.
        :raises BluetoothError: An error occurred in the bluetooth stack.
        :raises BluetoothDeviceNotFoundError: The bluetooth device belonging to the network can't be found.
        """

        if isinstance(addr_or_device, BLEDevice):
            addr = addr_or_device.address
        else:
            # Add colons if necessary.
            if ":" not in addr_or_device:
                addr_or_device = ":".join(["".join(p) for p in pairwise(addr)][::2])
            addr = addr_or_device

        self._logger.info(f"Trying to connect to casambi network {addr}...")

        if not self._httpClient:
            self._httpClient = AsyncClient()

        # Retrieve network information
        uuid = addr.replace(":", "").lower()
        await self._cache.setUuid(uuid)
        self._casaNetwork = Network(uuid, self._httpClient, self._cache)
        await self._casaNetwork.load()
        try:
            await self._casaNetwork.logIn(password, forceOffline)
        # TODO: I don't like that this logic is in this class but I couldn't think of a better way.
        except RequestError:
            self._logger.warning(
                "Network error while logging in. Trying to continue offline.",
                exc_info=True,
            )
            forceOffline = True

        await self._casaNetwork.update(forceOffline)
        await self._connectClient(addr_or_device)

    async def reconnect(self, addr_or_device: str | BLEDevice) -> None:
        """Reestablish the bluetooth connection. Only works after initial connection attempt and before disconnect has been called.

        :param addr: The MAC address of the network or a BLEDevice. Use `discover` to find the address of a network.
        :param password: The password for the network.
        :raises ProtocolError: The network did not follow the expected protocol.
        :raises BluetoothError: An error occurred in the bluetooth stack.
        :raises BluetoothDeviceNotFoundError: The bluetooth device belonging to the network can't be found.
        """

        self._checkNetwork()
        if self._casaClient is None:
            raise ConnectionStateError(
                ConnectionState.CONNECTED,
                ConnectionState.NONE,
                "Reconnect only possible after initial connection and before disconnect.",
            )
        if self._casaClient._connectionState != ConnectionState.NONE:
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
            )
            self._opContext = OperationsContextClassic()
        else:
            self._casaClient = CasambiClientEvolution(
                addr_or_device,
                self._dataCallback,
                self._disconnectCallback,
                self._casaNetwork,
            )
            self._opContext = OperationsContextEvolution()
        try:
            await self._casaClient.connect()
            await self._casaClient.exchangeKey()
            await self._casaClient.authenticate()
        except:
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

        self._logger.debug(
            f"Sending operation {opcode.name} with payload {b2a(state)}."
        )

        opPkt = self._opContext.prepareOperation(opcode, target, state)

        try:
            await self._casaClient.send(opPkt)
        except ConnectionStateError as exc:
            if exc.got == ConnectionState.NONE:
                self._logger.info("Trying to reconnect broken connection once.")
                await self._connectClient(self._casaClient._address_or_devive)
                await self._casaClient.send(opPkt)
            else:
                raise exc

    def _dataCallback(
        self, packetType: IncomingPacketType, data: dict[str, Any] | SwitchEvent
    ) -> None:
        self._logger.debug(f"Incoming data callback of type {str(packetType)}")
        if packetType == IncomingPacketType.UnitState:
            unitData = cast(dict[str, Any], data)
            self._logger.debug(
                f"Handling changed state {b2a(unitData['state'])} for unit {unitData['id']}"
            )

            found = False
            for u in self._casaNetwork.units:  # type: ignore[union-attr]
                if u.deviceId == unitData["id"]:
                    found = True
                    u.setStateFromBytes(unitData["state"])
                    u._on = unitData["on"]
                    u._online = unitData["online"]

                    # Notify listeners
                    for h in self._unitChangedCallbacks:
                        try:
                            h(u)
                        except Exception:
                            self._logger.error(
                                f"Exception occurred in unitChangedCallback {h}.",
                                exc_info=True,
                            )

            if not found:
                self._logger.error(
                    f"Changed state notification for unkown unit {unitData['id']}"
                )
        elif packetType == IncomingPacketType.SwitchEvent:
            switchData = cast(SwitchEvent, data)
            self._logger.debug(
                f"Handling switch event: unit_id={switchData.unit_id}, "
                f"button={switchData.button}, event={switchData.event}"
            )

            # Notify listeners
            for switch_handler in self._switchEventCallbacks:
                try:
                    switch_handler(switchData)
                except Exception:
                    self._logger.error(
                        f"Exception occurred in switchEventCallback {switch_handler}.",
                        exc_info=True,
                    )
        else:
            self._logger.warning(f"Handler for type {packetType} not implemented!")

    def registerUnitChangedHandler(self, handler: Callable[[Unit], None]) -> None:
        """Register a new handler for unit state changed.

        This handler is called whenever a new state for a unit is received.
        The handler is supplied by the unit for which the state changed
        and the state property of the unit is set to the new state.

        :param handler: The method to call when a new unit state is received.
        """
        self._unitChangedCallbacks.append(handler)
        self._logger.debug(f"Registered unit changed handler {handler}")

    def unregisterUnitChangedHandler(self, handler: Callable[[Unit], None]) -> None:
        """Unregister an existing unit state change handler.

        :param handler: The handler to unregister.
        :raises ValueError: If the handler isn't registered.
        """
        self._unitChangedCallbacks.remove(handler)
        self._logger.debug(f"Removed unit changed handler {handler}")

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
        self._logger.debug(f"Registered switch event handler {handler}")

    def unregisterSwitchEventHandler(
        self, handler: Callable[[SwitchEvent], None]
    ) -> None:
        """Unregister an existing switch event handler.

        :param handler: The handler to unregister.
        :raises ValueError: If the handler isn't registered.
        """
        self._switchEventCallbacks.remove(handler)
        self._logger.debug(f"Removed switch event handler {handler}")

    def registerDisconnectCallback(self, callback: Callable[[], None]) -> None:
        """Register a disconnect callback.

        The callback is called whenever the Bluetooth stack reports that
        the Bluetooth connection to the network was disconnected.

        :params callback: The callback to register.
        """
        self._disconnectCallbacks.append(callback)
        self._logger.debug(f"Registered disconnect callback {callback}")

    def unregisterDisconnectCallback(self, callback: Callable[[], None]) -> None:
        """Unregister an existing disconnect callback.

        :param callback: The callback to unregister.
        :raises ValueError: If the callback isn't registered.
        """
        self._disconnectCallbacks.remove(callback)
        self._logger.debug(f"Removed disconnect callback {callback}")

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
        for u in self.units:
            u._online = False
            for h in self._unitChangedCallbacks:
                try:
                    h(u)
                except Exception:
                    self._logger.error(
                        f"Exception occurred in unitChangedHandler {h}.",
                        exc_info=True,
                    )

        for d in self._disconnectCallbacks:
            try:
                d()
            except Exception:
                self._logger.error(
                    f"Exception occurred in disconnectCallback {d}.",
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
