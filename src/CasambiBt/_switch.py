import logging
from dataclasses import dataclass
from enum import Enum, unique
from time import monotonic
from typing import Final

from ._invocation import parse_invocation_stream

_LOGGER = logging.getLogger(__name__)

_BUTTON_EVENT_MIN: Final[int] = 29  # FunctionButtonEvent0
_BUTTON_EVENT_MAX: Final[int] = 36  # FunctionButtonEvent7
_INPUT_EVENT_MIN: Final[int] = 64  # FunctionNotifyInput0
_INPUT_EVENT_MAX: Final[int] = 71  # FunctionNotifyInput7

_TARGET_TYPE_BUTTON: Final[int] = 0x06
_TARGET_TYPE_INPUT: Final[int] = 0x12

_DEDUP_WINDOW_SECONDS: Final[float] = 0.5


@unique
class ButtonEventType(Enum):
    PRESS = 0x01
    RELEASE = 0x02
    HOLD = 0x09
    RELEASE_AFTER_HOLD = 0x0C
    UNKNOWN = 0xFFFF


@dataclass(frozen=True, repr=True)
class SwitchEvent:
    button_event_index: int  # 0-based index from protocol (opcode - base)
    button: int  # 1-based label = button_event_index + 1
    unit_id: int
    target_type: int  # 0x06 = button stream, 0x12 = input stream
    event: ButtonEventType
    flags: int
    extra_data: bytes


class SwitchEventDecoder:
    """Stateful decoder that filters BLE retransmissions of switch events.

    Wireless switches (e.g. EnOcean PTM215B) emit each physical event on two
    streams in the same BLE packet:
      - 0x06 (button stream): PRESS / RELEASE via origin & 0x02
      - 0x12 (input stream):  PRESS / RELEASE / HOLD / RELEASE_AFTER_HOLD via payload[0]

    Both streams are retransmitted up to 3 times.  A single physical action
    therefore produces up to 6 raw frames.

    Stream responsibilities:
      - 0x06 is the authoritative source for PRESS and RELEASE events.
      - 0x12 is used exclusively for HOLD and RELEASE_AFTER_HOLD events.
        Its PRESS (0x01) and RELEASE (0x02) codes are ignored because the 0x12
        stream sends code=0x02 during a long hold (before the HOLD code=0x09
        arrives), which would cause a spurious RELEASE event.

    Retransmit deduplication uses the `origin` field from each INVOCATION frame
    as the event identity: all retransmissions of the same physical action share
    an identical `origin` value, while a new physical action always carries a
    different `origin` (the device increments its sequence counter).  A 500 ms
    time window prevents a stale entry from masking a future genuine event with
    the same origin.
    """

    def __init__(self) -> None:
        # (unit_id, button_event_index, origin) -> monotonic timestamp of first acceptance
        # Storing all three dimensions lets us suppress a retransmit of event A even
        # after event B (different origin) has already been accepted for the same button.
        self._seen_origins: dict[tuple[int, int, int], float] = {}
        self._logger = _LOGGER

    def reset(self) -> None:
        """Clear all cached state (call on reconnect)."""
        self._seen_origins.clear()

    def _is_retransmit(self, unit_id: int, button_index: int, origin: int) -> bool:
        """Return True if this frame is a retransmit of a recently accepted event.

        Uses the protocol-level `origin` field as the event identity: all BLE
        retransmissions of the same physical action share the same origin value,
        while a new physical action always carries a different origin (the device
        increments its sequence counter).  The time window guards against the edge
        case where the same origin reappears after a very long gap.
        """
        ts = self._seen_origins.get((unit_id, button_index, origin))
        return ts is not None and (monotonic() - ts) < _DEDUP_WINDOW_SECONDS

    def decode(self, data: bytes, packet_seq: int) -> list[SwitchEvent]:
        """Parse decrypted type-7 packet payload and return deduplicated switch events."""

        frames = parse_invocation_stream(data)
        events: list[SwitchEvent] = []

        for frame in frames:
            target_type = frame.target & 0xFF
            unit_id = frame.target >> 8

            if (
                target_type == _TARGET_TYPE_BUTTON
                and _BUTTON_EVENT_MIN <= frame.opcode <= _BUTTON_EVENT_MAX
            ):
                # Button stream: press/release encoded in bit 1 of origin low byte.
                # Confirmed on PTM215B captures: is_release = (origin & 0x02) != 0
                button_event_index = frame.opcode - _BUTTON_EVENT_MIN
                is_release = bool(frame.origin & 0x02)
                event = ButtonEventType.RELEASE if is_release else ButtonEventType.PRESS

                if self._is_retransmit(unit_id, button_event_index, frame.origin):
                    self._logger.debug(
                        "Suppressed retransmit (0x06): unit_id=%d button_index=%d event=%s origin=0x%04x",
                        unit_id,
                        button_event_index,
                        event.name,
                        frame.origin,
                    )
                    continue
                self._seen_origins[(unit_id, button_event_index, frame.origin)] = (
                    monotonic()
                )

                events.append(
                    SwitchEvent(
                        button_event_index=button_event_index,
                        button=button_event_index + 1,
                        unit_id=unit_id,
                        target_type=target_type,
                        event=event,
                        flags=frame.flags,
                        extra_data=frame.payload,
                    )
                )

            elif (
                target_type == _TARGET_TYPE_INPUT
                and _INPUT_EVENT_MIN <= frame.opcode <= _INPUT_EVENT_MAX
            ):
                # Input stream: payload[0] is the event type directly.
                # Confirmed on PTM215B: 0x01=PRESS, 0x02=RELEASE, 0x09=HOLD, 0x0C=RELEASE_AFTER_HOLD
                # PRESS and RELEASE are ignored here — 0x06 is authoritative for those.
                # 0x12 sends code=0x02 during long holds before HOLD arrives, causing
                # a spurious RELEASE event if we don't filter it out.
                if not frame.payload:
                    self._logger.debug(
                        "Input stream frame with empty payload, skipping."
                    )
                    continue
                button_event_index = frame.opcode - _INPUT_EVENT_MIN
                try:
                    event = ButtonEventType(frame.payload[0])
                except ValueError:
                    self._logger.debug(
                        "Unknown input event code 0x%02x in input stream frame.",
                        frame.payload[0],
                    )
                    event = ButtonEventType.UNKNOWN

                if event in (ButtonEventType.PRESS, ButtonEventType.RELEASE):
                    self._logger.debug(
                        "Ignored 0x12 %s (authoritative source is 0x06): unit_id=%d button_index=%d",
                        event.name,
                        unit_id,
                        button_event_index,
                    )
                    continue

                if self._is_retransmit(unit_id, button_event_index, frame.origin):
                    self._logger.debug(
                        "Suppressed retransmit (0x12): unit_id=%d button_index=%d event=%s origin=0x%04x",
                        unit_id,
                        button_event_index,
                        event.name,
                        frame.origin,
                    )
                    continue
                self._seen_origins[(unit_id, button_event_index, frame.origin)] = (
                    monotonic()
                )

                events.append(
                    SwitchEvent(
                        button_event_index=button_event_index,
                        button=button_event_index + 1,
                        unit_id=unit_id,
                        target_type=target_type,
                        event=event,
                        flags=frame.flags,
                        extra_data=frame.payload[1:],
                    )
                )

            else:
                self._logger.debug(
                    "Ignoring INVOCATION frame: opcode=0x%02x target_type=0x%02x.",
                    frame.opcode,
                    target_type,
                )

        if not events:
            self._logger.debug("No switch events found in packet #%s.", packet_seq)

        return events
