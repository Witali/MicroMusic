; Intel 8080, 64 KiB ROM self-test, CRC-16, 31 bytes
; Polynomial: 0x00FF (nonstandard, reducible; not primitive).
; Initial CRC: 0x0000; CRC footer at FFFEh and FFFFh, MSB first.
; Thanks to 0x00FF feedback, SBB A itself produces the mask.
; No RAM or stack. INTE is 1 on pass, 0 on fail after RESET.

        ORG 0000H
        XRA A
        MOV D,A
        MOV E,A
        MOV H,A
        MOV L,A
NEXT:   LDAX D
        XRA H
        MOV H,A
        MVI B,8
BIT:    DAD H
        SBB A           ; A = 00h or FFh, already the feedback mask
        XRA L
        MOV L,A
        DCR B
        JNZ BIT
        INX D
        MOV A,D
        ORA E
        JNZ NEXT
        MOV A,H
        ORA L
        JNZ FINISH
        EI
FINISH: HLT
