"""Tests for sensor platform support: element_names, UnitState.sensors, Unit.sensor_cache."""

import warnings

from CasambiBt._unit import Unit, UnitControl, UnitControlType, UnitType

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_unit(
    controls: list[UnitControl],
    state_length: int,
    mode: str = "test",
) -> Unit:
    """Build a minimal Unit for testing."""
    ut = UnitType(
        id=1,
        model="test",
        manufacturer="test",
        mode=mode,
        stateLength=state_length,
        controls=controls,
    )
    return Unit(
        _typeId=1,
        deviceId=1,
        uuid="test-uuid",
        address="00:00:00:00:00:01",
        name="test",
        firmwareVersion="1.0",
        unitType=ut,
    )


# ── UnitType.element_names ─────────────────────────────────────────────────────


def test_element_names_dali_sensor() -> None:
    """DALI Sensor mode with two element names."""
    ut = UnitType(
        id=1,
        model="m",
        manufacturer="v",
        mode="DALI Sensor{Presence,Daylight}",
        stateLength=2,
        controls=[],
    )
    assert ut.element_names == ["Presence", "Daylight"]


def test_element_names_ext_elements() -> None:
    """EXT/Elements mode with two element names."""
    ut = UnitType(
        id=1,
        model="m",
        manufacturer="v",
        mode="EXT/Elements{Presence,Daylight}",
        stateLength=5,
        controls=[],
    )
    assert ut.element_names == ["Presence", "Daylight"]


def test_element_names_single() -> None:
    """Mode with a single element name."""
    ut = UnitType(
        id=1,
        model="m",
        manufacturer="v",
        mode="DALI Sensor{Motion}",
        stateLength=1,
        controls=[],
    )
    assert ut.element_names == ["Motion"]


def test_element_names_strips_whitespace() -> None:
    """Whitespace around names is stripped."""
    ut = UnitType(
        id=1,
        model="m",
        manufacturer="v",
        mode="DALI Sensor{ Presence , Daylight }",
        stateLength=2,
        controls=[],
    )
    assert ut.element_names == ["Presence", "Daylight"]


def test_element_names_no_braces() -> None:
    """Regular modes without braces return an empty list."""
    for mode in ("PWM/Dim", "EXT/1ch/Dim", "Kinetic Switch", "Sensor"):
        ut = UnitType(
            id=1, model="m", manufacturer="v", mode=mode, stateLength=1, controls=[]
        )
        assert ut.element_names == [], f"Expected [] for mode {mode!r}"


def test_element_names_empty_braces() -> None:
    """Empty braces return an empty list."""
    ut = UnitType(
        id=1,
        model="m",
        manufacturer="v",
        mode="DALI Sensor{}",
        stateLength=1,
        controls=[],
    )
    assert ut.element_names == []


# ── UnitState.sensors (DALI-2 style: UNKNOWN controls + element names) ─────────


def test_sensors_populated_from_unknown_controls() -> None:
    """UNKNOWN controls are keyed by element name when mode has element_names."""
    # Simulate DALI-2: 2 UNKOWN controls at offsets 0 and 2 (2 bits presence + 12 bits lux)
    unit = _make_unit(
        controls=[
            UnitControl(
                type=UnitControlType.UNKNOWN,
                offset=0,
                length=2,
                default=0,
                readonly=True,
            ),
            UnitControl(
                type=UnitControlType.UNKNOWN,
                offset=2,
                length=12,
                default=0,
                readonly=True,
            ),
        ],
        state_length=2,
        mode="DALI Sensor{Presence,Daylight}",
    )
    # Encode: presence=1 (bits 0-1), lux=512 (bits 2-13)
    # 1 in bits[1:0], 512 in bits[13:2]
    # 512 << 2 = 2048 = 0x0800
    # combined: 0x0800 | 0x01 = 0x0801 → little-endian bytes: 0x01, 0x08
    unit.setStateFromBytes(b"\x01\x08")
    assert unit.state is not None
    assert unit.state.sensors == {"Presence": 1, "Daylight": 512}


def test_sensors_partial_names() -> None:
    """Only UNKNOWN controls with a corresponding element name get a key; extras go to unknown_controls only."""
    unit = _make_unit(
        controls=[
            UnitControl(
                type=UnitControlType.UNKNOWN,
                offset=0,
                length=8,
                default=0,
                readonly=True,
            ),
            UnitControl(
                type=UnitControlType.UNKNOWN,
                offset=8,
                length=8,
                default=0,
                readonly=True,
            ),
        ],
        state_length=2,
        mode="DALI Sensor{OnlyOne}",  # only 1 name, 2 controls
    )
    unit.setStateFromBytes(b"\x0a\x0b")
    assert unit.state is not None
    assert unit.state.sensors == {"OnlyOne": 0x0A}
    assert len(unit.state.unknown_controls) == 2


def test_sensors_empty_without_element_names() -> None:
    """No element names in mode → sensors dict is always empty."""
    unit = _make_unit(
        controls=[
            UnitControl(
                type=UnitControlType.UNKNOWN,
                offset=0,
                length=8,
                default=0,
                readonly=True,
            ),
        ],
        state_length=1,
        mode="PWM/Dim",
    )
    unit.setStateFromBytes(b"\xff")
    assert unit.state is not None
    assert unit.state.sensors == {}
    # unknown_controls still populated as before
    assert unit.state.unknown_controls == [(0, 8, 0xFF)]


def test_sensors_reset_each_call() -> None:
    """sensors dict is cleared on each setStateFromBytes call (no accumulation)."""
    unit = _make_unit(
        controls=[
            UnitControl(
                type=UnitControlType.UNKNOWN,
                offset=0,
                length=8,
                default=0,
                readonly=True,
            ),
        ],
        state_length=1,
        mode="DALI Sensor{Presence}",
    )
    unit.setStateFromBytes(b"\x01")
    assert unit.state is not None
    assert unit.state.sensors == {"Presence": 1}

    unit.setStateFromBytes(b"\x00")
    assert unit.state.sensors == {"Presence": 0}


def test_sensors_returns_copy() -> None:
    """Mutating the returned dict does not affect internal state."""
    unit = _make_unit(
        controls=[
            UnitControl(
                type=UnitControlType.UNKNOWN,
                offset=0,
                length=8,
                default=0,
                readonly=True,
            ),
        ],
        state_length=1,
        mode="DALI Sensor{Presence}",
    )
    unit.setStateFromBytes(b"\x01")
    copy = unit.state.sensors  # type: ignore[union-attr]
    copy["Presence"] = 99
    assert unit.state.sensors == {"Presence": 1}  # type: ignore[union-attr]


# ── Unit.sensor_cache (EXT/Elements multiplexed protocol) ──────────────────────


def _ext_elements_unit() -> Unit:
    """Build an EXT/Elements unit with SENSOR controls (simplified: 1 control)."""
    return _make_unit(
        controls=[
            UnitControl(
                type=UnitControlType.SENSOR,
                offset=0,
                length=8,
                default=0,
                readonly=True,
            ),
        ],
        state_length=5,
        mode="EXT/Elements{Presence,Daylight}",
    )


def test_sensor_cache_initially_empty() -> None:
    """sensor_cache is empty before any state update."""
    unit = _ext_elements_unit()
    assert unit.sensor_cache == {}


def test_sensor_cache_accumulates_across_packets() -> None:
    """Successive packets with different packet_types all accumulate in sensor_cache."""
    unit = _ext_elements_unit()

    # packet_type=0 (rain): raw[1] bits[7:6]=00 → raw[1]=0x00, raw[2]=1
    unit.setStateFromBytes(b"\x04\x00\x01\x00\x3c")
    assert unit.sensor_cache == {0: 1}

    # packet_type=1 (wind): raw[1] bits[7:6]=01 → raw[1]=0x40, raw[2]=12
    unit.setStateFromBytes(b"\x04\x40\x0c\x00\x3c")
    assert unit.sensor_cache == {0: 1, 1: 12}

    # packet_type=2 (solar): raw[1] bits[7:6]=10 → raw[1]=0x80, raw[2]=68
    unit.setStateFromBytes(b"\x04\x80\x44\x00\x3c")
    assert unit.sensor_cache == {0: 1, 1: 12, 2: 68}

    # packet_type=3 (PIR): raw[1] bits[7:6]=11 → raw[1]=0xC0, raw[2]=0
    unit.setStateFromBytes(b"\x04\xc0\x00\x00\x3c")
    assert unit.sensor_cache == {0: 1, 1: 12, 2: 68, 3: 0}


def test_sensor_cache_updates_existing_key() -> None:
    """A new packet for the same packet_type overwrites the previous value."""
    unit = _ext_elements_unit()

    unit.setStateFromBytes(b"\x04\x00\x01\x00\x3c")  # rain = 1
    unit.setStateFromBytes(b"\x04\x00\x05\x00\x3c")  # rain = 5
    assert unit.sensor_cache[0] == 5


def test_sensor_cache_not_reset_between_calls() -> None:
    """sensor_cache persists across calls; only updated entries change."""
    unit = _ext_elements_unit()

    unit.setStateFromBytes(b"\x04\x00\x01\x00\x3c")  # packet_type=0
    unit.setStateFromBytes(b"\x04\x40\x0c\x00\x3c")  # packet_type=1

    # Both keys must still be present after two distinct packets
    assert 0 in unit.sensor_cache
    assert 1 in unit.sensor_cache


def test_sensor_cache_only_for_ext_elements() -> None:
    """sensor_cache is not populated for non-EXT/Elements modes."""
    unit = _make_unit(
        controls=[
            UnitControl(
                type=UnitControlType.SENSOR,
                offset=0,
                length=8,
                default=0,
                readonly=True,
            ),
        ],
        state_length=5,
        mode="DALI Sensor{Presence,Daylight}",
    )
    unit.setStateFromBytes(b"\x04\x40\x0c\x00\x3c")
    assert unit.sensor_cache == {}


def test_sensor_cache_ignores_short_packets() -> None:
    """Packets shorter than 3 bytes do not update the cache."""
    unit = _ext_elements_unit()
    unit.setStateFromBytes(b"\x04\x40")  # only 2 bytes
    assert unit.sensor_cache == {}


def test_sensor_cache_returns_copy() -> None:
    """Mutating the returned dict does not affect internal state."""
    unit = _ext_elements_unit()
    unit.setStateFromBytes(b"\x04\x00\x01\x00\x3c")
    copy = unit.sensor_cache
    copy[0] = 99
    assert unit.sensor_cache[0] == 1


# ── UnitControlType.UNKOWN deprecation + UNIMPLEMENTED distinction ──────────────


def test_unkown_alias_emits_deprecation_warning() -> None:
    """Accessing UNKOWN raises DeprecationWarning and returns the UNKNOWN member."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        alias = (
            UnitControlType.UNKOWN
        )  # noqa: F841 — intentionally testing deprecated access
    assert len(caught) == 1
    assert issubclass(caught[0].category, DeprecationWarning)
    assert "UNKOWN" in str(caught[0].message)
    assert alias is UnitControlType.UNKNOWN


def test_unimplemented_not_in_unknown_controls() -> None:
    """UNIMPLEMENTED controls are NOT included in unknown_controls or sensors."""
    unit = _make_unit(
        controls=[
            UnitControl(
                type=UnitControlType.UNIMPLEMENTED,
                offset=0,
                length=8,
                default=0,
                readonly=True,
            ),
            UnitControl(
                type=UnitControlType.UNKNOWN,
                offset=8,
                length=8,
                default=0,
                readonly=True,
            ),
        ],
        state_length=2,
        mode="DALI Sensor{Sensor1}",
    )
    unit.setStateFromBytes(b"\x0a\x0b")
    assert unit.state is not None
    # Only the UNKNOWN control appears in unknown_controls
    assert len(unit.state.unknown_controls) == 1
    assert unit.state.unknown_controls[0] == (8, 8, 0x0B)
    # And sensors only maps the UNKNOWN control
    assert unit.state.sensors == {"Sensor1": 0x0B}
