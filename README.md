![PyPI](https://img.shields.io/pypi/v/casambi-bt-revamped)
[![Discord](https://img.shields.io/discord/1186445089317326888)](https://discord.gg/jgZVugfx)

# Casambi Bluetooth Revamped - Enhanced Python library for Casambi networks

This is an enhanced fork of the original [casambi-bt](https://github.com/lkempf/casambi-bt) library with additional features:

- **Switch event support** - Receive button press/release events from Casambi switches
- **Improved relay status handling** - Better support for relay units
- **Bug fixes and improvements** - Various fixes based on real-world usage

This library provides a bluetooth interface to Casambi-based lights. It is not associated with Casambi.

For Home Assistant integration using this library, see [casambi-bt-hass](https://github.com/rankjie/casambi-bt-hass).

## Getting started

This library is available on PyPi:

```
pip install casambi-bt-revamped
```

Have a look at `demo.py` for a small example.

### Switch Event Support

This library now supports receiving switch button events:

```python
from CasambiBt import Casambi

def handle_switch_event(event_data):
    print(f"Switch event: Unit {event_data['unit_id']}, "
          f"Button {event_data['button']}, "
          f"Action: {event_data['event']}")

casa = Casambi()
# ... connect to network ...

# Register switch event handler
casa.registerSwitchEventHandler(handle_switch_event)

# Events will be received when buttons are pressed/released
```

### MacOS

MacOS [does not expose the Bluetooth MAC address via their official API](https://github.com/hbldh/bleak/issues/140),
if you're running this library on MacOS, it will use an undocumented IOBluetooth API to get the MAC Address.
Without the real MAC address the integration with Casambi will not work.
If you're running into problems fetching the MAC address on MacOS, try it on a Raspberry Pi.

### Casambi network setup

If you have problems connecting to the network please check that your network is configured appropriately before creating an issue. The network I test this with uses the **Evoultion firmware** and is configured as follows (screenshots are for the iOS app but the Android app should look very similar):

![Gateway settings](/doc/img/gateway.png)
![Network settings](/doc/img/network.png)
![Performance settings](/doc/img/perf.png)
