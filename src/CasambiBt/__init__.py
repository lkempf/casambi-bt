"""Top-level module for CasambiBt."""

from ._backup import BACKUP_FORMAT, BACKUP_VERSION
from ._cache import CACHE_VERSION
from ._casambi import Casambi
from ._constants import normalizeAddress
from ._discover import discover
from ._switch import ButtonEventType, SwitchEvent
from ._unit import (
    ColorSource,
    Group,
    Scene,
    Unit,
    UnitControl,
    UnitControlType,
    UnitState,
    UnitType,
)
from .errors import (
    AuthenticationError,
    BluetoothDeviceNotFoundError,
    BluetoothError,
    CasambiBtError,
    CloudUnavailableError,
    ConnectionStateError,
    NetworkNotFoundError,
    NetworkOnlineUpdateNeededError,
    NetworkUpdateError,
    OfflineBackupError,
    ProtocolError,
    UnsupportedProtocolVersion,
)

__all__ = [
    "BACKUP_FORMAT",
    "BACKUP_VERSION",
    "CACHE_VERSION",
    "AuthenticationError",
    "BluetoothDeviceNotFoundError",
    "BluetoothError",
    "ButtonEventType",
    "Casambi",
    "CasambiBtError",
    "CloudUnavailableError",
    "ColorSource",
    "ConnectionStateError",
    "Group",
    "NetworkNotFoundError",
    "NetworkOnlineUpdateNeededError",
    "NetworkUpdateError",
    "OfflineBackupError",
    "ProtocolError",
    "Scene",
    "SwitchEvent",
    "Unit",
    "UnitControl",
    "UnitControlType",
    "UnitState",
    "UnitType",
    "UnsupportedProtocolVersion",
    "discover",
    "normalizeAddress",
]
