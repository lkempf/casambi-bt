from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.backends.device import BLEDevice
from httpx import RequestError

from CasambiBt._casambi import Casambi
from CasambiBt._client import ConnectionState, IncomingPacketType
from CasambiBt._operation import (
    OpCode,
    OperationsContextClassic,
    OperationsContextEvolution,
)
from CasambiBt._switch import ButtonEventType, SwitchEvent
from CasambiBt._unit import Group, Scene, Unit, UnitControl, UnitControlType, UnitType
from CasambiBt.errors import ConnectionStateError


@pytest.fixture
def mock_network_class():
    with patch("CasambiBt._casambi.Network") as mock:
        yield mock


@pytest.fixture
def mock_client_class():
    with patch("CasambiBt._casambi.CasambiClientEvolution") as mock:
        yield mock


@pytest.fixture
def mock_client_classic_class():
    with patch("CasambiBt._casambi.CasambiClientClassic") as mock:
        yield mock


@pytest.fixture
def mock_unit():
    control = UnitControl(
        type=UnitControlType.DIMMER, offset=0, length=8, default=0, readonly=False
    )
    unit_type = UnitType(
        id=1,
        model="Model",
        manufacturer="Casambi",
        mode="Mode",
        stateLength=1,
        controls=[control],
    )
    unit = Unit(
        _typeId=1,
        deviceId=10,
        uuid="uuid1",
        address="addr1",
        name="Unit 1",
        firmwareVersion="1.0",
        unitType=unit_type,
    )
    return unit


@pytest.fixture
def mock_xy_unit():
    control = UnitControl(
        type=UnitControlType.XY, offset=0, length=22, default=0, readonly=False
    )
    unit_type = UnitType(
        id=2,
        model="Model",
        manufacturer="Casambi",
        mode="Mode",
        stateLength=3,
        controls=[control],
    )
    unit = Unit(
        _typeId=2,
        deviceId=11,
        uuid="uuid2",
        address="addr2",
        name="Unit 2",
        firmwareVersion="1.0",
        unitType=unit_type,
    )
    return unit


@pytest.fixture
def mock_group(mock_unit):
    return Group(groudId=20, name="Group 1", units=[mock_unit])


@pytest.fixture
def mock_scene():
    return Scene(sceneId=30, name="Scene 1")


@pytest.fixture
def casambi():
    return Casambi()


@pytest.fixture
def connected_casambi(casambi, mock_unit, mock_group, mock_scene):
    # Setup mock network
    mock_network = MagicMock()
    mock_network.disconnect = AsyncMock()
    mock_network._networkRevision = 1
    mock_network._networkName = "Test Network"
    mock_network._id = "test-id"
    mock_network.units = [mock_unit]
    mock_network.groups = [mock_group]
    mock_network.scenes = [mock_scene]
    mock_network.protocolVersion = 10

    # Setup mock client
    mock_client = AsyncMock()
    mock_client._connectionState = ConnectionState.AUTHENTICATED

    casambi._casaNetwork = mock_network
    casambi._casaClient = mock_client
    casambi._opContext = OperationsContextEvolution()
    return casambi


@pytest.fixture
def connected_casambi_classic(casambi, mock_unit, mock_group, mock_scene):
    # Setup mock network
    mock_network = MagicMock()
    mock_network.disconnect = AsyncMock()
    mock_network._networkRevision = 1
    mock_network._networkName = "Test Network Classic"
    mock_network._id = "test-id-classic"
    mock_network.units = [mock_unit]
    mock_network.groups = [mock_group]
    mock_network.scenes = [mock_scene]
    mock_network.protocolVersion = 5

    # Setup mock client
    mock_client = AsyncMock()
    mock_client._connectionState = ConnectionState.AUTHENTICATED

    casambi._casaNetwork = mock_network
    casambi._casaClient = mock_client
    casambi._opContext = OperationsContextClassic()
    return casambi


def test_init(casambi):
    assert casambi._casaClient is None
    assert casambi._casaNetwork is None
    assert not casambi.connected


def test_properties_unconnected(casambi):
    with pytest.raises(ConnectionStateError):
        _ = casambi.networkName
    with pytest.raises(ConnectionStateError):
        _ = casambi.networkId
    with pytest.raises(ConnectionStateError):
        _ = casambi.units
    with pytest.raises(ConnectionStateError):
        _ = casambi.groups
    with pytest.raises(ConnectionStateError):
        _ = casambi.scenes


def test_properties_connected(connected_casambi):
    assert connected_casambi.networkName == "Test Network"
    assert connected_casambi.networkId == "test-id"
    assert len(connected_casambi.units) == 1
    assert len(connected_casambi.groups) == 1
    assert len(connected_casambi.scenes) == 1
    assert connected_casambi.connected


async def test_connect(casambi, mock_network_class, mock_client_class):
    mock_network_inst = mock_network_class.return_value
    mock_network_inst.load = AsyncMock()
    mock_network_inst.logIn = AsyncMock()
    mock_network_inst.update = AsyncMock()
    mock_network_inst.protocolVersion = 10

    mock_client_inst = mock_client_class.return_value
    mock_client_inst.connect = AsyncMock()
    mock_client_inst.exchangeKey = AsyncMock()
    mock_client_inst.authenticate = AsyncMock()

    device = MagicMock(spec=BLEDevice)
    device.address = "00:11:22:33:44:55"
    await casambi.connect(device, "password")

    mock_network_class.assert_called_once()
    mock_network_inst.load.assert_called_once()
    mock_network_inst.logIn.assert_called_once_with("password", False)
    mock_network_inst.update.assert_called_once_with(False)

    mock_client_class.assert_called_once()
    mock_client_inst.connect.assert_called_once()
    mock_client_inst.exchangeKey.assert_called_once()
    mock_client_inst.authenticate.assert_called_once()


async def test_connect_classic(casambi, mock_network_class, mock_client_classic_class):
    mock_network_inst = mock_network_class.return_value
    mock_network_inst.load = AsyncMock()
    mock_network_inst.logIn = AsyncMock()
    mock_network_inst.update = AsyncMock()
    mock_network_inst.protocolVersion = 5

    mock_client_inst = mock_client_classic_class.return_value
    mock_client_inst.connect = AsyncMock()
    mock_client_inst.exchangeKey = AsyncMock()
    mock_client_inst.authenticate = AsyncMock()

    device = MagicMock(spec=BLEDevice)
    device.address = "00:11:22:33:44:55"
    await casambi.connect(device, "password")

    mock_network_class.assert_called_once()
    mock_network_inst.load.assert_called_once()
    mock_network_inst.logIn.assert_called_once_with("password", False)
    mock_network_inst.update.assert_called_once_with(False)

    mock_client_classic_class.assert_called_once()
    mock_client_inst.connect.assert_called_once()
    mock_client_inst.exchangeKey.assert_called_once()
    mock_client_inst.authenticate.assert_called_once()


async def test_connect_offline_fallback(casambi, mock_network_class, mock_client_class):
    mock_network_inst = mock_network_class.return_value
    mock_network_inst.load = AsyncMock()

    # Simulate RequestError during logIn
    mock_network_inst.logIn = AsyncMock(side_effect=RequestError("Error"))
    mock_network_inst.update = AsyncMock()
    mock_network_inst.protocolVersion = 10

    mock_client_inst = mock_client_class.return_value
    mock_client_inst.connect = AsyncMock()
    mock_client_inst.exchangeKey = AsyncMock()
    mock_client_inst.authenticate = AsyncMock()

    await casambi.connect("00:11:22:33:44:55", "password")

    mock_network_inst.logIn.assert_called_once_with("password", False)
    # Update should be called with forceOffline=True
    mock_network_inst.update.assert_called_once_with(True)


async def test_set_level_valid(connected_casambi, mock_unit):
    await connected_casambi.setLevel(mock_unit, 128)
    # Check what was sent
    connected_casambi._casaClient.send.assert_called_once()
    args, _ = connected_casambi._casaClient.send.call_args
    pkt = args[0]
    # Header is 9 bytes, followed by payload
    assert len(pkt) == 10  # 9 byte header + 1 byte payload
    assert pkt[-1] == 128


async def test_set_level_valid_classic(connected_casambi_classic, mock_unit):
    await connected_casambi_classic.setLevel(mock_unit, 128)
    # Check what was sent
    connected_casambi_classic._casaClient.send.assert_called_once()
    args, _ = connected_casambi_classic._casaClient.send.call_args
    pkt = args[0]
    # Header is 5 bytes, followed by payload
    assert len(pkt) == 6  # 5 byte header + 1 byte payload
    assert pkt[-1] == 128


async def test_set_level_invalid(connected_casambi, mock_unit):
    with pytest.raises(ValueError):
        await connected_casambi.setLevel(mock_unit, 256)
    with pytest.raises(ValueError):
        await connected_casambi.setLevel(mock_unit, -1)


async def test_set_color(connected_casambi, mock_unit):
    await connected_casambi.setColor(mock_unit, (255, 0, 0))
    connected_casambi._casaClient.send.assert_called_once()
    args, _ = connected_casambi._casaClient.send.call_args
    pkt = args[0]
    assert pkt[-3:] == b"\x00\x00\xff"


async def test_set_color_classic(connected_casambi_classic, mock_unit):
    await connected_casambi_classic.setColor(mock_unit, (255, 0, 0))
    connected_casambi_classic._casaClient.send.assert_called_once()
    args, _ = connected_casambi_classic._casaClient.send.call_args
    pkt = args[0]
    assert pkt[-3:] == b"\xff\x00\x00"


async def test_set_color_xy(connected_casambi, mock_xy_unit):
    await connected_casambi.setColorXY(mock_xy_unit, (0.5, 0.5))
    connected_casambi._casaClient.send.assert_called_once()
    args, _ = connected_casambi._casaClient.send.call_args
    pkt = args[0]
    # x = 0.5, mask = 2047 -> 1024. y = 1024
    # (1024 << 11) | 1024 = 2098176 -> b'\x00\x04\x20' in little endian
    assert pkt[-3:] == b"\x00\x04\x20"


async def test_set_temperature(connected_casambi, mock_unit):
    await connected_casambi.setTemperature(mock_unit, 4000)
    connected_casambi._casaClient.send.assert_called_once()
    args, _ = connected_casambi._casaClient.send.call_args
    pkt = args[0]
    # 4000 / 50 = 80 -> b'\x50'
    assert pkt[-1:] == b"\x50"


async def test_set_color_xy_classic(connected_casambi_classic, mock_xy_unit):
    with pytest.raises(KeyError):
        await connected_casambi_classic.setColorXY(mock_xy_unit, (0.5, 0.5))


async def test_set_color_xy_invalid(connected_casambi, mock_unit, mock_xy_unit):
    with pytest.raises(ValueError):
        await connected_casambi.setColorXY(
            mock_unit, (0.5, 0.5)
        )  # Unit doesn't support XY
    with pytest.raises(ValueError):
        await connected_casambi.setColorXY(mock_xy_unit, (1.5, 0.5))  # Out of bounds


async def test_turn_on(connected_casambi, mock_unit):
    await connected_casambi.turnOn(mock_unit)
    connected_casambi._casaClient.send.assert_called_once()
    args, _ = connected_casambi._casaClient.send.call_args
    pkt = args[0]
    assert pkt[-2:] == b"\xff\x05"


async def test_turn_on_classic(connected_casambi_classic, mock_unit):
    await connected_casambi_classic.turnOn(mock_unit)
    connected_casambi_classic._casaClient.send.assert_called_once()
    args, _ = connected_casambi_classic._casaClient.send.call_args
    pkt = args[0]
    assert pkt[-5:] == b"\xff\x01\x00\x00\x01"


async def test_switch_to_scene(connected_casambi, mock_scene):
    await connected_casambi.switchToScene(mock_scene)
    connected_casambi._casaClient.send.assert_called_once()


async def test_switch_to_scene_classic(connected_casambi_classic, mock_scene):
    await connected_casambi_classic.switchToScene(mock_scene)
    connected_casambi_classic._casaClient.send.assert_called_once()


async def test_send_unsupported_target(connected_casambi):
    with pytest.raises(TypeError):
        await connected_casambi._send("unsupported", b"", OpCode.SetLevel)


def test_data_callback_unit_state(connected_casambi, mock_unit):
    handler = MagicMock()
    connected_casambi.registerUnitChangedHandler(handler)

    data = {"id": mock_unit.deviceId, "on": True, "online": True, "state": b"\x00"}

    mock_unit.setStateFromBytes = MagicMock()
    connected_casambi._dataCallback(IncomingPacketType.UnitState, data)

    mock_unit.setStateFromBytes.assert_called_once_with(b"\x00")
    assert mock_unit._on is True
    assert mock_unit._online is True
    handler.assert_called_once_with(mock_unit)

    connected_casambi.unregisterUnitChangedHandler(handler)
    assert handler not in connected_casambi._unitChangedCallbacks


def test_data_callback_switch_event(connected_casambi):
    handler = MagicMock()
    connected_casambi.registerSwitchEventHandler(handler)

    event = SwitchEvent(
        button_event_index=0,
        button=1,
        unit_id=1,
        target_type=0x06,
        event=ButtonEventType.PRESS,
        flags=0x00,
        extra_data=b"",
    )
    connected_casambi._dataCallback(IncomingPacketType.SwitchEvent, event)

    handler.assert_called_once_with(event)

    connected_casambi.unregisterSwitchEventHandler(handler)
    assert handler not in connected_casambi._switchEventCallbacks


def test_disconnect_callback(connected_casambi, mock_unit):
    handler = MagicMock()
    connected_casambi.registerDisconnectCallback(handler)

    unit_handler = MagicMock()
    connected_casambi.registerUnitChangedHandler(unit_handler)

    connected_casambi._disconnectCallback()

    assert mock_unit._online is False
    unit_handler.assert_called_once_with(mock_unit)
    handler.assert_called_once()

    connected_casambi.unregisterDisconnectCallback(handler)
    assert handler not in connected_casambi._disconnectCallbacks


async def test_disconnect(connected_casambi):
    mock_network = connected_casambi._casaNetwork
    await connected_casambi.disconnect()
    connected_casambi._casaClient.disconnect.assert_called_once()
    mock_network.disconnect.assert_called_once()
    assert connected_casambi._casaNetwork is None


async def test_set_control_value_patches_bits(connected_casambi, mock_unit):
    """setControlValue sends a packet with only the target bits changed."""
    control = mock_unit.unitType.controls[0]  # DIMMER, offset=0, length=8

    # Seed the unit with a known raw state
    mock_unit.setStateFromBytes(b"\xaa")

    await connected_casambi.setControlValue(mock_unit, control, 0x42)

    connected_casambi._casaClient.send.assert_called_once()
    args, _ = connected_casambi._casaClient.send.call_args
    pkt = args[0]
    assert pkt[-1] == 0x42


async def test_set_control_value_no_state_uses_zeros(connected_casambi, mock_unit):
    """setControlValue falls back to zero-filled bytes when there is no prior state."""
    control = mock_unit.unitType.controls[0]  # DIMMER, offset=0, length=8
    mock_unit._state = None

    await connected_casambi.setControlValue(mock_unit, control, 0x55)

    args, _ = connected_casambi._casaClient.send.call_args
    pkt = args[0]
    assert pkt[-1] == 0x55


async def test_set_control_value_updates_unit_state(connected_casambi, mock_unit):
    """After setControlValue the unit's state reflects the new value."""
    control = mock_unit.unitType.controls[0]  # DIMMER, offset=0, length=8
    mock_unit.setStateFromBytes(b"\x00")

    await connected_casambi.setControlValue(mock_unit, control, 200)

    assert mock_unit.state is not None
    assert mock_unit.state.dimmer == 200


async def test_set_control_value_preserves_other_bytes(connected_casambi):
    """setControlValue only modifies the target bits; adjacent bytes stay unchanged."""
    # Build a unit with two 8-bit controls: DIMMER at offset 0, WHITE at offset 8
    controls = [
        UnitControl(
            type=UnitControlType.DIMMER, offset=0, length=8, default=0, readonly=False
        ),
        UnitControl(
            type=UnitControlType.WHITE, offset=8, length=8, default=0, readonly=False
        ),
    ]
    ut = UnitType(
        id=99,
        model="test",
        manufacturer="test",
        mode="test",
        stateLength=2,
        controls=controls,
    )
    unit = Unit(
        _typeId=99,
        deviceId=99,
        uuid="x",
        address="x",
        name="x",
        firmwareVersion="1",
        unitType=ut,
    )
    unit.setStateFromBytes(b"\x0a\xc8")  # dimmer=10, white=200

    dimmer_ctrl = controls[0]
    await connected_casambi.setControlValue(unit, dimmer_ctrl, 0x42)

    args, _ = connected_casambi._casaClient.send.call_args
    pkt = args[0]
    assert pkt[-2] == 0x42  # dimmer updated
    assert pkt[-1] == 0xC8  # white unchanged
