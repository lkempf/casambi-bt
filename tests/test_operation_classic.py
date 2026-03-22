import pytest

from CasambiBt._operation import OpCode, OperationsContextClassic
from CasambiBt._unit import Group, Scene, Unit, UnitControl, UnitControlType, UnitType


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
    return Unit(
        _typeId=1,
        deviceId=10,
        uuid="uuid1",
        address="addr1",
        name="Unit 1",
        firmwareVersion="1.0",
        unitType=unit_type,
    )


@pytest.fixture
def mock_group():
    return Group(groudId=20, name="Group 1", units=[])


@pytest.fixture
def mock_scene():
    return Scene(sceneId=30, name="Scene 1")


@pytest.fixture
def context():
    return OperationsContextClassic()


def test_init(context):
    assert context._origin == 1
    assert context.lifetime == 200


def test_prepareOperation_no_target(context):
    payload = b"\x12\x34"
    op = OpCode.SetLevel

    packet = context.prepareOperation(op, None, payload)

    # Flags = 4 | 0x40 = 0x44 (68)
    assert len(packet) == 6
    assert packet[1] == 0x44
    assert packet[2] == 1  # origin
    assert packet[3] == 200  # lifetime
    assert packet[4:6] == payload
    assert packet[0] == (len(packet) + 239) & 0xFF
    assert context._origin == 2


def test_prepareOperation_unit_target(context, mock_unit):
    payload = b"\xff"
    op = OpCode.SetColor

    packet = context.prepareOperation(op, mock_unit, payload)

    # Flags = 9 | 0x40 | 0x80 = 0xC9 (201)
    assert len(packet) == 6
    assert packet[1] == 0xC9
    assert packet[2] == 1
    assert packet[3] == 10  # targetId
    assert packet[4] == 200
    assert packet[5:] == payload
    assert packet[0] == (len(packet) + 239) & 0xFF
    assert context._origin == 2


def test_prepareOperation_group_target(context, mock_group):
    payload = b"\x80"
    op = OpCode.SetVertical

    packet = context.prepareOperation(op, mock_group, payload)

    # Flags = 29 | 0x40 | 0x80 = 0xDD (221)
    assert len(packet) == 6
    assert packet[1] == 0xDD
    assert packet[2] == 1
    assert packet[3] == 20  # targetId
    assert packet[4] == 200
    assert packet[5:] == payload
    assert packet[0] == (len(packet) + 239) & 0xFF
    assert context._origin == 2


def test_prepareOperation_scene_target(context, mock_scene):
    payload = b""
    op = OpCode.SetLevel

    packet = context.prepareOperation(op, mock_scene, payload)

    # Flags = 1 | 0x40 | 0x80 = 0xC1 (193)
    assert len(packet) == 5
    assert packet[1] == 0xC1
    assert packet[2] == 1
    assert packet[3] == 30  # targetId
    assert packet[4] == 200
    assert packet[0] == (len(packet) + 239) & 0xFF
    assert context._origin == 2


def test_prepareOperation_payload_too_long(context):
    with pytest.raises(ValueError, match="Payload too long"):
        context.prepareOperation(OpCode.SetLevel, None, b"0" * 17)


def test_prepareOperation_origin_wrap(context):
    context._origin = 256
    packet = context.prepareOperation(OpCode.SetLevel, None, b"")
    assert packet[2] == 1
    assert context._origin == 2
