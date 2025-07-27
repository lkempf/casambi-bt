# Using Casambi-BT with ESPHome Bluetooth Proxy

This guide explains how to use the Casambi-BT library with ESPHome Bluetooth proxies for extended range and distributed Bluetooth access.

## Overview

With the migration to `bleak-esphome`, this library now supports connecting to Casambi devices through ESP32 boards running ESPHome firmware as Bluetooth proxies. This allows you to:

- Extend Bluetooth range beyond your computer's built-in adapter
- Place ESP32 devices strategically around your space for better coverage
- Use multiple proxies for redundancy and load balancing
- Connect to Bluetooth devices from systems without Bluetooth hardware

## Prerequisites

1. **ESP32 Device**: You need an ESP32 board (not ESP8266, as it doesn't support Bluetooth)
2. **ESPHome**: Install ESPHome on your system or use the Home Assistant add-on
3. **Updated Library**: This library with `bleak-esphome` support

## Setting Up ESP32 as Bluetooth Proxy

### 1. Flash ESP32 with ESPHome

Use the provided `esphome_bluetooth_proxy.yaml` configuration:

```bash
# Install ESPHome if not already installed
pip install esphome

# Create secrets.yaml with your WiFi credentials
cat > secrets.yaml << EOF
wifi_ssid: "YourWiFiSSID"
wifi_password: "YourWiFiPassword"
ap_password: "fallback-hotspot-password"
EOF

# Compile and flash the firmware
esphome run esphome_bluetooth_proxy.yaml
```

### 2. Verify ESP32 is Running

After flashing, the ESP32 should:
- Connect to your WiFi network
- Start the Bluetooth proxy service
- Be accessible via web interface at `http://<esp32-ip-address>`

## Using the Library

The library now uses `bleak-esphome` automatically. Your existing code should work without modifications:

```python
import asyncio
from CasambiBt import Casambi, discover

async def main():
    # Create Casambi instance
    casa = Casambi()
    
    # Discover networks - will use ESPHome proxies if available
    networks = await discover()
    
    # Connect as usual
    if networks:
        await casa.connect(networks[0], "password")
        
        # Control devices
        for unit in casa.units:
            await casa.turnOn(unit)

asyncio.run(main())
```

## Configuration Options

### ESPHome YAML Configuration

Key settings in `esphome_bluetooth_proxy.yaml`:

- **scan_parameters**: Adjust scanning behavior
  - `interval`: Time between scans (default: 1100ms)
  - `window`: Active scanning time (default: 1100ms)
  - `active`: Enable active scanning for better discovery

- **bluetooth_proxy**: 
  - `active`: Must be `true` for Casambi control
  - `connection_slots`: Maximum simultaneous connections (max 3 recommended)

### Advanced Configuration

For specific proxy configuration or multiple proxies, you may need to set environment variables or use Home Assistant's configuration. Consult the `bleak-esphome` documentation for advanced setups.

## Troubleshooting

### ESP32 Not Connecting to WiFi
- Check WiFi credentials in `secrets.yaml`
- Ensure ESP32 is within WiFi range
- Try the fallback AP mode: look for "Casambi Bluetooth Proxy Hotspot"

### Devices Not Discovered
- Verify ESP32 status LED is solid (not blinking)
- Check web interface at `http://<esp32-ip>`
- Ensure Casambi devices are within range of ESP32
- Try increasing scan window/interval in YAML

### Connection Issues
- ESP32 supports max 3 simultaneous BLE connections
- Restart ESP32 if connections seem stuck
- Check ESP32 logs via web interface or `esphome logs`

### Performance Tips
- Use Ethernet-connected ESP32 for best performance
- Place ESP32 centrally for optimal coverage
- Use multiple ESP32 proxies for large spaces
- Keep ESP32 firmware updated

## Benefits Over Direct Bluetooth

1. **Extended Range**: ESP32 can be placed closer to Casambi devices
2. **No Computer Bluetooth Required**: Run on servers without Bluetooth
3. **Multiple Access Points**: Use several ESP32s for coverage
4. **Remote Access**: Control devices from anywhere on your network
5. **Better Reliability**: Dedicated ESP32 avoids computer sleep/bluetooth issues

## Example Setup Scenarios

### Single Room
- One ESP32 in the center of the room
- All Casambi devices within 10-15 meters

### Multi-Room Home
- One ESP32 per floor or per 100m²
- Strategic placement near device clusters
- All ESP32s on same network

### Commercial Space
- Multiple ESP32s with Ethernet connections
- Redundant coverage for critical areas
- Consider using external antennas

## Security Considerations

- Use strong WiFi passwords
- Enable API passwords in ESPHome if needed
- Keep ESPHome firmware updated
- Use encrypted API communication for sensitive installations

## Next Steps

- Monitor ESP32 performance via web interface
- Experiment with scan parameters for your environment
- Consider Home Assistant integration for automation
- Join ESPHome community for advanced configurations