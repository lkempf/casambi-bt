#!/usr/bin/env python3
"""
Analyze button press logs from Home Assistant - Fixed version
"""
from binascii import a2b_hex, b2a_hex

# All unique switch event data from logs with annotations
switch_events = [
    ("1002401459141200090100", "Button 0 first event"),
    ("100240145a1412000a0200", "Button 0 second event"),
    ("100240145a1412000d0200", "Button 0 third event"),
    ("100240145a141200260200", "Button 0 fourth event"),
    ("100241145e141200090101", "Button 1 first event"),
    ("100241145e1412000c0101", "Button 1 second event"),
    ("100241145f141200090201", "Button 1 third event"),
    ("100241145f141200500201", "Button 1 fourth event"),
]

def analyze_detailed():
    print("DETAILED BUTTON EVENT ANALYSIS")
    print("=" * 80)
    
    for hex_str, description in switch_events:
        data = a2b_hex(hex_str)
        print(f"\n{description}: {hex_str}")
        print(f"  Raw bytes: {' '.join(f'{b:02x}' for b in data)}")
        
        # Parse header
        msg_type = data[0]
        flags = data[1]
        length_param = data[2]
        payload_length = ((length_param >> 4) & 0x0F) + 1
        parameter = length_param & 0x0F
        
        print(f"  Header: type=0x{msg_type:02x}, flags=0x{flags:02x}, length={payload_length}, param={parameter}")
        
        # Parse payload
        payload = data[3:3+payload_length]
        print(f"  Payload ({len(payload)} bytes): {b2a_hex(payload).decode()}")
        
        if len(payload) >= 2:
            unit_id = payload[0]
            action = payload[1]
            print(f"    Unit ID: {unit_id} (0x{unit_id:02x})")
            print(f"    Action: 0x{action:02x} (binary: {action:08b})")
            
            # Check different interpretations of action
            is_release_bit1 = (action >> 1) & 1
            is_release_bit0 = action & 1
            print(f"    If bit 1 is release flag: {'RELEASE' if is_release_bit1 else 'PRESS'}")
            print(f"    If bit 0 is release flag: {'RELEASE' if is_release_bit0 else 'PRESS'}")
        
        # Check remaining data
        if len(data) > 3 + payload_length:
            remaining = data[3 + payload_length:]
            print(f"  Remaining data: {b2a_hex(remaining).decode()}")
    
    # Pattern analysis
    print("\n\nPATTERN OBSERVATIONS:")
    print("=" * 60)
    
    # Action values
    print("\nAction values by button:")
    print("Button 0: 0x59 (first), 0x5a (repeated 3x)")
    print("Button 1: 0x5e (repeated 2x), 0x5f (repeated 2x)")
    
    print("\nAction values in binary:")
    for action, desc in [(0x59, "Button 0 first"), (0x5a, "Button 0 later"), 
                         (0x5e, "Button 1 first"), (0x5f, "Button 1 later")]:
        print(f"  0x{action:02x} = {action:08b} ({desc})")
    
    print("\nPossible interpretations:")
    print("1. Lower 6 bits might be a counter/sequence")
    print("2. Upper bits might be flags")
    print("3. The pattern 0x59->0x5a and 0x5e->0x5f suggests increment")
    
    # Check if it's related to press/release timing
    print("\nTiming pattern hypothesis:")
    print("- First packet: Initial press/release notification")
    print("- Following packets: Confirmations or state updates")
    
    # The last bytes
    print("\nLast 3 bytes of each message:")
    for hex_str, desc in switch_events:
        data = a2b_hex(hex_str)
        last_bytes = data[-3:]
        button = (data[2] & 0x0F)
        print(f"  Button {button}: {b2a_hex(last_bytes).decode()} - {desc}")

if __name__ == "__main__":
    analyze_detailed()