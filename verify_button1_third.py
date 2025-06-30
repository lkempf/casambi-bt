#!/usr/bin/env python3
"""
Verify button 1 (second button) press and release - third time
"""
from binascii import a2b_hex

print("BUTTON 1 PRESS/RELEASE - THIRD OCCURRENCE")
print("=" * 80)
print("User action: press then release second button (button 1) on unit 20")
print()

# Extract hex data from logs
events = [
    ("100241146d141200080101", "Event 1"),
    ("100241146e1412000b0201", "Event 2"),
    ("100241146e141200320201", "Event 3"),
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
    
    # Parse state from additional data (last 3 bytes)
    state_byte = data[-2]  # Second to last byte
    state_str = "PRESS" if state_byte == 0x01 else "RELEASE" if state_byte == 0x02 else f"UNKNOWN(0x{state_byte:02x})"
    
    print(f"\n{desc}: {hex_str}")
    print(f"  Button: {button}")
    print(f"  Unit ID: {unit_id}")
    print(f"  Action: 0x{action:02x}")
    print(f"  State byte: 0x{state_byte:02x} → {state_str}")

print("\n\nSUMMARY:")
print("-" * 60)
print("Complete press/release sequence:")
print("  1. Press:   action=0x6d, state=0x01")
print("  2. Release: action=0x6e, state=0x02")
print("  3. Release: action=0x6e, state=0x02")
print()
print("ACTION COUNTER PROGRESSION:")
print("Previous: ...0x6b → 0x6c")
print("Current:  0x6d → 0x6e")
print()
print("PATTERN CONFIRMATION:")
print("- Action increments with each state change")
print("- State byte reliably indicates press (0x01) vs release (0x02)")
print("- Multiple release packets for reliability (2 in this case)")
print()
print("The updated parser using state bytes will correctly identify")
print("these events, while the current parser gives incorrect results.")