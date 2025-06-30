# Casambi Switch Event Protocol Findings

## Overview
Switch event packets (type 0x07) contain multiple message types, not just switch events. Each packet can contain several concatenated messages.

## Message Structure
All messages follow this format:
- Byte 0: Message type
- Byte 1: Flags/status
- Byte 2: `[Length-1:4][Parameter:4]` (high nibble = payload length - 1, low nibble = parameter)
- Bytes 3+: Payload (variable length based on byte 2 high nibble)

## Message Types

### Type 0x08 - Switch/Button Event (e.g., unit 31)
- Parameter: Button number (0-based)
- Payload[0]: Unit ID
- Payload[1]: Action byte (bit 1 determines press/release: 0=press, 1=release)
- Payload[2+]: Additional data (often 0x1f)

Example actions:
- 0x85 (10000101): Button press (bit 1 = 0)
- 0x8a (10001010): Button release (bit 1 = 1)

### Type 0x10 - Extended Switch Event (e.g., unit 20)
- Parameter: Button number (0-based)
- Payload[0]: Unit ID  
- Payload[1]: Action byte (rolling counter, increments with each state change)
- Payload[2-4]: Fixed data (often 0x14 0x12 0x00)
- **Additional 3 bytes after message**: Contains state information
  - Byte 0: Sequence/counter
  - Byte 1: State (0x01 = PRESS, 0x02 = RELEASE)
  - Byte 2: Button number confirmation

**Important**: For type 0x10, the action byte is NOT a press/release indicator but a counter. The state byte in the additional data is the reliable indicator.

### Type 0x29 - Unit State Update
- Parameter: Usually 0x0a (10)
- Payload[0]: Unit ID
- Payload[1]: State value
- Payload[2+]: Additional data

### Type 0x06 - Sequence/Status Message
- Parameter: Varies
- Payload[0]: Sequence number or status

### Type 0x00, 0x02 - General/Short Status Messages

## Key Findings

1. **Multiple messages per packet**: BLE packets efficiently batch multiple messages
2. **Reliability through repetition**: 
   - Press events: Usually 1-2 packets
   - Release events: Usually 2-3 packets
3. **Action counter**: The action byte in type 0x10 messages continuously increments across all button events
4. **State byte is definitive**: For type 0x10, only the state byte (0x01=press, 0x02=release) reliably indicates the event type

## Example Sequences

### Button 0 on unit 20 (type 0x10)
Press: action=0x66, state=0x01
Release: action=0x67, state=0x02 (×2)

### Button 1 on unit 20 (type 0x10)  
Press: action=0x6d, state=0x01
Release: action=0x6e, state=0x02 (×2)

### Button 0 on unit 31 (type 0x08)
Press: action=0x85 (bit 1 = 0)
Release: action=0x8a (bit 1 = 1)

## Implementation Notes

The parser must:
1. Parse multiple messages from each packet
2. Handle different message types appropriately
3. Use correct press/release detection for each type:
   - Type 0x08: Check bit 1 of action byte
   - Type 0x10: Check state byte in additional data
4. Not assume action values are fixed (they're counters for type 0x10)