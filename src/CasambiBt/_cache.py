import asyncio
import logging
import os
import pathlib
import shutil
from types import TracebackType
from typing import Final

from aiopath import AsyncPath  # type: ignore

_LOGGER = logging.getLogger(__name__)

CACHE_PATH_DEFAULT: Final = AsyncPath(os.getcwd()) / "casambi-bt-store"
CACHE_VERSION: Final = 2

# We need a global lock since there could be multiple Caambi instances
# with their own cache instances pointing to the same folder.
_cacheLock = asyncio.Lock()


def _blocking_delete(path: AsyncPath) -> None:
    shutil.rmtree(pathlib.Path(path))


class Cache:
    def __init__(self, cachePath: AsyncPath | pathlib.Path | None) -> None:
        if cachePath is None:
            self._cachePath = CACHE_PATH_DEFAULT
        elif not isinstance(cachePath, AsyncPath):
            self._cachePath = AsyncPath(cachePath)
        else:
            self._cachePath = cachePath

        self._cacheVersionFile = self._cachePath / ".cachever"
        self._uuid: str | None = None
        _LOGGER.info("Selecting cache path %s", self._cachePath)

    async def setUuid(self, uuid: str) -> None:
        async with _cacheLock:
            self._uuid = uuid

    async def _ensureCacheValid(self) -> None:
        # We assume that we already have a lock when calling this function
        assert _cacheLock.locked()

        if await self._cachePath.exists():
            cacheVer = None
            if await self._cacheVersionFile.exists():
                try:
                    cacheVer = int(await self._cacheVersionFile.read_text())
                    _LOGGER.debug("Read cache version %i.", cacheVer)
                except ValueError:
                    cacheVer = -1
                    _LOGGER.error("Failed to parse cache version.", exc_info=True)
            if cacheVer is None:
                cacheVer = 0
            if cacheVer < CACHE_VERSION:
                _LOGGER.warning(
                    "Cache is version %i, version %i is required. Recreating cache.",
                    cacheVer,
                    CACHE_VERSION,
                )
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, _blocking_delete, self._cachePath)

        # This is not a redunant condition. We may have deleted the cache.
        if not await self._cachePath.exists():
            _LOGGER.info("Creating new cache.")
            await self._cachePath.mkdir(mode=0o700)
            await self._cacheVersionFile.write_text(str(CACHE_VERSION))

    async def __aenter__(self) -> AsyncPath:
        await _cacheLock.acquire()

        if self._uuid is None:
            raise ValueError("UUID not set.")

        try:
            await self._ensureCacheValid()

            cacheDir = AsyncPath(self._cachePath / self._uuid)
            if not await cacheDir.exists():
                _LOGGER.debug("Creating cache entry for id %s", self._uuid)
                await cacheDir.mkdir()

            _LOGGER.debug("Returning cache path %s for id %s.", cacheDir, self._uuid)
            return cacheDir
        except Exception:
            _cacheLock.release()
            raise

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        _cacheLock.release()

    async def invalidateCache(self) -> None:
        async with _cacheLock:
            if self._uuid is None:
                raise ValueError("UUID not set.")
            await self._ensureCacheValid()
            if not await (self._cachePath / self._uuid).exists():
                return
            _LOGGER.info("Deleting cache entry %s", self._uuid)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, _blocking_delete, self._cachePath / self._uuid
            )
