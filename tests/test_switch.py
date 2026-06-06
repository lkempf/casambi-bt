"""Tests for SwitchEventDecoder — origin-based retransmit deduplication."""

import struct
from time import monotonic

from CasambiBt._switch import (
    _DEDUP_WINDOW_SECONDS,
    _TARGET_TYPE_BUTTON,
    _TARGET_TYPE_INPUT,
    ButtonEventType,
    SwitchEventDecoder,
)

# ---------------------------------------------------------------------------
# Helpers to build raw INVOCATION frames
# ---------------------------------------------------------------------------
# Frame layout (from _invocation.py):
#   flags:u16 (big-endian)  — low 6 bits = payload_len
#   opcode:u8
#   origin:u16 (big-endian)
#   target:u16 (big-endian) — low byte = target_type, high byte = unit_id
#   age:u16 (big-endian)
#   payload: payload_len bytes

_OPCODE_BUTTON_0 = 29  # FunctionButtonEvent0 → button 1
_OPCODE_INPUT_0 = 64  # FunctionNotifyInput0 → button 1
_UNIT_ID = 0x15
_AGE = 0x0001


def _button_frame(origin: int, payload: bytes = b"\xf9") -> bytes:
    """Build a 0x06 button-stream INVOCATION frame.

    Pass the raw origin value directly.  The decoder derives PRESS/RELEASE from
    bit 1: origin & 0x02 == 0 → PRESS, != 0 → RELEASE.

    Typical PTM215B pattern:
      - PRESS:   origin = 0xXXX0  (bit 1 clear)
      - RELEASE: origin = 0xXXX2  (bit 1 set, same counter bits)
      - Next physical event: counter bits incremented (e.g. 0xXXX4 / 0xXXX6)
    """
    payload_len = len(payload)
    flags = payload_len & 0x3F
    target = (_UNIT_ID << 8) | _TARGET_TYPE_BUTTON
    return (
        struct.pack(">HBHHH", flags, _OPCODE_BUTTON_0, origin, target, _AGE) + payload
    )


def _input_frame(origin: int, event_code: int, payload_extra: bytes = b"") -> bytes:
    """Build a 0x12 input-stream INVOCATION frame."""
    payload = bytes([event_code]) + payload_extra
    payload_len = len(payload)
    flags = payload_len & 0x3F
    target = (_UNIT_ID << 8) | _TARGET_TYPE_INPUT
    return struct.pack(">HBHHH", flags, _OPCODE_INPUT_0, origin, target, _AGE) + payload


# ---------------------------------------------------------------------------
# 0x06 button stream tests
# ---------------------------------------------------------------------------


class TestButtonStreamDedup:
    # PTM215B origin convention used in these tests:
    #   0xXXX0 → PRESS  (bit 1 = 0)
    #   0xXXX2 → RELEASE (bit 1 = 1, same counter bits)
    #   0xXXX4 → next physical PRESS  (counter incremented, bit 1 = 0)

    def test_sequential_retransmits_deduplicated(self):
        """3 identical PRESS frames (same origin) → exactly 1 PRESS emitted."""
        dec = SwitchEventDecoder()
        frame = _button_frame(origin=0x15B0)  # PRESS (bit 1 = 0)

        results = []
        for _ in range(3):
            results.extend(dec.decode(frame, packet_seq=1))

        assert len(results) == 1
        assert results[0].event == ButtonEventType.PRESS

    def test_press_then_release_both_emitted(self):
        """PRESS (origin 0x15B0) then RELEASE (origin 0x15B2) → both emitted."""
        dec = SwitchEventDecoder()
        press_frame = _button_frame(origin=0x15B0)  # bit 1 = 0 → PRESS
        release_frame = _button_frame(origin=0x15B2)  # bit 1 = 1 → RELEASE

        results = dec.decode(press_frame, packet_seq=1)
        results += dec.decode(release_frame, packet_seq=2)

        assert len(results) == 2
        assert results[0].event == ButtonEventType.PRESS
        assert results[1].event == ButtonEventType.RELEASE

    def test_late_press_retransmit_after_release_suppressed(self):
        """Core regression test: late PRESS retransmit (same origin) arriving
        after RELEASE must be suppressed, not emitted as a phantom PRESS."""
        dec = SwitchEventDecoder()
        press_frame = _button_frame(origin=0x15B0)  # PRESS
        release_frame = _button_frame(origin=0x15B2)  # RELEASE (different origin)
        late_press_retransmit = _button_frame(origin=0x15B0)  # same origin as PRESS

        results = dec.decode(press_frame, packet_seq=1)  # PRESS accepted
        results += dec.decode(release_frame, packet_seq=2)  # RELEASE accepted
        results += dec.decode(late_press_retransmit, packet_seq=3)  # must be suppressed

        assert len(results) == 2
        assert results[0].event == ButtonEventType.PRESS
        assert results[1].event == ButtonEventType.RELEASE

    def test_genuine_second_press_accepted_with_new_origin(self):
        """A new physical PRESS (different origin, counter incremented) is accepted
        immediately even within the dedup window."""
        dec = SwitchEventDecoder()
        first_press = _button_frame(origin=0x15B0)  # PRESS, counter N
        release = _button_frame(origin=0x15B2)  # RELEASE, counter N
        second_press = _button_frame(origin=0x15B4)  # PRESS, counter N+1 (new origin)

        results = dec.decode(first_press, packet_seq=1)
        results += dec.decode(release, packet_seq=2)
        results += dec.decode(second_press, packet_seq=3)

        assert len(results) == 3
        assert results[0].event == ButtonEventType.PRESS
        assert results[1].event == ButtonEventType.RELEASE
        assert results[2].event == ButtonEventType.PRESS

    def test_same_origin_accepted_after_window_expires(self):
        """Edge case: after the dedup window expires, the same origin is accepted
        again (guards against sequence counter wrap-around)."""
        dec = SwitchEventDecoder()
        origin = 0x15B0
        frame = _button_frame(origin=origin)

        # Inject a stale entry as if it was recorded before the window.
        past = monotonic() - _DEDUP_WINDOW_SECONDS - 0.1
        dec._seen_origins[(_UNIT_ID, 0, origin)] = past

        results = dec.decode(frame, packet_seq=1)

        assert len(results) == 1
        assert results[0].event == ButtonEventType.PRESS

    def test_different_origin_always_accepted_within_window(self):
        """Even within the window, a different origin (genuine new event) is accepted."""
        dec = SwitchEventDecoder()
        first_press = _button_frame(origin=0xAAA0)  # PRESS
        second_press = _button_frame(origin=0xAAA4)  # new PRESS, different counter

        results = dec.decode(first_press, packet_seq=1)
        results += dec.decode(second_press, packet_seq=2)

        assert len(results) == 2

    def test_button_label_is_one_based(self):
        """button field must equal button_event_index + 1."""
        dec = SwitchEventDecoder()
        frame = _button_frame(origin=0x1000)
        events = dec.decode(frame, packet_seq=1)
        assert events[0].button == events[0].button_event_index + 1

    def test_unit_id_and_target_type_extracted(self):
        """unit_id and target_type are correctly parsed from the target field."""
        dec = SwitchEventDecoder()
        frame = _button_frame(origin=0x1000)
        events = dec.decode(frame, packet_seq=1)
        assert events[0].unit_id == _UNIT_ID
        assert events[0].target_type == _TARGET_TYPE_BUTTON


# ---------------------------------------------------------------------------
# 0x12 input stream tests (HOLD / RELEASE_AFTER_HOLD)
# ---------------------------------------------------------------------------


class TestInputStreamDedup:
    def test_hold_retransmits_deduplicated(self):
        """3 identical HOLD frames → exactly 1 HOLD emitted."""
        dec = SwitchEventDecoder()
        frame = _input_frame(origin=0x15C0, event_code=0x09)  # HOLD

        results = []
        for _ in range(3):
            results.extend(dec.decode(frame, packet_seq=1))

        assert len(results) == 1
        assert results[0].event == ButtonEventType.HOLD

    def test_press_and_release_from_input_stream_ignored(self):
        """0x12 PRESS and RELEASE are authoritative only from 0x06 → ignored here."""
        dec = SwitchEventDecoder()
        press_frame = _input_frame(origin=0x0001, event_code=0x01)  # PRESS code
        release_frame = _input_frame(origin=0x0002, event_code=0x02)  # RELEASE code

        results = dec.decode(press_frame, packet_seq=1)
        results += dec.decode(release_frame, packet_seq=2)

        assert results == []

    def test_late_hold_retransmit_suppressed(self):
        """HOLD retransmit arriving after RELEASE_AFTER_HOLD is accepted is suppressed."""
        dec = SwitchEventDecoder()
        hold_origin = 0x15C0
        rah_origin = 0x15C1

        hold_frame = _input_frame(origin=hold_origin, event_code=0x09)
        rah_frame = _input_frame(origin=rah_origin, event_code=0x0C)
        late_hold = _input_frame(origin=hold_origin, event_code=0x09)

        results = dec.decode(hold_frame, packet_seq=1)
        results += dec.decode(rah_frame, packet_seq=2)
        results += dec.decode(late_hold, packet_seq=3)

        assert len(results) == 2
        assert results[0].event == ButtonEventType.HOLD
        assert results[1].event == ButtonEventType.RELEASE_AFTER_HOLD


# ---------------------------------------------------------------------------
# State reset tests
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_clears_dedup_state(self):
        """After reset(), a frame with the same origin as a prior event is accepted."""
        dec = SwitchEventDecoder()
        origin = 0x15B0
        frame = _button_frame(origin=origin)

        dec.decode(frame, packet_seq=1)  # accepted, origin recorded
        dec.reset()
        results = dec.decode(frame, packet_seq=2)  # same origin, but state cleared

        assert len(results) == 1
        assert results[0].event == ButtonEventType.PRESS

    def test_reset_called_on_reconnect_does_not_suppress_first_event(self):
        """After reconnect (reset), the very first event is never suppressed."""
        dec = SwitchEventDecoder()
        dec.reset()
        frame = _button_frame(origin=0xDEAD)
        results = dec.decode(frame, packet_seq=1)
        assert len(results) == 1
