from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class InvocationFrame:
    """One INVOCATION frame.

    Ground truth: casambi-android `v1.C1775b.Q(Q2.h)` parses:
    - flags:u16 (big-endian)
    - opcode:u8
    - origin:u16
    - target:u16
    - age:u16
    - origin_handle?:u8 (if flags & 0x0200)
    - payload: flags & 0x3f bytes
    """

    flags: int
    opcode: int
    origin: int
    target: int
    age: int
    origin_handle: int | None
    payload: bytes
    offset: int  # start offset of this frame in the decrypted type=7 payload

    @property
    def payload_len(self) -> int:
        return self.flags & 0x3F


_FLAG_HAS_ORIGIN_HANDLE: Final[int] = 0x0200


def parse_invocation_stream(
    data: bytes, *, logger: logging.Logger | None = None
) -> list[InvocationFrame]:
    """Parse decrypted packet type=7 payload into INVOCATION frames."""

    frames: list[InvocationFrame] = []
    pos = 0

    # Android bails out if < 9 bytes remain.
    while len(data) - pos >= 9:
        frame_offset = pos

        flags = int.from_bytes(data[pos : pos + 2], "big")
        pos += 2

        opcode = data[pos]
        pos += 1

        origin = int.from_bytes(data[pos : pos + 2], "big")
        pos += 2

        target = int.from_bytes(data[pos : pos + 2], "big")
        pos += 2

        age = int.from_bytes(data[pos : pos + 2], "big")
        pos += 2

        origin_handle: int | None = None
        if flags & _FLAG_HAS_ORIGIN_HANDLE:
            if pos >= len(data):
                if logger:
                    logger.debug(
                        "INVOCATION frame truncated at origin_handle (offset=%d flags=0x%04x).",
                        frame_offset,
                        flags,
                    )
                break
            origin_handle = data[pos]
            pos += 1

        payload_len = flags & 0x3F
        if pos + payload_len > len(data):
            if logger:
                logger.debug(
                    "INVOCATION frame truncated at payload (offset=%d flags=0x%04x payload_len=%d remaining=%d).",
                    frame_offset,
                    flags,
                    payload_len,
                    len(data) - pos,
                )
            break

        payload = data[pos : pos + payload_len]
        pos += payload_len

        frames.append(
            InvocationFrame(
                flags=flags,
                opcode=opcode,
                origin=origin,
                target=target,
                age=age,
                origin_handle=origin_handle,
                payload=payload,
                offset=frame_offset,
            )
        )

    if logger and pos != len(data):
        logger.debug(
            "INVOCATION stream has %d trailing bytes (parsed=%d total=%d).",
            len(data) - pos,
            pos,
            len(data),
        )

    return frames

