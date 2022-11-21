import logging
import pickle
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from re import sub
from typing import Awaitable, Dict, List, Optional

import httpx
from httpx import AsyncClient

from ._constants import BASE_PATH, DEVICE_NAME
from ._keystore import KeyStore
from ._unit import Group, Scene, Unit, UnitControl, UnitControlType, UnitType
from .errors import AuthenticationError, NetworkNotFoundError


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
    _session: _NetworkSession = None

    _networkName: str = None
    _networkRevision: int = None

    _unitTypes: Dict[int, UnitType] = {}
    units: List[Unit] = []
    groups: List[Group] = []
    scenes: List[Scene] = []

    def __init__(self, id: str, httpClient: AsyncClient = None) -> None:
        self._logger = logging.getLogger(__name__)
        self._keystore = KeyStore(id)
        self._id = id
        basePath = Path(BASE_PATH / id)

        if not basePath.exists():
            basePath.mkdir(parents=True)

        self._httpClient = httpClient

        self._sessionPath = basePath / "session.pck"
        if self._sessionPath.exists():
            self._loadSession()

        self._typeCachePath = basePath / "types.pck"
        if self._typeCachePath.exists():
            self._loadTypeCache()

    @property
    def name(self) -> str:
        return self._networkName

    @property
    def id(self) -> str:
        return self._id

    @property
    def revision(self) -> int:
        return self._networkRevision

    def _loadSession(self) -> None:
        self._logger.info("Loading session...")
        self._session = pickle.load(self._sessionPath.open("rb"))

    def _saveSesion(self) -> None:
        self._logger.info("Saving session...")
        pickle.dump(self._session, self._sessionPath.open("wb"))

    def _loadTypeCache(self) -> None:
        self._logger.info("Loading unit type cache...")
        self._unitTypes = pickle.load(self._typeCachePath.open("rb"))

    def _saveTypeCache(self) -> None:
        self._logger.info("Saving type cache...")
        pickle.dump(self._unitTypes, self._typeCachePath.open("wb"))

    def authenticated(self) -> bool:
        if not self._session:
            return False
        return not self._session.expired()

    def getKeyStore(self) -> KeyStore:
        return self._keystore

    async def logIn(self, password: str) -> Awaitable[bool]:
        self._logger.info(f"Logging in to network...")
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
            return True
        else:
            self._logger.error(f"Login failed: {res.status_code}\n{res.text}")
            return False

    async def update(self) -> Awaitable[bool]:
        self._logger.info(f"Updating network...")
        if not self.authenticated():
            raise AuthenticationError("Not authenticated!")

        # TODO: Save and send revision to receive actual updates?

        getNetworkUrl = f"https://api.casambi.com/network/{self._id}/"

        # **SECURITY**: Do not set session header for client! This could leak the session with external clients.
        res = await self._httpClient.put(
            getNetworkUrl,
            json={"formatVersion": 1, "deviceName": DEVICE_NAME},
            headers={"X-Casambi-Session": self._session.session},
        )

        if res.status_code != httpx.codes.OK:
            self._logger.error(f"Update failed: {res.status_code}\n{res.text}")
            return False

        self._logger.debug(f"Network: {res.text}")

        resJson = res.json()

        # Prase general information
        self._networkName = resJson["network"]["name"]
        self._networkRevision = resJson["network"]["revision"]

        # Parse keys
        keys = resJson["network"]["keyStore"]["keys"]
        for k in keys:
            self._keystore.addKey(k)

        # Parse units
        self.units = []
        units = resJson["network"]["units"]
        for u in units:
            uType = await self._fetchUnitInfo(u["type"])
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
        cells = resJson["network"]["grid"]["cells"]
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
        scenes = resJson["network"]["scenes"]
        for s in scenes:
            sObj = Scene(s["sceneID"], s["name"])
            self.scenes.append(sObj)

        # TODO: Parse more stuff

        self._saveTypeCache()

        self._logger.info("Network updated.")
        return True

    async def _fetchUnitInfo(self, id: int) -> Awaitable[UnitType]:
        self._logger.info(f"Fetching unit type for id {id}...")

        # Check whether unit type is already cached
        cachedType = self._unitTypes.get(id)
        if cachedType:
            self._logger.info("Using cached type.")
            return cachedType

        getUnitInfoUrl = f"https://api.casambi.com/fixture/{id}"
        async with AsyncClient() as request:
            res = await request.get(getUnitInfoUrl)

        if res.status_code != httpx.codes.OK:
            self._logger.error(f"Getting unit info returned {res.status_code}")

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
        self._unitTypes[unitTypeObj.id] = unitTypeObj

        self._logger.info("Sucessfully fetched unit type.")
        return unitTypeObj

    async def disconnect(self) -> None:
        return None


async def getNetworkIdFromUuid(mac: str, httpClient: AsyncClient) -> Awaitable[str]:
    _logger = logging.getLogger(__name__)
    _logger.info(f"Getting network id...")
    getNetworkIdUrl = f"https://api.casambi.com/network/uuid/{mac.replace(':', '')}"
    res = await httpClient.get(getNetworkIdUrl)

    if res.status_code == httpx.codes.NOT_FOUND:
        raise NetworkNotFoundError(
            "API failed to find network. Is your network configured correctly?"
        )
    if res.status_code != httpx.codes.OK:
        _logger.error(f"Getting network id returned {res.status_code}")
        return None

    id = res.json()["id"]
    _logger.info(f"Got network id {id}.")
    return id
