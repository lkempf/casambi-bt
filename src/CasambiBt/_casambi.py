import logging
from binascii import b2a_hex as b2a
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

from bleak.backends.device import BLEDevice
from httpx import AsyncClient

from ._client import CasambiClient, ConnectionState, IncommingPacketType
from ._network import Network, getNetworkIdFromUuid
from ._operation import OpCode, OperationsContext
from ._unit import Group, Scene, Unit, UnitState
from .errors import AuthenticationError, ConnectionStateError, ProtocolError


class Casambi:
    """Class to manage one Casambi network.

    This is the central point of interaction and should be preferred to dealing with the internal components,
    e.g. ``Network`` or ``CasambiClient``, directly.
    """

    _casaClient: CasambiClient
    _casaNetwork: Network
    _opContext: OperationsContext
    _httpClient: AsyncClient
    _ownHttpClient: bool

    _unitChangedCallbacks: List[Callable[[Unit], None]] = []

    def __init__(self, httpClient: Optional[AsyncClient] = None) -> None:
        self._logger = logging.getLogger(__name__)
        self._opContext = OperationsContext()
        if not httpClient:
            httpClient = AsyncClient()
            self._ownHttpClient = True
        else:
            self._ownHttpClient = False
        self._httpClient = httpClient

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
        return self._casaNetwork._networkName

    @property
    def networkId(self) -> str:
        self._checkNetwork()
        return self._casaNetwork.id

    @property
    def units(self) -> List[Unit]:
        """Get the units in the network if connected.

        :return: A list of all units in the network.
        :raises ConnectionStateError: There is no connection to the network.
        """
        self._checkNetwork()
        return self._casaNetwork.units

    @property
    def groups(self) -> List[Group]:
        """Get the groups in the network if connected.

        :return: A list of all groups in the network.
        :raises ConnectionStateError: There is no connection to the network.
        """
        self._checkNetwork()
        return self._casaNetwork.groups

    @property
    def scenes(self) -> List[Scene]:
        """Get the scenes of the network if connected.

        :return: A list of all scenes in the network.
        :raises ConnectionStateError: There is no connection to the network.
        """
        self._checkNetwork()
        return self._casaNetwork.scenes

    @property
    def connected(self) -> bool:
        """Check whether there is an active connection to the network."""
        return self._casaClient._connectionState == ConnectionState.AUTHENTICATED

    async def connect(
        self, addr_or_device: Union[str, BLEDevice], password: str
    ) -> Awaitable[None]:
        """Connect and authenticate to a network.

        :param addr: The MAC address of the network or a BLEDevice. Use `discover` to find the address of a network.
        :param password: The password for the network.
        :raises AuthenticationError: The supplied password is invalid.
        :raises ProtocolError: The network did not follow the expected protocol.
        :raises NetworkNotFoundError: No network was found under the supplied address.
        :raises BluetoothNotReadyError: Bluetooth isn't turned on or in a failed state.
        """

        if isinstance(addr_or_device, BLEDevice):
            addr = addr_or_device.address
        else:
            addr = addr_or_device

        self._logger.info(f"Trying to connect to casambi network {addr}...")

        self._casaClient = CasambiClient(addr_or_device, self._dataCallback)

        # Retrieve network information
        networkId = await getNetworkIdFromUuid(addr, self._httpClient)
        self._casaNetwork = Network(networkId, self._httpClient)
        if not self._casaNetwork.authenticated():
            loggedIn = await self._casaNetwork.logIn(password)
            if not loggedIn:
                raise AuthenticationError("Login failed")
        await self._casaNetwork.update()

        await self._connectClient()

    async def _connectClient(self) -> Awaitable[None]:
        """Initiate the bluetooth connection."""
        await self._casaClient.connect()
        try:
            await self._casaClient.exchangeKey()
            await self._casaClient.authenticate(self._casaNetwork.getKeyStore())
        except ProtocolError as e:
            await self._casaClient.disconnect()
            raise e

    async def setUnitState(self, target: Unit, state: UnitState) -> Awaitable[None]:
        """Set the state of one unit directly.

        :param target: The targeted unit.
        :param state: The desired state.
        :return: Nothing is returned by this function. To get the new state register a change handler.
        """
        stateBytes = target.getStateAsBytes(state)
        await self._send(target, stateBytes, OpCode.SetState)

    async def setLevel(
        self, target: Union[Unit, Group, None], level: int
    ) -> Awaitable[None]:
        """Set the level (brightness) for one or multiple units.

        If ``target`` is of type ``Unit`` only this unit is affected.
        If ``target`` is of type ``Group`` the whole group is affected.
        if ``target`` is of type ``None`` all units in the network are affected.

        :param target: One or multiple targeted units.
        :param level: The desired level in range [0, 255]. If 0 the unit is turned off.
        :return: Nothing is returned by this function. To get the new state register a change handler.
        :raises ValueError: The supplied level isn't in range
        """
        if level < 0 or level > 255:
            raise ValueError()

        payload = level.to_bytes(1, byteorder="big", signed=False)
        await self._send(target, payload, OpCode.SetLevel)

    async def turnOn(self, target: Union[Unit, Group, None]) -> Awaitable[None]:
        """Turn one or multiple units on to their last level.

        If ``target`` is of type ``Unit`` only this unit is affected.
        If ``target`` is of type ``Group`` the whole group is affected.
        if ``target`` is of type ``None`` all units in the network are affected.

        :param target: One or multiple targeted units.
        :return: Nothing is returned by this function. To get the new state register a change handler.
        """

        # Use -1 to indicate special packet format
        # Use RestoreLastLevel flag (1) and UseFullTimeFlag (4).
        # Not sure what UseFullTime does but this is what the app uses.
        await self._send(target, b"\xff\x05", OpCode.SetLevel)

    async def switchToScene(self, target: Scene) -> Awaitable[None]:
        """Switch the network to a predefined scene.

        :param target: The scene to switch to.
        :return: Nothing is returned by this function. To get the new state register a change handler.
        """
        await self._send(target, b"\xff", OpCode.SetLevel)

    async def _send(
        self, target: Union[Unit, Group, Scene, None], state: bytes, opcode: OpCode
    ) -> Awaitable[None]:
        targetCode = 0
        if isinstance(target, Unit):
            assert target.deviceId <= 0xFF
            targetCode = (target.deviceId << 8) | 0x01
        elif isinstance(target, Group):
            assert target.groudId <= 0xFF
            targetCode = (target.groudId << 8) | 0x02
        elif isinstance(target, Scene):
            assert target.sceneId <= 0xFF
            targetCode = (target.sceneId << 8) | 0x04
        elif target is not None:
            raise TypeError(f"Unkown target type {type(target)}")

        self._logger.debug(
            f"Sending operation {opcode.name} with payload {b2a(state)} for {targetCode:x}"
        )

        opPkt = self._opContext.prepareOperation(opcode, targetCode, state)

        try:
            await self._casaClient.send(opPkt)
        except ConnectionStateError as exc:
            if exc.got == ConnectionState.NONE:
                self._logger.info(f"Trying to reconnect broken connection once.")
                await self._connectClient()
                await self._casaClient.send(opPkt)
            else:
                raise exc

    def _dataCallback(
        self, packetType: IncommingPacketType, data: Dict[str, Any]
    ) -> None:
        self._logger.info(f"Incomming data callback of type {packetType}")
        if packetType == IncommingPacketType.UnitState:
            self._logger.debug(
                f"Handling changed state {b2a(data['state'])} for unit {data['id']}"
            )

            found = False
            for u in self._casaNetwork.units:
                if u.deviceId == data["id"]:
                    found = True
                    u.setStateFromBytes(data["state"])
                    u._on = data["on"]
                    u._online = data["online"]

                    # Notify listeners
                    for h in self._unitChangedCallbacks:
                        try:
                            h(u)
                        except Exception:
                            self._logger.error(
                                f"Exception occurred in unitChangedCallback {h}.",
                                exc_info=1,
                            )

            if not found:
                self._logger.error(
                    f"Changed state notification for unkown unit {data['id']}"
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
        self._logger.info(f"Registerd unit changed handler {handler}")

    def unregisterUnitChangedHandler(self, handler: Callable[[Unit], None]) -> None:
        """Unregister an existing unit state change handler.

        :param handler: The handler to unregister.
        :raises ValueError: If the handler isn't registered.
        """
        self._unitChangedCallbacks.remove(handler)
        self._logger.info(f"Removed unit changed handler {handler}")

    # TODO: Implement disconnected callback

    async def disconnect(self) -> Awaitable[None]:
        """Disconnect from the network."""
        if self._casaClient:
            await self._casaClient.disconnect()
        if self._casaNetwork:
            await self._casaNetwork.disconnect()
            self._casaNetwork = None
        if self._ownHttpClient:
            await self._httpClient.aclose()

    async def __aexit__(self) -> Awaitable[None]:
        await self.disconnect()
