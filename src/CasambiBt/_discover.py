import logging
from typing import Awaitable, List

from bleak import BleakScanner
from bleak.backends.client import BLEDevice
from bleak.exc import BleakDBusError, BleakError

from ._constants import CASA_UUID
from .errors import BluetoothError

_LOGGER = logging.getLogger(__name__)


async def discover() -> Awaitable[List[BLEDevice]]:
    """Discover all Casambi networks in range.

    :return: A list of all discovered Casambi devices.
    :raises BluetoothError: Bluetooth isn't turned on or in a failed state.
    """

    # Discover all devices in range
    try:
        devices = await BleakScanner.discover()
    except BleakDBusError as e:
        raise BluetoothError(e.dbus_error, e.dbus_error_details) from e
    except BleakError as e:
        raise BluetoothError from e

    # Filter out all devices that aren't primary communication endpoints for casambi networks
    discovered = []
    for d in devices:
        if "manufacturer_data" in d.metadata and 963 in d.metadata["manufacturer_data"]:
            if CASA_UUID in d.metadata["uuids"]:
                _LOGGER.debug(f"Discovered networt at {d.address}")
                discovered.append(d)

    return discovered
