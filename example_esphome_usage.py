#!/usr/bin/env python3
"""Example of using Casambi-BT with ESPHome Bluetooth Proxy.

This example demonstrates how to connect to Casambi devices through
an ESP32 running ESPHome with Bluetooth proxy enabled.
"""

import asyncio
import logging
from pathlib import Path
from CasambiBt import Casambi, discover

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Main example function."""
    
    # ESPHome proxy configuration (if needed)
    # Currently bleak-esphome should automatically discover proxies
    # through Home Assistant or can be configured with environment variables
    
    # Create Casambi instance
    casa = Casambi(cachePath=Path("~/.casambi_cache").expanduser())
    
    try:
        # Discover Casambi networks
        # This will now work through ESPHome proxies if available
        logger.info("Discovering Casambi networks...")
        networks = await discover()
        
        if not networks:
            logger.error("No Casambi networks found")
            return
            
        # Log discovered networks
        for network in networks:
            logger.info(f"Found network: {network.address} - {network.name}")
        
        # Connect to the first network
        network_device = networks[0]
        password = "your_network_password"  # Replace with actual password
        
        logger.info(f"Connecting to network {network_device.address}...")
        await casa.connect(network_device, password)
        
        logger.info(f"Connected to network: {casa.networkName}")
        logger.info(f"Network ID: {casa.networkId}")
        
        # List all units
        logger.info("\nUnits in network:")
        for unit in casa.units:
            logger.info(f"  - {unit.name} (ID: {unit.deviceId}, Online: {unit.online})")
        
        # List all groups
        logger.info("\nGroups in network:")
        for group in casa.groups:
            logger.info(f"  - {group.name} (ID: {group.groudId})")
        
        # List all scenes
        logger.info("\nScenes in network:")
        for scene in casa.scenes:
            logger.info(f"  - {scene.name} (ID: {scene.sceneId})")
        
        # Example: Control a unit
        if casa.units:
            unit = casa.units[0]
            logger.info(f"\nControlling unit: {unit.name}")
            
            # Turn on
            await casa.turnOn(unit)
            await asyncio.sleep(2)
            
            # Set brightness to 50%
            await casa.setLevel(unit, 128)
            await asyncio.sleep(2)
            
            # Turn off
            await casa.setLevel(unit, 0)
        
        # Register a callback for unit changes
        def unit_changed(unit):
            logger.info(f"Unit {unit.name} changed - On: {unit.on}, Level: {unit.level}")
        
        casa.registerUnitChangedHandler(unit_changed)
        
        # Register a callback for switch events
        def switch_event(event):
            logger.info(f"Switch event: {event}")
        
        casa.registerSwitchEventHandler(switch_event)
        
        # Keep the connection alive for a while to receive events
        logger.info("\nListening for events for 30 seconds...")
        await asyncio.sleep(30)
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
    finally:
        # Always disconnect
        await casa.disconnect()
        logger.info("Disconnected")


if __name__ == "__main__":
    asyncio.run(main())