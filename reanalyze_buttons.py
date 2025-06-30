#!/usr/bin/env python3
"""
Re-analyze with correct button indexing understanding
"""
from binascii import a2b_hex

print("BUTTON INDEXING CLARIFICATION")
print("=" * 80)
print("User's naming: button 0 = first button, button 1 = second button")
print("Parameter field in message uses same 0-based indexing")
print()

# Previous logs analysis
print("PREVIOUS LOGS:")
print("-" * 40)
print("'Press then release button 0 on unit 31':")
print("  → Messages had parameter=0 (correct)")
print()
print("'Press then release button 1 on unit 20':")
print("  → Messages had parameter=1 (correct)")
print()

# Current log analysis
print("CURRENT LOG ANALYSIS:")
print("-" * 40)
print("User said: 'press then release button 0 on unit 20'")
print("But the log shows:")

events = [
    ("10024114621412000c0101", "First event"),
    ("10024114631412000b0201", "Second event"), 
    ("1002411463141200180201", "Third event"),
    ("1002401465141200020200", "Fourth event"),
    ("1002401465141200490200", "Fifth event"),
]

for hex_str, desc in events:
    data = a2b_hex(hex_str)
    button_param = data[2] & 0x0F
    state = data[-2]
    action = data[4]
    
    state_str = "PRESS" if state == 0x01 else "RELEASE" if state == 0x02 else "UNKNOWN"
    print(f"\n{desc}:")
    print(f"  Button parameter: {button_param}")
    print(f"  Action: 0x{action:02x}, State: {state_str}")

print("\n\nCONCLUSION:")
print("-" * 60)
print("The log actually contains TWO button press/release sequences:")
print("1. Button 1 (second button): Press + 2 Release events")
print("2. Button 0 (first button): 2 Release events only (press not captured)")
print("\nThis explains why we see parameter=1 followed by parameter=0")
print("The user's button indexing is consistent with the protocol!")