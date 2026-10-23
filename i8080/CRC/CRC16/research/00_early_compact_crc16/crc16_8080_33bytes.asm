; Intel 8080, 64 KiB ROM self-test, CRC-16, 33 bytes
; Polynomial: 0x002D (x^16 + x^5 + x^3 + x^2 + 1)
; Initial CRC: 0x0000; byte order: MSB first; no final XOR.
; ROM[0xFFFE:0x10000] = CRC over ROM[0:0xFFFE], MSB first.
; Full-ROM CRC residue must equal 0. No RAM or stack needed.
; INTE: 1 on success, 0 on failure; intended to run after RESET.

        ORG 0000H

        XRA A           ; A=0
        MOV D,A         ; DE = ROM address 0000h
        MOV E,A
        MOV H,A         ; HL = CRC accumulator 0000h
        MOV L,A

NEXT:   LDAX D          ; Read ROM byte at address DE
        XRA H           ; XOR incoming byte into high CRC byte
        MOV H,A
        MVI B,8         ; Process eight bits

BIT:    DAD H           ; HL <<= 1; CY = outgoing bit 15
        SBB A           ; A = 00h if CY=0, FFh if CY=1
        ANI 02DH        ; A = 00h or 2Dh (polynomial low byte)
        XRA L           ; XOR CRC feedback into its low byte
        MOV L,A
        DCR B
        JNZ BIT

        INX D           ; Next ROM byte
        MOV A,D
        ORA E
        JNZ NEXT        ; Continue until DE wraps to 0000h

        MOV A,H         ; Final CRC == 0?
        ORA L
        JNZ FINISH      ; Failure: INTE stays low after RESET
        EI              ; Success: INTE rises
FINISH: HLT             ; Both paths stop here
