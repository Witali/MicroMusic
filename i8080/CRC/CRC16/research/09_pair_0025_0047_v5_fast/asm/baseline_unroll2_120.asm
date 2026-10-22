; Two-pass unrolled x2; 0x0025 + 0x0047. No RAM.
; Intel 8080 dual-CRC16 p=0025 + p=0047, 2 passes, no RAM or tables.
; DE=ROM pointer; HC=CRC (high/low); B=input scratch; HL polynomial workspace.
ORG 0000H
    DI
    XRA A
    MOV D,A
    MOV E,A
    MOV H,A
    MOV C,A

; poly 0x0025: 1+x^2+x^5 = 1 + x^2(1+x^3)
FIRST: LDAX D
    XRA H
    MOV B,A
    MOV L,A
    MVI H,0
    DAD H
    DAD H
    DAD H
    XRA L
    MOV L,A
    DAD H
    DAD H
    MOV A,H
    XRA C
    MOV H,A
    MOV A,B
    XRA L
    MOV C,A
    INX D
    LDAX D
    XRA H
    MOV B,A
    MOV L,A
    MVI H,0
    DAD H
    DAD H
    DAD H
    XRA L
    MOV L,A
    DAD H
    DAD H
    MOV A,H
    XRA C
    MOV H,A
    MOV A,B
    XRA L
    MOV C,A
    INR E
    JNZ FIRST
    INR D
    JNZ FIRST
    ORA H             ; A=C after last processed byte
    JNZ FAIL
    ; H,C already zero after a successful CRC check.

; poly 0x0047: 1+x+x^2+x^6 = 1+x(1+x(1+x^4))
SECOND: LDAX D
    XRA H
    MOV B,A
    MOV L,A
    MVI H,0
    DAD H
    DAD H
    DAD H
    DAD H
    MOV A,L
    XRA B
    MOV L,A
    DAD H
    MOV A,L
    XRA B
    MOV L,A
    DAD H
    MOV A,H
    XRA C
    MOV H,A
    MOV A,L
    XRA B
    MOV C,A
    INX D
    LDAX D
    XRA H
    MOV B,A
    MOV L,A
    MVI H,0
    DAD H
    DAD H
    DAD H
    DAD H
    MOV A,L
    XRA B
    MOV L,A
    DAD H
    MOV A,L
    XRA B
    MOV L,A
    DAD H
    MOV A,H
    XRA C
    MOV H,A
    MOV A,L
    XRA B
    MOV C,A
    INR E
    JNZ SECOND
    INR D
    JNZ SECOND
    ORA H             ; A=C after last processed byte
    JNZ FAIL
    EI
FAIL: HLT
