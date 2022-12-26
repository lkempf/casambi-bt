import asyncio
import logging

from CasambiBt import Casambi, discover

_LOGGER = logging.getLogger()
_LOGGER.addHandler(logging.StreamHandler())


async def main():
    logging.getLogger("CasambiBt").setLevel(logging.DEBUG)

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


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.create_task(main())
    loop.run_forever()
