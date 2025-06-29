import logging
from binascii import b2a_hex as b2a
from collections.abc import Callable
from typing import Any


# To be populated with the correct enum from the main library
class IncommingPacketType:
    SwitchEvent = 7

def parse_switch_event(
    data: bytes, data_callback: Callable[[IncommingPacketType, dict[str, Any]], None]
) -> None:
    """Parses a switch event packet."""
    logger = logging.getLogger(__name__)
    logger.info(f"Parsing incoming switch event... Data: {b2a(data)}")

    pos = 0
    try:
        # A switch event needs at least 3 bytes for a header
        if len(data) < 3:
            logger.warning(f"Incomplete switch event data: {b2a(data)}")
            data_callback(IncommingPacketType.SwitchEvent, {"data": data})
            return

        sensor_type = data[pos]
        flags = data[pos + 1]
        length = ((data[pos + 2] >> 4) & 15) + 1
        source_id = data[pos + 2] & 15
        pos += 3

        if len(data) - pos < length:
            logger.error(
                "Inconsistent length for switch event. "
                f"Declared: {length}, available: {len(data) - pos}. "
                f"Data: {b2a(data)}"
            )
            data_callback(IncommingPacketType.SwitchEvent, {"data": data})
            return

        value_payload = data[pos : pos + length]
        pos += length

        if not value_payload:
            logger.error(f"Switch event has zero length value. Data: {b2a(data)}")
            data_callback(IncommingPacketType.SwitchEvent, {"data": data})
            return

        unit_id = value_payload[0]
        actual_value = value_payload[1:]

        # The button number seems to be encoded in the source_id.
        button = source_id

        logger.info(
            f"Parsed switch event: sensor_type={sensor_type}, flags={flags:#04x}, "
            f"length={length}, source_id={source_id}, button={button}, unit_id={unit_id}, value={b2a(actual_value)}"
        )

        data_callback(
            IncommingPacketType.SwitchEvent,
            {
                "sensor_type": sensor_type,
                "flags": flags,
                "length": length,
                "source_id": source_id,
                "button": button,
                "unit_id": unit_id,
                "value": actual_value,
            },
        )
        

        remaining_data = data[pos:]
        if remaining_data:
            logger.info(f"Remaining data in switch event packet: {b2a(remaining_data)}")

    except Exception:
        logger.error(f"Error parsing switch event! Data: {b2a(data)}", exc_info=True)
        data_callback(IncommingPacketType.SwitchEvent, {"data": data})
