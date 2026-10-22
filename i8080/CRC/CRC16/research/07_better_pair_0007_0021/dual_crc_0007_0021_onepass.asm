; Intel 8080 dual CRC-16, optimized fused iteration v2.
; Same polynomials 0x0007 and 0x0021, all 65536 bytes, 4-byte footer.
; BC: CRC-16/0x0007, DE: CRC-16/0x0021, SP ROM reader, L counter.
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
        MOV H,A          ; t1 = data ^ B
        XRA B
        XRA D
        MOV D,A          ; t2 = data ^ D, and A=t2

        ; Process CRC 0x0021 FIRST: accumulator already holds t2!
        RRC
        RRC
        RRC
        MOV B,A          ; B available (old B already consumed)
        ANI 01FH
        XRA E
        MOV E,A          ; temporarily E=new high
        MOV A,B
        ANI 0E0H
        XRA D
        MOV D,E
        MOV E,A

        ; CRC 0x0007, t1 preserved in H throughout above calculation
        MOV A,H
        RLC
        RLC
        ANI 003H
        MOV B,A
        RAR
        XRA B
        XRA C
        MOV B,A
        MOV A,H
        ADD A
        XRA H
        ADD A
        XRA H
        MOV C,A

        INR L
        JNZ NEXT
        MOV H,L         ; L is 0 after INR L overflow
        INR L           ; HL = 0001h in two bytes, still 10 T
        DAD SP
        JNC NEXT

        MOV A,B
        ORA C
        ORA D
        ORA E
        JNZ FAIL
        EI
FAIL:   HLT
