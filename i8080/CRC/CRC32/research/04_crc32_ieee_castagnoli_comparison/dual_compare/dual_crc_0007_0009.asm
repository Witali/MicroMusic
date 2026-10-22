; Intel 8080 dual-CRC full 64 KiB ROM verifier - FAST profile
; Two independent table-free CRC-16 checks, passes over *same* ROM
; P1 = 0x0007; P2 = 0x0009; gcd(G1,G2) = 1; equivalent generator degree 32.
; CRC init=0; no reflection; xorout=0; 4-byte combined CRC footer.
; No RAM, stack, CALL or extra tables; requires contiguous ROM mapping of 64 KiB.
; INTE stays disabled on any failed check; EI on two successful passes.
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
        ; CRC1 = 0 -> A = 0. Reuse this zero to initialize pass 2.
        MOV D,A
        MOV E,A
        MOV H,A
        MOV C,A
        MOV B,A
P2_NEXT: LDAX D
        XRA H
        MOV L,A
        MOV H,B
        DAD H
        DAD H
        DAD H
        XRA L
        MOV L,A
        MOV A,H
        XRA C
        MOV H,A
        MOV C,L
        INR E
        JNZ P2_NEXT
        INR D
        JNZ P2_NEXT
        ORA C
        JNZ FAIL
        EI
FAIL:   HLT
