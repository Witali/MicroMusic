; ДИАГНОСТИКА INTEL 8080, ПЗУ 64 КБ. ЛИНИЯ A15 ПОДКЛЮЧЕНА К ПЗУ.
; При RESET выполняется код с 0000h: переход на 2100h, затем пик по INTE.
; Далее: CRC-16 (полином 002Dh) всего ПЗУ, проверка A0-A15 и D0-D7, тест команд 8080.
; При успехе 3 коротких сигнала и HLT, при ошибке 1-4 длинных и HLT.
; Без ОЗУ, без записей в память; INT (контакт 14) обязательно удерживать 0.
; ВАЖНО: типовой Intel 8080A не гарантированно работает на 3,5 МГц.
; Для сборки использовать build.py, либо самостоятельный FULL.asm.

ORG 0000H
JMP START

ORG 01000H
DB 01H, 02H, 04H, 08H, 10H, 20H, 40H, 80H

ORG 01010H
DB 0FEH, 0FDH, 0FBH, 0F7H, 0EFH, 0DFH, 0BFH, 7FH

ORG 01018H
DB 022H, 0E4H

ORG 01020H
DB 034H, 012H, 078H, 056H, 0BCH, 09AH, 047H, 0A6H

ORG 01030H

RET_PTR_NZ: DW RET_TARGET_NZ

RET_PTR_Z: DW RET_TARGET_Z

RET_PTR_NC: DW RET_TARGET_NC

RET_PTR_C: DW RET_TARGET_C

RET_PTR_PO: DW RET_TARGET_PO

RET_PTR_PE: DW RET_TARGET_PE

RET_PTR_P: DW RET_TARGET_P

RET_PTR_M: DW RET_TARGET_M

ORG 01040H
DW TARGET_RET

ORG 01C00H
; ===== FAST CRC16 ROM LOOKUP: HIGH 256 BYTES =====

DB 00H, 00H, 00H, 00H, 00H, 00H, 00H, 00H, 01H, 01H, 01H, 01H, 01H, 01H, 01H, 01H

DB 02H, 02H, 02H, 02H, 02H, 02H, 02H, 02H, 03H, 03H, 03H, 03H, 03H, 03H, 03H, 03H

DB 05H, 05H, 05H, 05H, 05H, 05H, 05H, 05H, 04H, 04H, 04H, 04H, 04H, 04H, 04H, 04H

DB 07H, 07H, 07H, 07H, 07H, 07H, 07H, 07H, 06H, 06H, 06H, 06H, 06H, 06H, 06H, 06H

DB 0BH, 0BH, 0BH, 0BH, 0BH, 0BH, 0BH, 0BH, 0AH, 0AH, 0AH, 0AH, 0AH, 0AH, 0AH, 0AH

DB 09H, 09H, 09H, 09H, 09H, 09H, 09H, 09H, 08H, 08H, 08H, 08H, 08H, 08H, 08H, 08H

DB 0EH, 0EH, 0EH, 0EH, 0EH, 0EH, 0EH, 0EH, 0FH, 0FH, 0FH, 0FH, 0FH, 0FH, 0FH, 0FH

DB 0CH, 0CH, 0CH, 0CH, 0CH, 0CH, 0CH, 0CH, 0DH, 0DH, 0DH, 0DH, 0DH, 0DH, 0DH, 0DH

DB 16H, 16H, 16H, 16H, 16H, 16H, 16H, 16H, 17H, 17H, 17H, 17H, 17H, 17H, 17H, 17H

DB 14H, 14H, 14H, 14H, 14H, 14H, 14H, 14H, 15H, 15H, 15H, 15H, 15H, 15H, 15H, 15H

DB 13H, 13H, 13H, 13H, 13H, 13H, 13H, 13H, 12H, 12H, 12H, 12H, 12H, 12H, 12H, 12H

DB 11H, 11H, 11H, 11H, 11H, 11H, 11H, 11H, 10H, 10H, 10H, 10H, 10H, 10H, 10H, 10H

DB 1DH, 1DH, 1DH, 1DH, 1DH, 1DH, 1DH, 1DH, 1CH, 1CH, 1CH, 1CH, 1CH, 1CH, 1CH, 1CH

DB 1FH, 1FH, 1FH, 1FH, 1FH, 1FH, 1FH, 1FH, 1EH, 1EH, 1EH, 1EH, 1EH, 1EH, 1EH, 1EH

DB 18H, 18H, 18H, 18H, 18H, 18H, 18H, 18H, 19H, 19H, 19H, 19H, 19H, 19H, 19H, 19H

DB 1AH, 1AH, 1AH, 1AH, 1AH, 1AH, 1AH, 1AH, 1BH, 1BH, 1BH, 1BH, 1BH, 1BH, 1BH, 1BH

ORG 01D00H
; ===== FAST CRC16 ROM LOOKUP: LOW 256 BYTES =====

DB 00H, 2DH, 5AH, 77H, 0B4H, 99H, 0EEH, 0C3H, 68H, 45H, 32H, 1FH, 0DCH, 0F1H, 86H, 0ABH

DB 0D0H, 0FDH, 8AH, 0A7H, 64H, 49H, 3EH, 13H, 0B8H, 95H, 0E2H, 0CFH, 0CH, 21H, 56H, 7BH

DB 0A0H, 8DH, 0FAH, 0D7H, 14H, 39H, 4EH, 63H, 0C8H, 0E5H, 92H, 0BFH, 7CH, 51H, 26H, 0BH

DB 70H, 5DH, 2AH, 07H, 0C4H, 0E9H, 9EH, 0B3H, 18H, 35H, 42H, 6FH, 0ACH, 81H, 0F6H, 0DBH

DB 40H, 6DH, 1AH, 37H, 0F4H, 0D9H, 0AEH, 83H, 28H, 05H, 72H, 5FH, 9CH, 0B1H, 0C6H, 0EBH

DB 90H, 0BDH, 0CAH, 0E7H, 24H, 09H, 7EH, 53H, 0F8H, 0D5H, 0A2H, 8FH, 4CH, 61H, 16H, 3BH

DB 0E0H, 0CDH, 0BAH, 97H, 54H, 79H, 0EH, 23H, 88H, 0A5H, 0D2H, 0FFH, 3CH, 11H, 66H, 4BH

DB 30H, 1DH, 6AH, 47H, 84H, 0A9H, 0DEH, 0F3H, 58H, 75H, 02H, 2FH, 0ECH, 0C1H, 0B6H, 9BH

DB 80H, 0ADH, 0DAH, 0F7H, 34H, 19H, 6EH, 43H, 0E8H, 0C5H, 0B2H, 9FH, 5CH, 71H, 06H, 2BH

DB 50H, 7DH, 0AH, 27H, 0E4H, 0C9H, 0BEH, 93H, 38H, 15H, 62H, 4FH, 8CH, 0A1H, 0D6H, 0FBH

DB 20H, 0DH, 7AH, 57H, 94H, 0B9H, 0CEH, 0E3H, 48H, 65H, 12H, 3FH, 0FCH, 0D1H, 0A6H, 8BH

DB 0F0H, 0DDH, 0AAH, 87H, 44H, 69H, 1EH, 33H, 98H, 0B5H, 0C2H, 0EFH, 2CH, 01H, 76H, 5BH

DB 0C0H, 0EDH, 9AH, 0B7H, 74H, 59H, 2EH, 03H, 0A8H, 85H, 0F2H, 0DFH, 1CH, 31H, 46H, 6BH

DB 10H, 3DH, 4AH, 67H, 0A4H, 89H, 0FEH, 0D3H, 78H, 55H, 22H, 0FH, 0CCH, 0E1H, 96H, 0BBH

DB 60H, 4DH, 3AH, 17H, 0D4H, 0F9H, 8EH, 0A3H, 08H, 25H, 52H, 7FH, 0BCH, 91H, 0E6H, 0CBH

DB 0B0H, 9DH, 0EAH, 0C7H, 04H, 29H, 5EH, 73H, 0D8H, 0F5H, 82H, 0AFH, 6CH, 41H, 36H, 1BH

    ; ===============================================================
    ; INTEL 8080 (NOT Z80) / 64 KiB ROM / ZERO RAM / A15 CONNECTED
    ; RESET at 0000h; INTE on pin 16; INT pin 14 must be LOW.
    ; Intel 8080A 3.5 MHz is above official datasheet maximum:
    ; use a tested 8080-compatible chip and suitable clock circuitry.
    ; ===============================================================
    ORG 2100H
    START:
        DI                 ; INTE low; forbid spurious interrupt
        ; --- Stage 0: audible short power-on beep (~83 ms at 3.5 MHz)
        MVI B, 5AH
    BOOT_TONE:
        EI                 ; INTE=1
        MVI C, 69H
    BOOT_HIGH:
        DCR C
        JNZ BOOT_HIGH
        DI                 ; INTE=0
        MVI C, 69H
    BOOT_LOW:
        DCR C
        JNZ BOOT_LOW
        DCR B
        JNZ BOOT_TONE
        DI

    ; ===== Секция 1. БЫСТРАЯ CRC-16, 2 таблицы в ПЗУ =====
    ; CRC-16 полином 002Dh, init=0000h, без отражения, CRC образа = 0.
    ; Верхняя таблица на 1C00h, нижняя на 1D00h; каждая 256 байт.
    ; BC хранит CRC: B=старший байт, C=младший; DE — адрес ROM.
    ; HL используется только для табличного чтения; никакой ОЗУ.
    ; Для одного байта: index = (ROM[DE] XOR B).
    ; new B = C XOR TABLE_HI[index]; new C = TABLE_LO[index].
        LXI D, 0000H      ; ROM address
        LXI B, 0000H      ; CRC=0000h
    ROM_CRC_BYTE:
        LDAX D            ; 7T: next byte of ROM
        XRA B             ; 4T: lookup index
        MOV L,A           ; 5T
        MVI H,01CH        ; 7T: high table base=1C00h
        MOV A,M           ; 7T: high CRC table byte
        XRA C             ; 4T: new high = old low XOR table high
        MOV B,A           ; 5T: save high
        INR H             ; 5T: switch to low table at 1D00h
        MOV A,M           ; 7T: low CRC table byte
        MOV C,A           ; 5T: save low
        INX D             ; 5T: next ROM address
        MOV A,D
        ORA E            ; 64 KiB: END when DE wraps to 0000h
        JNZ ROM_CRC_BYTE
        MOV A,B
        ORA C
        JNZ BAD_CHECKSUM

    ; ===== Секция 2. Адресная шина A0..A15: бегущий 0/1 =======
    ; For each of 16 address lines test bit 0 -> 1 while others are 0, then
    ; bit 1 -> 0 while others are 1. Two anchor addresses 0000/FFFF.
    ; Detect open/stuck/shorted lines where returned bytes differ.
    ; A15 IS tested, and must be routed to the ROM address pin.
        ; A0: all-zero background: 0 -> 1; all-one: 0 -> 1
        LXI H, 0000H ; zero anchor
        MOV A,M
        CPI 0C3H
        JNZ BAD_ADDRESS
        LXI H, 0001H ; walking 1
        MOV A,M
        CPI 00H
        JNZ BAD_ADDRESS
        LXI H, 0FFFEH ; walking 0
        MOV A,M
        CPI 9DH
        JNZ BAD_ADDRESS
        LXI H, 0FFFFH ; ones anchor
        MOV A,M
        CPI 0BEH
        JNZ BAD_ADDRESS
        ; A1: all-zero background: 0 -> 1; all-one: 0 -> 1
        LXI H, 0000H ; zero anchor
        MOV A,M
        CPI 0C3H
        JNZ BAD_ADDRESS
        LXI H, 0002H ; walking 1
        MOV A,M
        CPI 21H
        JNZ BAD_ADDRESS
        LXI H, 0FFFDH ; walking 0
        MOV A,M
        CPI 98H
        JNZ BAD_ADDRESS
        LXI H, 0FFFFH ; ones anchor
        MOV A,M
        CPI 0BEH
        JNZ BAD_ADDRESS
        ; A2: all-zero background: 0 -> 1; all-one: 0 -> 1
        LXI H, 0000H ; zero anchor
        MOV A,M
        CPI 0C3H
        JNZ BAD_ADDRESS
        LXI H, 0004H ; walking 1
        MOV A,M
        CPI 0EBH
        JNZ BAD_ADDRESS
        LXI H, 0FFFBH ; walking 0
        MOV A,M
        CPI 0DDH
        JNZ BAD_ADDRESS
        LXI H, 0FFFFH ; ones anchor
        MOV A,M
        CPI 0BEH
        JNZ BAD_ADDRESS
        ; A3: all-zero background: 0 -> 1; all-one: 0 -> 1
        LXI H, 0000H ; zero anchor
        MOV A,M
        CPI 0C3H
        JNZ BAD_ADDRESS
        LXI H, 0008H ; walking 1
        MOV A,M
        CPI 0E8H
        JNZ BAD_ADDRESS
        LXI H, 0FFF7H ; walking 0
        MOV A,M
        CPI 00H
        JNZ BAD_ADDRESS
        LXI H, 0FFFFH ; ones anchor
        MOV A,M
        CPI 0BEH
        JNZ BAD_ADDRESS
        ; A4: all-zero background: 0 -> 1; all-one: 0 -> 1
        LXI H, 0000H ; zero anchor
        MOV A,M
        CPI 0C3H
        JNZ BAD_ADDRESS
        LXI H, 0010H ; walking 1
        MOV A,M
        CPI 0C4H
        JNZ BAD_ADDRESS
        LXI H, 0FFEFH ; walking 0
        MOV A,M
        CPI 7FH
        JNZ BAD_ADDRESS
        LXI H, 0FFFFH ; ones anchor
        MOV A,M
        CPI 0BEH
        JNZ BAD_ADDRESS
        ; A5: all-zero background: 0 -> 1; all-one: 0 -> 1
        LXI H, 0000H ; zero anchor
        MOV A,M
        CPI 0C3H
        JNZ BAD_ADDRESS
        LXI H, 0020H ; walking 1
        MOV A,M
        CPI 0CFH
        JNZ BAD_ADDRESS
        LXI H, 0FFDFH ; walking 0
        MOV A,M
        CPI 0E8H
        JNZ BAD_ADDRESS
        LXI H, 0FFFFH ; ones anchor
        MOV A,M
        CPI 0BEH
        JNZ BAD_ADDRESS
        ; A6: all-zero background: 0 -> 1; all-one: 0 -> 1
        LXI H, 0000H ; zero anchor
        MOV A,M
        CPI 0C3H
        JNZ BAD_ADDRESS
        LXI H, 0040H ; walking 1
        MOV A,M
        CPI 12H
        JNZ BAD_ADDRESS
        LXI H, 0FFBFH ; walking 0
        MOV A,M
        CPI 63H
        JNZ BAD_ADDRESS
        LXI H, 0FFFFH ; ones anchor
        MOV A,M
        CPI 0BEH
        JNZ BAD_ADDRESS
        ; A7: all-zero background: 0 -> 1; all-one: 0 -> 1
        LXI H, 0000H ; zero anchor
        MOV A,M
        CPI 0C3H
        JNZ BAD_ADDRESS
        LXI H, 0080H ; walking 1
        MOV A,M
        CPI 6CH
        JNZ BAD_ADDRESS
        LXI H, 0FF7FH ; walking 0
        MOV A,M
        CPI 59H
        JNZ BAD_ADDRESS
        LXI H, 0FFFFH ; ones anchor
        MOV A,M
        CPI 0BEH
        JNZ BAD_ADDRESS
        ; A8: all-zero background: 0 -> 1; all-one: 0 -> 1
        LXI H, 0000H ; zero anchor
        MOV A,M
        CPI 0C3H
        JNZ BAD_ADDRESS
        LXI H, 0100H ; walking 1
        MOV A,M
        CPI 0C6H
        JNZ BAD_ADDRESS
        LXI H, 0FEFFH ; walking 0
        MOV A,M
        CPI 5CH
        JNZ BAD_ADDRESS
        LXI H, 0FFFFH ; ones anchor
        MOV A,M
        CPI 0BEH
        JNZ BAD_ADDRESS
        ; A9: all-zero background: 0 -> 1; all-one: 0 -> 1
        LXI H, 0000H ; zero anchor
        MOV A,M
        CPI 0C3H
        JNZ BAD_ADDRESS
        LXI H, 0200H ; walking 1
        MOV A,M
        CPI 0EAH
        JNZ BAD_ADDRESS
        LXI H, 0FDFFH ; walking 0
        MOV A,M
        CPI 5BH
        JNZ BAD_ADDRESS
        LXI H, 0FFFFH ; ones anchor
        MOV A,M
        CPI 0BEH
        JNZ BAD_ADDRESS
        ; A10: all-zero background: 0 -> 1; all-one: 0 -> 1
        LXI H, 0000H ; zero anchor
        MOV A,M
        CPI 0C3H
        JNZ BAD_ADDRESS
        LXI H, 0400H ; walking 1
        MOV A,M
        CPI 08H
        JNZ BAD_ADDRESS
        LXI H, 0FBFFH ; walking 0
        MOV A,M
        CPI 02H
        JNZ BAD_ADDRESS
        LXI H, 0FFFFH ; ones anchor
        MOV A,M
        CPI 0BEH
        JNZ BAD_ADDRESS
        ; A11: all-zero background: 0 -> 1; all-one: 0 -> 1
        LXI H, 0000H ; zero anchor
        MOV A,M
        CPI 0C3H
        JNZ BAD_ADDRESS
        LXI H, 0800H ; walking 1
        MOV A,M
        CPI 0FH
        JNZ BAD_ADDRESS
        LXI H, 0F7FFH ; walking 0
        MOV A,M
        CPI 0F1H
        JNZ BAD_ADDRESS
        LXI H, 0FFFFH ; ones anchor
        MOV A,M
        CPI 0BEH
        JNZ BAD_ADDRESS
        ; A12: all-zero background: 0 -> 1; all-one: 0 -> 1
        LXI H, 0000H ; zero anchor
        MOV A,M
        CPI 0C3H
        JNZ BAD_ADDRESS
        LXI H, 1000H ; walking 1
        MOV A,M
        CPI 01H
        JNZ BAD_ADDRESS
        LXI H, 0EFFFH ; walking 0
        MOV A,M
        CPI 33H
        JNZ BAD_ADDRESS
        LXI H, 0FFFFH ; ones anchor
        MOV A,M
        CPI 0BEH
        JNZ BAD_ADDRESS
        ; A13: all-zero background: 0 -> 1; all-one: 0 -> 1
        LXI H, 0000H ; zero anchor
        MOV A,M
        CPI 0C3H
        JNZ BAD_ADDRESS
        LXI H, 2000H ; walking 1
        MOV A,M
        CPI 9FH
        JNZ BAD_ADDRESS
        LXI H, 0DFFFH ; walking 0
        MOV A,M
        CPI 27H
        JNZ BAD_ADDRESS
        LXI H, 0FFFFH ; ones anchor
        MOV A,M
        CPI 0BEH
        JNZ BAD_ADDRESS
        ; A14: all-zero background: 0 -> 1; all-one: 0 -> 1
        LXI H, 0000H ; zero anchor
        MOV A,M
        CPI 0C3H
        JNZ BAD_ADDRESS
        LXI H, 4000H ; walking 1
        MOV A,M
        CPI 9EH
        JNZ BAD_ADDRESS
        LXI H, 0BFFFH ; walking 0
        MOV A,M
        CPI 36H
        JNZ BAD_ADDRESS
        LXI H, 0FFFFH ; ones anchor
        MOV A,M
        CPI 0BEH
        JNZ BAD_ADDRESS
        ; A15: all-zero background: 0 -> 1; all-one: 0 -> 1
        LXI H, 0000H ; zero anchor
        MOV A,M
        CPI 0C3H
        JNZ BAD_ADDRESS
        LXI H, 8000H ; walking 1
        MOV A,M
        CPI 73H
        JNZ BAD_ADDRESS
        LXI H, 7FFFH ; walking 0
        MOV A,M
        CPI 0D3H
        JNZ BAD_ADDRESS
        LXI H, 0FFFFH ; ones anchor
        MOV A,M
        CPI 0BEH
        JNZ BAD_ADDRESS

    ; ===== Секция 3. Шина данных D0..D7: бегущая 1/0 =======
    ; Locations 1000..1007 store 01,02,04,...80;
    ; locations 1010..1017 store FE,FD,FB,...7F.
        LXI H, 01000H
        MVI B, 01H
    DATA_ONE_LOOP:
        MOV A,M
        CMP B
        JNZ BAD_DATA
        INX H
        MOV A,B
        RLC
        MOV B,A
        CPI 01H
        JNZ DATA_ONE_LOOP
        LXI H, 01010H
        MVI B, 0FEH
    DATA_ZERO_LOOP:
        MOV A,M
        CMP B
        JNZ BAD_DATA
        INX H
        MOV A,B
        RLC
        MOV B,A
        CPI 0FEH
        JNZ DATA_ZERO_LOOP

    ; ===== Секция 4. Проверка MOV и регистров без ОЗУ ========
    ; Only tests where the result can be observed without RAM or I/O.
    ; Checks representative flags/results plus every register-to-
    ; register MOV opcode and every 8-bit ALU source (including M).
        NOP
        JMP TEST_REGISTER_MOV
        JMP BAD_CPU       ; unreachable if JMP works
    TEST_REGISTER_MOV:
        ; MOV B,B and register/accumulator data path
        MVI B, 0A5H
        MOV B,B
        MOV A,B
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV C,B and register/accumulator data path
        MVI B, 0A5H
        MOV C,B
        MOV A,C
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV D,B and register/accumulator data path
        MVI B, 0A5H
        MOV D,B
        MOV A,D
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV E,B and register/accumulator data path
        MVI B, 0A5H
        MOV E,B
        MOV A,E
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV H,B and register/accumulator data path
        MVI B, 0A5H
        MOV H,B
        MOV A,H
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV L,B and register/accumulator data path
        MVI B, 0A5H
        MOV L,B
        MOV A,L
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV A,B and register/accumulator data path
        MVI B, 0A5H
        MOV A,B
        MOV A,A
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV B,C and register/accumulator data path
        MVI C, 0A5H
        MOV B,C
        MOV A,B
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV C,C and register/accumulator data path
        MVI C, 0A5H
        MOV C,C
        MOV A,C
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV D,C and register/accumulator data path
        MVI C, 0A5H
        MOV D,C
        MOV A,D
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV E,C and register/accumulator data path
        MVI C, 0A5H
        MOV E,C
        MOV A,E
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV H,C and register/accumulator data path
        MVI C, 0A5H
        MOV H,C
        MOV A,H
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV L,C and register/accumulator data path
        MVI C, 0A5H
        MOV L,C
        MOV A,L
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV A,C and register/accumulator data path
        MVI C, 0A5H
        MOV A,C
        MOV A,A
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV B,D and register/accumulator data path
        MVI D, 0A5H
        MOV B,D
        MOV A,B
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV C,D and register/accumulator data path
        MVI D, 0A5H
        MOV C,D
        MOV A,C
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV D,D and register/accumulator data path
        MVI D, 0A5H
        MOV D,D
        MOV A,D
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV E,D and register/accumulator data path
        MVI D, 0A5H
        MOV E,D
        MOV A,E
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV H,D and register/accumulator data path
        MVI D, 0A5H
        MOV H,D
        MOV A,H
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV L,D and register/accumulator data path
        MVI D, 0A5H
        MOV L,D
        MOV A,L
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV A,D and register/accumulator data path
        MVI D, 0A5H
        MOV A,D
        MOV A,A
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV B,E and register/accumulator data path
        MVI E, 0A5H
        MOV B,E
        MOV A,B
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV C,E and register/accumulator data path
        MVI E, 0A5H
        MOV C,E
        MOV A,C
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV D,E and register/accumulator data path
        MVI E, 0A5H
        MOV D,E
        MOV A,D
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV E,E and register/accumulator data path
        MVI E, 0A5H
        MOV E,E
        MOV A,E
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV H,E and register/accumulator data path
        MVI E, 0A5H
        MOV H,E
        MOV A,H
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV L,E and register/accumulator data path
        MVI E, 0A5H
        MOV L,E
        MOV A,L
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV A,E and register/accumulator data path
        MVI E, 0A5H
        MOV A,E
        MOV A,A
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV B,H and register/accumulator data path
        MVI H, 0A5H
        MOV B,H
        MOV A,B
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV C,H and register/accumulator data path
        MVI H, 0A5H
        MOV C,H
        MOV A,C
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV D,H and register/accumulator data path
        MVI H, 0A5H
        MOV D,H
        MOV A,D
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV E,H and register/accumulator data path
        MVI H, 0A5H
        MOV E,H
        MOV A,E
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV H,H and register/accumulator data path
        MVI H, 0A5H
        MOV H,H
        MOV A,H
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV L,H and register/accumulator data path
        MVI H, 0A5H
        MOV L,H
        MOV A,L
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV A,H and register/accumulator data path
        MVI H, 0A5H
        MOV A,H
        MOV A,A
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV B,L and register/accumulator data path
        MVI L, 0A5H
        MOV B,L
        MOV A,B
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV C,L and register/accumulator data path
        MVI L, 0A5H
        MOV C,L
        MOV A,C
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV D,L and register/accumulator data path
        MVI L, 0A5H
        MOV D,L
        MOV A,D
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV E,L and register/accumulator data path
        MVI L, 0A5H
        MOV E,L
        MOV A,E
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV H,L and register/accumulator data path
        MVI L, 0A5H
        MOV H,L
        MOV A,H
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV L,L and register/accumulator data path
        MVI L, 0A5H
        MOV L,L
        MOV A,L
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV A,L and register/accumulator data path
        MVI L, 0A5H
        MOV A,L
        MOV A,A
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV B,A and register/accumulator data path
        MVI A, 0A5H
        MOV B,A
        MOV A,B
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV C,A and register/accumulator data path
        MVI A, 0A5H
        MOV C,A
        MOV A,C
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV D,A and register/accumulator data path
        MVI A, 0A5H
        MOV D,A
        MOV A,D
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV E,A and register/accumulator data path
        MVI A, 0A5H
        MOV E,A
        MOV A,E
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV H,A and register/accumulator data path
        MVI A, 0A5H
        MOV H,A
        MOV A,H
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV L,A and register/accumulator data path
        MVI A, 0A5H
        MOV L,A
        MOV A,L
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV A,A and register/accumulator data path
        MVI A, 0A5H
        MOV A,A
        MOV A,A
        CPI 0A5H
        JNZ BAD_CPU
        ; MOV r,M: read-only ROM operand, never MOV M,r
        LXI H, 01000H
        MOV B,M
        MOV A,B
        CPI 01H
        JNZ BAD_CPU
        LXI H, 01000H
        MOV C,M
        MOV A,C
        CPI 01H
        JNZ BAD_CPU
        LXI H, 01000H
        MOV D,M
        MOV A,D
        CPI 01H
        JNZ BAD_CPU
        LXI H, 01000H
        MOV E,M
        MOV A,E
        CPI 01H
        JNZ BAD_CPU
        LXI H, 01000H
        MOV H,M
        MOV A,H
        CPI 01H
        JNZ BAD_CPU
        LXI H, 01000H
        MOV L,M
        MOV A,L
        CPI 01H
        JNZ BAD_CPU
        LXI H, 01000H
        MOV A,M
        MOV A,A
        CPI 01H
        JNZ BAD_CPU

    ; ===== Секция 5. АЛУ: арифметика и логика с регистрами ==
        ; ADD B: expected A=57H, Z=0, CY=0
        MVI B, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        ADD B
        JZ BAD_CPU
        JC BAD_CPU
        CPI 57H
        JNZ BAD_CPU
        ; ADD C: expected A=57H, Z=0, CY=0
        MVI C, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        ADD C
        JZ BAD_CPU
        JC BAD_CPU
        CPI 57H
        JNZ BAD_CPU
        ; ADD D: expected A=57H, Z=0, CY=0
        MVI D, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        ADD D
        JZ BAD_CPU
        JC BAD_CPU
        CPI 57H
        JNZ BAD_CPU
        ; ADD E: expected A=57H, Z=0, CY=0
        MVI E, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        ADD E
        JZ BAD_CPU
        JC BAD_CPU
        CPI 57H
        JNZ BAD_CPU
        ; ADD H: expected A=57H, Z=0, CY=0
        MVI H, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        ADD H
        JZ BAD_CPU
        JC BAD_CPU
        CPI 57H
        JNZ BAD_CPU
        ; ADD L: expected A=57H, Z=0, CY=0
        MVI L, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        ADD L
        JZ BAD_CPU
        JC BAD_CPU
        CPI 57H
        JNZ BAD_CPU
        ; ADD A: expected A=6AH, Z=0, CY=0
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        ADD A
        JZ BAD_CPU
        JC BAD_CPU
        CPI 6AH
        JNZ BAD_CPU
        ; ADD M: expected A=57H, Z=0, CY=0
        LXI H, 01018H       ; immutable operand 22h
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        ADD M
        JZ BAD_CPU
        JC BAD_CPU
        CPI 57H
        JNZ BAD_CPU
        ; ADC B: expected A=58H, Z=0, CY=0
        MVI B, 022H
        MVI A, 035H
        STC
        ADC B
        JZ BAD_CPU
        JC BAD_CPU
        CPI 58H
        JNZ BAD_CPU
        ; ADC C: expected A=58H, Z=0, CY=0
        MVI C, 022H
        MVI A, 035H
        STC
        ADC C
        JZ BAD_CPU
        JC BAD_CPU
        CPI 58H
        JNZ BAD_CPU
        ; ADC D: expected A=58H, Z=0, CY=0
        MVI D, 022H
        MVI A, 035H
        STC
        ADC D
        JZ BAD_CPU
        JC BAD_CPU
        CPI 58H
        JNZ BAD_CPU
        ; ADC E: expected A=58H, Z=0, CY=0
        MVI E, 022H
        MVI A, 035H
        STC
        ADC E
        JZ BAD_CPU
        JC BAD_CPU
        CPI 58H
        JNZ BAD_CPU
        ; ADC H: expected A=58H, Z=0, CY=0
        MVI H, 022H
        MVI A, 035H
        STC
        ADC H
        JZ BAD_CPU
        JC BAD_CPU
        CPI 58H
        JNZ BAD_CPU
        ; ADC L: expected A=58H, Z=0, CY=0
        MVI L, 022H
        MVI A, 035H
        STC
        ADC L
        JZ BAD_CPU
        JC BAD_CPU
        CPI 58H
        JNZ BAD_CPU
        ; ADC A: expected A=6BH, Z=0, CY=0
        MVI A, 035H
        STC
        ADC A
        JZ BAD_CPU
        JC BAD_CPU
        CPI 6BH
        JNZ BAD_CPU
        ; ADC M: expected A=58H, Z=0, CY=0
        LXI H, 01018H       ; immutable operand 22h
        MVI A, 035H
        STC
        ADC M
        JZ BAD_CPU
        JC BAD_CPU
        CPI 58H
        JNZ BAD_CPU
        ; SUB B: expected A=13H, Z=0, CY=0
        MVI B, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        SUB B
        JZ BAD_CPU
        JC BAD_CPU
        CPI 13H
        JNZ BAD_CPU
        ; SUB C: expected A=13H, Z=0, CY=0
        MVI C, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        SUB C
        JZ BAD_CPU
        JC BAD_CPU
        CPI 13H
        JNZ BAD_CPU
        ; SUB D: expected A=13H, Z=0, CY=0
        MVI D, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        SUB D
        JZ BAD_CPU
        JC BAD_CPU
        CPI 13H
        JNZ BAD_CPU
        ; SUB E: expected A=13H, Z=0, CY=0
        MVI E, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        SUB E
        JZ BAD_CPU
        JC BAD_CPU
        CPI 13H
        JNZ BAD_CPU
        ; SUB H: expected A=13H, Z=0, CY=0
        MVI H, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        SUB H
        JZ BAD_CPU
        JC BAD_CPU
        CPI 13H
        JNZ BAD_CPU
        ; SUB L: expected A=13H, Z=0, CY=0
        MVI L, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        SUB L
        JZ BAD_CPU
        JC BAD_CPU
        CPI 13H
        JNZ BAD_CPU
        ; SUB A: expected A=00H, Z=1, CY=0
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        SUB A
        JNZ BAD_CPU
        JC BAD_CPU
        CPI 00H
        JNZ BAD_CPU
        ; SUB M: expected A=13H, Z=0, CY=0
        LXI H, 01018H       ; immutable operand 22h
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        SUB M
        JZ BAD_CPU
        JC BAD_CPU
        CPI 13H
        JNZ BAD_CPU
        ; SBB B: expected A=12H, Z=0, CY=0
        MVI B, 022H
        MVI A, 035H
        STC
        SBB B
        JZ BAD_CPU
        JC BAD_CPU
        CPI 12H
        JNZ BAD_CPU
        ; SBB C: expected A=12H, Z=0, CY=0
        MVI C, 022H
        MVI A, 035H
        STC
        SBB C
        JZ BAD_CPU
        JC BAD_CPU
        CPI 12H
        JNZ BAD_CPU
        ; SBB D: expected A=12H, Z=0, CY=0
        MVI D, 022H
        MVI A, 035H
        STC
        SBB D
        JZ BAD_CPU
        JC BAD_CPU
        CPI 12H
        JNZ BAD_CPU
        ; SBB E: expected A=12H, Z=0, CY=0
        MVI E, 022H
        MVI A, 035H
        STC
        SBB E
        JZ BAD_CPU
        JC BAD_CPU
        CPI 12H
        JNZ BAD_CPU
        ; SBB H: expected A=12H, Z=0, CY=0
        MVI H, 022H
        MVI A, 035H
        STC
        SBB H
        JZ BAD_CPU
        JC BAD_CPU
        CPI 12H
        JNZ BAD_CPU
        ; SBB L: expected A=12H, Z=0, CY=0
        MVI L, 022H
        MVI A, 035H
        STC
        SBB L
        JZ BAD_CPU
        JC BAD_CPU
        CPI 12H
        JNZ BAD_CPU
        ; SBB A: expected A=0FFH, Z=0, CY=1
        MVI A, 035H
        STC
        SBB A
        JZ BAD_CPU
        JNC BAD_CPU
        CPI 0FFH
        JNZ BAD_CPU
        ; SBB M: expected A=12H, Z=0, CY=0
        LXI H, 01018H       ; immutable operand 22h
        MVI A, 035H
        STC
        SBB M
        JZ BAD_CPU
        JC BAD_CPU
        CPI 12H
        JNZ BAD_CPU
        ; ANA B: expected A=20H, Z=0, CY=0
        MVI B, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        ANA B
        JZ BAD_CPU
        JC BAD_CPU
        CPI 20H
        JNZ BAD_CPU
        ; ANA C: expected A=20H, Z=0, CY=0
        MVI C, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        ANA C
        JZ BAD_CPU
        JC BAD_CPU
        CPI 20H
        JNZ BAD_CPU
        ; ANA D: expected A=20H, Z=0, CY=0
        MVI D, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        ANA D
        JZ BAD_CPU
        JC BAD_CPU
        CPI 20H
        JNZ BAD_CPU
        ; ANA E: expected A=20H, Z=0, CY=0
        MVI E, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        ANA E
        JZ BAD_CPU
        JC BAD_CPU
        CPI 20H
        JNZ BAD_CPU
        ; ANA H: expected A=20H, Z=0, CY=0
        MVI H, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        ANA H
        JZ BAD_CPU
        JC BAD_CPU
        CPI 20H
        JNZ BAD_CPU
        ; ANA L: expected A=20H, Z=0, CY=0
        MVI L, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        ANA L
        JZ BAD_CPU
        JC BAD_CPU
        CPI 20H
        JNZ BAD_CPU
        ; ANA A: expected A=35H, Z=0, CY=0
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        ANA A
        JZ BAD_CPU
        JC BAD_CPU
        CPI 35H
        JNZ BAD_CPU
        ; ANA M: expected A=20H, Z=0, CY=0
        LXI H, 01018H       ; immutable operand 22h
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        ANA M
        JZ BAD_CPU
        JC BAD_CPU
        CPI 20H
        JNZ BAD_CPU
        ; XRA B: expected A=17H, Z=0, CY=0
        MVI B, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        XRA B
        JZ BAD_CPU
        JC BAD_CPU
        CPI 17H
        JNZ BAD_CPU
        ; XRA C: expected A=17H, Z=0, CY=0
        MVI C, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        XRA C
        JZ BAD_CPU
        JC BAD_CPU
        CPI 17H
        JNZ BAD_CPU
        ; XRA D: expected A=17H, Z=0, CY=0
        MVI D, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        XRA D
        JZ BAD_CPU
        JC BAD_CPU
        CPI 17H
        JNZ BAD_CPU
        ; XRA E: expected A=17H, Z=0, CY=0
        MVI E, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        XRA E
        JZ BAD_CPU
        JC BAD_CPU
        CPI 17H
        JNZ BAD_CPU
        ; XRA H: expected A=17H, Z=0, CY=0
        MVI H, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        XRA H
        JZ BAD_CPU
        JC BAD_CPU
        CPI 17H
        JNZ BAD_CPU
        ; XRA L: expected A=17H, Z=0, CY=0
        MVI L, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        XRA L
        JZ BAD_CPU
        JC BAD_CPU
        CPI 17H
        JNZ BAD_CPU
        ; XRA A: expected A=00H, Z=1, CY=0
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        XRA A
        JNZ BAD_CPU
        JC BAD_CPU
        CPI 00H
        JNZ BAD_CPU
        ; XRA M: expected A=17H, Z=0, CY=0
        LXI H, 01018H       ; immutable operand 22h
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        XRA M
        JZ BAD_CPU
        JC BAD_CPU
        CPI 17H
        JNZ BAD_CPU
        ; ORA B: expected A=37H, Z=0, CY=0
        MVI B, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        ORA B
        JZ BAD_CPU
        JC BAD_CPU
        CPI 37H
        JNZ BAD_CPU
        ; ORA C: expected A=37H, Z=0, CY=0
        MVI C, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        ORA C
        JZ BAD_CPU
        JC BAD_CPU
        CPI 37H
        JNZ BAD_CPU
        ; ORA D: expected A=37H, Z=0, CY=0
        MVI D, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        ORA D
        JZ BAD_CPU
        JC BAD_CPU
        CPI 37H
        JNZ BAD_CPU
        ; ORA E: expected A=37H, Z=0, CY=0
        MVI E, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        ORA E
        JZ BAD_CPU
        JC BAD_CPU
        CPI 37H
        JNZ BAD_CPU
        ; ORA H: expected A=37H, Z=0, CY=0
        MVI H, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        ORA H
        JZ BAD_CPU
        JC BAD_CPU
        CPI 37H
        JNZ BAD_CPU
        ; ORA L: expected A=37H, Z=0, CY=0
        MVI L, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        ORA L
        JZ BAD_CPU
        JC BAD_CPU
        CPI 37H
        JNZ BAD_CPU
        ; ORA A: expected A=35H, Z=0, CY=0
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        ORA A
        JZ BAD_CPU
        JC BAD_CPU
        CPI 35H
        JNZ BAD_CPU
        ; ORA M: expected A=37H, Z=0, CY=0
        LXI H, 01018H       ; immutable operand 22h
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        ORA M
        JZ BAD_CPU
        JC BAD_CPU
        CPI 37H
        JNZ BAD_CPU
        ; CMP B: expected A=35H, Z=0, CY=0
        MVI B, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        CMP B
        JZ BAD_CPU
        JC BAD_CPU
        CPI 35H
        JNZ BAD_CPU
        ; CMP C: expected A=35H, Z=0, CY=0
        MVI C, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        CMP C
        JZ BAD_CPU
        JC BAD_CPU
        CPI 35H
        JNZ BAD_CPU
        ; CMP D: expected A=35H, Z=0, CY=0
        MVI D, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        CMP D
        JZ BAD_CPU
        JC BAD_CPU
        CPI 35H
        JNZ BAD_CPU
        ; CMP E: expected A=35H, Z=0, CY=0
        MVI E, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        CMP E
        JZ BAD_CPU
        JC BAD_CPU
        CPI 35H
        JNZ BAD_CPU
        ; CMP H: expected A=35H, Z=0, CY=0
        MVI H, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        CMP H
        JZ BAD_CPU
        JC BAD_CPU
        CPI 35H
        JNZ BAD_CPU
        ; CMP L: expected A=35H, Z=0, CY=0
        MVI L, 022H
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        CMP L
        JZ BAD_CPU
        JC BAD_CPU
        CPI 35H
        JNZ BAD_CPU
        ; CMP A: expected A=35H, Z=1, CY=0
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        CMP A
        JNZ BAD_CPU
        JC BAD_CPU
        CPI 35H
        JNZ BAD_CPU
        ; CMP M: expected A=35H, Z=0, CY=0
        LXI H, 01018H       ; immutable operand 22h
        MVI A, 035H
        STC
        CMC        ; CY clear, check carry output of ALU
        CMP M
        JZ BAD_CPU
        JC BAD_CPU
        CPI 35H
        JNZ BAD_CPU

    ; ===== Секция 6. Непосредственные операции АЛУ и флаги ==
        ; ADI 22h, expected A=57H CY=0
        MVI A, 035H
        STC
        CMC
        ADI 022H
        JC BAD_CPU
        CPI 57H
        JNZ BAD_CPU
        ; ACI 22h, expected A=58H CY=0
        MVI A, 035H
        STC
        ACI 022H
        JC BAD_CPU
        CPI 58H
        JNZ BAD_CPU
        ; SUI 22h, expected A=13H CY=0
        MVI A, 035H
        STC
        CMC
        SUI 022H
        JC BAD_CPU
        CPI 13H
        JNZ BAD_CPU
        ; SBI 22h, expected A=12H CY=0
        MVI A, 035H
        STC
        SBI 022H
        JC BAD_CPU
        CPI 12H
        JNZ BAD_CPU
        ; ANI 22h, expected A=20H CY=0
        MVI A, 035H
        STC
        CMC
        ANI 022H
        JC BAD_CPU
        CPI 20H
        JNZ BAD_CPU
        ; XRI 22h, expected A=17H CY=0
        MVI A, 035H
        STC
        CMC
        XRI 022H
        JC BAD_CPU
        CPI 17H
        JNZ BAD_CPU
        ; ORI 22h, expected A=37H CY=0
        MVI A, 035H
        STC
        CMC
        ORI 022H
        JC BAD_CPU
        CPI 37H
        JNZ BAD_CPU
        ; CPI 22h, expected A=35H CY=0
        MVI A, 035H
        STC
        CMC
        CPI 022H
        JC BAD_CPU
        CPI 35H
        JNZ BAD_CPU
        ; --- INR/DCR: cover all seven register encodings and preserve CY
        ; INR B and DCR B preserve the carry flag
        MVI B, 07FH
        STC
        INR B
        JNC BAD_CPU
        MOV A,B
        CPI 080H
        JNZ BAD_CPU
        STC
        DCR B
        JNC BAD_CPU
        MOV A,B
        CPI 07FH
        JNZ BAD_CPU
        ; INR C and DCR C preserve the carry flag
        MVI C, 07FH
        STC
        INR C
        JNC BAD_CPU
        MOV A,C
        CPI 080H
        JNZ BAD_CPU
        STC
        DCR C
        JNC BAD_CPU
        MOV A,C
        CPI 07FH
        JNZ BAD_CPU
        ; INR D and DCR D preserve the carry flag
        MVI D, 07FH
        STC
        INR D
        JNC BAD_CPU
        MOV A,D
        CPI 080H
        JNZ BAD_CPU
        STC
        DCR D
        JNC BAD_CPU
        MOV A,D
        CPI 07FH
        JNZ BAD_CPU
        ; INR E and DCR E preserve the carry flag
        MVI E, 07FH
        STC
        INR E
        JNC BAD_CPU
        MOV A,E
        CPI 080H
        JNZ BAD_CPU
        STC
        DCR E
        JNC BAD_CPU
        MOV A,E
        CPI 07FH
        JNZ BAD_CPU
        ; INR H and DCR H preserve the carry flag
        MVI H, 07FH
        STC
        INR H
        JNC BAD_CPU
        MOV A,H
        CPI 080H
        JNZ BAD_CPU
        STC
        DCR H
        JNC BAD_CPU
        MOV A,H
        CPI 07FH
        JNZ BAD_CPU
        ; INR L and DCR L preserve the carry flag
        MVI L, 07FH
        STC
        INR L
        JNC BAD_CPU
        MOV A,L
        CPI 080H
        JNZ BAD_CPU
        STC
        DCR L
        JNC BAD_CPU
        MOV A,L
        CPI 07FH
        JNZ BAD_CPU
        ; INR A and DCR A preserve the carry flag
        MVI A, 07FH
        STC
        INR A
        JNC BAD_CPU
        MOV A,A
        CPI 080H
        JNZ BAD_CPU
        STC
        DCR A
        JNC BAD_CPU
        MOV A,A
        CPI 07FH
        JNZ BAD_CPU
        ; Critical 8-bit flags: zero/carry/sign/parity
        MVI A, 0FFH
        ADI 01H
        JNZ BAD_CPU     ; FF+01 wraps to zero
        JNC BAD_CPU     ; carry must be set
        JPO BAD_CPU     ; parity of 00 = even
        JM BAD_CPU      ; zero has positive sign
        MVI A, 07FH
        ADI 01H
        JP BAD_CPU      ; result 80h is negative
        JPE BAD_CPU     ; 80h has odd parity
        JC BAD_CPU      ; no carry
        ; DAA after 09h+09h must give packed BCD 18h
        MVI A, 09H
        ADI 09H
        DAA
        CPI 018H
        JNZ BAD_CPU
        ; RLC,RRC,RAL,RAR and carry flip-flop
        MVI A, 081H
        RLC
        JNC BAD_CPU
        CPI 03H
        JNZ BAD_CPU
        MVI A, 081H
        RRC
        JNC BAD_CPU
        CPI 0C0H
        JNZ BAD_CPU
        MVI A, 080H
        STC
        RAL
        JNC BAD_CPU
        CPI 01H
        JNZ BAD_CPU
        MVI A, 001H
        STC
        RAR
        JNC BAD_CPU
        CPI 80H
        JNZ BAD_CPU
        MVI A, 055H
        CMA
        CPI 0AAH
        JNZ BAD_CPU
        STC
        CMC
        JC BAD_CPU
        STC
        JNC BAD_CPU

    ; ===== Секция 7. Пары регистров, 16-битная арифметика ==
        ; LXI / INX / DCX B
        LXI B, 1234H
        INX B
        DCX B
        MOV A,B
        CPI 12H
        JNZ BAD_CPU
        MOV A,C
        CPI 34H
        JNZ BAD_CPU
        ; LXI / INX / DCX D
        LXI D, 5678H
        INX D
        DCX D
        MOV A,D
        CPI 56H
        JNZ BAD_CPU
        MOV A,E
        CPI 78H
        JNZ BAD_CPU
        ; LXI / INX / DCX H
        LXI H, 9ABCH
        INX H
        DCX H
        MOV A,H
        CPI 9AH
        JNZ BAD_CPU
        MOV A,L
        CPI 0BCH
        JNZ BAD_CPU
        LXI SP, 05A3CH
        INX SP
        DCX SP
        LXI H, 0000H
        DAD SP
        MOV A,H
        CPI 05AH
        JNZ BAD_CPU
        MOV A,L
        CPI 03CH
        JNZ BAD_CPU
        LXI H, 0FFFFH
        LXI B, 0001H
        DAD B
        JNC BAD_CPU
        MOV A,H
        ORA L
        JNZ BAD_CPU
        LXI H, 01000H
        LXI D, 01234H
        DAD D
        MOV A,H
        CPI 022H
        JNZ BAD_CPU
        MOV A,L
        CPI 034H
        JNZ BAD_CPU
        LXI H, 01234H
        DAD H
        MOV A,H
        CPI 024H
        JNZ BAD_CPU
        MOV A,L
        CPI 068H
        JNZ BAD_CPU
        ; XCHG and SPHL (neither writes memory)
        LXI H, 01234H
        LXI D, 05678H
        XCHG
        MOV A,H
        CPI 056H
        JNZ BAD_CPU
        MOV A,E
        CPI 034H
        JNZ BAD_CPU
        SPHL
        LXI H, 0000H
        DAD SP
        MOV A,H
        CPI 056H
        JNZ BAD_CPU
        MOV A,L
        CPI 078H
        JNZ BAD_CPU

    ; ===== Секция 8. Прямое и косвенное чтение из ПЗУ ====
        LXI B, 01000H
        LDAX B
        CPI 01H
        JNZ BAD_CPU
        LXI D, 01001H
        LDAX D
        CPI 02H
        JNZ BAD_CPU
        LDA 01002H
        CPI 04H
        JNZ BAD_CPU
        LHLD 01018H    ; low=22h, high=E4h
        MOV A,L
        CPI 022H
        JNZ BAD_CPU
        MOV A,H
        CPI 0E4H
        JNZ BAD_CPU

    ; ===== Секция 9. POP/RET: читаем слова стека из ПЗУ ==
    ; POP and RET only READ the stack: safe with SP pointing to ROM.
    ; PUSH,CALL,RST,XTHL are NOT safe without writable memory.
        LXI SP, 01020H
        POP B
        MOV A,B
        CPI 012H
        JNZ BAD_CPU
        MOV A,C
        CPI 034H
        JNZ BAD_CPU
        POP D
        MOV A,D
        CPI 056H
        JNZ BAD_CPU
        MOV A,E
        CPI 078H
        JNZ BAD_CPU
        POP H
        MOV A,H
        CPI 09AH
        JNZ BAD_CPU
        MOV A,L
        CPI 0BCH
        JNZ BAD_CPU
        POP PSW
        JNC BAD_CPU    ; PSW has carry
        JNZ BAD_CPU    ; PSW has zero
        JPO BAD_CPU    ; PSW has even parity
        JM BAD_CPU     ; PSW sign clear
        CPI 0A6H
        JNZ BAD_CPU
        LXI SP, 01040H
        RET            ; pops address of TARGET_RET from ROM
        JMP BAD_CPU
    TARGET_RET:
        NOP
        ; conditional RET NZ reads its target from ROM
        LXI SP, RET_PTR_NZ
        MVI A,01H
        ORA A
        RNZ
        JMP BAD_CPU
    RET_TARGET_NZ:
        NOP
        ; conditional RET Z reads its target from ROM
        LXI SP, RET_PTR_Z
        MVI A,00H
        ORA A
        RZ
        JMP BAD_CPU
    RET_TARGET_Z:
        NOP
        ; conditional RET NC reads its target from ROM
        LXI SP, RET_PTR_NC
        MVI A,01H
        ORA A
        RNC
        JMP BAD_CPU
    RET_TARGET_NC:
        NOP
        ; conditional RET C reads its target from ROM
        LXI SP, RET_PTR_C
        STC
        RC
        JMP BAD_CPU
    RET_TARGET_C:
        NOP
        ; conditional RET PO reads its target from ROM
        LXI SP, RET_PTR_PO
        MVI A,01H
        ORA A
        RPO
        JMP BAD_CPU
    RET_TARGET_PO:
        NOP
        ; conditional RET PE reads its target from ROM
        LXI SP, RET_PTR_PE
        MVI A,00H
        ORA A
        RPE
        JMP BAD_CPU
    RET_TARGET_PE:
        NOP
        ; conditional RET P reads its target from ROM
        LXI SP, RET_PTR_P
        MVI A,00H
        ORA A
        RP
        JMP BAD_CPU
    RET_TARGET_P:
        NOP
        ; conditional RET M reads its target from ROM
        LXI SP, RET_PTR_M
        MVI A,080H
        ORA A
        RM
        JMP BAD_CPU
    RET_TARGET_M:
        NOP

    ; ===== Секция 10. Переходы JMP/PCHL и условный CALL ====
        ; Check JNZ taken path
        MVI A,01H
        ORA A
        JNZ J_TARGET_NZ
        JMP BAD_CPU
    J_TARGET_NZ:
        NOP
        ; Check JZ taken path
        MVI A,00H
        ORA A
        JZ J_TARGET_Z
        JMP BAD_CPU
    J_TARGET_Z:
        NOP
        ; Check JNC taken path
        MVI A,01H
        ORA A
        JNC J_TARGET_NC
        JMP BAD_CPU
    J_TARGET_NC:
        NOP
        ; Check JC taken path
        STC
        JC J_TARGET_C
        JMP BAD_CPU
    J_TARGET_C:
        NOP
        ; Check JPO taken path
        MVI A,01H
        ORA A
        JPO J_TARGET_PO
        JMP BAD_CPU
    J_TARGET_PO:
        NOP
        ; Check JPE taken path
        MVI A,00H
        ORA A
        JPE J_TARGET_PE
        JMP BAD_CPU
    J_TARGET_PE:
        NOP
        ; Check JP taken path
        MVI A,00H
        ORA A
        JP J_TARGET_P
        JMP BAD_CPU
    J_TARGET_P:
        NOP
        ; Check JM taken path
        MVI A,080H
        ORA A
        JM J_TARGET_M
        JMP BAD_CPU
    J_TARGET_M:
        NOP
        ; CNZ: only not-taken path is safe without RAM
        MVI A,00H
        ORA A
        CNZ BAD_CPU
        NOP
        ; CZ: only not-taken path is safe without RAM
        MVI A,01H
        ORA A
        CZ BAD_CPU
        NOP
        ; CNC: only not-taken path is safe without RAM
        STC
        CNC BAD_CPU
        NOP
        ; CC: only not-taken path is safe without RAM
        MVI A,01H
        ORA A
        CC BAD_CPU
        NOP
        ; CPO: only not-taken path is safe without RAM
        MVI A,00H
        ORA A
        CPO BAD_CPU
        NOP
        ; CPE: only not-taken path is safe without RAM
        MVI A,01H
        ORA A
        CPE BAD_CPU
        NOP
        ; CP: only not-taken path is safe without RAM
        MVI A,080H
        ORA A
        CP BAD_CPU
        NOP
        ; CM: only not-taken path is safe without RAM
        MVI A,00H
        ORA A
        CM BAD_CPU
        NOP
        LXI H, TARGET_PCHL
        PCHL          ; jumps via HL, uses no stack
        JMP BAD_CPU
    TARGET_PCHL:
        DI
        JMP SUCCESS

    ; ===== Секция 11. Звуковая сигнализация через INTE ====
    ; Success: three SHORT pips (~80ms each) and HLT.
    ; Failure checksum: one LONG beep (~0.21s).
    ; Failure address: two LONG beeps.
    ; Failure ROM data: three LONG beeps.
    ; Failure CPU opcode test: four LONG beeps.
    ; All error paths HALT; RESET is needed for another test.
    SUCCESS:
        MVI D, 03H        ; three short beeps
        MVI E, 05AH       ; beep length 90 cycles
        MVI H, 041H       ; 4100h pause
        JMP REPORT_BEEP
    BAD_CHECKSUM:
        MVI D, 01H
        JMP REPORT_ERROR
    BAD_ADDRESS:
        MVI D, 02H
        JMP REPORT_ERROR
    BAD_DATA:
        MVI D, 03H
        JMP REPORT_ERROR
    BAD_CPU:
        MVI D, 04H
        JMP REPORT_ERROR
    REPORT_ERROR:
        DI
        MVI E, 0E6H      ; beep length 230 cycles
        MVI H, 04AH       ; 4A00h pause
    REPORT_BEEP:
        MOV B,E
    REPORT_CYCLE:
        EI
        MVI C, 105
    REPORT_HIGH:
        DCR C
        JNZ REPORT_HIGH
        DI
        MVI C, 105
    REPORT_LOW:
        DCR C
        JNZ REPORT_LOW
        DCR B
        JNZ REPORT_CYCLE
        DI
        DCR D
        JZ DONE
        MOV B,H
        MVI C, 000H
    REPORT_PAUSE:
        DCX B
        MOV A,B
        ORA C
        JNZ REPORT_PAUSE
        JMP REPORT_BEEP
    DONE:
        DI             ; keep INTE low and INT disabled
        HLT            ; stop until RESET (or external intervention)
    END
