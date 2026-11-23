"""Robustness of the data path and the command path."""

import asyncio
from time import monotonic
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from CasambiBt import (
    BluetoothError,
    Casambi,
    ConnectionStateError,
    Group,
    Unit,
    UnitControl,
    UnitControlType,
    UnitType,
)
from CasambiBt._constants import ConnectionState, IncomingPacketType
from CasambiBt._operation import (
    OpCode,
    OperationsContextClassic,
    OperationsContextEvolution,
)
from CasambiBt._switch import _MAX_SEEN_ORIGINS, SwitchEventDecoder


def _unit(device_id: int, controls: list[UnitControl]) -> Unit:
    return Unit(
        1,
        device_id,
        f"u{device_id}",
        "a",
        "n",
        "1",
        UnitType(1, "m", "v", "mode", 1, controls),
    )


def _casambi_with_units(units: list[Unit]) -> Casambi:
    casa = Casambi()
    casa._casaNetwork = MagicMock(units=units)
    return casa


def test_unknown_color_source_keeps_other_controls() -> None:
    unit = _unit(
        1,
        [
            UnitControl(UnitControlType.COLORSOURCE, 0, 2, 0, False),
            UnitControl(UnitControlType.DIMMER, 2, 6, 0, False),
        ],
    )
    unit.setStateFromBytes(bytes([0b11111111]))
    assert unit.state is not None
    assert unit.state.colorsource is None
    assert unit.state.dimmer == 0b111111 << 2


def test_parse_error_does_not_drop_other_units() -> None:
    """A unit that fails to parse must not swallow the update of others."""
    broken = _unit(1, [UnitControl(UnitControlType.DIMMER, 0, 8, 0, False)])
    ok = _unit(2, [UnitControl(UnitControlType.DIMMER, 0, 8, 0, False)])
    casa = _casambi_with_units([broken, ok])
    seen: list[int] = []
    casa.registerUnitChangedHandler(lambda u: seen.append(u.deviceId))

    with patch.object(broken, "setStateFromBytes", side_effect=RuntimeError("boom")):
        casa._dataCallback(
            IncomingPacketType.UnitState,
            {"id": 1, "online": True, "on": True, "state": b"\x10"},
        )
    casa._dataCallback(
        IncomingPacketType.UnitState,
        {"id": 2, "online": True, "on": True, "state": b"\x20"},
    )

    assert seen == [1, 2]
    assert broken.online
    assert ok.state is not None and ok.state.dimmer == 0x20


def test_handler_may_unregister_itself() -> None:
    unit = _unit(1, [UnitControl(UnitControlType.DIMMER, 0, 8, 0, False)])
    casa = _casambi_with_units([unit])
    calls: list[str] = []

    def first(_unit: Unit) -> None:
        calls.append("first")
        casa.unregisterUnitChangedHandler(first)

    casa.registerUnitChangedHandler(first)
    casa.registerUnitChangedHandler(lambda _u: calls.append("second"))

    casa._dataCallback(
        IncomingPacketType.UnitState,
        {"id": 1, "online": True, "on": True, "state": b"\x00"},
    )
    assert calls == ["first", "second"]


def test_disconnect_callback_without_network() -> None:
    casa = Casambi()
    callback = MagicMock()
    casa.registerDisconnectCallback(callback)
    casa._disconnectCallback()
    callback.assert_called_once()


def test_classic_sequence_skips_zero() -> None:
    """The 16 bit sequence number of classic networks must never be 0."""
    from CasambiBt._client import CasambiClientClassic

    client = object.__new__(CasambiClientClassic)
    client._outPacketCount = 0x10000
    client._managerEncryptor = None
    client._visitorEncryptor = MagicMock(digest=lambda packet, _hash: packet)
    client._connhash = b"\0" * 8
    client._gattClient = MagicMock(write_gatt_char=AsyncMock())
    client._logger = MagicMock()

    asyncio.run(client._sendInternal(b"\x01"))

    written = client._gattClient.write_gatt_char.await_args.args[1]
    assert written[1:3] == b"\x00\x01"
    assert client._outPacketCount == 0x10001


@pytest.mark.parametrize(
    "context", [OperationsContextEvolution(), OperationsContextClassic()]
)
def test_large_ids_raise_value_error(context) -> None:
    unit = _unit(300, [])
    with pytest.raises(ValueError):
        context.prepareOperation(OpCode.SetLevel, unit, b"\x01")


def test_classic_unsupported_operation_raises_value_error() -> None:
    with pytest.raises(ValueError):
        OperationsContextClassic().prepareOperation(
            OpCode.SetColorXY, Group(1, "g", []), b"\x00"
        )


def test_switch_dedup_is_bounded() -> None:
    decoder = SwitchEventDecoder()
    old = monotonic() - 10
    for origin in range(_MAX_SEEN_ORIGINS + 10):
        decoder._seen_origins[(1, 0, origin)] = old
    decoder._is_retransmit(1, 0, 1)
    assert len(decoder._seen_origins) == 0


async def test_send_reconnect_is_bounded() -> None:
    """A command must not wait for an endless reconnect."""
    casa = Casambi()
    client = MagicMock()
    client.send = AsyncMock(
        side_effect=ConnectionStateError(
            ConnectionState.AUTHENTICATED, ConnectionState.NONE
        )
    )
    casa._casaClient = client
    casa._casaNetwork = MagicMock(_networkRevision=1, protocolVersion=10)
    casa._opContext = OperationsContextEvolution()

    async def _hang(*_args) -> None:
        await asyncio.sleep(10)

    with (
        patch("CasambiBt._casambi.SEND_RECONNECT_TIMEOUT", 0.05),
        patch.object(casa, "reconnect", _hang),
        pytest.raises(BluetoothError),
    ):
        await casa.turnOn(None)


async def test_ble_device_callback_is_passed_to_retries() -> None:
    """Connection retries use the current device of the callback."""
    from bleak.backends.device import BLEDevice

    from CasambiBt._client import CasambiClientEvolution

    initial = BLEDevice("AA:BB:CC:DD:EE:FF", "C", None)
    current = BLEDevice("AA:BB:CC:DD:EE:FF", "C", {"proxy": 2})
    network = MagicMock(protocolVersion=10)
    client = CasambiClientEvolution(
        initial, MagicMock(), MagicMock(), network, lambda: current
    )

    with (
        patch("CasambiBt._client.close_stale_connections", AsyncMock()),
        patch("CasambiBt._client.establish_connection", AsyncMock()) as establish,
    ):
        await client.connect()
        await client.disconnect()

    assert establish.await_args is not None
    callback = establish.await_args.kwargs["ble_device_callback"]
    assert callback() is current


async def test_out_of_slots_is_a_bluetooth_error() -> None:
    from bleak.backends.device import BLEDevice
    from bleak_retry_connector import BleakOutOfConnectionSlotsError

    from CasambiBt._client import CasambiClientEvolution

    client = CasambiClientEvolution(
        BLEDevice("AA:BB:CC:DD:EE:FF", "C", None),
        MagicMock(),
        MagicMock(),
        MagicMock(protocolVersion=10),
    )
    with (
        patch("CasambiBt._client.close_stale_connections", AsyncMock()),
        patch(
            "CasambiBt._client.establish_connection",
            AsyncMock(side_effect=BleakOutOfConnectionSlotsError("full")),
        ),
        pytest.raises(BluetoothError, match="full"),
    ):
        await client.connect()
    await client.disconnect()
