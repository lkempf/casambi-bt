import asyncio
import logging
import os
import sys
from pathlib import Path

# Ensure we import the local working tree, not an older site-packages install.
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from CasambiBt import Casambi  # noqa: E402


async def main() -> None:
    # macOS: you may need to allow Terminal/Python Bluetooth access in System Settings.
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("CasambiBt").setLevel(logging.DEBUG)

    address = os.environ.get("CASAMBI_ADDRESS", "2A:CC:3F:C4:84:12")
    password = os.environ.get("CASAMBI_PASSWORD", "REPLACE_ME")
    force_offline = os.environ.get("CASAMBI_FORCE_OFFLINE", "").strip() in ("1", "true", "yes")

    casa = Casambi()

    def on_switch(ev: dict) -> None:
        # Look for these in logs:
        # - [CASAMBI_BUTTON_EVENT] ... event=button_press|button_release
        print("SWITCH_EVENT:", ev)

    casa.registerSwitchEventHandler(on_switch)

    try:
        await casa.connect(address, password, forceOffline=force_offline)
        print("Connected. Press buttons now; Ctrl+C to stop.")
        while True:
            await asyncio.sleep(3600)
    finally:
        await casa.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
