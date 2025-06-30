#!/usr/bin/env python3
"""
Protocol findings based on analysis
"""
from binascii import a2b_hex

def analyze_structure():
    print("PROTOCOL STRUCTURE FINDINGS")
    print("=" * 80)
    
    # Key finding 1: The third byte's high nibble indicates payload length
    print("\n1. MESSAGE STRUCTURE:")
    print("   Byte 0: Message type")
    print("   Byte 1: Flags/status")
    print("   Byte 2: High nibble = (payload_length - 1), Low nibble = parameter")
    print("   Bytes 3+: Payload (length determined by high nibble + 1)")
    
    # Key finding 2: Messages are concatenated in packets
    print("\n2. PACKET STRUCTURE:")
    print("   Packets contain multiple concatenated messages")
    print("   Each message is self-contained with its length encoded")
    
    # Key finding 3: Specific message types observed
    print("\n3. MESSAGE TYPES OBSERVED:")
    print("   Type 0x08: Button events (unit 31)")
    print("   Type 0x29: Related unit updates") 
    print("   Type 0x10: Different sensor type")
    print("   Type 0x06: Short status messages")
    print("   Type 0x00: Status/state messages")
    print("   Type 0x02: Unknown short messages")
    
    # Test the structure
    print("\n4. TESTING STRUCTURE ON KNOWN DATA:")
    test_packets = [
        ('Button press packet', '0803201f851f06000599000229002a0f001f060003'),
        ('Button release packet', '0803201f8a1f060005190010'),
        ('Type 0x29 packet', '29002a08001f060003'),
        ('Type 0x10 packet', '1002430a981f120002020b'),
    ]
    
    for name, hex_str in test_packets:
        print(f"\n{name}: {hex_str}")
        data = a2b_hex(hex_str)
        parse_packet(data)

def parse_packet(data):
    """Parse a packet into individual messages using discovered structure"""
    pos = 0
    msg_num = 1
    
    while pos < len(data) and pos + 3 <= len(data):
        # Extract header
        msg_type = data[pos]
        flags = data[pos + 1]
        length_byte = data[pos + 2]
        
        # Calculate payload length
        payload_length = ((length_byte >> 4) & 0x0F) + 1
        parameter = length_byte & 0x0F
        
        # Check if we have enough data
        if pos + 3 + payload_length > len(data):
            print(f"  Message {msg_num}: Incomplete (need {payload_length} bytes, have {len(data) - pos - 3})")
            break
        
        # Extract payload
        payload = data[pos + 3 : pos + 3 + payload_length]
        
        print(f"  Message {msg_num}:")
        print(f"    Type: 0x{msg_type:02x}")
        print(f"    Flags: 0x{flags:02x}")
        print(f"    Payload length: {payload_length}")
        print(f"    Parameter: {parameter}")
        print(f"    Payload: {payload.hex()}")
        
        # Interpret based on message type
        if msg_type == 0x08:
            interpret_type_08(payload, parameter, flags)
        elif msg_type == 0x29:
            interpret_type_29(payload, parameter, flags)
        elif msg_type == 0x10:
            interpret_type_10(payload, parameter, flags)
        
        pos += 3 + payload_length
        msg_num += 1

def interpret_type_08(payload, parameter, flags):
    """Interpret type 0x08 messages - button events"""
    if len(payload) >= 2:
        unit_id = payload[0]
        action = payload[1]
        
        # Bit 1 of action determines press/release
        is_release = (action >> 1) & 1
        event = "release" if is_release else "press"
        
        print(f"    → Button event: unit {unit_id}, button {parameter}, {event} (action 0x{action:02x})")
        
        if len(payload) > 2:
            print(f"    → Additional data: {payload[2:].hex()}")

def interpret_type_29(payload, parameter, flags):
    """Interpret type 0x29 messages - related unit updates"""
    if len(payload) >= 2:
        unit_id = payload[0]
        value = payload[1]
        print(f"    → Unit update: unit {unit_id}, parameter {parameter}, value 0x{value:02x}")
        
        if len(payload) > 2:
            print(f"    → Additional data: {payload[2:].hex()}")

def interpret_type_10(payload, parameter, flags):
    """Interpret type 0x10 messages"""
    if len(payload) >= 2:
        unit_id = payload[0]
        value = payload[1]
        print(f"    → Type 0x10 event: unit {unit_id}, parameter {parameter}, value 0x{value:02x}")
        
        if len(payload) > 2:
            print(f"    → Additional data: {payload[2:].hex()}")

def analyze_button_sequence():
    print("\n\n5. BUTTON PRESS/RELEASE SEQUENCE ANALYSIS:")
    print("-" * 60)
    
    # The sequence of events for a single button press/release
    events = [
        ('0803201f851f', 'Button 0 PRESS on unit 31'),
        ('06000599', 'Type 0x06 message'),
        ('000229002a0f', 'Type 0x00 message'),
        ('001f0600', 'Type 0x00 message'),
        # Note: byte 0x03 remains - might be padding or part of next packet
        
        ('29002a08001f', 'Unit 8 update'),
        ('060003', 'Type 0x06 message (incomplete)'),
        
        ('29002a05001f', 'Unit 5 update'),
        ('060009', 'Type 0x06 message (incomplete)'),
        
        ('0803201f851f', 'Button 0 PRESS on unit 31 (duplicate)'),
        ('06000c99', 'Type 0x06 message'),
        ('000229002a02', 'Type 0x00 message'),
        ('001f0600', 'Type 0x00 message'),
        
        ('0803201f8a1f', 'Button 0 RELEASE on unit 31'),
        ('060005190010', 'Type 0x06 message'),
        
        ('0803201f8a1f', 'Button 0 RELEASE on unit 31 (dup 2)'),
        ('06000e190010', 'Type 0x06 message'),
        
        ('0803201f8a1f', 'Button 0 RELEASE on unit 31 (dup 3)'),
        ('060015190010', 'Type 0x06 message'),
    ]
    
    print("\nEvent sequence from single button press/release:")
    for hex_str, description in events:
        print(f"  {hex_str} - {description}")
    
    print("\nKey observations:")
    print("- Button events are sent multiple times (reliability?)")
    print("- Other units (5, 8) send updates when button 31 is pressed")
    print("- Type 0x06 messages follow many events")
    print("- The changing byte (05, 0c, 0e, 15) might be a sequence number")

if __name__ == "__main__":
    analyze_structure()
    analyze_button_sequence()