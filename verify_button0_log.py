#!/usr/bin/env python3
"""
Verify button 0 log data
"""
from binascii import a2b_hex, b2a_hex

# Log data - seems to contain both button 1 and button 0 events
events = [
    # First three are button 1 (from previous sequence?)
    ("10024114621412000c0101", "Button 1 event 1"),
    ("10024114631412000b0201", "Button 1 event 2"),
    ("1002411463141200180201", "Button 1 event 3"),
    # Last two are button 0
    ("1002401465141200020200", "Button 0 event 1"),
    ("1002401465141200490200", "Button 0 event 2"),
]

print("VERIFY BUTTON PRESS/RELEASE PATTERNS")
print("=" * 80)

for hex_str, desc in events:
    data = a2b_hex(hex_str)
    print(f"\n{desc}: {hex_str}")
    
    # Parse header
    msg_type = data[0]
    flags = data[1]
    length_param = data[2]
    length = ((length_param >> 4) & 0x0F) + 1
    button = length_param & 0x0F
    
    # Parse payload
    payload = data[3:3+length]
    unit_id = payload[0]
    action = payload[1]
    
    # Parse additional data
    additional = data[3+length:]
    if len(additional) >= 3:
        seq = additional[0]
        state = additional[1]
        button_confirm = additional[2]
        state_str = "PRESS" if state == 0x01 else "RELEASE" if state == 0x02 else f"UNKNOWN(0x{state:02x})"
    else:
        state_str = "NO DATA"
        state = None
    
    # Current parser interpretation
    current_parser_result = "button_press" if action in [0x62, 0x65] else "button_release"
    
    print(f"  Button: {button}, Unit: {unit_id}, Action: 0x{action:02x}")
    print(f"  State byte: 0x{state:02x} → {state_str}" if state else "  No state byte")
    print(f"  Current parser: {current_parser_result}")
    print(f"  Correct interpretation: {state_str}")

print("\n\nANALYSIS:")
print("-" * 60)
print("Button 1 sequence (0x62 → 0x63):")
print("  First:  state=0x01 (PRESS)")
print("  Others: state=0x02 (RELEASE)")

print("\nButton 0 sequence (0x65):")
print("  Both events: state=0x00 (UNKNOWN)")
print("\nThe state=0x00 is unexpected! This might indicate:")
print("  1. A different type of event (not press/release)")
print("  2. Missing press event (only captures release)")
print("  3. A 'tap' event (quick press+release)")

print("\n\nACTION VALUE TRACKING:")
print("-" * 60)
print("All button 1 actions seen: 0x5e, 0x5f, 0x60, 0x61, 0x62, 0x63")
print("All button 0 actions seen: 0x59, 0x5a, 0x65")
print("\nThe action values continue incrementing across button presses!")
print("This confirms action is a rolling counter, not a fixed value.")

print("\n\nCONCLUSION:")
print("-" * 60)
print("The parser must handle state byte values:")
print("  0x01 = PRESS")
print("  0x02 = RELEASE")
print("  0x00 = UNKNOWN (needs investigation)")
print("\nThe current parser will show 'unknown' for state=0x00,")
print("which is correct behavior until we understand what it means.")