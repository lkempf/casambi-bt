import asyncio
import logging
import sys
from importlib.metadata import version

from CasambiBt import Casambi, discover

formatter = logging.Formatter(
    fmt="%(asctime)s %(name)-8s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
stream = logging.StreamHandler()
stream.setFormatter(formatter)
logging.getLogger().addHandler(stream)
_LOGGER = logging.getLogger(__name__)


async def main() -> None:
    logLevel = logging.INFO
    if "-d" in sys.argv:
        logLevel = logging.DEBUG
        logging.getLogger("bleak").setLevel(logging.DEBUG)

    _LOGGER.setLevel(logLevel)
    logging.getLogger("CasambiBt").setLevel(logLevel)

    _LOGGER.debug(f"Bleak version: {version('bleak')}")
    _LOGGER.debug(f"Bleak retry connector version: {version('bleak-retry-connector')}")

    # Discover networks
    print("Searching...")
    devices = await discover()
    for i, d in enumerate(devices):
        print(f"[{i}]\t{d.address}")

    selection = int(input("Select network: "))

    device = devices[selection]
    pwd = input("Enter password: ")

    # Connect to the selected network
    casa = Casambi()
    try:
        await casa.connect(device, pwd)

        # Turn all lights on
        await casa.turnOn(None)
        await asyncio.sleep(5)

        # Turn all lights off
        await casa.setLevel(None, 0)
        await asyncio.sleep(1)

        # Print the state of all units
        for u in casa.units:
            print(u.__repr__())
    finally:
        await casa.disconnect()


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main())
