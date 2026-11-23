import logging

from cryptography.exceptions import InvalidSignature
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
        packet = bytes(packet)
        packet = packet[:headerLen] + self._encryptInternal(packet[headerLen:], nonce)

        cmacCipher = CMAC(self._aes)
        cmacCipher.update(packet)
        packet += cmacCipher.finalize()
        return packet

    def decryptAndVerify(
        self, packet: bytes, nonce: bytes, headerLen: int = 4
    ) -> bytes:
        packet = bytes(packet)
        ciphertext, packetMac = packet[0:-16], packet[-16:]

        # Always decrypt for timing reasons
        plaintext = self._encryptInternal(ciphertext[headerLen:], nonce)

        cmacCipher = CMAC(self._aes)
        cmacCipher.update(ciphertext)
        cmacCipher.verify(packetMac)
        return plaintext

    def _encryptInternal(self, packet: bytes, nonce: bytes) -> bytes:
        if len(nonce) != 16:
            raise ValueError("Nonce must be 16 bytes long.")

        nonceBlock = bytearray(nonce)

        counter = 0
        result = b""
        for i in range(0, len(packet), 16):
            nonceBlock[12:] = counter.to_bytes(4, "little")
            block = _encHelper(self._blockCipher, bytes(nonceBlock))
            rem = min(i + 16, len(packet))
            result += _xor(block[: rem - i], packet[i:rem])
            counter += 1

        return result


class ClassicEncryptor:
    def __init__(self, key: bytes, sig_len: int) -> None:
        self._aes = AES(key)
        self._cipher = Cipher(AES(key), mode=ECB())
        self._sig_len = sig_len
        self._logger = logging.getLogger(__name__)

    def digest(self, packet: bytes, connhash: bytes) -> bytes:
        # We leave handling the auth level to the caller and expect the packet to start with the signature.

        if len(connhash) != 8:
            raise ValueError("Connhash must be 8 bytes long.")

        cmacCipher = CMAC(self._aes)
        cmacCipher.update(connhash + packet)
        cmac = cmacCipher.finalize()

        return cmac[: self._sig_len] + packet

    def verify(self, packet: bytes, connhash: bytes) -> bytes:
        # We leave handling the auth level to the caller and expect the packet to start with the signature.

        if len(connhash) != 8:
            raise ValueError("Connhash must be 8 bytes long.")

        cmacCipher = CMAC(self._aes)
        cmacCipher.update(connhash + packet[self._sig_len :])
        computedMac = cmacCipher.finalize()[: self._sig_len]
        pckMac = packet[: self._sig_len]

        # Time-constant comparison. Need to do this ourselves because the signature is not always 16 bytes long.
        result = True
        for i in range(self._sig_len):
            if computedMac[i] != pckMac[i]:
                result = False

        if not result:
            self._logger.warning("Signature verification failed.")
            raise InvalidSignature("Signature verification failed.")

        return packet[self._sig_len :]
