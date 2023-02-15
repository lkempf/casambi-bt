from typing import Final
from ._constants import BASE_PATH

import shutil

CACHE_VERSION: Final = 1

CACHE_VER_FILE = BASE_PATH / ".cachever"


def ensureCacheValid() -> None:
    if BASE_PATH.exists():
        cacheVer = None
        if CACHE_VER_FILE.exists():
            cacheVer = int(CACHE_VER_FILE.read_text())
        if not cacheVer or cacheVer < 1:
            shutil.rmtree(BASE_PATH)

    # This is not a redunant condition. We my have deleted the cache.
    if not BASE_PATH.exists():
        BASE_PATH.mkdir(mode=0o700)
        CACHE_VER_FILE.write_text(str(CACHE_VERSION))
