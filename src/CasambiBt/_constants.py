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
