import os
import shutil
from pathlib import Path
from typing import Final

CACHE_PATH: Final = Path(os.getcwd()) / "casambi-bt-store"
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
