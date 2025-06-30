#!/usr/bin/env python3
"""
Test updated parser implementation
"""
from binascii import a2b_hex, b2a_hex

# Test data from logs
test_cases = [
    # From the specific log entries
    ("1002411460141200070101", "Button 1 press on unit 20"),
    ("1002411461141200060201", "Button 1 release on unit 20"),
    ("1002411461141200090201", "Button 1 release on unit 20"),
    ("10024114611412003a0201", "Button 1 release on unit 20"),
    
    # From earlier logs (type 0x08)
    ("0803201f851f06000599000229002a0f001f060003", "Button 0 press on unit 31"),
    ("0803201f8a1f060005190010", "Button 0 release on unit 31"),
]

def simulate_updated_parser(hex_str, description):
    """Simulate the updated parser logic"""
    data = a2b_hex(hex_str)
    print(f"\n{description}")
    print(f"Data: {hex_str}")
    print("-" * 60)
    
    pos = 0
    msg_num = 1
    
    while pos <= len(data) - 3:
        # Parse message header
        message_type = data[pos]
        flags = data[pos + 1]
        length = ((data[pos + 2] >> 4) & 15) + 1
        parameter = data[pos + 2] & 15
        oldPos = pos
        pos += 3
        
        # Check if we have enough data
        if pos + length > len(data):
            print(f"Message {msg_num}: Incomplete (type 0x{message_type:02x})")
            break
        
        # Extract payload
        payload = data[pos : pos + length]
        pos += length
        
        print(f"Message {msg_num}:")
        print(f"  Type: 0x{message_type:02x}, Flags: 0x{flags:02x}, Length: {length}, Param: {parameter}")
        
        # Process switch messages
        if message_type in [0x08, 0x10]:
            unit_id = payload[0]
            action = payload[1] if len(payload) > 1 else None
            extra_data = payload[2:] if len(payload) > 2 else b''
            
            event_string = "unknown"
            
            if message_type == 0x08:
                # Type 0x08: Use bit 1 of action
                if action is not None:
                    is_release = (action >> 1) & 1
                    event_string = "button_release" if is_release else "button_press"
            elif message_type == 0x10:
                # Type 0x10: Check additional state byte
                additional_data_pos = oldPos + 3 + len(payload)
                if additional_data_pos + 2 < len(data):
                    state_byte = data[additional_data_pos + 1]
                    if state_byte == 0x01:
                        event_string = "button_press"
                    elif state_byte == 0x02:
                        event_string = "button_release"
                else:
                    # Fallback to action pattern
                    if action in [0x59, 0x5e, 0x60]:
                        event_string = "button_press"
                    elif action in [0x5a, 0x5f, 0x61]:
                        event_string = "button_release"
            
            action_str = f"0x{action:02x}" if action is not None else "None"
            print(f"  → Switch event: button={parameter}, unit_id={unit_id}, "
                  f"action={action_str} ({event_string})")
            
            if len(extra_data) > 0:
                print(f"  → Extra data: {b2a_hex(extra_data).decode()}")
        else:
            print(f"  → Other message type: payload={b2a_hex(payload).decode()}")
        
        msg_num += 1

def main():
    print("TESTING UPDATED PARSER IMPLEMENTATION")
    print("=" * 80)
    
    for hex_str, description in test_cases:
        simulate_updated_parser(hex_str, description)

if __name__ == "__main__":
    main()