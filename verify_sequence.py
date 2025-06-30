#!/usr/bin/env python3
"""
Verify the sequence number hypothesis
"""
from binascii import a2b_hex

def analyze_changing_bytes():
    print("SEQUENCE NUMBER ANALYSIS")
    print("=" * 80)
    
    # Extract the changing bytes from type 0x06 messages
    type_06_messages = [
        ('packet 1', '06000599', 0x05),
        ('packet 4', '06000c99', 0x0c),
        ('packet 5', '060005190010', 0x05),
        ('packet 6', '06000e190010', 0x0e),
        ('packet 7', '060015190010', 0x15),
    ]
    
    print("\nType 0x06 messages with changing byte:")
    for name, hex_str, changing_byte in type_06_messages:
        print(f"  {name}: {hex_str} - byte position 3 = 0x{changing_byte:02x} ({changing_byte})")
    
    print("\nSequence: 5, 12, 5, 14, 21")
    print("Differences: +7, -7, +9, +7")
    
    # Also check byte 8 in button events
    print("\n\nByte 8 in button events (0803201f...):")
    button_events = [
        ('Press 1', '0803201f851f06000599000229002a0f001f060003', 8),
        ('Press 2', '0803201f851f06000c99000229002a02001f06000b', 8),
        ('Release 1', '0803201f8a1f060005190010', 8),
        ('Release 2', '0803201f8a1f06000e190010', 8),
        ('Release 3', '0803201f8a1f060015190010', 8),
    ]
    
    for name, hex_str, pos in button_events:
        data = a2b_hex(hex_str)
        if len(data) > pos:
            print(f"  {name}: byte {pos} = 0x{data[pos]:02x} ({data[pos]})")
    
    print("\nSequence in button events: 5, 12, 5, 14, 21")
    print("This matches the type 0x06 message sequence!")
    
    # Check if it could be a counter
    print("\n\nCOUNTER HYPOTHESIS:")
    values = [5, 12, 5, 14, 21]
    print(f"Values: {values}")
    print(f"In binary: {[bin(v) for v in values]}")
    print(f"As 5-bit values: {[v & 0x1F for v in values]}")
    
    # Check modulo patterns
    for mod in [8, 16, 32]:
        print(f"\nModulo {mod}: {[v % mod for v in values]}")

def proposed_structure():
    print("\n\nPROPOSED MESSAGE STRUCTURE:")
    print("=" * 80)
    
    print("""
Based on analysis, the protocol structure appears to be:

MESSAGE FORMAT:
  Byte 0: Message Type
  Byte 1: Flags/Status
  Byte 2: [Length-1:4][Parameter:4] (high nibble = length-1, low nibble = parameter)
  Byte 3+: Payload (variable length based on byte 2 high nibble)

MESSAGE TYPES:
  0x08: Switch/Button Event
    - Parameter (byte 2 low): Button number
    - Payload[0]: Unit ID
    - Payload[1]: Action (bit 1 indicates press/release)
    - Payload[2]: Additional data (often 0x1f)
    
  0x29: Unit State Update
    - Parameter (byte 2 low): Usually 0x0a (10)
    - Payload[0]: Unit ID
    - Payload[1]: State value
    - Payload[2]: Additional data (often 0x1f)
    
  0x06: Sequence/Status Message
    - Parameter (byte 2 low): Varies
    - Payload[0]: Sequence number or status
    
  0x00: General Status
  0x02: Short Status
  0x10: Extended Event

OBSERVATIONS:
  1. The byte at position 8 in long packets appears to be a sequence number
  2. This same value appears in type 0x06 messages
  3. Multiple messages are concatenated in a single BLE packet
  4. Button events are sent multiple times for reliability
  5. Related units send updates when a button is pressed
""")

if __name__ == "__main__":
    analyze_changing_bytes()
    proposed_structure()