import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Final, Optional

_LOGGER = logging.getLogger(__name__)

# HA detection logic: Use .storage folder if running under the assumed storage layout.
_cachePath = Path(os.getcwd()) / ".storage"
if not (_cachePath.exists() and _cachePath.is_dir() and "homeassistant" in sys.modules):
    _cachePath = _cachePath.parent
_cachePath /= "casambi-bt-store"
_LOGGER.info("Selecting cache path %s", _cachePath)

CACHE_PATH: Final = _cachePath
CACHE_VERSION: Final = 1
CACHE_VER_FILE: Final = CACHE_PATH / ".cachever"


def _ensureCacheValid() -> None:
    if CACHE_PATH.exists():
        cacheVer = None
        if CACHE_VER_FILE.exists():
            cacheVer = int(CACHE_VER_FILE.read_text())
        if not cacheVer or cacheVer < 1:
            shutil.rmtree(CACHE_PATH)

    # This is not a redunant condition. We may have deleted the cache.
    if not CACHE_PATH.exists():
        CACHE_PATH.mkdir(mode=0o700)
        CACHE_VER_FILE.write_text(str(CACHE_VERSION))


def getCacheDir(id: str) -> Path:
    _ensureCacheValid()

    cacheDir = CACHE_PATH / id
    if not cacheDir.exists():
        cacheDir.mkdir()

    return cacheDir


def invalidateCache(id: Optional[str]) -> None:
    if id is None:
        _LOGGER.warning("Invalidating all caches!")
        shutil.rmtree(CACHE_PATH)
    else:
        _LOGGER.info("Invalidating cache %s", id)
        shutil.rmtree(getCacheDir(id))
    _ensureCacheValid()
