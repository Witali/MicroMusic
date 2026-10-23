; Intel 8080 dual CRC16, balanced-local-4bit profile
; P1=0x0007, P2=0x001B, coprime, combined degree-32 generator.
; No RAM, stack, lookup tables. Scan ROM twice, 4 CRC footer bytes.
        ORG 0000H
        XRA A
        MOV D,A
        MOV E,A
        MOV H,A
        MOV C,A
P1_NEXT: LDAX D
        XRA H
        MOV B,A
        MOV L,A
        MVI H,0
        DAD H
        XRA L
        MOV L,A
        DAD H
        MOV A,B
        XRA L
        MOV L,A
        MOV A,H
        XRA C
        MOV H,A
        MOV C,L
        INR E
        JNZ P1_NEXT
        INR D
        JNZ P1_NEXT
        ORA C
        JNZ FAIL
        ; A=0 after successful check
        MOV D,A
        MOV E,A
        MOV H,A
        MOV C,A
P2_NEXT: LDAX D
        XRA H
        MOV L,A
        MVI H,0
        DAD H
        XRA L
        MOV L,A
        MOV B,L
        MOV A,H
        DAD H
        DAD H
        DAD H
        XRA H
        XRA C
        MOV H,A
        MOV A,L
        XRA B
        MOV C,A
        INR E
        JNZ P2_NEXT
        INR D
        JNZ P2_NEXT
        ORA H
        JNZ FAIL
        EI
FAIL:   HLT
