![PyPI](https://img.shields.io/pypi/v/casambi-bt)
[![Discord](https://img.shields.io/discord/1186445089317326888)](https://discord.gg/jgZVugfx)

# A bluetooth based Python library for controlling Casambi networks

This library provides a currently **alpha quality** interface to Casambi-based lights over Bluetooth.
The author is not associated with Casambi and the implementation is based on his own analysis of the protocol.
This interface is not feature complete and was only tested with a very small network.

If you want to check out my (slow) progress in writing a integration for Home Assistant using this library you can take a look at [https://github.com/lkempf/casambi-bt-hass/](https://github.com/lkempf/casambi-bt-hass/).

For a more mature solution using a gateway and the official Casambi API have a look at [https://github.com/hellqvio86/aiocasambi](https://github.com/hellqvio86/aiocasambi).

## Getting started

This library is available on PyPi:

```
pip install casambi-bt
```

Have a look at `demo.py` for a small example.

### Switch event support

This library can receive physical switch events as a decoded stream of INVOCATION frames, matching the behavior observed in the official Android app.

Event types you can expect:
- `button_press`
- `button_release`
- `button_hold`
- `button_release_after_hold`
- `input_event` for raw `NotifyInput` frames that are still useful for diagnostics

```python
from CasambiBt import Casambi


def handle_switch_event(event_data):
    print(
        "Switch event:",
        {
            "unit_id": event_data.get("unit_id"),
            "button": event_data.get("button"),
            "event": event_data.get("event"),
            "event_id": event_data.get("event_id"),
            "opcode": event_data.get("opcode"),
            "target_type": event_data.get("target_type"),
            "origin": event_data.get("origin"),
            "age": event_data.get("age"),
            "input_code": event_data.get("input_code"),
            "input_channel": event_data.get("input_channel"),
            "input_value16": event_data.get("input_value16"),
            "input_mapped_event": event_data.get("input_mapped_event"),
        },
    )


casa = Casambi()
casa.registerSwitchEventHandler(handle_switch_event)
```

Notes:
- Wireless switches usually send a button stream (`target_type 0x06`) for press/release and a `NotifyInput` stream (`target_type 0x12`) for hold or release-after-hold.
- Wired switches often only send `NotifyInput`, so common input codes are mapped into the same button event taxonomy when possible.
- Duplicate same-state retransmits are suppressed in the decoder, so consumers usually do not need an extra time-window deduplication layer.

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

## Development

The switch parser is covered by log-driven unit tests:

```bash
python -m unittest tests.test_switch_event_logs -v
```
