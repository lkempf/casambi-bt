from enum import IntEnum, unique
from typing import Final

DEVICE_NAME: Final = "Casambi BT Python"

CASA_UUID: Final = "0000fe4d-0000-1000-8000-00805f9b34fb"
CASA_AUTH_CHAR_UUID: Final = "c9ffde48-ca5a-0001-ab83-8f519b482f77"


@unique
class ConnectionState(IntEnum):
    NONE = 0
    CONNECTED = 1
    KEY_EXCHANGED = 2
    AUTHENTICATED = 3
    ERROR = 99


@unique
class IncomingPacketType(IntEnum):
    UnitState = 6
    SwitchEvent = 7
    NetworkConfig = 9


MIN_EVO_VERSION: Final[int] = 10
MAX_EVO_VERSION: Final[int] = 11
FIRST_EVO_VERSION: Final[int] = 10
MIN_SUPPORTED_CLASSIC_VERSION: Final[int] = 5


def isClassicNetwork(version: int) -> bool:
    return version < FIRST_EVO_VERSION


CLASSIC_AUTH_LEVEL_MANAGER: Final = 3
CLASSIC_AUTH_LEVEL_VISITOR: Final = 2


def normalizeAddress(address: str) -> str:
    """Return a mac address in the colon separated, upper case notation.

    Accepts addresses with or without colons or dashes.

    :raises ValueError: The address isn't a mac address.
    """
    digits = address.replace(":", "").replace("-", "").strip().upper()
    if len(digits) != 12 or any(c not in "0123456789ABCDEF" for c in digits):
        raise ValueError(f"Invalid mac address {address!r}.")
    return ":".join(digits[i : i + 2] for i in range(0, 12, 2))
