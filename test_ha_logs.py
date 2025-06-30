import logging
import sys
from binascii import a2b_hex, b2a_hex
from typing import Any

# Set up basic logging to see the output
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

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
            remaining = data[3 + length:]
            logger.info(f"Additional data after switch event: {b2a(remaining)} (length: {len(remaining)})")
            result["remaining_data"] = remaining

        return result

    except Exception as e:
        logger.error(f"Error parsing switch event! Data: {b2a(data)}", exc_info=True)
        return {}


if __name__ == "__main__":
    # All hex data from the Home Assistant logs
    ha_log_data = [
        ("2025-06-30 15:04:54.385", "0803201f851f06000599000229002a0f001f060003"),
        ("2025-06-30 15:04:54.389", "29002a08001f060003"),
        ("2025-06-30 15:04:54.422", "29002a05001f060009"),
        ("2025-06-30 15:04:54.460", "0803201f851f06000c99000229002a02001f06000b"),
        ("2025-06-30 15:04:54.534", "0803201f8a1f060005190010"),
        ("2025-06-30 15:04:54.609", "0803201f8a1f06000e190010"),
        ("2025-06-30 15:04:54.686", "0803201f8a1f060015190010"),
        ("2025-06-30 15:04:54.723", "1002430a981f120002020b"),
        ("2025-06-30 15:04:54.728", "10024308611f120002020b"),
        ("2025-06-30 15:04:54.834", "29002a02001f060030"),
        ("2025-06-30 15:04:58.171", "29002a02001f06017d"),
    ]

    print("=" * 80)
    print("Testing switch event parser with Home Assistant log data")
    print("=" * 80)

    # Summary statistics
    sensor_types = {}
    button_counts = {}
    unit_ids = {}
    event_types = {}

    for timestamp, hex_data in ha_log_data:
        print(f"\nTimestamp: {timestamp}")
        print(f"Hex data: {hex_data}")
        print("-" * 60)
        
        try:
            binary_data = a2b_hex(hex_data)
            result = parse_switch_event(binary_data)
            
            if result:
                # Collect statistics
                sensor_types[result['sensor_type']] = sensor_types.get(result['sensor_type'], 0) + 1
                button_counts[result['button']] = button_counts.get(result['button'], 0) + 1
                unit_ids[result['unit_id']] = unit_ids.get(result['unit_id'], 0) + 1
                event_types[result['event']] = event_types.get(result['event'], 0) + 1
                
                print(f"Parsed result:")
                print(f"  Sensor Type: {result['sensor_type']}")
                print(f"  Button: {result['button']}")
                print(f"  Unit ID: {result['unit_id']}")
                print(f"  Event: {result['event']}")
                if result['action'] is not None:
                    print(f"  Action: {result['action']:#04x}")
                if result['value']:
                    print(f"  Value: {b2a(result['value'])}")
                if 'remaining_data' in result:
                    print(f"  Note: Has additional data after event")
                    
        except Exception as e:
            print(f"Error processing hex data: {e}")

    print("\n" + "=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)
    
    print("\nSensor Types:")
    for sensor_type, count in sorted(sensor_types.items()):
        print(f"  Type {sensor_type}: {count} events")
    
    print("\nButtons Used:")
    for button, count in sorted(button_counts.items()):
        print(f"  Button {button}: {count} events")
    
    print("\nUnit IDs:")
    for unit_id, count in sorted(unit_ids.items()):
        print(f"  Unit {unit_id}: {count} events")
    
    print("\nEvent Types:")
    for event_type, count in sorted(event_types.items()):
        print(f"  {event_type}: {count} events")