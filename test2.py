import asyncio
import binascii
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from src.CasambiBt import Casambi, discover


async def main():
    print("Scanning for nearby Casambi network devices...")
    try:
        devices = await discover()
        
        if not devices:
            print("No Casambi devices found.")
            return

        print(f"Found {len(devices)} Casambi device(s):")
        for device in devices:
            print(f"Device: {device.name or 'Unknown'}")
            print(f"  Address: {device.address}")
            print(f"  RSSI: {device.rssi}")
            if device.metadata.get("manufacturer_data"):
                for company_code, data in device.metadata["manufacturer_data"].items():
                    print(f"  Manufacturer Data:")
                    print(f"    Company Code: {company_code}")
                    print(f"    Data: {binascii.b2a_hex(data).decode()}")

        # Select the first device (you can modify this to allow user selection)
        selected_device = devices[0]
        
        # You need to provide the network password here
        network_password = "111930zc"  # Replace with actual password

        # Connect to the network
        casa = Casambi()
        await casa.connect(selected_device, network_password)
        print(f"Connected to network: {selected_device.name}")

        # Print all units in the network
        print("\nUnits in the network:")
        for unit in casa.units:
            print(f"  Unit ID: {unit.id}")
            print(f"    Name: {unit.name}")
            print(f"    Address: {unit.address}")
            print(f"    Type: {unit.type.model}")
            print(f"    State: {unit.state}")
            print()

        # Don't forget to disconnect
        await casa.disconnect()

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())