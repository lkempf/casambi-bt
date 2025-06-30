#!/usr/bin/env python3
"""
Verify button 1 (second button) press and release on unit 20
"""
from binascii import a2b_hex

print("BUTTON 1 (SECOND BUTTON) PRESS/RELEASE VERIFICATION")
print("=" * 80)
print("User action: press then release second button (button 1) on unit 20")
print()

events = [
    ("1002411469141200100201", "Event 1"),
    ("10024114691412001a0201", "Event 2"),
    ("1002411469141200390201", "Event 3"),
    ("1002411469141200c20201", "Event 4"),
]

print("LOG ANALYSIS:")
print("-" * 60)

for hex_str, desc in events:
    data = a2b_hex(hex_str)
    
    # Parse message
    msg_type = data[0]
    flags = data[1]
    length_param = data[2]
    button = length_param & 0x0F
    unit_id = data[3]
    action = data[4]
    
    # Parse state from additional data
    state_byte = data[-2]
    state_str = "PRESS" if state_byte == 0x01 else "RELEASE" if state_byte == 0x02 else f"UNKNOWN(0x{state_byte:02x})"
    
    # What current parser shows
    current_parser = "button_press"  # All show as press because action=0x69
    
    print(f"\n{desc}: {hex_str}")
    print(f"  Button: {button} (second button)")
    print(f"  Unit ID: {unit_id}")
    print(f"  Action: 0x{action:02x}")
    print(f"  State byte: 0x{state_byte:02x} → {state_str}")
    print(f"  Current parser shows: {current_parser}")
    print(f"  Should be: {state_str}")

print("\n\nSUMMARY:")
print("-" * 60)
print("UNEXPECTED PATTERN!")
print("All 4 events have:")
print("  - Same action: 0x69")
print("  - Same state: 0x02 (RELEASE)")
print()
print("This suggests:")
print("1. The press event was not captured, OR")
print("2. This was a very quick tap (press+release), OR")
print("3. The button was already pressed when logging started")
print()
print("ACTION COUNTER STATUS:")
print("Button 1: ...0x63 → 0x69 (jumped from 0x63 to 0x69)")
print("Button 0: ...0x67")
print()
print("The gap in action values (0x64-0x68 missing) suggests")
print("some button events occurred between the previous logs")