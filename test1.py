import asyncio
import binascii

from bleak import BleakScanner


async def main():
    devices = await BleakScanner.discover()
    for device in devices:
        print(f"Device: {device.name or 'Unknown'}")
        print(f"  Address: {device.address}")
        print(f"  RSSI: {device.rssi}")
        if device.metadata.get("manufacturer_data"):
            for company_code, data in device.metadata["manufacturer_data"].items():
                print(f"  Manufacturer Data:")
                print(f"    Company Code: {company_code}")
                print(f"    Data: {binascii.b2a_hex(data).decode()}")
        print()

asyncio.run(main())
