import logging
import sys
from binascii import a2b_hex
from collections.abc import Callable
from typing import Any

from src.CasambiBt._client import CasambiClient, IncommingPacketType

# Set up basic logging to see the output
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

def dummy_data_callback(packet_type: IncommingPacketType, data: dict[str, Any]) -> None:
    print(f"Dummy Callback received - Type: {packet_type}, Data: {data}")


if __name__ == "__main__":
    # Create a dummy CasambiClient instance for testing
    # Note: This instance is not fully functional as it lacks network and encryption setup.
    # It's only for testing the _parseSwitchEvent method.
    class DummyNetwork:
        protocolVersion = 10
        keyStore = None

    dummy_client = CasambiClient(
        address_or_device="AA:BB:CC:DD:EE:FF",
        dataCallback=dummy_data_callback,
        disonnectedCallback=lambda: None,
        network=DummyNetwork(),
    )

    # --- Paste your log data here ---
    # Example from your logs: b'0803201f851f06000599000229002a0f001f060003'
    # You can replace this with any other hex string from your logs.
    hex_data = "0803201f851f06000599000229002a0f001f060003"

    # Convert the hex string to bytes
    try:
        binary_data = a2b_hex(hex_data)
        dummy_client._parseSwitchEvent(binary_data)
    except Exception as e:
        print(f"Error processing hex data: {e}")
        
        
# 2025-06-30 15:04:54.384 INFO (MainThread) [CasambiBt._encryption] Decrypting packet: b'0700008013284dc55fec63ef9e9f547fe5b067d82033ca1743d24e78081303fa8691ee238f3092d06b01' of len 42 with nonce b'070000803e4d047d297ca431f9bcc130'
# 2025-06-30 15:04:54.385 INFO (MainThread) [CasambiBt._client] Parsing incoming switch event... Data: b'0803201f851f06000599000229002a0f001f060003'
# 2025-06-30 15:04:54.385 INFO (MainThread) [CasambiBt._client] Parsed switch event: sensor_type=8, flags=0x03, length=3, button=0, unit_id=31, action=0x85 (button_press), value=b'1f'
# 2025-06-30 15:04:54.385 INFO (MainThread) [CasambiBt._casambi] Incomming data callback of type 7
# 2025-06-30 15:04:54.385 WARNING (MainThread) [CasambiBt._casambi] Handler for type 7 not implemented!
# 2025-06-30 15:04:54.385 INFO (MainThread) [CasambiBt._client] Remaining data in switch event packet: b'06000599000229002a0f001f060003'
# 2025-06-30 15:04:54.389 INFO (MainThread) [CasambiBt._encryption] Decrypting packet: b'08000080723fa43e8ea7b0914935f5d299cf67293e4cdf0813ff6de83b44' of len 30 with nonce b'080000803e4d047d297ca431f9bcc130'
# 2025-06-30 15:04:54.389 INFO (MainThread) [CasambiBt._client] Parsing incoming switch event... Data: b'29002a08001f060003'
# 2025-06-30 15:04:54.389 INFO (MainThread) [CasambiBt._client] Parsed switch event: sensor_type=41, flags=0x00, length=3, button=10, unit_id=8, action=0x00 (button_press), value=b'1f'
# 2025-06-30 15:04:54.389 INFO (MainThread) [CasambiBt._casambi] Incomming data callback of type 7
# 2025-06-30 15:04:54.389 WARNING (MainThread) [CasambiBt._casambi] Handler for type 7 not implemented!
# 2025-06-30 15:04:54.389 INFO (MainThread) [CasambiBt._client] Remaining data in switch event packet: b'060003'
# 2025-06-30 15:04:54.422 INFO (MainThread) [CasambiBt._encryption] Decrypting packet: b'090000805aa2ca96c60f660c875be5d9b834e720efe60d6d63dc03de3cd1' of len 30 with nonce b'090000803e4d047d297ca431f9bcc130'
# 2025-06-30 15:04:54.422 INFO (MainThread) [CasambiBt._client] Parsing incoming switch event... Data: b'29002a05001f060009'
# 2025-06-30 15:04:54.422 INFO (MainThread) [CasambiBt._client] Parsed switch event: sensor_type=41, flags=0x00, length=3, button=10, unit_id=5, action=0x00 (button_press), value=b'1f'
# 2025-06-30 15:04:54.422 INFO (MainThread) [CasambiBt._casambi] Incomming data callback of type 7
# 2025-06-30 15:04:54.422 WARNING (MainThread) [CasambiBt._casambi] Handler for type 7 not implemented!
# 2025-06-30 15:04:54.423 INFO (MainThread) [CasambiBt._client] Remaining data in switch event packet: b'060009'
# 2025-06-30 15:04:54.459 INFO (MainThread) [CasambiBt._encryption] Decrypting packet: b'0a0000809bc5a3597053f4b08f99440041e679cf348dfe2d2b27945a25d2fa2f5a9906cffab23c5ae727' of len 42 with nonce b'0a0000803e4d047d297ca431f9bcc130'
# 2025-06-30 15:04:54.460 INFO (MainThread) [CasambiBt._client] Parsing incoming switch event... Data: b'0803201f851f06000c99000229002a02001f06000b'
# 2025-06-30 15:04:54.460 INFO (MainThread) [CasambiBt._client] Parsed switch event: sensor_type=8, flags=0x03, length=3, button=0, unit_id=31, action=0x85 (button_press), value=b'1f'
# 2025-06-30 15:04:54.460 INFO (MainThread) [CasambiBt._casambi] Incomming data callback of type 7
# 2025-06-30 15:04:54.460 WARNING (MainThread) [CasambiBt._casambi] Handler for type 7 not implemented!
# 2025-06-30 15:04:54.460 INFO (MainThread) [CasambiBt._client] Remaining data in switch event packet: b'06000c99000229002a02001f06000b'
# 2025-06-30 15:04:54.534 INFO (MainThread) [CasambiBt._encryption] Decrypting packet: b'0b0000806ce5763c37efa6aea2cadeea568a50b9613a1cd637723dfb9db3f4baa9' of len 33 with nonce b'0b0000803e4d047d297ca431f9bcc130'
# 2025-06-30 15:04:54.534 INFO (MainThread) [CasambiBt._client] Parsing incoming switch event... Data: b'0803201f8a1f060005190010'
# 2025-06-30 15:04:54.535 INFO (MainThread) [CasambiBt._client] Parsed switch event: sensor_type=8, flags=0x03, length=3, button=0, unit_id=31, action=0x8a (button_release), value=b'1f'
# 2025-06-30 15:04:54.535 INFO (MainThread) [CasambiBt._casambi] Incomming data callback of type 7
# 2025-06-30 15:04:54.535 WARNING (MainThread) [CasambiBt._casambi] Handler for type 7 not implemented!
# 2025-06-30 15:04:54.535 INFO (MainThread) [CasambiBt._client] Remaining data in switch event packet: b'060005190010'
# 2025-06-30 15:04:54.609 INFO (MainThread) [CasambiBt._encryption] Decrypting packet: b'0c00008080cde209cc61ea29c6a524450285f0b55750e3ac4acbd8b1039d1c4224' of len 33 with nonce b'0c0000803e4d047d297ca431f9bcc130'
# 2025-06-30 15:04:54.609 INFO (MainThread) [CasambiBt._client] Parsing incoming switch event... Data: b'0803201f8a1f06000e190010'
# 2025-06-30 15:04:54.609 INFO (MainThread) [CasambiBt._client] Parsed switch event: sensor_type=8, flags=0x03, length=3, button=0, unit_id=31, action=0x8a (button_release), value=b'1f'
# 2025-06-30 15:04:54.609 INFO (MainThread) [CasambiBt._casambi] Incomming data callback of type 7
# 2025-06-30 15:04:54.609 WARNING (MainThread) [CasambiBt._casambi] Handler for type 7 not implemented!
# 2025-06-30 15:04:54.609 INFO (MainThread) [CasambiBt._client] Remaining data in switch event packet: b'06000e190010'
# 2025-06-30 15:04:54.685 INFO (MainThread) [CasambiBt._encryption] Decrypting packet: b'0d00008091f0aca22ba3a614948e42ade869ff1d3c780004b32e5cac75acb55568' of len 33 with nonce b'0d0000803e4d047d297ca431f9bcc130'
# 2025-06-30 15:04:54.686 INFO (MainThread) [CasambiBt._client] Parsing incoming switch event... Data: b'0803201f8a1f060015190010'
# 2025-06-30 15:04:54.686 INFO (MainThread) [CasambiBt._client] Parsed switch event: sensor_type=8, flags=0x03, length=3, button=0, unit_id=31, action=0x8a (button_release), value=b'1f'
# 2025-06-30 15:04:54.686 INFO (MainThread) [CasambiBt._casambi] Incomming data callback of type 7
# 2025-06-30 15:04:54.686 WARNING (MainThread) [CasambiBt._casambi] Handler for type 7 not implemented!
# 2025-06-30 15:04:54.686 INFO (MainThread) [CasambiBt._client] Remaining data in switch event packet: b'060015190010'
# 2025-06-30 15:04:54.722 INFO (MainThread) [CasambiBt._encryption] Decrypting packet: b'0e0000802e3ae4ee0e658c1f3fa9117d7a858c028ebfaff727207e0dd83c8f90' of len 32 with nonce b'0e0000803e4d047d297ca431f9bcc130'
# 2025-06-30 15:04:54.723 INFO (MainThread) [CasambiBt._client] Parsing incoming switch event... Data: b'1002430a981f120002020b'
# 2025-06-30 15:04:54.723 INFO (MainThread) [CasambiBt._client] Parsed switch event: sensor_type=16, flags=0x02, length=5, button=3, unit_id=10, action=0x98 (button_press), value=b'1f1200'
# 2025-06-30 15:04:54.723 INFO (MainThread) [CasambiBt._casambi] Incomming data callback of type 7
# 2025-06-30 15:04:54.723 WARNING (MainThread) [CasambiBt._casambi] Handler for type 7 not implemented!
# 2025-06-30 15:04:54.723 INFO (MainThread) [CasambiBt._client] Remaining data in switch event packet: b'02020b'
# 2025-06-30 15:04:54.728 INFO (MainThread) [CasambiBt._encryption] Decrypting packet: b'0f0000802fce74fd7e49ded8f2f078206a88be0f7acc3065be66ad143469f913' of len 32 with nonce b'0f0000803e4d047d297ca431f9bcc130'
# 2025-06-30 15:04:54.728 INFO (MainThread) [CasambiBt._client] Parsing incoming switch event... Data: b'10024308611f120002020b'
# 2025-06-30 15:04:54.728 INFO (MainThread) [CasambiBt._client] Parsed switch event: sensor_type=16, flags=0x02, length=5, button=3, unit_id=8, action=0x61 (button_press), value=b'1f1200'
# 2025-06-30 15:04:54.728 INFO (MainThread) [CasambiBt._casambi] Incomming data callback of type 7
# 2025-06-30 15:04:54.728 WARNING (MainThread) [CasambiBt._casambi] Handler for type 7 not implemented!
# 2025-06-30 15:04:54.729 INFO (MainThread) [CasambiBt._client] Remaining data in switch event packet: b'02020b'
# 2025-06-30 15:04:54.834 INFO (MainThread) [CasambiBt._encryption] Decrypting packet: b'10000080666c9b6cbfba4d2dd55d0db18b3aa4cf5291e89063369c883fb3' of len 30 with nonce b'100000803e4d047d297ca431f9bcc130'
# 2025-06-30 15:04:54.834 INFO (MainThread) [CasambiBt._client] Parsing incoming switch event... Data: b'29002a02001f060030'
# 2025-06-30 15:04:54.834 INFO (MainThread) [CasambiBt._client] Parsed switch event: sensor_type=41, flags=0x00, length=3, button=10, unit_id=2, action=0x00 (button_press), value=b'1f'
# 2025-06-30 15:04:54.834 INFO (MainThread) [CasambiBt._casambi] Incomming data callback of type 7
# 2025-06-30 15:04:54.834 WARNING (MainThread) [CasambiBt._casambi] Handler for type 7 not implemented!
# 2025-06-30 15:04:54.835 INFO (MainThread) [CasambiBt._client] Remaining data in switch event packet: b'060030'
# 2025-06-30 15:04:58.170 INFO (MainThread) [CasambiBt._encryption] Decrypting packet: b'11000080e1595479d644d5ed63be8bd8df04874627023b75cc783d7b9f1d' of len 30 with nonce b'110000803e4d047d297ca431f9bcc130'
# 2025-06-30 15:04:58.171 INFO (MainThread) [CasambiBt._client] Parsing incoming switch event... Data: b'29002a02001f06017d'
# 2025-06-30 15:04:58.171 INFO (MainThread) [CasambiBt._client] Parsed switch event: sensor_type=41, flags=0x00, length=3, button=10, unit_id=2, action=0x00 (button_press), value=b'1f'
# 2025-06-30 15:04:58.171 INFO (MainThread) [CasambiBt._casambi] Incomming data callback of type 7
# 2025-06-30 15:04:58.171 WARNING (MainThread) [CasambiBt._casambi] Handler for type 7 not implemented!
# 2025-06-30 15:04:58.171 INFO (MainThread) [CasambiBt._client] Remaining data in switch event packet: b'06017d'