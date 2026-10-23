; Intel 8080 ROM CRC-16, table-free, 38 bytes (speed-focused compromise).
; Polynomial 0x001B => x^16 + x^4 + x^3 + x + 1.
; WARNING: reducible polynomial; double-bit period is only 59055 bits,
; compared with 65535 for the preferred primitive polynomial 0x002D.
; CRC init=0, MSB-first, xorout=0; two footer bytes at FFFEh/FFFFh.
; DE=read address, H=CRC_hi, C=CRC_lo, B/L scratch.
; CRC step: t = byte XOR old_hi; u=t^(t<<1); w=u^(u<<3);
;           newCRC=(oldCRC_lo<<8) XOR w.
; NO RAM, stack, tables or interrupts. Run immediately after hardware RESET.
        ORG 0000H
        XRA A
        MOV D,A
        MOV E,A
        MOV H,A
        MOV C,A
NEXT:   LDAX D
        XRA H
        MOV L,A
        MVI H,0
        DAD H           ; <<1
        XRA L           ; u_low = t XOR (t<<1)
        MOV L,A
        MOV B,L
        MOV A,H
        DAD H           ; <<1
        DAD H           ; <<2
        DAD H           ; <<3
        XRA H
        XRA C
        MOV H,A
        MOV A,L
        XRA B
        MOV C,A
        INR E
        JNZ NEXT
        INR D
        JNZ NEXT
        ORA H
        JNZ FINISH
        EI
FINISH: HLT
