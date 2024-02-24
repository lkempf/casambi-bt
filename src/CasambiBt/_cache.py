import logging
import os
import shutil
import threading
from pathlib import Path
from types import TracebackType
from typing import Final, Optional

_LOGGER = logging.getLogger(__name__)

CACHE_PATH_DEFAULT: Final = Path(os.getcwd()) / "casambi-bt-store"
CACHE_VERSION: Final = 2

# We need a global lock since there could be multiple Caambi instances
# with their own cache instances pointing to the same folder.
_cacheLock = threading.Lock()


class Cache:
    def __init__(self, cachePath: Optional[Path]) -> None:
        self._cachePath = cachePath if cachePath is not None else CACHE_PATH_DEFAULT
        self._cacheVersionFile = self._cachePath / ".cachever"
        self._uuid: Optional[str] = None
        _LOGGER.info("Selecting cache path %s", self._cachePath)

    def setUuid(self, uuid: str) -> None:
        with _cacheLock:
            self._uuid = uuid

    def _ensureCacheValid(self) -> None:
        # We assume that we already have a lock when calling this function
        assert _cacheLock.locked()

        if self._cachePath.exists():
            cacheVer = None
            if self._cacheVersionFile.exists():
                try:
                    cacheVer = int(self._cacheVersionFile.read_text())
                    _LOGGER.debug("Read cache version %i.", cacheVer)
                except ValueError:
                    cacheVer = -1
                    _LOGGER.error("Failed to parse cache version.", exc_info=True)
            if cacheVer is None:
                cacheVer = 0
            if cacheVer < CACHE_VERSION:
                _LOGGER.warn(
                    "Cache is version %i, version %i is required. Recreating cache.",
                    cacheVer,
                    CACHE_VERSION,
                )
                shutil.rmtree(self._cachePath)

        # This is not a redunant condition. We may have deleted the cache.
        if not self._cachePath.exists():
            _LOGGER.info("Creating new cache.")
            self._cachePath.mkdir(mode=0o700)
            self._cacheVersionFile.write_text(str(CACHE_VERSION))

    def __enter__(self) -> Path:
        _cacheLock.acquire()

        if self._uuid is None:
            raise ValueError("UUID not set.")

        try:
            self._ensureCacheValid()

            cacheDir = self._cachePath / self._uuid
            if not cacheDir.exists():
                _LOGGER.debug("Creating cache entry for id %s", self._uuid)
                cacheDir.mkdir()

            _LOGGER.debug("Returning cache path %s for id %s.", cacheDir, self._uuid)
            return cacheDir
        except Exception:
            _cacheLock.release()
            raise

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        _cacheLock.release()

    def invalidateCache(self) -> None:
        with _cacheLock:
            if self._uuid is None:
                raise ValueError("UUID not set.")
            self._ensureCacheValid()
            if not (self._cachePath / self._uuid).exists():
                return
            _LOGGER.info("Deleting cache entry %s", self._uuid)
            shutil.rmtree(self._cachePath / self._uuid)
