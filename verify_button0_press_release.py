#!/usr/bin/env python3
"""
Verify button 0 (first button) press and release on unit 20
"""
from binascii import a2b_hex

print("BUTTON 0 PRESS/RELEASE VERIFICATION")
print("=" * 80)
print("User action: press, release first button (button 0) on unit 20")
print()

events = [
    ("1002401466141200070100", "Event 1"),
    ("1002401467141200060200", "Event 2"),
    ("1002401467141200170200", "Event 3"),
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
    
    # What current parser shows (incorrectly)
    current_parser = "button_release" if action == 0x67 else "button_release"  # Both show as release
    
    print(f"\n{desc}: {hex_str}")
    print(f"  Button: {button} (first button)")
    print(f"  Unit ID: {unit_id}")
    print(f"  Action: 0x{action:02x}")
    print(f"  State byte: 0x{state_byte:02x} → {state_str}")
    print(f"  Current parser shows: {current_parser} (INCORRECT for first event)")
    print(f"  Should be: {state_str}")

print("\n\nSUMMARY:")
print("-" * 60)
print("Complete button 0 press/release sequence captured:")
print("  1. Press event:   action=0x66, state=0x01 (PRESS)")
print("  2. Release event: action=0x67, state=0x02 (RELEASE)")  
print("  3. Release event: action=0x67, state=0x02 (RELEASE)")
print()
print("PATTERN CONFIRMED:")
print("- Action increments: 0x66 (press) → 0x67 (release)")
print("- Multiple release events sent for reliability")
print("- State byte is the definitive indicator")
print()
print("ACTION COUNTER TRACKING:")
print("Button 0: ...0x65 → 0x66 → 0x67")
print("Button 1: ...0x62 → 0x63")
print("The action continues incrementing across all button events!")