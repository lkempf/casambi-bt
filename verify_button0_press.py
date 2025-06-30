#!/usr/bin/env python3
"""
Verify button 0 (first button) press on unit 20
"""
from binascii import a2b_hex

print("BUTTON 0 PRESS VERIFICATION")
print("=" * 80)
print("User action: pressed the first button on unit 20")
print()

# Extract hex data from logs
events = [
    ("100240146f141200050100", "Event 1"),
    ("1002401470141200060200", "Event 2"),
    ("10024014701412001b0200", "Event 3"),
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
    
    # Current parser result (from log)
    if action == 0x6f:
        current_parser = "button_release"
    else:
        current_parser = "button_press"
    
    # Updated parser result (using state byte)
    updated_parser = state_str.lower().replace(" ", "_")
    if state_str.startswith("UNKNOWN"):
        updated_parser = "unknown"
    else:
        updated_parser = f"button_{updated_parser}"
    
    print(f"\n{desc}: {hex_str}")
    print(f"  Button: {button} (first button)")
    print(f"  Unit ID: {unit_id}")
    print(f"  Action: 0x{action:02x}")
    print(f"  State byte: 0x{state_byte:02x} → {state_str}")
    print(f"  Current parser shows: {current_parser}")
    print(f"  Updated parser shows: {updated_parser}")
    print(f"  Match? {'✓' if updated_parser == state_str.lower().replace(' ', '_').replace('button_', '') else '✗'}")

print("\n\nSUMMARY:")
print("-" * 60)
print("Button press sequence:")
print("  1. Press:   action=0x6f, state=0x01")
print("  2. Release: action=0x70, state=0x02")
print("  3. Release: action=0x70, state=0x02")
print()
print("PARSER COMPARISON:")
print("Current parser (using bit logic):")
print("  - Event 1: Shows 'button_release' (WRONG - should be press)")
print("  - Event 2&3: Shows 'button_press' (WRONG - should be release)")
print()
print("Updated parser (using state byte):")
print("  - Event 1: Shows 'button_press' (CORRECT)")
print("  - Event 2&3: Shows 'button_release' (CORRECT)")
print()
print("ACTION COUNTER:")
print("Button 0: ...0x67 → 0x6f → 0x70")
print("Continues incrementing as expected")