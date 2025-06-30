#!/usr/bin/env python3
"""
Analyze button press logs from Home Assistant
"""
from binascii import a2b_hex, b2a_hex

# All unique switch event data from logs
switch_events = [
    "1002401459141200090100",  # Button 0 press
    "100240145a1412000a0200",  # Button 0 release
    "100240145a1412000d0200",  # Button 0 release
    "100240145a141200260200",  # Button 0 release
    "100241145e141200090101",  # Button 1 press
    "100241145e1412000c0101",  # Button 1 press
    "100241145f141200090201",  # Button 1 release
    "100241145f141200500201",  # Button 1 release
]

def parse_message(hex_str):
    """Parse a single message using discovered structure"""
    data = a2b_hex(hex_str)
    
    # Header
    msg_type = data[0]
    flags = data[1]
    length_param = data[2]
    
    # Extract length and parameter
    payload_length = ((length_param >> 4) & 0x0F) + 1
    parameter = length_param & 0x0F
    
    # Payload
    payload = data[3:3+payload_length]
    
    return {
        'type': msg_type,
        'flags': flags,
        'parameter': parameter,
        'payload_length': payload_length,
        'payload': payload
    }

def analyze_switch_events():
    print("BUTTON PRESS/RELEASE ANALYSIS FROM LOGS")
    print("=" * 80)
    
    # Group by button
    button_0_events = []
    button_1_events = []
    
    for hex_str in switch_events:
        msg = parse_message(hex_str)
        
        # All are type 0x10 messages
        if msg['type'] == 0x10:
            # For type 0x10, parameter seems to be button number
            if msg['parameter'] == 0:
                button_0_events.append((hex_str, msg))
            elif msg['parameter'] == 1:
                button_1_events.append((hex_str, msg))
    
    # Analyze Button 0
    print("\nBUTTON 0 EVENTS:")
    print("-" * 40)
    for hex_str, msg in button_0_events:
        unit_id = msg['payload'][0]
        action = msg['payload'][1]
        is_release = (action >> 1) & 1
        event = "RELEASE" if is_release else "PRESS"
        
        print(f"{hex_str}")
        print(f"  Type: 0x{msg['type']:02x}, Flags: 0x{msg['flags']:02x}, Button: {msg['parameter']}")
        print(f"  Unit ID: {unit_id} (0x{unit_id:02x})")
        print(f"  Action: 0x{action:02x} - {event}")
        print(f"  Full payload: {b2a_hex(msg['payload']).decode()}")
        if len(msg['payload']) > 2:
            print(f"  Extra data: {b2a_hex(msg['payload'][2:]).decode()}")
        print()
    
    # Analyze Button 1
    print("\nBUTTON 1 EVENTS:")
    print("-" * 40)
    for hex_str, msg in button_1_events:
        unit_id = msg['payload'][0]
        action = msg['payload'][1]
        is_release = (action >> 1) & 1
        event = "RELEASE" if is_release else "PRESS"
        
        print(f"{hex_str}")
        print(f"  Type: 0x{msg['type']:02x}, Flags: 0x{msg['flags']:02x}, Button: {msg['parameter']}")
        print(f"  Unit ID: {unit_id} (0x{unit_id:02x})")
        print(f"  Action: 0x{action:02x} - {event}")
        print(f"  Full payload: {b2a_hex(msg['payload']).decode()}")
        if len(msg['payload']) > 2:
            print(f"  Extra data: {b2a_hex(msg['payload'][2:]).decode()}")
        print()
    
    # Compare patterns
    print("\nPATTERN ANALYSIS:")
    print("-" * 40)
    
    # Extract sequence numbers (byte at position 8)
    print("\nSequence/Counter values (byte position 8):")
    for i, hex_str in enumerate(switch_events):
        data = a2b_hex(hex_str)
        if len(data) > 8:
            seq = data[8]
            msg = parse_message(hex_str)
            button = msg['parameter']
            action = msg['payload'][1]
            is_release = (action >> 1) & 1
            event = "release" if is_release else "press"
            print(f"  Event {i+1}: Button {button} {event:7} - seq: 0x{seq:02x} ({seq})")
    
    # Check the changing values
    print("\nChanging values in extra data:")
    for hex_str in switch_events:
        msg = parse_message(hex_str)
        if len(msg['payload']) > 4:
            extra = msg['payload'][4]  # The changing byte
            button = msg['parameter']
            action = msg['payload'][1]
            is_release = (action >> 1) & 1
            event = "release" if is_release else "press"
            print(f"  Button {button} {event:7} - byte 4: 0x{extra:02x} ({extra})")

if __name__ == "__main__":
    analyze_switch_events()