import json
import logging
import pickle
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Optional, cast

import httpx
from httpx import AsyncClient, RequestError

from ._cache import Cache
from ._constants import DEVICE_NAME
from ._keystore import KeyStore
from ._unit import Group, Scene, Unit, UnitControl, UnitControlType, UnitType
from .errors import (
    AuthenticationError,
    NetworkNotFoundError,
    NetworkOnlineUpdateNeededError,
    NetworkUpdateError,
)

SESSION_CACHE_FILE: Final = "session.pck"
TYPES_CACHE_FILE: Final = "types.pck"


@dataclass()
class _NetworkSession:
    session: str
    network: str
    manager: bool
    keyID: int
    expires: datetime

    role: int = 3  # TODO: Support other role types?

    def expired(self) -> bool:
        return datetime.utcnow() > self.expires


class Network:
    def __init__(self, uuid: str, httpClient: AsyncClient, cache: Cache) -> None:
        self._session: Optional[_NetworkSession] = None

        self._networkName: Optional[str] = None
        self._networkRevision: Optional[int] = None

        self._unitTypes: dict[int, tuple[Optional[UnitType], datetime]] = {}
        self.units: list[Unit] = []
        self.groups: list[Group] = []
        self.scenes: list[Scene] = []

        self._logger = logging.getLogger(__name__)
        # TODO: Create LoggingAdapter to prepend uuid.

        self._id: Optional[str] = None
        self._uuid = uuid
        self._httpClient = httpClient

        self._cache = cache
        self._keystore = KeyStore(self._cache)

        self._loadSession()
        self._loadTypeCache()

    def _loadSession(self) -> None:
        self._logger.debug("Loading session...")
        with self._cache as cachePath:
            if (cachePath / SESSION_CACHE_FILE).exists():
                self._session = pickle.load((cachePath / SESSION_CACHE_FILE).open("rb"))
                self._logger.info("Session loaded.")

    def _saveSesion(self) -> None:
        self._logger.debug("Saving session...")
        with self._cache as cachePath:
            pickle.dump(self._session, (cachePath / SESSION_CACHE_FILE).open("wb"))

    def _loadTypeCache(self) -> None:
        self._logger.debug("Loading unit type cache...")
        with self._cache as cachePath:
            if (cachePath / TYPES_CACHE_FILE).exists():
                self._unitTypes = pickle.load((cachePath / TYPES_CACHE_FILE).open("rb"))
                self._logger.info("Unit type cache loaded.")

    def _saveTypeCache(self) -> None:
        self._logger.debug("Saving type cache...")
        with self._cache as cachePath:
            pickle.dump(self._unitTypes, (cachePath / TYPES_CACHE_FILE).open("wb"))

    async def getNetworkId(self, forceOffline: bool = False) -> None:
        self._logger.info("Getting network id...")

        with self._cache as cachePath:
            networkCacheFile = cachePath / "networkid"

            if networkCacheFile.exists():
                self._id = networkCacheFile.read_text()

        if forceOffline:
            if not self._id:
                raise NetworkOnlineUpdateNeededError("Network isn't cached.")
            else:
                return

        getNetworkIdUrl = f"https://api.casambi.com/network/uuid/{self._uuid}"
        try:
            res = await self._httpClient.get(getNetworkIdUrl)
        except RequestError as err:
            if not self._id:
                raise NetworkOnlineUpdateNeededError from err
            else:
                self._logger.warning(
                    "Network error while fetching network id. Continuing with cache.",
                    exc_info=True,
                )
                return

        if res.status_code == httpx.codes.NOT_FOUND:
            raise NetworkNotFoundError(
                "API failed to find network. Is your network configured correctly?"
            )
        if res.status_code != httpx.codes.OK:
            raise NetworkNotFoundError(
                f"Getting network id returned unexpected status {res.status_code}"
            )

        new_id = cast(str, res.json()["id"])
        if self._id != new_id:
            self._logger.info(f"Network id changed from {self._id} to {new_id}.")
            with self._cache as cachePath:
                networkCacheFile = cachePath / "networkid"
                networkCacheFile.write_text(new_id)
            self._id = new_id
        self._logger.info(f"Got network id {self._id}.")

    def authenticated(self) -> bool:
        if not self._session:
            return False
        return not self._session.expired()

    def getKeyStore(self) -> KeyStore:
        return self._keystore

    async def logIn(self, password: str, forceOffline: bool = False) -> None:
        await self.getNetworkId(forceOffline)

        # No need to be authenticated if we try to be offline anyway.
        if self.authenticated() or forceOffline:
            return

        self._logger.info("Logging in to network...")
        getSessionUrl = f"https://api.casambi.com/network/{self._id}/session"

        res = await self._httpClient.post(
            getSessionUrl, json={"password": password, "deviceName": DEVICE_NAME}
        )
        if res.status_code == httpx.codes.OK:
            # Parse session
            sessionJson = res.json()
            sessionJson["expires"] = datetime.utcfromtimestamp(
                sessionJson["expires"] / 1000
            )
            self._session = _NetworkSession(**sessionJson)
            self._logger.info("Login sucessful.")
            self._saveSesion()
        else:
            raise AuthenticationError(f"Login failed: {res.status_code}\n{res.text}")

    async def update(self, forceOffline: bool = False) -> None:
        self._logger.info("Updating network...")
        if not self.authenticated() and not forceOffline:
            raise AuthenticationError("Not authenticated!")

        assert self._id is not None, "Network id must be set."

        # TODO: Save and send revision to receive actual updates?

        with self._cache as cachePath:
            cachedNetworkPah = cachePath / f"{self._id}.json"
            if cachedNetworkPah.exists():
                network = json.loads(cachedNetworkPah.read_bytes())
                self._networkRevision = network["network"]["revision"]
                self._logger.info(
                    f"Loaded cached network. Revision: {self._networkRevision}"
                )
            else:
                if forceOffline:
                    raise NetworkOnlineUpdateNeededError("Network isn't cached.")
                self._networkRevision = 0

        if not forceOffline:
            getNetworkUrl = f"https://api.casambi.com/network/{self._id}/"

            try:
                # **SECURITY**: Do not set session header for client! This could leak the session with external clients.
                res = await self._httpClient.put(
                    getNetworkUrl,
                    json={
                        "formatVersion": 1,
                        "deviceName": DEVICE_NAME,
                        "revision": self._networkRevision,
                    },
                    headers={"X-Casambi-Session": self._session.session},  # type: ignore[union-attr]
                )

                # Apparently this happens when the password changes.
                # In this case we should at least invalidate the session.
                # Currently we invalidate the whole cache for the network since recreating it doesn't cost much.
                if res.status_code == httpx.codes.GONE:
                    self._logger.error(
                        "API reports that network is gone. Deleting cache. Retry later."
                    )
                    self._cache.invalidateCache()

                if res.status_code != httpx.codes.OK:
                    self._logger.error(f"Update failed: {res.status_code}\n{res.text}")
                    raise NetworkUpdateError("Could not update network!")

                self._logger.debug(f"Network: {res.text}")

                updateResult = res.json()
                if updateResult["status"] != "UPTODATE":
                    self._networkRevision = updateResult["network"]["revision"]
                    with self._cache as cachePath:
                        cachedNetworkPah = cachePath / f"{self._id}.json"
                        cachedNetworkPah.write_bytes(res.content)
                    network = updateResult
                    self._logger.info(
                        f"Fetched updated network with revision {self._networkRevision}"
                    )
            except RequestError as err:
                if self._networkRevision == 0:
                    raise NetworkUpdateError from err
                self._logger.warning(
                    "Failed to update network. Continuing offline.", exc_info=True
                )

        # Prase general information
        self._networkName = network["network"]["name"]

        # Parse keys if there are any. Otherwise the network is probably a classic network.
        if "keyStore" in network["network"]:
            keys = network["network"]["keyStore"]["keys"]
            for k in keys:
                self._keystore.addKey(k)

        # TODO: Parse managerKey and visitorKey for classic networks.

        # Parse units
        self.units = []
        units = network["network"]["units"]
        for u in units:
            uType = await self._fetchUnitInfo(u["type"])
            if uType is None:
                self._logger.info(
                    "Failed to fetch type for unit %i. Skipping.", u["type"]
                )
                continue
            uObj = Unit(
                u["type"],
                u["deviceID"],
                u["uuid"],
                u["address"],
                u["name"],
                str(u["firmware"]),
                uType,
            )
            self.units.append(uObj)

        # Parse cells
        self.groups = []
        cells = network["network"]["grid"]["cells"]
        for c in cells:
            # Only one type at top level is currently supported
            if c["type"] != 2:
                continue

            # Parse group members
            group_units = []
            # We assume no nested groups here
            for subC in c["cells"]:
                # Ignore everyting that isn't a unit
                if subC["type"] != 1:
                    continue

                unitMatch = list(
                    filter(lambda u: u.deviceId == subC["unit"], self.units)
                )
                if len(unitMatch) != 1:
                    self._logger.warning(
                        f"Incositent unit reference to {subC['unit']} in group {c['groupID']}. Got {len(unitMatch)} matches."
                    )
                    continue
                group_units.append(unitMatch[0])

            gObj = Group(c["groupID"], c["name"], group_units)
            self.groups.append(gObj)

        # Parse scenes
        self.scenes = []
        scenes = network["network"]["scenes"]
        for s in scenes:
            sObj = Scene(s["sceneID"], s["name"])
            self.scenes.append(sObj)

        # TODO: Parse more stuff

        self._saveTypeCache()

        self._logger.info("Network updated.")

    async def _fetchUnitInfo(self, id: int) -> Optional[UnitType]:
        self._logger.info(f"Fetching unit type for id {id}...")

        # Check whether unit type is already cached
        if id in self._unitTypes:
            cachedType, cacheExpiry = self._unitTypes[id]

            # We don't want to cache types forever so use an expiry date.
            if cacheExpiry < datetime.utcnow():
                self._logger.info("Cache expiry for type %i. Refetching.", id)
                self._unitTypes.pop(id)
            else:
                self._logger.info("Using cached type.")
                return cachedType

        getUnitInfoUrl = f"https://api.casambi.com/fixture/{id}"
        async with AsyncClient() as request:
            res = await request.get(getUnitInfoUrl)

        if res.status_code != httpx.codes.OK:
            self._logger.error(f"Getting unit info returned {res.status_code}")
            self._unitTypes[id] = (
                None,
                datetime.utcnow() + timedelta(days=7),
            )
            return None

        unitTypeJson = res.json()

        # Parse UnitControls
        controls = []
        for controlJson in unitTypeJson["controls"]:
            typeStr = controlJson["type"].upper()
            try:
                type = UnitControlType[typeStr]
            except KeyError:
                self._logger.warning(
                    f"Unsupported control mode {typeStr} in fixture {id}."
                )
                type = UnitControlType.UNKOWN

            controlObj = UnitControl(
                type,
                controlJson["offset"],
                controlJson["length"],
                controlJson["default"],
                controlJson["readonly"],
                controlJson.get("min", None),
                controlJson.get("max", None),
            )

            controls.append(controlObj)

        # Parse UnitType
        unitTypeObj = UnitType(
            unitTypeJson["id"],
            unitTypeJson["model"],
            unitTypeJson["vendor"],
            unitTypeJson["mode"],
            unitTypeJson["stateLength"],
            controls,
        )

        # Chache unit type
        self._unitTypes[unitTypeObj.id] = (
            unitTypeObj,
            datetime.utcnow() + timedelta(days=28),
        )

        self._logger.info("Sucessfully fetched unit type.")
        return unitTypeObj

    async def disconnect(self) -> None:
        return None
