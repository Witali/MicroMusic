; Intel 8080 CRC-16 polynomial 0x0007: x^16+x^2+x+1
; No tables, RAM, or stack. Read all 64 KiB. CRC init=0; final=0.
; DE address, H CRC high, C CRC low, B scratch, L scratch.
; t=byte XOR crcHigh
; w = t*(1+x+x^2) = t XOR 2*(t XOR 2*t), calculated as 16-bit GF(2)
        ORG 0000H
        XRA A
        MOV D,A
        MOV E,A
        MOV H,A
        MOV C,A
NEXT:   LDAX D
        XRA H
        MOV B,A           ; save t
        MOV L,A           ; HL=t
        MVI H,0
        DAD H             ; HL = t<<1
        XRA L             ; A = t XOR low(t<<1)
        MOV L,A           ; HL = t XOR (t<<1)
        DAD H             ; HL = (t<<1) XOR (t<<2)
        MOV A,B           ; restore t
        XRA L             ; XOR t
        MOV L,A           ; new low
        MOV A,H
        XRA C             ; new high
        MOV H,A
        MOV C,L
        INR E
        JNZ NEXT
        INR D
        JNZ NEXT
        ORA C
        JNZ FINISH
        EI
FINISH: HLT
