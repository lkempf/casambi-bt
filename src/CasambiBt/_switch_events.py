from __future__ import annotations

import logging
import time
from binascii import b2a_hex as b2a
from dataclasses import dataclass
from typing import Any, Final

from ._invocation import InvocationFrame, parse_invocation_stream


_BUTTON_EVENT_MIN: Final[int] = 29  # FunctionButtonEvent0
_BUTTON_EVENT_MAX: Final[int] = 36  # FunctionButtonEvent7
_INPUT_EVENT_MIN: Final[int] = 64  # FunctionNotifyInput0
_INPUT_EVENT_MAX: Final[int] = 71  # FunctionNotifyInput7

_TARGET_TYPE_BUTTON: Final[int] = 0x06
_TARGET_TYPE_INPUT: Final[int] = 0x12


def _guess_button_label_4gang(button_event_index: int) -> int:
    """Casambi app labels a typical 4-button switch as 1..4.

    Observed mapping for 4-gang switches in provided logs:
    - ButtonEvent0 -> label 4
    - ButtonEvent1 -> label 1
    - ButtonEvent2 -> label 2
    - ButtonEvent3 -> label 3
    """

    if 0 <= button_event_index <= 3:
        return ((button_event_index + 3) % 4) + 1
    return button_event_index


@dataclass(slots=True)
class SwitchDecoderStats:
    frames_total: int = 0
    frames_button: int = 0
    frames_input: int = 0
    frames_ignored: int = 0
    events_emitted: int = 0
    events_suppressed_same_state: int = 0


class SwitchEventStreamDecoder:
    """Decode decrypted packet type=7 payload into high-level switch events."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)
        # (unit_id, button_event_index) -> pressed(bool)
        self._last_pressed: dict[tuple[int, int], bool] = {}
        # (unit_id, input_index) -> last input code (payload[0]) we emitted as a semantic event.
        self._last_input_code: dict[tuple[int, int], int] = {}
        # (unit_id, button_label) -> observed real button stream (target_type=0x06) for that button.
        # If present, we avoid creating synthetic press/release events from input frames.
        self._button_stream_seen: set[tuple[int, int]] = set()

    def reset(self) -> None:
        self._last_pressed.clear()
        self._last_input_code.clear()
        self._button_stream_seen.clear()

    def decode(
        self,
        data: bytes,
        *,
        packet_seq: int | None = None,
        raw_packet: bytes | None = None,
        arrival_sequence: int | None = None,
    ) -> tuple[list[dict[str, Any]], SwitchDecoderStats]:
        """Decode one decrypted switch packet payload."""

        frames = parse_invocation_stream(data, logger=self._logger)
        stats = SwitchDecoderStats(frames_total=len(frames))
        events: list[dict[str, Any]] = []

        for frame in frames:
            ev = self._decode_frame(
                frame,
                data=data,
                packet_seq=packet_seq,
                raw_packet=raw_packet,
                arrival_sequence=arrival_sequence,
                stats=stats,
            )
            if ev is None:
                continue
            events.append(ev)
            stats.events_emitted += 1

        return events, stats

    def _decode_frame(
        self,
        frame: InvocationFrame,
        *,
        data: bytes,
        packet_seq: int | None,
        raw_packet: bytes | None,
        arrival_sequence: int | None,
        stats: SwitchDecoderStats,
    ) -> dict[str, Any] | None:
        unit_id = (frame.target >> 8) & 0xFF
        target_type = frame.target & 0xFF

        origin_unit_id = (frame.origin >> 8) & 0xFF
        origin_type = frame.origin & 0xFF

        # Button events (press/release) are INVOCATIONs targeted at type 0x06.
        if (
            target_type == _TARGET_TYPE_BUTTON
            and _BUTTON_EVENT_MIN <= frame.opcode <= _BUTTON_EVENT_MAX
        ):
            stats.frames_button += 1

            button_event_index = frame.opcode - _BUTTON_EVENT_MIN
            button = _guess_button_label_4gang(button_event_index)
            self._button_stream_seen.add((unit_id, button))

            pressed = bool(frame.payload and (frame.payload[0] & 0x80))
            state_key = (unit_id, button_event_index)
            last_pressed = self._last_pressed.get(state_key)

            # Wireless switches retransmit; drop repeated same-state frames to avoid duplicate events.
            if last_pressed is not None and last_pressed == pressed:
                stats.events_suppressed_same_state += 1
                self._logger.debug(
                    "[CASAMBI_EVENT_SUPPRESS] unit=%d button_index=%d button=%d pressed=%s opcode=0x%02x origin=0x%04x age=0x%04x",
                    unit_id,
                    button_event_index,
                    button,
                    pressed,
                    frame.opcode,
                    frame.origin,
                    frame.age,
                )
                return None
            self._last_pressed[state_key] = pressed

            b0 = frame.payload[0] if frame.payload else 0
            param_p = (b0 >> 3) & 0x0F
            param_s = b0 & 0x07

            event = "button_press" if pressed else "button_release"

            # Stable identifier for consumers to deduplicate further if needed.
            event_id = f"invoke:{frame.origin:04x}:{frame.age:04x}:{frame.opcode:02x}:{frame.target:04x}"

            self._logger.info(
                "[CASAMBI_BUTTON_EVENT] packet=%s unit=%d button=%d event=%s opcode=0x%02x origin=0x%04x age=0x%04x flags=0x%04x payload=%s",
                packet_seq,
                unit_id,
                button,
                event,
                frame.opcode,
                frame.origin,
                frame.age,
                frame.flags,
                b2a(frame.payload),
            )

            return {
                # Back-compat / existing consumers
                "unit_id": unit_id,
                "button": button,
                "event": event,
                "message_type": 0x07,  # decrypted packet type (SwitchEvent)
                "message_position": frame.offset,
                "extra_data": None,
                # INVOCATION fields
                "invocation_flags": frame.flags,
                "opcode": frame.opcode,
                "origin": frame.origin,
                "origin_unit_id": origin_unit_id,
                "origin_type": origin_type,
                "target": frame.target,
                "target_type": target_type,
                "age": frame.age,
                "origin_handle": frame.origin_handle,
                "payload": frame.payload,
                "payload_hex": b2a(frame.payload),
                "frame_offset": frame.offset,
                "button_event_index": button_event_index,
                "param_p": param_p,
                "param_s": param_s,
                # Diagnostics / correlation
                "packet_sequence": packet_seq,
                "arrival_sequence": arrival_sequence,
                "event_id": event_id,
                "raw_packet": b2a(raw_packet) if raw_packet else None,
                "decrypted_data": b2a(data),
                "frame_hex": b2a(
                    data[frame.offset : frame.offset + (9 + (1 if frame.origin_handle is not None else 0) + frame.payload_len)]
                ),
                "received_at": time.time(),
            }

        # Input notify frames (often accompany wireless switches).
        if (
            target_type == _TARGET_TYPE_INPUT
            and _INPUT_EVENT_MIN <= frame.opcode <= _INPUT_EVENT_MAX
        ):
            stats.frames_input += 1
            input_index = frame.opcode - _INPUT_EVENT_MIN
            input_code = frame.payload[0] if frame.payload else None
            input_b1 = frame.payload[1] if len(frame.payload) >= 2 else None
            input_channel = (input_b1 & 0x07) if input_b1 is not None else None
            input_value16 = (
                int.from_bytes(frame.payload[2:4], "little")
                if len(frame.payload) >= 4
                else None
            )
            button = _guess_button_label_4gang(input_index)

            # Map common input codes into the legacy "switch" event taxonomy.
            # Observed:
            # - wired: 01xx press, 02xx release, 0cxx release_after_hold
            # - wireless: 09xx hold, 0cxx release_after_hold (+ separate button stream for press/release)
            mapped_event: str | None = None
            if input_code is not None:
                if input_code == 0x09:
                    mapped_event = "button_hold"
                elif input_code == 0x0C:
                    mapped_event = "button_release_after_hold"
                elif input_code == 0x01:
                    mapped_event = "button_press"
                elif input_code == 0x02:
                    mapped_event = "button_release"

            input_mapped_event = mapped_event

            # Avoid duplicating press/release for wireless switches that also produce the real button stream.
            if mapped_event in ("button_press", "button_release") and (unit_id, button) in self._button_stream_seen:
                mapped_event = None

            if mapped_event is not None and input_code is not None:
                state_key = (unit_id, input_index)
                last_code = self._last_input_code.get(state_key)
                if last_code == input_code:
                    stats.events_suppressed_same_state += 1
                    self._logger.debug(
                        "[CASAMBI_EVENT_SUPPRESS] input unit=%d input_index=%d button=%d code=0x%02x opcode=0x%02x origin=0x%04x age=0x%04x",
                        unit_id,
                        input_index,
                        button,
                        input_code,
                        frame.opcode,
                        frame.origin,
                        frame.age,
                    )
                    return None
                self._last_input_code[state_key] = input_code

                self._logger.info(
                    "[CASAMBI_INPUT_AS_BUTTON] packet=%s unit=%d button=%d event=%s code=0x%02x opcode=0x%02x origin=0x%04x age=0x%04x flags=0x%04x payload=%s",
                    packet_seq,
                    unit_id,
                    button,
                    mapped_event,
                    input_code,
                    frame.opcode,
                    frame.origin,
                    frame.age,
                    frame.flags,
                    b2a(frame.payload),
                )
            event = mapped_event or "input_event"
            self._logger.debug(
                "[CASAMBI_INPUT_EVENT] packet=%s unit=%d input=%d opcode=0x%02x origin=0x%04x age=0x%04x flags=0x%04x code=%s ch=%s val=%s payload=%s",
                packet_seq,
                unit_id,
                input_index,
                frame.opcode,
                frame.origin,
                frame.age,
                frame.flags,
                f"0x{input_code:02x}" if input_code is not None else None,
                input_channel,
                input_value16,
                b2a(frame.payload),
            )
            return {
                "unit_id": unit_id,
                "button": button,
                "event": event,
                "message_type": 0x07,
                "message_position": frame.offset,
                "extra_data": None,
                "invocation_flags": frame.flags,
                "opcode": frame.opcode,
                "origin": frame.origin,
                "origin_unit_id": origin_unit_id,
                "origin_type": origin_type,
                "target": frame.target,
                "target_type": target_type,
                "age": frame.age,
                "origin_handle": frame.origin_handle,
                "payload": frame.payload,
                "payload_hex": b2a(frame.payload),
                "frame_offset": frame.offset,
                "input_index": input_index,
                "input_code": input_code,
                "input_b1": input_b1,
                "input_channel": input_channel,
                "input_value16": input_value16,
                "input_mapped_event": input_mapped_event,
                "packet_sequence": packet_seq,
                "arrival_sequence": arrival_sequence,
                "event_id": f"invoke:{frame.origin:04x}:{frame.age:04x}:{frame.opcode:02x}:{frame.target:04x}",
                "raw_packet": b2a(raw_packet) if raw_packet else None,
                "decrypted_data": b2a(data),
                "received_at": time.time(),
            }

        stats.frames_ignored += 1
        self._logger.debug(
            "[CASAMBI_INVOKE_IGNORED] packet=%s opcode=0x%02x origin=0x%04x target=0x%04x age=0x%04x flags=0x%04x payload=%s",
            packet_seq,
            frame.opcode,
            frame.origin,
            frame.target,
            frame.age,
            frame.flags,
            b2a(frame.payload),
        )
        return None
