#!/usr/bin/env python3
"""
Test current parser implementation with specific hex data
"""
from binascii import a2b_hex, b2a_hex

# Test data from the log
test_data = [
    "1002411460141200070101",
    "1002411461141200060201", 
    "1002411461141200090201",
    "10024114611412003a0201"
]

def simulate_current_parser(hex_str):
    """Simulate the current parser logic"""
    data = a2b_hex(hex_str)
    print(f"\nParsing: {hex_str}")
    print(f"Data length: {len(data)} bytes")
    
    # Current parser logic (from the log output)
    # It appears to parse the first message as a switch event
    sensor_type = data[0]  # Actually message type
    flags = data[1]
    length = ((data[2] >> 4) & 15) + 1
    button = data[2] & 15
    
    # Extract payload
    payload = data[3:3+length]
    unit_id = payload[0]
    action = payload[1] if len(payload) > 1 else None
    value = payload[2:] if len(payload) > 2 else b''
    
    # Determine event type (current logic)
    if action is not None:
        is_release = (action >> 1) & 1
        event_string = "button_release" if is_release else "button_press"
    else:
        event_string = "unknown"
    
    print(f"Current parser output:")
    print(f"  sensor_type={sensor_type}, flags=0x{flags:02x}, length={length}, button={button}")
    print(f"  unit_id={unit_id}, action=0x{action:02x} ({event_string}), value={b2a_hex(value).decode()}")
    
    # Remaining data
    remaining = data[3+length:]
    if remaining:
        print(f"  Remaining data: {b2a_hex(remaining).decode()}")
    
    return action, event_string, remaining

def analyze_with_new_understanding(hex_str):
    """Analyze with our new understanding"""
    data = a2b_hex(hex_str)
    
    print(f"\nNew analysis of: {hex_str}")
    
    # Parse as message type 0x10
    msg_type = data[0]
    flags = data[1] 
    length_button = data[2]
    length = ((length_button >> 4) & 0x0F) + 1
    button = length_button & 0x0F
    
    payload = data[3:3+length]
    remaining = data[3+length:] if len(data) > 3+length else b''
    
    unit_id = payload[0]
    action = payload[1]
    extra_payload = payload[2:]
    
    print(f"  Message type: 0x{msg_type:02x}")
    print(f"  Button: {button}")
    print(f"  Unit ID: {unit_id}")
    print(f"  Action: 0x{action:02x}")
    
    # Check the remaining 3 bytes
    if len(remaining) >= 3:
        seq = remaining[0]
        state = remaining[1]
        button_confirm = remaining[2]
        
        state_str = "PRESS" if state == 0x01 else "RELEASE" if state == 0x02 else "UNKNOWN"
        print(f"  Additional info: seq={seq}, state=0x{state:02x} ({state_str}), button={button_confirm}")

def main():
    print("TESTING CURRENT PARSER WITH LOG DATA")
    print("=" * 80)
    
    # Test with current parser logic
    print("\n1. CURRENT PARSER BEHAVIOR:")
    print("-" * 60)
    
    actions_seen = []
    for hex_str in test_data:
        action, event, remaining = simulate_current_parser(hex_str)
        actions_seen.append((action, event))
    
    print("\n\nSummary of current parser:")
    for i, (action, event) in enumerate(actions_seen):
        print(f"  Packet {i+1}: action=0x{action:02x} → {event}")
    
    print("\nISSUE: All packets show as 'button_press' because:")
    print("- 0x60 binary: 01100000 → bit 1 = 0 → press")
    print("- 0x61 binary: 01100001 → bit 1 = 0 → press")
    
    # Analyze with new understanding
    print("\n\n2. ANALYSIS WITH NEW UNDERSTANDING:")
    print("-" * 60)
    
    for hex_str in test_data:
        analyze_with_new_understanding(hex_str)
    
    print("\n\nCONCLUSION:")
    print("-" * 60)
    print("The current parser incorrectly identifies all these as 'button_press'")
    print("However, the additional data clearly shows:")
    print("- First packet: state=0x01 (PRESS)")
    print("- Following packets: state=0x02 (RELEASE)")
    print("\nThe parser needs to be updated to:")
    print("1. Handle message type 0x10 differently from type 0x08")
    print("2. Use the additional state byte for press/release detection")
    print("3. Or recognize the action value pattern (0x60→0x61 indicates press→release)")

if __name__ == "__main__":
    main()