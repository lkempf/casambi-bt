import binascii
import logging
import sys
from binascii import b2a_hex as b2a

from cryptography.hazmat.primitives.ciphers import Cipher
from cryptography.hazmat.primitives.ciphers.algorithms import AES
from cryptography.hazmat.primitives.ciphers.modes import CBC, ECB
from cryptography.hazmat.primitives.cmac import CMAC


def _xor(data: bytes, key: bytes) -> bytes:
    assert len(data) == len(key)
    return bytes(a ^ b for a, b in zip(data, key))


def _encHelper(cipher: Cipher, input: bytes) -> bytes:
    assert len(input) % 16 == 0

    context = cipher.encryptor()
    return context.update(input) + context.finalize()


class Encryptor:
    def __init__(self, key: bytes) -> None:
        self._aes = AES(key)
        self._blockCipher = Cipher(AES(key), mode=ECB())
        self._cmacCipher = Cipher(AES(key), mode=CBC(b"\0" * 16))
        self._logger = logging.getLogger(__name__)

    def encryptThenMac(self, packet: bytes, nonce: bytes, headerLen: int = 4) -> bytes:
        self._logger.info(
            f"Encrypting packet: {b2a(packet)} of len {len(packet)} with nonce {b2a(nonce)}"
        )
        packet = bytes(packet)
        packet = packet[:headerLen] + self._encryptInternal(packet[headerLen:], nonce)
        self._logger.debug(f"Encrypted packet: {b2a(packet)}")

        cmacCipher = CMAC(self._aes)
        cmacCipher.update(packet)
        packet += cmacCipher.finalize()
        self._logger.debug(f"Authenticated packet: {b2a(packet)}")

        return packet

    def decryptAndVerify(
        self, packet: bytes, nonce: bytes, headerLen: int = 4
    ) -> bytes:
        self._logger.info(
            f"Decrypting packet: {b2a(packet)} of len {len(packet)} with nonce {b2a(nonce)}"
        )
        packet = bytes(packet)
        ciphertext, packetMac = packet[0:-16], packet[-16:]

        # Always decrypt for timing reasons
        plaintext = self._encryptInternal(ciphertext[headerLen:], nonce)
        self._logger.debug(f"Decrypted package: {b2a(plaintext)}")

        cmacCipher = CMAC(self._aes)
        cmacCipher.update(ciphertext)
        cmacCipher.verify(packetMac)
        return plaintext

    def _encryptInternal(self, packet: bytes, nonce: bytes) -> bytes:
        if len(nonce) != 16:
            raise ValueError("Nonce must be 16 bytes long.")

        nonce = bytearray(nonce)

        counter = 0
        result = b""
        for i in range(0, len(packet), 16):
            nonce[12:] = counter.to_bytes(4, "little")
            block = _encHelper(self._blockCipher, nonce)
            rem = min(i + 16, len(packet))
            result += _xor(block[: rem - i], packet[i:rem])
            counter += 1

        return result

    # TODO: Replace with CMAC primitive
    def cmac(self, data: bytes) -> bytes:
        encZeros = _encHelper(self._blockCipher, bytes(16))
        encZeros = self._randomTransform(encZeros)

        # pad with zeros
        pakLen = len(data)
        if pakLen % 16 != 0:
            data += b"\x80"
            data += bytes((((pakLen // 16) + 1) * 16) - pakLen)[1:]

            encZeros = self._randomTransform(encZeros)

        mac = bytes(16)
        if len(data) > 16:
            mac = _encHelper(self._cmacCipher, data[:-16])[-16:]

        lastInput = _xor(data[-16:], _xor(encZeros, mac))
        result = _encHelper(self._blockCipher, lastInput)
        self._logger.debug(f"CMAC is {b2a(result)}")
        return result

    def _randomTransform(self, block: bytes) -> bytes:
        highestBit = (block[0] & 128) != 0
        block = self._shiftBlock(block)
        if highestBit:
            block = block[:-1] + bytes([block[-1] ^ 135])
        return block

    def _shiftBlock(self, block: bytes) -> bytes:
        assert len(block) == 16

        blockInt = int.from_bytes(block, "big") << 1
        return int.to_bytes(blockInt, 17, "big")[1:]
