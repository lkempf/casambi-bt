import logging
from binascii import b2a_hex as b2a
from colorsys import hsv_to_rgb, rgb_to_hsv
from dataclasses import dataclass
from enum import Enum, unique
from typing import Final, List, Optional, Tuple

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

    UNKOWN = 99
    """State isn't implemented. Control saved for debuggin purposes."""


@dataclass(frozen=True, repr=True)
class UnitControl:
    type: UnitControlType
    offset: int
    length: int
    default: int
    readonly: bool


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
    controls: List[UnitControl]

    def get_control(self, controlType: UnitControlType) -> Optional[UnitControl]:
        """Return the control description if the unit type supports the given type of control.

        :param controlType: The desired control type.
        :return: A control description for the given control type if available, otherwise `None`
        """
        for c in self.controls:
            if c.type == controlType:
                return c


# TODO: Support for different resolutions?
# TODO: Work with HS instead of RGB internally
class UnitState:
    """Parsed representation of the state of a unit."""

    _dimmer: Optional[int] = None
    _rgb: Optional[Tuple[int, int, int]] = None
    _white: Optional[int] = None

    def _check_range(self, value: int, min: int, max: int) -> None:
        if value < min or value > max:
            raise ValueError(f"{value} is not between {min} and {max}")

    @property
    def dimmer(self) -> Optional[int]:
        return self._dimmer

    DIMMER_RESOLUTION: Final = 8
    DIMMER_MIN: Final = 0
    DIMMER_MAX: Final = 2**DIMMER_RESOLUTION - 1

    @dimmer.setter
    def dimmer(self, value: int) -> None:
        self._check_range(value, self.DIMMER_MIN, self.DIMMER_MAX)
        self._dimmer = value

    @dimmer.deleter
    def dimmer(self) -> None:
        self._dimmer = None

    @property
    def rgb(self) -> Optional[Tuple[int, int, int]]:
        return self._rgb

    RGB_RESOLUTION: Final = 8
    RGB_MIN: Final = 0
    RGB_MAX: Final = 2**RGB_RESOLUTION - 1

    @rgb.setter
    def rgb(self, value: Tuple[int, int, int]) -> None:
        r, g, b = value
        self._check_range(r, self.RGB_MIN, self.RGB_MAX)
        self._check_range(g, self.RGB_MIN, self.RGB_MAX)
        self._check_range(b, self.RGB_MIN, self.RGB_MAX)

        self._rgb = (r, g, b)

    @rgb.deleter
    def rgb(self) -> None:
        self._rgb = None

    @property
    def hs(self) -> Optional[Tuple[float, float]]:
        """Convert RGB into HS where H is a float in [0..1[ and S a float in [0..1]"""
        if self._rgb is None:
            return None

        rgb_float = [c / (2**self.RGB_RESOLUTION - 1) for c in self._rgb]
        h, s, _ = rgb_to_hsv(*rgb_float)

        h %= 1
        if h == 0 and s == 0:
            h = 0.5

        return (h, s)

    @hs.setter
    def hs(self, value: Tuple[float, float]) -> None:
        """Convert HS color to interal RBG representation where H is a float in [0..1[ and S a float in [0..1]"""
        h, s = value

        rgb = hsv_to_rgb(h, s, 1)
        self.rgb = [round(c * (2**self.RGB_RESOLUTION - 1)) for c in rgb]

    @property
    def white(self) -> Optional[int]:
        return self._white

    WHITE_RESOLUTION = 8
    WHITE_MIN = 0
    WHITE_MAX = 2**WHITE_RESOLUTION - 1

    @white.setter
    def white(self, value: int) -> None:
        self._check_range(value, self.WHITE_MIN, self.WHITE_MAX)
        self._white = value

    @white.deleter
    def white(self) -> None:
        self._white = None

    def __repr__(self) -> str:
        return f"UnitState(dimmer={self.dimmer}, rgb={self.rgb.__repr__()}, white={self.white})"


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

    _state: Optional[UnitState] = None
    _on: bool = False
    _online: bool = False

    @property
    def state(self) -> Optional[UnitState]:
        """Get the state of the unit if it has been set."""
        return self._state

    @property
    def is_on(self) -> bool:
        """Determine whether the unit is turned on."""
        if self.unitType.get_control(UnitControlType.DIMMER):
            return self._on and self._state.dimmer > 0
        else:
            return self._on

    @property
    def online(self) -> bool:
        return self._online

    def getStateAsBytes(self, state: UnitState) -> bytes:
        """Given a generic UnitState convert it into the internal state representation.

        Unsupported state information will be ignored.
        """

        # offset, lenth, value
        values: List[Tuple[int, int, int]] = []

        # TODO: Support for resolutions >8 byte?
        # Parse and convert state
        for c in self.unitType.controls:
            scaledValue = None
            if c.type == UnitControlType.DIMMER and state.dimmer is not None:
                scale = UnitState.DIMMER_RESOLUTION - c.length
                scaledValue = state.dimmer >> scale
            elif c.type == UnitControlType.RGB and state.rgb is not None:
                hueLen = (c.length * 10) // 18
                hueMask = 2**hueLen - 1
                satLen = c.length - hueLen
                satMask = 2**satLen - 1

                h, s = state.hs

                scaledValue = ((round(h * hueMask) & hueMask) << satLen) + (
                    round(s * satMask) & satMask
                )

                # Old RGB code (might still be useful for earlier protocol versions):
                """
                assert c.length % 3 == 0, "Invalid RGB length"
                scale = UnitState.RGB_RESOLUTION - (c.length // 3)
                scaledValue = 0
                value = state.rgb
                for i in range(3):
                    scaledValue += (value[i] >> scale) * 2 ** (
                        (c.length // 3) * (2 - i)
                    )
                """
            elif c.type == UnitControlType.WHITE and state.white is not None:
                scale = UnitState.WHITE_RESOLUTION - c.length
                scaledValue = state.white >> scale

            # Use default if unsupported type or unset value in state
            else:
                scaledValue = c.default

            values.append((c.offset, c.length, scaledValue))

        # Pack state into bytes
        res = bytearray(self.unitType.stateLength)
        for off, len, val in values:
            byteLen = (len - 1) // 8 + 1
            valBytes = val.to_bytes(byteLen, byteorder="little", signed=False)
            for i in range(byteLen):
                if off % 8 == 0:
                    res[off // 8] |= valBytes[i]
                    off += 8
                else:
                    res[off // 8] |= valBytes[i] << (off % 8)
                    off += off % 8

        _LOGGER.debug(f"Packing {values.__repr__()} as {res}")
        return bytes(res)

    def setStateFromBytes(self, value: bytes) -> None:
        """Parse state bytes into a `UnitState` and set it for the current unit.

        :param value: State bytes for the unit.
        """
        if not self._state:
            self._state = UnitState()

        # TODO: Support for resolutions >8 byte?
        for c in self.unitType.controls:
            # Extract all relevant bytes from the state
            byteLen = (c.length - 1) // 8 + 1
            cBytes = value[c.offset // 8 : c.offset // 8 + byteLen]

            # Extract c.Length bits form the byte string
            cInt = int.from_bytes(cBytes, byteorder="little", signed=False)
            cInt >>= c.offset % 8
            cInt &= 2**c.length - 1

            if c.type == UnitControlType.DIMMER:
                scale = UnitState.DIMMER_RESOLUTION - c.length
                self._state.dimmer = cInt << scale
            elif c.type == UnitControlType.RGB:
                hueLen = (c.length * 10) // 18
                hueMask = 2**hueLen - 1
                satLen = c.length - hueLen
                satMask = 2**satLen - 1

                h = (cInt >> satLen) / hueMask
                s = (cInt & satMask) / satMask

                self.state.hs = (h, s)
                # Old RGB Code (might still be useful for earlier protocol versions):
                """
                assert c.length % 3 == 0, "Invalid RGB length"
                compLen = c.length // 3
                rgb = []
                scale = UnitState.RGB_RESOLUTION - compLen

                # Extract components from int and scale them
                for i in range(3):
                    v = (cInt >> ((2 - i) * compLen)) & (2 ** compLen - 1)
                    v <<= scale
                    rgb.append(v)
                self._state.rgb = tuple(rgb)
                """
            elif c.type == UnitControlType.WHITE:
                scale = UnitState.WHITE_RESOLUTION - c.length
                self._state.white = cInt << scale
            elif c.type == UnitControlType.UNKOWN:
                # Might be useful for implementing more state types
                _LOGGER.debug(f"Value for unkown control type at {c.offset}: {cInt}")

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

    units: List[Unit]
