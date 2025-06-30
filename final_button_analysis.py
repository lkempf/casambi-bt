#!/usr/bin/env python3
"""
Final analysis of button press/release events
"""
from binascii import a2b_hex, b2a_hex

def analyze_protocol_findings():
    print("CASAMBI BUTTON EVENT PROTOCOL ANALYSIS")
    print("=" * 80)
    
    print("\nFINDINGS:")
    print("-" * 40)
    
    print("\n1. MESSAGE STRUCTURE (Type 0x10):")
    print("   Byte 0: Message type (0x10 for these button events)")
    print("   Byte 2: Flags (0x02)")
    print("   Byte 2: [Length-1:4][Button:4] = 0x40 or 0x41")
    print("           Length = 5, Button = 0 or 1")
    print("   Bytes 3-7: Payload (5 bytes)")
    print("   Bytes 8-10: Additional data (possibly another message)")
    
    print("\n2. PAYLOAD STRUCTURE:")
    print("   Byte 0: Unit ID (0x14 = 20)")
    print("   Byte 1: Action/State")
    print("   Bytes 2-4: Fixed data (0x14 0x12 0x00)")
    
    print("\n3. ACTION VALUES:")
    print("   Button 0:")
    print("     - 0x59 (01011001): Initial event (likely PRESS)")
    print("     - 0x5a (01011010): Follow-up events (likely RELEASE)")
    print("   Button 1:")
    print("     - 0x5e (01011110): Initial events")
    print("     - 0x5f (01011111): Later events")
    print("\n   Pattern: The action increments by 1 between press and release")
    
    print("\n4. EVENT SEQUENCE:")
    print("   - Multiple packets are sent for each physical button action")
    print("   - Press: 1 packet with lower action value")
    print("   - Release: 3 packets with higher action value")
    
    print("\n5. ADDITIONAL DATA (last 3 bytes):")
    print("   - Byte 0: Counter/sequence (0x09, 0x0a, 0x0d, 0x26, etc.)")
    print("   - Byte 1: State byte (0x01 for press, 0x02 for release)")
    print("   - Byte 2: Button number (0x00 or 0x01)")
    
    # Test the hypothesis
    print("\n\nVERIFYING HYPOTHESIS:")
    print("-" * 40)
    
    events = [
        ("1002401459141200090100", "Button 0", "First"),
        ("100240145a1412000a0200", "Button 0", "Second"),
        ("100240145a1412000d0200", "Button 0", "Third"),
        ("100240145a141200260200", "Button 0", "Fourth"),
        ("100241145e141200090101", "Button 1", "First"),
        ("100241145e1412000c0101", "Button 1", "Second"),
        ("100241145f141200090201", "Button 1", "Third"),
        ("100241145f141200500201", "Button 1", "Fourth"),
    ]
    
    for hex_str, button_desc, order in events:
        data = a2b_hex(hex_str)
        action = data[4]
        state_byte = data[9]
        button_confirm = data[10]
        
        # Determine press/release from action value
        if action in [0x59, 0x5e]:
            event_from_action = "PRESS"
        else:
            event_from_action = "RELEASE"
        
        # Determine press/release from state byte
        event_from_state = "PRESS" if state_byte == 0x01 else "RELEASE"
        
        print(f"{button_desc} {order:6}: Action=0x{action:02x} → {event_from_action:7}, "
              f"State=0x{state_byte:02x} → {event_from_state:7}")
    
    print("\n\nCONCLUSION:")
    print("-" * 40)
    print("The state byte (position 9) clearly indicates:")
    print("  0x01 = PRESS")
    print("  0x02 = RELEASE")
    print("\nThe action values also follow a pattern where lower values")
    print("indicate press and higher values indicate release.")

if __name__ == "__main__":
    analyze_protocol_findings()