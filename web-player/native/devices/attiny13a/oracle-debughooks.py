# Project-local Microchip Studio hooks (IronPython 2.7 / Python 3 compatible).
# API: official Microchip Studio User Guide, section 9.7.1. Read-only callbacks.
import json

BUILD_ID = None  # Stamped by build-attiny13a-oracle.mjs; never edit vendor files.
CASE_COUNT = None  # Stamped from the shared stimulus catalog.
COMPLETE_BYTE_ADDRESS = None  # Stamped from the linked ELF.
BREAKPOINT_ADDRESS_UNIT = "unconfirmed"
_seen = False
_calibration_seen = False


def should_process_breakpoint(studio_interface, breakpoint_address, breakpoint_id, obj):
    return True


def has_processed_breakpoint(studio_interface, breakpoint_address, breakpoint_id, obj):
    global _seen, _calibration_seen
    if _seen or BUILD_ID is None:
        return
    try:
        address = int(breakpoint_address)
        if address != breakpoint_address:
            return
        if BREAKPOINT_ADDRESS_UNIT == "unconfirmed":
            if not _calibration_seen and address in (COMPLETE_BYTE_ADDRESS, COMPLETE_BYTE_ADDRESS // 2):
                studio_interface.Print("MICROMUSIC_ORACLE " + json.dumps({
                    "schema": "micromusic-oracle-stop-calibration-v1",
                    "observedAddress": address, "expectedByteAddress": COMPLETE_BYTE_ADDRESS,
                    "hostVerified": False}), "MicroMusicOracle")
                _calibration_seen = True
            return
        expected = COMPLETE_BYTE_ADDRESS
        if BREAKPOINT_ADDRESS_UNIT == "words":
            expected //= 2
        elif BREAKPOINT_ADDRESS_UNIT != "bytes":
            return
        if address != expected:
            return
        def byte(expression):
            value = studio_interface.CalcNumericValue(expression, -1)
            number = int(value)
            if value != number or number < 0 or number > 255:
                raise ValueError("Unreadable byte")
            return number
        magic = [byte("oracle_record.magic[{}]".format(n)) for n in range(4)]
        if magic != [65, 86, 49, 51]:
            return
        build = [byte("oracle_record.build[{}]".format(n)) for n in range(4)]
        if build != list(BUILD_ID):
            studio_interface.Print("MICROMUSIC_ORACLE build-mismatch", "MicroMusicOracle")
            return
        control = [byte("oracle_record.control[{}]".format(n)) for n in range(4)]
        cases = [[byte("oracle_record.cases[{}][{}]".format(n, k))
                  for k in range(4)] for n in range(CASE_COUNT)]
        payload = {"schema": "micromusic-attiny13a-debug-observation-v1",
                   "captureKind": "unverified-debugger", "hostVerified": False,
                   "buildId": build, "record": magic + build + control +
                   [value for case in cases for value in case]}
        studio_interface.Print("MICROMUSIC_ORACLE " + json.dumps(payload), "MicroMusicOracle")
        _seen = True
    except Exception:
        # Do not copy exceptions, evaluated expressions, paths or user data.
        studio_interface.Print("MICROMUSIC_ORACLE read-error", "MicroMusicOracle")


def on_reset(studio_interface, reset_address):
    global _seen, _calibration_seen
    _seen = False
    _calibration_seen = False


def on_eval_expr(studio_interface, expression):
    return expression
