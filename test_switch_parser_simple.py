import logging
import sys
from binascii import a2b_hex, b2a_hex
from typing import Any

# Set up basic logging to see the output
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# Define minimal required classes
class IncommingPacketType:
    SwitchEvent = 7

def b2a(data: bytes) -> str:
    return b2a_hex(data).decode()

# Create a simple switch event parser based on the fixed logic
def parse_switch_event(data: bytes) -> dict[str, Any]:
    logger = logging.getLogger("switch_parser")
    logger.info(f"Parsing incoming switch event... Data: {b2a(data)}")

    # A switch event needs at least 3 bytes for a header
    if len(data) < 3:
        logger.warning(f"Incomplete switch event data: {b2a(data)}")
        return {}

    try:
        # Parse the header
        sensor_type = data[0]
        flags = data[1]
        length = ((data[2] >> 4) & 15) + 1
        source_id = data[2] & 15

        # Check if we have enough data for the payload
        if len(data) < 3 + length:
            logger.error(
                "Inconsistent length for switch event. "
                f"Declared: {length}, available: {len(data) - 3}. "
                f"Data: {b2a(data)}"
            )
            return {}

        # Extract the payload
        value_payload = data[3 : 3 + length]

        if not value_payload:
            logger.error(f"Switch event has zero length value. Data: {b2a(data)}")
            return {}

        # The button number seems to be encoded in the source_id.
        button = source_id

        unit_id = value_payload[0]

        action = None
        if len(value_payload) > 1:
            action = value_payload[1]

        actual_value = b''
        if len(value_payload) > 2:
            actual_value = value_payload[2:]

        event_string = "unknown"
        if action is not None:
            is_release = (action >> 1) & 1
            event_string = "button_release" if is_release else "button_press"

        action_display = f"{action:#04x}" if action is not None else "N/A"

        logger.info(
            f"Parsed switch event: sensor_type={sensor_type}, flags={flags:#04x}, "
            f"length={length}, button={button}, unit_id={unit_id}, "
            f"action={action_display} ({event_string}), value={b2a(actual_value)}"
        )

        result = {
            "sensor_type": sensor_type,
            "flags": flags,
            "length": length,
            "button": button,
            "unit_id": unit_id,
            "action": action,
            "event": event_string,
            "value": actual_value,
        }

        # Check if there's remaining data (which shouldn't be part of this event)
        if len(data) > 3 + length:
            logger.debug(f"Additional data after switch event: {b2a(data[3 + length:])}")

        return result

    except Exception as e:
        logger.error(f"Error parsing switch event! Data: {b2a(data)}", exc_info=True)
        return {}


if __name__ == "__main__":
    # Test with the hex data from your logs
    test_cases = [
        "0803201f851f06000599000229002a0f001f060003",  # First event from the test data
        "0803201f851f",  # Just the first event
        "06000599",  # What looks like a second event
        "000229002a0f",  # What looks like a third event
        "001f06",  # What looks like a fourth event
        "0003",  # Remaining bytes
        # Other examples from logs
        "29002a08001f060003",
        "29002a05001f060009",
        "0803201f8a1f060005190010",
        "1002430a981f120002020b",
        "10024308611f120002020b",
    ]

    print("=" * 80)
    print("Testing switch event parser with various data patterns")
    print("=" * 80)

    for i, hex_data in enumerate(test_cases, 1):
        print(f"\nTest Case {i}: {hex_data}")
        print("-" * 40)
        
        try:
            binary_data = a2b_hex(hex_data)
            result = parse_switch_event(binary_data)
            if result:
                print(f"Result: {result}")
        except Exception as e:
            print(f"Error processing hex data: {e}")