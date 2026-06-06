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


def test_unit_state_presence() -> None:
    """presence property stores values in [0, 3] and rejects out-of-range."""
    state = UnitState()
    assert state.presence is None

    state.presence = 0
    assert state.presence == 0

    state.presence = 1
    assert state.presence == 1

    state.presence = 3
    assert state.presence == 3

    with pytest.raises(ValueError):
        state.presence = -1

    with pytest.raises(ValueError):
        state.presence = 4

    del state.presence
    assert state.presence is None


def test_unit_state_lux() -> None:
    """lux property stores values in [0, 4095] and rejects out-of-range."""
    state = UnitState()
    assert state.lux is None

    state.lux = 0
    assert state.lux == 0

    state.lux = 2048
    assert state.lux == 2048

    state.lux = 4095
    assert state.lux == 4095

    with pytest.raises(ValueError):
        state.lux = -1

    with pytest.raises(ValueError):
        state.lux = 4096

    del state.lux
    assert state.lux is None


def test_setStateFromBytes_decodes_presence() -> None:
    """PRESENCE control is decoded correctly into UnitState.presence."""
    unit = _make_unit(
        [
            UnitControl(
                type=UnitControlType.PRESENCE,
                offset=0,
                length=2,
                default=0,
                readonly=False,
            )
        ],
        state_length=1,
    )

    # 0b01 in bits [1:0] → presence = 1 (present)
    unit.setStateFromBytes(b"\x01")
    assert unit.state is not None
    assert unit.state.presence == 1

    # 0b00 → absent
    unit.setStateFromBytes(b"\x00")
    assert unit.state.presence == 0


def test_setStateFromBytes_decodes_lux() -> None:
    """LUX control is decoded correctly into UnitState.lux."""
    unit = _make_unit(
        [
            UnitControl(
                type=UnitControlType.LUX,
                offset=0,
                length=12,
                default=0,
                readonly=False,
            )
        ],
        state_length=2,
    )

    # 500 lux, little-endian 12-bit in 2 bytes: 500 = 0x1F4 → bytes 0xF4 0x01
    unit.setStateFromBytes(b"\xf4\x01")
    assert unit.state is not None
    assert unit.state.lux == 500

    unit.setStateFromBytes(b"\x00\x00")
    assert unit.state.lux == 0


def test_getStateAsBytes_encodes_presence() -> None:
    """PRESENCE control is encoded correctly from UnitState.presence."""
    unit = _make_unit(
        [
            UnitControl(
                type=UnitControlType.PRESENCE,
                offset=0,
                length=2,
                default=0,
                readonly=False,
            )
        ],
        state_length=1,
    )

    state = UnitState()
    state.presence = 1
    data = unit.getStateAsBytes(state)
    assert data[0] & 0x03 == 1

    state.presence = 0
    data = unit.getStateAsBytes(state)
    assert data[0] & 0x03 == 0


def test_getStateAsBytes_encodes_lux() -> None:
    """LUX control is encoded correctly from UnitState.lux."""
    unit = _make_unit(
        [
            UnitControl(
                type=UnitControlType.LUX,
                offset=0,
                length=12,
                default=0,
                readonly=False,
            )
        ],
        state_length=2,
    )

    state = UnitState()
    state.lux = 500
    data = unit.getStateAsBytes(state)
    val = int.from_bytes(data[:2], byteorder="little") & 0xFFF
    assert val == 500


def test_getStateAsBytes_preserves_unknown_control_current_value() -> None:
    """getStateAsBytes re-uses the last received value for UNKNOWN controls."""
    unit = _make_unit(
        [
            UnitControl(
                type=UnitControlType.UNKNOWN,
                offset=0,
                length=8,
                default=0,
                readonly=False,
            )
        ],
        state_length=1,
    )

    # Seed the unit with a known raw state — this stores value 0x2A in unknown_controls.
    unit.setStateFromBytes(b"\x2a")

    # Calling getStateAsBytes with an empty UnitState should NOT revert to default (0).
    state = UnitState()
    data = unit.getStateAsBytes(state)
    assert data == b"\x2a"


def test_getStateAsBytes_uses_default_when_no_state() -> None:
    """getStateAsBytes falls back to control.default when there is no prior state."""
    unit = _make_unit(
        [
            UnitControl(
                type=UnitControlType.UNKNOWN,
                offset=0,
                length=8,
                default=0xBE,
                readonly=False,
            )
        ],
        state_length=1,
    )
    # No setStateFromBytes called — _state is None.
    state = UnitState()
    data = unit.getStateAsBytes(state)
    assert data == bytes([0xBE])


# ---------------------------------------------------------------------------
# WHITECOLORBALANCE tests
# ---------------------------------------------------------------------------


def test_unit_state_white_balance() -> None:
    """white_balance range validation and del."""
    state = UnitState()
    assert state.white_balance is None

    state.white_balance = 0
    assert state.white_balance == 0

    state.white_balance = 63
    assert state.white_balance == 63

    with pytest.raises(ValueError):
        state.white_balance = -1

    with pytest.raises(ValueError):
        state.white_balance = 64

    del state.white_balance
    assert state.white_balance is None


def test_setStateFromBytes_decodes_white_color_balance() -> None:
    """setStateFromBytes populates white_balance for WHITECOLORBALANCE controls."""
    unit = _make_unit(
        [
            UnitControl(
                type=UnitControlType.WHITECOLORBALANCE,
                offset=0,
                length=6,
                default=0,
                readonly=False,
            )
        ],
        state_length=1,
    )

    unit.setStateFromBytes(bytes([0x2A]))  # 0x2A = 42
    assert unit.state is not None
    assert unit.state.white_balance == 42


def test_setStateFromBytes_resets_white_balance_on_each_call() -> None:
    """white_balance is overwritten, not accumulated, on repeated calls."""
    unit = _make_unit(
        [
            UnitControl(
                type=UnitControlType.WHITECOLORBALANCE,
                offset=0,
                length=6,
                default=0,
                readonly=False,
            )
        ],
        state_length=1,
    )

    unit.setStateFromBytes(bytes([10]))
    unit.setStateFromBytes(bytes([20]))
    assert unit.state is not None
    assert unit.state.white_balance == 20


def test_getStateAsBytes_writes_white_color_balance() -> None:
    """getStateAsBytes encodes white_balance into the correct bits."""
    unit = _make_unit(
        [
            UnitControl(
                type=UnitControlType.WHITECOLORBALANCE,
                offset=0,
                length=6,
                default=0,
                readonly=False,
            )
        ],
        state_length=1,
    )

    state = UnitState()
    state.white_balance = 42
    data = unit.getStateAsBytes(state)
    assert data[0] & 0x3F == 42  # lower 6 bits


def test_getStateAsBytes_preserves_white_balance_when_not_in_new_state() -> None:
    """white_balance from the last received state is preserved when not set in the new UnitState."""
    unit = _make_unit(
        [
            UnitControl(
                type=UnitControlType.WHITECOLORBALANCE,
                offset=0,
                length=6,
                default=0,
                readonly=False,
            )
        ],
        state_length=1,
    )

    unit.setStateFromBytes(bytes([31]))  # seed white_balance = 31

    # New state does not set white_balance → should preserve 31
    state = UnitState()
    data = unit.getStateAsBytes(state)
    assert data[0] & 0x3F == 31


def test_getStateAsBytes_uses_wcb_default_when_no_current_state() -> None:
    """Falls back to control.default when there is no prior state."""
    unit = _make_unit(
        [
            UnitControl(
                type=UnitControlType.WHITECOLORBALANCE,
                offset=0,
                length=6,
                default=10,
                readonly=False,
            )
        ],
        state_length=1,
    )

    # No setStateFromBytes called
    state = UnitState()
    data = unit.getStateAsBytes(state)
    assert data[0] & 0x3F == 10


def test_white_color_balance_not_in_unknown_controls() -> None:
    """WHITECOLORBALANCE values must not appear in unknown_controls."""
    unit = _make_unit(
        [
            UnitControl(
                type=UnitControlType.WHITECOLORBALANCE,
                offset=0,
                length=6,
                default=0,
                readonly=False,
            )
        ],
        state_length=1,
    )

    unit.setStateFromBytes(bytes([42]))
    assert unit.state is not None
    assert unit.state.unknown_controls == []
