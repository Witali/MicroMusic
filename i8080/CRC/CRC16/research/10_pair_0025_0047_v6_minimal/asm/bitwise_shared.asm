; Intel 8080, dual CRC-16 polynomial 0x0025 + 0x0047
; Shared bitwise CRC kernel. No RAM, no stack, no lookup tables.
; H:L = CRC; D:E = ROM pointer; C = polynomial low byte; B = bit count
; CRC init 0000h. Compare zero residue. FFFC..FFFF = 4-byte common footer.
        ORG 0000H
        DI
        XRA A
        MOV D,A
        MOV E,A
        MOV H,A
        MOV L,A
        MVI C,025H
NEXT:   LDAX D
        XRA H
        MOV H,A
        MVI B,8
BIT:    DAD H
        SBB A
        ANA C
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
        JNZ FAIL
        MOV A,C
        XRI 062H     ; switch 25h <-> 47h
        MOV C,A
        ANI 040H     ; 47h -> next pass; 25h -> done
        JNZ NEXT
        EI
FAIL:   HLT
