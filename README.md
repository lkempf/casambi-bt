![PyPI](https://img.shields.io/pypi/v/casambi-bt)

# A bluetooth based Python library for controlling Casambi networks

This library provides a currently **alpha quality** interface to Casambi-based lights over Bluetooth.
The author is not associated with Casambi and the implementation is based on his own analysis of the protocol.
This interface is not feature complete and was only tested with a very small network.

If you want to check out my (slow) progress in writing a integration for Homeassistant using this library you can take a look at [https://github.com/lkempf/casambi-bt-hass/](https://github.com/lkempf/casambi-bt-hass/).

For a more mature solution using a gateway and the official Casambi API have a look at [https://github.com/hellqvio86/aiocasambi](https://github.com/hellqvio86/aiocasambi).

## Getting started

This library is available on PyPi:
```
pip install casambi-bt
```
Have a look at `demo.py` for a small example.

### Casambi network setup

If you have problems connecting to the network please check that your network is configured appropriately before creating an issue. The network I test this with is configured as follows (screenshots are for the iOS app but the Android app should look very similar):

![Gateway settings](/doc/img/gateway.png)
![Network settings](/doc/img/network.png)
![Performance settings](/doc/img/perf.png)
