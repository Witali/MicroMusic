#!/usr/bin/env python3
"""Reject unresolved ELF symbols and inspect selected AVR BRBC/BRBS operands.

This standard-library example reads a fully linked little-endian AVR ELF32.
It does not execute firmware or establish timing, ABI, or protocol correctness.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import struct

FLAGS = {'C': 0, 'Z': 1, 'N': 2, 'V': 3, 'S': 4, 'H': 5, 'T': 6, 'I': 7}


class AuditError(ValueError):
    """The ELF or one of its requested operand contracts is invalid."""


class AVRImage:
    def __init__(self, data: bytes):
        self.data = data
        header = self.unpack('<16sHHIIIIIHHHHHH', 0)
        ident, kind, machine = header[:3]
        if ident[:7] != b'\x7fELF\x01\x01\x01' or machine != 83 or kind != 2:
            raise AuditError('expected a fully linked little-endian AVR ELF32 executable')
        section_offset, entry_size, section_count = header[6], header[11], header[12]
        if entry_size != 40 or section_count == 0:
            raise AuditError('unsupported or missing ELF section table')
        self.sections = [self.unpack('<IIIIIIIIII', section_offset + i * entry_size)
                         for i in range(section_count)]
        self.symbols: dict[str, set[int]] = {}
        self.undefined: set[str] = set()
        has_symbols = False
        for section in self.sections:
            if section[1] not in (2, 11):  # SHT_SYMTAB / SHT_DYNSYM
                continue
            has_symbols = True
            if section[9] != 16 or section[5] % 16 or section[6] >= len(self.sections):
                raise AuditError('invalid ELF symbol table')
            strings_section = self.sections[section[6]]
            strings = self.slice(strings_section[4], strings_section[5])
            self.slice(section[4], section[5])
            for offset in range(section[4], section[4] + section[5], 16):
                name_offset, value, _, _, _, index = self.unpack('<IIIBBH', offset)
                if name_offset == 0:
                    continue
                if name_offset >= len(strings):
                    raise AuditError('invalid ELF symbol name offset')
                end = strings.find(b'\0', name_offset)
                if end == -1:
                    raise AuditError('unterminated ELF symbol name')
                name = strings[name_offset:end].decode('utf-8', errors='replace')
                if index == 0:  # SHN_UNDEF, including weak undefined references
                    self.undefined.add(name)
                else:
                    self.symbols.setdefault(name, set()).add(value)
        if not has_symbols:
            raise AuditError('unstripped ELF symbol table required for undefined-symbol audit')

    def slice(self, offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset > len(self.data) or size > len(self.data) - offset:
            raise AuditError('truncated ELF data')
        return self.data[offset:offset + size]

    def unpack(self, fmt: str, offset: int) -> tuple:
        return struct.unpack(fmt, self.slice(offset, struct.calcsize(fmt)))

    def address(self, expression: str) -> int:
        name, separator, increment = expression.partition('+')
        try:
            base = int(name, 0)
        except ValueError:
            values = self.symbols.get(name, set())
            if len(values) != 1:
                raise AuditError('expected one defined symbol for ' + name) from None
            base = next(iter(values))
        try:
            return base + (int(increment, 0) if separator else 0)
        except ValueError:
            raise AuditError('invalid address increment') from None

    def word(self, address: int) -> int:
        if address % 2:
            raise AuditError('AVR instruction address must be even')
        for section in self.sections:
            if section[1] == 1 and section[2] & 4:  # executable SHT_PROGBITS
                delta = address - section[3]
                if 0 <= delta and delta + 2 <= section[5]:
                    return int.from_bytes(self.slice(section[4] + delta, 2), 'little')
        raise AuditError('requested word is outside an executable section')

    def check(self, contract: str) -> int:
        try:
            location, sense, flag = contract.split(':')
            bit = FLAGS[flag.upper()] if flag.upper() in FLAGS else int(flag, 0)
        except (ValueError, KeyError):
            raise AuditError('branch syntax is SYMBOL+BYTE_OFFSET:clear|set:FLAG') from None
        if sense not in ('clear', 'set') or not 0 <= bit <= 7:
            raise AuditError('invalid branch sense or SREG bit')
        address = self.address(location)
        word = self.word(address)
        opcode = 0xf400 if sense == 'clear' else 0xf000
        if word & 0xfc07 != opcode | bit:
            raise AuditError('raw BRBC/BRBS operand mismatch at ' + location)
        relative = (word >> 3) & 0x7f
        if relative & 0x40:
            relative -= 0x80
        return address + 2 + relative * 2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--branch', action='append', default=[],
                        metavar='SYMBOL+BYTE_OFFSET:clear|set:FLAG')
    args = parser.parse_args()
    try:
        image = AVRImage(args.elf.read_bytes())
        if image.undefined:
            raise AuditError('undefined ELF symbols: ' + ', '.join(sorted(image.undefined)))
        for contract in args.branch:
            image.check(contract)
    except (OSError, AuditError) as error:
        parser.exit(1, 'FAIL: ' + str(error) + '\n')
    print(f'PASS: no undefined ELF symbols; {len(args.branch)} raw branch operands checked')


if __name__ == '__main__':
    main()
