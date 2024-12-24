import binascii
import logging
import pickle
from dataclasses import dataclass
from typing import Final

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
            self._keys = pickle.loads(key_bytes)
            self._logger.debug(f"Loaded {len(self._keys)} keys.")

    async def _save(self) -> None:
        self._logger.info("Saving keys...")
        async with self._cache as cachePath:
            key_bytes = pickle.dumps(self._keys)
            await (cachePath / KEY_CACHE_FILE).write_bytes(key_bytes)
            self._logger.debug(f"Saved {len(self._keys)} keys.")

    async def addKey(self, dict: dict) -> None:
        if "id" not in dict:
            raise KeyError("id")
        id = int(dict["id"])
        if id < 0:
            raise ValueError("id")

        if any(filter(lambda k: k.id == id, self._keys)):  # type: ignore
            self._logger.info(f"Key with id {id} already exists. Skipping...")
            return

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
        except binascii.Error:
            raise ValueError("key")

        keyObj = Key(id, type, role, name, key)
        self._keys.append(keyObj)
        self._logger.info(f"Added key {name} with role {role} to store.")
        await self._save()

    async def clear(self, save: bool = False) -> None:
        self._keys.clear()
        self._logger.info("Keystore cleared.")
        if save:
            await self._save()

    def getKey(self) -> Key | None:
        key: Key | None = None
        for k in self._keys:
            if not key:
                key = k
            elif key.role < k.role:
                key = k
        return key
