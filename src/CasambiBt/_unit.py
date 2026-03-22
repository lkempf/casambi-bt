import logging
from binascii import b2a_hex as b2a
from colorsys import hsv_to_rgb, rgb_to_hsv
from dataclasses import dataclass
from enum import Enum, unique
from typing import Final

_LOGGER = logging.getLogger(__name__)


# Numbers are totally arbitrary so far.
@unique
class UnitControlType(Enum):
    """All implemented control types."""

    DIMMER = 0
    """The brightness of the light can be adjusted."""

    WHITE = 1
    """The amount of white in the light can be adjusted."""

    RGB = 2
    """The color of the light can be adjusted."""

    ONOFF = 3
    """The unit can be turned on or off."""

    TEMPERATURE = 4
    """The temperature of the light can be adjusted."""

    VERTICAL = 5
    """The vertical value of the light can be adjusted."""

    COLORSOURCE = 6
    """The light can switch color source. (TW, RGB, XY)"""

    XY = 7
    """The color of the light can be controlled using CIE color space."""

    SLIDER = 8
    """The slider of the light can be adjusted."""

    SENSOR = 9
    """A sensor value of the light."""

    UNKOWN = 99
    """State isn't implemented. Control saved for debuggin purposes."""


@unique
class ColorSource(Enum):
    """The possible values for the color source control."""

    TEMPERATURE = 0
    RGB = 1
    XY = 2


@dataclass(frozen=True, repr=True)
class UnitControl:
    type: UnitControlType
    offset: int
    length: int
    default: int
    readonly: bool

    min: int | None = None
    max: int | None = None


@dataclass(frozen=True, repr=True)
class UnitType:
    """Each ``Unit`` has one type that describes what the model is capable of.

    :ivar model: The model name of this unit type.
    :ivar manufacturer: The manufacturer of this unit type.
    :ivar controls: The different types of controls this unit type is capable of.
    """

    id: int
    model: str
    manufacturer: str
    mode: str
    stateLength: int
    controls: list[UnitControl]

    def get_control(self, controlType: UnitControlType) -> UnitControl | None:
        """Return the control description if the unit type supports the given type of control.

        :param controlType: The desired control type.
        :return: A control description for the given control type if available, otherwise `None`
        """
        for c in self.controls:
            if c.type == controlType:
                return c

        return None


# TODO: Support for different resolutions?
# TODO: Work with HS instead of RGB internally
class UnitState:
    """Parsed representation of the state of a unit."""

    def __init__(self) -> None:
        self._dimmer: int | None = None
        self._rgb: tuple[int, int, int] | None = None
        self._white: int | None = None
        self._temperature: int | None = None
        self._vertical: int | None = None
        self._colorsource: ColorSource | None = None
        self._xy: tuple[float, float] | None = None
        self._slider: int | None = None
        self._onoff: bool | None = None
        self._raw_state: bytes | None = None
        self._unknown_controls: list[tuple[int, int, int]] = []

    @property
    def raw_state(self) -> bytes | None:
        """Return the raw BLE state bytes last received for this unit, or None if not yet set."""
        return self._raw_state

    @property
    def unknown_controls(self) -> list[tuple[int, int, int]]:
        """Return a copy of the list of unknown controls parsed from the last state update.

        Each entry is a tuple of ``(bit_offset, bit_length, value)`` corresponding to a
        control whose type is :attr:`UnitControlType.UNKOWN`.
        """
        return list(self._unknown_controls)

    def _check_range(
        self, value: int | float, min: int | float, max: int | float
    ) -> None:
        if value < min or value > max:
            raise ValueError(f"{value} is not between {min} and {max}")

    DIMMER_RESOLUTION: Final = 8
    DIMMER_MIN: Final = 0
    DIMMER_MAX: Final = 2**DIMMER_RESOLUTION - 1

    @property
    def dimmer(self) -> int | None:
        return self._dimmer

    @dimmer.setter
    def dimmer(self, value: int) -> None:
        self._check_range(value, self.DIMMER_MIN, self.DIMMER_MAX)
        self._dimmer = value

    @dimmer.deleter
    def dimmer(self) -> None:
        self._dimmer = None

    VERTICAL_RESOLUTION: Final = 8
    VERTICAL_MIN: Final = 0
    VERTICAL_MAX: Final = 2**VERTICAL_RESOLUTION - 1

    @property
    def vertical(self) -> int | None:
        return self._vertical

    @vertical.setter
    def vertical(self, value: int) -> None:
        self._check_range(value, self.VERTICAL_MIN, self.VERTICAL_MAX)
        self._vertical = value

    @vertical.deleter
    def vertical(self) -> None:
        self._vertical = None

    RGB_RESOLUTION: Final = 8
    RGB_MIN: Final = 0
    RGB_MAX: Final = 2**RGB_RESOLUTION - 1

    @property
    def rgb(self) -> tuple[int, int, int] | None:
        return self._rgb

    @rgb.setter
    def rgb(self, value: tuple[int, int, int]) -> None:
        r, g, b = value
        self._check_range(r, self.RGB_MIN, self.RGB_MAX)
        self._check_range(g, self.RGB_MIN, self.RGB_MAX)
        self._check_range(b, self.RGB_MIN, self.RGB_MAX)

        self._rgb = (r, g, b)

    @rgb.deleter
    def rgb(self) -> None:
        self._rgb = None

    @property
    def hs(self) -> tuple[float, float] | None:
        """Convert RGB into HS where H is a float in [0..1[ and S a float in [0..1]."""
        if self._rgb is None:
            return None

        rgb_float = [c / (2**self.RGB_RESOLUTION - 1) for c in self._rgb]
        h, s, _ = rgb_to_hsv(*rgb_float)

        h %= 1
        if h == 0 and s == 0:
            h = 0.5

        return (h, s)

    @hs.setter
    def hs(self, value: tuple[float, float]) -> None:
        """Convert HS color to internal RBG representation where H is a float in [0..1[ and S a float in [0..1]."""
        h, s = value

        rgb = hsv_to_rgb(h, s, 1)
        self.rgb = tuple([round(c * (2**self.RGB_RESOLUTION - 1)) for c in rgb])  # type: ignore[assignment]

    WHITE_RESOLUTION = 8
    WHITE_MIN = 0
    WHITE_MAX = 2**WHITE_RESOLUTION - 1

    @property
    def white(self) -> int | None:
        return self._white

    @white.setter
    def white(self, value: int) -> None:
        self._check_range(value, self.WHITE_MIN, self.WHITE_MAX)
        self._white = value

    @white.deleter
    def white(self) -> None:
        self._white = None

    @property
    def temperature(self) -> int | None:
        return self._temperature

    @temperature.setter
    def temperature(self, value: int) -> None:
        self._temperature = value

    @temperature.deleter
    def temperature(self) -> None:
        self._temperature = None

    @property
    def colorsource(self) -> ColorSource | None:
        return self._colorsource

    @colorsource.setter
    def colorsource(self, value: ColorSource) -> None:
        self._colorsource = value

    @colorsource.deleter
    def colorsource(self) -> None:
        self._colorsource = None

    @property
    def xy(self) -> tuple[float, float] | None:
        return self._xy

    @xy.setter
    def xy(self, value: tuple[float, float]) -> None:
        x, y = value
        self._check_range(x, 0, 1)
        self._check_range(y, 0, 1)
        self._xy = (x, y)

    @xy.deleter
    def xy(self) -> None:
        self._xy = None

    SLIDER_RESOLUTION: Final = 8
    SLIDER_MIN: Final = 0
    SLIDER_MAX: Final = 2**VERTICAL_RESOLUTION - 1

    @property
    def slider(self) -> int | None:
        return self._slider

    @slider.setter
    def slider(self, value: int) -> None:
        self._check_range(value, self.SLIDER_MIN, self.SLIDER_MAX)
        self._slider = value

    @slider.deleter
    def slider(self) -> None:
        self._slider = None

    @property
    def onoff(self) -> bool | None:
        return self._onoff

    @onoff.setter
    def onoff(self, value: bool) -> None:
        self._onoff = value

    @onoff.deleter
    def onoff(self) -> None:
        self._onoff = None

    def __repr__(self) -> str:
        return f"UnitState(dimmer={self.dimmer}, vertical={self.vertical}, rgb={self.rgb.__repr__()}, white={self.white}, temperature={self.temperature}, colorsource={self.colorsource}, xy={self.xy}, slider={self.slider}, onoff={self.onoff})"

    @staticmethod
    def int_from_hs(hs: tuple[float, float], length: int) -> int:
        hueLen = (length * 10) // 18
        assert hueLen > 0, "Invalid HS length"
        hueMask: int = 2**hueLen - 1
        satLen = length - hueLen
        assert satLen > 0, "Invalid HS length"
        satMask: int = 2**satLen - 1

        h, s = hs
        return ((round(h * hueMask) & hueMask) << satLen) + (
            round(s * satMask) & satMask
        )

    @staticmethod
    def hs_from_int(val: int, length: int) -> tuple[float, float]:
        hueLen = (length * 10) // 18
        assert hueLen > 0, "Invalid HS length"
        hueMask: int = 2**hueLen - 1
        satLen = length - hueLen
        assert satLen > 0, "Invalid HS length"
        satMask: int = 2**satLen - 1

        h = (val >> satLen) / hueMask
        s = (val & satMask) / satMask
        return (h, s)

    @staticmethod
    def int_from_rgb(rgb: tuple[int, int, int], length: int) -> int:
        assert length % 3 == 0, "Invalid RGB length"
        scale = UnitState.RGB_RESOLUTION - (length // 3)
        scaledValue = 0
        for i in range(3):
            scaledValue += (rgb[i] >> scale) * 2 ** ((length // 3) * i)
        return scaledValue

    @staticmethod
    def rgb_from_int(val: int, length: int) -> tuple[int, int, int]:
        assert length % 3 == 0, "Invalid RGB length"
        compLen = length // 3
        rgb = []
        scale = UnitState.RGB_RESOLUTION - compLen

        for i in range(3):
            v = (val >> (i * compLen)) & (2**compLen - 1)
            v <<= scale
            rgb.append(v)
        return tuple(rgb)

    @staticmethod
    def int_from_xy(xy: tuple[float, float], length: int) -> int:
        coordLen = length // 2
        assert coordLen > 0, "Invalid XY length"
        x, y = xy
        xyMask: int = 2**coordLen - 1
        return (round(x * xyMask) << coordLen) | round(y * xyMask)

    @staticmethod
    def xy_from_int(val: int, length: int) -> tuple[float, float]:
        coordLen = length // 2
        assert coordLen > 0, "Invalid XY length"
        xyMask: int = 2**coordLen - 1
        y = val & xyMask
        x = (val >> coordLen) & xyMask
        return (x / xyMask, y / xyMask)

    @staticmethod
    def int_from_temperature(
        temperature: int, min_temp: int, max_temp: int, length: int
    ) -> int:
        clampedTemp = min(max_temp, max(min_temp, temperature))
        assert length > 0, "Invalid temp length"
        tempMask: int = 2**length - 1
        return (tempMask * (clampedTemp - min_temp)) // (max_temp - min_temp)

    @staticmethod
    def temperature_from_int(
        val: int, min_temp: int, max_temp: int, length: int
    ) -> int:
        tempRange = max_temp - min_temp
        assert length > 0, "Invalid temp length"
        tempMask: int = 2**length - 1
        return int(((val / tempMask) * tempRange) + min_temp)

    @staticmethod
    def payload_from_hs(hs: tuple[float, float]) -> bytes:
        val = UnitState.int_from_hs(hs, 18)
        hue = val >> 8
        sat = val & 0xFF
        return hue.to_bytes(2, byteorder="little", signed=False) + sat.to_bytes(
            1, byteorder="little", signed=False
        )

    @staticmethod
    def payload_from_rgb(rgb: tuple[int, int, int], length: int = 24) -> bytes:
        val = UnitState.int_from_rgb(rgb, length)
        return val.to_bytes(3, byteorder="little", signed=False)

    @staticmethod
    def payload_from_xy(xy: tuple[float, float], length: int = 22) -> bytes:
        val = UnitState.int_from_xy(xy, length)
        return val.to_bytes(3, byteorder="little", signed=False)

    @staticmethod
    def payload_from_temperature(temperature: int) -> bytes:
        temp = int(temperature / 50)
        return temp.to_bytes(1, byteorder="little", signed=False)


# TODO: Make unit immutable (refactor state, on, online out of it)
@dataclass(init=True, repr=True)
class Unit:
    """A unit in a network.

    :ivar deviceId: Id of the unit within the network.
    :ivar uuid: Globally unique id of the unit.
    :ivar address: MAC address of the unit.
    :ivar name: User assigned name of the unit.
    :ivar firmwareVersion: Firmware version of the unit.

    :ivar unitType: Type of the unit. Determines the capabilities.
    """

    _typeId: int
    deviceId: int
    uuid: str
    address: str
    name: str
    firmwareVersion: str

    unitType: UnitType

    _state: UnitState | None = None
    _on: bool = False
    _online: bool = False
    _isClassic: bool = False

    @property
    def state(self) -> UnitState | None:
        """Get the state of the unit if it has been set."""
        return self._state

    @property
    def is_on(self) -> bool:
        """Determine whether the unit is turned on."""
        if self.unitType.get_control(UnitControlType.ONOFF) and self._state:
            return self._on and self._state.onoff is True
        if self.unitType.get_control(UnitControlType.DIMMER) and self._state:
            return (
                self._on and self._state.dimmer is not None and self._state.dimmer > 0
            )
        else:
            return self._on

    @property
    def online(self) -> bool:
        return self._online

    # TODO: Add tests for this method
    def getStateAsBytes(self, state: UnitState) -> bytes:
        """Given a generic UnitState convert it into the internal state representation.

        Unsupported state information will be ignored.
        """

        # offset, lenth, value
        values: list[tuple[int, int, int]] = []

        # TODO: Support for resolutions >8 byte?
        # Parse and convert state
        for c in self.unitType.controls:
            if c.type == UnitControlType.DIMMER and state.dimmer is not None:
                scale = UnitState.DIMMER_RESOLUTION - c.length
                scaledValue = state.dimmer >> scale
            elif c.type == UnitControlType.VERTICAL and state.vertical is not None:
                scale = UnitState.VERTICAL_RESOLUTION - c.length
                scaledValue = state.vertical >> scale
            elif c.type == UnitControlType.RGB and state.rgb is not None:
                if self._isClassic:
                    scaledValue = UnitState.int_from_rgb(state.rgb, c.length)
                else:
                    scaledValue = UnitState.int_from_hs(state.hs, c.length)  # type: ignore[arg-type]
            elif c.type == UnitControlType.WHITE and state.white is not None:
                scale = UnitState.WHITE_RESOLUTION - c.length
                scaledValue = state.white >> scale
            elif (
                c.type == UnitControlType.TEMPERATURE
                and state.temperature is not None
                and c.min is not None
                and c.max is not None
            ):
                scaledValue = UnitState.int_from_temperature(
                    state.temperature, c.min, c.max, c.length
                )
            elif (
                c.type == UnitControlType.COLORSOURCE and state.colorsource is not None
            ):
                scaledValue = state.colorsource.value
            elif c.type == UnitControlType.XY and state.xy is not None:
                scaledValue = UnitState.int_from_xy(state.xy, c.length)
            elif c.type == UnitControlType.SLIDER and state.slider is not None:
                scale = UnitState.SLIDER_RESOLUTION - c.length
                scaledValue = state.slider >> scale
            elif c.type == UnitControlType.ONOFF and state.onoff is not None:
                scaledValue = 1 if state.onoff else 0

            # Use default if unsupported type or unset value in state
            else:
                scaledValue = c.default

            values.append((c.offset, c.length, scaledValue))

        # Pack state into bytes
        res = bytearray(self.unitType.stateLength)
        for off, len, val in values:
            val <<= off % 8
            byteLen = (len + off % 8 - 1) // 8 + 1
            valBytes = val.to_bytes(byteLen, byteorder="little", signed=False)
            for i in range(byteLen):
                res[off // 8] |= valBytes[i]
                off += 8 - off % 8

        _LOGGER.debug(f"Packing {values.__repr__()} as {res}")
        return bytes(res)

    # TODO: Add tests for this method
    def setStateFromBytes(self, value: bytes) -> None:
        """Parse state bytes into a `UnitState` and set it for the current unit.

        :param value: State bytes for the unit.
        """
        if not self._state:
            self._state = UnitState()

        self._state._raw_state = value
        self._state._unknown_controls = []

        # TODO: Support for resolutions >8 byte?
        for c in self.unitType.controls:
            # Extract all relevant bytes from the state
            byteLen = (c.length + c.offset % 8 - 1) // 8 + 1
            cBytes = value[c.offset // 8 : c.offset // 8 + byteLen]

            # Extract c.Length bits form the byte string
            cInt = int.from_bytes(cBytes, byteorder="little", signed=False)
            cInt >>= c.offset % 8
            cInt &= 2**c.length - 1

            if c.type == UnitControlType.DIMMER:
                scale = UnitState.DIMMER_RESOLUTION - c.length
                self._state.dimmer = cInt << scale
            elif c.type == UnitControlType.VERTICAL:
                scale = UnitState.VERTICAL_RESOLUTION - c.length
                self._state.vertical = cInt << scale
            elif c.type == UnitControlType.RGB:
                if self._isClassic:
                    self._state.rgb = UnitState.rgb_from_int(cInt, c.length)
                else:
                    self._state.hs = UnitState.hs_from_int(cInt, c.length)
            elif c.type == UnitControlType.WHITE:
                scale = UnitState.WHITE_RESOLUTION - c.length
                self._state.white = cInt << scale
            elif c.type == UnitControlType.TEMPERATURE:
                if c.max is None or c.min is None:
                    _LOGGER.warning("Can't set temperature when min or max unknown.")
                    continue
                self._state.temperature = UnitState.temperature_from_int(
                    cInt, c.min, c.max, c.length
                )
            elif c.type == UnitControlType.COLORSOURCE:
                self._state.colorsource = ColorSource(cInt)
            elif c.type == UnitControlType.XY:
                self._state.xy = UnitState.xy_from_int(cInt, c.length)
            elif c.type == UnitControlType.SLIDER:
                scale = UnitState.SLIDER_RESOLUTION - c.length
                self._state.slider = cInt << scale
            elif c.type == UnitControlType.ONOFF:
                self._state.onoff = cInt != 0
            elif c.type == UnitControlType.UNKOWN:
                # Might be useful for implementing more state types
                _LOGGER.debug(
                    f"Value for unkown control type at {c.offset}: {cInt}. Unit type is {self.unitType.id}."
                )
                self._state._unknown_controls.append((c.offset, c.length, cInt))

        _LOGGER.debug(f"Parsed {b2a(value)} to {self.state.__repr__()}")


@dataclass
class Scene:
    """A scene in a network.

    :ivar sceneId: The id of the scene in the network.
    :ivar name: The name of the scene.
    """

    sceneId: int
    name: str


@dataclass
class Group:
    """A group (collection of units) in a network.

    :ivar groupId: The id of the group in the network.
    :ivar name: The name of the group.
    :ivar units: A list of units in this group.
    """

    groudId: int
    name: str

    units: list[Unit]
