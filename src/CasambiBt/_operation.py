import struct
from enum import IntEnum, unique


@unique
class OpCode(IntEnum):
    Response = 0
    SetLevel = 1
    SetState = 48


class OperationsContext:
    origin: int = 1
    lifetime: int = 5

    def prepareOperation(self, op: OpCode, target: int, payload: bytes) -> bytes:
        if len(payload) > 63:
            raise ValueError("Payload too long")

        flags = (self.lifetime & 15) << 11 | len(payload)

        packet = struct.pack(">hbhhh", flags, op, self.origin, target, 0)
        self.origin += 1

        return packet + payload
