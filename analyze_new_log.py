#!/usr/bin/env python3
"""
Analyze new log data - press then release button 1 on unit 20
"""
from binascii import a2b_hex, b2a_hex

# New log data
new_events = [
    ("10024114621412000c0101", "First event"),
    ("10024114631412000b0201", "Second event"),
    ("1002411463141200180201", "Third event"),
]

print("NEW LOG ANALYSIS - Press then release button 1 on unit 20")
print("=" * 80)

for hex_str, desc in new_events:
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
        state_str = "PRESS" if state == 0x01 else "RELEASE" if state == 0x02 else "UNKNOWN"
    else:
        state_str = "NO DATA"
    
    print(f"  Type: 0x{msg_type:02x}, Button: {button}, Unit: {unit_id}")
    print(f"  Action: 0x{action:02x}")
    print(f"  State byte: 0x{state:02x} → {state_str}")
    
print("\n\nOBSERVATIONS:")
print("-" * 60)
print("1. ALL packets show action 0x62 or 0x63 (which are 'release' values)")
print("2. First packet has state 0x01 (PRESS)")
print("3. Following packets have state 0x02 (RELEASE)")
print("\nThis suggests:")
print("- No separate 'press' packet was captured")
print("- The first packet might be a 'button pressed and released' notification")
print("- Or the press packet was missed in the logs")

print("\n\nACTION VALUE PATTERN:")
print("-" * 60)
print("Previous logs:")
print("  Button 0: 0x59 (press) → 0x5a (release)")
print("  Button 1: 0x5e/0x60 (press) → 0x5f/0x61 (release)")
print("\nThis log:")
print("  Button 1: 0x62 → 0x63")
print("\nThe action values seem to increment with each button press/release cycle!")

# Compare with previous patterns
print("\n\nCOMPARING ACTION VALUES:")
print("-" * 60)
previous_button1_actions = [0x5e, 0x5f, 0x60, 0x61]
current_actions = [0x62, 0x63]
all_actions = previous_button1_actions + current_actions

print("Button 1 action sequence across logs:")
for i, action in enumerate(all_actions):
    binary = format(action, '08b')
    print(f"  0x{action:02x} ({action}) = {binary}")

print("\nPattern: The action value appears to be a counter that increments")
print("with each state change (press or release)")

print("\n\nCORRECT INTERPRETATION:")
print("-" * 60)
print("The state byte (position -2) is the reliable indicator:")
print("  0x01 = PRESS")
print("  0x02 = RELEASE")
print("\nThe current parser using bit 1 of action byte is incorrect for type 0x10.")
print("We should rely on the state byte instead.")