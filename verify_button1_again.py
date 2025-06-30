#!/usr/bin/env python3
"""
Verify button 1 (second button) press and release again
"""
from binascii import a2b_hex

print("BUTTON 1 PRESS/RELEASE - SECOND OCCURRENCE")
print("=" * 80)
print("User action: press then release second button (button 1) on unit 20 AGAIN")
print()

events = [
    ("100241146b1412000b0101", "Event 1"),
    ("100241146c141200090201", "Event 2"),
    ("100241146c141200440201", "Event 3"),
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
    
    # What current parser shows (using bit logic incorrectly)
    # 0x6b = 01101011, bit 1 = 1 → release
    # 0x6c = 01101100, bit 1 = 0 → press
    if action == 0x6b:
        current_parser = "button_release"
    else:
        current_parser = "button_press"
    
    print(f"\n{desc}: {hex_str}")
    print(f"  Button: {button} (second button)")
    print(f"  Unit ID: {unit_id}")
    print(f"  Action: 0x{action:02x} (binary: {action:08b})")
    print(f"  State byte: 0x{state_byte:02x} → {state_str}")
    print(f"  Current parser shows: {current_parser}")
    print(f"  Should be: {state_str}")

print("\n\nSUMMARY:")
print("-" * 60)
print("COMPLETE SEQUENCE CAPTURED!")
print("  1. Press event:   action=0x6b, state=0x01 (PRESS)")
print("  2. Release event: action=0x6c, state=0x02 (RELEASE)")
print("  3. Release event: action=0x6c, state=0x02 (RELEASE)")
print()
print("ACTION COUNTER:")
print("Previous: 0x69")
print("Now: 0x6b → 0x6c")
print("Confirms continuous increment: ...0x69 → 0x6a (missed) → 0x6b → 0x6c")
print()
print("IMPORTANT FINDING:")
print("The current parser accidentally gets the first event correct!")
print("- 0x6b has bit 1 = 1, so parser shows 'release'")
print("- But state byte = 0x01 (PRESS)")
print("This proves bit 1 logic is WRONG for type 0x10 messages!")