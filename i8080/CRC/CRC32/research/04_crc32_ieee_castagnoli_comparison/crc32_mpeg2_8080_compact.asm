; Intel 8080, 64-KiB ROM self-test: CRC-32/MPEG-2 (MSB-first)
; polynomial 0x04C11DB7, init 0xFFFFFFFF, xorout 0, non-reflected.
; ROM[FFFC..FFFF] = CRC32 of ROM[0000..FFFB], most significant byte first.
; Successful validation: CRC32(ROM[0000..FFFF]) == 0.
; B:C:D:E = CRC32 MSB first, H:L = two ROM bytes read by POP H.
; SP points to ROM, and POP reads (does NOT write) ROM. Interrupts OFF.
; No RAM, no lookup table, no subroutines and no stack writes.
; All 65536 bytes checked. Requires real 64KiB mapped ROM.
        ORG 0000H
        DI
        LXI SP,0000H
        XRA A
        CMA
        MOV B,A
        MOV C,A
        MOV D,A
        MOV E,A
NEXT:   POP H             ; L = ROM[SP], H = ROM[SP+1]; SP+=2
        MOV A,L
        XRA B             ; CRC ^= first byte << 24
        MOV B,A
        MVI L,16          ; process two bytes in a common bit loop
BIT:    XCHG              ; swap CRC_low (DE) with temporary HL
        DAD H             ; CRC_low <<= 1, CY = carry to high half
        XCHG              ; restore temp HL; now DE = shifted CRC_low
        MOV A,C
        RAL               ; CRC_high <<= 1, including carry from low
        MOV C,A
        MOV A,B
        RAL
        MOV B,A           ; CY = former CRC bit31
        JNC NOXOR        ; if old msb=1: CRC ^= polynomial
        MOV A,B
        XRI 04H
        MOV B,A
        MOV A,C
        XRI C1H
        MOV C,A
        MOV A,D
        XRI 1DH
        MOV D,A
        MOV A,E
        XRI B7H
        MOV E,A
NOXOR:  DCR L
        JZ ENDP
        MOV A,L
        CPI 8             ; 8 bits remain -> switch to second byte
        JNZ BIT
        MOV A,H           ; second byte from POP
        XRA B
        MOV B,A
        JMP BIT
ENDP:
        ; Both input bytes processed. Test if POP advanced SP to 0000H.
        LXI H,0000H
        DAD SP            ; HL = SP, no memory accessed
        MOV A,H
        ORA L
        JNZ NEXT
        ; Full 64-KiB CRC is zero if ROM matches its footer.
        MOV A,B
        ORA C
        ORA D
        ORA E
        JNZ FAIL
        EI                ; result signal on INTE (hardware-dependent)
FAIL:   HLT               ; failure: interrupts disabled, success: enabled
