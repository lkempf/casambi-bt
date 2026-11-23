import binascii
import logging
import pickle
from dataclasses import dataclass
from typing import Final

from CasambiBt._constants import CLASSIC_AUTH_LEVEL_MANAGER, CLASSIC_AUTH_LEVEL_VISITOR

from ._cache import Cache


@dataclass()
class Key:
    id: int
    type: int
    role: int
    name: str
    key: bytes


KEY_CACHE_FILE: Final = "keys.pck"


class KeyStore:
    def __init__(self, cache: Cache) -> None:
        self._keys: list[Key] = []
        self._logger = logging.getLogger(__name__)

        self._cache = cache

    async def load(self) -> None:
        self._logger.info("Loading keys...")
        async with self._cache as cachePath:
            if not await (cachePath / KEY_CACHE_FILE).exists():
                self._logger.debug("No cached keys.")
                return
            key_bytes = await (cachePath / KEY_CACHE_FILE).read_bytes()
            try:
                self._keys = pickle.loads(key_bytes)
            except Exception:
                # The keys are part of the network configuration and are
                # restored from it on the next update.
                self._logger.warning("Key cache is unreadable.", exc_info=True)
                self._keys = []
                return
            self._logger.debug("Loaded %i keys.", len(self._keys))

    async def _save(self) -> None:
        self._logger.info("Saving keys...")
        async with self._cache as cachePath:
            key_bytes = pickle.dumps(self._keys)
            await (cachePath / KEY_CACHE_FILE).write_bytes(key_bytes)
            self._logger.debug("Saved %i keys.", len(self._keys))

    async def addKey(self, dict: dict) -> None:
        if await self._addKeyInternal(dict):
            await self._save()

    async def _addKeyInternal(self, dict: dict) -> bool:
        if "id" not in dict:
            raise KeyError("id")
        id = int(dict["id"])
        if id < 0:
            raise ValueError("id")

        if any(k.id == id for k in self._keys):
            self._logger.debug("Key with id %i already exists. Skipping...", id)
            return False

        if "type" not in dict:
            raise KeyError("type")
        type = int(dict["type"])
        if type < 0 or type > 0xFF:
            raise ValueError("type")

        if "role" not in dict:
            raise KeyError("role")
        role = int(dict["role"])
        if role < 0 or role > 3:
            raise ValueError("role")

        if "name" not in dict:
            raise KeyError("name")
        name = dict["name"]

        if "key" not in dict:
            raise KeyError("key")
        try:
            key = binascii.a2b_hex(dict["key"])
        except binascii.Error as err:
            raise ValueError("key") from err

        keyObj = Key(id, type, role, name, key)
        self._keys.append(keyObj)
        self._logger.info("Added key %s with role %i to store.", name, role)
        return True

    async def setLegacyKey(self, key: str, isVisitor: bool) -> None:
        if self._setLegacyKeyInternal(key, isVisitor):
            await self._save()

    def _setLegacyKeyInternal(self, key: str, isVisitor: bool) -> bool:
        keyRole = (
            CLASSIC_AUTH_LEVEL_VISITOR if isVisitor else CLASSIC_AUTH_LEVEL_MANAGER
        )
        keyBytes = binascii.a2b_hex(key)
        for i, k in enumerate(self._keys):
            if k.type != -1:  # Not a legacy key
                continue
            if k.role == keyRole:
                if k.key == keyBytes:
                    return False
                _ = self._keys.pop(i)
                break

        self._keys.append(Key(-1, -1, keyRole, "legacy", keyBytes))
        self._logger.info("Added legacy key with role %i to store.", keyRole)
        return True

    async def replaceKeys(
        self,
        keys: list[dict],
        visitorKey: str | None = None,
        managerKey: str | None = None,
    ) -> None:
        """Replace the stored keys with the keys of a network configuration.

        Keys that changed or were removed from the network are updated, so a
        rotated key never sticks in the cache. The keys are only saved when
        they changed.
        """
        newStore = KeyStore(self._cache)
        for k in keys:
            await newStore._addKeyInternal(k)
        if visitorKey:
            newStore._setLegacyKeyInternal(visitorKey, True)
        if managerKey:
            newStore._setLegacyKeyInternal(managerKey, False)

        if newStore._keys == self._keys:
            return
        self._keys = newStore._keys
        self._logger.info("Updated keys. %i keys in store.", len(self._keys))
        await self._save()

    async def clear(self, save: bool = False) -> None:
        self._keys.clear()
        self._logger.info("Keystore cleared.")
        if save:
            await self._save()

    def getKey(self) -> Key | None:
        key: Key | None = None
        for k in self._keys:
            if k.type == -1:  # Legacy key
                continue
            if not key:
                key = k
            elif key.role < k.role:
                key = k
        return key

    def getLegacyKey(self, role: int) -> Key | None:
        for k in self._keys:
            if k.type != -1:  # Not a legacy key
                continue
            elif k.role == role:
                return k
        return None
