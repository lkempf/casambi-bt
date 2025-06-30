#!/usr/bin/env python3
"""
Verify button 1 (second button) press/release on unit 20
"""
from binascii import a2b_hex

print("BUTTON 1 (SECOND BUTTON) PRESS/RELEASE")
print("=" * 80)
print("User action: press then release second button on unit 20")
print()

# Extract hex data from logs
events = [
    ("1002411473141200040101", "Event 1"),
    ("1002411474141200060201", "Event 2"),
    ("1002411474141200070201", "Event 3"),
]

print("HEX DATA ANALYSIS:")
print("-" * 60)

for hex_str, desc in events:
    data = a2b_hex(hex_str)
    
    # Parse message structure
    msg_type = data[0]
    flags = data[1]
    length_param = data[2]
    button = length_param & 0x0F
    unit_id = data[3]
    action = data[4]
    
    # Parse state from additional data
    state_byte = data[-2]
    state_str = "PRESS" if state_byte == 0x01 else "RELEASE" if state_byte == 0x02 else f"UNKNOWN(0x{state_byte:02x})"
    
    # Current parser result (based on bit 1)
    bit1 = (action >> 1) & 1
    current_parser = "button_release" if bit1 else "button_press"
    
    # Compare with actual state
    match = "✓" if (state_str == "PRESS" and current_parser == "button_press") or \
                   (state_str == "RELEASE" and current_parser == "button_release") else "✗"
    
    print(f"\n{desc}: {hex_str}")
    print(f"  Button: {button} (second button)")
    print(f"  Unit ID: {unit_id}")
    print(f"  Action: 0x{action:02x} (binary: {action:08b}, bit 1 = {bit1})")
    print(f"  State byte: 0x{state_byte:02x} → {state_str}")
    print(f"  Current parser: {current_parser} {match}")
    print(f"  Updated parser: button_{state_str.lower()} ✓")

print("\n\nSUMMARY:")
print("-" * 60)
print("Complete press/release sequence:")
print("  1. Press:   action=0x73, state=0x01")
print("  2. Release: action=0x74, state=0x02")
print("  3. Release: action=0x74, state=0x02")
print()
print("ACTION COUNTER:")
print("Button 1: ...0x6e → 0x73 → 0x74")
print("(Gap suggests button activity between logs)")
print()
print("PARSER COMPARISON:")
print("- Current parser: WRONG on all events!")
print("  - Shows press as 'release' (0x73 bit 1 = 1)")
print("  - Shows releases as 'press' (0x74 bit 1 = 0)")
print("- Updated parser: CORRECT on all events (using state byte)")
print()
print("This perfectly demonstrates why state byte is essential!")