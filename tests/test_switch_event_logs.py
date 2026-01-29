from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

# Allow tests to run without installing the package.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from CasambiBt._switch_events import SwitchEventStreamDecoder  # noqa: E402


_HEX_RE = re.compile(r"b'([0-9a-fA-F]+)'")


def _extract_switch_payloads_from_log(log_path: Path) -> list[bytes]:
    """Extract decrypted type=7 payloads (without the leading type byte) from a log file."""

    payloads: list[bytes] = []
    text = log_path.read_text(encoding="utf-8", errors="replace")

    for line in text.splitlines():
        # New/desired stable format:
        #   [CASAMBI_SWITCH_PACKET] Full data #N: hex=b'...' len=...
        if "[CASAMBI_SWITCH_PACKET]" in line:
            m = _HEX_RE.search(line)
            if m:
                payloads.append(bytes.fromhex(m.group(1)))
            continue

        # Existing HA-style format:
        #   Parsing incoming switch event packet #... Data: b'...'
        if "Parsing incoming switch event packet" in line and "Data:" in line:
            m = _HEX_RE.search(line)
            if m:
                payloads.append(bytes.fromhex(m.group(1)))
            continue

        # Older capture format:
        #   [CASAMBI_DECRYPTED] Type=7 #N: b'07...'
        if "[CASAMBI_DECRYPTED]" in line and "Type=7" in line:
            m = _HEX_RE.search(line)
            if m:
                decrypted = bytes.fromhex(m.group(1))
                if decrypted and decrypted[0] == 0x07:
                    payloads.append(decrypted[1:])
            continue

    return payloads


class TestSwitchEventsFromLogs(unittest.TestCase):
    def test_wired_unit20_button1_single_press(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        log_path = repo_root / "testlogs" / "single_press_wired_unit_20_button_1.log"
        payloads = _extract_switch_payloads_from_log(log_path)
        self.assertGreater(len(payloads), 0, "No switch payloads extracted from log.")

        dec = SwitchEventStreamDecoder()
        events: list[dict] = []
        for p in payloads:
            evs, _ = dec.decode(p)
            events.extend(evs)

        semantic = [e for e in events if e.get("event") in ("button_press", "button_release", "button_hold", "button_release_after_hold")]
        self.assertEqual([e["event"] for e in semantic], ["button_press", "button_release"])
        self.assertEqual(semantic[0]["unit_id"], 20)
        self.assertEqual(semantic[0]["button"], 1)
        self.assertEqual(semantic[1]["unit_id"], 20)
        self.assertEqual(semantic[1]["button"], 1)

    def test_wired_unit20_button1_long_press(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        for fname in (
            "long_press_wired_unit_20_button_1.log",
            "long_press_wired_unit_20_button_1_sample2.log",
        ):
            log_path = repo_root / "testlogs" / fname
            payloads = _extract_switch_payloads_from_log(log_path)
            self.assertGreater(len(payloads), 0, f"No switch payloads extracted from {fname}.")

            dec = SwitchEventStreamDecoder()
            events: list[dict] = []
            for p in payloads:
                evs, _ = dec.decode(p)
                events.extend(evs)

            semantic = [e for e in events if e.get("event") in ("button_press", "button_release", "button_hold", "button_release_after_hold")]
            # Wired long press reports release-after-hold (0x0c), not a separate hold stream in samples.
            self.assertEqual([e["event"] for e in semantic], ["button_press", "button_release_after_hold"])
            self.assertEqual(semantic[0]["unit_id"], 20)
            self.assertEqual(semantic[0]["button"], 1)
            self.assertEqual(semantic[1]["unit_id"], 20)
            self.assertEqual(semantic[1]["button"], 1)

    def test_wireless_unit31_button3_single_press(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        log_path = repo_root / "testlogs" / "single_press_wireless_unit_31_button_3.log"
        payloads = _extract_switch_payloads_from_log(log_path)
        self.assertGreater(len(payloads), 0, "No switch payloads extracted from log.")

        dec = SwitchEventStreamDecoder()
        events: list[dict] = []
        for p in payloads:
            evs, _ = dec.decode(p)
            events.extend(evs)

        btn_events = [e for e in events if e.get("event") in ("button_press", "button_release")]
        # After correct INVOCATION parsing + same-state suppression, this becomes one press + one release.
        self.assertEqual([e["event"] for e in btn_events], ["button_press", "button_release"])
        self.assertEqual(btn_events[0]["unit_id"], 31)
        self.assertEqual(btn_events[0]["button"], 3)
        self.assertEqual(btn_events[1]["unit_id"], 31)
        self.assertEqual(btn_events[1]["button"], 3)

    def test_wireless_unit31_button1_long_press_then_release(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        log_path = repo_root / "testlogs" / "long_press_then_release_wireless_unit_31_button_1.log"
        payloads = _extract_switch_payloads_from_log(log_path)
        self.assertGreater(len(payloads), 0, "No switch payloads extracted from log.")

        dec = SwitchEventStreamDecoder()
        events: list[dict] = []
        for p in payloads:
            evs, _ = dec.decode(p)
            events.extend(evs)

        semantic = [e for e in events if e.get("event") in ("button_press", "button_release", "button_hold", "button_release_after_hold")]
        # Long press: press, (optional hold), release, (optional release-after-hold from input stream)
        self.assertGreaterEqual(len(semantic), 2)
        self.assertEqual(semantic[0]["event"], "button_press")
        self.assertIn(semantic[-1]["event"], ("button_release", "button_release_after_hold"))
        self.assertEqual(semantic[0]["unit_id"], 31)
        self.assertEqual(semantic[0]["button"], 1)
        self.assertEqual(semantic[-1]["unit_id"], 31)
        self.assertEqual(semantic[-1]["button"], 1)

        # Ensure no consecutive same-state spam remains.
        for prev, cur in zip(semantic, semantic[1:]):
            self.assertNotEqual(prev["event"], cur["event"])

    def test_android_capture_button_label_mapping(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]

        # u32-b1.log should decode as button 1 press+release.
        log_b1 = repo_root / "casambi-android" / "u32-b1.log"
        payloads_b1 = _extract_switch_payloads_from_log(log_b1)
        dec1 = SwitchEventStreamDecoder()
        events_b1: list[dict] = []
        for p in payloads_b1:
            evs, _ = dec1.decode(p)
            events_b1.extend(evs)
        btn_b1 = [e for e in events_b1 if e.get("event") in ("button_press", "button_release")]
        self.assertEqual([e["event"] for e in btn_b1[:2]], ["button_press", "button_release"])
        self.assertEqual(btn_b1[0]["unit_id"], 32)
        self.assertEqual(btn_b1[0]["button"], 1)
        self.assertEqual(btn_b1[0]["button_event_index"], 1)

        # u32-b4.log should decode as button 4 press+release (ButtonEvent0 -> label 4).
        log_b4 = repo_root / "casambi-android" / "u32-b4.log"
        payloads_b4 = _extract_switch_payloads_from_log(log_b4)
        dec4 = SwitchEventStreamDecoder()
        events_b4: list[dict] = []
        for p in payloads_b4:
            evs, _ = dec4.decode(p)
            events_b4.extend(evs)
        btn_b4 = [e for e in events_b4 if e.get("event") in ("button_press", "button_release")]
        self.assertEqual([e["event"] for e in btn_b4[:2]], ["button_press", "button_release"])
        self.assertEqual(btn_b4[0]["unit_id"], 32)
        self.assertEqual(btn_b4[0]["button"], 4)
        self.assertEqual(btn_b4[0]["button_event_index"], 0)

    def test_notify_input_fields_are_exposed(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        log_path = repo_root / "testlogs" / "another_wireless_single_press.log"
        payloads = _extract_switch_payloads_from_log(log_path)
        self.assertGreater(len(payloads), 0, "No switch payloads extracted from log.")

        dec = SwitchEventStreamDecoder()
        events: list[dict] = []
        for p in payloads:
            evs, _ = dec.decode(p)
            events.extend(evs)

        # In the captured log we have a NotifyInput frame with payload 0209:
        # input_code=0x02 (release), channel=(0x09&7)=1, value16 absent (len=2).
        notify = [
            e
            for e in events
            if e.get("target_type") == 0x12 and e.get("opcode") == 0x41 and e.get("payload_hex") == b"0209"
        ]
        self.assertGreaterEqual(len(notify), 1)
        e0 = notify[0]
        self.assertEqual(e0["event"], "input_event")
        self.assertEqual(e0["input_code"], 0x02)
        self.assertEqual(e0["input_b1"], 0x09)
        self.assertEqual(e0["input_channel"], 1)
        self.assertIsNone(e0["input_value16"])
        self.assertEqual(e0["input_mapped_event"], "button_release")


if __name__ == "__main__":
    unittest.main()
