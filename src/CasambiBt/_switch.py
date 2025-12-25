import logging
from binascii import b2a_hex as b2a
from dataclasses import dataclass
from enum import Enum, unique

_LOGGER = logging.getLogger(__name__)


@unique
class ButtonEventType(Enum):
    PRESS = 0x01
    RELEASE = 0x02
    HOLD = 0x09
    RELEASE_AFTER_HOLD = 0x0C
    UNKNOWN = 0xFFFF


# TODO: Add message type enum.
# TODO: Add action type enum.


@dataclass(frozen=True, repr=True)
class SwitchEvent:
    message_type: int
    button: int
    unit_id: int
    action: int | None
    event: ButtonEventType
    flags: int
    extra_data: bytes


def parseSwitchEvents(
    data: bytes, packet_seq: int, raw_packet: bytes
) -> list[SwitchEvent]:
    """Parse switch event packet which contains multiple message types."""

    # Log complete packet structure with marker
    _LOGGER.debug(
        f"[CASAMBI_SWITCH_PACKET] Full data #{packet_seq}: hex={b2a(data)} len={len(data)}"
    )

    # Special handling for message type 0x29 - not a switch event
    if len(data) >= 1 and data[0] == 0x29:
        _LOGGER.debug(f"Ignoring message type 0x29 (not a switch event): {b2a(data)}")
        return []

    pos = 0
    oldPos = 0
    switch_events_found = 0
    all_messages_found = []
    switch_events = []

    try:
        while pos <= len(data) - 3:
            oldPos = pos

            # Parse message header
            message_type = data[pos]
            flags = data[pos + 1]
            length = ((data[pos + 2] >> 4) & 15) + 1
            parameter = data[pos + 2]  # Full byte, not just lower 4 bits
            pos += 3

            # Log every message found with detailed structure
            _LOGGER.debug(
                f"[CASAMBI_MSG_FOUND] At pos={oldPos}: type=0x{message_type:02x} flags=0x{flags:02x} "
                f"len={length} param=0x{parameter:02x}"
            )

            # Sanity check: message type should be reasonable
            if message_type > 0x80:
                _LOGGER.debug(
                    f"Skipping invalid message type 0x{message_type:02x} at position {oldPos}"
                )
                # Try to resync by looking for next valid message
                pos = oldPos + 1
                continue

            # Check if we have enough data for the payload
            if pos + length > len(data):
                _LOGGER.debug(
                    f"Incomplete message at position {oldPos}. "
                    f"Type: 0x{message_type:02x}, declared length: {length}, available: {len(data) - pos}"
                )
                break

            # Extract the payload
            payload = data[pos : pos + length]
            pos += length

            # Log the payload
            _LOGGER.debug(
                f"[CASAMBI_MSG_PAYLOAD] Type 0x{message_type:02x} payload: {b2a(payload)} "
                f"(bytes {oldPos+3} to {oldPos+3+length-1})"
            )

            # Track all messages
            all_messages_found.append(
                {
                    "type": message_type,
                    "pos": oldPos,
                    "flags": flags,
                    "param": parameter,
                    "payload": b2a(payload),
                }
            )

            # Process based on message type
            if message_type == 0x08 or message_type == 0x10:  # Switch/button events
                switch_events_found += 1

                # Button extraction differs between type 0x08 and type 0x10
                if message_type == 0x08:
                    # For type 0x08, the lower nibble is a code that maps to physical button id
                    # Using formula: ((code + 2) % 4) + 1 based on reverse engineering findings
                    code_nibble = parameter & 0x0F
                    button = ((code_nibble + 2) % 4) + 1
                    _LOGGER.debug(
                        f"Type 0x08 button extraction: parameter=0x{parameter:02x}, code={code_nibble}, button={button}"
                    )
                    full_message_data = data
                elif message_type == 0x10:
                    # For type 0x10, use existing logic
                    button_lower = parameter & 0x0F
                    button_upper = (parameter >> 4) & 0x0F

                    # Use upper 4 bits if lower 4 bits are 0, otherwise use lower 4 bits
                    if button_lower == 0 and button_upper != 0:
                        button = button_upper
                        _LOGGER.debug(
                            f"Type 0x10 button extraction: parameter=0x{parameter:02x}, using upper nibble, button={button}"
                        )
                    else:
                        button = button_lower
                        _LOGGER.debug(
                            f"Type 0x10 button extraction: parameter=0x{parameter:02x}, using lower nibble, button={button}"
                        )

                    # For type 0x10 messages, we need to pass additional data beyond the declared payload
                    # Extend to include at least 10 bytes from message start for state byte
                    extended_end = min(oldPos + 11, len(data))
                    full_message_data = data[oldPos:extended_end]

                switch_events.append(
                    _processSwitchMessage(
                        message_type, flags, button, payload, full_message_data
                    )
                )
            elif message_type == 0x29:
                # This shouldn't happen due to check above, but just in case
                _LOGGER.debug("Ignoring embedded type 0x29 message")
            elif message_type in [0x00, 0x06, 0x09, 0x1F, 0x2A]:
                # Known non-switch message types - log at debug level
                _LOGGER.debug(f"Non-switch message type 0x{message_type:02x}")
            else:
                # Unknown message types - log at info level
                _LOGGER.info(f"Unknown message type 0x{message_type:02x}")

            oldPos = pos

    except IndexError:
        _LOGGER.warning("Ran out of data while parsing switch event packet!")
        _LOGGER.info(f"Remaining data {b2a(data[oldPos:])} in {b2a(data)}.")

    # Log summary of all messages found
    _LOGGER.debug(
        f"[CASAMBI_PARSE_SUMMARY] Packet #{packet_seq}: Found {len(all_messages_found)} messages, "
        f"{switch_events_found} switch events"
    )
    for i, msg in enumerate(all_messages_found):
        _LOGGER.debug(
            f"[CASAMBI_MSG_{i+1}] Type=0x{msg['type']:02x} Pos={msg['pos']} "
            f"Flags=0x{msg['flags']:02x} Param=0x{msg['param']:02x} Payload={msg['payload']}"
        )

    if switch_events_found == 0:
        _LOGGER.info(f"No switch events found in packet: {b2a(data)}")

    return switch_events


def _processSwitchMessage(
    message_type: int, flags: int, button: int, payload: bytes, full_data: bytes
) -> SwitchEvent:
    """Process a switch/button message (types 0x08 or 0x10)."""

    assert len(payload) > 0

    # Extract unit_id based on message type
    if message_type == 0x10 and len(payload) >= 3:
        # Type 0x10: unit_id is at payload[2]
        unit_id = payload[2]
        extra_data = payload[3:] if len(payload) > 3 else b""
    else:
        # Standard parsing for other message types
        unit_id = payload[0]
        extra_data = b""
        if len(payload) > 2:
            extra_data = payload[2:]

    # Extract action based on message type (action SHOULD be different for press vs release)
    if len(payload) > 1:
        # Action is at payload[1]
        action = payload[1]
    else:
        action = None

    event = ButtonEventType.UNKNOWN

    # Different interpretation based on message type
    if message_type == 0x08:
        # Type 0x08: Use bit 1 of action for press/release
        if action is not None:
            is_release = (action >> 1) & 1
            event = ButtonEventType.RELEASE if is_release else ButtonEventType.PRESS
    elif message_type == 0x10:
        # Type 0x10: The state byte is at position 9 (0-indexed) from message start
        # This applies to all units, not just unit 31
        # full_data for type 0x10 is the message data starting from position 0
        state_pos = 9
        if len(full_data) > state_pos:
            state_byte = full_data[state_pos]
            if state_byte in ButtonEventType:
                event = ButtonEventType(state_byte)
            else:
                _LOGGER.debug(
                    f"Type 0x10: Unknown state byte 0x{state_byte:02x} at message pos {state_pos}"
                )
        else:
            # Fallback when message is too short
            if len(extra_data) >= 1 and extra_data[0] == 0x12:
                event = ButtonEventType.RELEASE
                _LOGGER.debug(
                    "Type 0x10: Using extra_data pattern for release detection"
                )
            else:
                # Cannot determine state
                _LOGGER.warning(
                    f"Type 0x10 message missing state info, unit_id={unit_id}, payload={b2a(payload)}"
                )

    action_display = f"{action:#04x}" if action is not None else "N/A"

    _LOGGER.info(
        f"Switch event (type 0x{message_type:02x}): button={button}, unit_id={unit_id}, "
        f"action={action_display} ({event}), flags=0x{flags:02x}"
    )

    # Log detailed info about type 0x08 messages (now processed, not filtered)
    if message_type == 0x08:
        _LOGGER.debug(
            f"[CASAMBI_TYPE08_PROCESSED] Type 0x08 event processed: button={button}, unit_id={unit_id}, "
            f"action={action_display}, event={event}, flags=0x{flags:02x}, "
            f"payload={b2a(payload)}, extra_data={b2a(extra_data) if extra_data else 'none'}"
        )

    return SwitchEvent(message_type, button, unit_id, action, event, flags, extra_data)
