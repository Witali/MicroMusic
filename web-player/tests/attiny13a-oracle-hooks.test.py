"""Python 3 contract stubs, not a Microchip Studio/IronPython execution."""
import json
import unittest
from pathlib import Path

SOURCE = (Path(__file__).parents[1] / "native/devices/attiny13a/oracle-debughooks.py").read_text()


def hooks(unit="bytes", configured=True):
    source = SOURCE
    if configured:
        source = source.replace("BUILD_ID = None", "BUILD_ID = (1, 2, 3, 4)")
        source = source.replace("CASE_COUNT = None", "CASE_COUNT = 12")
        source = source.replace("COMPLETE_BYTE_ADDRESS = None", "COMPLETE_BYTE_ADDRESS = 556")
        source = source.replace('BREAKPOINT_ADDRESS_UNIT = "unconfirmed"',
                                'BREAKPOINT_ADDRESS_UNIT = ' + repr(unit))
    namespace = {}
    exec(compile(source, "oracle-debughooks.py", "exec"), namespace)
    return namespace


class StudioStub:
    def __init__(self):
        self.values = {}
        for name, values in [("magic", [65, 86, 49, 51]), ("build", [1, 2, 3, 4]),
                             ("control", [0, 0, 254, 0])]:
            for n, value in enumerate(values):
                self.values["oracle_record.{}[{}]".format(name, n)] = value
        for n in range(12):
            for k in range(4):
                self.values["oracle_record.cases[{}][{}]".format(n, k)] = n + k
        self.messages = []
        self.reads = 0

    def CalcNumericValue(self, expression, default):
        self.reads += 1
        return self.values.get(expression, default)

    def Print(self, text, tab):
        self.messages.append((text, tab))


class HooksTests(unittest.TestCase):
    def capture(self, h, s, address=556):
        h["has_processed_breakpoint"](s, address, 7, None)

    def test_all_callbacks_preserve_breakpoints_and_expressions(self):
        h = hooks()
        s = StudioStub()
        self.assertTrue(h["should_process_breakpoint"](s, 0, 7, None))
        expression = "unrelated_watch_expression"
        self.assertEqual(h["on_eval_expr"](s, expression), expression)
        self.assertEqual(s.messages, [])

    def test_unstamped_and_wrong_stop_never_read_mailbox(self):
        for h, address in [(hooks(configured=False), 556), (hooks(), 0), (hooks(), 278)]:
            s = StudioStub()
            self.capture(h, s, address)
            self.assertEqual((s.reads, s.messages), (0, []))

    def test_unconfirmed_units_only_emit_calibration_without_data(self):
        for address in [556, 278]:
            h, s = hooks("unconfirmed"), StudioStub()
            self.capture(h, s, address)
            self.capture(h, s, address)
            self.assertEqual(s.reads, 0)
            self.assertEqual(len(s.messages), 1)
            payload = json.loads(s.messages[0][0].split(" ", 1)[1])
            self.assertEqual(payload["observedAddress"], address)
            self.assertNotIn("record", payload)
            self.assertFalse(payload["hostVerified"])

    def test_confirmed_units_capture_once_and_reset_rearms(self):
        for unit, address in [("bytes", 556), ("words", 278)]:
            h, s = hooks(unit), StudioStub()
            self.capture(h, s, address)
            self.capture(h, s, address)
            self.assertEqual(len(s.messages), 1)
            payload = json.loads(s.messages[0][0].split(" ", 1)[1])
            self.assertEqual(len(payload["record"]), 60)
            self.assertFalse(payload["hostVerified"])
            self.assertEqual(payload["captureKind"], "unverified-debugger")
            h["on_reset"](s, 0)
            self.capture(h, s, address)
            self.assertEqual(len(s.messages), 2)

    def test_partial_and_stale_records_are_not_published(self):
        for key, value in [("oracle_record.magic[0]", 0), ("oracle_record.build[0]", 9)]:
            h, s = hooks(), StudioStub()
            s.values[key] = value
            self.capture(h, s)
            self.assertFalse(any('"record"' in text for text, _ in s.messages))

    def test_unreadable_and_fractional_bytes_emit_only_generic_error(self):
        for value in [-1, 256, 1.5, None]:
            h, s = hooks(), StudioStub()
            s.values["oracle_record.control[0]"] = value
            self.capture(h, s)
            self.assertEqual(s.messages, [("MICROMUSIC_ORACLE read-error", "MicroMusicOracle")])


if __name__ == "__main__":
    unittest.main()
