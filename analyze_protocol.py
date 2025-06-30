#!/usr/bin/env python3
"""
Analyze Casambi protocol patterns without assumptions
"""
from binascii import a2b_hex
from collections import defaultdict
import struct

# Raw data from logs - single button press/release sequence
packets = [
    ('15:04:54.385', '0803201f851f06000599000229002a0f001f060003', 'packet 1'),
    ('15:04:54.389', '29002a08001f060003', 'packet 2'),
    ('15:04:54.422', '29002a05001f060009', 'packet 3'),
    ('15:04:54.460', '0803201f851f06000c99000229002a02001f06000b', 'packet 4'),
    ('15:04:54.534', '0803201f8a1f060005190010', 'packet 5'),
    ('15:04:54.609', '0803201f8a1f06000e190010', 'packet 6'),
    ('15:04:54.686', '0803201f8a1f060015190010', 'packet 7'),
    ('15:04:54.723', '1002430a981f120002020b', 'packet 8'),
    ('15:04:54.728', '10024308611f120002020b', 'packet 9'),
    ('15:04:54.834', '29002a02001f060030', 'packet 10'),
    ('15:04:58.171', '29002a02001f06017d', 'packet 11'),
]

def analyze_patterns():
    print("=" * 80)
    print("PATTERN ANALYSIS - NO ASSUMPTIONS")
    print("=" * 80)
    
    # First, let's look at raw byte patterns
    print("\n1. RAW BYTE ANALYSIS")
    print("-" * 40)
    
    for time, hex_str, label in packets:
        data = a2b_hex(hex_str)
        print(f"\n{label} ({time}): {hex_str}")
        print(f"  Length: {len(data)} bytes")
        print(f"  Bytes: {' '.join(f'{b:02x}' for b in data)}")
        
        # Look for repeating patterns
        if len(data) >= 3:
            print(f"  First 3 bytes: {data[0]:02x} {data[1]:02x} {data[2]:02x}")
    
    # Look for common byte sequences
    print("\n\n2. COMMON SEQUENCES")
    print("-" * 40)
    
    # Find all 3-byte sequences
    sequences = defaultdict(list)
    for time, hex_str, label in packets:
        data = a2b_hex(hex_str)
        for i in range(len(data) - 2):
            seq = data[i:i+3]
            sequences[seq.hex()].append((label, i))
    
    # Show sequences that appear multiple times
    for seq_hex, occurrences in sorted(sequences.items()):
        if len(occurrences) > 1:
            print(f"\nSequence {seq_hex} appears {len(occurrences)} times:")
            for label, pos in occurrences:
                print(f"  - {label} at position {pos}")
    
    # Analyze specific patterns
    print("\n\n3. SPECIFIC OBSERVATIONS")
    print("-" * 40)
    
    # Pattern: 08 03 20 1f
    button_press_packets = []
    button_release_packets = []
    
    for time, hex_str, label in packets:
        data = a2b_hex(hex_str)
        if data.startswith(b'\x08\x03\x20\x1f\x85'):
            button_press_packets.append((label, data))
        elif data.startswith(b'\x08\x03\x20\x1f\x8a'):
            button_release_packets.append((label, data))
    
    print(f"\nPackets starting with '08 03 20 1f 85': {len(button_press_packets)}")
    for label, data in button_press_packets:
        print(f"  {label}: {data.hex()}")
    
    print(f"\nPackets starting with '08 03 20 1f 8a': {len(button_release_packets)}")
    for label, data in button_release_packets:
        print(f"  {label}: {data.hex()}")
    
    # Look at the differences
    print("\n\n4. PACKET STRUCTURE HYPOTHESIS")
    print("-" * 40)
    
    # Let's examine the structure more carefully
    for time, hex_str, label in packets[:5]:  # First 5 packets
        data = a2b_hex(hex_str)
        print(f"\n{label}:")
        
        # Try different interpretations
        if len(data) >= 4:
            # Hypothesis 1: First byte is type, second is flags/status
            print(f"  If byte 0 is type: {data[0]:02x}")
            print(f"  If byte 1 is flags: {data[1]:02x} = {data[1]:08b}b")
            print(f"  If byte 2 is compound: {data[2]:02x} = high:{(data[2]>>4):x} low:{(data[2]&0xf):x}")
            
            # Look for length indicators
            nibble_high = (data[2] >> 4) & 0xf
            nibble_low = data[2] & 0xf
            
            # Check if high nibble could be length
            if 3 + nibble_high <= len(data):
                print(f"  If high nibble of byte 2 is length-1: {nibble_high+1} → ends at byte {3+nibble_high}")
            
            # Check if low nibble could be length  
            if 3 + nibble_low <= len(data):
                print(f"  If low nibble of byte 2 is length-1: {nibble_low+1} → ends at byte {3+nibble_low}")

def analyze_button_events():
    print("\n\n5. BUTTON PRESS/RELEASE ANALYSIS")
    print("-" * 40)
    
    # Focus on the known button events
    press_1 = a2b_hex('0803201f851f06000599000229002a0f001f060003')
    press_2 = a2b_hex('0803201f851f06000c99000229002a02001f06000b')
    release_1 = a2b_hex('0803201f8a1f060005190010')
    release_2 = a2b_hex('0803201f8a1f06000e190010')
    release_3 = a2b_hex('0803201f8a1f060015190010')
    
    print("\nComparing button presses:")
    print(f"Press 1:   {' '.join(f'{b:02x}' for b in press_1[:10])}")
    print(f"Press 2:   {' '.join(f'{b:02x}' for b in press_2[:10])}")
    print("\nDifferences in first 10 bytes:")
    for i in range(min(10, len(press_1), len(press_2))):
        if press_1[i] != press_2[i]:
            print(f"  Byte {i}: {press_1[i]:02x} vs {press_2[i]:02x}")
    
    print("\nComparing button releases:")
    print(f"Release 1: {' '.join(f'{b:02x}' for b in release_1)}")
    print(f"Release 2: {' '.join(f'{b:02x}' for b in release_2)}")
    print(f"Release 3: {' '.join(f'{b:02x}' for b in release_3)}")
    print("\nDifferences:")
    for i in range(min(len(release_1), len(release_2), len(release_3))):
        if not (release_1[i] == release_2[i] == release_3[i]):
            print(f"  Byte {i}: {release_1[i]:02x} vs {release_2[i]:02x} vs {release_3[i]:02x}")

def analyze_packet_boundaries():
    print("\n\n6. PACKET BOUNDARY ANALYSIS")
    print("-" * 40)
    
    # Let's see if we can find where one "message" ends and another begins
    long_packet = a2b_hex('0803201f851f06000599000229002a0f001f060003')
    
    print(f"Analyzing long packet: {long_packet.hex()}")
    print(f"Length: {len(long_packet)} bytes")
    
    # Try to find patterns that might indicate message boundaries
    # Look for sequences that appear to be "headers"
    pos = 0
    messages = []
    
    while pos < len(long_packet):
        # Look for potential header patterns
        if pos + 3 <= len(long_packet):
            byte0 = long_packet[pos]
            byte1 = long_packet[pos+1]
            byte2 = long_packet[pos+2]
            
            # Calculate potential lengths
            len_from_nibble = ((byte2 >> 4) & 0xf) + 1
            
            print(f"\nPosition {pos}: {byte0:02x} {byte1:02x} {byte2:02x}")
            print(f"  Potential length from high nibble: {len_from_nibble}")
            
            # See if this length makes sense
            if pos + 3 + len_from_nibble <= len(long_packet):
                potential_msg = long_packet[pos:pos+3+len_from_nibble]
                print(f"  Potential message: {potential_msg.hex()}")
                messages.append(potential_msg)
                pos += 3 + len_from_nibble
            else:
                print(f"  Length would exceed packet boundary")
                pos += 1
        else:
            break
    
    print(f"\nFound {len(messages)} potential messages")
    for i, msg in enumerate(messages):
        print(f"  Message {i+1}: {msg.hex()}")

if __name__ == "__main__":
    analyze_patterns()
    analyze_button_events()
    analyze_packet_boundaries()