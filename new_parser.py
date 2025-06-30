#!/usr/bin/env python3
"""
New parser implementation based on reverse-engineered protocol
"""
from binascii import a2b_hex, b2a_hex
from typing import List, Dict, Any, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CasambiMessage:
    """Represents a single Casambi message"""
    def __init__(self, msg_type: int, flags: int, parameter: int, payload: bytes):
        self.type = msg_type
        self.flags = flags
        self.parameter = parameter
        self.payload = payload
    
    def __repr__(self):
        return f"CasambiMessage(type=0x{self.type:02x}, flags=0x{self.flags:02x}, param={self.parameter}, payload={b2a_hex(self.payload).decode()})"

class CasambiPacketParser:
    """Parser for Casambi BLE packets containing multiple messages"""
    
    @staticmethod
    def parse_packet(data: bytes) -> List[CasambiMessage]:
        """Parse a packet into individual messages"""
        messages = []
        pos = 0
        
        while pos < len(data):
            # Need at least 3 bytes for header
            if pos + 3 > len(data):
                logger.debug(f"Incomplete header at position {pos}, remaining: {b2a_hex(data[pos:]).decode()}")
                break
            
            # Parse header
            msg_type = data[pos]
            flags = data[pos + 1]
            length_param_byte = data[pos + 2]
            
            # Extract length and parameter
            payload_length = ((length_param_byte >> 4) & 0x0F) + 1
            parameter = length_param_byte & 0x0F
            
            # Check if we have enough data for payload
            if pos + 3 + payload_length > len(data):
                logger.debug(f"Incomplete payload at position {pos}, need {payload_length} bytes")
                break
            
            # Extract payload
            payload = data[pos + 3 : pos + 3 + payload_length]
            
            # Create message
            msg = CasambiMessage(msg_type, flags, parameter, payload)
            messages.append(msg)
            
            # Move to next message
            pos += 3 + payload_length
        
        return messages
    
    @staticmethod
    def interpret_message(msg: CasambiMessage) -> Dict[str, Any]:
        """Interpret a message based on its type"""
        result = {
            'type': msg.type,
            'flags': msg.flags,
            'parameter': msg.parameter,
            'raw_payload': b2a_hex(msg.payload).decode()
        }
        
        if msg.type == 0x08:  # Switch/Button Event
            result.update(CasambiPacketParser._interpret_switch_event(msg))
        elif msg.type == 0x29:  # Unit State Update
            result.update(CasambiPacketParser._interpret_unit_update(msg))
        elif msg.type == 0x06:  # Sequence/Status
            result.update(CasambiPacketParser._interpret_sequence_status(msg))
        elif msg.type == 0x10:  # Extended Event
            result.update(CasambiPacketParser._interpret_extended_event(msg))
        
        return result
    
    @staticmethod
    def _interpret_switch_event(msg: CasambiMessage) -> Dict[str, Any]:
        """Interpret type 0x08 switch/button events"""
        if len(msg.payload) < 2:
            return {'error': 'Payload too short for switch event'}
        
        unit_id = msg.payload[0]
        action = msg.payload[1]
        
        # Bit 1 determines press/release
        is_release = (action >> 1) & 1
        event_type = 'release' if is_release else 'press'
        
        result = {
            'message_type': 'switch_event',
            'button': msg.parameter,
            'unit_id': unit_id,
            'action': action,
            'event': f'button_{event_type}'
        }
        
        if len(msg.payload) > 2:
            result['extra_data'] = b2a_hex(msg.payload[2:]).decode()
        
        return result
    
    @staticmethod
    def _interpret_unit_update(msg: CasambiMessage) -> Dict[str, Any]:
        """Interpret type 0x29 unit state updates"""
        if len(msg.payload) < 1:
            return {'error': 'Payload too short for unit update'}
        
        unit_id = msg.payload[0]
        
        result = {
            'message_type': 'unit_update',
            'unit_id': unit_id,
            'update_type': msg.parameter
        }
        
        if len(msg.payload) > 1:
            result['value'] = msg.payload[1]
        
        if len(msg.payload) > 2:
            result['extra_data'] = b2a_hex(msg.payload[2:]).decode()
        
        return result
    
    @staticmethod
    def _interpret_sequence_status(msg: CasambiMessage) -> Dict[str, Any]:
        """Interpret type 0x06 sequence/status messages"""
        if len(msg.payload) < 1:
            return {'error': 'Payload too short for sequence status'}
        
        return {
            'message_type': 'sequence_status',
            'sequence_or_status': msg.payload[0],
            'status_type': msg.parameter
        }
    
    @staticmethod
    def _interpret_extended_event(msg: CasambiMessage) -> Dict[str, Any]:
        """Interpret type 0x10 extended events"""
        if len(msg.payload) < 2:
            return {'error': 'Payload too short for extended event'}
        
        unit_id = msg.payload[0]
        value = msg.payload[1]
        
        result = {
            'message_type': 'extended_event',
            'unit_id': unit_id,
            'value': value,
            'event_type': msg.parameter
        }
        
        if len(msg.payload) > 2:
            result['extra_data'] = b2a_hex(msg.payload[2:]).decode()
        
        return result

def test_new_parser():
    """Test the new parser with known data"""
    test_packets = [
        ("Button press", "0803201f851f06000599000229002a0f001f060003"),
        ("Button release", "0803201f8a1f060005190010"),
        ("Unit update", "29002a08001f060003"),
        ("Extended event", "1002430a981f120002020b"),
    ]
    
    parser = CasambiPacketParser()
    
    for name, hex_str in test_packets:
        print(f"\n{name}: {hex_str}")
        print("-" * 60)
        
        data = a2b_hex(hex_str)
        messages = parser.parse_packet(data)
        
        for i, msg in enumerate(messages, 1):
            print(f"\nMessage {i}: {msg}")
            interpretation = parser.interpret_message(msg)
            for key, value in interpretation.items():
                print(f"  {key}: {value}")

def test_button_sequence():
    """Test parsing the complete button press/release sequence"""
    print("\n\nBUTTON PRESS/RELEASE SEQUENCE ANALYSIS")
    print("=" * 80)
    
    packets = [
        "0803201f851f06000599000229002a0f001f060003",
        "29002a08001f060003",
        "29002a05001f060009",
        "0803201f851f06000c99000229002a02001f06000b",
        "0803201f8a1f060005190010",
        "0803201f8a1f06000e190010",
        "0803201f8a1f060015190010",
        "1002430a981f120002020b",
        "10024308611f120002020b",
        "29002a02001f060030",
        "29002a02001f06017d",
    ]
    
    parser = CasambiPacketParser()
    sequence_numbers = []
    
    for i, hex_str in enumerate(packets, 1):
        print(f"\nPacket {i}:")
        data = a2b_hex(hex_str)
        messages = parser.parse_packet(data)
        
        for msg in messages:
            interpretation = parser.interpret_message(msg)
            
            # Extract key information
            if interpretation.get('message_type') == 'switch_event':
                print(f"  → Button {interpretation['button']} {interpretation['event']} on unit {interpretation['unit_id']}")
            elif interpretation.get('message_type') == 'unit_update':
                print(f"  → Unit {interpretation['unit_id']} update")
            elif interpretation.get('message_type') == 'sequence_status':
                seq = interpretation['sequence_or_status']
                sequence_numbers.append(seq)
                print(f"  → Sequence/Status: {seq}")
    
    print(f"\nSequence numbers observed: {sequence_numbers}")

if __name__ == "__main__":
    test_new_parser()
    test_button_sequence()