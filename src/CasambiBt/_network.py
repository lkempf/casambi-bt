import contextlib
import json
import logging
import pickle
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final, cast

import httpx
from httpx import AsyncClient, RequestError

from ._cache import Cache
from ._constants import DEVICE_NAME, isClassicNetwork
from ._keystore import KeyStore
from ._unit import Group, Scene, Unit, UnitControl, UnitControlType, UnitType
from .errors import (
    AuthenticationError,
    CloudUnavailableError,
    NetworkNotFoundError,
    NetworkOnlineUpdateNeededError,
    NetworkUpdateError,
)

SESSION_CACHE_FILE: Final = "session.pck"
TYPES_CACHE_FILE: Final = "types.pck"
NETWORK_ID_FILE: Final = "networkid"

API_BASE: Final = "https://api.casambi.com"

# Unit types are refetched after this time when the cloud is reachable. An
# expired type is still used while the cloud can't be reached.
TYPE_CACHE_DURATION: Final = timedelta(days=28)

# Login answers that reject the credentials. Every other error of the cloud
# (maintenance, rate limits, ...) says nothing about the password.
AUTH_REJECTED_STATUSES: Final = frozenset({httpx.codes.UNAUTHORIZED})


def unknownUnitType(typeId: int) -> UnitType:
    """Return a placeholder for a unit type that couldn't be fetched.

    The unit is kept in the network so it doesn't disappear for consumers, but
    it has no controls until the real type is known.
    """
    return UnitType(typeId, "Unknown", "Unknown", "", 0, [])


@dataclass()
class _NetworkSession:
    session: str
    network: str
    manager: bool
    keyID: int
    expires: datetime

    role: int = 3  # TODO: Support other role types?

    def expired(self) -> bool:
        return datetime.now(UTC) > self.expires


class Network:
    def __init__(self, uuid: str, httpClient: AsyncClient, cache: Cache) -> None:
        self._session: _NetworkSession | None = None

        self._networkName: str | None = None
        self._networkRevision: int | None = None
        self._protocolVersion: int = -1

        self._unitTypes: dict[int, tuple[UnitType | None, datetime]] = {}
        self.units: list[Unit] = []
        self.groups: list[Group] = []
        self.scenes: list[Scene] = []

        self._logger = logging.getLogger(__name__)

        self._id: str | None = None
        self._uuid = uuid
        self._httpClient = httpClient

        self._cache = cache
        self._keystore = KeyStore(self._cache)

    async def load(self) -> None:
        self._keystore = KeyStore(self._cache)
        await self._keystore.load()

        await self._loadSession()
        await self._loadTypeCache()

    async def _loadSession(self) -> None:
        self._logger.debug("Loading session...")
        async with self._cache as cachePath:
            sessionFile = cachePath / SESSION_CACHE_FILE
            if await sessionFile.exists():
                try:
                    self._session = pickle.loads(await sessionFile.read_bytes())
                    self._logger.info("Session loaded.")
                except Exception:
                    # The session is only a shortcut for the cloud login.
                    self._logger.warning(
                        "Session cache is unreadable. Dropping it.", exc_info=True
                    )
                    self._session = None
                    await sessionFile.unlink(missing_ok=True)

    async def _saveSesion(self) -> None:
        self._logger.debug("Saving session...")
        async with self._cache as cachePath:
            sessionData = pickle.dumps(self._session)
            await (cachePath / SESSION_CACHE_FILE).write_bytes(sessionData)

    async def _dropSession(self) -> None:
        self._session = None
        async with self._cache as cachePath:
            await (cachePath / SESSION_CACHE_FILE).unlink(missing_ok=True)

    async def _loadTypeCache(self) -> None:
        self._logger.debug("Loading unit type cache...")
        async with self._cache as cachePath:
            typesFile = cachePath / TYPES_CACHE_FILE
            if await typesFile.exists():
                try:
                    self._unitTypes = pickle.loads(await typesFile.read_bytes())
                    self._logger.info("Unit type cache loaded.")
                except Exception:
                    self._logger.warning(
                        "Unit type cache is unreadable. Dropping it.", exc_info=True
                    )
                    self._unitTypes = {}
                    await typesFile.unlink(missing_ok=True)

    async def _saveTypeCache(self) -> None:
        self._logger.debug("Saving type cache...")
        async with self._cache as cachePath:
            typeData = pickle.dumps(self._unitTypes)
            await (cachePath / TYPES_CACHE_FILE).write_bytes(typeData)

    async def _readCachedNetworkId(self) -> None:
        async with self._cache as cachePath:
            networkCacheFile = cachePath / NETWORK_ID_FILE
            if await networkCacheFile.exists():
                self._id = (await networkCacheFile.read_text()).strip() or None

    async def _readCachedNetwork(self) -> dict[str, Any] | None:
        if not self._id:
            return None
        async with self._cache as cachePath:
            cachedNetworkPath = cachePath / f"{self._id}.json"
            if not await cachedNetworkPath.exists():
                return None
            try:
                network = json.loads(await cachedNetworkPath.read_bytes())
                int(network["network"]["revision"])
            except (ValueError, KeyError, TypeError):
                self._logger.warning("Cached network is unreadable.", exc_info=True)
                return None
            return cast(dict[str, Any], network)

    async def hasCache(self) -> bool:
        """Return True if the network can be loaded without the cloud."""
        await self._readCachedNetworkId()
        return await self._readCachedNetwork() is not None

    async def getNetworkId(self, forceOffline: bool = False) -> None:
        self._logger.info("Getting network id...")

        await self._readCachedNetworkId()

        if forceOffline:
            if not self._id:
                raise NetworkOnlineUpdateNeededError("Network isn't cached.")
            return

        getNetworkIdUrl = f"{API_BASE}/network/uuid/{self._uuid}"
        try:
            res = await self._httpClient.get(getNetworkIdUrl)
            if res.status_code == httpx.codes.OK:
                new_id = str(res.json()["id"])
            else:
                new_id = None
        except (RequestError, ValueError, KeyError, TypeError) as err:
            if not self._id:
                raise NetworkOnlineUpdateNeededError(
                    "Casambi cloud not reachable and network isn't cached."
                ) from err
            self._logger.warning(
                "Failed to fetch network id. Continuing with cache.", exc_info=True
            )
            return

        if new_id is None:
            if self._id:
                # The id of a network never changes, the cached one is fine.
                self._logger.warning(
                    "Getting network id returned status %i. Continuing with cache.",
                    res.status_code,
                )
                return
            if res.status_code == httpx.codes.NOT_FOUND:
                raise NetworkNotFoundError(
                    "API failed to find network. Is your network configured correctly?"
                )
            raise CloudUnavailableError(
                f"Getting network id returned unexpected status {res.status_code}",
                res.status_code,
            )

        if self._id != new_id:
            self._logger.info("Network id changed from %s to %s.", self._id, new_id)
            async with self._cache as cachePath:
                await (cachePath / NETWORK_ID_FILE).write_text(new_id)
            self._id = new_id
        self._logger.info("Got network id %s.", self._id)

    def authenticated(self) -> bool:
        if not self._session:
            return False
        return not self._session.expired()

    @property
    def keyStore(self) -> KeyStore:
        return self._keystore

    @property
    def protocolVersion(self) -> int:
        return self._protocolVersion

    @property
    def revision(self) -> int | None:
        """Return the revision of the network configuration in use."""
        return self._networkRevision

    async def logIn(self, password: str, forceOffline: bool = False) -> None:
        """Log in to the cloud unless a valid session exists.

        :raises AuthenticationError: The cloud rejected the password.
        :raises CloudUnavailableError: The cloud can't be used at the moment.
        """
        await self.getNetworkId(forceOffline)

        # No need to be authenticated if we try to be offline anyway.
        if self.authenticated() or forceOffline:
            return

        self._logger.info("Logging in to network...")
        getSessionUrl = f"{API_BASE}/network/{self._id}/session"

        try:
            res = await self._httpClient.post(
                getSessionUrl, json={"password": password, "deviceName": DEVICE_NAME}
            )
        except RequestError as err:
            raise CloudUnavailableError("Casambi cloud not reachable.") from err

        if res.status_code in AUTH_REJECTED_STATUSES:
            # Never log the body: it is controlled by the cloud.
            raise AuthenticationError(
                f"Login failed: {res.status_code}", status_code=res.status_code
            )
        if res.status_code != httpx.codes.OK:
            raise CloudUnavailableError(
                f"Login failed: {res.status_code}", res.status_code
            )

        try:
            sessionJson = res.json()
            sessionJson["expires"] = datetime.fromtimestamp(
                sessionJson["expires"] / 1000, UTC
            )
            self._session = _NetworkSession(**sessionJson)
        except (ValueError, KeyError, TypeError) as err:
            raise CloudUnavailableError("Malformed login response.") from err
        self._logger.info("Login sucessful.")
        await self._saveSesion()

    async def _fetchNetwork(self, revision: int) -> dict[str, Any] | None:
        """Fetch the network configuration if the cloud has a newer revision.

        :return: The new configuration or None if the given revision is current.
        :raises AuthenticationError: The session isn't valid anymore.
        :raises CloudUnavailableError: The cloud can't be used at the moment.
        """
        if not self.authenticated():
            raise AuthenticationError("Not authenticated!")
        assert self._session is not None

        getNetworkUrl = f"{API_BASE}/network/{self._id}/"
        try:
            # **SECURITY**: Do not set session header for client! This could leak the session with external clients.
            res = await self._httpClient.put(
                getNetworkUrl,
                json={
                    "formatVersion": 1,
                    "deviceName": DEVICE_NAME,
                    "revision": revision,
                },
                headers={"X-Casambi-Session": self._session.session},
            )
        except RequestError as err:
            raise CloudUnavailableError("Casambi cloud not reachable.") from err

        if res.status_code == httpx.codes.GONE:
            # Apparently this happens when the password changes. Only the
            # session is invalid: keep the network and its keys so the
            # network keeps working offline until the user logs in again.
            self._logger.error("API reports that the session is gone.")
            await self._dropSession()
            raise AuthenticationError(
                "Session is no longer valid.", status_code=res.status_code
            )
        if res.status_code != httpx.codes.OK:
            raise CloudUnavailableError(
                f"Update failed: {res.status_code}", res.status_code
            )

        try:
            updateResult = cast(dict[str, Any], res.json())
            if updateResult["status"] == "UPTODATE":
                return None
            int(updateResult["network"]["revision"])
        except (ValueError, KeyError, TypeError) as err:
            raise CloudUnavailableError("Malformed network response.") from err

        async with self._cache as cachePath:
            await (cachePath / f"{self._id}.json").write_bytes(res.content)
        return updateResult

    async def update(self, forceOffline: bool = False) -> None:
        """Load the network configuration, from the cloud if possible.

        Cloud errors fall back to the cached configuration.

        :raises AuthenticationError: Not logged in or the session was revoked.
        :raises NetworkOnlineUpdateNeededError: The network isn't cached and
            the cloud can't be used.
        :raises NetworkUpdateError: The configuration is malformed.
        """
        self._logger.info("Updating network...")
        if not self.authenticated() and not forceOffline:
            raise AuthenticationError("Not authenticated!")

        assert self._id is not None, "Network id must be set."

        network = await self._readCachedNetwork()
        if network is not None:
            self._networkRevision = int(network["network"]["revision"])
            self._logger.info(
                "Loaded cached network. Revision: %i", self._networkRevision
            )
        elif forceOffline:
            raise NetworkOnlineUpdateNeededError("Network isn't cached.")
        else:
            self._networkRevision = 0

        if not forceOffline:
            try:
                fresh = await self._fetchNetwork(self._networkRevision or 0)
            except CloudUnavailableError as err:
                if network is None:
                    raise NetworkOnlineUpdateNeededError(
                        "Network isn't cached and the cloud can't be used."
                    ) from err
                self._logger.warning(
                    "Failed to update network (%s). Continuing offline.", err
                )
            else:
                if fresh is not None:
                    network = fresh
                    self._logger.info(
                        "Fetched updated network with revision %s",
                        fresh["network"]["revision"],
                    )

        assert network is not None
        await self._parseNetwork(network, forceOffline)
        self._logger.info("Network updated.")

    async def fetchUpdate(self) -> bool:
        """Download a newer network configuration into the cache.

        The configuration in use (units, groups, scenes) is left untouched so
        that live objects stay valid; it is applied by the next connect. The
        unit types of the new configuration are fetched as well so it can be
        used offline later.

        :return: True if the cloud had a newer configuration.
        :raises AuthenticationError: Not logged in or the session was revoked.
        :raises CloudUnavailableError: The cloud can't be used at the moment.
        """
        fresh = await self._fetchNetwork(self._networkRevision or 0)
        if fresh is None:
            return False
        for u in fresh["network"].get("units", []):
            with contextlib.suppress(KeyError, TypeError, ValueError):
                await self._fetchUnitInfo(int(u["type"]))
        await self._saveTypeCache()
        return True

    async def _parseNetwork(self, network: dict[str, Any], forceOffline: bool) -> None:
        try:
            netJson = network["network"]
            revision = int(netJson["revision"])
            networkName = str(netJson["name"])
            protocolVersion = int(netJson["protocolVersion"])

            # Keys of the network. Classic networks use legacy keys instead.
            await self._keystore.replaceKeys(
                netJson.get("keyStore", {}).get("keys", []),
                netJson.get("visitorKey"),
                netJson.get("managerKey"),
            )

            units: list[Unit] = []
            for u in netJson["units"]:
                typeId = int(u["type"])
                uType = await self._fetchUnitInfo(typeId, forceOffline)
                if uType is None:
                    self._logger.warning(
                        "Type %i of unit %s is unknown. Keeping the unit without controls.",
                        typeId,
                        u["deviceID"],
                    )
                    uType = unknownUnitType(typeId)
                units.append(
                    Unit(
                        typeId,
                        int(u["deviceID"]),
                        str(u["uuid"]),
                        str(u["address"]),
                        str(u["name"]),
                        str(u["firmware"]),
                        uType,
                        _isClassic=isClassicNetwork(protocolVersion),
                    )
                )

            groups: list[Group] = []
            for c in netJson["grid"]["cells"]:
                # Only one type at top level is currently supported
                if c["type"] != 2:
                    continue

                # Parse group members, we assume no nested groups here
                group_units = []
                for subC in c["cells"]:
                    # Ignore everyting that isn't a unit
                    if subC["type"] != 1:
                        continue

                    unitMatch = [u for u in units if u.deviceId == subC["unit"]]
                    if len(unitMatch) != 1:
                        self._logger.warning(
                            "Inconsistent unit reference to %s in group %s. Got %i matches.",
                            subC["unit"],
                            c["groupID"],
                            len(unitMatch),
                        )
                        continue
                    group_units.append(unitMatch[0])

                groups.append(Group(int(c["groupID"]), str(c["name"]), group_units))

            scenes = [
                Scene(int(s["sceneID"]), str(s["name"])) for s in netJson["scenes"]
            ]
        except (KeyError, TypeError, ValueError) as err:
            raise NetworkUpdateError("Malformed network configuration.") from err

        self._networkRevision = revision
        self._networkName = networkName
        self._protocolVersion = protocolVersion
        self.units = units
        self.groups = groups
        self.scenes = scenes

        await self._saveTypeCache()

    async def _fetchUnitInfo(
        self, id: int, forceOffline: bool = False
    ) -> UnitType | None:
        """Return the type of a unit.

        A cached type is used until it expires. An expired type is refetched
        but kept if the cloud can't be used, so the network keeps working
        offline. Failures are not cached so the next connect tries again.
        """
        cachedType: UnitType | None = None
        if id in self._unitTypes:
            cachedType, cacheExpiry = self._unitTypes[id]
            if cachedType is not None and cacheExpiry >= datetime.now(UTC):
                return cachedType

        if forceOffline:
            return cachedType

        self._logger.info("Fetching unit type for id %i...", id)
        getUnitInfoUrl = f"{API_BASE}/fixture/{id}"
        try:
            res = await self._httpClient.get(getUnitInfoUrl)
            if res.status_code != httpx.codes.OK:
                self._logger.warning(
                    "Getting unit info for %i returned %i.", id, res.status_code
                )
                return cachedType
            unitTypeObj = _parseUnitType(res.json())
        except (RequestError, ValueError, KeyError, TypeError):
            self._logger.warning("Failed to fetch unit info for %i.", id, exc_info=True)
            return cachedType

        self._unitTypes[unitTypeObj.id] = (
            unitTypeObj,
            datetime.now(UTC) + TYPE_CACHE_DURATION,
        )
        self._logger.info("Sucessfully fetched unit type.")
        return unitTypeObj

    def unitTypes(self) -> dict[int, UnitType]:
        """Return the known unit types."""
        return {k: v for k, (v, _) in self._unitTypes.items() if v is not None}

    async def storeUnitTypes(self, types: list[UnitType]) -> None:
        """Store unit types in the cache, e.g. from an offline backup."""
        for t in types:
            self._unitTypes[t.id] = (t, datetime.now(UTC) + TYPE_CACHE_DURATION)
        await self._saveTypeCache()

    async def disconnect(self) -> None:
        return None


def _parseUnitType(unitTypeJson: dict[str, Any]) -> UnitType:
    logger = logging.getLogger(__name__)
    controls = []
    for controlJson in unitTypeJson["controls"]:
        typeStr = str(controlJson["type"]).upper()
        try:
            type = UnitControlType[typeStr]
        except KeyError:
            logger.warning(
                "Unsupported control mode %s in fixture %s.",
                typeStr,
                unitTypeJson.get("id"),
            )
            type = UnitControlType.UNIMPLEMENTED

        controls.append(
            UnitControl(
                type,
                int(controlJson["offset"]),
                int(controlJson["length"]),
                int(controlJson["default"]),
                bool(controlJson["readonly"]),
                controlJson.get("min", None),
                controlJson.get("max", None),
            )
        )

    return UnitType(
        int(unitTypeJson["id"]),
        str(unitTypeJson["model"]),
        str(unitTypeJson["vendor"]),
        str(unitTypeJson["mode"]),
        int(unitTypeJson["stateLength"]),
        controls,
    )
