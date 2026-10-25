#!/usr/bin/env python3
"""Convert an LPC2 file to an Arduino PROGMEM header."""

from pathlib import Path
import argparse

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("symbol", nargs="?", default="voiceLpc2")
    args = parser.parse_args()

    data = Path(args.input).read_bytes()
    if len(data) < 4 or data[:4] != b"LPC2":
        raise SystemExit("Input is not an LPC2 file")

    rows = []
    for i in range(0, len(data), 16):
        rows.append("  " + ", ".join(f"0x{x:02X}" for x in data[i:i+16]))

    text = (
        "#pragma once\n"
        "#include <Arduino.h>\n"
        "#include <avr/pgmspace.h>\n\n"
        f"const uint8_t {args.symbol}[] PROGMEM = {{\n"
        + ",\n".join(rows)
        + "\n};\n"
        f"const uint32_t {args.symbol}Length = sizeof({args.symbol});\n"
    )
    Path(args.output).write_text(text, encoding="utf-8")

if __name__ == "__main__":
    main()
