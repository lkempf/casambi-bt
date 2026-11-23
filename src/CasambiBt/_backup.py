"""Offline backups of a network.

A backup holds everything needed to connect to a network without the
Casambi cloud: the network configuration as delivered by the cloud
(including the keys of the network) and the types of its units. Restoring it
fills the cache so that a connect works offline.

The backup contains the keys of the network. Treat it like a password.
"""

import json
import logging
from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

from ._cache import Cache
from ._constants import normalizeAddress
from ._unit import UnitControl, UnitControlType, UnitType
from .errors import OfflineBackupError

if TYPE_CHECKING:
    from ._network import Network

_LOGGER = logging.getLogger(__name__)

BACKUP_FORMAT: Final = "casambi-bt-offline-backup"
BACKUP_VERSION: Final = 1


def _serializeUnitType(unitType: UnitType) -> dict[str, Any]:
    data = asdict(unitType)
    data["controls"] = [{**asdict(c), "type": c.type.name} for c in unitType.controls]
    return data


def _deserializeUnitType(data: Mapping[str, Any]) -> UnitType:
    controls = [
        UnitControl(
            UnitControlType[str(c["type"])],
            int(c["offset"]),
            int(c["length"]),
            int(c["default"]),
            bool(c["readonly"]),
            None if c.get("min") is None else int(c["min"]),
            None if c.get("max") is None else int(c["max"]),
        )
        for c in data["controls"]
    ]
    return UnitType(
        int(data["id"]),
        str(data["model"]),
        str(data["manufacturer"]),
        str(data["mode"]),
        int(data["stateLength"]),
        controls,
    )


async def createBackup(network: "Network") -> dict[str, Any]:
    """Create an offline backup of a loaded network."""
    configuration = await network._readCachedNetwork()  # noqa: SLF001
    if configuration is None:
        raise OfflineBackupError("The network configuration isn't cached.")

    knownTypes = network.unitTypes()
    usedTypes = {u.unitType.id for u in network.units}
    missing = sorted(t for t in usedTypes if t not in knownTypes)
    if missing:
        _LOGGER.warning("The backup lacks the unknown unit types %s.", missing)

    return {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "created": datetime.now(UTC).isoformat(),
        "address": normalizeAddress(network._uuid),  # noqa: SLF001
        "networkId": network._id,  # noqa: SLF001
        "network": configuration,
        "unitTypes": [
            _serializeUnitType(knownTypes[t]) for t in sorted(usedTypes - set(missing))
        ],
    }


def parseBackup(
    backup: Mapping[str, Any],
) -> tuple[str, str, dict[str, Any], list[UnitType]]:
    """Validate a backup and return its address, network id, configuration and types.

    :raises OfflineBackupError: The backup is invalid.
    """
    if not isinstance(backup, Mapping):
        raise OfflineBackupError("The backup isn't an object.")
    if backup.get("format") != BACKUP_FORMAT:
        raise OfflineBackupError("This isn't a casambi-bt offline backup.")
    if backup.get("version") != BACKUP_VERSION:
        raise OfflineBackupError(
            f"Unsupported backup version {backup.get('version')!r}."
        )
    try:
        address = normalizeAddress(str(backup["address"]))
        networkId = str(backup["networkId"])
        if not networkId or "/" in networkId or networkId.startswith("."):
            raise ValueError("Invalid network id.")
        configuration = dict(backup["network"])
        netJson = configuration["network"]
        int(netJson["revision"])
        str(netJson["name"])
        int(netJson["protocolVersion"])
        list(netJson["units"])
        unitTypes = [_deserializeUnitType(t) for t in backup["unitTypes"]]
    except (KeyError, TypeError, ValueError) as err:
        raise OfflineBackupError("The backup is incomplete or malformed.") from err
    return address, networkId, configuration, unitTypes


async def restoreBackup(cache: Cache, backup: Mapping[str, Any]) -> str:
    """Write a backup into the cache and return the address of the network.

    The cached session is dropped: it belongs to the password of the
    network at the time of the old cache, not to the backup.

    :raises OfflineBackupError: The backup is invalid.
    """
    # Late import to avoid a cycle with the network module.
    from ._network import NETWORK_ID_FILE, SESSION_CACHE_FILE, Network

    address, networkId, configuration, unitTypes = parseBackup(backup)
    uuid = address.replace(":", "").lower()

    restoreCache = Cache(cache._cachePath)  # noqa: SLF001
    await restoreCache.setUuid(uuid)
    async with restoreCache as cachePath:
        await (cachePath / NETWORK_ID_FILE).write_text(networkId)
        await (cachePath / f"{networkId}.json").write_text(json.dumps(configuration))
        await (cachePath / SESSION_CACHE_FILE).unlink(missing_ok=True)

    # Merge the types into the type cache of the network.
    network = Network(uuid, None, restoreCache)  # type: ignore[arg-type]
    await network.load()
    await network.storeUnitTypes(unitTypes)

    _LOGGER.info(
        "Restored offline backup of network %s with %i unit types.",
        address,
        len(unitTypes),
    )
    return address
