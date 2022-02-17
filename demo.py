import asyncio
import logging

from CasambiBt import Casambi, discover

_LOGGER = logging.getLogger()
_LOGGER.addHandler(logging.StreamHandler())


async def main():
    logging.getLogger("CasambiBt").setLevel(logging.DEBUG)

    # Discover networks
    print("Searching...")
    addrs = await discover()
    for i, a in enumerate(addrs):
        print(f"[{i}]\t{a}")

    selection = int(input("Select network: "))

    addr = addrs[selection]
    pwd = input("Enter password: ")

    # Connect to the selected network
    casa = Casambi()
    await casa.connect(addr, pwd)

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
