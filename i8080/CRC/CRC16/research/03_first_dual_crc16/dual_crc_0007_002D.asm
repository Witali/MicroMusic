; Intel 8080 dual-CRC full 64 KiB ROM verifier - STRONGER LOCAL profile
; Two independent table-free CRC-16 checks; same ROM, twice.
; P1=0x0007 (all odd bit counts); P2=0x002D (primitive period 65535)
; Common degree-32 generator; CRC init=0, 4-byte combined footer.
; No RAM, stack or lookup tables.
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
        ; CRC1=0, A=0
        MOV D,A
        MOV E,A
        MOV H,A
        MOV C,A
P2_NEXT: LDAX D
        XRA H
        MOV L,A
        MVI H,0
        DAD H
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
