#!/usr/bin/env python3
"""Example of using Casambi-BT with ESPHome Bluetooth Proxy via bleak-esphome.

This example shows how to connect to Casambi devices through an ESP32
running ESPHome with Bluetooth proxy enabled using bleak-esphome.
"""

import asyncio
import logging
from pathlib import Path
from bleak import BleakClient, BleakScanner
from bleak_esphome import ESPHomeDeviceConfig, APIConnectionManager
from CasambiBt import Casambi, discover

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def connect_via_esphome_proxy():
    """Example of connecting through ESPHome proxy."""
    
    # ESPHome device configuration
    esphome_config = ESPHomeDeviceConfig(
        address="192.168.1.100",  # Replace with your ESP32 IP
        port=6053,  # Default ESPHome API port
        # password="your_api_password",  # If you set an API password
        # encryption_key="your_base64_key",  # If using encryption
    )
    
    # Create API connection manager
    connection_manager = APIConnectionManager()
    
    try:
        # Connect to ESPHome device
        logger.info(f"Connecting to ESPHome device at {esphome_config.address}...")
        api_client = await connection_manager.get_client(esphome_config)
        
        # The bleak-esphome library sets up the environment so that
        # standard bleak calls will route through the ESPHome proxy
        
        # Now use Casambi as normal - it will automatically use the proxy
        casa = Casambi(cachePath=Path("~/.casambi_cache").expanduser())
        
        # Discover networks through the proxy
        logger.info("Discovering Casambi networks via ESPHome proxy...")
        networks = await discover()
        
        if not networks:
            logger.error("No Casambi networks found")
            return
            
        # Connect and control as usual
        network_device = networks[0]
        password = "your_network_password"
        
        logger.info(f"Connecting to network {network_device.address}...")
        await casa.connect(network_device, password)
        
        logger.info(f"Connected to network: {casa.networkName}")
        
        # Control devices as normal
        for unit in casa.units:
            logger.info(f"Unit: {unit.name} (ID: {unit.deviceId})")
            
        await casa.disconnect()
        
    finally:
        # Clean up ESPHome connection
        await connection_manager.disconnect_all()


async def direct_esphome_example():
    """Lower-level example using bleak-esphome directly."""
    from bleak_esphome import connect
    
    # ESPHome device configuration
    esphome_config = ESPHomeDeviceConfig(
        address="192.168.1.100",  # Your ESP32 IP
        port=6053,
    )
    
    # MAC address of your Casambi device
    device_address = "XX:XX:XX:XX:XX:XX"
    
    # Connect to BLE device through ESPHome proxy
    async with connect(device_address, esphome_config) as client:
        # Now use client as a normal BleakClient
        services = await client.get_services()
        for service in services:
            logger.info(f"Service: {service.uuid}")
            for char in service.characteristics:
                logger.info(f"  Characteristic: {char.uuid}")


async def auto_discovery_with_home_assistant():
    """Example using automatic discovery with Home Assistant.
    
    If bleak-esphome is running in a Home Assistant environment,
    it can automatically discover and use ESPHome Bluetooth proxies.
    """
    
    # In Home Assistant environment, bleak-esphome can automatically
    # discover and use available ESPHome Bluetooth proxies
    
    casa = Casambi(cachePath=Path("~/.casambi_cache").expanduser())
    
    # This will automatically use available ESPHome proxies
    # if running in Home Assistant with bluetooth proxies configured
    networks = await discover()
    
    if networks:
        logger.info(f"Found {len(networks)} networks via proxy")
        # Continue as normal...


if __name__ == "__main__":
    # Choose which example to run
    asyncio.run(connect_via_esphome_proxy())