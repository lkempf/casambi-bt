#!/usr/bin/env python3
"""
Verify button 0 press/release with mixed order events
"""
from binascii import a2b_hex

print("BUTTON 0 PRESS/RELEASE - MIXED ORDER VERIFICATION")
print("=" * 80)
print("User action: press then release first button on unit 20")
print("Note: Events may be captured out of order!")
print()

# Extract hex data from logs
events = [
    ("10024014711412000c0100", "Event 1"),
    ("1002401471141200110100", "Event 2"),
    ("1002401472141200050200", "Event 3"),
]

print("HEX DATA ANALYSIS:")
print("-" * 60)

press_events = []
release_events = []

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
    if action == 0x71:
        current_parser = "button_press"
    else:
        current_parser = "button_release"
    
    print(f"\n{desc}: {hex_str}")
    print(f"  Button: {button} (first button)")
    print(f"  Unit ID: {unit_id}")
    print(f"  Action: 0x{action:02x}")
    print(f"  State byte: 0x{state_byte:02x} → {state_str}")
    print(f"  Current parser: {current_parser}")
    print(f"  Updated parser: button_{state_str.lower()}")
    
    # Collect events by type
    if state_byte == 0x01:
        press_events.append((desc, action))
    elif state_byte == 0x02:
        release_events.append((desc, action))

print("\n\nSUMMARY:")
print("-" * 60)
print(f"Press events: {len(press_events)}")
for desc, action in press_events:
    print(f"  - {desc}: action=0x{action:02x}")

print(f"\nRelease events: {len(release_events)}")
for desc, action in release_events:
    print(f"  - {desc}: action=0x{action:02x}")

print("\nOBSERVATION:")
print("- 2 press events with action=0x71")
print("- 1 release event with action=0x72")
print()
print("INTERESTING PATTERN:")
print("The press event was sent TWICE before the release!")
print("This could be:")
print("1. Extra reliability for press events")
print("2. A long press generating multiple press packets")
print("3. Network conditions causing duplicate transmission")
print()
print("ACTION COUNTER:")
print("Button 0: ...0x70 → 0x71 → 0x72")
print()
print("PARSER ACCURACY:")
print("- Current parser: Accidentally correct (0x71 bit 1=0→press, 0x72 bit 1=1→release)")
print("- Updated parser: Always correct (using state byte)")