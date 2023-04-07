import binascii
import logging
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass()
class Key:
    id: int
    type: int
    role: int
    name: str
    key: bytes


class KeyStore:
    def __init__(self, cacheDir: Path) -> None:
        self._keys: list[Key] = []
        self._logger = logging.getLogger(__name__)

        self._storePath = cacheDir / "keys.pck"
        if self._storePath.exists():
            self._load()

    def _load(self) -> None:
        self._logger.info("Loading keys...")
        self._keys = pickle.load(self._storePath.open("rb"))
        self._logger.info(f"Loaded {len(self._keys)} keys.")

    def _save(self) -> None:
        self._logger.info("Saving keys...")
        pickle.dump(self._keys, (self._storePath.open("wb")))

    def addKey(self, dict: dict) -> None:
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
        self._save()

    def clear(self, save: bool = False) -> None:
        self._keys.clear()
        self._logger.info("Keystore cleared.")
        if save:
            self._save()

    def getKey(self) -> Optional[Key]:
        key: Optional[Key] = None
        for k in self._keys:
            if not key:
                key = k
            elif key.role < k.role:
                key = k
        return key
