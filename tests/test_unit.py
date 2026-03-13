import pytest

from CasambiBt._unit import Unit, UnitControl, UnitControlType, UnitState, UnitType


def test_unit_state_dimmer():
    state = UnitState()
    assert state.dimmer is None

    state.dimmer = 100
    assert state.dimmer == 100

    state.dimmer = 0
    assert state.dimmer == 0

    state.dimmer = 255
    assert state.dimmer == 255

    with pytest.raises(ValueError):
        state.dimmer = -1

    with pytest.raises(ValueError):
        state.dimmer = 256

    del state.dimmer
    assert state.dimmer is None


def test_unit_state_rgb():
    state = UnitState()
    assert state.rgb is None

    state.rgb = (0, 128, 255)
    assert state.rgb == (0, 128, 255)

    with pytest.raises(ValueError):
        state.rgb = (-1, 0, 0)

    with pytest.raises(ValueError):
        state.rgb = (0, 256, 0)

    del state.rgb
    assert state.rgb is None


def test_unit_state_hs_conversion():
    state = UnitState()

    # Red
    state.hs = (0.0, 1.0)
    assert state.rgb is not None
    r, g, b = state.rgb
    assert r == 255
    assert g == 0
    assert b == 0

    # Green
    state.rgb = (0, 255, 0)
    assert state.hs is not None
    h, s = state.hs
    # Hue for green is 1/3 ~= 0.333
    assert abs(h - 1 / 3) < 0.01
    assert s == 1.0

    del state.rgb
    assert state.hs is None


def test_unit_state_white():
    state = UnitState()
    state.white = 100
    assert state.white == 100
    with pytest.raises(ValueError):
        state.white = 256
    del state.white
    assert state.white is None


def test_unit_state_xy():
    state = UnitState()
    state.xy = (0.1, 0.9)
    assert state.xy == (0.1, 0.9)
    with pytest.raises(ValueError):
        state.xy = (1.1, 0.5)
    del state.xy
    assert state.xy is None


def test_unit_state_vertical():
    state = UnitState()
    state.vertical = 50
    assert state.vertical == 50
    with pytest.raises(ValueError):
        state.vertical = 256
    del state.vertical
    assert state.vertical is None


def test_unit_state_slider():
    state = UnitState()
    state.slider = 10
    assert state.slider == 10
    with pytest.raises(ValueError):
        state.slider = 256
    del state.slider
    assert state.slider is None


def test_unit_is_on_priority():
    # Setup UnitType with ONOFF and DIMMER controls
    controls = [
        UnitControl(
            type=UnitControlType.ONOFF, offset=0, length=1, default=0, readonly=False
        ),
        UnitControl(
            type=UnitControlType.DIMMER, offset=1, length=8, default=0, readonly=False
        ),
    ]
    ut = UnitType(
        id=1,
        model="test",
        manufacturer="test",
        mode="test",
        stateLength=2,
        controls=controls,
    )
    unit = Unit(
        _typeId=1,
        deviceId=1,
        uuid="1",
        address="1",
        name="1",
        firmwareVersion="1",
        unitType=ut,
    )

    unit._on = True
    unit._state = UnitState()
    state = unit.state
    assert state is not None

    # If ONOFF control exists, it strictly uses onoff state
    state.onoff = True
    assert unit.is_on

    state.onoff = False
    assert not unit.is_on

    # Use del to clear the value
    del state.onoff
    assert not unit.is_on


def test_unit_is_on_dimmer_fallback():
    # Setup UnitType with only DIMMER control
    controls = [
        UnitControl(
            type=UnitControlType.DIMMER, offset=0, length=8, default=0, readonly=False
        )
    ]
    ut = UnitType(
        id=1,
        model="test",
        manufacturer="test",
        mode="test",
        stateLength=1,
        controls=controls,
    )
    unit = Unit(
        _typeId=1,
        deviceId=1,
        uuid="1",
        address="1",
        name="1",
        firmwareVersion="1",
        unitType=ut,
    )

    unit._on = True
    unit._state = UnitState()
    state = unit.state
    assert state is not None

    state.dimmer = 100
    assert unit.is_on

    state.dimmer = 0
    assert not unit.is_on

    del state.dimmer
    assert not unit.is_on


def test_unit_serialization_dimmer():
    controls = [
        UnitControl(
            type=UnitControlType.DIMMER, offset=0, length=8, default=0, readonly=False
        )
    ]
    ut = UnitType(
        id=1,
        model="test",
        manufacturer="test",
        mode="test",
        stateLength=1,
        controls=controls,
    )
    unit = Unit(
        _typeId=1,
        deviceId=1,
        uuid="1",
        address="1",
        name="1",
        firmwareVersion="1",
        unitType=ut,
    )

    state = UnitState()
    state.dimmer = 128

    # Test getStateAsBytes
    data = unit.getStateAsBytes(state)
    assert len(data) == 1
    assert data[0] == 128

    # Test setStateFromBytes
    unit.setStateFromBytes(b"\xff")
    assert unit.state is not None
    assert unit.state.dimmer == 255


def test_unit_serialization_rgb():
    # RGB control
    controls = [
        UnitControl(
            type=UnitControlType.RGB, offset=0, length=24, default=0, readonly=False
        )
    ]
    ut = UnitType(
        id=1,
        model="test",
        manufacturer="test",
        mode="test",
        stateLength=3,
        controls=controls,
    )
    unit = Unit(
        _typeId=1,
        deviceId=1,
        uuid="1",
        address="1",
        name="1",
        firmwareVersion="1",
        unitType=ut,
    )

    state = UnitState()
    state.rgb = (255, 0, 0)  # Red -> H=0, S=1

    data = unit.getStateAsBytes(state)

    # Verify we can read it back
    unit._state = None
    unit.setStateFromBytes(data)

    assert unit.state is not None
    assert unit.state.rgb is not None
    r, g, b = unit.state.rgb
    # Conversion might be lossy, allow some tolerance
    assert r == 255
    assert g == 0
    assert b == 0


@pytest.mark.parametrize(
    "color, expected_bytes",
    [
        ((255, 0, 0), b"\xff\x00\x00"),
        ((0, 255, 0), b"\x00\xff\x00"),
        ((0, 0, 255), b"\x00\x00\xff"),
        ((123, 45, 67), b"\x7b\x2d\x43"),
    ],
)
def test_unit_serialization_rgb_classic(color, expected_bytes):
    # RGB control
    controls = [
        UnitControl(
            type=UnitControlType.RGB, offset=0, length=24, default=0, readonly=False
        )
    ]
    ut = UnitType(
        id=1,
        model="test",
        manufacturer="test",
        mode="test",
        stateLength=3,
        controls=controls,
    )
    unit = Unit(
        _typeId=1,
        deviceId=1,
        uuid="1",
        address="1",
        name="1",
        firmwareVersion="1",
        unitType=ut,
        _isClassic=True,
    )

    state = UnitState()
    state.rgb = color

    data = unit.getStateAsBytes(state)
    assert data == expected_bytes

    # Verify we can read it back
    unit._state = None
    unit.setStateFromBytes(data)

    assert unit.state is not None
    assert unit.state.rgb is not None
    r, g, b = unit.state.rgb
    # Conversion might be lossy, allow some tolerance
    assert r == color[0]
    assert g == color[1]
    assert b == color[2]


def test_unit_serialization_mixed():
    # Dimmer (8 bits) + White (8 bits)
    controls = [
        UnitControl(
            type=UnitControlType.DIMMER, offset=0, length=8, default=0, readonly=False
        ),
        UnitControl(
            type=UnitControlType.WHITE, offset=8, length=8, default=0, readonly=False
        ),
    ]
    ut = UnitType(
        id=1,
        model="test",
        manufacturer="test",
        mode="test",
        stateLength=2,
        controls=controls,
    )
    unit = Unit(
        _typeId=1,
        deviceId=1,
        uuid="1",
        address="1",
        name="1",
        firmwareVersion="1",
        unitType=ut,
    )

    state = UnitState()
    state.dimmer = 10
    state.white = 200

    data = unit.getStateAsBytes(state)
    assert len(data) == 2
    assert data[0] == 10
    assert data[1] == 200

    unit._state = None
    unit.setStateFromBytes(b"\x64\x32")  # 100, 50
    assert unit.state is not None
    assert unit.state.dimmer == 100
    assert unit.state.white == 50


def test_unit_serialization_onoff():
    controls = [
        UnitControl(
            type=UnitControlType.ONOFF, offset=0, length=1, default=0, readonly=False
        )
    ]
    ut = UnitType(
        id=1,
        model="test",
        manufacturer="test",
        mode="test",
        stateLength=1,
        controls=controls,
    )
    unit = Unit(
        _typeId=1,
        deviceId=1,
        uuid="1",
        address="1",
        name="1",
        firmwareVersion="1",
        unitType=ut,
    )

    state = UnitState()
    state.onoff = True

    data = unit.getStateAsBytes(state)
    # 1 bit set in first byte
    assert data[0] & 0x01

    unit._state = None
    unit.setStateFromBytes(b"\x01")
    assert unit.state is not None
    assert unit.state.onoff is True

    unit.setStateFromBytes(b"\x00")
    assert unit.state is not None
    assert unit.state.onoff is False


def test_unit_serialization_temperature():
    # Temperature control with min/max
    controls = [
        UnitControl(
            type=UnitControlType.TEMPERATURE,
            offset=0,
            length=16,
            default=0,
            readonly=False,
            min=2000,
            max=6000,
        )
    ]
    ut = UnitType(
        id=1,
        model="test",
        manufacturer="test",
        mode="test",
        stateLength=2,
        controls=controls,
    )
    unit = Unit(
        _typeId=1,
        deviceId=1,
        uuid="1",
        address="1",
        name="1",
        firmwareVersion="1",
        unitType=ut,
    )

    state = UnitState()
    state.temperature = 4000

    # Range 2000-6000 (span 4000). Value 4000 is mid-point.
    # 16-bit max is 65535. Mid-point roughly 32767.

    data = unit.getStateAsBytes(state)
    assert len(data) == 2

    val = int.from_bytes(data, byteorder="little")
    # Expected: (65535 * (4000 - 2000)) // (6000 - 2000) = 65535 * 2000 // 4000 = 32767
    assert abs(val - 32767) < 5

    # Test deserialize
    # If we feed it back, it should map back to ~4000
    unit._state = None
    unit.setStateFromBytes(data)
    assert unit.state is not None
    assert unit.state.temperature is not None
    assert abs(unit.state.temperature - 4000) < 5


def _make_unit(controls: list[UnitControl], state_length: int) -> Unit:
    """Build a minimal Unit for testing."""
    ut = UnitType(
        id=1,
        model="test",
        manufacturer="test",
        mode="test",
        stateLength=state_length,
        controls=controls,
    )
    return Unit(
        _typeId=1,
        deviceId=1,
        uuid="1",
        address="1",
        name="1",
        firmwareVersion="1",
        unitType=ut,
    )


def test_unit_state_raw_state() -> None:
    """raw_state is None initially, then mirrors the bytes passed to setStateFromBytes."""
    state = UnitState()
    assert state.raw_state is None

    unit = _make_unit(
        [
            UnitControl(
                type=UnitControlType.DIMMER,
                offset=0,
                length=8,
                default=0,
                readonly=False,
            )
        ],
        state_length=1,
    )

    unit.setStateFromBytes(b"\xff")
    assert unit.state is not None
    assert unit.state.raw_state == b"\xff"

    # Second call must overwrite, not accumulate.
    unit.setStateFromBytes(b"\x00")
    assert unit.state.raw_state == b"\x00"


def test_unit_state_unknown_controls() -> None:
    """unknown_controls captures UNKOWN controls and returns a defensive copy."""
    unit = _make_unit(
        [
            UnitControl(
                type=UnitControlType.UNKOWN,
                offset=0,
                length=8,
                default=0,
                readonly=False,
            )
        ],
        state_length=1,
    )

    unit.setStateFromBytes(b"\x2a")
    assert unit.state is not None
    assert unit.state.unknown_controls == [(0, 8, 0x2A)]

    # Mutating the returned list must not affect internal state.
    copy = unit.state.unknown_controls
    copy.clear()
    assert unit.state.unknown_controls == [(0, 8, 0x2A)]


def test_unit_state_unknown_controls_reset() -> None:
    """unknown_controls is cleared on each setStateFromBytes call (no accumulation)."""
    unit = _make_unit(
        [
            UnitControl(
                type=UnitControlType.UNKOWN,
                offset=0,
                length=8,
                default=0,
                readonly=False,
            )
        ],
        state_length=1,
    )

    unit.setStateFromBytes(b"\x01")
    assert unit.state is not None
    assert len(unit.state.unknown_controls) == 1

    unit.setStateFromBytes(b"\x02")
    controls = unit.state.unknown_controls
    assert len(controls) == 1
    assert controls[0][2] == 0x02
