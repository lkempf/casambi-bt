import asyncio
import logging

from CasambiBt import Casambi, discover

_LOGGER = logging.getLogger()
_LOGGER.addHandler(logging.StreamHandler())


async def main():
    logging.getLogger("CasambiBt").setLevel(logging.DEBUG)

    print("Searching...")
    addrs = await discover()
    for i, a in enumerate(addrs):
        print(f"[{i}]\t{a}")

    selection = int(input("Select network: "))

    addr = addrs[selection]
    pwd = input("Enter password: ")

    casa = Casambi()
    await casa.connect(addr, pwd)

    await casa.setLevel(None, 0)
    await asyncio.sleep(1)
    for u in casa.units:
        print(u.__repr__())


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.create_task(main())
    loop.run_forever()
