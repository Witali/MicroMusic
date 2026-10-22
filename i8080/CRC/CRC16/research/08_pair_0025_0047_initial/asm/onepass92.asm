; Intel 8080, one-pass CRC-16 0x0025 + 0x0047, no RAM or lookup tables
; BC CRC 0x25, DE CRC 0x47; SP ROM data pointer, L byte counter.
ORG 0000H
        DI
        LXI SP,0FFFFH
        XRA A
        MOV B,A
        MOV C,A
        MOV D,A
        MOV E,A
        MOV L,A
NEXT:   POP PSW
        DCX SP
        XRA B
        MOV H,A          ; t25=b xor crc25hi
        XRA B
        XRA D
        MOV D,A          ; t47=b xor crc47hi

        ; CRC47 FIRST. A is already t47, D=t47, H=t25.
        RLC
        RLC
        ANI 03H         ; x=t47>>6
        MOV B,A          ; save x
        RAR
        XRA B           ; t47>>7 xor t47>>6
        XRA E
        MOV E,A          ; high partial
        MOV A,D
        RRC
        RRC
        MOV B,A          ; ror2(t47)
        ANI 03FH         ; t47>>2
        XRA E
        MOV E,A          ; new high
        MOV A,B
        ANI 0C0H         ; t47<<6 low
        MOV B,A
        MOV A,D
        ADD A
        XRA D
        ADD A
        XRA D
        XRA B
        MOV D,E
        MOV E,A          ; new low CRC47

        ; CRC 0x0025 using 8-bit rotate and carryless shifts.
        ; t1 is H; old crc low is C; D holds t2.
        MOV A,H
        RRC
        RRC
        RRC
        MOV B,A          ; ror3(t1)
        ANI 01FH        ; t1 >> 3
        XRA C
        MOV C,A          ; upper partial
        MOV A,H
        RLC
        RLC
        ANI 03H         ; t1 >> 6
        XRA C
        MOV C,A          ; new upper CRC25
        MOV A,B
        ANI 0E0H        ; t1 << 5 (low 8 bits)
        MOV B,A
        MOV A,H
        ADD A
        ADD A
        XRA H           ; t1 ^ (t1 << 2)
        XRA B           ; new lower CRC25
        MOV B,C
        MOV C,A

        INR L
        JNZ NEXT
        MOV H,L
        INR L
        DAD SP
        JNC NEXT
        MOV A,B
        ORA C
        ORA D
        ORA E
        JNZ FAIL
        EI
FAIL:   HLT
